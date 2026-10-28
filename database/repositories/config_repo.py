"""Repository for managing application dynamic runtime configuration stored in SQLite."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional
from database.repositories.base import BaseRepository

logger = logging.getLogger(__name__)


class ConfigRepository(BaseRepository):
    """Manages key-value pairs stored in app_state table."""

    async def get_value(self, key: str, default: Optional[str] = None) -> Optional[str]:
        row = await self.fetch_one("SELECT value FROM app_state WHERE key = ?", (key,))
        if row and row["value"] is not None:
            return str(row["value"])
        return default

    async def set_value(self, key: str, value: str) -> None:
        await self.execute(
            """
            INSERT INTO app_state (key, value, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP
            """,
            (key, str(value)),
        )

    async def get_llm_config(
        self,
        default_enabled: bool = False,
        default_api_key: str = "",
        default_base_url: str = "https://api.openai.com/v1",
        default_model: str = "gpt-4o-mini",
    ) -> Dict[str, Any]:
        """Fetch active LLM settings from app_state, falling back to passed defaults."""
        enabled_val = await self.get_value("llm_enabled", "1" if default_enabled else "0")
        api_key_val = await self.get_value("llm_api_key", default_api_key)
        base_url_val = await self.get_value("llm_base_url", default_base_url)
        model_val = await self.get_value("llm_model", default_model)

        return {
            "llm_enabled": enabled_val == "1",
            "llm_api_key": api_key_val or "",
            "llm_base_url": base_url_val or default_base_url,
            "llm_model": model_val or default_model,
        }

    async def set_llm_config(
        self,
        enabled: Optional[bool] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Update any subset of LLM settings in app_state."""
        if enabled is not None:
            await self.set_value("llm_enabled", "1" if enabled else "0")
        if api_key is not None:
            await self.set_value("llm_api_key", api_key.strip())
        if base_url is not None:
            await self.set_value("llm_base_url", base_url.strip().rstrip("/"))
        if model is not None:
            await self.set_value("llm_model", model.strip())

        return await self.get_llm_config()
