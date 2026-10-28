"""Hybrid profanity and toxicity detector: fast regex heuristics + deep LLM verification."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from moderation.llm_client import LLMClient

logger = logging.getLogger(__name__)


@dataclass
class ProfanityResult:
    is_profane: bool
    method: str  # "regex", "llm", "clean"
    reason: str
    confidence: float


class ProfanityDetector:
    """Two-tier profanity detection engine with heuristic pre-filtering and LLM fallback."""

    # Normalization mapping for common letter/symbol substitutions (leetspeak)
    LEET_MAP = str.maketrans({
        "@": "а", "a": "а", "0": "о", "o": "о", "3": "з", "e": "е",
        "1": "и", "i": "и", "!": "и", "4": "ч", "$": "с", "c": "с",
        "y": "у", "u": "у", "x": "х", "p": "р", "b": "в", "k": "к",
        "t": "т", "h": "н", "m": "м",
    })

    # Core Russian obscene roots (мат)
    PROFANITY_PATTERNS: List[re.Pattern[str]] = [
        re.compile(r"[хx][уy][йиеяёюeja]", re.IGNORECASE),
        re.compile(r"[пp][иe1i][зz3][дd]", re.IGNORECASE),
        re.compile(r"([а-я]*[еёe][бb][аеиоутылaeyut]|\b[еёe][бb]\b|долбо[еёe]б|выеб)", re.IGNORECASE),
        re.compile(r"[бb][лl][яe]([дdтt]|ть)?", re.IGNORECASE),
        re.compile(r"[мm][уy][дd][аеиоуaeyo][кчd]", re.IGNORECASE),
        re.compile(r"[пp][иe1i][дd][аоa][рr]", re.IGNORECASE),
        re.compile(r"[шsh][лl][юy][хx]", re.IGNORECASE),
        re.compile(r"[гg][аоao][нn][дd][оo][нn]", re.IGNORECASE),
        re.compile(r"\b[сs][уy][кk][аеиыуaeyu]\b", re.IGNORECASE),
    ]

    # Whitelist for innocent Russian words that contain similar substrings
    WHITELIST_PATTERNS: List[re.Pattern[str]] = [
        re.compile(r"^рубл[яейь]", re.IGNORECASE),
        re.compile(r"^страхов[а-я]*", re.IGNORECASE),
        re.compile(r"^колебан[а-я]*", re.IGNORECASE),
        re.compile(r"^употреблен[а-я]*", re.IGNORECASE),
        re.compile(r"^влюбл[а-я]*", re.IGNORECASE),
        re.compile(r"^стебел[а-я]*", re.IGNORECASE),
        re.compile(r"^хлеб[а-я]*", re.IGNORECASE),
        re.compile(r"^теребит[а-я]*", re.IGNORECASE),
        re.compile(r"^педикюр[а-я]*", re.IGNORECASE),
        re.compile(r"^оскорбл[а-я]*", re.IGNORECASE),
        re.compile(r"^сабл[яеиь]", re.IGNORECASE),
        re.compile(r"^потреб[а-я]*", re.IGNORECASE),
        re.compile(r"^гребл[яеиь]", re.IGNORECASE),
    ]

    def __init__(self, llm_client: Optional[LLMClient] = None, llm_enabled: bool = False) -> None:
        self.llm_client = llm_client
        self.llm_enabled = llm_enabled
        self._cache: Dict[str, ProfanityResult] = {}
        self._max_cache_size = 1000

    def set_llm_enabled(self, enabled: bool) -> None:
        """Dynamically toggle LLM deep check on or off and flush cache."""
        self.llm_enabled = enabled
        self._cache.clear()

    def check_regex(self, text: str) -> Optional[ProfanityResult]:
        """Perform fast, zero-latency heuristic check for obvious obscenities."""
        if not text or not text.strip():
            return None

        normalized = text.lower()
        # Collapse repeated letters: "ееееббббааать" -> "ебать"
        collapsed = re.sub(r"(.)\1{2,}", r"\1\1", normalized)

        # Extract word tokens
        tokens = re.findall(r"[a-zA-Zа-яА-ЯёЁ0-9@!$]+", collapsed)
        for token in tokens:
            # 1. Whitelist check for this token
            if any(wl.search(token) for wl in self.WHITELIST_PATTERNS):
                continue

            # 2. Transliterate leetspeak for this token
            translit_token = token.translate(self.LEET_MAP)

            # 3. Profanity pattern check
            for pat in self.PROFANITY_PATTERNS:
                if pat.search(token) or pat.search(translit_token):
                    return ProfanityResult(
                        is_profane=True,
                        method="regex",
                        reason="Ненормативная лексика",
                        confidence=0.98,
                    )
        return None

    async def check_text(self, text: str) -> ProfanityResult:
        """Evaluate text using fast heuristics first, falling back to LLM if enabled."""
        cleaned = text.strip()
        if not cleaned:
            return ProfanityResult(is_profane=False, method="clean", reason="", confidence=1.0)

        # Check in-memory cache
        if cleaned in self._cache:
            return self._cache[cleaned]

        # Tier 1: Fast Regex Check
        regex_match = self.check_regex(cleaned)
        if regex_match:
            self._save_to_cache(cleaned, regex_match)
            return regex_match

        # Tier 2: LLM Deep Analysis if enabled
        if self.llm_enabled and self.llm_client and len(cleaned) > 2:
            llm_result = await self._check_with_llm(cleaned)
            if llm_result:
                self._save_to_cache(cleaned, llm_result)
                return llm_result

        result = ProfanityResult(is_profane=False, method="clean", reason="", confidence=0.9)
        self._save_to_cache(cleaned, result)
        return result

    async def _check_with_llm(self, text: str) -> Optional[ProfanityResult]:
        """Ask LLM to classify text for profanity, masked obscenities, or severe toxicity."""
        prompt_system = (
            "Ты — строгий русскоязычный модератор чата. Твоя задача — выявлять:\n"
            "1. Нецензурную брань (русский мат, в том числе завуалированный, со скрытыми буквами/символами или транслитом).\n"
            "2. Прямые грубые оскорбления участников.\n"
            "Обычные разговорные слова (блин, черт, хрен, дурак, фигня, жесть) НЕ считай матом.\n"
            "Ответь СТРОГО в формате JSON без разметки markdown:\n"
            '{"is_profane": true, "reason": "краткое пояснение на русском", "confidence": 0.95}'
        )
        messages = [
            {"role": "system", "content": prompt_system},
            {"role": "user", "content": f'Проверь сообщение: "{text}"'},
        ]
        assert self.llm_client is not None
        response_text = await self.llm_client.chat_completion(messages, temperature=0.0, max_tokens=100)
        if not response_text:
            return None

        try:
            clean_json = response_text.strip()
            if clean_json.startswith("```"):
                clean_json = clean_json.strip("`")
                if clean_json.startswith("json"):
                    clean_json = clean_json[4:].strip()
            data = json.loads(clean_json)
            return ProfanityResult(
                is_profane=bool(data.get("is_profane")),
                method="llm",
                reason=str(data.get("reason", "Обнаружена ненормативная лексика")),
                confidence=float(data.get("confidence", 0.9)),
            )
        except Exception as e:
            logger.warning("Failed to parse LLM moderation JSON response: %s (raw: %s)", e, response_text[:100])
            return None

    def _save_to_cache(self, key: str, value: ProfanityResult) -> None:
        if len(self._cache) >= self._max_cache_size:
            self._cache.pop(next(iter(self._cache)))
        self._cache[key] = value
