from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional
from database.repositories.base import BaseRepository

logger = logging.getLogger(__name__)


class ProfileRepository(BaseRepository):


    async def get_profile(self, user_id: int, chat_id: int = 0) -> Optional[Dict[str, Any]]:
        row = await self.fetch_one(
            "SELECT p.*, u.username, u.first_name, u.last_name, u.role FROM user_style_profiles p LEFT JOIN users u ON p.user_id = u.user_id WHERE p.user_id = ? AND p.chat_id = ?",
            (user_id, chat_id),
        )
        return self._format_profile(dict(row)) if row else None

    async def upsert_profile(
        self,
        user_id: int,
        chat_id: int,
        is_owner: bool,
        sample_count: int,
        total_words: int,
        total_characters: int,
        avg_sentence_len: float,
        lexical_richness: float,
        punctuation_stats: Dict[str, Any],
        emoji_stats: Dict[str, Any],
        formality_markers: Dict[str, Any],
        activity_hours: Dict[str, int],
    ) -> None:
        await self.execute(
            """
            INSERT INTO user_style_profiles (
                user_id, chat_id, is_owner, sample_count, total_words, total_characters,
                avg_sentence_len, lexical_richness, punctuation_stats, emoji_stats,
                formality_markers, activity_hours, last_updated
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id, chat_id) DO UPDATE SET
                is_owner = excluded.is_owner,
                sample_count = excluded.sample_count,
                total_words = excluded.total_words,
                total_characters = excluded.total_characters,
                avg_sentence_len = excluded.avg_sentence_len,
                lexical_richness = excluded.lexical_richness,
                punctuation_stats = excluded.punctuation_stats,
                emoji_stats = excluded.emoji_stats,
                formality_markers = excluded.formality_markers,
                activity_hours = excluded.activity_hours,
                last_updated = CURRENT_TIMESTAMP
            """,
            (
                user_id,
                chat_id,
                1 if is_owner else 0,
                sample_count,
                total_words,
                total_characters,
                avg_sentence_len,
                lexical_richness,
                json.dumps(punctuation_stats),
                json.dumps(emoji_stats),
                json.dumps(formality_markers),
                json.dumps(activity_hours),
            ),
        )

    async def list_profiles(self, limit: int = 50) -> List[Dict[str, Any]]:
        rows = await self.fetch_all(
            "SELECT p.*, u.username, u.first_name, u.last_name, u.role FROM user_style_profiles p LEFT JOIN users u ON p.user_id = u.user_id WHERE p.chat_id = 0 ORDER BY p.sample_count DESC LIMIT ?",
            (limit,),
        )
        return [self._format_profile(dict(r)) for r in rows]

    async def delete_user_profile(self, user_id: int) -> int:
        cursor = await self.execute("DELETE FROM user_style_profiles WHERE user_id = ?", (user_id,))
        return cursor.rowcount

    async def delete_all_profiles(self) -> int:
        cursor = await self.execute("DELETE FROM user_style_profiles")
        return cursor.rowcount


    async def is_excluded(self, entity_type: str, entity_id: int) -> bool:
        row = await self.fetch_one(
            "SELECT is_excluded FROM privacy_settings WHERE entity_type = ? AND entity_id = ?",
            (entity_type, entity_id),
        )
        return bool(row["is_excluded"]) if row else False

    async def set_exclusion(self, entity_type: str, entity_id: int, is_excluded: bool = True) -> None:
        await self.execute(
            """
            INSERT INTO privacy_settings (entity_type, entity_id, is_excluded)
            VALUES (?, ?, ?)
            ON CONFLICT(entity_type, entity_id) DO UPDATE SET is_excluded = excluded.is_excluded
            """,
            (entity_type, entity_id, 1 if is_excluded else 0),
        )

    async def remove_exclusion(self, entity_type: str, entity_id: int) -> bool:
        cursor = await self.execute(
            "DELETE FROM privacy_settings WHERE entity_type = ? AND entity_id = ?",
            (entity_type, entity_id),
        )
        return cursor.rowcount > 0

    async def list_exclusions(self) -> List[Dict[str, Any]]:
        rows = await self.fetch_all("SELECT * FROM privacy_settings ORDER BY created_at DESC")
        return [dict(r) for r in rows]


    async def get_state(self, key: str, default: Optional[str] = None) -> Optional[str]:
        row = await self.fetch_one("SELECT value FROM app_state WHERE key = ?", (key,))
        return row["value"] if row else default

    async def set_state(self, key: str, value: str) -> None:
        await self.execute(
            """
            INSERT INTO app_state (key, value, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP
            """,
            (key, value),
        )

    async def is_system_paused(self) -> bool:
        val = await self.get_state("is_paused", "0")
        return val == "1"

    async def set_system_paused(self, paused: bool) -> None:
        await self.set_state("is_paused", "1" if paused else "0")

    def _format_profile(self, p: Dict[str, Any]) -> Dict[str, Any]:
        res = dict(p)
        for key in ("punctuation_stats", "emoji_stats", "formality_markers", "activity_hours"):
            val = res.get(key)
            if isinstance(val, str):
                try:
                    res[key] = json.loads(val)
                except Exception:
                    res[key] = {}
            elif val is None:
                res[key] = {}
        return res
