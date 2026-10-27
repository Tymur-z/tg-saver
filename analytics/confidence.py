from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, List


@dataclass
class ConfidenceAssessment:

    level: str
    label_ru: str
    sample_count: int
    margin_of_error_pct: float
    is_statistically_valid: bool
    observations: List[str]
    hypotheses: List[str]
    alternative_explanations: List[str]
    ethical_disclaimer: str


class ConfidenceEvaluator:

    MIN_THRESHOLD = 10
    LOW_THRESHOLD = 50
    MODERATE_THRESHOLD = 200

    DISCLAIMER_TEXT = (
        "⚠️ Данный срез отражает исключительно измеряемые параметры письменной речи в мессенджере "
        "и частотные характеристики текста. Система не определяет психологические черты, истинные намерения, "
        "эмоциональное состояние или медицинские особенности автора. Скорость ответа или краткость формулировок "
        "могут быть обусловлены внешними обстоятельствами (занятость, устройство ввода, формат задач)."
    )

    @classmethod
    def evaluate(cls, sample_count: int, profile_metrics: Dict[str, Any]) -> ConfidenceAssessment:
        if sample_count < cls.MIN_THRESHOLD:
            return ConfidenceAssessment(
                level="INSUFFICIENT",
                label_ru=f"Недостаточно данных (требуется от {cls.MIN_THRESHOLD} сообщений, собрано: {sample_count})",
                sample_count=sample_count,
                margin_of_error_pct=100.0,
                is_statistically_valid=False,
                observations=["Выборка слишком мала для выявления устойчивых языковых привычек."],
                hypotheses=[],
                alternative_explanations=["Единичные сообщения не отражают средний стиль общения."],
                ethical_disclaimer=cls.DISCLAIMER_TEXT,
            )

        margin = round(min(50.0, (1.0 / math.sqrt(sample_count)) * 100.0), 1)

        if sample_count < cls.LOW_THRESHOLD:
            level = "LOW"
            label = f"Низкая уверенность (предварительный срез, {sample_count} сообщений, погрешность ~±{margin}%)"
            valid = True
        elif sample_count < cls.MODERATE_THRESHOLD:
            level = "MODERATE"
            label = f"Умеренная уверенность (устойчивые паттерны, {sample_count} сообщений, погрешность ~±{margin}%)"
            valid = True
        else:
            level = "HIGH"
            label = f"Высокая надёжность (репрезентативная база, {sample_count} сообщений, погрешность ~±{margin}%)"
            valid = True

        observations: List[str] = []
        hypotheses: List[str] = []
        alternatives: List[str] = []

        total_words = profile_metrics.get("total_words", 0)
        avg_sentence_len = profile_metrics.get("avg_sentence_len", 0.0)
        punct = profile_metrics.get("punctuation_stats", {})
        formality = profile_metrics.get("formality_markers", {})
        emojis = profile_metrics.get("emoji_stats", {})

        observations.append(f"Проанализировано сообщений: {sample_count}, суммарно слов: {total_words}.")
        if avg_sentence_len > 0:
            observations.append(f"Средняя длина смыслового блока: {avg_sentence_len:.1f} слов на предложение.")

        trailing_dot_pct = punct.get("no_trailing_dot_pct", 0)
        observations.append(f"Опущение точки в конце финального сообщения: {trailing_dot_pct:.1f}% случаев.")

        if avg_sentence_len < 4.0:
            hypotheses.append("Преобладание коротких реплик и лаконичных ответов.")
            alternatives.append("Возможен частый ввод со смартфона на ходу или специфика рабочих коротких подтверждений.")
        elif avg_sentence_len > 12.0:
            hypotheses.append("Тенденция к развёрнутому изложению мыслей с сложной синтаксической структурой.")
            alternatives.append("Возможно написание отчётов, инструкций или разбор технических вопросов.")

        slang_pct = formality.get("slang_frequency_per_100w", 0)
        polite_pct = formality.get("polite_frequency_per_100w", 0)
        if slang_pct > 2.0:
            hypotheses.append("Широкое применение разговорных сокращений и сетевого сленга.")
            alternatives.append("Неформальная атмосфера в конкретной группе среди близких коллег или друзей.")
        if polite_pct > 2.0:
            hypotheses.append("Регулярное использование этикетных формул и маркеров вежливости.")

        top_emojis = emojis.get("top_emojis", [])
        if top_emojis:
            observations.append(f"Наиболее частые графические символы: {' '.join(top_emojis[:5])}")

        return ConfidenceAssessment(
            level=level,
            label_ru=label,
            sample_count=sample_count,
            margin_of_error_pct=margin,
            is_statistically_valid=valid,
            observations=observations,
            hypotheses=hypotheses,
            alternative_explanations=alternatives,
            ethical_disclaimer=cls.DISCLAIMER_TEXT,
        )
