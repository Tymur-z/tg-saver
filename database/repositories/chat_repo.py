from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from database.repositories.base import BaseRepository

logger = logging.getLogger(__name__)


class ChatRepository(BaseRepository):

    async def upsert_chat(
        self,
        chat_id: int,
        title: str,
        chat_type: str,
        username: Optional[str] = None,
        is_source: Optional[bool] = None,
        is_destination: Optional[bool] = None,
    ) -> Dict[str, Any]:
        existing = await self.get_chat(chat_id)
        if existing:
            new_is_source = existing["is_source"] if is_source is None else (1 if is_source else 0)
            new_is_dest = existing["is_destination"] if is_destination is None else (1 if is_destination else 0)
            await self.execute(
                """
                UPDATE chats
                SET title = ?, chat_type = ?, username = ?, is_source = ?, is_destination = ?, updated_at = CURRENT_TIMESTAMP
                WHERE chat_id = ?
                """,
                (title, chat_type, username, new_is_source, new_is_dest, chat_id),
            )
        else:
            await self.execute(
                """
                INSERT INTO chats (chat_id, title, chat_type, username, is_source, is_destination)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    chat_id,
                    title,
                    chat_type,
                    username,
                    1 if is_source else 0,
                    1 if is_destination else 0,
                ),
            )
        row = await self.get_chat(chat_id)
        return dict(row) if row else {}

    async def ensure_chat_exists(
        self,
        chat_id: int,
        is_source: bool = False,
        is_destination: bool = False,
        title: Optional[str] = None,
        chat_type: str = "unknown",
        username: Optional[str] = None,
    ) -> None:
        existing = await self.get_chat(chat_id)
        if not existing:
            await self.execute(
                """
                INSERT INTO chats (chat_id, title, chat_type, username, is_source, is_destination)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(chat_id) DO NOTHING
                """,
                (
                    chat_id,
                    title or f"Chat {chat_id}",
                    chat_type,
                    username,
                    1 if is_source else 0,
                    1 if is_destination else 0,
                ),
            )
        else:
            updates = []
            params = []
            if title and existing["title"].startswith("Chat "):
                updates.append("title = ?")
                params.append(title)
            if username and not existing.get("username"):
                updates.append("username = ?")
                params.append(username)
            if is_source and not existing["is_source"]:
                updates.append("is_source = 1")
            if is_destination and not existing["is_destination"]:
                updates.append("is_destination = 1")
            if updates:
                params.append(chat_id)
                await self.execute(
                    f"UPDATE chats SET {', '.join(updates)}, updated_at = CURRENT_TIMESTAMP WHERE chat_id = ?",
                    tuple(params),
                )

    async def get_chat(self, chat_id: int) -> Optional[Dict[str, Any]]:
        row = await self.fetch_one("SELECT * FROM chats WHERE chat_id = ?", (chat_id,))
        return dict(row) if row else None

    async def list_sources(self, user_id: Optional[int] = None) -> List[Dict[str, Any]]:
        if user_id and user_id > 0:
            rows = await self.fetch_all(
                """
                SELECT DISTINCT c.* FROM chats c
                LEFT JOIN routes r ON r.source_chat_id = c.chat_id
                WHERE c.is_source = 1 AND (c.registered_by_user_id = ? OR r.created_by_user_id = ?)
                ORDER BY c.title ASC
                """,
                (user_id, user_id),
            )
        else:
            rows = await self.fetch_all("SELECT * FROM chats WHERE is_source = 1 ORDER BY title ASC")
        return [dict(r) for r in rows]

    async def list_destinations(self, user_id: Optional[int] = None) -> List[Dict[str, Any]]:
        if user_id and user_id > 0:
            rows = await self.fetch_all(
                """
                SELECT DISTINCT c.* FROM chats c
                LEFT JOIN routes r ON r.destination_chat_id = c.chat_id
                WHERE c.is_destination = 1 AND (c.registered_by_user_id = ? OR r.created_by_user_id = ?)
                ORDER BY c.title ASC
                """,
                (user_id, user_id),
            )
        else:
            rows = await self.fetch_all("SELECT * FROM chats WHERE is_destination = 1 ORDER BY title ASC")
        return [dict(r) for r in rows]

    async def list_all(self) -> List[Dict[str, Any]]:
        rows = await self.fetch_all("SELECT * FROM chats ORDER BY title ASC")
        return [dict(r) for r in rows]

    async def list_moderation_chats(self) -> List[Dict[str, Any]]:
        """Return all group, supergroup, and channel chats for moderation settings."""
        rows = await self.fetch_all(
            """
            SELECT * FROM chats
            WHERE chat_type IN ('group', 'supergroup', 'channel')
            ORDER BY title ASC
            """
        )
        return [dict(r) for r in rows]



    async def set_strictness(self, chat_id: int, strictness: str) -> None:
        valid = {"hard", "medium", "all"}
        val = strictness if strictness in valid else "hard"
        await self.execute(
            "UPDATE chats SET profanity_strictness = ?, updated_at = CURRENT_TIMESTAMP WHERE chat_id = ?",
            (val, chat_id),
        )

    async def set_custom_words(self, chat_id: int, words: List[str]) -> None:
        import json
        clean_words = [w.strip().lower() for w in words if w.strip()]
        await self.execute(
            "UPDATE chats SET custom_profanity_words = ?, updated_at = CURRENT_TIMESTAMP WHERE chat_id = ?",
            (json.dumps(clean_words, ensure_ascii=False), chat_id),
        )

    async def cycle_strictness(self, chat_id: int) -> str:
        """Cycles between 'hard' (только жесткий мат) and 'all' (жесткий мат + легкая брань/оскорбления)."""
        chat = await self.get_chat(chat_id)
        current = chat.get("profanity_strictness", "hard") if chat else "hard"
        cycle_map = {"hard": "medium", "medium": "all", "all": "hard"}
        new_val = cycle_map.get(current, "hard")
        await self.execute(
            "UPDATE chats SET profanity_strictness = ?, updated_at = CURRENT_TIMESTAMP WHERE chat_id = ?",
            (new_val, chat_id),
        )
        return new_val


    async def set_delete_warn_seconds(self, chat_id: int, seconds: int) -> None:
        val = max(0, seconds)
        await self.execute(
            "UPDATE chats SET profanity_delete_warn_seconds = ?, updated_at = CURRENT_TIMESTAMP WHERE chat_id = ?",
            (val, chat_id),
        )

    async def cycle_delete_warn_seconds(self, chat_id: int) -> int:
        chat = await self.get_chat(chat_id)
        current = int(chat.get("profanity_delete_warn_seconds", 0)) if chat else 0
        cycle_map = {0: 15, 15: 30, 30: 60, 60: 0}
        new_val = cycle_map.get(current, 0)
        await self.set_delete_warn_seconds(chat_id, new_val)
        return new_val

    async def set_whitelist_words(self, chat_id: int, words: List[str]) -> None:
        import json
        clean_words = [w.strip().lower() for w in words if w.strip()]
        await self.execute(
            "UPDATE chats SET custom_whitelist_words = ?, updated_at = CURRENT_TIMESTAMP WHERE chat_id = ?",
            (json.dumps(clean_words, ensure_ascii=False), chat_id),
        )

    async def set_auto_mute(self, chat_id: int, duration_seconds: int) -> None:
        val = max(0, duration_seconds)
        await self.execute(
            "UPDATE chats SET auto_mute_duration = ?, updated_at = CURRENT_TIMESTAMP WHERE chat_id = ?",
            (val, chat_id),
        )

    async def cycle_auto_mute(self, chat_id: int) -> int:
        chat = await self.get_chat(chat_id)
        current = int(chat.get("auto_mute_duration", 0)) if chat else 0
        cycle_map = {0: 600, 600: 3600, 3600: 86400, 86400: 0}
        new_val = cycle_map.get(current, 0)
        await self.set_auto_mute(chat_id, new_val)
        return new_val

    async def toggle_setting(self, chat_id: int, field_name: str) -> bool:
        """Toggle a boolean moderation setting for a specific chat."""
        allowed_fields = {
            "profanity_filter_enabled",
            "profanity_warn_enabled",
            "profanity_delete_enabled",
            "chat_ai_enabled",
            "llm_moderation_enabled",
        }
        if field_name not in allowed_fields:
            raise ValueError(f"Invalid chat setting field: {field_name}")

        chat = await self.get_chat(chat_id)
        if not chat:
            return False

        current_val = bool(chat.get(field_name, 0))
        new_val = 0 if current_val else 1
        await self.execute(
            f"UPDATE chats SET {field_name} = ?, updated_at = CURRENT_TIMESTAMP WHERE chat_id = ?",
            (new_val, chat_id),
        )
        return bool(new_val)

    async def set_role(self, chat_id: int, is_source: bool, is_destination: bool) -> None:
        await self.execute(
            """
            UPDATE chats
            SET is_source = ?, is_destination = ?, updated_at = CURRENT_TIMESTAMP
            WHERE chat_id = ?
            """,
            (1 if is_source else 0, 1 if is_destination else 0, chat_id),
        )

    async def delete_chat(self, chat_id: int) -> bool:
        cursor = await self.execute("DELETE FROM chats WHERE chat_id = ?", (chat_id,))
        return cursor.rowcount > 0

    async def add_companion_message(
        self,
        chat_id: int,
        user_id: int,
        user_name: str,
        text: str,
        username: Optional[str] = None,
        is_bot: bool = False,
    ) -> None:
        await self.execute(
            "INSERT INTO companion_chat_history (chat_id, user_id, user_name, username, text, is_bot) VALUES (?, ?, ?, ?, ?, ?)",
            (chat_id, user_id, user_name, username or "", text, 1 if is_bot else 0),
        )

    async def get_last_message_from_user(
        self,
        chat_id: int,
        target_name: str,
    ) -> Optional[Dict[str, Any]]:
        clean_target = target_name.strip().lstrip("@").lower()
        row = await self.fetch_one(
            "SELECT * FROM companion_chat_history WHERE chat_id = ? AND is_bot = 0 AND (lower(user_name) LIKE '%' || ? || '%' OR lower(username) = ?) ORDER BY id DESC LIMIT 1",
            (chat_id, clean_target, clean_target),
        )
        return dict(row) if row else None

    async def get_companion_history(self, chat_id: int, limit: int = 25) -> List[Dict[str, Any]]:
        rows = await self.fetch_all(
            "SELECT * FROM (SELECT * FROM companion_chat_history WHERE chat_id = ? ORDER BY id DESC LIMIT ?) ORDER BY id ASC",
            (chat_id, limit),
        )
        return [dict(r) for r in rows]

    async def clear_companion_history(self, chat_id: int) -> int:
        cursor = await self.execute("DELETE FROM companion_chat_history WHERE chat_id = ?", (chat_id,))
        return cursor.rowcount

    async def clear_all_companion_history(self) -> int:
        cursor = await self.execute("DELETE FROM companion_chat_history")
        return cursor.rowcount

    async def record_violation(self, chat_id: int, user_id: int, reason: str, severity: str = "hard") -> None:
        await self.execute(
            "INSERT INTO moderation_violations (chat_id, user_id, reason, severity) VALUES (?, ?, ?, ?)",
            (chat_id, user_id, reason, severity),
        )

    async def count_recent_violations(self, chat_id: int, user_id: int, hours: int = 24) -> int:
        row = await self.fetch_one(
            "SELECT COUNT(*) AS cnt FROM moderation_violations WHERE chat_id = ? AND user_id = ? AND created_at >= datetime('now', '-' || ? || ' hours')",
            (chat_id, user_id, hours),
        )
        return int(row["cnt"]) if row else 0
