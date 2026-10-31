"""Модуль обнаружения ненормативной лексики и оскорблений с поддержкой 3 уровней строгости и пользовательских стоп-слов."""

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
    method: str
    reason: str
    confidence: float
    severity: str = "hard"  # "hard", "medium", "mild", "custom"


class ProfanityDetector:
    """
    Детектор ненормативной лексики:
    - Защита от обходов: подмена букв (латиница/кириллица, омоглифы, leetspeak, 0->o, 1->i, 3->з, 4->ч, @->а, $->с),
      невидимые символы (zero-width spaces), точки/пробелы между буквами, повторы букв ('сууукааа').
    - 3 уровня строгости (strictness):
        'hard'   — только тяжелый мат (сука, пидор, гандон, хуй, пизда, ебать, блядь и их производные/маскировки).
        'medium' — тяжелый мат + грубые оскорбления (урод, тварь, мразь, дебил, даун, гнида).
        'all'    — максимальная строгость (+ легкая брань и обзывательства: блин, тупой, дурак, чмо, лох, идиот).
    - Пользовательские стоп-слова (custom_words) для каждого чата.
    """

    HOMOGLYPHS = {
        'a': 'а', 'b': 'в', 'c': 'с', 'e': 'е', 'h': 'н', 'i': 'и', 'j': 'й',
        'k': 'к', 'm': 'м', 'o': 'о', 'p': 'р', 's': 'с', 't': 'т', 'u': 'у',
        'x': 'х', 'y': 'у',
        '0': 'о', '1': 'и', '3': 'з', '4': 'ч', '6': 'б', '@': 'а', '$': 'с',
        '!': 'и',
    }

    # 1. ЖЕСТКИЙ МАТ (HARD)
    HARD_PATTERNS: List[re.Pattern[str]] = [
        re.compile(r"х+у+[йиеяёюeja]", re.IGNORECASE),
        re.compile(r"п+и+з+д", re.IGNORECASE),
        re.compile(r"([а-я]*[еёe]б[аеиоутылaeyut]|\b[еёe]б\b|долбо[еёe]б|выеб|уеб|въеб)", re.IGNORECASE),
        re.compile(r"б+л+я+([дdтt]|ть)?", re.IGNORECASE),
        re.compile(r"м+у+д+[аеиоукч]", re.IGNORECASE),
        re.compile(r"п+и+д+[аоеи]?р", re.IGNORECASE),
        re.compile(r"ш+л+ю+х", re.IGNORECASE),
        re.compile(r"г+[ао]?н+д+[ао]?н", re.IGNORECASE),
        re.compile(r"\bс+у+к+[аеиыу]?\b", re.IGNORECASE),
        re.compile(r"\bс+у+ч+[кч][аеиыу]?\b", re.IGNORECASE),
        re.compile(r"залуп", re.IGNORECASE),
        re.compile(r"дроч", re.IGNORECASE),
        re.compile(r"ебл[оаищ]", re.IGNORECASE),
        re.compile(r"пизд[еаоыу]", re.IGNORECASE),
        re.compile(r"оху[ееияю]", re.IGNORECASE),
        re.compile(r"аху[ееияю]", re.IGNORECASE),
        re.compile(r"наху[йия]", re.IGNORECASE),
        re.compile(r"поху[йия]", re.IGNORECASE),
    ]

    # 2. ГРУБЫЕ ОСКОРБЛЕНИЯ (MEDIUM)
    MEDIUM_PATTERNS: List[re.Pattern[str]] = [
        re.compile(r"\bурод[а-я]*\b", re.IGNORECASE),
        re.compile(r"\bтварь\b", re.IGNORECASE),
        re.compile(r"\bмраз[а-я]*\b", re.IGNORECASE),
        re.compile(r"\bдебил[а-я]*\b", re.IGNORECASE),
        re.compile(r"\bдаун[а-я]*\b", re.IGNORECASE),
        re.compile(r"\bгнид[а-я]*\b", re.IGNORECASE),
    ]

    # 3. ЛЕГКАЯ БРАНЬ И ТОКСИЧНОСТЬ (MILD / ALL)
    MILD_PATTERNS: List[re.Pattern[str]] = [
        re.compile(r"\bтуп+[оыае][йеяюе]?\b", re.IGNORECASE),
        re.compile(r"\bтупиц[аеыу]\b", re.IGNORECASE),
        re.compile(r"\bдур+[а-я]*\b", re.IGNORECASE),
        re.compile(r"\bидиот[а-я]*\b", re.IGNORECASE),
        re.compile(r"\bкретин[а-я]*\b", re.IGNORECASE),
        re.compile(r"\bчмо[а-я]*\b", re.IGNORECASE),
        re.compile(r"\bлох[а-я]*\b", re.IGNORECASE),
        re.compile(r"\bблин\b", re.IGNORECASE),
    ]

    # Белый список частых слов, содержащих похожие корни без мата
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
        re.compile(r"^дубрав[а-я]*", re.IGNORECASE),
    ]

    def __init__(self, llm_client: Optional[LLMClient] = None, llm_enabled: bool = False) -> None:
        self.llm_client = llm_client
        self.llm_enabled = llm_enabled
        self._cache: Dict[str, ProfanityResult] = {}
        self._max_cache_size = 1000

    def set_llm_enabled(self, enabled: bool) -> None:
        self.llm_enabled = enabled
        self._cache.clear()

    @classmethod
    def normalize(cls, text: str) -> str:
        """Нормализует текст: убирает невидимые символы, мапит похожие буквы и сжимает повторы."""
        if not text:
            return ""
        t = text.lower()
        t = re.sub(r"[​-‏﻿­]", "", t)
        trans = str.maketrans(cls.HOMOGLYPHS)
        t = t.translate(trans)
        t = re.sub(r"(.)\1{2,}", r"\1", t)
        return t

    def check_regex(
        self,
        text: str,
        strictness: str = "hard",
        custom_words: Optional[List[str]] = None,
    ) -> Optional[ProfanityResult]:
        if not text or not text.strip():
            return None

        normalized = self.normalize(text)

        # 0. Проверка пользовательских стоп-слов чата
        if custom_words:
            for cw in custom_words:
                cw_norm = self.normalize(cw.strip())
                if cw_norm and len(cw_norm) >= 2:
                    if re.search(rf"\b{re.escape(cw_norm)}\b", normalized):
                        return ProfanityResult(
                            is_profane=True,
                            method="regex",
                            reason=f"Запрещенное слово чата: {cw}",
                            confidence=1.0,
                            severity="custom",
                        )

        # 1. Проверка по токенам (обычные слова)
        tokens = re.findall(r"[а-яa-z0-9]+", normalized)
        for token in tokens:
            if any(wl.search(token) for wl in self.WHITELIST_PATTERNS):
                continue

            for pat in self.HARD_PATTERNS:
                if pat.search(token):
                    return ProfanityResult(
                        is_profane=True,
                        method="regex",
                        reason="Обнаружен жесткий мат",
                        confidence=0.99,
                        severity="hard",
                    )

            if strictness in ("medium", "all"):
                for pat in self.MEDIUM_PATTERNS:
                    if pat.search(token):
                        return ProfanityResult(
                            is_profane=True,
                            method="regex",
                            reason="Обнаружено грубое оскорбление",
                            confidence=0.96,
                            severity="medium",
                        )

            if strictness == "all":
                for pat in self.MILD_PATTERNS:
                    if pat.search(token):
                        return ProfanityResult(
                            is_profane=True,
                            method="regex",
                            reason="Обнаружена легкая брань / токсичность",
                            confidence=0.95,
                            severity="mild",
                        )

        # 2. Проверка слов, разделенных точками, пробелами или спецсимволами ('с.у.к.а', 'п и д о р')
        alpha_only = re.sub(r"[^а-яa-z0-9]", "", normalized)
        if alpha_only and len(alpha_only) >= 3:
            if not any(wl.search(alpha_only) for wl in self.WHITELIST_PATTERNS):
                for pat in self.HARD_PATTERNS:
                    if pat.search(alpha_only):
                        return ProfanityResult(
                            is_profane=True,
                            method="regex",
                            reason="Обнаружен замаскированный жесткий мат",
                            confidence=0.98,
                            severity="hard",
                        )

                if strictness in ("medium", "all"):
                    for pat in self.MEDIUM_PATTERNS:
                        if pat.search(alpha_only):
                            return ProfanityResult(
                                is_profane=True,
                                method="regex",
                                reason="Обнаружено замаскированное оскорбление",
                                confidence=0.94,
                                severity="medium",
                            )

                if strictness == "all":
                    for pat in self.MILD_PATTERNS:
                        if pat.search(alpha_only):
                            return ProfanityResult(
                                is_profane=True,
                                method="regex",
                                reason="Обнаружена замаскированная брань / токсичность",
                                confidence=0.92,
                                severity="mild",
                            )

        return None

    async def check_text(
        self,
        text: str,
        strictness: str = "hard",
        custom_words: Optional[List[str]] = None,
    ) -> ProfanityResult:
        cleaned = text.strip()
        if not cleaned:
            return ProfanityResult(is_profane=False, method="clean", reason="", confidence=1.0)

        cw_key = ",".join(sorted(custom_words)) if custom_words else ""
        cache_key = f"{strictness}:{cw_key}:{cleaned}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        regex_match = self.check_regex(cleaned, strictness=strictness, custom_words=custom_words)
        if regex_match:
            self._save_to_cache(cache_key, regex_match)
            return regex_match

        if self.llm_enabled and self.llm_client and len(cleaned) > 2:
            llm_result = await self._check_with_llm(cleaned, strictness=strictness)
            if llm_result:
                self._save_to_cache(cache_key, llm_result)
                return llm_result

        result = ProfanityResult(is_profane=False, method="clean", reason="", confidence=0.9)
        self._save_to_cache(cache_key, result)
        return result

    async def _check_with_llm(self, text: str, strictness: str = "hard") -> Optional[ProfanityResult]:
        if strictness == "hard":
            strictness_rule = (
                "Ты должен регистрировать ТОЛЬКО РЕАЛЬНО ЖЕСТКИЙ МАТ (сука, пидор, гандон, хуй, пизда, ебать, блядь и их любые скрытые формы).\n"
                "Обычные ругательства (блин, дурак, тупой, черт, хрен, капец, урод) НЕ считай матом (is_profane: false)."
            )
        elif strictness == "medium":
            strictness_rule = (
                "Ты должен регистрировать ЖЕСТКИЙ МАТ + ГРУБЫЕ ОСКОРБЛЕНИЯ (урод, тварь, мразь, дебил, даун, гнида).\n"
                "Легкие междометия (блин, капец, черт) НЕ считай нарушением (is_profane: false)."
            )
        else:
            strictness_rule = (
                "Ты должен регистрировать КАК ЖЕСТКИЙ МАТ, ТАК И ЛЮБУЮ БРАНЬ / ТОКСИЧНЫЕ ОСКОРБЛЕНИЯ (блин, тупой, дурак, дебил, даун, урод, мразь и т.д.)."
            )

        prompt_system = (
            "Ты — строгий экспертный модератор чата Telegram.\n"
            f"{strictness_rule}\n"
            "Учитывай разные буквы, подмены (латиница/кириллица, цифры 0, 1, 3, 4, символы @, $, точки и пробелы между буквами).\n"
            "Ответь ИСКЛЮЧИТЕЛЬНО в формате JSON без markdown:\n"
            '{"is_profane": true, "severity": "hard", "reason": "Причина на русском", "confidence": 0.95}'
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
            is_prof = bool(data.get("is_profane"))
            severity = str(data.get("severity", "hard" if strictness == "hard" else "mild"))

            if strictness == "hard" and severity in ("mild", "medium"):
                is_prof = False
            elif strictness == "medium" and severity == "mild":
                is_prof = False

            return ProfanityResult(
                is_profane=is_prof,
                method="llm",
                reason=str(data.get("reason", "Обнаружена ненормативная лексика")),
                confidence=float(data.get("confidence", 0.9)),
                severity=severity,
            )
        except Exception as e:
            logger.warning("Failed to parse LLM moderation JSON response: %s (raw: %s)", e, response_text[:100])
            return None

    def _save_to_cache(self, key: str, value: ProfanityResult) -> None:
        if len(self._cache) >= self._max_cache_size:
            self._cache.pop(next(iter(self._cache)))
        self._cache[key] = value
