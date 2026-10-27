from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Set

WORD_PATTERN = re.compile(r"\b[a-zA-Zа-яА-ЯёЁ0-9_-]+\b", re.UNICODE)
SENTENCE_SPLIT_PATTERN = re.compile(r"[.!?]+(?:\s+|$)", re.UNICODE)

FORMAL_GREETINGS = {"здравствуйте", "добрый день", "доброе утро", "добрый вечер", "приветствую", "уважаемый"}
INFORMAL_GREETINGS = {"привет", "хай", "хеллоу", "ку", "здорово", "йо", "салют", "даров"}
POLITENESS_MARKERS = {"пожалуйста", "спасибо", "благодарю", "будьте добры", "прошу", "извините", "простите"}
SLANG_MARKERS = {"хз", "спс", "плз", "лол", "имхо", "мб", "кста", "норм", "пон", "жиза", "рофл", "че", "чо", "ща", "оч"}

EMOJI_PATTERN = re.compile(
    "["
    "\U0001F600-\U0001F64F"
    "\U0001F300-\U0001F5FF"
    "\U0001F680-\U0001F6FF"
    "\U0001F700-\U0001F77F"
    "\U0001F780-\U0001F7FF"
    "\U0001F800-\U0001F8FF"
    "\U0001F900-\U0001F9FF"
    "\U0001FA00-\U0001FA6F"
    "\U0001FA70-\U0001FAFF"
    "\U00002702-\U000027B0"
    "\U000024C2-\U0001F251"
    "]+",
    flags=re.UNICODE,
)


@dataclass
class MessageFeatures:

    char_count: int
    word_count: int
    sentence_count: int
    avg_sentence_len: float
    lexical_richness: float
    unique_words: Set[str] = field(default_factory=set)

    has_trailing_dot: bool = False
    has_trailing_ellipsis: bool = False
    exclamation_count: int = 0
    question_count: int = 0
    comma_count: int = 0
    bracket_smiles_count: int = 0

    emoji_count: int = 0
    emojis: List[str] = field(default_factory=list)
    all_caps_words_count: int = 0

    formal_greetings_count: int = 0
    informal_greetings_count: int = 0
    polite_markers_count: int = 0
    slang_markers_count: int = 0

    is_reply: bool = False
    has_links: bool = False
    created_hour: int = 12
    created_weekday: int = 0


class FeatureExtractor:

    @classmethod
    def extract(
        cls,
        text: str,
        created_at: datetime,
        is_reply: bool = False,
    ) -> MessageFeatures:
        text = text.strip() if text else ""
        char_count = len(text)

        if not text:
            return MessageFeatures(
                char_count=0,
                word_count=0,
                sentence_count=0,
                avg_sentence_len=0.0,
                lexical_richness=0.0,
                created_hour=created_at.hour,
                created_weekday=created_at.weekday(),
                is_reply=is_reply,
            )

        raw_words = WORD_PATTERN.findall(text)
        word_count = len(raw_words)
        lower_words = [w.lower() for w in raw_words]
        unique_words = set(lower_words)
        ttr = (len(unique_words) / word_count) if word_count > 0 else 0.0

        raw_sentences = [s.strip() for s in SENTENCE_SPLIT_PATTERN.split(text) if s.strip()]
        sentence_count = max(1, len(raw_sentences))
        avg_sentence_len = round(word_count / sentence_count, 2) if sentence_count > 0 else 0.0

        has_trailing_dot = text.endswith(".") and not text.endswith("..")
        has_trailing_ellipsis = text.endswith("...") or text.endswith("..")
        exclamation_count = text.count("!")
        question_count = text.count("?")
        comma_count = text.count(",")

        bracket_smiles = len(re.findall(r"\)+|\(+", text))

        found_emojis: List[str] = []
        for match in EMOJI_PATTERN.finditer(text):
            found_emojis.extend(list(match.group()))
        emoji_count = len(found_emojis)

        all_caps_words = [w for w in raw_words if len(w) > 1 and w.isupper() and not w.isdigit()]
        all_caps_count = len(all_caps_words)

        formal_cnt = sum(1 for w in lower_words if w in FORMAL_GREETINGS)
        informal_cnt = sum(1 for w in lower_words if w in INFORMAL_GREETINGS)
        polite_cnt = sum(1 for w in lower_words if w in POLITENESS_MARKERS)
        slang_cnt = sum(1 for w in lower_words if w in SLANG_MARKERS)

        has_links = bool(re.search(r"https?://\S+", text, re.IGNORECASE))

        return MessageFeatures(
            char_count=char_count,
            word_count=word_count,
            sentence_count=sentence_count,
            avg_sentence_len=avg_sentence_len,
            lexical_richness=round(ttr, 4),
            unique_words=unique_words,
            has_trailing_dot=has_trailing_dot,
            has_trailing_ellipsis=has_trailing_ellipsis,
            exclamation_count=exclamation_count,
            question_count=question_count,
            comma_count=comma_count,
            bracket_smiles_count=bracket_smiles,
            emoji_count=emoji_count,
            emojis=found_emojis,
            all_caps_words_count=all_caps_count,
            formal_greetings_count=formal_cnt,
            informal_greetings_count=informal_cnt,
            polite_markers_count=polite_cnt,
            slang_markers_count=slang_cnt,
            is_reply=is_reply,
            has_links=has_links,
            created_hour=created_at.hour,
            created_weekday=created_at.weekday(),
        )
