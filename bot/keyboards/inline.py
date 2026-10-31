from __future__ import annotations

from typing import Any, Dict, List
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

MEDIA_TYPE_LABELS = {
    "text": "📝 Текст",
    "photo": "🖼️ Фото",
    "video": "🎬 Видео",
    "video_note": "⭕ Кружочки",
    "voice": "🎤 Голосовые",
    "document": "📁 Файлы",
    "audio": "🎵 Музыка",
    "sticker": "🎭 Стикеры",
    "animation": "🎞️ GIF",
}


def main_menu_kb(is_admin: bool = False, is_subadmin: bool = False) -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton(text="🔀 Мои маршруты", callback_data="nav_routes"),
            InlineKeyboardButton(text="➕ Создать маршрут", callback_data="route_create"),
        ],
        [
            InlineKeyboardButton(text="📡 Источники", callback_data="nav_sources"),
            InlineKeyboardButton(text="🎯 Назначения", callback_data="nav_destinations"),
        ],
        [
            InlineKeyboardButton(text="📊 Мой стиль", callback_data="nav_analytics"),
            InlineKeyboardButton(text="🔒 Приватность", callback_data="nav_privacy"),
        ],
    ]

    if is_admin:
        admin_label = "🛡️ Админ-Панель (Модерация)" if is_subadmin else "👑 Админ-Панель (Управление)"
        buttons.append([
            InlineKeyboardButton(text=admin_label, callback_data="nav_admin"),
        ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def admin_panel_kb(is_subadmin: bool = False) -> InlineKeyboardMarkup:
    if is_subadmin:
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="👥 Пользователи (Аккаунты)", callback_data="admin_users"),
                    InlineKeyboardButton(text="🌐 Все маршруты системы", callback_data="admin_all_routes"),
                ],
                [
                    InlineKeyboardButton(text="📡 Все чаты бота", callback_data="admin_all_chats"),
                    InlineKeyboardButton(text="🛡️ Модерация и чаты", callback_data="admin_moderation_chats"),
                ],
                [
                    InlineKeyboardButton(text="🤖 Настройки ИИ (LLM)", callback_data="admin_llm_settings"),
                    InlineKeyboardButton(text="📊 Стили участников", callback_data="admin_all_profiles"),
                ],
                [
                    InlineKeyboardButton(text="⚙️ Статус и пауза", callback_data="nav_status"),
                    InlineKeyboardButton(text="⬅️ В главное меню", callback_data="nav_main"),
                ],
            ]
        )

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="👥 Пользователи (Аккаунты)", callback_data="admin_users"),
                InlineKeyboardButton(text="🌐 Все маршруты системы", callback_data="admin_all_routes"),
            ],
            [
                InlineKeyboardButton(text="📡 Все чаты бота", callback_data="admin_all_chats"),
                InlineKeyboardButton(text="🛡️ Модерация и чаты", callback_data="admin_moderation_chats"),
            ],
            [
                InlineKeyboardButton(text="🤖 Настройки ИИ (LLM)", callback_data="admin_llm_settings"),
                InlineKeyboardButton(text="🔑 Пароль доступа", callback_data="admin_password"),
            ],
            [
                InlineKeyboardButton(text="📊 Стили участников", callback_data="admin_all_profiles"),
                InlineKeyboardButton(text="⚙️ Статус и пауза", callback_data="nav_status"),
            ],
            [
                InlineKeyboardButton(text="⬅️ В главное меню", callback_data="nav_main"),
            ],
        ]
    )


def users_list_kb(users: List[Dict[str, Any]]) -> InlineKeyboardMarkup:
    buttons: List[List[InlineKeyboardButton]] = []
    for u in users:
        role = u.get("role", "user")
        if role == "owner":
            role_icon = "👑"
        elif role == "admin":
            role_icon = "⭐"
        elif role == "subadmin":
            role_icon = "🛡️"
        else:
            role_icon = "👤"

        status_icon = "🚫" if u.get("is_blocked") else ("🟢" if u.get("is_authorized") else "🔒")
        name = u.get("first_name") or f"ID {u['user_id']}"
        routes_cnt = u.get("routes_count", 0)
        btn_text = f"{status_icon} {role_icon} {name[:14]} ({routes_cnt} маршр.)"
        buttons.append([InlineKeyboardButton(text=btn_text, callback_data=f"user_view:{u['user_id']}")])

    buttons.append([
        InlineKeyboardButton(text="🔄 Обновить список", callback_data="admin_users"),
        InlineKeyboardButton(text="⬅️ В админ-панель", callback_data="nav_admin"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def user_card_kb(
    target_user: Dict[str, Any],
    is_owner: bool = False,
    is_self: bool = False,
    is_subadmin: bool = False,
) -> InlineKeyboardMarkup:
    uid = target_user["user_id"]
    is_blocked = bool(target_user.get("is_blocked"))
    role = target_user.get("role", "user")

    buttons: List[List[InlineKeyboardButton]] = []

    # Owner or self cannot be blocked or reset
    if is_owner or is_self or role == "owner":
        buttons.append([InlineKeyboardButton(text="👑 Главный владелец (Защищён)", callback_data="noop")])
    elif is_subadmin:
        # Subadmin cannot block admins or change roles
        if role in ("admin", "subadmin"):
            buttons.append([InlineKeyboardButton(text="🛡️ Администрация системы (Защищён)", callback_data="noop")])
        else:
            if is_blocked:
                buttons.append([InlineKeyboardButton(text="✅ Разблокировать пользователя", callback_data=f"user_unblock:{uid}")])
            else:
                buttons.append([InlineKeyboardButton(text="🚫 Заблокировать аккаунт", callback_data=f"user_block:{uid}")])
    else:
        # Full admin / owner:
        if is_blocked:
            buttons.append([InlineKeyboardButton(text="✅ Разблокировать пользователя", callback_data=f"user_unblock:{uid}")])
        else:
            buttons.append([InlineKeyboardButton(text="🚫 Заблокировать аккаунт", callback_data=f"user_block:{uid}")])

        if role == "user":
            buttons.append([
                InlineKeyboardButton(text="🛡️ Сделать младшим админом", callback_data=f"user_role:{uid}:subadmin"),
                InlineKeyboardButton(text="👑 Сделать администратором", callback_data=f"user_role:{uid}:admin"),
            ])
        elif role == "subadmin":
            buttons.append([
                InlineKeyboardButton(text="👑 Повысить до администратора", callback_data=f"user_role:{uid}:admin"),
                InlineKeyboardButton(text="👤 Понизить до пользователя", callback_data=f"user_role:{uid}:user"),
            ])
        elif role == "admin":
            buttons.append([
                InlineKeyboardButton(text="🛡️ Перевести в младшие админы", callback_data=f"user_role:{uid}:subadmin"),
                InlineKeyboardButton(text="👤 Снять права администратора", callback_data=f"user_role:{uid}:user"),
            ])

        buttons.append([
            InlineKeyboardButton(text="🔑 Сбросить авторизацию (потребует пароль)", callback_data=f"user_reset_auth:{uid}")
        ])

    buttons.append([
        InlineKeyboardButton(text="📊 Анализ стиля пользователя", callback_data=f"view_profile:{uid}"),
    ])
    buttons.append([
        InlineKeyboardButton(text="⬅️ Назад к пользователям", callback_data="admin_users"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def password_management_kb(password_required: bool) -> InlineKeyboardMarkup:
    req_icon = "🟢 Включена (требуется пароль)" if password_required else "⚪ Отключена (вход свободный)"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✏️ Изменить пароль доступа", callback_data="admin_change_pw")],
            [InlineKeyboardButton(text=f"🔒 Защита: {req_icon}", callback_data="admin_toggle_pw_req")],
            [InlineKeyboardButton(text="⬅️ В админ-панель", callback_data="nav_admin")],
        ]
    )


def all_routes_kb(routes: List[Dict[str, Any]]) -> InlineKeyboardMarkup:
    buttons: List[List[InlineKeyboardButton]] = []
    for r in routes:
        status_icon = "🟢" if r.get("is_active") else "⏸️"
        mode_icon = "↗️" if r.get("mode") == "forward" else "📋"
        creator = r.get("creator_username") or r.get("creator_name") or f"ID {r.get('created_by_user_id', 0)}"
        title = f"{status_icon} {mode_icon} #{r['id']} {r['name'][:16]} [{creator[:10]}]"
        buttons.append([InlineKeyboardButton(text=title, callback_data=f"route_view:{r['id']}")])

    buttons.append([
        InlineKeyboardButton(text="➕ Создать маршрут", callback_data="route_create"),
        InlineKeyboardButton(text="🔄 Обновить", callback_data="admin_all_routes"),
    ])
    buttons.append([InlineKeyboardButton(text="⬅️ В админ-панель", callback_data="nav_admin")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def routes_list_kb(routes: List[Dict[str, Any]]) -> InlineKeyboardMarkup:
    buttons: List[List[InlineKeyboardButton]] = []
    for r in routes:
        status_icon = "🟢" if r.get("is_active") else "⏸️"
        mode_icon = "↗️" if r.get("mode") == "forward" else "📋"
        title = f"{status_icon} {mode_icon} #{r['id']} {r['name'][:22]}"
        buttons.append([InlineKeyboardButton(text=title, callback_data=f"route_view:{r['id']}")])

    buttons.append([
        InlineKeyboardButton(text="➕ Создать маршрут", callback_data="route_create"),
        InlineKeyboardButton(text="🔄 Обновить", callback_data="nav_routes"),
    ])
    buttons.append([InlineKeyboardButton(text="⬅️ Главное меню", callback_data="nav_main")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def route_detail_kb(route: Dict[str, Any], is_admin: bool = False) -> InlineKeyboardMarkup:
    route_id = route["id"]
    is_active = bool(route.get("is_active"))
    mode = route.get("mode", "forward")

    toggle_status_text = "⏸️ Пауза" if is_active else "▶️ Включить"
    mode_btn_text = "📋 Режим: Copy" if mode == "copy" else "↗️ Режим: Forward"

    selected_types = route.get("filter_media_types", [])
    types_count = len(selected_types) if selected_types else len(MEDIA_TYPE_LABELS)

    buttons: List[List[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(text=toggle_status_text, callback_data=f"route_toggle:{route_id}"),
            InlineKeyboardButton(text=mode_btn_text, callback_data=f"route_mode_toggle:{route_id}"),
        ],
        [
            InlineKeyboardButton(
                text=f"🎯 Типы контента ({types_count}/{len(MEDIA_TYPE_LABELS)})",
                callback_data=f"route_media_menu:{route_id}",
            ),
        ],
        [
            InlineKeyboardButton(text="🔤 Ключевые слова", callback_data=f"route_kw_menu:{route_id}"),
            InlineKeyboardButton(text="🚫 Стоп-слова", callback_data=f"route_ex_menu:{route_id}"),
        ],
    ]

    if mode == "copy":
        clean_links_icon = "🟢" if route.get("clean_links") else "⚪"
        clean_tags_icon = "🟢" if route.get("clean_tags") else "⚪"
        clean_mentions_icon = "🟢" if route.get("clean_mentions") else "⚪"
        source_link_icon = "🟢" if route.get("append_source_link") else "⚪"

        buttons.append([
            InlineKeyboardButton(
                text=f"🧹 Удалять ссылки: {clean_links_icon}",
                callback_data=f"route_toggle_field:{route_id}:clean_links",
            ),
            InlineKeyboardButton(
                text=f"🏷️ Хештеги: {clean_tags_icon}",
                callback_data=f"route_toggle_field:{route_id}:clean_tags",
            ),
        ])
        buttons.append([
            InlineKeyboardButton(
                text=f"👤 @Упоминания: {clean_mentions_icon}",
                callback_data=f"route_toggle_field:{route_id}:clean_mentions",
            ),
            InlineKeyboardButton(
                text=f"📌 Ссылка источника: {source_link_icon}",
                callback_data=f"route_toggle_field:{route_id}:append_source_link",
            ),
        ])

    buttons.append([
        InlineKeyboardButton(text="🗑️ Удалить маршрут", callback_data=f"route_delete:{route_id}"),
    ])
    back_target = "nav_routes"
    buttons.append([
        InlineKeyboardButton(text="⬅️ Назад к маршрутам", callback_data=back_target),
    ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def media_types_selection_kb(route_id: int, selected_types: List[str]) -> InlineKeyboardMarkup:
    buttons: List[List[InlineKeyboardButton]] = []
    is_all_active_by_default = len(selected_types) == 0

    row: List[InlineKeyboardButton] = []
    for mtype, label in MEDIA_TYPE_LABELS.items():
        is_enabled = is_all_active_by_default or (mtype in selected_types)
        icon = "✅" if is_enabled else "❌"
        btn_text = f"{icon} {label}"
        row.append(InlineKeyboardButton(text=btn_text, callback_data=f"mtype_toggle:{route_id}:{mtype}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    buttons.append([
        InlineKeyboardButton(text="Включить все", callback_data=f"mtype_all:{route_id}:1"),
        InlineKeyboardButton(text="Снять все", callback_data=f"mtype_all:{route_id}:0"),
    ])
    buttons.append([
        InlineKeyboardButton(text="💾 Сохранить и вернуться", callback_data=f"route_view:{route_id}"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def keywords_menu_kb(route_id: int, is_exclude: bool = False) -> InlineKeyboardMarkup:
    prefix = "ex" if is_exclude else "inc"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ Добавить слово", callback_data=f"kw_add:{prefix}:{route_id}")],
            [InlineKeyboardButton(text="🗑️ Очистить список", callback_data=f"kw_clear:{prefix}:{route_id}")],
            [InlineKeyboardButton(text="⬅️ Назад к маршруту", callback_data=f"route_view:{route_id}")],
        ]
    )


def select_chat_kb(chats: List[Dict[str, Any]], action_prefix: str) -> InlineKeyboardMarkup:
    buttons: List[List[InlineKeyboardButton]] = []
    for c in chats[:8]:
        title = c.get("title") or f"Chat {c['chat_id']}"
        buttons.append([
            InlineKeyboardButton(text=f"👉 {title[:28]}", callback_data=f"{action_prefix}:{c['chat_id']}"),
        ])
    buttons.append([InlineKeyboardButton(text="⌨️ Ввести другой ID вручную", callback_data=f"{action_prefix}:manual")])
    buttons.append([InlineKeyboardButton(text="❌ Отмена", callback_data="route_cancel")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def mode_selection_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="↗️ Forward (со ссылкой на источник)", callback_data="route_mode:forward")],
            [InlineKeyboardButton(text="📋 Copy (чистая копия без авторства)", callback_data="route_mode:copy")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="route_cancel")],
        ]
    )


def confirm_delete_kb(action_code: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⚠️ Подтвердить удаление", callback_data=f"confirm_del:{action_code}")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="nav_main")],
        ]
    )


def privacy_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🗑️ Удалить мой личный профиль", callback_data="priv_del_my")],
            [InlineKeyboardButton(text="⚠️ Очистить ВСЮ аналитику", callback_data="priv_del_all")],
            [InlineKeyboardButton(text="⬅️ Главное меню", callback_data="nav_main")],
        ]
    )


def moderation_chats_list_kb(chats: List[Dict[str, Any]]) -> InlineKeyboardMarkup:
    buttons: List[List[InlineKeyboardButton]] = []
    for c in chats:
        title = c.get("title") or f"Chat {c['chat_id']}"
        filter_on = bool(c.get("profanity_filter_enabled", 0))
        warn_on = bool(c.get("profanity_warn_enabled", 0))
        del_on = bool(c.get("profanity_delete_enabled", 0))

        status_icons = []
        if filter_on:
            status_icons.append("🟢")
        else:
            status_icons.append("⚪")
        if warn_on:
            status_icons.append("⚠️")
        if del_on:
            status_icons.append("🗑️")

        badges = "".join(status_icons)
        btn_text = f"[{badges}] {title[:25]}"
        buttons.append([InlineKeyboardButton(text=btn_text, callback_data=f"mod_chat_view:{c['chat_id']}")])

    buttons.append([
        InlineKeyboardButton(text="🔄 Обновить", callback_data="admin_moderation_chats"),
        InlineKeyboardButton(text="⬅️ В админ-панель", callback_data="nav_admin"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def chat_moderation_detail_kb(chat: Dict[str, Any]) -> InlineKeyboardMarkup:
    cid = chat["chat_id"]
    filter_on = bool(chat.get("profanity_filter_enabled", 0))
    warn_on = bool(chat.get("profanity_warn_enabled", 0))
    del_on = bool(chat.get("profanity_delete_enabled", 0))
    ai_on = bool(chat.get("chat_ai_enabled", 0))

    strictness = chat.get("profanity_strictness", "hard")
    strict_labels = {
        "hard": "🤬 Hard",
        "medium": "⚠️ Medium",
        "all": "🛑 All",
    }
    strict_short = strict_labels.get(strictness, "🤬 Hard")

    warn_sec = int(chat.get("profanity_delete_warn_seconds", 0))
    warn_sec_label = f"⏱️ Варн: {warn_sec}с" if warn_sec > 0 else "⏱️ Варн: Выкл"

    auto_mute = int(chat.get("auto_mute_duration", 0))
    if auto_mute == 0:
        mute_label = "🔇 Мут: Выкл"
    elif auto_mute < 3600:
        mute_label = f"🔇 Мут: {auto_mute // 60}м"
    else:
        mute_label = f"🔇 Мут: {auto_mute // 3600}ч"

    warn_sec_label = f"⏱️ Срок варна: {warn_sec}с" if warn_sec > 0 else "⏱️ Срок варна: Выкл"

    btn_filter = f"{'🟢' if filter_on else '⚪'} Фильтр мата"
    btn_del = f"{'🟢' if del_on else '⚪'} Удалять"
    btn_warn = f"{'🟢' if warn_on else '⚪'} Предупреждать"
    btn_ai = f"{'🟢' if ai_on else '⚪'} ИИ Ричард"

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=btn_filter, callback_data=f"mod_toggle:{cid}:profanity_filter_enabled"),
                InlineKeyboardButton(text=btn_del, callback_data=f"mod_toggle:{cid}:profanity_delete_enabled"),
            ],
            [
                InlineKeyboardButton(text=btn_warn, callback_data=f"mod_toggle:{cid}:profanity_warn_enabled"),
                InlineKeyboardButton(text=warn_sec_label, callback_data=f"mod_autodel_cycle:{cid}"),
            ],
            [
                InlineKeyboardButton(text=f"🎯 Строгость: {strict_short}", callback_data=f"mod_select_strictness:{cid}"),
                InlineKeyboardButton(text=mute_label, callback_data=f"mod_automute_cycle:{cid}"),
            ],
            [
                InlineKeyboardButton(text="🚫 Стоп-слова", callback_data=f"mod_custom_words:{cid}"),
                InlineKeyboardButton(text="⚪ Белый список", callback_data=f"mod_wl_menu:{cid}"),
            ],
            [
                InlineKeyboardButton(text=btn_ai, callback_data=f"mod_toggle:{cid}:chat_ai_enabled"),
                InlineKeyboardButton(text="👥 По участникам", callback_data=f"mod_users_ctx:{cid}"),
            ],
            [
                InlineKeyboardButton(text="📜 Память ИИ", callback_data=f"mod_view_history:{cid}"),
                InlineKeyboardButton(text="🧹 Очистить чат", callback_data=f"mod_clear_mem:{cid}"),
            ],
            [
                InlineKeyboardButton(text="🔄 Обновить", callback_data=f"mod_chat_view:{cid}"),
                InlineKeyboardButton(text="⬅️ К списку чатов", callback_data="admin_moderation_chats"),
            ],
        ]
    )


def llm_settings_kb(is_enabled: bool, conf: Optional[Dict[str, Any]] = None, is_subadmin: bool = False) -> InlineKeyboardMarkup:
    conf = conf or {}
    toggle_text = "🟢 ИИ: ВКЛЮЧЕН (нажмите для откл.)" if is_enabled else "⚪ ИИ: ОТКЛЮЧЕН (нажмите для вкл.)"

    ctx = conf.get("companion_context_limit", 15)
    toks = conf.get("companion_max_tokens", 800)
    temp = conf.get("companion_temperature", 0.7)

    persona = conf.get("companion_persona", "student")
    p_labels = {
        "student": "🎓 Студент",
        "expert": "💼 Эксперт",
        "sarcastic": "😈 Дерзкий",
        "concise": "⚡ Краткий",
        "custom": "✍️ Свой",
    }
    p_text = p_labels.get(persona, "🎓 Студент")

    trigger = conf.get("companion_trigger_mode", "name_and_reply")
    trig_text = "🗣️ Имя+Реплай" if trigger == "name_and_reply" else "📢 Все теги"

    typing_on = conf.get("companion_typing_indicator", True)
    typing_text = "🟢 «Печатает...»" if typing_on else "⚪ «Печатает...»"

    rand_chance = conf.get("companion_random_reply_chance", 0)
    rand_text = f"💬 Инициатива: {rand_chance}%" if rand_chance > 0 else "💬 Инициатива: Выкл"

    if is_subadmin:
        llm_top_rows = [
            [InlineKeyboardButton(text=toggle_text, callback_data="llm_toggle_enabled")],
            [
                InlineKeyboardButton(text="🧠 Выбрать модель", callback_data="llm_select_model"),
                InlineKeyboardButton(text="🧪 Проверить связь", callback_data="llm_test_ping"),
            ],
        ]
    else:
        llm_top_rows = [
            [InlineKeyboardButton(text=toggle_text, callback_data="llm_toggle_enabled")],
            [
                InlineKeyboardButton(text="🔑 Задать API-ключ", callback_data="llm_set_key"),
                InlineKeyboardButton(text="🧠 Выбрать модель", callback_data="llm_select_model"),
            ],
            [
                InlineKeyboardButton(text="🌐 Base URL / IP", callback_data="llm_select_url"),
                InlineKeyboardButton(text="🧪 Проверить связь", callback_data="llm_test_ping"),
            ],
        ]

    return InlineKeyboardMarkup(
        inline_keyboard=llm_top_rows + [
            [
                InlineKeyboardButton(text=f"📚 Контекст: {ctx} сообщ.", callback_data="llm_select_context"),
                InlineKeyboardButton(text=f"📝 Ответ: {toks} tok", callback_data="llm_select_tokens"),
            ],
            [
                InlineKeyboardButton(text=f"🌡️ Temp: {temp}", callback_data="llm_select_temp"),
                InlineKeyboardButton(text=f"🎭 Персона: {p_text}", callback_data="llm_select_persona"),
            ],
            [
                InlineKeyboardButton(text=f"🎯 Реакция: {trig_text}", callback_data="llm_select_trigger"),
                InlineKeyboardButton(text=typing_text, callback_data="llm_toggle_typing"),
            ],
            [
                InlineKeyboardButton(text=rand_text, callback_data="llm_select_random"),
                InlineKeyboardButton(text="🧹 Очистить всю память", callback_data="llm_clear_all_mem"),
            ],
            [
                InlineKeyboardButton(text="🔄 Обновить", callback_data="admin_llm_settings"),
                InlineKeyboardButton(text="⬅️ В админ-панель", callback_data="nav_admin"),
            ],
        ]
    )


def llm_models_select_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="⚡ gpt-4o-mini (OpenAI)", callback_data="llm_preset_model:gpt-4o-mini"),
                InlineKeyboardButton(text="⚡ gemini-1.5-flash (Google)", callback_data="llm_preset_model:gemini-1.5-flash"),
            ],
            [
                InlineKeyboardButton(text="🧠 gpt-4o (OpenAI)", callback_data="llm_preset_model:gpt-4o"),
                InlineKeyboardButton(text="💎 gemini-1.5-pro (Google)", callback_data="llm_preset_model:gemini-1.5-pro"),
            ],
            [
                InlineKeyboardButton(text="🚀 deepseek-chat", callback_data="llm_preset_model:deepseek-chat"),
                InlineKeyboardButton(text="✏️ Ввести вручную", callback_data="llm_custom_model"),
            ],
            [InlineKeyboardButton(text="⬅️ Назад к ИИ", callback_data="admin_llm_settings")],
        ]
    )


def llm_base_urls_select_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🌐 OpenAI Official", callback_data="llm_preset_url:https://api.openai.com/v1"),
            ],
            [
                InlineKeyboardButton(text="🌐 Google Gemini (OpenAI API)", callback_data="llm_preset_url:https://generativelanguage.googleapis.com/v1beta/openai/"),
            ],
            [
                InlineKeyboardButton(text="🌐 DeepSeek API", callback_data="llm_preset_url:https://api.deepseek.com/v1"),
            ],
            [
                InlineKeyboardButton(text="✏️ Ввести свой URL / IP адрес", callback_data="llm_custom_url"),
            ],
            [InlineKeyboardButton(text="⬅️ Назад к ИИ", callback_data="admin_llm_settings")],
        ]
    )


def llm_cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="admin_llm_settings")],
        ]
    )


def my_style_kb(is_admin: bool = False) -> InlineKeyboardMarkup:
    buttons = []
    if is_admin:
        buttons.append([
            InlineKeyboardButton(text="👥 Стили всех участников", callback_data="admin_all_profiles"),
        ])
    buttons.append([
        InlineKeyboardButton(text="🔒 Приватность", callback_data="nav_privacy"),
        InlineKeyboardButton(text="⬅️ В главное меню", callback_data="nav_main"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)



def mod_strictness_select_kb(cid: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🤬 1. Только жесткий мат", callback_data=f"mod_set_strict:{cid}:hard")],
            [InlineKeyboardButton(text="⚠️ 2. Жесткий мат + грубые слова", callback_data=f"mod_set_strict:{cid}:medium")],
            [InlineKeyboardButton(text="🛑 3. Максимальная строгость (+ брань)", callback_data=f"mod_set_strict:{cid}:all")],
            [InlineKeyboardButton(text="⬅️ Назад к настройкам чата", callback_data=f"mod_chat_view:{cid}")],
        ]
    )


def mod_custom_words_kb(cid: int, has_words: bool) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="✏️ Задать / Изменить стоп-слова", callback_data=f"mod_cw_edit:{cid}")],
    ]
    if has_words:
        buttons.append([InlineKeyboardButton(text="🗑️ Очистить свои стоп-слова", callback_data=f"mod_cw_clear:{cid}")])
    buttons.append([InlineKeyboardButton(text="⬅️ Назад к настройкам чата", callback_data=f"mod_chat_view:{cid}")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def llm_context_select_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="⚡ 5 сообщ.", callback_data="llm_preset_ctx:5"),
                InlineKeyboardButton(text="📌 10 сообщ.", callback_data="llm_preset_ctx:10"),
            ],
            [
                InlineKeyboardButton(text="📗 15 сообщ. (стандарт)", callback_data="llm_preset_ctx:15"),
                InlineKeyboardButton(text="📚 25 сообщ.", callback_data="llm_preset_ctx:25"),
            ],
            [
                InlineKeyboardButton(text="📖 40 сообщ. (глубокий)", callback_data="llm_preset_ctx:40"),
                InlineKeyboardButton(text="✏️ Ввести число", callback_data="llm_custom_ctx"),
            ],
            [InlineKeyboardButton(text="⬅️ Назад в меню ИИ", callback_data="admin_llm_settings")],
        ]
    )


def llm_tokens_select_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="⚡ Краткий (~250)", callback_data="llm_preset_tokens:250"),
                InlineKeyboardButton(text="📝 Средний (~600)", callback_data="llm_preset_tokens:600"),
            ],
            [
                InlineKeyboardButton(text="📖 Развернутый (~1000)", callback_data="llm_preset_tokens:1000"),
                InlineKeyboardButton(text="📚 Большой (~1500)", callback_data="llm_preset_tokens:1500"),
            ],
            [
                InlineKeyboardButton(text="🚀 Максимум (~2500)", callback_data="llm_preset_tokens:2500"),
                InlineKeyboardButton(text="✏️ Ввести число", callback_data="llm_custom_tokens"),
            ],
            [InlineKeyboardButton(text="⬅️ Назад в меню ИИ", callback_data="admin_llm_settings")],
        ]
    )


def llm_temp_select_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🎯 Точный (0.2)", callback_data="llm_preset_temp:0.2"),
                InlineKeyboardButton(text="⚖️ Сбалансированный (0.7)", callback_data="llm_preset_temp:0.7"),
                InlineKeyboardButton(text="🎨 Креативный (1.0)", callback_data="llm_preset_temp:1.0"),
            ],
            [InlineKeyboardButton(text="⬅️ Назад в меню ИИ", callback_data="admin_llm_settings")],
        ]
    )


def mod_whitelist_kb(cid: int, has_words: bool) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="✏️ Задать / Изменить белый список", callback_data=f"mod_wl_edit:{cid}")],
    ]
    if has_words:
        buttons.append([InlineKeyboardButton(text="🗑️ Очистить белый список", callback_data=f"mod_wl_clear:{cid}")])
    buttons.append([InlineKeyboardButton(text="⬅️ Назад к настройкам чата", callback_data=f"mod_chat_view:{cid}")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def llm_persona_select_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🎓 Студент-сокурсник (по умолч.)", callback_data="llm_set_persona:student")],
            [InlineKeyboardButton(text="💼 Деловой эксперт", callback_data="llm_set_persona:expert")],
            [InlineKeyboardButton(text="😈 Дерзкий / Остроумный", callback_data="llm_set_persona:sarcastic")],
            [InlineKeyboardButton(text="⚡ Краткий / По делу", callback_data="llm_set_persona:concise")],
            [InlineKeyboardButton(text="✍️ Задать свой системный промпт", callback_data="llm_custom_persona")],
            [InlineKeyboardButton(text="⬅️ Назад в меню ИИ", callback_data="admin_llm_settings")],
        ]
    )


def llm_trigger_select_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🗣️ Только имя («Ричард») и реплай", callback_data="llm_set_trigger:name_and_reply")],
            [InlineKeyboardButton(text="📢 Все упоминания (@RichardHelperBot + имя + реплай)", callback_data="llm_set_trigger:all")],
            [InlineKeyboardButton(text="⬅️ Назад в меню ИИ", callback_data="admin_llm_settings")],
        ]
    )


def mod_history_kb(cid: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🧹 Очистить память для этого чата", callback_data=f"mod_clear_mem:{cid}")],
            [InlineKeyboardButton(text="⬅️ Назад к настройкам чата", callback_data=f"mod_chat_view:{cid}")],
        ]
    )


def llm_random_select_kb(curr_val: int = 0) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"{'✅ ' if curr_val == 0 else ''}⚪ Выкл (только тег/реплай)", callback_data="llm_set_random:0")],
            [
                InlineKeyboardButton(text=f"{'✅ ' if curr_val == 2 else ''}🟢 Редко (2%)", callback_data="llm_set_random:2"),
                InlineKeyboardButton(text=f"{'✅ ' if curr_val == 5 else ''}🟡 Умеренно (5%)", callback_data="llm_set_random:5"),
            ],
            [
                InlineKeyboardButton(text=f"{'✅ ' if curr_val == 10 else ''}🟠 Активно (10%)", callback_data="llm_set_random:10"),
                InlineKeyboardButton(text="✏️ Задать свой %", callback_data="llm_custom_random"),
            ],
            [InlineKeyboardButton(text="⬅️ Назад в меню ИИ", callback_data="admin_llm_settings")],
        ]
    )


def mod_participants_list_kb(chat_id: int, participants: List[Dict[str, Any]]) -> InlineKeyboardMarkup:
    buttons: List[List[InlineKeyboardButton]] = []
    for p in participants:
        uname = f" (@{p['username']})" if p.get("username") else ""
        label = f"👤 {p['user_name'][:14]}{uname} ({p['msg_count']} сообщ.)"
        buttons.append([InlineKeyboardButton(text=label, callback_data=f"mod_user_ctx:{chat_id}:{p['user_id']}")])

    buttons.append([InlineKeyboardButton(text="⬅️ Назад к настройкам чата", callback_data=f"mod_chat_view:{chat_id}")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def mod_user_history_kb(chat_id: int, user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🧹 Очистить контекст этого участника", callback_data=f"mod_clear_user_ctx:{chat_id}:{user_id}")],
            [InlineKeyboardButton(text="👥 Ко всем участникам", callback_data=f"mod_users_ctx:{chat_id}")],
            [InlineKeyboardButton(text="⬅️ К настройкам чата", callback_data=f"mod_chat_view:{chat_id}")],
        ]
    )
