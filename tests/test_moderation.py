"""Tests for profanity detection, LLM client, and per-chat moderation settings."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock

from database.connection import Database
from database.repositories.chat_repo import ChatRepository
from moderation.profanity import ProfanityDetector, ProfanityResult
from moderation.llm_client import LLMClient


@pytest.mark.asyncio
async def test_regex_profanity_detection() -> None:
    detector = ProfanityDetector(llm_enabled=False)

    # Obvious Russian profanities
    profane_samples = [
        "Пошел нахуй отсюда",
        "Полный пиздец творится",
        "Да ебать его в рот",
        "Бляяяяять, опять сломалось",
        "Ты конченый мудак",
        "Вот сука такая",
        "Ну ты и пидорас",
        "Гандон штопаный",
        "Дай 100 рублей, блять",
    ]
    for sample in profane_samples:
        res = await detector.check_text(sample)
        assert res.is_profane is True, f"Failed to detect profanity in: '{sample}'"
        assert res.method == "regex"


@pytest.mark.asyncio
async def test_regex_whitelist_clean_text() -> None:
    detector = ProfanityDetector(llm_enabled=False)

    clean_samples = [
        "Привет, как дела?",
        "Переведи мне 500 рублей пожалуйста",
        "Оформил страхование автомобиля",
        "Колебания на рынке ценных бумаг",
        "Купи свежий хлеб в магазине",
        "Употребление витаминов полезно для здоровья",
        "Он искренне влюблен в свою профессию",
    ]
    for sample in clean_samples:
        res = await detector.check_text(sample)
        assert res.is_profane is False, f"False positive profanity detection in: '{sample}'"


@pytest.mark.asyncio
async def test_detector_cache() -> None:
    detector = ProfanityDetector(llm_enabled=False)
    text = "Какое-то проверочное сообщение"

    res1 = await detector.check_text(text)
    assert text in detector._cache

    res2 = await detector.check_text(text)
    assert res1 is res2


@pytest.mark.asyncio
async def test_llm_profanity_fallback() -> None:
    mock_llm = AsyncMock(spec=LLMClient)
    mock_llm.chat_completion.return_value = '{"is_profane": true, "reason": "Скрытый мат", "confidence": 0.95}'

    detector = ProfanityDetector(llm_client=mock_llm, llm_enabled=True)
    # A phrase disguised without standard regex triggers
    res = await detector.check_text("какая-то замаскированная токсичность")

    assert res.is_profane is True
    assert res.method == "llm"
    assert res.reason == "Скрытый мат"
    mock_llm.chat_completion.assert_awaited_once()


@pytest.mark.asyncio
async def test_chat_repo_moderation_settings(test_db: Database) -> None:
    async with test_db.connect() as conn:
        repo = ChatRepository(conn)

        # 1. Add chats of different types
        await repo.upsert_chat(chat_id=-1001, title="Test Group", chat_type="supergroup")
        await repo.upsert_chat(chat_id=-1002, title="Test Channel", chat_type="channel")
        await repo.upsert_chat(chat_id=12345, title="Private Chat", chat_type="private")

        # 2. list_moderation_chats should return only supergroup and channel
        mod_chats = await repo.list_moderation_chats()
        chat_ids = [c["chat_id"] for c in mod_chats]
        assert -1001 in chat_ids
        assert -1002 in chat_ids
        assert 12345 not in chat_ids

        # 3. Default flags should be False (0)
        target = await repo.get_chat(-1001)
        assert target is not None
        assert target["profanity_filter_enabled"] == 0
        assert target["profanity_warn_enabled"] == 0
        assert target["profanity_delete_enabled"] == 0

        # 4. Toggle settings
        new_val = await repo.toggle_setting(-1001, "profanity_filter_enabled")
        assert new_val is True
        target = await repo.get_chat(-1001)
        assert target["profanity_filter_enabled"] == 1

        new_val = await repo.toggle_setting(-1001, "profanity_warn_enabled")
        assert new_val is True
        target = await repo.get_chat(-1001)
        assert target["profanity_warn_enabled"] == 1

        # Toggle back to False
        new_val = await repo.toggle_setting(-1001, "profanity_filter_enabled")
        assert new_val is False
        target = await repo.get_chat(-1001)
        assert target["profanity_filter_enabled"] == 0

        # Invalid field rejection
        with pytest.raises(ValueError):
            await repo.toggle_setting(-1001, "invalid_column_name")


@pytest.mark.asyncio
async def test_config_repo_llm_settings(test_db: Database) -> None:
    from database.repositories.config_repo import ConfigRepository

    async with test_db.connect() as conn:
        repo = ConfigRepository(conn)

        # 1. Defaults
        conf = await repo.get_llm_config(
            default_enabled=False,
            default_api_key="default_key",
            default_base_url="https://api.openai.com/v1",
            default_model="gpt-4o-mini",
        )
        assert conf["llm_enabled"] is False
        assert conf["llm_api_key"] == "default_key"
        assert conf["llm_base_url"] == "https://api.openai.com/v1"
        assert conf["llm_model"] == "gpt-4o-mini"

        # 2. Update config dynamically
        updated = await repo.set_llm_config(
            enabled=True,
            api_key="sk-new-secret-key",
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
            model="gemini-1.5-flash",
        )
        assert updated["llm_enabled"] is True
        assert updated["llm_api_key"] == "sk-new-secret-key"
        assert updated["llm_base_url"] == "https://generativelanguage.googleapis.com/v1beta/openai"
        assert updated["llm_model"] == "gemini-1.5-flash"

        # 3. Retrieve again
        persisted = await repo.get_llm_config()
        assert persisted["llm_enabled"] is True
        assert persisted["llm_api_key"] == "sk-new-secret-key"
        assert persisted["llm_model"] == "gemini-1.5-flash"


def test_llm_client_update_config() -> None:
    client = LLMClient(api_key="key1", base_url="https://api.openai.com/v1", model="gpt-4o-mini")
    assert client.api_key == "key1"
    assert client.model == "gpt-4o-mini"

    client.update_config(api_key="key2", model="gemini-1.5-flash", base_url="http://192.168.1.1:11434/v1/")
    assert client.api_key == "key2"
    assert client.model == "gemini-1.5-flash"
    assert client.base_url == "http://192.168.1.1:11434/v1"


@pytest.mark.asyncio
async def test_llm_client_test_connection_no_key() -> None:
    client = LLMClient(api_key="")
    success, msg, latency = await client.test_connection()
    assert success is False
    assert "не установлен" in msg

