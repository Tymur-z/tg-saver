from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from analytics.profiler import StyleProfiler

logger = logging.getLogger(__name__)


class TelegramJsonImporter:

    def __init__(self, profiler: StyleProfiler, owner_id: int = 0) -> None:
        self.profiler = profiler
        self.owner_id = owner_id

    async def import_file(self, file_path: str | Path, target_chat_id: Optional[int] = None) -> Dict[str, Any]:
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Export file not found: {path}")

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        chat_id = target_chat_id or data.get("id", 0)
        chat_name = data.get("name", "Unknown Chat")
        raw_messages = data.get("messages", [])

        processed_count = 0
        skipped_count = 0
        users_encountered: set[int] = set()

        for item in raw_messages:
            if item.get("type") != "message":
                skipped_count += 1
                continue

            raw_from_id = item.get("from_id")
            if not raw_from_id:
                skipped_count += 1
                continue

            user_id = 0
            if isinstance(raw_from_id, str) and raw_from_id.startswith("user"):
                try:
                    user_id = int(raw_from_id[4:])
                except ValueError:
                    user_id = 0
            elif isinstance(raw_from_id, int):
                user_id = raw_from_id

            if user_id == 0:
                skipped_count += 1
                continue

            date_str = item.get("date", "")
            try:
                dt = datetime.fromisoformat(date_str)
            except Exception:
                dt = datetime.now()

            raw_text = item.get("text", "")
            if isinstance(raw_text, list):
                text_parts = []
                for part in raw_text:
                    if isinstance(part, str):
                        text_parts.append(part)
                    elif isinstance(part, dict) and "text" in part:
                        text_parts.append(part["text"])
                text = "".join(text_parts)
            else:
                text = str(raw_text)

            if not text.strip():
                skipped_count += 1
                continue

            is_reply = bool(item.get("reply_to_message_id"))
            is_owner = bool(self.owner_id > 0 and user_id == self.owner_id)

            success = await self.profiler.process_message(
                user_id=user_id,
                chat_id=chat_id,
                text=text,
                created_at=dt,
                is_reply=is_reply,
                is_owner=is_owner,
            )
            if success:
                processed_count += 1
                users_encountered.add(user_id)
            else:
                skipped_count += 1

        logger.info(
            "Import finished for %s: %s messages processed, %s unique users.",
            chat_name,
            processed_count,
            len(users_encountered),
        )

        return {
            "chat_name": chat_name,
            "chat_id": chat_id,
            "processed_messages": processed_count,
            "skipped_messages": skipped_count,
            "unique_users_profiled": len(users_encountered),
        }
