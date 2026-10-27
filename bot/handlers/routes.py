from __future__ import annotations

import logging
from typing import Any, Dict, List

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from database.connection import Database
from database.repositories.chat_repo import ChatRepository
from database.repositories.route_repo import RouteRepository
from forwarder.cycle_detector import RouteCycleDetector
from bot.keyboards.inline import (
    MEDIA_TYPE_LABELS,
    keywords_menu_kb,
    main_menu_kb,
    media_types_selection_kb,
    mode_selection_kb,
    route_detail_kb,
    routes_list_kb,
    select_chat_kb,
    shadow_dest_kb,
)

logger = logging.getLogger(__name__)
router = Router(name="routes_router")


class CreateRouteStates(StatesGroup):
    waiting_for_name = State()
    waiting_for_source = State()
    waiting_for_dest = State()
    waiting_for_mode = State()


class RouteKeywordStates(StatesGroup):
    waiting_for_keyword = State()


class ShadowDestStates(StatesGroup):
    waiting_for_shadow_dest = State()


def render_route_card(route: Dict[str, Any]) -> str:
    route_id = route["id"]
    name = route["name"]
    is_active = bool(route.get("is_active"))
    mode = route.get("mode", "forward")
    is_hidden = bool(route.get("is_hidden"))
    shadow_id = route.get("shadow_dest_chat_id")
    shadow_title = route.get("shadow_dest_title") or (f"Чат {shadow_id}" if shadow_id else None)

    status_str = "🟢 <b>Активен (пересылает)</b>" if is_active else "⏸️ <b>Приостановлен</b>"
    mode_str = "↗️ <b>Forward</b> (со ссылкой на автора)" if mode == "forward" else "📋 <b>Copy</b> (чистая копия без авторства)"
    stealth_badge = " 🕵️ <b>[СКРЫТЫЙ МАРШРУТ]</b>" if is_hidden else ""

    source_title = route.get("source_title") or f"Чат {route['source_chat_id']}"
    dest_title = route.get("dest_title") or f"Чат {route['destination_chat_id']}"

    selected_types: List[str] = route.get("filter_media_types", [])
    if not selected_types:
        media_summary = "✅ <i>Пересылаются ВСЕ типы контента (без ограничений)</i>"
    else:
        media_lines = []
        for mtype, label in MEDIA_TYPE_LABELS.items():
            icon = "✅" if mtype in selected_types else "❌"
            media_lines.append(f"{icon} {label}")
        media_summary = " | ".join(media_lines[:5]) + "\n• " + " | ".join(media_lines[5:])

    kws = route.get("filter_keywords", [])
    kws_str = ", ".join(f"<code>{w}</code>" for w in kws) if kws else "<i>(любые сообщения)</i>"

    ex_kws = route.get("filter_exclude_keywords", [])
    ex_str = ", ".join(f"<code>{w}</code>" for w in ex_kws) if ex_kws else "<i>(нет стоп-слов)</i>"

    lines = [
        f"🔀 <b>Маршрут #{route_id}: {name}</b>{stealth_badge}\n",
        f"• Статус: {status_str}",
        f"• Режим: {mode_str}\n",
        f"📡 <b>Источник:</b> {source_title} [<code>{route['source_chat_id']}</code>]",
        f"🎯 <b>Назначение:</b> {dest_title} [<code>{route['destination_chat_id']}</code>]",
    ]

    if shadow_id:
        lines.append(f"🕵️ <b>Скрытый пункт назначения:</b> {shadow_title} [<code>{shadow_id}</code>]")

    lines.extend([
        f"\n📦 <b>Фильтр типов контента:</b>\n• {media_summary}\n",
        f"🔍 <b>Фильтр по словам:</b>",
        f"• Обязательные слова: {kws_str}",
        f"• Стоп-слова (пропускать): {ex_str}\n",
    ])

    if mode == "copy":
        clean_links = "🟢 Вкл" if route.get("clean_links") else "⚪ Выкл"
        clean_tags = "🟢 Вкл" if route.get("clean_tags") else "⚪ Выкл"
        clean_mentions = "🟢 Вкл" if route.get("clean_mentions") else "⚪ Выкл"
        source_link = "🟢 Вкл" if route.get("append_source_link") else "⚪ Выкл"

        lines.extend([
            "🛠️ <b>Опции форматирования (режим Copy):</b>",
            f"• Удалять ссылки (http/https): {clean_links}",
            f"• Удалять хештеги (#тег): {clean_tags}",
            f"• Удалять @упоминания: {clean_mentions}",
            f"• Добавлять подпись источника: {source_link}\n",
        ])

    lines.append("<i>Нажмите кнопки ниже, чтобы изменить любую настройку в 1 клик:</i>")
    return "\n".join(lines)


@router.message(Command("routes"))
@router.callback_query(F.data == "nav_routes")
async def cmd_routes(event: Message | CallbackQuery, db: Database, is_admin: bool = False) -> None:
    user_id = event.from_user.id if event.from_user else 0
    async with db.connect() as conn:
        repo = RouteRepository(conn)
        routes = await repo.list_routes(user_id=None if is_admin else user_id)

    header_badge = "Все маршруты системы" if is_admin else "Ваши маршруты"
    text = f"🔀 <b>{header_badge} ({len(routes)}):</b>\n\n"
    if not routes:
        text += "Маршруты ещё не созданы. Нажмите <b>«➕ Создать маршрут»</b> ниже."
    else:
        text += "Выберите маршрут для детальной настройки фильтров и опций:"

    kb = routes_list_kb(routes)
    if isinstance(event, Message):
        await event.answer(text, reply_markup=kb, parse_mode="HTML")
    else:
        await event.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
        await event.answer()


@router.message(Command("sources"))
@router.callback_query(F.data == "nav_sources")
async def cmd_sources(event: Message | CallbackQuery, db: Database, is_admin: bool = False) -> None:
    user_id = event.from_user.id if event.from_user else 0
    async with db.connect() as conn:
        repo = ChatRepository(conn)
        sources = await repo.list_sources(user_id=None if is_admin else user_id)

    lines = ["📡 <b>Зарегистрированные чаты-источники:</b>\n"]
    if not sources:
        lines.append("Источники ещё не добавлены.")
        lines.append(
            "\n<i>💡 Чтобы чат появился здесь: добавьте бота в группу/канал и отправьте любое сообщение.\n"
            "Для каналов бот должен быть Администратором, для групп — отключите Privacy Mode в @BotFather.</i>"
        )
    else:
        for s in sources:
            user_part = f" (@{s['username']})" if s.get("username") else ""
            lines.append(f"• <b>{s['title']}</b>{user_part} [<code>{s['chat_id']}</code>, {s['chat_type']}]")

    text = "\n".join(lines)
    if isinstance(event, Message):
        await event.answer(text, reply_markup=main_menu_kb(is_admin=is_admin), parse_mode="HTML")
    else:
        await event.message.edit_text(text, reply_markup=main_menu_kb(is_admin=is_admin), parse_mode="HTML")
        await event.answer()


@router.message(Command("destinations"))
@router.callback_query(F.data == "nav_destinations")
async def cmd_destinations(event: Message | CallbackQuery, db: Database, is_admin: bool = False) -> None:
    user_id = event.from_user.id if event.from_user else 0
    async with db.connect() as conn:
        repo = ChatRepository(conn)
        dests = await repo.list_destinations(user_id=None if is_admin else user_id)

    lines = ["🎯 <b>Зарегистрированные чаты-назначения:</b>\n"]
    if not dests:
        lines.append("Назначения ещё не зарегистрированы.")
        lines.append("\n<i>💡 Добавьте бота в целевой канал как Администратора с правом публикации сообщений.</i>")
    else:
        for d in dests:
            user_part = f" (@{d['username']})" if d.get("username") else ""
            lines.append(f"• <b>{d['title']}</b>{user_part} [<code>{d['chat_id']}</code>, {d['chat_type']}]")

    text = "\n".join(lines)
    if isinstance(event, Message):
        await event.answer(text, reply_markup=main_menu_kb(is_admin=is_admin), parse_mode="HTML")
    else:
        await event.message.edit_text(text, reply_markup=main_menu_kb(is_admin=is_admin), parse_mode="HTML")
        await event.answer()


@router.callback_query(F.data.startswith("route_view:"))
async def cb_route_view(callback: CallbackQuery, db: Database, is_admin: bool = False) -> None:
    await callback.answer()
    route_id = int(callback.data.split(":")[1])
    async with db.connect() as conn:
        repo = RouteRepository(conn)
        route = await repo.get_route(route_id)

    if not route:
        await callback.message.edit_text("❌ Маршрут не найден.", reply_markup=main_menu_kb(is_admin=is_admin))
        return

    text = render_route_card(route)
    await callback.message.edit_text(text, reply_markup=route_detail_kb(route, is_admin=is_admin), parse_mode="HTML")


@router.callback_query(F.data.startswith("route_toggle:"))
async def cb_route_toggle(callback: CallbackQuery, db: Database, is_admin: bool = False) -> None:
    await callback.answer()
    route_id = int(callback.data.split(":")[1])
    async with db.connect() as conn:
        repo = RouteRepository(conn)
        route = await repo.get_route(route_id)
        if route:
            await repo.toggle_route(route_id, not route["is_active"])
            route = await repo.get_route(route_id)

    if route:
        await callback.message.edit_text(render_route_card(route), reply_markup=route_detail_kb(route, is_admin=is_admin), parse_mode="HTML")


@router.callback_query(F.data.startswith("route_mode_toggle:"))
async def cb_route_mode_toggle(callback: CallbackQuery, db: Database, is_admin: bool = False) -> None:
    await callback.answer()
    route_id = int(callback.data.split(":")[1])
    async with db.connect() as conn:
        repo = RouteRepository(conn)
        await repo.toggle_mode(route_id)
        route = await repo.get_route(route_id)

    if route:
        await callback.message.edit_text(render_route_card(route), reply_markup=route_detail_kb(route, is_admin=is_admin), parse_mode="HTML")


@router.callback_query(F.data.startswith("route_toggle_field:"))
async def cb_route_toggle_field(callback: CallbackQuery, db: Database, is_admin: bool = False) -> None:
    await callback.answer()
    parts = callback.data.split(":")
    route_id = int(parts[1])
    field_name = parts[2]

    async with db.connect() as conn:
        repo = RouteRepository(conn)
        await repo.toggle_field(route_id, field_name)
        route = await repo.get_route(route_id)

    if route:
        await callback.message.edit_text(render_route_card(route), reply_markup=route_detail_kb(route, is_admin=is_admin), parse_mode="HTML")


@router.callback_query(F.data.startswith("route_media_menu:"))
async def cb_route_media_menu(callback: CallbackQuery, db: Database) -> None:
    await callback.answer()
    route_id = int(callback.data.split(":")[1])
    async with db.connect() as conn:
        repo = RouteRepository(conn)
        route = await repo.get_route(route_id)

    if not route:
        return

    selected = route.get("filter_media_types", [])
    text = (
        f"🎯 <b>Настройка типов контента для маршрута #{route_id}:</b>\n\n"
        "Нажимайте на кнопки, чтобы включить (✅) или исключить (❌) нужный тип медиа:\n"
        "• <i>Если включены все или ни один не выбран — пересылаются все сообщения.</i>"
    )
    await callback.message.edit_text(
        text,
        reply_markup=media_types_selection_kb(route_id, selected),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("mtype_toggle:"))
async def cb_mtype_toggle(callback: CallbackQuery, db: Database) -> None:
    await callback.answer()
    parts = callback.data.split(":")
    route_id = int(parts[1])
    mtype = parts[2]

    async with db.connect() as conn:
        repo = RouteRepository(conn)
        route = await repo.get_route(route_id)
        current = list(route.get("filter_media_types", [])) if route else []
        if not current:
            current = list(MEDIA_TYPE_LABELS.keys())

        if mtype in current:
            current.remove(mtype)
        else:
            current.append(mtype)

        import json
        await repo.execute("UPDATE routes SET filter_media_types = ? WHERE id = ?", (json.dumps(current), route_id))

    await callback.message.edit_reply_markup(reply_markup=media_types_selection_kb(route_id, current))


@router.callback_query(F.data.startswith("mtype_all:"))
async def cb_mtype_all(callback: CallbackQuery, db: Database) -> None:
    await callback.answer()
    parts = callback.data.split(":")
    route_id = int(parts[1])
    enable = parts[2] == "1"

    async with db.connect() as conn:
        repo = RouteRepository(conn)
        selected = await repo.set_all_media_types(route_id, enable_all=enable)

    await callback.message.edit_reply_markup(reply_markup=media_types_selection_kb(route_id, selected))


@router.callback_query(F.data.startswith("route_kw_menu:"))
async def cb_route_kw_menu(callback: CallbackQuery, db: Database) -> None:
    await callback.answer()
    route_id = int(callback.data.split(":")[1])
    async with db.connect() as conn:
        repo = RouteRepository(conn)
        route = await repo.get_route(route_id)

    kws = route.get("filter_keywords", []) if route else []
    kws_str = "\n".join(f"• <code>{w}</code>" for w in kws) if kws else "<i>(список пуст, пересылаются все сообщения)</i>"

    text = (
        f"🔤 <b>Обязательные ключевые слова для маршрута #{route_id}:</b>\n\n"
        f"Сообщение будет переслано, только если в нём есть хотя бы одно из слов:\n{kws_str}"
    )
    await callback.message.edit_text(text, reply_markup=keywords_menu_kb(route_id, is_exclude=False), parse_mode="HTML")


@router.callback_query(F.data.startswith("route_ex_menu:"))
async def cb_route_ex_menu(callback: CallbackQuery, db: Database) -> None:
    await callback.answer()
    route_id = int(callback.data.split(":")[1])
    async with db.connect() as conn:
        repo = RouteRepository(conn)
        route = await repo.get_route(route_id)

    kws = route.get("filter_exclude_keywords", []) if route else []
    kws_str = "\n".join(f"• <code>{w}</code>" for w in kws) if kws else "<i>(список пуст, ничего не блокируется)</i>"

    text = (
        f"🚫 <b>Стоп-слова для маршрута #{route_id}:</b>\n\n"
        f"Сообщение будет ПРОПУЩЕНО, если содержит любое из этих слов:\n{kws_str}"
    )
    await callback.message.edit_text(text, reply_markup=keywords_menu_kb(route_id, is_exclude=True), parse_mode="HTML")


@router.callback_query(F.data.startswith("kw_clear:"))
async def cb_kw_clear(callback: CallbackQuery, db: Database) -> None:
    await callback.answer("Список очищен!")
    parts = callback.data.split(":")
    is_exclude = parts[1] == "ex"
    route_id = int(parts[2])

    async with db.connect() as conn:
        repo = RouteRepository(conn)
        if is_exclude:
            await repo.clear_exclude_keywords(route_id)
            await cb_route_ex_menu(callback, db)
        else:
            await repo.clear_keywords(route_id)
            await cb_route_kw_menu(callback, db)


@router.callback_query(F.data.startswith("kw_add:"))
async def cb_kw_add_prompt(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    parts = callback.data.split(":")
    is_exclude = parts[1] == "ex"
    route_id = int(parts[2])

    await state.set_state(RouteKeywordStates.waiting_for_keyword)
    await state.update_data(route_id=route_id, is_exclude=is_exclude)

    type_label = "стоп-слово (для пропуска)" if is_exclude else "ключевое слово (для пересылки)"
    await callback.message.answer(
        f"✏️ Введите новое {type_label}:\n<i>(можно ввести одно слово или несколько через запятую)</i>",
        parse_mode="HTML",
    )


@router.message(RouteKeywordStates.waiting_for_keyword)
async def state_kw_save(message: Message, state: FSMContext, db: Database, is_admin: bool = False) -> None:
    data = await state.get_data()
    route_id = data["route_id"]
    is_exclude = data["is_exclude"]
    await state.clear()

    input_text = message.text.strip()
    words = [w.strip() for w in input_text.split(",") if w.strip()]

    async with db.connect() as conn:
        repo = RouteRepository(conn)
        for w in words:
            if is_exclude:
                await repo.add_exclude_keyword(route_id, w)
            else:
                await repo.add_keyword(route_id, w)

        route = await repo.get_route(route_id)

    await message.answer(
        f"✅ Добавлено слов: {len(words)} для маршрута #{route_id}.",
        reply_markup=route_detail_kb(route, is_admin=is_admin) if route else main_menu_kb(is_admin=is_admin),
    )


@router.callback_query(F.data.startswith("route_delete:"))
async def cb_route_delete(callback: CallbackQuery, db: Database) -> None:
    route_id = int(callback.data.split(":")[1])
    async with db.connect() as conn:
        repo = RouteRepository(conn)
        await repo.delete_route(route_id)

    await callback.answer("Маршрут успешно удалён.", show_alert=True)
    await cmd_routes(callback, db)


@router.callback_query(F.data == "route_create")
async def cb_route_create_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(CreateRouteStates.waiting_for_name)
    await callback.message.edit_text(
        "📝 <b>Шаг 1 из 4:</b> Введите понятное название для нового маршрута (например: <i>Новости -> Архив</i>):",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(CreateRouteStates.waiting_for_name)
async def state_route_name(message: Message, state: FSMContext, db: Database) -> None:
    name = message.text.strip()
    await state.update_data(name=name)
    await state.set_state(CreateRouteStates.waiting_for_source)

    async with db.connect() as conn:
        chat_repo = ChatRepository(conn)
        sources = await chat_repo.list_sources()

    if sources:
        kb = select_chat_kb(sources, "sel_src")
        await message.answer(
            "📡 <b>Шаг 2 из 4:</b> Выберите <b>источник</b> из списка известных чатов или нажмите «Ввести ID вручную»:",
            reply_markup=kb,
            parse_mode="HTML",
        )
    else:
        await message.answer(
            "📡 <b>Шаг 2 из 4:</b> Введите <b>Telegram ID чата-источника</b> (например: <code>-1001234567890</code>):",
            parse_mode="HTML",
        )


@router.callback_query(CreateRouteStates.waiting_for_source, F.data.startswith("sel_src:"))
async def cb_select_source(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    val = callback.data.split(":")[1]
    if val == "manual":
        await callback.message.edit_text(
            "📡 Введите <b>Telegram ID чата-источника</b> вручную (число, например: <code>-1001234567890</code>):",
            parse_mode="HTML",
        )
        await callback.answer()
        return

    source_id = int(val)
    await state.update_data(source_chat_id=source_id)
    await state.set_state(CreateRouteStates.waiting_for_dest)

    async with db.connect() as conn:
        chat_repo = ChatRepository(conn)
        dests = await chat_repo.list_destinations()

    if dests:
        kb = select_chat_kb(dests, "sel_dst")
        await callback.message.edit_text(
            f"🎯 <b>Шаг 3 из 4:</b> Источник выбран: <code>{source_id}</code>.\n"
            "Выберите <b>целевой чат (назначение)</b> из списка или введите ID вручную:",
            reply_markup=kb,
            parse_mode="HTML",
        )
    else:
        await callback.message.edit_text(
            f"🎯 <b>Шаг 3 из 4:</b> Источник выбран: <code>{source_id}</code>.\n"
            "Введите <b>Telegram ID целевого чата-назначения</b>:",
            parse_mode="HTML",
        )
    await callback.answer()


@router.message(CreateRouteStates.waiting_for_source)
async def state_route_source(message: Message, state: FSMContext, db: Database) -> None:
    try:
        source_id = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Ошибка: ID чата должен быть целым числом. Попробуйте снова:")
        return

    await state.update_data(source_chat_id=source_id)
    await state.set_state(CreateRouteStates.waiting_for_dest)

    async with db.connect() as conn:
        chat_repo = ChatRepository(conn)
        dests = await chat_repo.list_destinations()

    if dests:
        kb = select_chat_kb(dests, "sel_dst")
        await message.answer(
            f"🎯 <b>Шаг 3 из 4:</b> Источник: <code>{source_id}</code>.\n"
            "Выберите <b>целевой чат-назначение</b> из списка или введите ID вручную:",
            reply_markup=kb,
            parse_mode="HTML",
        )
    else:
        await message.answer(
            "🎯 <b>Шаг 3 из 4:</b> Введите <b>Telegram ID целевого чата-назначения</b>:",
            parse_mode="HTML",
        )


@router.callback_query(CreateRouteStates.waiting_for_dest, F.data.startswith("sel_dst:"))
async def cb_select_dest(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    val = callback.data.split(":")[1]
    if val == "manual":
        await callback.message.edit_text(
            "🎯 Введите <b>Telegram ID целевого чата</b> вручную (число, например: <code>-1001234567890</code>):",
            parse_mode="HTML",
        )
        await callback.answer()
        return

    dest_id = int(val)
    data = await state.get_data()
    source_id = data["source_chat_id"]

    if source_id == dest_id:
        await callback.answer("Источник и назначение не могут совпадать!", show_alert=True)
        return

    async with db.connect() as conn:
        repo = RouteRepository(conn)
        existing_pairs = await repo.get_route_pairs()

    if RouteCycleDetector.would_create_cycle(existing_pairs, source_id, dest_id):
        await callback.answer("⛔ Ошибка: создание этого маршрута вызовет циклическую пересылку!", show_alert=True)
        return

    await state.update_data(destination_chat_id=dest_id)
    await state.set_state(CreateRouteStates.waiting_for_mode)
    await callback.message.edit_text(
        "⚙️ <b>Шаг 4 из 4:</b> Выберите базовый режим отправки сообщений:\n"
        "<i>(Все детальные фильтры медиа и стоп-слов вы сможете настроить сразу после создания)</i>",
        reply_markup=mode_selection_kb(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(CreateRouteStates.waiting_for_dest)
async def state_route_dest(message: Message, state: FSMContext, db: Database) -> None:
    try:
        dest_id = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Ошибка: ID чата должен быть целым числом. Попробуйте снова:")
        return

    data = await state.get_data()
    source_id = data["source_chat_id"]

    if source_id == dest_id:
        await message.answer("❌ Источник и назначение не могут совпадать! Введите другой ID назначения:")
        return

    async with db.connect() as conn:
        repo = RouteRepository(conn)
        existing_pairs = await repo.get_route_pairs()

    if RouteCycleDetector.would_create_cycle(existing_pairs, source_id, dest_id):
        await message.answer(
            "⛔ <b>Обнаружен риск циклической пересылки!</b>\n"
            "Этот маршрут создаст петлю между чатами. Выберите другое назначение:",
            parse_mode="HTML",
        )
        return

    await state.update_data(destination_chat_id=dest_id)
    await state.set_state(CreateRouteStates.waiting_for_mode)
    await message.answer(
        "⚙️ <b>Шаг 4 из 4:</b> Выберите базовый режим отправки сообщений:\n"
        "<i>(Фильтры медиа, слов и удаление ссылок можно будет настроить сразу после создания)</i>",
        reply_markup=mode_selection_kb(),
        parse_mode="HTML",
    )


@router.callback_query(CreateRouteStates.waiting_for_mode, F.data.startswith("route_mode:"))
async def state_route_mode(callback: CallbackQuery, state: FSMContext, db: Database, is_admin: bool = False) -> None:
    await callback.answer()
    mode = callback.data.split(":")[1]
    data = await state.get_data()
    await state.clear()

    try:
        source_id = data.get("source_chat_id")
        dest_id = data.get("destination_chat_id")
        name = data.get("name", "Маршрут")
        is_hidden = bool(data.get("is_hidden", False))

        if not source_id or not dest_id:
            await callback.message.edit_text(
                "❌ Ошибка: данные маршрута утеряны. Начните заново через /routes",
                reply_markup=main_menu_kb(is_admin=is_admin),
            )
            return

        source_title = None
        dest_title = None
        source_type = "unknown"
        dest_type = "unknown"
        source_user = None
        dest_user = None

        try:
            s_chat = await callback.bot.get_chat(source_id)
            source_title = s_chat.title or s_chat.full_name
            source_type = s_chat.type
            source_user = s_chat.username
        except Exception:
            pass

        try:
            d_chat = await callback.bot.get_chat(dest_id)
            dest_title = d_chat.title or d_chat.full_name
            dest_type = d_chat.type
            dest_user = d_chat.username
        except Exception:
            pass

        async with db.connect() as conn:
            chat_repo = ChatRepository(conn)
            await chat_repo.ensure_chat_exists(
                source_id, is_source=True, title=source_title, chat_type=source_type, username=source_user
            )
            await chat_repo.ensure_chat_exists(
                dest_id, is_destination=True, title=dest_title, chat_type=dest_type, username=dest_user
            )

            repo = RouteRepository(conn)
            existing_routes = await repo.get_routes_for_source(source_id, active_only=False)
            already_exists = any(r["destination_chat_id"] == dest_id for r in existing_routes)
            if already_exists:
                await callback.message.edit_text(
                    f"⚠️ <b>Маршрут между источником <code>{source_id}</code> и назначением <code>{dest_id}</code> уже существует!</b>",
                    reply_markup=main_menu_kb(is_admin=is_admin),
                    parse_mode="HTML",
                )
                return

            user_id = callback.from_user.id if callback.from_user else 0
            route = await repo.create_route(
                name=name,
                source_chat_id=source_id,
                destination_chat_id=dest_id,
                mode=mode,
                created_by_user_id=user_id,
                is_hidden=is_hidden,
            )
            full_route = await repo.get_route(route["id"])

        await callback.message.edit_text(
            render_route_card(full_route or route),
            reply_markup=route_detail_kb(full_route or route, is_admin=is_admin),
            parse_mode="HTML",
        )
    except Exception as e:
        logger.exception("Error in state_route_mode: %s", e)
        await callback.message.answer(
            f"❌ Не удалось сохранить маршрут. Причина: <code>{e}</code>\nПопробуйте снова через /routes",
            reply_markup=main_menu_kb(is_admin=is_admin),
            parse_mode="HTML",
        )


@router.callback_query(F.data == "route_cancel")
async def cb_route_cancel(callback: CallbackQuery, state: FSMContext, is_admin: bool = False) -> None:
    await state.clear()
    await callback.message.edit_text("Создание маршрута отменено.", reply_markup=main_menu_kb(is_admin=is_admin))
    await callback.answer()


@router.callback_query(F.data == "route_create_hidden")
async def cb_route_create_hidden_start(callback: CallbackQuery, state: FSMContext, is_admin: bool = False) -> None:
    if not is_admin:
        await callback.answer("Только для администраторов.", show_alert=True)
        return
    await state.clear()
    await state.set_state(CreateRouteStates.waiting_for_name)
    await state.update_data(is_hidden=True)
    await callback.message.edit_text(
        "🕵️ <b>Создание скрытого маршрута (Шаг 1 из 4):</b>\n\n"
        "Введите понятное название для скрытого маршрута:\n"
        "<i>(Этот маршрут будет виден исключительно в меню Супер-Администратора)</i>",
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("route_toggle_hidden:"))
async def cb_route_toggle_hidden(callback: CallbackQuery, db: Database, is_admin: bool = False) -> None:
    if not is_admin:
        await callback.answer("Только для администраторов.", show_alert=True)
        return
    await callback.answer()
    route_id = int(callback.data.split(":")[1])
    async with db.connect() as conn:
        repo = RouteRepository(conn)
        new_status = await repo.toggle_hidden(route_id)
        route = await repo.get_route(route_id)

    if route:
        status_text = "скрытым 🕵️" if new_status else "публичным 🌐"
        await callback.answer(f"Маршрут #{route_id} теперь {status_text}!", show_alert=True)
        await callback.message.edit_text(
            render_route_card(route),
            reply_markup=route_detail_kb(route, is_admin=is_admin),
            parse_mode="HTML",
        )


@router.callback_query(F.data.startswith("route_shadow_menu:"))
async def cb_route_shadow_menu(callback: CallbackQuery, db: Database, is_admin: bool = False) -> None:
    if not is_admin:
        await callback.answer("Только для администраторов.", show_alert=True)
        return
    await callback.answer()
    route_id = int(callback.data.split(":")[1])
    async with db.connect() as conn:
        repo = RouteRepository(conn)
        route = await repo.get_route(route_id)

    if not route:
        return

    shadow_id = route.get("shadow_dest_chat_id")
    shadow_title = route.get("shadow_dest_title") or (f"Чат {shadow_id}" if shadow_id else None)
    current_status = f"<code>{shadow_id}</code> ({shadow_title})" if shadow_id else "<i>не задан (отключен)</i>"

    text = (
        f"🕵️ <b>Скрытый пункт назначения (Теневая копия)</b>\n"
        f"для маршрута #{route_id} ({route['name']}):\n\n"
        f"• Текущий теневой чат: {current_status}\n\n"
        "<i>При настройке скрытого назначения все входящие сообщения, пересылаемые по этому маршруту, "
        "будут одновременно и незаметно копироваться в указанный скрытый чат.</i>\n\n"
        "Выберите действие:"
    )
    kb = shadow_dest_kb(route_id, shadow_id)
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data.startswith("shadow_set:"))
async def cb_shadow_set_prompt(callback: CallbackQuery, state: FSMContext, is_admin: bool = False) -> None:
    if not is_admin:
        await callback.answer("Только для администраторов.", show_alert=True)
        return
    await callback.answer()
    route_id = int(callback.data.split(":")[1])
    await state.set_state(ShadowDestStates.waiting_for_shadow_dest)
    await state.update_data(route_id=route_id)
    await callback.message.answer(
        f"✏️ <b>Введите Telegram ID скрытого чата-назначения</b> для маршрута #{route_id}:\n"
        "<i>(Числовой ID, например <code>-1001234567890</code>. Бот должен состоять в этом чате и иметь права на отправку)</i>",
        parse_mode="HTML",
    )


@router.message(ShadowDestStates.waiting_for_shadow_dest)
async def state_save_shadow_dest(message: Message, state: FSMContext, db: Database, is_admin: bool = False) -> None:
    if not is_admin:
        return
    try:
        shadow_id = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Ошибка: ID чата должен быть целым числом. Попробуйте снова:")
        return

    data = await state.get_data()
    route_id = data.get("route_id")
    await state.clear()

    chat_title = None
    chat_type = "unknown"
    chat_user = None
    try:
        c = await message.bot.get_chat(shadow_id)
        chat_title = c.title or c.full_name
        chat_type = c.type
        chat_user = c.username
    except Exception:
        pass

    async with db.connect() as conn:
        chat_repo = ChatRepository(conn)
        await chat_repo.ensure_chat_exists(
            shadow_id, is_destination=True, title=chat_title, chat_type=chat_type, username=chat_user
        )
        repo = RouteRepository(conn)
        await repo.set_shadow_destination(route_id, shadow_id)
        route = await repo.get_route(route_id)

    await message.answer(
        f"✅ <b>Скрытый пункт назначения успешно установлен!</b>\n"
        f"Маршрут #{route_id} теперь дублирует сообщения в <code>{shadow_id}</code>.",
        reply_markup=route_detail_kb(route, is_admin=is_admin) if route else main_menu_kb(is_admin=True),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("shadow_clear:"))
async def cb_shadow_clear(callback: CallbackQuery, db: Database, is_admin: bool = False) -> None:
    if not is_admin:
        await callback.answer("Только для администраторов.", show_alert=True)
        return
    await callback.answer("Скрытый чат удалён.", show_alert=True)
    route_id = int(callback.data.split(":")[1])
    async with db.connect() as conn:
        repo = RouteRepository(conn)
        await repo.set_shadow_destination(route_id, None)
        route = await repo.get_route(route_id)

    if route:
        await callback.message.edit_text(
            render_route_card(route),
            reply_markup=route_detail_kb(route, is_admin=is_admin),
            parse_mode="HTML",
        )
