"""Tests for ChatCompanion, ChatContextBuffer, and conversation feature."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock
import pytest
from aiogram.types import Chat, Message, User

from database.connection import Database
from database.repositories.chat_repo import ChatRepository
from moderation.companion import ChatCompanion, ChatContextBuffer
from moderation.llm_client import LLMClient


def make_mock_message(
    chat_id: int,
    chat_type: str,
    text: str,
    from_user_id: int = 123,
    from_username: str = "alice",
    reply_to_user_id: int | None = None,
    reply_to_username: str | None = None,
) -> Message:
    msg = MagicMock(spec=Message)
    msg.message_id = 999
    msg.text = text
    msg.caption = None
    msg.entities = []
    msg.date = datetime.now()

    chat = MagicMock(spec=Chat)
    chat.id = chat_id
    chat.type = chat_type
    chat.title = f"Chat {chat_id}"
    chat.username = None
    msg.chat = chat

    user = MagicMock(spec=User)
    user.id = from_user_id
    user.first_name = from_username
    user.username = from_username
    user.full_name = from_username
    msg.from_user = user

    if reply_to_user_id is not None:
        reply_msg = MagicMock(spec=Message)
        reply_user = MagicMock(spec=User)
        reply_user.id = reply_to_user_id
        reply_user.username = reply_to_username
        reply_msg.from_user = reply_user
        msg.reply_to_message = reply_msg
    else:
        msg.reply_to_message = None

    msg.bot = AsyncMock()
    return msg


def test_context_buffer_add_and_format() -> None:
    buf = ChatContextBuffer(max_history=5)
    chat_id = -1001

    buf.add_message(chat_id, user_id=1, user_name="Иван", text="Кто идет на пару?")
    buf.add_message(chat_id, user_id=2, user_name="Мария", text="Я в колледже, жду")
    buf.add_message(chat_id, user_id=3, user_name="Олег", text="/help")  # Commands must be ignored
    buf.add_message(chat_id, user_id=0, user_name="Ричард", text="Привет всем!", is_bot=True)

    formatted = buf.format_context(chat_id)
    assert "[Иван]: Кто идет на пару?" in formatted
    assert "[Мария]: Я в колледже, жду" in formatted
    assert "/help" not in formatted
    assert "[Ричард (Бот)]: Привет всем!" in formatted


def test_context_buffer_maxlen() -> None:
    buf = ChatContextBuffer(max_history=3)
    chat_id = -1002

    for i in range(5):
        buf.add_message(chat_id, user_id=i, user_name=f"User{i}", text=f"Message {i}")

    messages = buf.get_context(chat_id)
    assert len(messages) == 3
    assert messages[0].text == "Message 2"
    assert messages[2].text == "Message 4"


def test_companion_trigger_private_chat() -> None:
    companion = ChatCompanion()
    msg = make_mock_message(chat_id=123, chat_type="private", text="Привет, Ричард!")
    triggered, prompt = companion.is_triggered(msg, bot_username="RichardHelperBot", bot_id=7761395820)
    assert triggered is True
    assert prompt == "Привет, Ричард!"

    cmd_msg = make_mock_message(chat_id=123, chat_type="private", text="/start")
    triggered_cmd, _ = companion.is_triggered(cmd_msg, bot_username="RichardHelperBot", bot_id=7761395820)
    assert triggered_cmd is False


def test_companion_trigger_group_no_mention() -> None:
    companion = ChatCompanion()
    msg = make_mock_message(chat_id=-1001, chat_type="supergroup", text="Обычное сообщение в группе")
    triggered, _ = companion.is_triggered(msg, bot_username="RichardHelperBot", bot_id=7761395820)
    assert triggered is False


def test_companion_trigger_group_mention() -> None:
    companion = ChatCompanion()
    msg = make_mock_message(
        chat_id=-1001,
        chat_type="supergroup",
        text="@richardhelperbot о чем тут базарят?",
    )
    triggered, prompt = companion.is_triggered(msg, bot_username="RichardHelperBot", bot_id=7761395820)
    assert triggered is True
    assert prompt == "о чем тут базарят?"


def test_companion_trigger_group_reply_to_bot() -> None:
    companion = ChatCompanion()
    msg = make_mock_message(
        chat_id=-1001,
        chat_type="group",
        text="А ты пойдешь на пару?",
        reply_to_user_id=7761395820,
        reply_to_username="RichardHelperBot",
    )
    triggered, prompt = companion.is_triggered(msg, bot_username="RichardHelperBot", bot_id=7761395820)
    assert triggered is True
    assert prompt == "А ты пойдешь на пару?"


def test_companion_trigger_group_reply_to_other_user() -> None:
    companion = ChatCompanion()
    msg = make_mock_message(
        chat_id=-1001,
        chat_type="group",
        text="Отвечаю другому человеку",
        reply_to_user_id=9999999,
        reply_to_username="another_user",
    )
    triggered, _ = companion.is_triggered(msg, bot_username="RichardHelperBot", bot_id=7761395820)
    assert triggered is False


@pytest.mark.asyncio
async def test_companion_generate_reply_with_context() -> None:
    mock_llm = AsyncMock(spec=LLMClient)
    mock_llm.api_key = "test-key"
    mock_llm.chat_completion.return_value = "Обсуждали пары в колледже, все на расслабоне!"

    buf = ChatContextBuffer()
    chat_id = -1005
    buf.add_message(chat_id, user_id=1, user_name="Иван", text="Вторая пара отменилась")
    buf.add_message(chat_id, user_id=2, user_name="Мария", text="Круто, идем пить кофе")

    companion = ChatCompanion(llm_client=mock_llm, context_buffer=buf)

    reply = await companion.generate_reply(
        chat_id=chat_id,
        user_name="Алексей",
        user_prompt="О чем речь?",
    )

    assert reply == "Обсуждали пары в колледже, все на расслабоне!"
    mock_llm.chat_completion.assert_awaited_once()

    call_args = mock_llm.chat_completion.call_args[1]
    messages = call_args["messages"]
    system_msgs = [m["content"] for m in messages if m["role"] == "system"]
    assert any("Вторая пара отменилась" in s for s in system_msgs)

    # Check bot reply added to context buffer
    ctx = buf.get_context(chat_id)
    assert ctx[-1].is_bot is True
    assert ctx[-1].text == "Обсуждали пары в колледже, все на расслабоне!"


@pytest.mark.asyncio
async def test_chat_repo_chat_ai_toggle(test_db: Database) -> None:
    async with test_db.connect() as conn:
        repo = ChatRepository(conn)
        await repo.upsert_chat(chat_id=-10099, title="College Group", chat_type="supergroup")

        chat = await repo.get_chat(-10099)
        assert chat is not None
        assert chat["chat_ai_enabled"] == 0

        val1 = await repo.toggle_setting(-10099, "chat_ai_enabled")
        assert val1 is True

        chat_after = await repo.get_chat(-10099)
        assert chat_after["chat_ai_enabled"] == 1

        val2 = await repo.toggle_setting(-10099, "chat_ai_enabled")
        assert val2 is False

        chat_final = await repo.get_chat(-10099)
        assert chat_final["chat_ai_enabled"] == 0


@pytest.mark.asyncio
async def test_forward_handler_companion_silence_when_disabled(test_db: Database) -> None:
    from bot.handlers.forward import handle_incoming_message
    from config.settings import Settings

    settings = Settings(BOT_TOKEN="123:ABC", OWNER_ID=999, ANALYTICS_ENABLED=False)
    mock_forward_engine = AsyncMock()
    mock_profiler = AsyncMock()

    mock_llm = AsyncMock(spec=LLMClient)
    mock_llm.api_key = "test-key"
    mock_llm.chat_completion.return_value = "Привет из ИИ!"

    companion = ChatCompanion(llm_client=mock_llm)
    companion._bot_user = MagicMock(id=7761395820, username="RichardHelperBot")

    chat_id = -100777
    async with test_db.connect() as conn:
        repo = ChatRepository(conn)
        await repo.upsert_chat(chat_id=chat_id, title="Silent Group", chat_type="supergroup")

    msg = make_mock_message(
        chat_id=chat_id,
        chat_type="supergroup",
        text="@RichardHelperBot как дела?",
    )
    msg.reply = AsyncMock()

    # Chat AI is disabled (0), bot MUST stay silent!
    await handle_incoming_message(
        message=msg,
        forward_engine=mock_forward_engine,
        style_profiler=mock_profiler,
        settings=settings,
        db=test_db,
        companion=companion,
    )

    msg.reply.assert_not_called()
    mock_llm.chat_completion.assert_not_called()

    # Now enable chat AI
    async with test_db.connect() as conn:
        repo = ChatRepository(conn)
        await repo.toggle_setting(chat_id, "chat_ai_enabled")

    # Send message again
    await handle_incoming_message(
        message=msg,
        forward_engine=mock_forward_engine,
        style_profiler=mock_profiler,
        settings=settings,
        db=test_db,
        companion=companion,
    )

    msg.reply.assert_awaited_once_with("Привет из ИИ!", parse_mode="HTML")
    mock_llm.chat_completion.assert_awaited_once()


def test_format_context_clean_linear_no_confusing_summary() -> None:
    buf = ChatContextBuffer(max_history=5)
    chat_id = -100999
    buf.add_message(chat_id, user_id=10, user_name="Соль", text="Привет всем")
    buf.add_message(chat_id, user_id=20, user_name="Тимур", text="Здорово")

    formatted = buf.format_context(chat_id)
    assert "[Соль]: Привет всем" in formatted
    assert "[Тимур]: Здорово" in formatted
    assert "Сводка по участникам беседы" not in formatted
    assert "Недавние реплики участников" not in formatted


def test_system_prompt_has_few_shots_and_anti_cringe_rules() -> None:
    companion = ChatCompanion()
    prompt = companion.get_effective_system_prompt()
    assert "СТРОЖАЙШЕ ЗАПРЕЩЕНО вслух говорить о сарказме" in prompt
    assert "солью веселого сарказма" in prompt
    assert "ПРИМЕРЫ ПРАВИЛЬНЫХ ОТВЕТОВ:" in prompt


@pytest.mark.asyncio
async def test_participant_micropriming_in_generate_reply() -> None:
    llm = MagicMock(spec=LLMClient)
    llm.api_key = "dummy-key"
    llm.chat_completion = AsyncMock(return_value="Чёткий ответ.")
    companion = ChatCompanion(llm_client=llm)

    # 1. Test Forsazh 0 emoji rule priming
    await companion.generate_reply(
        chat_id=-1002255156347,
        user_name="форсаж",
        user_prompt="Ричард как дела",
        user_id=5985808271,
        username="ishowdealer",
    )
    call_args = llm.chat_completion.call_args[1]["messages"]
    system_contents = [m["content"] for m in call_args if m["role"] == "system"]
    assert any("СТРОГО 0 смайликов" in s for s in system_contents)
    assert any("форсаж (@ishowdealer)" in m["content"] for m in call_args if m["role"] == "user")

    # 2. Test Sol priming
    await companion.generate_reply(
        chat_id=-1002255156347,
        user_name="Соль",
        user_prompt="Ричард ты где",
        user_id=1696889505,
        username="ciel_hleb",
    )
    call_args2 = llm.chat_completion.call_args[1]["messages"]
    system_contents2 = [m["content"] for m in call_args2 if m["role"] == "system"]
    assert any("называть строго Соль" in s for s in system_contents2)

    # 3. Test Daily Memory injection
    await companion.generate_reply(
        chat_id=-1002255156347,
        user_name="MixaRed",
        user_prompt="Ты фуфлыжник",
        user_id=5956803305,
        username="mixared",
        daily_memory_summary="MixaRed примерял ушки с хвостом у Тимура дома.",
        daily_memory_facts=["MixaRed сидит у Тимура", "⠁⠃⠽⠎⠎ просил стереть память"],
    )
    call_args3 = llm.chat_completion.call_args[1]["messages"]
    system_contents3 = [m["content"] for m in call_args3 if m["role"] == "system"]
    assert any("ДНЕВНАЯ ПАМЯТЬ" in s for s in system_contents3)
    assert any("ушки с хвостом" in s for s in system_contents3)
    assert any("ПРАВИЛО ПАФОСА И МЕСТИ" in s for s in system_contents3)

    # 4. Test Timur creator micropriming
    await companion.generate_reply(
        chat_id=911338473,
        user_name="Тимур",
        user_prompt="Твой скрипт явно нуждается в доработке",
        user_id=911338473,
        username="Tymur2000",
        is_owner=True,
    )
    call_args4 = llm.chat_completion.call_args[1]["messages"]
    system_contents4 = [m["content"] for m in call_args4 if m["role"] == "system"]
    assert any("твой создатель и разработчик" in s for s in system_contents4)
    assert any("Никаких 'верных псов'" in s for s in system_contents4)
    assert any("СТРОГО ЗАПРЕЩЕНЫ детские стрелки" in s for s in system_contents4)


def test_transcription_request_and_summary_discrimination() -> None:
    from bot.handlers.forward import is_transcription_request, is_summary_request

    # False positives for transcription
    assert not is_transcription_request("Что за х**йню ты несёшь, хорош, и чётко дай что там по чату")
    assert not is_transcription_request("Ричард дай сводку по чату тирамису")
    assert not is_transcription_request("что там по чату")
    assert not is_transcription_request("что тут происходит")
    assert not is_transcription_request("дай что там по чату")

    # True transcription
    assert is_transcription_request("что в кружке")
    assert is_transcription_request("расшифруй голосовое")
    assert is_transcription_request("что он сказал в гс")
    assert is_transcription_request("переведи в текст")
    assert is_transcription_request("что тут", is_reply_to_media=True)

    # Summary requests
    assert is_summary_request("Ричард дай сводку по чату тирамису")
    assert is_summary_request("что там по чату")
    assert is_summary_request("дай сводку")
    assert is_summary_request("расскажи что в чате")
    assert not is_summary_request("Привет как дела")


@pytest.mark.asyncio
async def test_summary_admin_security(test_db: Database) -> None:
    from bot.handlers.forward import handle_incoming_message
    from config.settings import Settings

    settings = Settings(
        BOT_TOKEN="123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11",
        OWNER_ID=911338473,
    )
    mock_engine = MagicMock()
    mock_engine.process_incoming_message = AsyncMock()

    mock_profiler = MagicMock()
    mock_profiler.process_message = AsyncMock()
    mock_llm = MagicMock()
    companion = ChatCompanion(llm_client=mock_llm)
    companion._bot_user = MagicMock(id=7761395820, username="RichardHelperBot")

    chat_id = -1002255156347
    async with test_db.connect() as conn:
        repo = ChatRepository(conn)
        await repo.upsert_chat(chat_id=chat_id, title="TiraMMMiSu", chat_type="supergroup")
        await repo.toggle_setting(chat_id, "chat_ai_enabled")

    # Non-admin user asks for summary -> must receive denial
    guest_msg = make_mock_message(
        chat_id=chat_id,
        chat_type="supergroup",
        text="Ричард дай сводку по чату тирамису",
        from_user_id=5956803305,  # MixaRed, regular user
        from_username="mixared",
    )
    guest_msg.reply = AsyncMock()
    guest_msg.bot = MagicMock()
    guest_msg.bot.send_chat_action = AsyncMock()

    await handle_incoming_message(
        message=guest_msg,
        forward_engine=mock_engine,
        style_profiler=mock_profiler,
        settings=settings,
        db=test_db,
        companion=companion,
    )

    guest_msg.reply.assert_awaited_once()
    reply_call = guest_msg.reply.call_args[0][0]
    assert "только для создателя и админов" in reply_call


@pytest.mark.asyncio
async def test_chat_repo_compressed_history_and_daily_memory(test_db: Database) -> None:
    async with test_db.connect() as conn:
        repo = ChatRepository(conn)
        cid = -100999888777
        # Insert messages including laughs and stickers
        await repo.add_companion_message(cid, 1, "MixaRed", "Привет", is_bot=False)
        await repo.add_companion_message(cid, 1, "MixaRed", "ХАХАХАХАХА", is_bot=False)
        await repo.add_companion_message(cid, 1, "MixaRed", "хахахаха", is_bot=False)
        await repo.add_companion_message(cid, 2, "forsazh", "[Стикер: 🌟]", is_bot=False)
        await repo.add_companion_message(cid, 2, "forsazh", "[Стикер: 🌟]", is_bot=False)
        await repo.add_companion_message(cid, 2, "forsazh", "[Стикер: 🌟]", is_bot=False)
        await repo.add_companion_message(cid, 1, "MixaRed", "Круто", is_bot=False)

        compressed = await repo.get_compressed_history(cid, raw_limit=10)
        assert len(compressed) < 7  # compressed!
        assert any("отправил 3 стикеров" in c["text"] for c in compressed)

        # Test daily memory
        await repo.upsert_daily_memory(
            chat_id=cid,
            date_str="2026-11-03",
            summary="Тестовые события дня",
            key_facts=["Факт 1", "Факт 2"],
            last_msg_id=123,
        )
        mem = await repo.get_daily_memory(cid, "2026-11-03")
        assert mem is not None
        assert mem["summary"] == "Тестовые события дня"
        assert "Факт 1" in mem["key_facts"]






@pytest.mark.asyncio
async def test_non_admin_pm_summary_and_begging_denial(test_db: Database) -> None:
    from bot.handlers.forward import handle_incoming_message
    from config.settings import Settings
    from database.repositories.user_repo import UserRepository

    settings = Settings(
        BOT_TOKEN="123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11",
        OWNER_ID=911338473,
    )
    mock_engine = MagicMock()
    mock_engine.process_incoming_message = AsyncMock()

    mock_profiler = MagicMock()
    mock_profiler.process_message = AsyncMock()
    mock_llm = MagicMock()
    mock_llm.api_key = "dummy"
    mock_llm.chat_completion = AsyncMock(return_value="Обычный ответ")
    companion = ChatCompanion(llm_client=mock_llm)
    companion._bot_user = MagicMock(id=7761395820, username="RichardHelperBot")

    # Second account with name 'Тимур', but user_id 6205547383 (role: user)
    second_user_id = 6205547383
    async with test_db.connect() as conn:
        u_repo = UserRepository(conn)
        await u_repo.upsert_user(user_id=second_user_id, username="Tymur_zav", role="user", is_authorized=True)

    # 1. Ask for summary in PM
    msg1 = make_mock_message(
        chat_id=second_user_id,
        chat_type="private",
        text="ты давай, поменьше выпендрежа, и сводку по тирамису давай",
        from_user_id=second_user_id,
        from_username="Тимур",
    )
    msg1.reply = AsyncMock()
    msg1.bot = MagicMock()
    msg1.bot.send_chat_action = AsyncMock()

    await handle_incoming_message(
        message=msg1,
        forward_engine=mock_engine,
        style_profiler=mock_profiler,
        settings=settings,
        db=test_db,
        companion=companion,
    )
    msg1.reply.assert_awaited_once()
    assert "только для создателя и админов" in msg1.reply.call_args[0][0]

    # 2. Beg for summary 'Ну пожалуйста' in PM
    msg2 = make_mock_message(
        chat_id=second_user_id,
        chat_type="private",
        text="Ну пожалуйста",
        from_user_id=second_user_id,
        from_username="Тимур",
    )
    msg2.reply = AsyncMock()
    msg2.bot = MagicMock()
    msg2.bot.send_chat_action = AsyncMock()

    await handle_incoming_message(
        message=msg2,
        forward_engine=mock_engine,
        style_profiler=mock_profiler,
        settings=settings,
        db=test_db,
        companion=companion,
    )
    # Must ALSO be denied, not leak summary!
    msg2.reply.assert_awaited_once()
    assert "только для создателя и админов" in msg2.reply.call_args[0][0]
