from datetime import datetime
import pytest

from database.connection import Database
from database.repositories.profile_repo import ProfileRepository
from analytics.profiler import StyleProfiler


@pytest.mark.asyncio
async def test_privacy_user_exclusion(test_db: Database, test_profiler: StyleProfiler):
    user_id = 999111
    chat_id = -100555

    async with test_db.connect() as conn:
        repo = ProfileRepository(conn)
        await repo.set_exclusion("user", user_id, True)
        assert await repo.is_excluded("user", user_id) is True

    result = await test_profiler.process_message(
        user_id=user_id,
        chat_id=chat_id,
        text="Это приватное сообщение, которое не должно анализироваться.",
        created_at=datetime.now(),
    )
    assert result is False

    async with test_db.connect() as conn:
        repo = ProfileRepository(conn)
        profile = await repo.get_profile(user_id, chat_id)
        assert profile is None


@pytest.mark.asyncio
async def test_privacy_delete_profile(test_db: Database, test_profiler: StyleProfiler):
    user_id = 888222
    chat_id = -100777

    for i in range(5):
        await test_profiler.process_message(
            user_id=user_id,
            chat_id=chat_id,
            text=f"Тестовое сообщение номер {i} для профиля.",
            created_at=datetime.now(),
        )

    async with test_db.connect() as conn:
        repo = ProfileRepository(conn)
        profile = await repo.get_profile(user_id, chat_id)
        assert profile is not None
        assert profile["sample_count"] == 5

        deleted_rows = await repo.delete_user_profile(user_id)
        assert deleted_rows >= 1

        assert await repo.get_profile(user_id, chat_id) is None
        assert await repo.get_profile(user_id, 0) is None
