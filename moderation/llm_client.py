"""Async client for OpenAI-compatible LLM endpoints (OpenAI, Gemini, DeepSeek, Ollama, etc.)."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional
import aiohttp

logger = logging.getLogger(__name__)


class LLMClient:
    """Universal asynchronous client for OpenAI-compatible Chat Completions API."""

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.openai.com/v1",
        model: str = "gpt-4o-mini",
        timeout_seconds: float = 8.0,
    ) -> None:
        self.api_key = api_key.strip() if api_key else ""
        self.base_url = base_url.strip().rstrip("/") if base_url else "https://api.openai.com/v1"
        self.model = model.strip() if model else "gpt-4o-mini"
        self.timeout = aiohttp.ClientTimeout(total=timeout_seconds)

    def update_config(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
    ) -> None:
        """Dynamically update client credentials and endpoint at runtime."""
        if api_key is not None:
            self.api_key = api_key.strip()
        if base_url is not None:
            self.base_url = base_url.strip().rstrip("/")
        if model is not None:
            self.model = model.strip()

    async def test_connection(self) -> tuple[bool, str, float]:
        """Test LLM connectivity and measure response latency in milliseconds."""
        if not self.api_key:
            return False, "API-ключ не установлен", 0.0

        start_t = time.perf_counter()
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": "user", "content": "Ping. Answer with one word: Pong"}],
            "max_tokens": 10,
            "temperature": 0.0,
        }

        try:
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                async with session.post(url, headers=headers, json=payload) as resp:
                    elapsed = (time.perf_counter() - start_t) * 1000
                    if resp.status != 200:
                        err_text = await resp.text()
                        return False, f"HTTP {resp.status}: {err_text[:120]}", elapsed
                    data = await resp.json()
                    choices = data.get("choices", [])
                    if choices and "message" in choices[0]:
                        msg = choices[0]["message"].get("content", "").strip()
                        return True, msg, elapsed
                    return False, "Некорректный формат ответа от API", elapsed
        except asyncio.TimeoutError:
            elapsed = (time.perf_counter() - start_t) * 1000
            return False, f"Таймаут соединения ({self.timeout.total} сек)", elapsed
        except Exception as e:
            elapsed = (time.perf_counter() - start_t) * 1000
            return False, f"Ошибка соединения: {str(e)[:120]}", elapsed

    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.0,
        max_tokens: int = 150,
        response_json: bool = False,
    ) -> Optional[str]:
        """Send chat completion request to configured LLM endpoint."""
        if not self.api_key:
            logger.debug("LLMClient called without API key. Skipping.")
            return None

        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if response_json:
            payload["response_format"] = {"type": "json_object"}

        try:
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                async with session.post(url, headers=headers, json=payload) as resp:
                    if resp.status != 200:
                        err_text = await resp.text()
                        logger.warning("LLM API returned HTTP %s from %s: %s", resp.status, url, err_text[:200])
                        return None
                    data = await resp.json()
                    choices = data.get("choices", [])
                    if choices and "message" in choices[0]:
                        return choices[0]["message"].get("content", "").strip()
                    return None
        except asyncio.TimeoutError:
            logger.warning("LLM API call timed out after %s seconds", self.timeout.total)
            return None
        except Exception as e:
            logger.warning("Failed to call LLM API at %s: %s", url, e)
            return None
