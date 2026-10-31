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

@pytest.mark.asyncio
async def test_profanity_whitelist():
    detector = ProfanityDetector(llm_enabled=False)

    # Word that would normally be flagged as hard profanity
    text = "Вот сука такая"
    res1 = await detector.check_text(text, strictness="hard")
    assert res1.is_profane is True

    # With whitelist containing "сука", it should NOT be flagged
    res2 = await detector.check_text(text, strictness="hard", whitelist_words=["сука"])
    assert res2.is_profane is False


@pytest.mark.asyncio
async def test_chat_repo_extensions(tmp_path):
    import aiosqlite
    from database.schema import init_db
    from database.repositories.chat_repo import ChatRepository

    db_file = tmp_path / "test_repo.db"
    async with aiosqlite.connect(str(db_file)) as conn:
        conn.row_factory = aiosqlite.Row
        await init_db(conn)
        repo = ChatRepository(conn)

        await repo.ensure_chat_exists(100, "Test Chat", "group")

        # Test delete warn seconds cycling
        assert await repo.cycle_delete_warn_seconds(100) == 15
        assert await repo.cycle_delete_warn_seconds(100) == 30
        assert await repo.cycle_delete_warn_seconds(100) == 60
        assert await repo.cycle_delete_warn_seconds(100) == 0

        # Test auto mute cycling
        assert await repo.cycle_auto_mute(100) == 600
        assert await repo.cycle_auto_mute(100) == 3600
        assert await repo.cycle_auto_mute(100) == 86400
        assert await repo.cycle_auto_mute(100) == 0

        # Test companion persistent history
        await repo.add_companion_message(100, 1, "Alice", "Hello Richard", is_bot=False)
        await repo.add_companion_message(100, 0, "Ричард", "Hi Alice!", is_bot=True)
        hist = await repo.get_companion_history(100, limit=10)
        assert len(hist) == 2
        assert hist[0]["text"] == "Hello Richard"
        assert hist[1]["text"] == "Hi Alice!"

        # Test clear companion history
        deleted = await repo.clear_companion_history(100)
        assert deleted == 2
        hist_empty = await repo.get_companion_history(100, limit=10)
        assert len(hist_empty) == 0

        # Test violations recording & counting
        await repo.record_violation(100, 555, "Hard profanity", "hard")
        await repo.record_violation(100, 555, "Hard profanity again", "hard")
        cnt = await repo.count_recent_violations(100, 555, hours=24)
        assert cnt == 2


def test_companion_personas():
    from moderation.companion import ChatCompanion, PERSONA_PRESETS

    companion = ChatCompanion(persona="sarcastic")
    prompt = companion.get_effective_system_prompt(is_owner=False)
    assert "сарказм" in prompt.lower()

    # Owner awareness
    prompt_owner = companion.get_effective_system_prompt(is_owner=True)
    assert "Тимур" in prompt_owner
