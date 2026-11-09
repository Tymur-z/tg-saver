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
    msg.bot.get_file = AsyncMock()
    msg.bot.download_file = AsyncMock()

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

    msg.audio = None

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


@pytest.mark.asyncio
async def test_reply_to_circle_asking_what_was_said(test_db: Database, test_stt_service: NvidiaSTTService) -> None:
    """When a user replies to a circle asking 'Ричард, что он сказал?' or 'что в кружке', it outputs pure transcription and does not chat."""
    from moderation.companion import ChatCompanion
    from moderation.llm_client import LLMClient

    settings = Settings(BOT_TOKEN="123:ABC", OWNER_ID=999, ANALYTICS_ENABLED=False)
    mock_forward_engine = AsyncMock()
    mock_profiler = AsyncMock()

    mock_llm = AsyncMock(spec=LLMClient)
    mock_llm.api_key = "test-key"
    companion = ChatCompanion(llm_client=mock_llm)

    chat_id = -100999
    async with test_db.connect() as conn:
        repo = ChatRepository(conn)
        await repo.upsert_chat(chat_id=chat_id, title="Test Group", chat_type="supergroup")
        await conn.execute("UPDATE chats SET chat_ai_enabled = 1, stt_enabled = 1 WHERE chat_id = ?", (chat_id,))
        await conn.commit()

    circle_msg = make_mock_message(chat_id=chat_id, video_note=True)
    user_ask_msg = make_mock_message(chat_id=chat_id, text="Ричард, что он сказал?", reply_to=circle_msg)

    with patch.object(test_stt_service, "transcribe_telegram_file", return_value="Секретная информация из кружка"):
        await handle_incoming_message(
            message=user_ask_msg,
            forward_engine=mock_forward_engine,
            style_profiler=mock_profiler,
            settings=settings,
            db=test_db,
            companion=companion,
            stt_service=test_stt_service,
        )

    # Bot must reply with transcription
    user_ask_msg.reply.assert_called_once()
    reply_call = user_ask_msg.reply.call_args[0][0]
    assert "Расшифровка (Кружок):" in reply_call
    assert "Секретная информация из кружка" in reply_call
    # LLM companion should NOT be called for casual chatter
    mock_llm.chat_completion.assert_not_called()


@pytest.mark.asyncio
async def test_reply_to_circle_conversational_enriches_extra_context(test_db: Database, test_stt_service: NvidiaSTTService) -> None:
    """When a user asks Richard's opinion about a circle, Richard converses with the circle transcription in extra_context."""
    from moderation.companion import ChatCompanion
    from moderation.llm_client import LLMClient

    settings = Settings(BOT_TOKEN="123:ABC", OWNER_ID=999, ANALYTICS_ENABLED=False)
    mock_forward_engine = AsyncMock()
    mock_profiler = AsyncMock()

    mock_llm = AsyncMock(spec=LLMClient)
    mock_llm.api_key = "test-key"
    mock_llm.chat_completion.return_value = "Мне кажется, автор кружка абсолютно прав!"
    companion = ChatCompanion(llm_client=mock_llm)
    companion._bot_user = MagicMock(id=7761395820, username="RichardHelperBot")

    chat_id = -100998
    async with test_db.connect() as conn:
        repo = ChatRepository(conn)
        await repo.upsert_chat(chat_id=chat_id, title="Test Group", chat_type="supergroup")
        await conn.execute("UPDATE chats SET chat_ai_enabled = 1, stt_enabled = 1 WHERE chat_id = ?", (chat_id,))
        await conn.commit()

    circle_msg = make_mock_message(chat_id=chat_id, video_note=True)
    user_conv_msg = make_mock_message(chat_id=chat_id, text="Ричард, что думаешь по поводу кружка?", reply_to=circle_msg)

    with patch.object(test_stt_service, "transcribe_telegram_file", return_value="Мы сегодня открываем новый проект!"):
        await handle_incoming_message(
            message=user_conv_msg,
            forward_engine=mock_forward_engine,
            style_profiler=mock_profiler,
            settings=settings,
            db=test_db,
            companion=companion,
            stt_service=test_stt_service,
        )

    # LLM should be called
    mock_llm.chat_completion.assert_called_once()
    # Check messages sent to LLM
    call_messages = mock_llm.chat_completion.call_args[1]["messages"]
    system_contents = [m["content"] for m in call_messages if m["role"] == "system"]
    assert any("Мы сегодня открываем новый проект!" in c for c in system_contents)

    user_conv_msg.reply.assert_called_once()
    assert "Мне кажется, автор кружка абсолютно прав!" in user_conv_msg.reply.call_args[0][0]


def test_is_transcription_request_variations() -> None:
    from bot.handlers.forward import is_transcription_request

    # Positive: direct transcription queries
    assert is_transcription_request("Ричард что я сказал") is True
    assert is_transcription_request("что я сказал") is True
    assert is_transcription_request("что я наговорил") is True
    assert is_transcription_request("Покажи что происходит тут на кружочке@RichardHelperBot") is True
    assert is_transcription_request("Рокажи что происходит тут на кружочке") is True
    assert is_transcription_request("что происходит в кружке") is True
    assert is_transcription_request("что происходит на кружочке") is True
    assert is_transcription_request("переведи кружок") is True
    assert is_transcription_request("расшифруй голосовое") is True
    assert is_transcription_request("что в последнем кружке") is True
    assert is_transcription_request("Ричард, пожалуйста расскажи что в гс") is True
    assert is_transcription_request("/transcribe") is True

    # Negative: chat drama queries (without media words) & conversational opinions
    assert is_transcription_request("Блять что с вами. Ричард что тут нах происходит") is False
    assert is_transcription_request("Что здесь чёрт возьми происходит 😂👍") is False
    assert is_transcription_request("Ричард что тут происходит") is False
    assert is_transcription_request("Ричард, что думаешь по поводу кружка?") is False
    assert is_transcription_request("Ричард прокомментируй кружок") is False
    assert is_transcription_request("как дела Ричард?") is False


@pytest.mark.asyncio
async def test_non_reply_transcription_what_did_i_say(test_db: Database, test_stt_service: NvidiaSTTService) -> None:
    """When a user sends a circle and then writes 'Ричард что я сказал' without reply, bot transcribes the user's circle!"""
    settings = Settings(BOT_TOKEN="123:ABC", OWNER_ID=999, ANALYTICS_ENABLED=False)
    mock_forward_engine = AsyncMock()
    mock_profiler = AsyncMock()

    chat_id = -100444
    user_id = 911338473  # Timur
    async with test_db.connect() as conn:
        repo = ChatRepository(conn)
        await repo.upsert_chat(chat_id=chat_id, title="Group Chat", chat_type="supergroup")
        await conn.execute("UPDATE chats SET chat_ai_enabled = 1, stt_enabled = 1 WHERE chat_id = ?", (chat_id,))
        await conn.commit()

    # 1. Timur sends a circle note
    circle_msg = make_mock_message(chat_id=chat_id, user_id=user_id, user_name="Тимур", video_note=True)
    await handle_incoming_message(
        message=circle_msg,
        forward_engine=mock_forward_engine,
        style_profiler=mock_profiler,
        settings=settings,
        db=test_db,
        stt_service=test_stt_service,
    )

    # 2. Timur sends 'Ричард что я сказал' without swiping/replying
    ask_msg = make_mock_message(chat_id=chat_id, user_id=user_id, user_name="Тимур", text="Ричард что я сказал", reply_to=None)
    with patch.object(test_stt_service, "transcribe_telegram_file", return_value="Всем привет, я тестирую распознавание речи!"):
        await handle_incoming_message(
            message=ask_msg,
            forward_engine=mock_forward_engine,
            style_profiler=mock_profiler,
            settings=settings,
            db=test_db,
            stt_service=test_stt_service,
        )

    ask_msg.reply.assert_called_once()
    reply_text = ask_msg.reply.call_args[0][0]
    assert "Расшифровка (Кружок от Тимур):" in reply_text
    assert "Всем привет, я тестирую распознавание речи!" in reply_text


@pytest.mark.asyncio
async def test_non_reply_transcription_show_what_happens_in_circle(test_db: Database, test_stt_service: NvidiaSTTService) -> None:
    """When User A sends a circle, and User B writes 'Покажи что происходит тут на кружочке@RichardHelperBot' without reply, bot transcribes it!"""
    settings = Settings(BOT_TOKEN="123:ABC", OWNER_ID=999, ANALYTICS_ENABLED=False)
    mock_forward_engine = AsyncMock()
    mock_profiler = AsyncMock()

    chat_id = -100445
    async with test_db.connect() as conn:
        repo = ChatRepository(conn)
        await repo.upsert_chat(chat_id=chat_id, title="Group Chat 2", chat_type="supergroup")
        await conn.execute("UPDATE chats SET chat_ai_enabled = 1, stt_enabled = 1 WHERE chat_id = ?", (chat_id,))
        await conn.commit()

    # 1. Timur sends a video note
    circle_msg = make_mock_message(chat_id=chat_id, user_id=911338473, user_name="Тимур", video_note=True)
    await handle_incoming_message(
        message=circle_msg,
        forward_engine=mock_forward_engine,
        style_profiler=mock_profiler,
        settings=settings,
        db=test_db,
        stt_service=test_stt_service,
    )

    # 2. MixaRed asks 'Рокажи что происходит тут на кружочке@RichardHelperBot' without reply
    mixa_msg = make_mock_message(chat_id=chat_id, user_id=5956803305, user_name="MixaRed", text="Рокажи что происходит тут на кружочке@RichardHelperBot", reply_to=None)
    with patch.object(test_stt_service, "transcribe_telegram_file", return_value="На кружочке я показываю код на сервере"):
        await handle_incoming_message(
            message=mixa_msg,
            forward_engine=mock_forward_engine,
            style_profiler=mock_profiler,
            settings=settings,
            db=test_db,
            stt_service=test_stt_service,
        )

    mixa_msg.reply.assert_called_once()
    reply_text = mixa_msg.reply.call_args[0][0]
    assert "Расшифровка (Кружок от Тимур):" in reply_text
    assert "На кружочке я показываю код на сервере" in reply_text


@pytest.mark.asyncio
async def test_non_reply_conversational_with_audio_enrichment(test_db: Database, test_stt_service: NvidiaSTTService) -> None:
    """When a circle is sent and then someone asks 'Ричард что думаешь про кружок' without reply, extra_context receives the circle transcript!"""
    from moderation.companion import ChatCompanion
    from moderation.llm_client import LLMClient

    settings = Settings(BOT_TOKEN="123:ABC", OWNER_ID=999, ANALYTICS_ENABLED=False)
    mock_forward_engine = AsyncMock()
    mock_profiler = AsyncMock()

    mock_llm = AsyncMock(spec=LLMClient)
    mock_llm.api_key = "test-key"
    mock_llm.chat_completion.return_value = "По-моему, идея отличная."
    companion = ChatCompanion(llm_client=mock_llm)
    companion._bot_user = MagicMock(id=7761395820, username="RichardHelperBot")

    chat_id = -100446
    async with test_db.connect() as conn:
        repo = ChatRepository(conn)
        await repo.upsert_chat(chat_id=chat_id, title="Enrich Group", chat_type="supergroup")
        await conn.execute("UPDATE chats SET chat_ai_enabled = 1, stt_enabled = 1 WHERE chat_id = ?", (chat_id,))
        await conn.commit()

    # 1. Sol sends a video note
    sol_circle = make_mock_message(chat_id=chat_id, user_id=1696889505, user_name="Соль", video_note=True)
    with patch.object(test_stt_service, "transcribe_telegram_file", return_value="Я гуляю по парку и ем мороженое"):
        await handle_incoming_message(
            message=sol_circle,
            forward_engine=mock_forward_engine,
            style_profiler=mock_profiler,
            settings=settings,
            db=test_db,
            companion=companion,
            stt_service=test_stt_service,
        )

    # 2. MixaRed writes 'Ричард что думаешь про кружок?' without reply
    conv_msg = make_mock_message(chat_id=chat_id, user_id=5956803305, user_name="MixaRed", text="Ричард что думаешь про кружок?", reply_to=None)
    await handle_incoming_message(
        message=conv_msg,
        forward_engine=mock_forward_engine,
        style_profiler=mock_profiler,
        settings=settings,
        db=test_db,
        companion=companion,
        stt_service=test_stt_service,
    )

    mock_llm.chat_completion.assert_called_once()
    call_messages = mock_llm.chat_completion.call_args[1]["messages"]
    system_contents = [m["content"] for m in call_messages if m["role"] == "system"]
    assert any("Контекст недавнего кружок от Соль" in c for c in system_contents)
    assert any("Я гуляю по парку и ем мороженое" in c for c in system_contents)

    conv_msg.reply.assert_called_once()
    assert "По-моему, идея отличная." in conv_msg.reply.call_args[0][0]


@pytest.mark.asyncio
async def test_non_reply_conversational_with_silent_melody_enrichment(test_db: Database, test_stt_service: NvidiaSTTService) -> None:
    """When a circle note has no clear speech (humming a tune), companion receives melody fallback context!"""
    from moderation.companion import ChatCompanion
    from moderation.llm_client import LLMClient

    settings = Settings(BOT_TOKEN="123:ABC", OWNER_ID=999, ANALYTICS_ENABLED=False)
    mock_forward_engine = AsyncMock()
    mock_profiler = AsyncMock()

    mock_llm = AsyncMock(spec=LLMClient)
    mock_llm.api_key = "test-key"
    mock_llm.chat_completion.return_value = "Вокал на уровне Грэмми."
    companion = ChatCompanion(llm_client=mock_llm)
    companion._bot_user = MagicMock(id=7761395820, username="RichardHelperBot")

    chat_id = -100447
    async with test_db.connect() as conn:
        repo = ChatRepository(conn)
        await repo.upsert_chat(chat_id=chat_id, title="Melody Group", chat_type="supergroup")
        await conn.execute("UPDATE chats SET chat_ai_enabled = 1, stt_enabled = 1 WHERE chat_id = ?", (chat_id,))
        await conn.commit()

    # 1. Sol sends a video note with melody (STT returns None/empty)
    sol_circle = make_mock_message(chat_id=chat_id, user_id=1696889505, user_name="Соль", video_note=True)
    with patch.object(test_stt_service, "transcribe_telegram_file", return_value=None):
        await handle_incoming_message(
            message=sol_circle,
            forward_engine=mock_forward_engine,
            style_profiler=mock_profiler,
            settings=settings,
            db=test_db,
            companion=companion,
            stt_service=test_stt_service,
        )

    # 2. Someone asks 'Ричард как тебе пение в кружке?'
    conv_msg = make_mock_message(chat_id=chat_id, user_id=5848551858, user_name="⠁⠃⠽⠎⠎", text="Ричард как тебе пение в кружке?", reply_to=None)
    with patch.object(test_stt_service, "transcribe_telegram_file", return_value=None):
        await handle_incoming_message(
            message=conv_msg,
            forward_engine=mock_forward_engine,
            style_profiler=mock_profiler,
            settings=settings,
            db=test_db,
            companion=companion,
            stt_service=test_stt_service,
        )

    mock_llm.chat_completion.assert_called_once()
    call_messages = mock_llm.chat_completion.call_args[1]["messages"]
    system_contents = [m["content"] for m in call_messages if m["role"] == "system"]
    assert any("была мелодия, напевание или музыка" in c for c in system_contents)



