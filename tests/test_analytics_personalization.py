"""Tests for personal profile isolation and per-user stylometry."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
import pytest
from aiogram.types import Chat, Message, User

from database.connection import Database
from database.repositories.profile_repo import ProfileRepository
from config.settings import Settings
from bot.handlers.forward import handle_incoming_message


def make_test_message(
    chat_id: int,
    chat_type: str,
    text: str,
    user_id: int,
    username: str = "tester",
) -> Message:
    msg = MagicMock(spec=Message)
    msg.message_id = 101
    msg.text = text
    msg.caption = None
    msg.entities = []
    msg.date = None

    chat = MagicMock(spec=Chat)
    chat.id = chat_id
    chat.type = chat_type
    chat.title = f"Chat {chat_id}"
    chat.username = None
    msg.chat = chat

    user = MagicMock(spec=User)
    user.id = user_id
    user.first_name = username
    user.username = username
    user.full_name = username
    msg.from_user = user

    msg.reply_to_message = None
    msg.bot = AsyncMock()
    return msg


@pytest.mark.asyncio
async def test_user_profiles_strictly_isolated(test_db: Database) -> None:
    async with test_db.connect() as conn:
        repo = ProfileRepository(conn)

        # Create profile for User 1
        await repo.upsert_profile(
            user_id=111,
            chat_id=0,
            is_owner=True,
            sample_count=15,
            total_words=150,
            total_characters=800,
            avg_sentence_len=10.0,
            lexical_richness=0.8,
            punctuation_stats={},
            emoji_stats={},
            formality_markers={},
            activity_hours={},
        )

        # Create profile for User 2
        await repo.upsert_profile(
            user_id=222,
            chat_id=0,
            is_owner=False,
            sample_count=5,
            total_words=30,
            total_characters=180,
            avg_sentence_len=6.0,
            lexical_richness=0.6,
            punctuation_stats={},
            emoji_stats={},
            formality_markers={},
            activity_hours={},
        )

        p1 = await repo.get_profile(111, chat_id=0)
        p2 = await repo.get_profile(222, chat_id=0)

        assert p1 is not None and p2 is not None
        assert p1["user_id"] == 111
        assert p1["sample_count"] == 15
        assert p1["total_words"] == 150

        assert p2["user_id"] == 222
        assert p2["sample_count"] == 5
        assert p2["total_words"] == 30

        # Verify list_profiles does not duplicate and filters chat_id=0
        await repo.upsert_profile(
            user_id=111,
            chat_id=-1001,
            is_owner=True,
            sample_count=10,
            total_words=100,
            total_characters=500,
            avg_sentence_len=10.0,
            lexical_richness=0.8,
            punctuation_stats={},
            emoji_stats={},
            formality_markers={},
            activity_hours={},
        )

        profiles = await repo.list_profiles()
        assert len(profiles) == 2
        uids = [p["user_id"] for p in profiles]
        assert 111 in uids
        assert 222 in uids
        # Ensure only chat_id=0 profiles are listed
        assert all(p["chat_id"] == 0 for p in profiles)


@pytest.mark.asyncio
async def test_private_chat_not_profiled_by_default(test_db: Database) -> None:
    settings = Settings(BOT_TOKEN="123:ABC", OWNER_ID=999, ANALYTICS_ENABLED=True)
    mock_forward_engine = AsyncMock()
    mock_profiler = AsyncMock()

    # User sends a private message to the bot
    msg = make_test_message(chat_id=55555, chat_type="private", text="Привет, Ричард!", user_id=55555)

    await handle_incoming_message(
        message=msg,
        forward_engine=mock_forward_engine,
        style_profiler=mock_profiler,
        settings=settings,
        db=test_db,
    )

    # Style profiler must NOT be called for normal private messages to the bot
    mock_profiler.process_message.assert_not_called()


@pytest.mark.asyncio
async def test_group_chat_is_profiled(test_db: Database) -> None:
    settings = Settings(BOT_TOKEN="123:ABC", OWNER_ID=999, ANALYTICS_ENABLED=True)
    mock_forward_engine = AsyncMock()
    mock_profiler = AsyncMock()

    # User sends a message in a group
    msg = make_test_message(chat_id=-100999, chat_type="supergroup", text="Всем привет в группе!", user_id=777)

    await handle_incoming_message(
        message=msg,
        forward_engine=mock_forward_engine,
        style_profiler=mock_profiler,
        settings=settings,
        db=test_db,
    )

    # Style profiler MUST be called for group messages
    mock_profiler.process_message.assert_awaited_once()
    call_args = mock_profiler.process_message.call_args[1]
    assert call_args["user_id"] == 777
    assert call_args["chat_id"] == -100999
    assert call_args["text"] == "Всем привет в группе!"
