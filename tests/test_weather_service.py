import pytest
import re
from unittest.mock import AsyncMock, patch
from moderation.weather_service import (
    is_weather_query,
    resolve_target_city,
    get_weather_summary,
    WMO_WEATHER_CODES,
)
from moderation.companion import COMMON_CHAT_RULES, ChatCompanion


def test_is_weather_query():
    assert is_weather_query("Какая погода") is True
    assert is_weather_query("холодно на улице?") is True
    assert is_weather_query("сколько градусов?") is True
    assert is_weather_query("идёт ли дождь?") is True
    assert is_weather_query("как дела бро") is False
    assert is_weather_query("") is False


def test_resolve_target_city():
    # Explicit city in prompt
    assert resolve_target_city("погода в Хаванте")[0] == "havant"
    assert resolve_target_city("что там в Hindhead")[0] == "hindhead"
    assert resolve_target_city("как там в Олтоне")[0] == "alton"

    # User ID defaults
    assert resolve_target_city("какая погода", user_id=5956803305)[0] == "alton"  # MixaRed
    assert resolve_target_city("какая погода", user_id=5985808271)[0] == "alton"  # Forsazh
    assert resolve_target_city("какая погода", user_id=1696889505)[0] == "havant" # Sol
    assert resolve_target_city("какая погода", user_id=5848551858)[0] == "hindhead" # Abyss

    # Fallback default
    assert resolve_target_city("какая погода", user_id=999999999)[0] == "alton"


@pytest.mark.asyncio
async def test_get_weather_summary_mocked():
    fake_weather = {
        "temperature": 7.5,
        "weathercode": 2,
        "windspeed": 12.0,
    }
    with patch("moderation.weather_service.fetch_current_weather", AsyncMock(return_value=fake_weather)):
        summary = await get_weather_summary("Какая погода", user_id=5956803305)
        assert summary is not None
        assert "ОЛТОНЕ" in summary
        assert "7.5°C" in summary
        assert "переменная облачность" in summary


@pytest.mark.asyncio
async def test_get_weather_summary_fallback():
    with patch("moderation.weather_service.fetch_current_weather", AsyncMock(return_value=None)):
        summary = await get_weather_summary("Какая погода", user_id=1696889505)
        assert summary is not None
        assert "Хаванте" in summary
        assert "Великобритания" in summary


def test_companion_rules_contain_uk_locations_and_vulgarity_ban():
    assert "ВЕЛИКОБРИТАНИИ" in COMMON_CHAT_RULES
    assert "Олтон" in COMMON_CHAT_RULES or "Alton" in COMMON_CHAT_RULES
    assert "Хавант" in COMMON_CHAT_RULES or "Havant" in COMMON_CHAT_RULES
    assert "Хайндхед" in COMMON_CHAT_RULES or "Hindhead" in COMMON_CHAT_RULES
    assert "порнографическ" in COMMON_CHAT_RULES.lower()


@pytest.mark.asyncio
async def test_companion_post_guard_strips_pornographic_metaphors():
    mock_llm = AsyncMock()
    mock_llm.api_key = "test-key"
    mock_llm.chat_completion.return_value = "Да там природу-порнографический шторм на улице."
    companion = ChatCompanion(llm_client=mock_llm)
    reply = await companion.generate_reply(chat_id=-100, user_name="MixaRed", user_prompt="какая погода")
    assert "порнографический" not in reply.lower()
