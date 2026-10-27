from __future__ import annotations

import logging
from typing import Any, List, Optional
import aiosqlite

logger = logging.getLogger(__name__)


class BaseRepository:

    def __init__(self, conn: aiosqlite.Connection) -> None:
        self.conn = conn

    async def execute(self, query: str, parameters: tuple[Any, ...] = ()) -> aiosqlite.Cursor:
        return await self.conn.execute(query, parameters)

    async def executemany(self, query: str, parameters_list: list[tuple[Any, ...]]) -> aiosqlite.Cursor:
        return await self.conn.executemany(query, parameters_list)

    async def fetch_one(self, query: str, parameters: tuple[Any, ...] = ()) -> Optional[aiosqlite.Row]:
        cursor = await self.conn.execute(query, parameters)
        row = await cursor.fetchone()
        await cursor.close()
        return row

    async def fetch_all(self, query: str, parameters: tuple[Any, ...] = ()) -> List[aiosqlite.Row]:
        cursor = await self.conn.execute(query, parameters)
        rows = await cursor.fetchall()
        await cursor.close()
        return rows
