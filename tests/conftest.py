import os
import sys
from pathlib import Path
from typing import AsyncGenerator

import aiosqlite
import pytest
import pytest_asyncio

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from database.connection import Database
from database.schema import init_db
from analytics.profiler import StyleProfiler


@pytest_asyncio.fixture
async def test_db(tmp_path: Path) -> AsyncGenerator[Database, None]:
    db_file = tmp_path / "test_forwarder.db"
    db = Database(str(db_file))

    async with db.connect() as conn:
        await init_db(conn)

    yield db


@pytest_asyncio.fixture
async def test_profiler(test_db: Database) -> StyleProfiler:
    return StyleProfiler(db=test_db)
