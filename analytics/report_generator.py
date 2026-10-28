from __future__ import annotations

from typing import Any, Dict, List

from analytics.confidence import ConfidenceEvaluator


def make_progress_bar(current: int, total: int, length: int = 10) -> str:
    if total <= 0:
        return "░" * length
    pct = min(1.0, max(0.0, current / total))
    filled = round(pct * length)
    return "█" * filled + "░" * (length - filled)


class ReportGenerator:

    DIVIDER = "━━━━━━━━━━━━━━━━━━━━━━"

    @classmethod
    def generate_profile_report(cls, profile: Dict[str, Any], user_label: str = "Участник") -> str:
        sample_count = profile.get("sample_count", 0)
        confidence = ConfidenceEvaluator.evaluate(sample_count, profile)

        if not confidence.is_statistically_valid:
            bar = make_progress_bar(sample_count, ConfidenceEvaluator.MIN_THRESHOLD)
            pct = int((sample_count / ConfidenceEvaluator.MIN_THRESHOLD) * 100)
            lines = [
                f"📊 <b>Аналитический профиль стиля:</b> {user_label}",
                cls.DIVIDER,
                "⏳ <b>Статус накопления базы:</b>",
                f"<code>[{bar}] {sample_count} / {ConfidenceEvaluator.MIN_THRESHOLD} сообщ. ({pct}%)</code>\n",
                f"ℹ️ <i>Для формирования портрета речи необходимо собрать минимум {ConfidenceEvaluator.MIN_THRESHOLD} сообщений в подключенных чатах.</i>",
                cls.DIVIDER,
                "💡 <i>Отправляйте сообщения в чаты, где присутствует бот — профиль рассчитается автоматически.</i>",
            ]
            return "\n".join(lines)

        total_words = profile.get("total_words", 0)
        total_chars = profile.get("total_characters", 0)
        avg_sent = profile.get("avg_sentence_len", 0.0)
        lex_rich = profile.get("lexical_richness", 0.0)

        # Confidence badge
        if confidence.level == "HIGH":
            conf_badge = "🟢 <b>Высокая точность</b>"
        elif confidence.level == "MODERATE":
            conf_badge = "🟡 <b>Умеренная точность</b>"
        else:
            conf_badge = "⚪ <b>Предварительный срез</b>"

        punct = profile.get("punctuation_stats", {})
        no_dot_pct = punct.get("no_trailing_dot_pct", 0.0)
        brackets = punct.get("total_bracket_smiles", 0)
        exclamations = punct.get("total_exclamations", 0)
        questions = punct.get("total_questions", 0)

        emojis = profile.get("emoji_stats", {})
        top_emojis: List[str] = emojis.get("top_emojis", [])
        total_emojis = emojis.get("total_emojis", 0)
        emojis_per_msg = total_emojis / max(1, sample_count)

        formality = profile.get("formality_markers", {})
        polite_cnt = formality.get("polite_markers", 0)
        polite_freq = formality.get("polite_frequency_per_100w", 0.0)
        slang_cnt = formality.get("slang_markers", 0)
        slang_freq = formality.get("slang_frequency_per_100w", 0.0)
        caps_cnt = formality.get("all_caps_words", 0)

        lines: List[str] = [
            f"📊 <b>Аналитический профиль стиля:</b> {user_label}",
            cls.DIVIDER,
            f"📈 <b>Объём выборки:</b> <code>{sample_count} сообщ.</code> • <code>{total_words} слов</code> (<code>{total_chars} знаков</code>)",
            f"🎯 <b>Надёжность данных:</b> {conf_badge}",
            cls.DIVIDER,
            "📏 <b>Параметры текста:</b>",
            f"• Средняя длина реплики: <b>{avg_sent:.1f}</b> сл/сообщ.",
            f"• Лексический багаж (TTR): <b>{lex_rich:.3f}</b>\n",
            "✏️ <b>Пунктуационные маркеры:</b>",
            f"• Пропуск точки в конце: <b>{no_dot_pct:.0f}%</b>",
            f"• Скобки-смайлики <code>)</code>: <b>{brackets} шт.</b>",
            f"• Вопросительные конструкции: <b>{questions}</b>",
            f"• Восклицательные конструкции: <b>{exclamations}</b>\n",
            "😊 <b>Эмодзи и графика:</b>",
            f"• Плотность: <b>{emojis_per_msg:.1f}</b> на сообщ. (всего: <code>{total_emojis}</code>)",
        ]

        if top_emojis:
            lines.append(f"• Топ смайлов: {' '.join(top_emojis[:8])}")

        lines.extend([
            "\n🤝 <b>Тональность и лексика:</b>",
            f"• Вежливость: <b>{polite_cnt}</b> <i>({polite_freq:.1f} на 100 сл.)</i>",
            f"• Сленг и сокращения: <b>{slang_cnt}</b> <i>({slang_freq:.1f} на 100 сл.)</i>",
            f"• ВЕРХНИЙ РЕГИСТР (капс): <b>{caps_cnt} слов</b>",
        ])

        activity = profile.get("activity_hours", {})
        if activity:
            sorted_hours = sorted(activity.items(), key=lambda x: int(x[0]))
            peak_hour, peak_val = max(activity.items(), key=lambda x: x[1])
            lines.extend([
                cls.DIVIDER,
                f"⏰ <b>Пик активности:</b> <code>{peak_hour}:00 - {int(peak_hour)+1}:00 UTC</code> <i>({peak_val} сообщ.)</i>",
            ])

        return "\n".join(lines)
