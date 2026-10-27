from analytics.comparator import StyleComparator


def test_style_comparator_match():
    baseline = {
        "sample_count": 50,
        "avg_sentence_len": 5.0,
        "punctuation_stats": {
            "no_trailing_dot_pct": 80.0,
            "total_bracket_smiles": 25,
        },
        "formality_markers": {
            "slang_frequency_per_100w": 1.0,
            "polite_frequency_per_100w": 0.5,
        },
        "emoji_stats": {
            "top_emojis": ["👍", "🔥"],
            "total_emojis": 10,
        },
    }

    text = "Привет все отлично сделаем скоро)"
    res = StyleComparator.compare(text, baseline)

    assert res["similarity_score"] >= 80.0
    assert len(res["observations"]) >= 1


def test_style_comparator_mimicry_prompt():
    baseline = {
        "sample_count": 100,
        "avg_sentence_len": 4.5,
        "punctuation_stats": {
            "no_trailing_dot_pct": 90.0,
            "total_bracket_smiles": 40,
        },
        "formality_markers": {
            "slang_frequency_per_100w": 2.0,
            "polite_frequency_per_100w": 0.2,
        },
        "emoji_stats": {
            "top_emojis": ["🤝", "⚡"],
            "total_emojis": 15,
        },
    }

    prompt = StyleComparator.generate_mimicry_prompt(baseline)
    assert "НЕ ставьте точку" in prompt
    assert "4.5 слов" in prompt
    assert "🤝" in prompt
