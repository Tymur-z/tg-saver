from __future__ import annotations

import logging
from typing import Any, Dict, Optional
from database.repositories.base import BaseRepository

logger = logging.getLogger(__name__)


class ForwardRepository(BaseRepository):

    async def get_forward_record(
        self,
        route_id: int,
        source_chat_id: int,
        source_message_id: int,
    ) -> Optional[Dict[str, Any]]:
        row = await self.fetch_one(
            """
            SELECT * FROM forward_logs
            WHERE route_id = ? AND source_chat_id = ? AND source_message_id = ?
            """,
            (route_id, source_chat_id, source_message_id),
        )
        return dict(row) if row else None

    async def is_already_forwarded(
        self,
        route_id: int,
        source_chat_id: int,
        source_message_id: int,
    ) -> bool:
        row = await self.get_forward_record(route_id, source_chat_id, source_message_id)
        if not row:
            return False
        return row["status"] in ("SENT", "PENDING")

    async def record_pending(
        self,
        route_id: int,
        source_chat_id: int,
        source_message_id: int,
        dest_chat_id: int,
        media_group_id: Optional[str] = None,
    ) -> int:
        cursor = await self.execute(
            """
            INSERT INTO forward_logs (
                route_id, source_chat_id, source_message_id, dest_chat_id,
                media_group_id, status
            )
            VALUES (?, ?, ?, ?, ?, 'PENDING')
            ON CONFLICT(route_id, source_chat_id, source_message_id) DO UPDATE SET
                status = 'PENDING',
                error_message = NULL,
                created_at = CURRENT_TIMESTAMP
            """,
            (route_id, source_chat_id, source_message_id, dest_chat_id, media_group_id),
        )
        return cursor.lastrowid

    async def mark_sent(
        self,
        route_id: int,
        source_chat_id: int,
        source_message_id: int,
        dest_message_id: Optional[int] = None,
    ) -> None:
        await self.execute(
            """
            UPDATE forward_logs
            SET status = 'SENT', dest_message_id = ?, error_message = NULL
            WHERE route_id = ? AND source_chat_id = ? AND source_message_id = ?
            """,
            (dest_message_id, route_id, source_chat_id, source_message_id),
        )

    async def mark_failed(
        self,
        route_id: int,
        source_chat_id: int,
        source_message_id: int,
        error_message: str,
    ) -> None:
        await self.execute(
            """
            UPDATE forward_logs
            SET status = 'FAILED', error_message = ?
            WHERE route_id = ? AND source_chat_id = ? AND source_message_id = ?
            """,
            (error_message[:500], route_id, source_chat_id, source_message_id),
        )

    async def mark_filtered(
        self,
        route_id: int,
        source_chat_id: int,
        source_message_id: int,
        dest_chat_id: int,
        reason: str,
    ) -> None:
        await self.execute(
            """
            INSERT INTO forward_logs (
                route_id, source_chat_id, source_message_id, dest_chat_id, status, error_message
            )
            VALUES (?, ?, ?, ?, 'FILTERED', ?)
            ON CONFLICT(route_id, source_chat_id, source_message_id) DO UPDATE SET
                status = 'FILTERED',
                error_message = excluded.error_message
            """,
            (route_id, source_chat_id, source_message_id, dest_chat_id, reason),
        )

    async def cleanup_old_logs(self, retention_days: int) -> int:
        cursor = await self.execute(
            """
            DELETE FROM forward_logs
            WHERE created_at < datetime('now', '-' || ? || ' days')
            """,
            (retention_days,),
        )
        return cursor.rowcount

    async def get_stats(self) -> Dict[str, int]:
        rows = await self.fetch_all("SELECT status, COUNT(*) as cnt FROM forward_logs GROUP BY status")
        stats: Dict[str, int] = {"TOTAL": 0, "SENT": 0, "FAILED": 0, "FILTERED": 0, "PENDING": 0}
        for r in rows:
            st = r["status"]
            cnt = r["cnt"]
            stats[st] = cnt
            stats["TOTAL"] += cnt
        return stats
