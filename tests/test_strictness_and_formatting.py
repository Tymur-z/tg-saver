# -*- coding: utf-8 -*-
import pytest
from moderation.profanity import ProfanityDetector
from moderation.companion import format_companion_html

@pytest.mark.asyncio
async def test_profanity_strictness_levels():
    detector = ProfanityDetector(llm_enabled=False)

    # 1. Hard profanity must trigger in both "hard" and "all"
    hard_words = [
        "Вот сука такая",
        "Ну ты и пидор",
        "Гандон штопаный",
        "с.у.к.а",
        "п и д о р",
        "cуkа",   # Latin homoglyphs
        "п1дор",   # Leetspeak
        "г@ндон",  # Symbols
        "сууукааа",# Character repetitions
    ]
    for w in hard_words:
        res_hard = await detector.check_text(w, strictness="hard")
        assert res_hard.is_profane is True, f"Hard check failed for: {w}"

        res_all = await detector.check_text(w, strictness="all")
        assert res_all.is_profane is True, f"All check failed for: {w}"

    # 2. Mild profanity (тупой, блин, дурак, дебил)
    mild_words = [
        "Ну ты и тупой",
        "Да блин вообще",
        "Какой же он дурак",
        "т.у.п.о.й",
        "тупооой",
    ]
    for w in mild_words:
        # In "hard" mode, mild words should NOT trigger
        res_hard = await detector.check_text(w, strictness="hard")
        assert res_hard.is_profane is False, f"Mild word triggered in hard mode: {w}"

        # In "all" mode, mild words MUST trigger
        res_all = await detector.check_text(w, strictness="all")
        assert res_all.is_profane is True, f"Mild word failed to trigger in all mode: {w}"

def test_companion_markdown_to_html_formatting():
    raw_markdown = """Ого, запрос на 1000 слов!
### Основные понятия термодинамики:

1. **Системы и окружение**: Термодинамика изучает системы.
2. *Первый закон*: Энергия сохраняется.
`inline_code_test`
```python
x = 10 < 20
```"""

    formatted = format_companion_html(raw_markdown)

    # Must NOT have raw markdown headers
    assert "###" not in formatted
    assert "<b>Основные понятия термодинамики:</b>" in formatted

    # Must NOT have raw asterisks
    assert "**Системы" not in formatted
    assert "<b>Системы и окружение</b>" in formatted
    assert "<i>Первый закон</i>" in formatted

    # Must preserve code tags properly
    assert "<code>inline_code_test</code>" in formatted
    assert "<pre><code>x = 10 &lt; 20</code></pre>" in formatted