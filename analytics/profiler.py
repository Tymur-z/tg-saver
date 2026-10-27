from __future__ import annotations

import logging
from collections import Counter
from datetime import datetime
from typing import Any, Dict, Optional

from database.connection import Database
from database.repositories.profile_repo import ProfileRepository
from analytics.extractor import FeatureExtractor, MessageFeatures

logger = logging.getLogger(__name__)


class StyleProfiler:

    def __init__(self, db: Database) -> None:
        self.db = db

    async def process_message(
        self,
        user_id: int,
        chat_id: int,
        text: str,
        created_at: datetime,
        is_reply: bool = False,
        is_owner: bool = False,
    ) -> bool:
        if not text or not text.strip():
            return False

        async with self.db.connect() as conn:
            repo = ProfileRepository(conn)

            if await repo.is_excluded("user", user_id):
                logger.debug("User %s is excluded from analytics. Skipping.", user_id)
                return False
            if await repo.is_excluded("chat", chat_id):
                logger.debug("Chat %s is excluded from analytics. Skipping.", chat_id)
                return False

            features = FeatureExtractor.extract(text=text, created_at=created_at, is_reply=is_reply)

            await self._merge_and_save(repo, user_id, chat_id, features, is_owner)
            if chat_id != 0:
                await self._merge_and_save(repo, user_id, 0, features, is_owner)

            return True

    async def _merge_and_save(
        self,
        repo: ProfileRepository,
        user_id: int,
        chat_id: int,
        feat: MessageFeatures,
        is_owner: bool,
    ) -> None:
        existing = await repo.get_profile(user_id, chat_id)
        if not existing:
            sample_count = 1
            total_words = feat.word_count
            total_chars = feat.char_count
            avg_sentence_len = feat.avg_sentence_len
            lexical_richness = feat.lexical_richness

            punct_stats = {
                "total_exclamations": feat.exclamation_count,
                "total_questions": feat.question_count,
                "total_commas": feat.comma_count,
                "total_bracket_smiles": feat.bracket_smiles_count,
                "no_trailing_dot_count": 0 if feat.has_trailing_dot else 1,
                "no_trailing_dot_pct": 0.0 if feat.has_trailing_dot else 100.0,
            }

            emoji_counts: Counter[str] = Counter(feat.emojis)
            emoji_stats = {
                "total_emojis": feat.emoji_count,
                "top_emojis": [em for em, _ in emoji_counts.most_common(10)],
                "emoji_histogram": dict(emoji_counts.most_common(20)),
            }

            formality_markers = {
                "formal_greetings": feat.formal_greetings_count,
                "informal_greetings": feat.informal_greetings_count,
                "polite_markers": feat.polite_markers_count,
                "slang_markers": feat.slang_markers_count,
                "all_caps_words": feat.all_caps_words_count,
                "slang_frequency_per_100w": round((feat.slang_markers_count / max(1, feat.word_count)) * 100, 2),
                "polite_frequency_per_100w": round((feat.polite_markers_count / max(1, feat.word_count)) * 100, 2),
            }

            activity_hours = {str(feat.created_hour): 1}

        else:
            old_n = existing.get("sample_count", 0)
            sample_count = old_n + 1
            total_words = existing.get("total_words", 0) + feat.word_count
            total_chars = existing.get("total_characters", 0) + feat.char_count

            old_avg_sent = existing.get("avg_sentence_len", 0.0)
            avg_sentence_len = round(old_avg_sent + (feat.avg_sentence_len - old_avg_sent) / sample_count, 2)

            old_ttr = existing.get("lexical_richness", 0.0)
            lexical_richness = round(old_ttr + (feat.lexical_richness - old_ttr) / sample_count, 4)

            punct_stats = existing.get("punctuation_stats", {})
            punct_stats["total_exclamations"] = punct_stats.get("total_exclamations", 0) + feat.exclamation_count
            punct_stats["total_questions"] = punct_stats.get("total_questions", 0) + feat.question_count
            punct_stats["total_commas"] = punct_stats.get("total_commas", 0) + feat.comma_count
            punct_stats["total_bracket_smiles"] = (
                punct_stats.get("total_bracket_smiles", 0) + feat.bracket_smiles_count
            )
            if not feat.has_trailing_dot:
                punct_stats["no_trailing_dot_count"] = punct_stats.get("no_trailing_dot_count", 0) + 1
            punct_stats["no_trailing_dot_pct"] = round(
                (punct_stats.get("no_trailing_dot_count", 0) / sample_count) * 100.0, 1
            )

            emoji_stats = existing.get("emoji_stats", {})
            emoji_stats["total_emojis"] = emoji_stats.get("total_emojis", 0) + feat.emoji_count
            hist: Dict[str, int] = emoji_stats.get("emoji_histogram", {})
            for em in feat.emojis:
                hist[em] = hist.get(em, 0) + 1
            sorted_emojis = sorted(hist.items(), key=lambda x: x[1], reverse=True)
            emoji_stats["top_emojis"] = [em for em, _ in sorted_emojis[:10]]
            emoji_stats["emoji_histogram"] = dict(sorted_emojis[:20])

            formality_markers = existing.get("formality_markers", {})
            formality_markers["formal_greetings"] = (
                formality_markers.get("formal_greetings", 0) + feat.formal_greetings_count
            )
            formality_markers["informal_greetings"] = (
                formality_markers.get("informal_greetings", 0) + feat.informal_greetings_count
            )
            formality_markers["polite_markers"] = (
                formality_markers.get("polite_markers", 0) + feat.polite_markers_count
            )
            formality_markers["slang_markers"] = formality_markers.get("slang_markers", 0) + feat.slang_markers_count
            formality_markers["all_caps_words"] = (
                formality_markers.get("all_caps_words", 0) + feat.all_caps_words_count
            )

            tw = max(1, total_words)
            formality_markers["slang_frequency_per_100w"] = round(
                (formality_markers["slang_markers"] / tw) * 100, 2
            )
            formality_markers["polite_frequency_per_100w"] = round(
                (formality_markers["polite_markers"] / tw) * 100, 2
            )

            activity_hours = existing.get("activity_hours", {})
            h_key = str(feat.created_hour)
            activity_hours[h_key] = activity_hours.get(h_key, 0) + 1

        await repo.upsert_profile(
            user_id=user_id,
            chat_id=chat_id,
            is_owner=is_owner,
            sample_count=sample_count,
            total_words=total_words,
            total_characters=total_chars,
            avg_sentence_len=avg_sentence_len,
            lexical_richness=lexical_richness,
            punctuation_stats=punct_stats,
            emoji_stats=emoji_stats,
            formality_markers=formality_markers,
            activity_hours=activity_hours,
        )
