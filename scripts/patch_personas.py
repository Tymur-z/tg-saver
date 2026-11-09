import sys
import re

def patch_companion():
    path = r"C:\Users\sla_5\Programing\Projects\Tg Saver\moderation\companion.py"
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    new_presets = '''PERSONA_PRESETS: Dict[str, str] = {
    "student": (
        "Ты — Ричард, остроумный, сообразительный и живой парень в Telegram-чате друзей.\\n"
        "Ты прекрасно понимаешь студенческую жизнь, сессии, пары, завалы, дедлайны, мемы, игры и чатовый движ.\\n"
        "Главные принципы:\\n"
        "- Разговаривай как настоящий бро и реальный участник чата, а не как сухой робот или шаблонный бот.\\n"
        "- Отвечай живо, хлёстко, по существу (1-3 фразы), с хорошим чувством юмора и самоиронией.\\n"
        "- Общайся на равных, без душноты и канцеляризмов. Не спамь фразой 'на парах' в неподходящих темах.\\n"
        "- Если над тобой прикалываются — отвечай метко, с характером, сохраняя дружескую атмосферу."
    ),
    "expert": (
        "Ты — Ричард, рассудительный, тактичный и высокоинтеллектуальный собеседник.\\n"
        "Твой стиль — деловой, взвешенный и конструктивный, но сохраняющий естественность и ясность.\\n"
        "Главные принципы:\\n"
        "- Излагай мысли четко, логично и последовательно, опираясь на факты и здравый смысл.\\n"
        "- Воздерживайся от дворового сленга, дешевых подколок и фамильярности.\\n"
        "- Формулируй ответы ёмко (1-3 предложения), структурированно и вежливо, уважая время собеседника.\\n"
        "- При спорах аргументируй спокойно и весомо, не вступая в эмоциональные перепалки."
    ),
    "sarcastic": (
        "Ты — Ричард, дерзкий, харизматичный парень с острым как бритва языком, черным юмором и отменным вкусом к тонкому сарказму.\\n"
        "Главные принципы:\\n"
        "- Меткие, хлесткие панчи и остроумные подколы. Никаких нудных оправданий и шаблонных фраз.\\n"
        "- Держи высокую планку: сарказм должен быть умным, неожиданным и бьющим точно в цель.\\n"
        "- Не обижайся на наезды — моментально обращай их против оппонента, красиво осаживая его.\\n"
        "- Ответы короткие (1-2, максимум 3 предложения), с искрой и характером."
    ),
    "concise": (
        "Ты — Ричард, ультра-лаконичный и точный собеседник. Твоё главное правило — экономия слов при максимальной смысловой плотности.\\n"
        "Главные принципы:\\n"
        "- Отвечай строго 1-2 предложениями, ни одного лишнего слова или пустой вводной конструкции.\\n"
        "- Никакой воды, приветствий через силу и пространных рассуждений — сразу к сути вопроса.\\n"
        "- Формулируй хлёстко, уверенно и по факту."
    ),
    "gamer": (
        "Ты — Ричард, заядлый геймер и завсегдатай голосовых каналов Discord и соревновательных катков.\\n"
        "Ты отлично понимаешь игровой сленг, CS2, Faceit (эло, тильт, клатчи, раскидки), SnowRunner (замесы в грязи), скидки в Steam и новинки индустрии.\\n"
        "Главные принципы:\\n"
        "- Общайся на естественном геймерском языке без натужности и кринжа.\\n"
        "- Подкалывай за слитые клатчи, застрявшие в болоте грузовики и вечный тильт, но по-братски.\\n"
        "- Отвечай энергично, кратко (1-3 фразы) и с соревновательным задором."
    ),
    "tech": (
        "Ты — Ричард, подкованный технарь и эрудит с инженерно-научным складом ума.\\n"
        "Ты свободно ориентируешься в химии (газы, кислоты, реакции), физике, коде (Python, Linux, базы данных, серверы, железо) и точных науках.\\n"
        "Главные принципы:\\n"
        "- Разговаривай грамотно, научно обоснованно и логично, но без занудства — понятным живым языком.\\n"
        "- С глубоким уважением относись к реальным научным и техническим фактам. Отличай газы (CO2 от сероводорода H2S), архитектуру кода, протоколы.\\n"
        "- Отвечай ёмко (1-3 предложения), доказательно и по сути, с легкой иронией над псевдонаучной чушью."
    ),
    "chill": (
        "Ты — Ричард, воплощение абсолютного дзена, спокойствия и душевного чилла.\\n"
        "Тебя невозможно вывести из себя, забайтить или разозлить. Ты смотришь на любую суету с высоты философского пофигизма.\\n"
        "Главные принципы:\\n"
        "- Общайся легко, расслабленно, с доброй иронией ('да не парься', 'жизнь коротка, чтобы суетиться').\\n"
        "- Гаси любые споры и токсичность невозмутимым спокойствием и добродушным юмором.\\n"
        "- Отвечай коротко (1-2 фразы), тепло и вайбово, без суеты и давления."
    ),
    "toxic": (
        "Ты — Ричард в режиме максимальной прожарки (Roast Mode) и бескомпромиссного токсика для чатовых зазнаек.\\n"
        "Главные принципы:\\n"
        "- Безжалостно высмеивай глупость, понты, школьные ловушки и пустые наезды оппонентов.\\n"
        "- Бей жестко, иронично, прямо по больному и по реальным косякам участников (ушки кошкодевочки, сливы, глупые вопросы).\\n"
        "- Никаких соплей: твой ответ должен заставлять весь чат угарать над твоей мишенью.\\n"
        "- Отвечай хлёстко (1-2 фразы), уверенно и с ощущением полного морального превосходства.\\n"
        "- ВАЖНОЕ ИСКЛЮЧЕНИЕ: Это правило никогда не применяется к Тимуру (создателю) — к нему всегда уважение и братский тон."
    ),
}'''

    pattern = r"PERSONA_PRESETS:\s*Dict\[str,\s*str\]\s*=\s*\{.*?\n\}"
    match = re.search(pattern, content, flags=re.DOTALL)
    if not match:
        raise ValueError("Could not find PERSONA_PRESETS in companion.py")
    
    new_content = content[:match.start()] + new_presets + content[match.end():]
    with open(path, "w", encoding="utf-8") as f:
        f.write(new_content)
    print("Patched companion.py successfully")


def patch_inline_keyboards():
    path = r"C:\Users\sla_5\Programing\Projects\Tg Saver\bot\keyboards\inline.py"
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    # 1. Update p_labels in llm_settings_kb
    old_labels_pattern = r"p_labels\s*=\s*\{[^}]+\}"
    new_labels = '''p_labels = {
        "student": "🎓 Студент",
        "expert": "💼 Эксперт",
        "sarcastic": "😈 Дерзкий",
        "concise": "⚡ Краткий",
        "gamer": "🎮 Геймер",
        "tech": "🧠 Технарь",
        "chill": "☕ Чилл",
        "toxic": "🐺 Токсик",
        "custom": "✍️ Свой",
    }'''
    match = re.search(old_labels_pattern, content)
    if not match:
        raise ValueError("Could not find p_labels in inline.py")
    content = content[:match.start()] + new_labels + content[match.end():]

    # 2. Update llm_persona_select_kb
    old_kb_pattern = r"def llm_persona_select_kb\(\)[^:]*:.*?\n(?=def )"
    new_kb = '''def llm_persona_select_kb(current_persona: str = "student") -> InlineKeyboardMarkup:
    presets = [
        ("student", "🎓 Студент"),
        ("expert", "💼 Деловой"),
        ("sarcastic", "😈 Дерзкий"),
        ("concise", "⚡ Краткий"),
        ("gamer", "🎮 Геймер"),
        ("tech", "🧠 Технарь"),
        ("chill", "☕ Чилл"),
        ("toxic", "🐺 Токсик"),
    ]
    rows: List[List[InlineKeyboardButton]] = []
    for i in range(0, len(presets), 2):
        row = []
        for code, label in presets[i : i + 2]:
            mark = "✅ " if current_persona == code else ""
            row.append(InlineKeyboardButton(text=f"{mark}{label}", callback_data=f"llm_set_persona:{code}"))
        rows.append(row)

    custom_mark = "✅ " if current_persona == "custom" else ""
    rows.append([InlineKeyboardButton(text=f"{custom_mark}✍️ Задать свой системный промпт", callback_data="llm_custom_persona")])
    rows.append([InlineKeyboardButton(text="⬅️ Назад в меню ИИ", callback_data="admin_llm_settings")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


'''
    match_kb = re.search(old_kb_pattern, content, flags=re.DOTALL)
    if not match_kb:
        raise ValueError("Could not find llm_persona_select_kb in inline.py")
    content = content[:match_kb.start()] + new_kb + content[match_kb.end():]

    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print("Patched inline.py successfully")


def patch_admin_handlers():
    path = r"C:\Users\sla_5\Programing\Projects\Tg Saver\bot\handlers\admin.py"
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    # 1. Update persona_map in _render_llm_settings
    old_persona_map_pattern = r"persona_map\s*=\s*\{[^}]+\}"
    new_persona_map = '''persona_map = {
        "student": "🎓 Студент / Свой пацан",
        "expert": "💼 Деловой эксперт",
        "sarcastic": "😈 Дерзкий / Остроумный",
        "concise": "⚡ Краткий / По делу",
        "gamer": "🎮 Геймер / CS2 & Катки",
        "tech": "🧠 Технарь / Интеллектуал",
        "chill": "☕ Чилл / Пофигист",
        "toxic": "🐺 Токсик / Прожарка",
        "custom": "✍️ Свой системный промпт",
    }'''
    match = re.search(old_persona_map_pattern, content)
    if not match:
        raise ValueError("Could not find persona_map in admin.py")
    content = content[:match.start()] + new_persona_map + content[match.end():]

    # 2. Update cb_llm_select_persona and cb_llm_set_persona
    old_handlers_pattern = r"@router\.callback_query\(F\.data == \"llm_select_persona\"\).*?@router\.callback_query\(F\.data == \"llm_custom_persona\"\)"
    new_handlers = '''@router.callback_query(F.data == "llm_select_persona")
async def cb_llm_select_persona(callback: CallbackQuery, db: Database, is_admin: bool = False) -> None:
    if not is_admin:
        await callback.answer("⚠️ Доступ только для администраторов.", show_alert=True)
        return
    async with db.connect() as conn:
        config_repo = ConfigRepository(conn)
        conf = await config_repo.get_llm_config()
    current_persona = conf.get("companion_persona", "student")

    persona_map = {
        "student": "🎓 Студент / Свой пацан",
        "expert": "💼 Деловой эксперт",
        "sarcastic": "😈 Дерзкий / Остроумный",
        "concise": "⚡ Краткий / По делу",
        "gamer": "🎮 Геймер / CS2 & Катки",
        "tech": "🧠 Технарь / Интеллектуал",
        "chill": "☕ Чилл / Пофигист",
        "toxic": "🐺 Токсик / Прожарка",
        "custom": "✍️ Свой системный промпт",
    }
    current_label = persona_map.get(current_persona, current_persona)

    text = (
        "🎭 <b>Выбор характера и личности Ричарда:</b>\\n\\n"
        "• 🎓 <b>Студент / Свой пацан</b> — живой участник чата, остроумный, на равных, шарит за мемы, учебу и движ\\n"
        "• 💼 <b>Деловой эксперт</b> — вежливый, структурный, без уличного сленга, аргументы по фактам\\n"
        "• 😈 <b>Дерзкий / Остроумный</b> — тонкая ирония, хлёсткий сарказм, черноватый юмор и подколы\\n"
        "• ⚡ <b>Краткий / По делу</b> — строго 1-2 предложения, максимум сути без лишней воды\\n"
        "• 🎮 <b>Геймер / CS2 & Катки</b> — CS2, Faceit (эло, тильт, клатчи), SnowRunner, Steam и гейминг\\n"
        "• 🧠 <b>Технарь / Интеллектуал</b> — химия (газы/кислоты), физика, код (Python/Linux), серверы и логика\\n"
        "• ☕ <b>Чилл / Пофигист</b> — невозмутимый дзен, гасит конфликты спокойствием, легкий вайб\\n"
        "• 🐺 <b>Токсик / Прожарка</b> — режим жесткого роаста троллей, бьет по косякам с максимальным сарказмом\\n"
        "• ✍️ <b>Свой системный промпт</b> — задайте любую свою инструкцию для нейросети\\n\\n"
        f"Текущий режим: <b>{current_label}</b>\\n"
        "Выберите характер:"
    )
    await callback.message.edit_text(text, reply_markup=llm_persona_select_kb(current_persona=current_persona), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("llm_set_persona:"))
async def cb_llm_set_persona(
    callback: CallbackQuery,
    db: Database,
    settings: Settings,
    companion: Optional[ChatCompanion] = None,
    is_admin: bool = False,
) -> None:
    if not is_admin:
        await callback.answer("⚠️ Доступ только для администраторов.", show_alert=True)
        return
    persona_code = callback.data.split(":", 1)[1]
    from moderation.companion import PERSONA_PRESETS
    if persona_code not in PERSONA_PRESETS and persona_code != "custom":
        await callback.answer("⚠️ Неизвестный характер.", show_alert=True)
        return
    async with db.connect() as conn:
        config_repo = ConfigRepository(conn)
        await config_repo.set_llm_config(persona=persona_code)
        text, is_on, conf = await _render_llm_settings(conn, settings)
    if companion:
        companion.update_config(persona=persona_code)

    persona_map = {
        "student": "🎓 Студент / Свой пацан",
        "expert": "💼 Деловой эксперт",
        "sarcastic": "😈 Дерзкий / Остроумный",
        "concise": "⚡ Краткий / По делу",
        "gamer": "🎮 Геймер / CS2 & Катки",
        "tech": "🧠 Технарь / Интеллектуал",
        "chill": "☕ Чилл / Пофигист",
        "toxic": "🐺 Токсик / Прожарка",
        "custom": "✍️ Свой системный промпт",
    }
    p_label = persona_map.get(persona_code, persona_code)
    await callback.message.edit_text(text, reply_markup=llm_settings_kb(is_on, conf), parse_mode="HTML")
    await callback.answer(f"✅ Характер: {p_label}")


@router.callback_query(F.data == "llm_custom_persona")'''

    match_handlers = re.search(old_handlers_pattern, content, flags=re.DOTALL)
    if not match_handlers:
        raise ValueError("Could not find persona callbacks in admin.py")
    content = content[:match_handlers.start()] + new_handlers + content[match_handlers.end():]

    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print("Patched admin.py successfully")


if __name__ == "__main__":
    patch_companion()
    patch_inline_keyboards()
    patch_admin_handlers()
