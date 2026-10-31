from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from database.repositories.base import BaseRepository

logger = logging.getLogger(__name__)


class UserRepository(BaseRepository):

    async def upsert_user(
        self,
        user_id: int,
        username: Optional[str] = None,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
        role: Optional[str] = None,
        is_authorized: Optional[bool] = None,
        is_blocked: Optional[bool] = None,
    ) -> Dict[str, Any]:
        existing = await self.get_user(user_id)
        if existing:
            new_role = role if role is not None else existing["role"]
            new_auth = (1 if is_authorized else 0) if is_authorized is not None else existing["is_authorized"]
            new_block = (1 if is_blocked else 0) if is_blocked is not None else existing["is_blocked"]

            await self.execute(
                """
                UPDATE users
                SET username = ?, first_name = ?, last_name = ?, role = ?,
                    is_authorized = ?, is_blocked = ?, updated_at = CURRENT_TIMESTAMP
                WHERE user_id = ?
                """,
                (username, first_name, last_name, new_role, new_auth, new_block, user_id),
            )
        else:
            await self.execute(
                """
                INSERT INTO users (
                    user_id, username, first_name, last_name, role,
                    is_authorized, is_blocked, authorized_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """,
                (
                    user_id,
                    username,
                    first_name,
                    last_name,
                    role or "user",
                    1 if is_authorized else 0,
                    1 if is_blocked else 0,
                ),
            )
        row = await self.get_user(user_id)
        return dict(row) if row else {}

    async def get_user(self, user_id: int) -> Optional[Dict[str, Any]]:
        row = await self.fetch_one("SELECT * FROM users WHERE user_id = ?", (user_id,))
        return dict(row) if row else None

    async def list_users(self, limit: int = 100) -> List[Dict[str, Any]]:
        rows = await self.fetch_all(
            """
            SELECT u.*,
                   (SELECT COUNT(*) FROM routes r WHERE r.created_by_user_id = u.user_id) AS routes_count
            FROM users u
            WHERE u.user_id NOT IN (1087968824, 777000, 136817688)
            ORDER BY u.created_at DESC
            LIMIT ?
            """,
            (limit,),
        )
        return [dict(r) for r in rows]

    async def set_authorized(self, user_id: int, is_authorized: bool = True) -> None:
        await self.execute(
            """
            UPDATE users
            SET is_authorized = ?, authorized_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
            WHERE user_id = ?
            """,
            (1 if is_authorized else 0, user_id),
        )

    async def set_blocked(self, user_id: int, is_blocked: bool = True) -> None:
        await self.execute(
            """
            UPDATE users
            SET is_blocked = ?, updated_at = CURRENT_TIMESTAMP
            WHERE user_id = ?
            """,
            (1 if is_blocked else 0, user_id),
        )

    async def set_role(self, user_id: int, role: str) -> None:
        valid_roles = {"owner", "admin", "subadmin", "user", "guest"}
        if role not in valid_roles:
            raise ValueError(f"Invalid role: {role}")
        await self.execute(
            "UPDATE users SET role = ?, updated_at = CURRENT_TIMESTAMP WHERE user_id = ?",
            (role, user_id),
        )

    async def is_user_authorized(self, user_id: int) -> bool:
        row = await self.fetch_one("SELECT is_authorized FROM users WHERE user_id = ?", (user_id,))
        return bool(row["is_authorized"]) if row else False

    async def is_user_blocked(self, user_id: int) -> bool:
        row = await self.fetch_one("SELECT is_blocked FROM users WHERE user_id = ?", (user_id,))
        return bool(row["is_blocked"]) if row else False


    async def get_access_password(self, default: str = "7788") -> str:
        row = await self.fetch_one("SELECT value FROM app_state WHERE key = 'access_password'")
        return row["value"] if row else default

    async def set_access_password(self, password: str) -> None:
        await self.execute(
            """
            INSERT INTO app_state (key, value, updated_at)
            VALUES ('access_password', ?, CURRENT_TIMESTAMP)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP
            """,
            (password.strip(),),
        )

    async def is_password_required(self, default: bool = True) -> bool:
        row = await self.fetch_one("SELECT value FROM app_state WHERE key = 'password_required'")
        if not row:
            return default
        return row["value"] == "1"

    async def set_password_required(self, required: bool) -> None:
        await self.execute(
            """
            INSERT INTO app_state (key, value, updated_at)
            VALUES ('password_required', ?, CURRENT_TIMESTAMP)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP
            """,
            ("1" if required else "0",),
        )
