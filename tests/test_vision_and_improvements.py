# -*- coding: utf-8 -*-
from __future__ import annotations

import io
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from PIL import Image

from moderation.vision_service import VisionService
from moderation.llm_client import LLMClient
from moderation.companion import ChatCompanion
from bot.handlers.forward import is_transcription_request, handle_incoming_message
from config.settings import Settings
from database.connection import Database
from database.repositories.chat_repo import ChatRepository


def create_test_image(width: int = 2000, height: int = 1500, color: str = "blue") -> bytes:
    img = Image.new("RGB", (width, height), color=color)
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def make_mock_message(
    chat_id: int,
    chat_type: str = "supergroup",
    text: str = "",
    caption: str = "",
    user_id: int = 12345,
    user_name: str = "Тестовый Юзер",
    message_id: int = 100,
    photo: bool = False,
    reply_to: MagicMock = None,
) -> MagicMock:
    msg = MagicMock()
    msg.message_id = message_id
    msg.chat = MagicMock()
    msg.chat.id = chat_id
    msg.chat.type = chat_type
    msg.chat.title = "Тестовый Чат"
    msg.chat.username = "testchat"

    msg.from_user = MagicMock()
    msg.from_user.id = user_id
    msg.from_user.first_name = user_name
    msg.from_user.full_name = user_name
    msg.from_user.username = "testuser"

    msg.text = text if text else None
    msg.caption = caption if caption else None
    msg.media_group_id = None
    msg.entities = []
    msg.reply_to_message = reply_to
    msg.reply = AsyncMock()
    msg.delete = AsyncMock()
    msg.date = None
    msg.bot = MagicMock()
    msg.bot.send_chat_action = AsyncMock()
    msg.bot.get_file = AsyncMock()
    msg.bot.download_file = AsyncMock()
    msg.voice = None
    msg.video_note = None
    msg.audio = None

    if photo:
        p1 = MagicMock(file_id="f_small", file_unique_id="u_small", width=320, height=240)
        p2 = MagicMock(file_id="f_large", file_unique_id="u_large", width=1600, height=1200)
        msg.photo = [p1, p2]
    else:
        msg.photo = None

    return msg


def test_transcription_keywords_quote_and_video_typos() -> None:
    # 1. Quoting commands in reply to media
    assert is_transcription_request("Ричард процитируй", is_reply_to_media=True)
    assert is_transcription_request("процитируй", is_reply_to_media=True)
    assert is_transcription_request("цитируй", is_reply_to_media=True)
    assert is_transcription_request("повтори", is_reply_to_media=True)
    assert is_transcription_request("Ричард повтори", is_reply_to_media=True)

    # 2. Typos like видеокурске / произнес
    assert is_transcription_request("Я попросил чётко сказать что я произнес на видеокурске")
    assert is_transcription_request("что я произнес на видеокружке")
    assert is_transcription_request("что он произнес в кружке")
    assert is_transcription_request("процитируй кружок")
    assert is_transcription_request("процитируй голосовое")


def test_vision_service_optimize_image() -> None:
    service = VisionService(enabled=True, max_dimension=800, jpeg_quality=80)
    raw = create_test_image(width=2000, height=1000)
    b64 = service.optimize_image_bytes(raw)
    assert b64 is not None

    import base64
    decoded = base64.b64decode(b64)
    with Image.open(io.BytesIO(decoded)) as res_img:
        assert max(res_img.size) <= 800
        assert res_img.format == "JPEG"


@pytest.mark.asyncio
async def test_vision_service_download_and_cache() -> None:
    service = VisionService(enabled=True, max_dimension=1024)
    raw = create_test_image(width=1200, height=800)

    mock_bot = MagicMock()
    mock_file = MagicMock(file_path="photos/file_0.jpg")
    mock_bot.get_file = AsyncMock(return_value=mock_file)

    async def fake_download(path, destination):
        destination.write(raw)
    mock_bot.download_file = AsyncMock(side_effect=fake_download)

    p_size = MagicMock(file_id="p123", file_unique_id="uniq_p123", width=1200, height=800)
    res_b64 = await service.download_and_process_photo(mock_bot, [p_size])
    assert res_b64 is not None
    assert mock_bot.get_file.call_count == 1

    # Second call should use RAM cache without re-downloading
    cached_b64 = await service.download_and_process_photo(mock_bot, [p_size])
    assert cached_b64 == res_b64
    assert mock_bot.get_file.call_count == 1  # Unchanged!


@pytest.mark.asyncio
async def test_companion_multimodal_reply_structure() -> None:
    mock_llm = AsyncMock(spec=LLMClient)
    mock_llm.api_key = "test-key"
    mock_llm.chat_completion.return_value = "На фото вижу мешок штукатурки и профили."

    companion = ChatCompanion(llm_client=mock_llm)
    reply = await companion.generate_reply(
        chat_id=123,
        user_name="MixaRed",
        user_prompt="Что тут на фото дай краткую смету",
        image_base64="BASE64_IMAGE_DATA_MOCK",
        image_detail="auto",
    )
    assert reply == "На фото вижу мешок штукатурки и профили."
    call_args = mock_llm.chat_completion.call_args[1]["messages"]
    user_msg = [m for m in call_args if m["role"] == "user"][-1]
    assert isinstance(user_msg["content"], list)
    assert user_msg["content"][0]["type"] == "text"
    assert "Что тут на фото дай краткую смету" in user_msg["content"][0]["text"]
    assert user_msg["content"][1]["type"] == "image_url"
    assert "BASE64_IMAGE_DATA_MOCK" in user_msg["content"][1]["image_url"]["url"]


def test_no_repetitive_bazar_phrase_in_rules() -> None:
    companion = ChatCompanion()
    sys_prompt = companion.get_effective_system_prompt(is_owner=True)

    # Must contain prohibition against repeating "Понял, базар фильтрую. Проехали."
    assert "СТРОЖАЙШИЙ ЗАПРЕТ повторять одну и ту же заезженную фразу ('Понял, базар фильтрую. Проехали.')" in sys_prompt
    assert "VISION" in sys_prompt
    assert "РАСПОЗНАВАНИЕ И ОБСУЖДЕНИЕ ФОТОГРАФИЙ" in sys_prompt


@pytest.mark.asyncio
async def test_forward_photo_vision_flow(test_db: Database) -> None:
    """End-to-end forward flow: user sends a photo, then asks Richard what he thinks about it."""
    settings = Settings(BOT_TOKEN="123:ABC", OWNER_ID=911338473, ANALYTICS_ENABLED=False)
    mock_forward_engine = AsyncMock()
    mock_profiler = AsyncMock()

    mock_llm = AsyncMock(spec=LLMClient)
    mock_llm.api_key = "valid-key"
    mock_llm.chat_completion.return_value = "Вижу мешок цемента и перфоратор на полу."

    companion = ChatCompanion(llm_client=mock_llm)
    companion._bot_user = MagicMock(id=7761395820, username="RichardHelperBot")

    vision_service = VisionService(llm_client=mock_llm, enabled=True)
    raw_img = create_test_image(800, 600)
    with patch.object(vision_service, "download_and_process_photo", AsyncMock(return_value="FAKE_B64")):
        chat_id = -100999
        async with test_db.connect() as conn:
            repo = ChatRepository(conn)
            await repo.upsert_chat(chat_id=chat_id, title="Test Group", chat_type="supergroup")
            await conn.execute("UPDATE chats SET chat_ai_enabled = 1 WHERE chat_id = ?", (chat_id,))
            await conn.commit()

        # Step 1: User sends a photo
        photo_msg = make_mock_message(chat_id=chat_id, photo=True, user_id=5956803305, user_name="MixaRed")
        await handle_incoming_message(
            message=photo_msg,
            forward_engine=mock_forward_engine,
            style_profiler=mock_profiler,
            settings=settings,
            db=test_db,
            companion=companion,
            vision_service=vision_service,
        )

        # Step 2: User asks "Ричард что про фото думаешь?"
        ask_msg = make_mock_message(chat_id=chat_id, text="Ричард что про фото думаешь?", user_id=5956803305, user_name="MixaRed")
        await handle_incoming_message(
            message=ask_msg,
            forward_engine=mock_forward_engine,
            style_profiler=mock_profiler,
            settings=settings,
            db=test_db,
            companion=companion,
            vision_service=vision_service,
        )

        ask_msg.reply.assert_called_once()
        reply_sent = ask_msg.reply.call_args[0][0]
        assert "Вижу мешок цемента и перфоратор на полу." in reply_sent

        # Check that LLM received image_url
        call_msgs = mock_llm.chat_completion.call_args[1]["messages"]
        user_msg = [m for m in call_msgs if m["role"] == "user"][-1]
        assert any(p.get("type") == "image_url" for p in user_msg["content"])


def test_snowrunner_prohibition_in_rules() -> None:
    companion = ChatCompanion()
    sys_prompt = companion.get_effective_system_prompt(is_owner=False)

    assert "СТРОЖАЙШИЙ ЗАПРЕТ НА СПАМ СЛОВОМ «SnowRunner» / «сноуранер»" in sys_prompt
    assert "застрявшие в болоте грузовики в SnowRunner" not in sys_prompt
    assert "Ты в SnowRunner сначала из канавы выедь" not in sys_prompt


@pytest.mark.asyncio
async def test_snowrunner_post_guard_cleanup() -> None:
    mock_llm = AsyncMock(spec=LLMClient)
    mock_llm.api_key = "valid-key"
    # LLM hallucinated SnowRunner into an unrelated photo response:
    mock_llm.chat_completion.return_value = (
        "На фото набор для косплея. Если ты решил примерить это на себя, то у Миши в SnowRunner будет больше поводов для смеха, чем для зависти!"
    )
    companion = ChatCompanion(llm_client=mock_llm)

    # User didn't ask about SnowRunner:
    reply = await companion.generate_reply(
        chat_id=123,
        user_name="Тимур",
        user_prompt="Ричард, что думаешь по фото?",
        is_owner=True,
    )
    assert "SnowRunner" not in reply
    assert "то у Миши будет больше поводов для смеха" in reply

    # If user explicitly asked about SnowRunner, it shouldn't be stripped:
    mock_llm.chat_completion.return_value = "SnowRunner — отличная игра для замесов в грязи."
    reply_game = await companion.generate_reply(
        chat_id=123,
        user_name="MixaRed",
        user_prompt="Как тебе игра SnowRunner?",
        is_owner=False,
    )
    assert "SnowRunner" in reply_game


def test_fuflyzhnik_prohibition_in_rules() -> None:
    companion = ChatCompanion()
    sys_prompt = companion.get_effective_system_prompt(is_owner=False)

    assert "СТРОЖАЙШИЙ ЗАПРЕТ НА СПАМ СЛОВОМ «ФУФЛЫЖНИК» И «НАБОР ФУФЛЫЖНИКА»" in sys_prompt
    assert "СТРОЖАЙШИЙ ЗАПРЕТ НА РЖУЩИЕ И ШАБЛОННЫЕ СМАЙЛИКИ" in sys_prompt


@pytest.mark.asyncio
async def test_fuflyzhnik_and_emoji_post_cleanup() -> None:
    mock_llm = AsyncMock(spec=LLMClient)
    mock_llm.api_key = "valid-key"
    mock_llm.chat_completion.return_value = (
        "Слушай, Миша, этот набор для фуфлыжников на максималках выглядит стильно! 😄 Давай лучше обсудим этот набор фуфлыжника — кто из нас надел бы его первым?"
    )
    companion = ChatCompanion(llm_client=mock_llm)

    reply = await companion.generate_reply(
        chat_id=456,
        user_name="MixaRed",
        user_prompt="Тебе костюм понравился?",
        is_owner=False,
    )
    assert "фуфлыж" not in reply.lower()
    assert "😄" not in reply
    assert "кто из нас надел бы его первым" not in reply.lower()
    assert "Слушай, Миша" not in reply


@pytest.mark.asyncio
async def test_anti_parrot_duplicate_bot_reply() -> None:
    mock_llm = AsyncMock(spec=LLMClient)
    mock_llm.api_key = "valid-key"
    companion = ChatCompanion(llm_client=mock_llm)

    # Simulate bot already having said "Принял, торможу. Давай по делу, что конкретно нужно обсудить?"
    chat_id = 789
    companion.context_buffer.add_message(
        chat_id=chat_id,
        user_id=0,
        user_name="Ричард",
        text="Принял, торможу. Давай по делу, что конкретно нужно обсудить?",
        is_bot=True,
    )

    # LLM repeats the exact same text again:
    mock_llm.chat_completion.return_value = "Принял, торможу. Давай по делу, что конкретно нужно обсудить?"
    reply = await companion.generate_reply(
        chat_id=chat_id,
        user_name="Тимур",
        user_prompt="так, что теперь Ричард",
        is_owner=True,
    )
    # Anti-parrot must replace the duplicate!
    assert reply != "Принял, торможу. Давай по делу, что конкретно нужно обсудить?"
    assert "на связи" in reply or "Давай" in reply


@pytest.mark.asyncio
async def test_daily_memory_poison_sanitization() -> None:
    mock_llm = AsyncMock(spec=LLMClient)
    mock_llm.api_key = "valid-key"
    mock_llm.chat_completion.return_value = "Костюм топ, чисто для косплея."
    companion = ChatCompanion(llm_client=mock_llm)

    await companion.generate_reply(
        chat_id=999,
        user_name="Тимур",
        user_prompt="Оцени костюм",
        is_owner=True,
        daily_memory_summary="Сегодня участники чата обсуждали тему фуфлыжников и SnowRunner.",
        daily_memory_facts=["Обсуждение фуфлыжников и цундере стало основной темой дня.", "Нормальный факт про погоду."],
    )

    # Check messages passed to chat_completion
    call_msgs = mock_llm.chat_completion.call_args[1]["messages"]
    sys_mem = [m for m in call_msgs if m["role"] == "system" and "ХРОНИКА И СОБЫТИЯ" in m["content"]][0]
    assert "фуфлыж" not in sys_mem["content"].lower()
    assert "snowrunner" not in sys_mem["content"].lower()
    assert "Нормальный факт про погоду" in sys_mem["content"]


