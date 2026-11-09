import pytest
from unittest.mock import AsyncMock, MagicMock
from moderation.companion import ChatCompanion, PERSONA_PRESETS, COMMON_CHAT_RULES
from bot.keyboards.inline import llm_persona_select_kb, llm_settings_kb
from bot.handlers.admin import cb_llm_set_persona, cb_llm_select_persona
from database.connection import Database
from database.schema import init_db
from database.repositories.config_repo import ConfigRepository
from config import Settings


EXPECTED_PRESETS = [
    "student",
    "expert",
    "sarcastic",
    "concise",
    "gamer",
    "tech",
    "chill",
    "toxic",
]


def test_all_expected_presets_exist():
    for p in EXPECTED_PRESETS:
        assert p in PERSONA_PRESETS, f"Preset {p} is missing from PERSONA_PRESETS"
        text = PERSONA_PRESETS[p]
        assert len(text) > 50, f"Preset {p} description is too short"
        assert "Ты — Ричард" in text, f"Preset {p} must identify as Richard"


def test_persona_prompts_contain_chat_rules():
    for p in EXPECTED_PRESETS:
        companion = ChatCompanion(persona=p)
        prompt = companion.get_effective_system_prompt(is_owner=False)
        # Check persona text is in prompt
        assert PERSONA_PRESETS[p] in prompt
        # Check common chat rules are in prompt
        assert "ПРАВИЛО ПАФОСА И МЕСТИ" in prompt or "ПАСХАЛКИ" in prompt

        # Check creator protection when is_owner=True
        owner_prompt = companion.get_effective_system_prompt(is_owner=True)
        assert "Тимур" in owner_prompt
        assert "@Tymur2000" in owner_prompt
        assert "СТРОЖАЙШЕ ЗАПРЕЩЕН ВЫПЕНДРЕЖ" in owner_prompt


def test_persona_switching_in_companion():
    companion = ChatCompanion(persona="student")
    assert "студенческую жизнь" in companion.get_effective_system_prompt()

    companion.update_config(persona="gamer")
    assert companion.persona == "gamer"
    gamer_prompt = companion.get_effective_system_prompt()
    assert "CS2" in gamer_prompt
    assert "SnowRunner" in gamer_prompt

    companion.update_config(persona="tech")
    assert companion.persona == "tech"
    tech_prompt = companion.get_effective_system_prompt()
    assert "химии" in tech_prompt
    assert "CO2" in tech_prompt

    companion.update_config(persona="chill")
    assert companion.persona == "chill"
    chill_prompt = companion.get_effective_system_prompt()
    assert "дзена" in chill_prompt

    companion.update_config(persona="toxic")
    assert companion.persona == "toxic"
    toxic_prompt = companion.get_effective_system_prompt()
    assert "Roast Mode" in toxic_prompt


def test_persona_select_keyboard_active_marker():
    # Test default/student
    kb_student = llm_persona_select_kb(current_persona="student")
    all_buttons = [btn for row in kb_student.inline_keyboard for btn in row]
    
    student_btn = next((b for b in all_buttons if b.callback_data == "llm_set_persona:student"), None)
    assert student_btn is not None
    assert "✅" in student_btn.text

    expert_btn = next((b for b in all_buttons if b.callback_data == "llm_set_persona:expert"), None)
    assert expert_btn is not None
    assert "✅" not in expert_btn.text

    # Test gamer active
    kb_gamer = llm_persona_select_kb(current_persona="gamer")
    all_buttons_gamer = [btn for row in kb_gamer.inline_keyboard for btn in row]
    gamer_btn = next((b for b in all_buttons_gamer if b.callback_data == "llm_set_persona:gamer"), None)
    assert gamer_btn is not None
    assert "✅" in gamer_btn.text
    student_btn2 = next((b for b in all_buttons_gamer if b.callback_data == "llm_set_persona:student"), None)
    assert "✅" not in student_btn2.text

    # Test custom active
    kb_custom = llm_persona_select_kb(current_persona="custom")
    all_buttons_custom = [btn for row in kb_custom.inline_keyboard for btn in row]
    custom_btn = next((b for b in all_buttons_custom if b.callback_data == "llm_custom_persona"), None)
    assert custom_btn is not None
    assert "✅" in custom_btn.text


def test_llm_settings_kb_shows_all_persona_names():
    for p in EXPECTED_PRESETS:
        kb = llm_settings_kb(is_enabled=True, conf={"companion_persona": p})
        all_buttons = [btn for row in kb.inline_keyboard for btn in row]
        persona_btn = next((b for b in all_buttons if b.callback_data == "llm_select_persona"), None)
        assert persona_btn is not None
        assert "🎭 Персона:" in persona_btn.text
        # Ensure it didn't fall back to "🎓 Студент" when testing another persona
        if p == "gamer":
            assert "🎮 Геймер" in persona_btn.text
        elif p == "tech":
            assert "🧠 Технарь" in persona_btn.text
        elif p == "chill":
            assert "☕ Чилл" in persona_btn.text
        elif p == "toxic":
            assert "🐺 Токсик" in persona_btn.text


@pytest.mark.asyncio
async def test_cb_llm_set_persona(tmp_path):
    db_path = tmp_path / "test_persona.db"
    db = Database(str(db_path))
    async with db.connect() as conn:
        await init_db(conn)

    settings = Settings(BOT_TOKEN="123:ABC", OWNER_ID=123)
    companion = ChatCompanion(persona="student")

    callback = MagicMock()
    callback.data = "llm_set_persona:gamer"
    callback.answer = AsyncMock()
    callback.message = MagicMock()
    callback.message.edit_text = AsyncMock()

    await cb_llm_set_persona(
        callback=callback,
        db=db,
        settings=settings,
        companion=companion,
        is_admin=True,
    )

    # 1. Companion persona updated
    assert companion.persona == "gamer"

    # 2. Database config updated
    async with db.connect() as conn:
        conf = await ConfigRepository(conn).get_llm_config()
    assert conf["companion_persona"] == "gamer"

    # 3. Callback answered with label
    callback.answer.assert_called_once()
    assert "Геймер" in callback.answer.call_args[0][0]

    # 4. Message updated with LLM settings
    callback.message.edit_text.assert_called_once()
    rendered_text = callback.message.edit_text.call_args[0][0]
    assert "Геймер" in rendered_text
