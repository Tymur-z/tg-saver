from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from analytics.extractor import FeatureExtractor

logger = logging.getLogger(__name__)


class StyleComparator:

    @classmethod
    def compare(cls, text: str, baseline: Dict[str, Any]) -> Dict[str, Any]:
        features = FeatureExtractor.extract(text=text, created_at=datetime.now())

        b_sample_count = baseline.get("sample_count", 0)
        b_avg_sent = baseline.get("avg_sentence_len", 0.0)
        b_punct = baseline.get("punctuation_stats", {})
        b_formality = baseline.get("formality_markers", {})
        b_emojis = baseline.get("emoji_stats", {})

        diffs: List[str] = []
        similarity_points = 100.0

        if b_avg_sent > 0:
            ratio = features.avg_sentence_len / b_avg_sent
            if ratio > 1.8:
                diffs.append(
                    f"Длина предложений заметно выше обычной: {features.avg_sentence_len:.1f} слов "
                    f"(ваш базовый уровень: {b_avg_sent:.1f} слов/предл.)."
                )
                similarity_points -= 20.0
            elif ratio < 0.5 and features.word_count > 3:
                diffs.append(
                    f"Слишком лаконично по сравнению с базой: {features.avg_sentence_len:.1f} слов "
                    f"(базовый уровень: {b_avg_sent:.1f})."
                )
                similarity_points -= 15.0

        b_no_dot_pct = b_punct.get("no_trailing_dot_pct", 50.0)
        if b_no_dot_pct > 75.0 and features.has_trailing_dot:
            diffs.append("Вы редко ставите точку в конце последнего предложения (в базе: опущена в 75%+ случаев).")
            similarity_points -= 10.0
        elif b_no_dot_pct < 25.0 and not features.has_trailing_dot:
            diffs.append("Обычно вы завершаете финальную мысль точкой.")
            similarity_points -= 10.0

        b_top_emojis: List[str] = b_emojis.get("top_emojis", [])
        if features.emoji_count > 0:
            matched = [em for em in features.emojis if em in b_top_emojis]
            if not matched and b_top_emojis:
                diffs.append(f"Использованы эмодзи, не входящие в ваш топ: {features.emojis}")
                similarity_points -= 10.0
        elif b_emojis.get("total_emojis", 0) / max(1, b_sample_count) > 1.0:
            diffs.append("В базовом стиле вы чаще сопровождаете сообщения эмодзи.")
            similarity_points -= 5.0

        b_brackets = b_punct.get("total_bracket_smiles", 0)
        if b_brackets / max(1, b_sample_count) > 0.4 and features.bracket_smiles_count == 0:
            diffs.append("Обычно вы используете скобки в качестве смайликов ')'.")
            similarity_points -= 5.0

        similarity_score = max(0.0, min(100.0, round(similarity_points, 1)))

        return {
            "similarity_score": similarity_score,
            "observations": diffs if diffs else ["Текст полностью соответствует вашим типичным языковым паттернам."],
            "candidate_stats": {
                "words": features.word_count,
                "avg_sentence_len": features.avg_sentence_len,
                "has_trailing_dot": features.has_trailing_dot,
                "emoji_count": features.emoji_count,
            },
        }

    @classmethod
    def generate_mimicry_prompt(cls, baseline: Dict[str, Any]) -> str:
        n = baseline.get("sample_count", 0)
        avg_sent = baseline.get("avg_sentence_len", 0.0)
        punct = baseline.get("punctuation_stats", {})
        emojis = baseline.get("emoji_stats", {})
        formality = baseline.get("formality_markers", {})

        no_dot = punct.get("no_trailing_dot_pct", 50.0) > 60.0
        top_emojis = emojis.get("top_emojis", [])
        slang_pct = formality.get("slang_frequency_per_100w", 0)

        rules: List[str] = []
        rules.append(f"- Средняя длина предложений: около {avg_sent:.1f} слов. Формулируйте мысли соразмерно.")

        if no_dot:
            rules.append("- В конце последнего предложения сообщения НЕ ставьте точку (характерно для автора).")
        else:
            rules.append("- Завершайте финальные предложения нормативной пунктуацией.")

        if punct.get("total_bracket_smiles", 0) > (n * 0.3):
            rules.append("- Для выражения дружелюбия/иронии используйте закрывающую скобку ')' вместо классических эмодзи.")

        if top_emojis:
            rules.append(f"- Характерные эмодзи (использовать умеренно): {' '.join(top_emojis[:4])}")

        if slang_pct > 1.5:
            rules.append("- Тон неформальный, допустимы общепринятые сокращения (спс, плз, нормик, мб).")
        else:
            rules.append("- Тон нейтрально-деловой, без нарочитого интернет-сленга.")

        prompt = (
            "### Руководство по стилю автора \n\n"
            "При составлении сообщений от лица владельца соблюдайте следующие принципы:\n"
            + "\n".join(rules)
            + "\n\n(Сформировано автоматически на базе анализа "
            + str(n)
            + " верифицированных сообщений автора)"
        )
        return prompt
