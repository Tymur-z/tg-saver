from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional
from database.repositories.base import BaseRepository

logger = logging.getLogger(__name__)


class RouteRepository(BaseRepository):

    async def create_route(
        self,
        name: str,
        source_chat_id: int,
        destination_chat_id: int,
        mode: str = "forward",
        filter_media_types: Optional[List[str]] = None,
        filter_keywords: Optional[List[str]] = None,
        filter_exclude_keywords: Optional[List[str]] = None,
        is_active: bool = True,
        created_by_user_id: int = 0,
        ) -> Dict[str, Any]:
        await self.execute(
            """
            INSERT INTO chats (chat_id, title, chat_type, is_source, is_destination)
            VALUES (?, ?, 'unknown', 1, 0)
            ON CONFLICT(chat_id) DO UPDATE SET is_source = 1
            """,
            (source_chat_id, f"Chat {source_chat_id}"),
        )
        await self.execute(
            """
            INSERT INTO chats (chat_id, title, chat_type, is_source, is_destination)
            VALUES (?, ?, 'unknown', 0, 1)
            ON CONFLICT(chat_id) DO UPDATE SET is_destination = 1
            """,
            (destination_chat_id, f"Chat {destination_chat_id}"),
        )

        media_types_json = json.dumps(filter_media_types or [])
        keywords_json = json.dumps(filter_keywords or [])
        exclude_json = json.dumps(filter_exclude_keywords or [])

        cursor = await self.execute(
            """
            INSERT INTO routes (
                name, source_chat_id, destination_chat_id, mode,
                filter_media_types, filter_keywords, filter_exclude_keywords, is_active,
                created_by_user_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                name,
                source_chat_id,
                destination_chat_id,
                mode,
                media_types_json,
                keywords_json,
                exclude_json,
                1 if is_active else 0,
                created_by_user_id,
            ),
        )
        route_id = cursor.lastrowid
        row = await self.get_route(route_id)
        return self._format_route(dict(row)) if row else {}

    async def get_route(self, route_id: int) -> Optional[Dict[str, Any]]:
        row = await self.fetch_one(
            """
            SELECT r.*,
                   sc.title AS source_title,
                   dc.title AS dest_title,
                   u.username AS creator_username,
                   u.first_name AS creator_name
            FROM routes r
            LEFT JOIN chats sc ON r.source_chat_id = sc.chat_id
            LEFT JOIN chats dc ON r.destination_chat_id = dc.chat_id
            LEFT JOIN users u ON r.created_by_user_id = u.user_id
            WHERE r.id = ?
            """,
            (route_id,),
        )
        return self._format_route(dict(row)) if row else None

    async def list_routes(
        self,
        user_id: Optional[int] = None,
        active_only: bool = False,
        is_owner: bool = False,
    ) -> List[Dict[str, Any]]:
        sql = """
            SELECT r.*,
                   sc.title AS source_title,
                   dc.title AS dest_title,
                   u.username AS creator_username,
                   u.first_name AS creator_name
            FROM routes r
            LEFT JOIN chats sc ON r.source_chat_id = sc.chat_id
            LEFT JOIN chats dc ON r.destination_chat_id = dc.chat_id
            LEFT JOIN users u ON r.created_by_user_id = u.user_id
            WHERE 1=1
        """
        params: List[Any] = []
        if user_id is not None:
            if is_owner and user_id > 0:
                sql += " AND (r.created_by_user_id = ? OR r.created_by_user_id = 0)"
                params.append(user_id)
            elif user_id > 0:
                sql += " AND r.created_by_user_id = ?"
                params.append(user_id)
            else:
                sql += " AND r.created_by_user_id = -1" 

        if active_only:
            sql += " AND r.is_active = 1"
        sql += " ORDER BY r.id ASC"

        rows = await self.fetch_all(sql, tuple(params))
        return [self._format_route(dict(r)) for r in rows]

    async def get_routes_for_source(self, source_chat_id: int, active_only: bool = True) -> List[Dict[str, Any]]:
        sql = """
            SELECT r.*,
                   sc.title AS source_title,
                   dc.title AS dest_title
            FROM routes r
            LEFT JOIN chats sc ON r.source_chat_id = sc.chat_id
            LEFT JOIN chats dc ON r.destination_chat_id = dc.chat_id
            WHERE r.source_chat_id = ?
        """
        if active_only:
            sql += " AND r.is_active = 1"
        sql += " ORDER BY r.id ASC"

        rows = await self.fetch_all(sql, (source_chat_id,))
        return [self._format_route(dict(r)) for r in rows]

    async def toggle_route(self, route_id: int, is_active: bool) -> bool:
        cursor = await self.execute(
            "UPDATE routes SET is_active = ? WHERE id = ?",
            (1 if is_active else 0, route_id),
        )
        return cursor.rowcount > 0

    async def toggle_mode(self, route_id: int) -> str:
        route = await self.get_route(route_id)
        if not route:
            return "forward"
        new_mode = "copy" if route["mode"] == "forward" else "forward"
        await self.execute("UPDATE routes SET mode = ? WHERE id = ?", (new_mode, route_id))
        return new_mode

    async def toggle_field(self, route_id: int, field_name: str) -> bool:
        valid_fields = {"clean_links", "clean_tags", "clean_mentions", "append_source_link"}
        if field_name not in valid_fields:
            raise ValueError(f"Invalid field name: {field_name}")
        route = await self.get_route(route_id)
        if not route:
            return False
        current_val = bool(route.get(field_name, 0))
        new_val = 0 if current_val else 1
        await self.execute(f"UPDATE routes SET {field_name} = ? WHERE id = ?", (new_val, route_id))
        return bool(new_val)

    async def toggle_media_type(self, route_id: int, media_type: str) -> List[str]:
        route = await self.get_route(route_id)
        if not route:
            return []
        current: List[str] = list(route.get("filter_media_types", []))
        if media_type in current:
            current.remove(media_type)
        else:
            current.append(media_type)
        await self.execute(
            "UPDATE routes SET filter_media_types = ? WHERE id = ?",
            (json.dumps(current), route_id),
        )
        return current

    async def set_all_media_types(self, route_id: int, enable_all: bool) -> List[str]:
        all_types = ["text", "photo", "video", "video_note", "voice", "document", "audio", "sticker", "animation"]
        new_val = all_types if enable_all else []
        await self.execute(
            "UPDATE routes SET filter_media_types = ? WHERE id = ?",
            (json.dumps(new_val), route_id),
        )
        return new_val

    async def add_keyword(self, route_id: int, keyword: str) -> List[str]:
        route = await self.get_route(route_id)
        if not route:
            return []
        kws: List[str] = list(route.get("filter_keywords", []))
        cleaned = keyword.strip().lower()
        if cleaned and cleaned not in kws:
            kws.append(cleaned)
            await self.execute("UPDATE routes SET filter_keywords = ? WHERE id = ?", (json.dumps(kws), route_id))
        return kws

    async def clear_keywords(self, route_id: int) -> None:
        await self.execute("UPDATE routes SET filter_keywords = '[]' WHERE id = ?", (route_id,))

    async def add_exclude_keyword(self, route_id: int, keyword: str) -> List[str]:
        route = await self.get_route(route_id)
        if not route:
            return []
        kws: List[str] = list(route.get("filter_exclude_keywords", []))
        cleaned = keyword.strip().lower()
        if cleaned and cleaned not in kws:
            kws.append(cleaned)
            await self.execute("UPDATE routes SET filter_exclude_keywords = ? WHERE id = ?", (json.dumps(kws), route_id))
        return kws

    async def clear_exclude_keywords(self, route_id: int) -> None:
        await self.execute("UPDATE routes SET filter_exclude_keywords = '[]' WHERE id = ?", (route_id,))

    async def delete_route(self, route_id: int) -> bool:
        cursor = await self.execute("DELETE FROM routes WHERE id = ?", (route_id,))
        return cursor.rowcount > 0

    async def get_route_pairs(self) -> List[tuple[int, int]]:
        rows = await self.fetch_all("SELECT source_chat_id, destination_chat_id FROM routes WHERE is_active = 1")
        return [(r["source_chat_id"], r["destination_chat_id"]) for r in rows]

    def _format_route(self, r: Dict[str, Any]) -> Dict[str, Any]:
        res = dict(r)
        for key in ("filter_media_types", "filter_keywords", "filter_exclude_keywords"):
            val = res.get(key)
            if isinstance(val, str):
                try:
                    res[key] = json.loads(val)
                except Exception:
                    res[key] = []
            elif val is None:
                res[key] = []
        return res

    async def migrate_chat_id(self, old_id: int, new_id: int) -> None:
        await self.execute("UPDATE routes SET source_chat_id = ? WHERE source_chat_id = ?", (new_id, old_id))
        await self.execute("UPDATE routes SET destination_chat_id = ? WHERE destination_chat_id = ?", (new_id, old_id))
