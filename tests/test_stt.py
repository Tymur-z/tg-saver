from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from moderation.stt_service import NvidiaSTTService
from bot.handlers.forward import handle_incoming_message
from database.connection import Database
from database.repositories.chat_repo import ChatRepository
from config.settings import Settings


def make_mock_message(
    chat_id: int,
    chat_type: str = "supergroup",
    text: str = "",
    user_id: int = 12345,
    user_name: str = "Тестовый Юзер",
    message_id: int = 100,
    voice: bool = False,
    video_note: bool = False,
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

    msg.text = text if (text and not voice and not video_note) else None
    msg.caption = None
    msg.media_group_id = None
    msg.entities = []
    msg.reply_to_message = reply_to
    msg.reply = AsyncMock()
    msg.delete = AsyncMock()
    msg.date = None
    msg.bot = MagicMock()
    msg.bot.send_chat_action = AsyncMock()

    if voice:
        v = MagicMock()
        v.file_id = "voice_file_123"
        v.file_unique_id = "unique_voice_123"
        msg.voice = v
    else:
        msg.voice = None

    if video_note:
        vn = MagicMock()
        vn.file_id = "vn_file_456"
        vn.file_unique_id = "unique_vn_456"
        msg.video_note = vn
    else:
        msg.video_note = None

    return msg


@pytest.fixture
def test_stt_service() -> NvidiaSTTService:
    stt = NvidiaSTTService(
        api_key="nvapi-mock-test-key",
        function_id="b702f636-f60c-4a3d-a6f4-f3568c13bd7d",
        uri="grpc.nvcf.nvidia.com:443",
        language_code="ru-RU",
        enabled=True,
    )
    # Mock internal ASR service
    mock_asr = MagicMock()
    mock_result = MagicMock()
    mock_alt = MagicMock()
    mock_alt.transcript = "Привет, Ричард! Как твои дела?"
    mock_result.alternatives = [mock_alt]
    mock_resp = MagicMock()
    mock_resp.results = [mock_result]
    mock_asr.offline_recognize.return_value = mock_resp
    stt._asr_service = mock_asr
    return stt


def test_stt_init_and_cache(test_stt_service: NvidiaSTTService) -> None:
    assert test_stt_service.is_available() is True
    test_stt_service.set_cached_transcript("uniq_1", "Закешированный текст")
    assert test_stt_service.get_cached_transcript("uniq_1") == "Закешированный текст"
    assert test_stt_service.get_cached_transcript("non_existent") is None


@pytest.mark.asyncio
async def test_stt_transcribe_audio_bytes(test_stt_service: NvidiaSTTService) -> None:
    with patch.object(test_stt_service, "convert_to_pcm16_wav", return_value=b"RIFF" + b"\x00" * 100):
        res = await test_stt_service.transcribe_audio_bytes(b"dummy_oga_bytes", cache_key="cache_key_test")
        assert res == "Привет, Ричард! Как твои дела?"
        # Verify cached
        assert test_stt_service.get_cached_transcript("cache_key_test") == "Привет, Ричард! Как твои дела?"


@pytest.mark.asyncio
async def test_stt_reply_to_voice_transcribe_command(test_db: Database, test_stt_service: NvidiaSTTService) -> None:
    """When a user replies with '/transcribe' or 'текст' to a voice message, bot replies with transcription."""
    settings = Settings(BOT_TOKEN="123:ABC", OWNER_ID=999, ANALYTICS_ENABLED=False)
    mock_forward_engine = AsyncMock()
    mock_profiler = AsyncMock()

    voice_msg = make_mock_message(chat_id=-100123, voice=True)
    user_cmd_msg = make_mock_message(chat_id=-100123, text="текст", reply_to=voice_msg)

    with patch.object(test_stt_service, "transcribe_telegram_file", return_value="Привет из голосового!"):
        await handle_incoming_message(
            message=user_cmd_msg,
            forward_engine=mock_forward_engine,
            style_profiler=mock_profiler,
            settings=settings,
            db=test_db,
            stt_service=test_stt_service,
        )

    user_cmd_msg.reply.assert_called_once()
    reply_call = user_cmd_msg.reply.call_args[0][0]
    assert "Расшифровка (Голосовое):" in reply_call
    assert "Привет из голосового!" in reply_call


@pytest.mark.asyncio
async def test_stt_auto_transcribe_in_chat(test_db: Database, test_stt_service: NvidiaSTTService) -> None:
    """When stt_auto_transcribe is 1 in chat, bot automatically replies to the incoming circle/voice with text."""
    settings = Settings(BOT_TOKEN="123:ABC", OWNER_ID=999, ANALYTICS_ENABLED=False)
    mock_forward_engine = AsyncMock()
    mock_profiler = AsyncMock()

    chat_id = -100555
    async with test_db.connect() as conn:
        repo = ChatRepository(conn)
        await repo.upsert_chat(chat_id=chat_id, title="Auto Transcribe Chat", chat_type="supergroup")
        await conn.execute("UPDATE chats SET stt_enabled = 1, stt_auto_transcribe = 1 WHERE chat_id = ?", (chat_id,))
        await conn.commit()

    circle_msg = make_mock_message(chat_id=chat_id, video_note=True)

    with patch.object(test_stt_service, "transcribe_telegram_file", return_value="Смотрите какое классное видео!"):
        await handle_incoming_message(
            message=circle_msg,
            forward_engine=mock_forward_engine,
            style_profiler=mock_profiler,
            settings=settings,
            db=test_db,
            stt_service=test_stt_service,
        )

    circle_msg.reply.assert_called_once()
    reply_text = circle_msg.reply.call_args[0][0]
    assert "Расшифровка (Кружок):" in reply_text
    assert "Смотрите какое классное видео!" in reply_text


@pytest.mark.asyncio
async def test_stt_voice_triggers_companion_richard(test_db: Database, test_stt_service: NvidiaSTTService) -> None:
    """When a voice message addressing Richard arrives, Richard understands it and generates a response!"""
    from moderation.companion import ChatCompanion
    from moderation.llm_client import LLMClient

    settings = Settings(BOT_TOKEN="123:ABC", OWNER_ID=999, ANALYTICS_ENABLED=False)
    mock_forward_engine = AsyncMock()
    mock_profiler = AsyncMock()

    mock_llm = AsyncMock(spec=LLMClient)
    mock_llm.api_key = "test-key"
    mock_llm.chat_completion.return_value = "Привет! Я отлично слышу твой голосовой кружок."

    companion = ChatCompanion(llm_client=mock_llm)
    companion._bot_user = MagicMock(id=7761395820, username="RichardHelperBot")

    chat_id = -100888
    async with test_db.connect() as conn:
        repo = ChatRepository(conn)
        await repo.upsert_chat(chat_id=chat_id, title="Companion AI Chat", chat_type="supergroup")
        await conn.execute("UPDATE chats SET chat_ai_enabled = 1, stt_enabled = 1 WHERE chat_id = ?", (chat_id,))
        await conn.commit()

    voice_msg = make_mock_message(chat_id=chat_id, voice=True)

    with patch.object(test_stt_service, "transcribe_telegram_file", return_value="Ричард, какая сегодня погода?"):
        await handle_incoming_message(
            message=voice_msg,
            forward_engine=mock_forward_engine,
            style_profiler=mock_profiler,
            settings=settings,
            db=test_db,
            companion=companion,
            stt_service=test_stt_service,
        )

    voice_msg.reply.assert_called_once()
    reply_text = voice_msg.reply.call_args[0][0]
    assert "Привет! Я отлично слышу твой голосовой кружок." in reply_text
