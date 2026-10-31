"""Tests for ChatCompanion, ChatContextBuffer, and conversation feature."""

from __future__ import annotations

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

