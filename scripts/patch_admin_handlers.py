import re

admin_path = r"c:\Users\sla_5\Programing\Projects\Tg Saver\bot\handlers\admin.py"
with open(admin_path, "r", encoding="utf-8") as f:
    content = f.read()

# 1. Update imports
old_import = "    llm_settings_kb,\n    llm_temp_select_kb,"
new_import = "    daily_memory_kb,\n    llm_settings_kb,\n    llm_temp_select_kb,"
assert old_import in content, "old_import not found"
content = content.replace(old_import, new_import)

# 2. Update cmd_admin_panel
old_admin_panel = """    async with db.connect() as conn:
        user_repo = UserRepository(conn)
        route_repo = RouteRepository(conn)
        chat_repo = ChatRepository(conn)

        users_cnt = len(await user_repo.list_users(limit=500))
        routes_cnt = len(await route_repo.list_routes())
        hidden_routes_cnt = len(await route_repo.list_routes(hidden_only=True))
        chats_cnt = len(await chat_repo.list_all())
        pw_req = await user_repo.is_password_required(settings.PASSWORD_REQUIRED)

    pw_status = "🟢 Включен" if pw_req else "⚪ Отключен"
    div = "━━━━━━━━━━━━━━━━━━━━━━"

    if is_subadmin:
        text = (
            f"🛡️ <b>Панель Младшего Администратора</b>\\n{div}\\n"
            f"• 👥 <b>Пользователей в системе:</b> <code>{users_cnt}</code>\\n"
            f"• 🔀 <b>Доступных маршрутов:</b> <code>{routes_cnt}</code>\\n"
            f"• 📡 <b>Подключенных чатов:</b> <code>{chats_cnt}</code>\\n{div}\\n"
            "👇 <i>Вам доступно управление чатами, модерацией, ИИ и аналитикой:</i>"
        )
    else:
        text = (
            f"👑 <b>Панель Администратора</b>\\n{div}\\n"
            f"• 👥 <b>Пользователей в системе:</b> <code>{users_cnt}</code>\\n"
            f"• 🔀 <b>Всего маршрутов:</b> <code>{routes_cnt}</code> <i>(все авторы)</i>\\n"
            f"• 📡 <b>Подключенных чатов:</b> <code>{chats_cnt}</code>\\n"
            f"• 🔑 <b>Пароль доступа:</b> {pw_status}\\n{div}\\n"
            "👇 <i>Выберите нужный раздел для управления:</i>"
        )"""

new_admin_panel = """    async with db.connect() as conn:
        user_repo = UserRepository(conn)
        route_repo = RouteRepository(conn)
        chat_repo = ChatRepository(conn)
        config_repo = ConfigRepository(conn)

        users_cnt = len(await user_repo.list_users(limit=500))
        routes_cnt = len(await route_repo.list_routes())
        hidden_routes_cnt = len(await route_repo.list_routes(hidden_only=True))
        chats_cnt = len(await chat_repo.list_all())
        pw_req = await user_repo.is_password_required(settings.PASSWORD_REQUIRED)

        llm_conf = await config_repo.get_llm_config(
            default_enabled=settings.LLM_ENABLED,
            default_model=settings.LLM_MODEL,
        )
        stt_conf = await config_repo.get_stt_config(
            default_enabled=settings.STT_ENABLED,
        )
        today_str = datetime.now().strftime("%Y-%m-%d")
        today_mem = await chat_repo.get_daily_memory(-1002255156347, today_str)

    pw_status = "🟢 Включен" if pw_req else "⚪ Отключен"
    llm_status_str = "🟢 Включен" if llm_conf["llm_enabled"] else "⚪ Выключен"
    stt_status_str = "🟢 Включено" if stt_conf["stt_enabled"] else "⚪ Выключено"
    mem_status_str = "🟢 Зафиксирована" if today_mem else "⚪ Ожидает диалогов"
    div = "━━━━━━━━━━━━━━━━━━━━━━"

    if is_subadmin:
        text = (
            f"🛡️ <b>Панель Младшего Администратора</b>\\n{div}\\n"
            f"• 👥 <b>Пользователей в системе:</b> <code>{users_cnt}</code>\\n"
            f"• 🔀 <b>Доступных маршрутов:</b> <code>{routes_cnt}</code>\\n"
            f"• 📡 <b>Подключенных чатов:</b> <code>{chats_cnt}</code>\\n"
            f"• 🤖 <b>ИИ Ричард:</b> {llm_status_str}\\n"
            f"• 🎙️ <b>Распознавание речи:</b> {stt_status_str}\\n{div}\\n"
            "👇 <i>Вам доступно управление чатами, модерацией, ИИ и аналитикой:</i>"
        )
    else:
        text = (
            f"👑 <b>Панель Администратора</b>\\n{div}\\n"
            f"• 👥 <b>Пользователей в системе:</b> <code>{users_cnt}</code>\\n"
            f"• 🔀 <b>Всего маршрутов:</b> <code>{routes_cnt}</code> <i>(все авторы)</i>\\n"
            f"• 📡 <b>Подключенных чатов:</b> <code>{chats_cnt}</code>\\n"
            f"• 🔑 <b>Пароль доступа:</b> {pw_status}\\n"
            f"• 🤖 <b>ИИ-собеседник (Ричард):</b> {llm_status_str} <code>({llm_conf['llm_model']})</code>\\n"
            f"• 🎙️ <b>Распознавание речи:</b> {stt_status_str}\\n"
            f"• 📜 <b>Дневная память:</b> {mem_status_str}\\n{div}\\n"
            "👇 <i>Выберите нужный раздел для управления:</i>"
        )"""

assert old_admin_panel in content, "old_admin_panel not found"
content = content.replace(old_admin_panel, new_admin_panel)

# 3. Update _render_llm_settings
old_render_llm = """    lines = top_lines + [
        "⚙️ <b>Параметры генерации и памяти:</b>",
        f"• 📚 <b>Контекст чата:</b> <code>{ctx}</code> недавних сообщ.",
        f"• 📝 <b>Длина ответа:</b> <code>{toks}</code> токенов",
        f"• 🌡️ <b>Креативность:</b> <code>{temp}</code>",
        f"• 🎭 <b>Характер / Личность:</b> <b>{persona_str}</b>",
        f"• 🎯 <b>Триггер в группе:</b> {trigger_str}",
        f"• ⌨️ <b>Статус «Печатает...»:</b> {typing_str}",
        f"• 🎲 <b>Случайные реплики:</b> {rand_str}",
        div,
        "💡 <i>Поддерживаются OpenAI, Google Gemini, DeepSeek и локальные LLM (vLLM / Ollama).</i>",
    ]"""

new_render_llm = """    today_str = datetime.now().strftime("%Y-%m-%d")
    today_mem = await ChatRepository(conn).get_daily_memory(-1002255156347, today_str)
    mem_status = "🟢 Зафиксирована" if today_mem else "⚪ Ожидает диалогов"

    lines = top_lines + [
        "⚙️ <b>Параметры генерации и памяти:</b>",
        f"• 📚 <b>Контекст чата:</b> <code>{ctx}</code> недавних сообщ.",
        f"• 📝 <b>Длина ответа:</b> <code>{toks}</code> токенов",
        f"• 🌡️ <b>Креативность:</b> <code>{temp}</code>",
        f"• 🎭 <b>Характер / Личность:</b> <b>{persona_str}</b>",
        f"• 🎯 <b>Триггер в группе:</b> {trigger_str}",
        f"• ⌨️ <b>Статус «Печатает...»:</b> {typing_str}",
        f"• 🎲 <b>Случайные реплики:</b> {rand_str}",
        f"• 📜 <b>Дневная память:</b> {mem_status}",
        div,
        "💡 <i>Поддерживаются OpenAI, Google Gemini, DeepSeek и локальные LLM (vLLM / Ollama).</i>",
    ]"""

assert old_render_llm in content, "old_render_llm not found"
content = content.replace(old_render_llm, new_render_llm)

# 4. Update cb_llm_clear_all_mem to also wipe chat_daily_memories
old_clear_mem = """    async with db.connect() as conn:
        await ChatRepository(conn).clear_all_companion_history()
    if companion:
        companion.context_buffer._buffers.clear()
    await callback.answer("Вся память диалогов Ричарда во всех чатах очищена!", show_alert=True)"""

new_clear_mem = """    async with db.connect() as conn:
        await ChatRepository(conn).clear_all_companion_history()
        await conn.execute("DELETE FROM chat_daily_memories")
    if companion:
        companion.context_buffer._buffers.clear()
    await callback.answer("Вся память диалогов и дневная хроника Ричарда во всех чатах очищена!", show_alert=True)"""

assert old_clear_mem in content, "old_clear_mem not found"
content = content.replace(old_clear_mem, new_clear_mem)

# 5. Add admin_daily_memory callbacks
daily_mem_handlers = """

@router.callback_query(F.data == "admin_daily_memory")
async def cb_admin_daily_memory(
    callback: CallbackQuery,
    db: Database,
    is_admin: bool = False,
) -> None:
    if not is_admin:
        await callback.answer("⚠️ Доступ только для администраторов.", show_alert=True)
        return

    today_str = datetime.now().strftime("%Y-%m-%d")
    target_cid = -1002255156347
    div = "━━━━━━━━━━━━━━━━━━━━━━"

    async with db.connect() as conn:
        repo = ChatRepository(conn)
        mem = await repo.get_daily_memory(target_cid, today_str)
        chat_row = await conn.execute("SELECT title FROM chats WHERE chat_id = ?", (target_cid,))
        c_data = await chat_row.fetchone()
        c_title = c_data["title"] if c_data else "TiraMMMiSu"

    if not mem or not (mem.get("summary") or mem.get("key_facts")):
        text = (
            f"📜 <b>Управление дневной памятью и сводками</b>\\n{div}\\n"
            f"• 📅 <b>Дата:</b> <code>{today_str}</code>\\n"
            f"• 📡 <b>Основной чат:</b> <b>{html.escape(c_title)}</b> (<code>{target_cid}</code>)\\n"
            f"• 🧠 <b>Статус:</b> ⚪ <i>Сводка на сегодня ещё не сформирована</i>\\n{div}\\n"
            "💡 <i>Нажмите кнопку ниже, чтобы ИИ проанализировал последние сообщения чата и составил свежую сводку дня.</i>"
        )
        has_mem = False
    else:
        facts_list = mem.get("key_facts") or []
        facts_text = "\\n".join(f"  • {html.escape(f)}" for f in facts_list[:6]) if facts_list else "  <i>(нет ключевых фактов)</i>"
        text = (
            f"📜 <b>Управление дневной памятью и сводками</b>\\n{div}\\n"
            f"• 📅 <b>Дата:</b> <code>{today_str}</code>\\n"
            f"• 📡 <b>Основной чат:</b> <b>{html.escape(c_title)}</b> (<code>{target_cid}</code>)\\n"
            f"• 🧠 <b>Статус:</b> 🟢 <b>Сводка зафиксирована</b>\\n{div}\\n"
            f"📝 <b>Хроника событий за сегодня:</b>\\n{html.escape(mem.get('summary', ''))}\\n\\n"
            f"📌 <b>Ключевые факты и рофлы дня:</b>\\n{facts_text}\\n{div}\\n"
            "💡 <i>Эта хроника используется Ричардом для контекстных ответов, осаживания оппонентов и выдачи сводки админу.</i>"
        )
        has_mem = True

    await callback.message.edit_text(text, reply_markup=daily_memory_kb(has_memory=has_mem), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "daily_mem_regenerate")
async def cb_daily_mem_regenerate(
    callback: CallbackQuery,
    db: Database,
    companion: Optional[ChatCompanion] = None,
    is_admin: bool = False,
) -> None:
    if not is_admin:
        await callback.answer("⚠️ Доступ только для администраторов.", show_alert=True)
        return

    await callback.answer("⏳ Анализирую диалоги и формирую сводку дня...", show_alert=False)
    today_str = datetime.now().strftime("%Y-%m-%d")
    target_cid = -1002255156347

    messages_list = []
    async with db.connect() as conn:
        cursor = await conn.execute(
            "SELECT user_name, text, created_at, is_bot FROM companion_chat_history WHERE chat_id = ? ORDER BY id DESC LIMIT 40",
            (target_cid,)
        )
        rows = await cursor.fetchall()
        for r in reversed(rows):
            sender = "Ричард (Бот)" if r["is_bot"] else (r["user_name"] or "Участник")
            messages_list.append(f"[{sender}]: {r['text']}")

    if not messages_list:
        await callback.answer("⚠️ В базе данных пока нет сообщений для этого чата.", show_alert=True)
        return

    if not companion or not companion.llm_client:
        await callback.answer("⚠️ ИИ-клиент не подключен.", show_alert=True)
        return

    raw_logs = "\\n".join(messages_list)
    prompt = (
        "Составь структурированную дневную память чата для ИИ-собеседника на русском языке в формате JSON.\\n"
        "КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО выдумывать еду, десерты или вымышленные факты! Говори строго по логам.\\n"
        "Формат ответа:\\n"
        "{\\n"
        '  "summary": "Краткое изложение главных событий дня (2-3 предложения)",\\n'
        '  "key_facts": ["факт 1", "факт 2", "факт 3"]\\n'
        "}\\n\\n"
        f"Лог сообщений чата:\\n{raw_logs}"
    )
    try:
        raw_res = await companion.llm_client.chat_completion(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.5,
            max_tokens=600,
        )
        clean_json = raw_res.strip()
        if clean_json.startswith("```"):
            clean_json = re.sub(r"^```(?:json)?\\n?", "", clean_json)
            clean_json = re.sub(r"\\n?```$", "", clean_json)
        parsed = json.loads(clean_json)
        sum_text = parsed.get("summary", "")
        facts = parsed.get("key_facts", [])

        async with db.connect() as conn:
            await ChatRepository(conn).upsert_daily_memory(
                chat_id=target_cid,
                date_str=today_str,
                summary=sum_text,
                key_facts=facts,
            )
        await callback.answer("✅ Сводка дня успешно пересобрана нейросетью!", show_alert=True)
    except Exception as ex:
        logger.exception("Error regenerating daily memory: %s", ex)
        await callback.answer(f"❌ Ошибка генерации: {ex}", show_alert=True)

    await cb_admin_daily_memory(callback, db=db, is_admin=is_admin)


@router.callback_query(F.data == "daily_mem_clear")
async def cb_daily_mem_clear(
    callback: CallbackQuery,
    db: Database,
    is_admin: bool = False,
) -> None:
    if not is_admin:
        await callback.answer("⚠️ Доступ только для администраторов.", show_alert=True)
        return

    today_str = datetime.now().strftime("%Y-%m-%d")
    target_cid = -1002255156347
    async with db.connect() as conn:
        await conn.execute("DELETE FROM chat_daily_memories WHERE chat_id = ? AND date_str = ?", (target_cid, today_str))

    await callback.answer("🗑️ Дневная память за сегодня очищена!", show_alert=True)
    await cb_admin_daily_memory(callback, db=db, is_admin=is_admin)
"""

content += daily_mem_handlers

with open(admin_path, "w", encoding="utf-8") as f:
    f.write(content)

print("admin.py patched successfully")
