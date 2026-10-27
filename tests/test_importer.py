import json
from pathlib import Path
import pytest

from database.connection import Database
from database.repositories.profile_repo import ProfileRepository
from analytics.profiler import StyleProfiler
from importer.json_importer import TelegramJsonImporter


@pytest.mark.asyncio
async def test_telegram_json_importer(test_db: Database, test_profiler: StyleProfiler, tmp_path: Path):
    sample_export = {
        "name": "Project Chat",
        "type": "supergroup",
        "id": 1234567,
        "messages": [
            {
                "id": 1,
                "type": "message",
                "date": "2026-10-20T10:00:00",
                "from": "Alice",
                "from_id": "user1001",
                "text": "Привет всем! Начинаем встречу.",
            },
            {
                "id": 2,
                "type": "message",
                "date": "2026-10-20T10:05:00",
                "from": "Bob",
                "from_id": "user1002",
                "text": "Здравствуйте, коллеги. Спасибо за ссылку.",
            },
            {
                "id": 3,
                "type": "message",
                "date": "2026-10-20T10:06:00",
                "from": "Alice",
                "from_id": "user1001",
                "text": [
                    "Отправляю документ и ссылку: ",
                    {"type": "link", "text": "https://example.com"},
                    " проверьте плз)"
                ],
            },
            {
                "id": 4,
                "type": "service",
                "date": "2026-10-20T10:10:00",
                "action": "pin_message",
            }
        ]
    }

    export_file = tmp_path / "result.json"
    with open(export_file, "w", encoding="utf-8") as f:
        json.dump(sample_export, f)

    importer = TelegramJsonImporter(profiler=test_profiler, owner_id=1001)
    summary = await importer.import_file(export_file)

    assert summary["processed_messages"] == 3
    assert summary["skipped_messages"] == 1
    assert summary["unique_users_profiled"] == 2

    async with test_db.connect() as conn:
        repo = ProfileRepository(conn)
        alice_profile = await repo.get_profile(1001, chat_id=1234567)
        assert alice_profile is not None
        assert alice_profile["sample_count"] == 2
        assert alice_profile["is_owner"] == 1

        bob_profile = await repo.get_profile(1002, chat_id=1234567)
        assert bob_profile is not None
        assert bob_profile["sample_count"] == 1
        assert bob_profile["is_owner"] == 0
