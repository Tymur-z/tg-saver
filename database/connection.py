from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

import aiosqlite

logger = logging.getLogger(__name__)


class Database:

    def __init__(self, db_path: str = "data/forwarder.db") -> None:
        self.db_path = db_path
        self._ensure_parent_directory()

    def _ensure_parent_directory(self) -> None:
        path = Path(self.db_path)
        if path.parent:
            path.parent.mkdir(parents=True, exist_ok=True)

    @asynccontextmanager
    async def connect(self) -> AsyncGenerator[aiosqlite.Connection, None]:
        conn = await aiosqlite.connect(self.db_path)
        conn.row_factory = aiosqlite.Row
        try:
            await conn.execute("PRAGMA journal_mode = WAL;")
            await conn.execute("PRAGMA synchronous = NORMAL;")
            await conn.execute("PRAGMA foreign_keys = ON;")
            await conn.execute("PRAGMA busy_timeout = 5000;")
            yield conn
            await conn.commit()
        except Exception:
            await conn.rollback()
            raise
        finally:
            await conn.close()

    @asynccontextmanager
    async def transaction(self) -> AsyncGenerator[aiosqlite.Connection, None]:
        async with self.connect() as conn:
            await conn.execute("BEGIN IMMEDIATE;")
            try:
                yield conn
                await conn.commit()
            except Exception:
                await conn.rollback()
                raise
