from __future__ import annotations

from typing import Any, Dict, List

from analytics.confidence import ConfidenceEvaluator


class ReportGenerator:

    @classmethod
    def generate_profile_report(cls, profile: Dict[str, Any], user_label: str = "Участник") -> str:
        sample_count = profile.get("sample_count", 0)
        confidence = ConfidenceEvaluator.evaluate(sample_count, profile)

        lines: List[str] = [
            f"📊 <b>Аналитический профиль стиля: {user_label}</b>",
            f"<i>{confidence.label_ru}</i>\n",
        ]

        if not confidence.is_statistically_valid:
            lines.append(f"ℹ️ Для построения надёжного профиля необходимо собрать минимум {ConfidenceEvaluator.MIN_THRESHOLD} сообщений.")
            lines.append(f"Текущее число сообщений в выборке: <b>{sample_count}</b>.")
            lines.append("\n" + confidence.ethical_disclaimer)
            return "\n".join(lines)

        total_words = profile.get("total_words", 0)
        total_chars = profile.get("total_characters", 0)
        avg_sent = profile.get("avg_sentence_len", 0.0)
        lex_rich = profile.get("lexical_richness", 0.0)

        lines.append("📏 <b>Количественные показатели:</b>")
        lines.append(f"• Сообщений в базе: <code>{sample_count}</code>")
        lines.append(f"• Всего слов: <code>{total_words}</code> (символов: <code>{total_chars}</code>)")
        lines.append(f"• Средняя длина реплики: <code>{avg_sent:.1f}</code> слов/предл.")
        lines.append(f"• Лексическое разнообразие (TTR): <code>{lex_rich:.3f}</code>\n")

        punct = profile.get("punctuation_stats", {})
        no_dot_pct = punct.get("no_trailing_dot_pct", 0.0)
        brackets = punct.get("total_bracket_smiles", 0)
        exclamations = punct.get("total_exclamations", 0)
        questions = punct.get("total_questions", 0)

        lines.append("✏️ <b>Пунктуационные маркеры:</b>")
        lines.append(f"• Опущение финальной точки: <code>{no_dot_pct:.1f}%</code>")
        lines.append(f"• Использование скобок-смайлов ')': <code>{brackets}</code>")
        lines.append(f"• Вопросительные конструкции: <code>{questions}</code>")
        lines.append(f"• Восклицательные конструкции: <code>{exclamations}</code>\n")

        emojis = profile.get("emoji_stats", {})
        top_emojis: List[str] = emojis.get("top_emojis", [])
        total_emojis = emojis.get("total_emojis", 0)
        lines.append("😊 <b>Графика и эмодзи:</b>")
        lines.append(f"• Всего эмодзи: <code>{total_emojis}</code> (в среднем {total_emojis / max(1, sample_count):.2f} на сообщ.)")
        if top_emojis:
            lines.append(f"• Любимые эмодзи: {' '.join(top_emojis[:8])}")
        lines.append("")

        formality = profile.get("formality_markers", {})
        lines.append("🤝 <b>Тональность и лексика:</b>")
        lines.append(f"• Маркеры вежливости: <code>{formality.get('polite_markers', 0)}</code> ({formality.get('polite_frequency_per_100w', 0):.1f} на 100 слов)")
        lines.append(f"• Сленг и сокращения: <code>{formality.get('slang_markers', 0)}</code> ({formality.get('slang_frequency_per_100w', 0):.1f} на 100 слов)")
        lines.append(f"• Слова ВЕРХНИМ РЕГИСТРОМ: <code>{formality.get('all_caps_words', 0)}</code>\n")

        activity = profile.get("activity_hours", {})
        if activity:
            sorted_hours = sorted(activity.items(), key=lambda x: int(x[0]))
            peak_hour, peak_val = max(activity.items(), key=lambda x: x[1])
            lines.append("⏰ <b>Активность по времени суток (UTC):</b>")
            lines.append(f"• Пиковый интервал: <code>{peak_hour}:00 - {int(peak_hour)+1}:00</code> ({peak_val} сообщений)")
            chart_blocks = []
            for h, count in sorted_hours:
                chart_blocks.append(f"{h.zfill(2)}h: {count}")
            lines.append("• " + " | ".join(chart_blocks[:6]))
            lines.append("")

        if confidence.hypotheses:
            lines.append("💡 <b>Наблюдаемые паттерны:</b>")
            for hyp in confidence.hypotheses:
                lines.append(f"• {hyp}")
            lines.append("")

        if confidence.alternative_explanations:
            lines.append("🔍 <b>Возможные альтернативные факторы:</b>")
            for alt in confidence.alternative_explanations:
                lines.append(f"• <i>{alt}</i>")
            lines.append("")

        lines.append(confidence.ethical_disclaimer)
        return "\n".join(lines)
