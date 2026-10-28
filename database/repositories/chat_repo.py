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

    async def toggle_setting(self, chat_id: int, field_name: str) -> bool:
        """Toggle a boolean moderation setting for a specific chat."""
        allowed_fields = {
            "profanity_filter_enabled",
            "profanity_warn_enabled",
            "profanity_delete_enabled",
            "chat_ai_enabled",
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
