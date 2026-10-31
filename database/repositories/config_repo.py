from __future__ import annotations

import logging
from typing import Any, Dict, Optional
from database.repositories.base import BaseRepository

logger = logging.getLogger(__name__)


class ConfigRepository(BaseRepository):

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
        default_context_limit: int = 15,
        default_max_tokens: int = 800,
        default_temperature: float = 0.7,
        default_persona: str = "student",
        default_custom_prompt: str = "",
        default_trigger_mode: str = "name_and_reply",
        default_typing_indicator: bool = True,
        default_random_reply_chance: int = 0,
    ) -> Dict[str, Any]:
        enabled_val = await self.get_value("llm_enabled", "1" if default_enabled else "0")
        api_key_val = await self.get_value("llm_api_key", default_api_key)
        base_url_val = await self.get_value("llm_base_url", default_base_url)
        model_val = await self.get_value("llm_model", default_model)
        ctx_val = await self.get_value("llm_context_limit", str(default_context_limit))
        tokens_val = await self.get_value("llm_max_tokens", str(default_max_tokens))
        temp_val = await self.get_value("llm_temperature", str(default_temperature))

        try:
            ctx_int = int(ctx_val) if ctx_val else default_context_limit
        except ValueError:
            ctx_int = default_context_limit

        try:
            tokens_int = int(tokens_val) if tokens_val else default_max_tokens
        except ValueError:
            tokens_int = default_max_tokens

        try:
            temp_flt = float(temp_val) if temp_val else default_temperature
        except ValueError:
            temp_flt = default_temperature

        persona_val = await self.get_value("llm_companion_persona", default_persona)
        custom_prompt_val = await self.get_value("llm_companion_custom_prompt", default_custom_prompt)
        trigger_val = await self.get_value("llm_companion_trigger_mode", default_trigger_mode)
        typing_val = await self.get_value("llm_companion_typing", "1" if default_typing_indicator else "0")
        rand_val = await self.get_value("llm_companion_random_chance", str(default_random_reply_chance))
        try:
            rand_int = int(rand_val) if rand_val else 0
        except ValueError:
            rand_int = 0

        return {
            "llm_enabled": enabled_val == "1",
            "llm_api_key": api_key_val or "",
            "llm_base_url": base_url_val or default_base_url,
            "llm_model": model_val or default_model,
            "companion_context_limit": ctx_int,
            "companion_max_tokens": tokens_int,
            "companion_temperature": temp_flt,
            "companion_persona": persona_val or "student",
            "companion_custom_prompt": custom_prompt_val or "",
            "companion_trigger_mode": trigger_val or "name_and_reply",
            "companion_typing_indicator": typing_val == "1",
            "companion_random_reply_chance": rand_int,
        }

    async def set_llm_config(
        self,
        enabled: Optional[bool] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        context_limit: Optional[int] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        persona: Optional[str] = None,
        custom_prompt: Optional[str] = None,
        trigger_mode: Optional[str] = None,
        typing_indicator: Optional[bool] = None,
        random_reply_chance: Optional[int] = None,
    ) -> Dict[str, Any]:
        if enabled is not None:
            await self.set_value("llm_enabled", "1" if enabled else "0")
        if api_key is not None:
            await self.set_value("llm_api_key", api_key.strip())
        if base_url is not None:
            await self.set_value("llm_base_url", base_url.strip().rstrip("/"))
        if model is not None:
            await self.set_value("llm_model", model.strip())
        if context_limit is not None:
            await self.set_value("llm_context_limit", str(context_limit))
        if max_tokens is not None:
            await self.set_value("llm_max_tokens", str(max_tokens))
        if temperature is not None:
            await self.set_value("llm_temperature", str(temperature))
        if persona is not None:
            await self.set_value("llm_companion_persona", persona.strip())
        if custom_prompt is not None:
            await self.set_value("llm_companion_custom_prompt", custom_prompt.strip())
        if trigger_mode is not None:
            await self.set_value("llm_companion_trigger_mode", trigger_mode.strip())
        if typing_indicator is not None:
            await self.set_value("llm_companion_typing", "1" if typing_indicator else "0")
        if random_reply_chance is not None:
            await self.set_value("llm_companion_random_chance", str(random_reply_chance))

        return await self.get_llm_config()


    async def get_stt_config(
        self,
        default_enabled: bool = True,
        default_api_key: str = "",
        default_function_id: str = "b702f636-f60c-4a3d-a6f4-f3568c13bd7d",
        default_uri: str = "grpc.nvcf.nvidia.com:443",
        default_language: str = "ru-RU",
    ) -> Dict[str, Any]:
        enabled_val = await self.get_value("stt_enabled", "1" if default_enabled else "0")
        api_key_val = await self.get_value("stt_api_key", default_api_key)
        func_id_val = await self.get_value("stt_function_id", default_function_id)
        uri_val = await self.get_value("stt_uri", default_uri)
        lang_val = await self.get_value("stt_language", default_language)
        return {
            "stt_enabled": enabled_val == "1",
            "stt_api_key": api_key_val or default_api_key,
            "stt_function_id": func_id_val or default_function_id,
            "stt_uri": uri_val or default_uri,
            "stt_language": lang_val or default_language,
        }

    async def set_stt_config(
        self,
        enabled: Optional[bool] = None,
        api_key: Optional[str] = None,
        function_id: Optional[str] = None,
        uri: Optional[str] = None,
        language: Optional[str] = None,
    ) -> Dict[str, Any]:
        if enabled is not None:
            await self.set_value("stt_enabled", "1" if enabled else "0")
        if api_key is not None:
            await self.set_value("stt_api_key", api_key.strip())
        if function_id is not None:
            await self.set_value("stt_function_id", function_id.strip())
        if uri is not None:
            await self.set_value("stt_uri", uri.strip())
        if language is not None:
            await self.set_value("stt_language", language.strip())
        return await self.get_stt_config()
