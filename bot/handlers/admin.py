from __future__ import annotations

import logging
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from config.settings import Settings
from database.connection import Database
from database.repositories.chat_repo import ChatRepository
from database.repositories.forward_repo import ForwardRepository
from database.repositories.profile_repo import ProfileRepository
from database.repositories.route_repo import RouteRepository
from database.repositories.user_repo import UserRepository
from forwarder.queue import ForwardQueue
from database.repositories.config_repo import ConfigRepository
from moderation.llm_client import LLMClient
from moderation.profanity import ProfanityDetector
from bot.keyboards.inline import (
    status_menu_kb,
    stt_settings_kb,
    stt_transcribe_kb,
    admin_panel_kb,
    all_routes_kb,
    chat_moderation_detail_kb,
    llm_base_urls_select_kb,
    llm_cancel_kb,
    llm_context_select_kb,
    llm_models_select_kb,
    llm_settings_kb,
    llm_temp_select_kb,
    llm_tokens_select_kb,
    mod_custom_words_kb,
    mod_strictness_select_kb,
    mod_whitelist_kb,
    mod_history_kb,
    llm_random_select_kb,
    mod_participants_list_kb,
    mod_user_history_kb,
    llm_persona_select_kb,
    llm_trigger_select_kb,
    main_menu_kb,
    moderation_chats_list_kb,
    password_management_kb,
    user_card_kb,
    users_list_kb,
)

logger = logging.getLogger(__name__)
router = Router(name="admin_router")


class AdminPasswordStates(StatesGroup):
    waiting_for_new_password = State()


@router.message(Command("start"))
async def cmd_start(message: Message, is_admin: bool = False) -> None:
    role_badge = "👑 <b>Администратор</b>" if is_admin else "👤 <b>Пользователь</b>"
    user_name = message.from_user.first_name if message.from_user else "пользователь"
    div = "━━━━━━━━━━━━━━━━━━━━━━"

    text = (
        f"👋 <b>Добро пожаловать, {user_name}!</b> [{role_badge}]\n"
        f"{div}\n"
        "<b>Возможности системы:</b>\n"
        "• 🔀 <b>Маршруты:</b> пересылка, фильтрация медиа и очистка текста\n"
        "• 🛡️ <b>Модерация:</b> защита чатов от мата и автопредупреждения\n"
        "• 💬 <b>ИИ-Собеседник:</b> общение по тегу или ответу (Reply)\n"
        "• 📊 <b>Стилометрия:</b> анализ стиля речи в подключенных группах\n"
        f"{div}\n"
        "👇 <i>Используйте кнопки меню ниже для навигации:</i>"
    )
    await message.answer(text, reply_markup=main_menu_kb(is_admin=is_admin), parse_mode="HTML")


@router.message(Command("help"))
async def cmd_help(message: Message, is_admin: bool = False) -> None:
    lines = [
        "📖 <b>Справочник возможностей</b>\n",
        "<b>Маршруты и пересылка:</b>",
        "• /routes — список ваших маршрутов и их тонкая настройка",
        "• /sources — подключенные чаты-источники",
        "• /destinations — чаты-назначения (куда пересылать)\n",
        "<b>Анализ стиля (Стилометрия):</b>",
        "• /profile — ваш детальный лингвистический портрет",
        "• /compare &lt;текст&gt; — сравнение текста с вашим базовым стилем",
        "• /mimic — правила написания текстов в вашей тональности\n",
        "<b>Приватность:</b>",
        "• /privacy — настройки хранения и исключений",
        "• /delete_data — удаление вашего профиля стиля\n",
    ]

    if is_admin:
        lines.extend([
            "👑 <b>Команды Супер-Администратора:</b>",
            "• /admin — главная панель управления",
            "• /users — управление пользователями и аккаунтами",
            "• /password — настройка и смена пароля доступа",
            "• /moderation — модерация матов и предупреждения нарушителей",
            "• /llm — настройка ИИ (модель, API-ключ, URL/IP)",
            "• /all_routes — просмотр всех маршрутов всех пользователей",
            "• /all_chats — просмотр всех каналов и групп бота",
            "• /status — статус очередей, пауза и статистика",
        ])

    await message.answer("\n".join(lines), parse_mode="HTML")


@router.message(Command("admin"))
@router.callback_query(F.data == "nav_admin")
async def cmd_admin_panel(event: Message | CallbackQuery, db: Database, settings: Settings, is_admin: bool = False, is_subadmin: bool = False) -> None:
    if not is_admin:
        if isinstance(event, CallbackQuery):
            await event.answer("⛔ Доступ разрешён только администраторам.", show_alert=True)
        else:
            await event.answer("⛔ <b>Доступ запрещён.</b>", parse_mode="HTML")
        return

    async with db.connect() as conn:
        user_repo = UserRepository(conn)
        route_repo = RouteRepository(conn)
        chat_repo = ChatRepository(conn)

        users_cnt = len(await user_repo.list_users(limit=500))
        routes_cnt = len(await route_repo.list_routes())
        chats_cnt = len(await chat_repo.list_all())
        pw_req = await user_repo.is_password_required(settings.PASSWORD_REQUIRED)

    pw_status = "🟢 Включен" if pw_req else "⚪ Отключен"
    div = "━━━━━━━━━━━━━━━━━━━━━━"

    if is_subadmin:
        text = (
            f"🛡️ <b>Панель Младшего Администратора</b>\n{div}\n"
            f"• 👥 <b>Пользователей в системе:</b> <code>{users_cnt}</code>\n"
            f"• 🔀 <b>Доступных маршрутов:</b> <code>{routes_cnt}</code>\n"
            f"• 📡 <b>Подключенных чатов:</b> <code>{chats_cnt}</code>\n{div}\n"
            "👇 <i>Вам доступно управление чатами, модерацией, ИИ и аналитикой:</i>"
        )
    else:
        text = (
            f"👑 <b>Панель Администратора</b>\n{div}\n"
            f"• 👥 <b>Пользователей в системе:</b> <code>{users_cnt}</code>\n"
            f"• 🔀 <b>Всего маршрутов:</b> <code>{routes_cnt}</code> <i>(все авторы)</i>\n"
            f"• 📡 <b>Подключенных чатов:</b> <code>{chats_cnt}</code>\n"
            f"• 🔑 <b>Пароль доступа:</b> {pw_status}\n{div}\n"
            "👇 <i>Выберите нужный раздел для управления:</i>"
        )

    kb = admin_panel_kb(is_subadmin=is_subadmin)
    if isinstance(event, Message):
        await event.answer(text, reply_markup=kb, parse_mode="HTML")
    else:
        await event.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
        await event.answer()


@router.message(Command("users"))
@router.callback_query(F.data == "admin_users")
async def cmd_admin_users(event: Message | CallbackQuery, db: Database, is_admin: bool = False) -> None:
    if not is_admin:
        return

    async with db.connect() as conn:
        user_repo = UserRepository(conn)
        users = await user_repo.list_users(limit=100)

    text = (
        f"👥 <b>Управление пользователями ({len(users)}):</b>\n\n"
        "Нажмите на пользователя для просмотра деталей, блокировки или выдачи прав:"
    )

    kb = users_list_kb(users)
    if isinstance(event, Message):
        await event.answer(text, reply_markup=kb, parse_mode="HTML")
    else:
        await event.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
        await event.answer()


@router.callback_query(F.data.startswith("user_view:"))
async def cb_user_view(callback: CallbackQuery, db: Database, settings: Settings, is_admin: bool = False, is_subadmin: bool = False) -> None:
    if not is_admin:
        return
    await callback.answer()
    target_id = int(callback.data.split(":")[1])

    async with db.connect() as conn:
        user_repo = UserRepository(conn)
        route_repo = RouteRepository(conn)
        target = await user_repo.get_user(target_id)
        routes = await route_repo.list_routes(user_id=target_id)

    if not target:
        await callback.message.edit_text("❌ Пользователь не найден.", reply_markup=admin_panel_kb())
        return

    status_str = "🚫 <b>Заблокирован</b>" if target.get("is_blocked") else ("🟢 <b>Авторизован</b>" if target.get("is_authorized") else "🔒 <b>Не авторизован (гость)</b>")
    role_str = "👑 <b>Владелец</b>" if target.get("role") == "owner" else ("⭐ <b>Администратор</b>" if target.get("role") == "admin" else "👤 <b>Пользователь</b>")
    user_handle = f"@{target['username']}" if target.get("username") else "отсутствует"

    text = (
        f"👤 <b>Карточка пользователя:</b>\n\n"
        f"• Имя: <b>{target.get('first_name', '')} {target.get('last_name', '') or ''}</b>\n"
        f"• Telegram ID: <code>{target['user_id']}</code>\n"
        f"• Юзернейм: {user_handle}\n"
        f"• Роль: {role_str}\n"
        f"• Статус доступа: {status_str}\n"
        f"• Создано маршрутов: <b>{len(routes)}</b>\n"
        f"• Дата регистрации: <code>{target.get('created_at', '')[:19]}</code>"
    )

    caller_id = callback.from_user.id if callback.from_user else 0
    is_owner_target = (target.get("role") == "owner" or target_id == settings.OWNER_ID)
    is_self = (target_id == caller_id)
    await callback.message.edit_text(
        text,
        reply_markup=user_card_kb(target, is_owner=is_owner_target, is_self=is_self, is_subadmin=is_subadmin),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("user_block:"))
async def cb_user_block(callback: CallbackQuery, db: Database, settings: Settings, is_admin: bool = False, is_subadmin: bool = False) -> None:
    if not is_admin:
        return
    target_id = int(callback.data.split(":")[1])
    if target_id == settings.OWNER_ID or target_id == callback.from_user.id:
        await callback.answer("⛔ Нельзя заблокировать главного владельца или самого себя!", show_alert=True)
        return

    if is_subadmin:
        async with db.connect() as conn:
            target_u = await UserRepository(conn).get_user(target_id)
        if target_u and target_u.get("role") in ("owner", "admin", "subadmin"):
            await callback.answer("⛔ Младший администратор не может блокировать администрацию!", show_alert=True)
            return
    async with db.connect() as conn:
        user_repo = UserRepository(conn)
        await user_repo.set_blocked(target_id, True)

    await callback.answer("🚫 Пользователь заблокирован!", show_alert=True)
    await cb_user_view(callback, db, settings=settings, is_admin=True, is_subadmin=is_subadmin)


@router.callback_query(F.data.startswith("user_unblock:"))
async def cb_user_unblock(callback: CallbackQuery, db: Database, settings: Settings, is_admin: bool = False, is_subadmin: bool = False) -> None:
    if not is_admin:
        return
    target_id = int(callback.data.split(":")[1])
    async with db.connect() as conn:
        user_repo = UserRepository(conn)
        await user_repo.set_blocked(target_id, False)

    await callback.answer("✅ Пользователь разблокирован!", show_alert=True)
    await cb_user_view(callback, db, settings=settings, is_admin=True, is_subadmin=is_subadmin)


@router.callback_query(F.data.startswith("user_role:"))
async def cb_user_role(callback: CallbackQuery, db: Database, settings: Settings, is_admin: bool = False, is_subadmin: bool = False) -> None:
    if not is_admin or is_subadmin:
        await callback.answer("⛔ Изменение ролей доступно только старшему администратору.", show_alert=True)
        return
    parts = callback.data.split(":")
    target_id = int(parts[1])
    new_role = parts[2]

    async with db.connect() as conn:
        user_repo = UserRepository(conn)
        await user_repo.set_role(target_id, new_role)

    await callback.answer(f"Роль изменена на: {new_role}!", show_alert=True)
    await cb_user_view(callback, db, settings=settings, is_admin=True, is_subadmin=is_subadmin)


@router.callback_query(F.data.startswith("user_reset_auth:"))
async def cb_user_reset_auth(callback: CallbackQuery, db: Database, settings: Settings, is_admin: bool = False, is_subadmin: bool = False) -> None:
    if not is_admin:
        return
    target_id = int(callback.data.split(":")[1])
    if target_id == settings.OWNER_ID or target_id == callback.from_user.id:
        await callback.answer("⛔ Нельзя сбросить авторизацию владельца!", show_alert=True)
        return
    async with db.connect() as conn:
        user_repo = UserRepository(conn)
        await user_repo.set_authorized(target_id, False)

    await callback.answer("🔑 Авторизация сброшена. Пользователь должен ввести пароль повторно.", show_alert=True)
    await cb_user_view(callback, db, settings=settings, is_admin=True, is_subadmin=is_subadmin)


@router.message(Command("all_routes"))
@router.callback_query(F.data == "admin_all_routes")
async def cmd_admin_all_routes(event: Message | CallbackQuery, db: Database, is_admin: bool = False, is_subadmin: bool = False) -> None:
    if not is_admin or is_subadmin:
        if isinstance(event, CallbackQuery):
            await event.answer("⛔ Доступ разрешён только главному администратору.", show_alert=True)
        return

    async with db.connect() as conn:
        repo = RouteRepository(conn)
        routes = await repo.list_routes()

    text = f"🌐 <b>Все маршруты системы ({len(routes)}):</b>\n\n"
    if not routes:
        text += "В системе пока нет активных маршрутов."

    kb = all_routes_kb(routes)
    if isinstance(event, Message):
        await event.answer(text, reply_markup=kb, parse_mode="HTML")
    else:
        await event.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
        await event.answer()


@router.message(Command("all_chats"))
@router.callback_query(F.data == "admin_all_chats")
async def cmd_admin_all_chats(event: Message | CallbackQuery, db: Database, is_admin: bool = False, is_subadmin: bool = False) -> None:
    if not is_admin or is_subadmin:
        if isinstance(event, CallbackQuery):
            await event.answer("⛔ Доступ разрешён только главному администратору.", show_alert=True)
        return

    async with db.connect() as conn:
        repo = ChatRepository(conn)
        chats = await repo.list_all()

    lines = [f"📡 <b>Все подключенные чаты бота ({len(chats)}):</b>\n"]
    if not chats:
        lines.append("Бот пока не добавлен ни в один чат.")
    else:
        for c in chats:
            roles = []
            if c.get("is_source"):
                roles.append("Источник")
            if c.get("is_destination"):
                roles.append("Назначение")
            roles_str = f" [{', '.join(roles)}]" if roles else ""
            user_part = f" (@{c['username']})" if c.get("username") else ""
            lines.append(f"• <b>{c['title']}</b>{user_part} [<code>{c['chat_id']}</code>, {c['chat_type']}]{roles_str}")

    text = "\n".join(lines)
    if isinstance(event, Message):
        await event.answer(text, reply_markup=admin_panel_kb(), parse_mode="HTML")
    else:
        await event.message.edit_text(text, reply_markup=admin_panel_kb(), parse_mode="HTML")
        await event.answer()


@router.message(Command("password"))
@router.callback_query(F.data == "admin_password")
async def cmd_admin_password(event: Message | CallbackQuery, db: Database, settings: Settings, is_admin: bool = False, is_subadmin: bool = False) -> None:
    if not is_admin or is_subadmin:
        if isinstance(event, CallbackQuery):
            await event.answer("⛔ Управление паролем доступа доступно только главному администратору.", show_alert=True)
        return
        return

    async with db.connect() as conn:
        user_repo = UserRepository(conn)
        current_pw = await user_repo.get_access_password(settings.ACCESS_PASSWORD)
        pw_req = await user_repo.is_password_required(settings.PASSWORD_REQUIRED)

    status_str = "🟢 <b>Включена</b> (новые пользователи обязаны ввести пароль)" if pw_req else "⚪ <b>Отключена</b> (свободный вход)"

    text = (
        "🔑 <b>Управление паролем доступа к боту</b>\n\n"
        f"• Действующий пароль: <code>{current_pw}</code>\n"
        f"• Защита паролем: {status_str}\n\n"
        "Вы можете изменить пароль или переключить режим проверки кнопками ниже:"
    )

    kb = password_management_kb(pw_req)
    if isinstance(event, Message):
        await event.answer(text, reply_markup=kb, parse_mode="HTML")
    else:
        await event.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
        await event.answer()


@router.callback_query(F.data == "admin_toggle_pw_req")
async def cb_admin_toggle_pw_req(callback: CallbackQuery, db: Database, settings: Settings, is_admin: bool = False, is_subadmin: bool = False) -> None:
    if not is_admin or is_subadmin:
        await callback.answer("⛔ Доступ разрешён только главному администратору.", show_alert=True)
        return
        return
    await callback.answer()

    async with db.connect() as conn:
        user_repo = UserRepository(conn)
        current_req = await user_repo.is_password_required(settings.PASSWORD_REQUIRED)
        new_req = not current_req
        await user_repo.set_password_required(new_req)

    await cmd_admin_password(callback, db, settings, is_admin=True)


@router.callback_query(F.data == "admin_change_pw")
async def cb_admin_change_pw_prompt(callback: CallbackQuery, state: FSMContext, is_admin: bool = False) -> None:
    if not is_admin:
        return
    await callback.answer()
    await state.set_state(AdminPasswordStates.waiting_for_new_password)

    await callback.message.answer(
        "✏️ <b>Введите новый пароль для доступа к боту:</b>\n"
        "<i>(Пароль может содержать буквы, цифры или символы)</i>",
        parse_mode="HTML",
    )


@router.message(AdminPasswordStates.waiting_for_new_password)
async def state_save_new_password(message: Message, state: FSMContext, db: Database, settings: Settings, is_admin: bool = False) -> None:
    if not is_admin:
        return
    new_pw = message.text.strip()
    await state.clear()

    if not new_pw or len(new_pw) < 2:
        await message.answer("❌ Пароль слишком короткий. Попробуйте снова через /password")
        return

    async with db.connect() as conn:
        user_repo = UserRepository(conn)
        await user_repo.set_access_password(new_pw)

    await message.answer(
        f"✅ <b>Пароль успешно обновлён!</b>\n\nНовый пароль доступа: <code>{new_pw}</code>",
        reply_markup=admin_panel_kb(),
        parse_mode="HTML",
    )


@router.message(Command("status"))
@router.callback_query(F.data == "nav_status")
async def cmd_status(
    event: Message | CallbackQuery,
    db: Database,
    queue: ForwardQueue,
    is_admin: bool = False,
    is_subadmin: bool = False,
) -> None:
    if not is_admin or is_subadmin:
        if isinstance(event, CallbackQuery):
            await event.answer("⛔ Доступ к статусу системы разрешён только главному администратору.", show_alert=True)
        return
    async with db.connect() as conn:
        profile_repo = ProfileRepository(conn)
        route_repo = RouteRepository(conn)
        forward_repo = ForwardRepository(conn)
        user_repo = UserRepository(conn)

        is_paused = await profile_repo.is_system_paused()
        routes = await route_repo.list_routes()
        active_routes_cnt = sum(1 for r in routes if r.get("is_active"))
        stats = await forward_repo.get_stats()
        users_cnt = len(await user_repo.list_users(limit=500))

    status_str = "⏸️ <b>ПРИОСТАНОВЛЕНО</b>" if is_paused else "🟢 <b>АКТИВНО РАБОТАЕТ</b>"
    queue_len = queue.queue.qsize()
    div = "━━━━━━━━━━━━━━━━━━━━━━"

    text = (
        f"⚙️ <b>Состояние системы</b>\n{div}\n"
        f"• ⚡ <b>Режим работы:</b> {status_str}\n"
        f"• 👥 <b>Пользователей:</b> <code>{users_cnt}</code>\n"
        f"• 🔀 <b>Маршрутов:</b> <code>{active_routes_cnt}</code> активных <i>(всего: {len(routes)})</i>\n"
        f"• 📬 <b>Очередь сообщений:</b> <code>{queue_len}</code> в ожидании\n{div}\n"
        "📈 <b>Статистика пересылки (Forward Logs):</b>\n"
        f"• ✅ Успешно доставлено: <code>{stats.get('SENT', 0)}</code>\n"
        f"• 🔍 Отфильтровано: <code>{stats.get('FILTERED', 0)}</code>\n"
        f"• ❌ Ошибок отправки: <code>{stats.get('FAILED', 0)}</code>\n"
        f"• 📊 Всего обработано: <code>{stats.get('TOTAL', 0)}</code>"
    )

    if is_admin:
        kb = status_menu_kb(is_paused=is_paused, is_subadmin=is_subadmin)
    else:
        kb = main_menu_kb(is_admin=False, is_subadmin=False)

    if isinstance(event, Message):
        await event.answer(text, reply_markup=kb, parse_mode="HTML")
    else:
        await event.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
        await event.answer()


@router.callback_query(F.data == "admin_toggle_pause")
async def cb_admin_toggle_pause(
    callback: CallbackQuery,
    db: Database,
    queue: ForwardQueue,
    is_admin: bool = False,
    is_subadmin: bool = False,
) -> None:
    if not is_admin or is_subadmin:
        await callback.answer("⛔ Доступ разрешён только главному администратору.", show_alert=True)
        return
        await callback.answer("⛔ Доступ разрешён только администраторам.", show_alert=True)
        return

    async with db.connect() as conn:
        repo = ProfileRepository(conn)
        curr = await repo.is_system_paused()
        new_paused = not curr
        await repo.set_system_paused(new_paused)

    alert_text = "⏸️ Система приостановлена" if new_paused else "▶️ Система запущена"
    await callback.answer(alert_text)
    await cmd_status(callback, db, queue, is_admin=is_admin, is_subadmin=is_subadmin)


@router.callback_query(F.data == "nav_main")
async def cb_main_menu(callback: CallbackQuery, is_admin: bool = False) -> None:
    await callback.message.edit_text(
        "Главная панель управления:",
        reply_markup=main_menu_kb(is_admin=is_admin),
    )
    await callback.answer()

@router.message(Command("moderation"))
async def cmd_admin_moderation_chats(event: Message | CallbackQuery, db: Database, is_admin: bool = False) -> None:
    if not is_admin:
        if isinstance(event, CallbackQuery):
            await event.answer("⚠️ Доступ разрешен только администраторам.", show_alert=True)
        return

    async with db.connect() as conn:
        chat_repo = ChatRepository(conn)
        chats = await chat_repo.list_moderation_chats()

    lines = [
        "🛡️ <b>Модерация ненормативной лексики (ИИ и фильтры)</b>\n",
        "Выберите группу или супергруппу для настройки параметров модерации:",
        "• 🟢 — фильтр матов включен (гибридный анализ: регулярные шаблоны + нейросеть)",
        "• ⚠️ — отправка предупреждений нарушителям в чате",
        "• 🗑️ — автоматическое удаление нецензурных сообщений\n",
        f"Всего групп и каналов в системе: <b>{len(chats)}</b>",
    ]
    text = "\n".join(lines)
    kb = moderation_chats_list_kb(chats)
    if isinstance(event, CallbackQuery):
        await event.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
        await event.answer()
    else:
        await event.answer(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data == "admin_moderation_chats")
async def cb_admin_moderation_chats(callback: CallbackQuery, db: Database, is_admin: bool = False) -> None:
    await cmd_admin_moderation_chats(callback, db=db, is_admin=is_admin)


@router.callback_query(F.data.startswith("mod_chat_view:"))
async def cb_chat_moderation_view(callback: CallbackQuery, db: Database, is_admin: bool = False) -> None:
    if not is_admin:
        await callback.answer("⚠️ Доступ только для администраторов.", show_alert=True)
        return

    chat_id = int(callback.data.split(":")[1])
    async with db.connect() as conn:
        chat_repo = ChatRepository(conn)
        chat = await chat_repo.get_chat(chat_id)

    if not chat:
        await callback.answer("❌ Чат не найден в базе.", show_alert=True)
        return

    title = chat.get("title") or f"ID {chat_id}"
    c_type = chat.get("chat_type", "group")
    import json
    f_on = "🟢 ВКЛ" if chat.get("profanity_filter_enabled") else "⚪ ВЫКЛ"
    w_on = "🟢 ВКЛ" if chat.get("profanity_warn_enabled") else "⚪ ВЫКЛ"
    d_on = "🟢 ВКЛ" if chat.get("profanity_delete_enabled") else "⚪ ВЫКЛ"
    a_on = "🟢 ВКЛ" if chat.get("chat_ai_enabled") else "⚪ ВЫКЛ"

    strictness = chat.get("profanity_strictness", "hard")
    strict_labels = {
        "hard": "🤬 Только жесткий мат",
        "medium": "⚠️ Жесткий мат + грубые слова",
        "all": "🛑 Максимальная (+ любая брань)",
    }
    strict_desc = strict_labels.get(strictness, "🤬 Только жесткий мат")

    warn_sec = int(chat.get("profanity_delete_warn_seconds", 0))
    warn_sec_str = "Не удалять" if warn_sec == 0 else f"{warn_sec} сек."

    auto_mute = int(chat.get("auto_mute_duration", 0))
    auto_mute_str = "Выключено" if auto_mute == 0 else (f"{auto_mute // 60} мин." if auto_mute < 3600 else f"{auto_mute // 3600} ч.")

    raw_cw = chat.get("custom_profanity_words", "[]")
    raw_wl = chat.get("custom_whitelist_words", "[]")
    try:
        c_words = json.loads(raw_cw) if isinstance(raw_cw, str) else (raw_cw or [])
    except Exception:
        c_words = []
    try:
        w_words = json.loads(raw_wl) if isinstance(raw_wl, str) else (raw_wl or [])
    except Exception:
        w_words = []

    cw_desc = f"{len(c_words)} шт." if c_words else "<i>(нет)</i>"
    wl_desc = f"{len(w_words)} шт." if w_words else "<i>(нет)</i>"

    lines = [
        f"🛡️ <b>Настройки модерации и чата #{chat_id}</b>",
        "━━━━━━━━━━━━━━━━━━━━━━",
        f"• 🏷️ <b>Название:</b> <b>{title}</b>",
        f"• 🆔 <b>ID чата:</b> <code>{chat_id}</code>",
        f"• 📂 <b>Тип:</b> {c_type}",
        "━━━━━━━━━━━━━━━━━━━━━━",
        "⚙️ <b>Параметры фильтрации:</b>",
        f"• 🎯 <b>Строгость мата:</b> <b>{strict_desc}</b>",
        f"• 🗑️ <b>Удаление сообщений:</b> {d_on}",
        f"• ⚠️ <b>Предупреждать нарушителя:</b> {w_on}",
        f"• ⏱️ <b>Автоудаление предупреждения:</b> <b>{warn_sec_str}</b>",
        f"• 🔇 <b>Авто-мут при 3 нарушениях:</b> <b>{auto_mute_str}</b>",
        f"• 📝 <b>Черный список (стоп-слова):</b> {cw_desc}",
        f"• ⚪ <b>Белый список (исключения):</b> {wl_desc}",
        "━━━━━━━━━━━━━━━━━━━━━━",
        "🤖 <b>ИИ Собеседник (Ричард):</b>",
        f"• 💬 <b>Общение в чате:</b> {a_on}",
        "━━━━━━━━━━━━━━━━━━━━━━",
        "🎙️ <b>Распознавание речи (NVIDIA Whisper):</b>",
        f"• 🗣️ <b>Голосовые и видео-кружки:</b> {'🟢 Включено' if chat.get('stt_enabled', 1) else '⚪ Выключено'}",
        f"• 📝 <b>Авто-расшифровка в чат:</b> {'🟢 Включена' if chat.get('stt_auto_transcribe', 0) else '⚪ Выключена'}",
        "━━━━━━━━━━━━━━━━━━━━━━",
        "💡 <i>Используйте кнопки ниже для переключения опций:</i>",
    ]
    await callback.message.edit_text("\n".join(lines), reply_markup=chat_moderation_detail_kb(chat), parse_mode="HTML")


@router.callback_query(F.data.startswith("mod_toggle:"))
async def cb_chat_moderation_toggle(callback: CallbackQuery, db: Database, is_admin: bool = False) -> None:
    if not is_admin:
        await callback.answer("⚠️ Доступ только для администраторов.", show_alert=True)
        return

    parts = callback.data.split(":")
    chat_id = int(parts[1])
    field_name = parts[2]

    async with db.connect() as conn:
        chat_repo = ChatRepository(conn)
        await chat_repo.toggle_setting(chat_id, field_name)

    await callback.answer("✅ Настройка обновлена")
    await cb_chat_moderation_view(callback, db, is_admin=is_admin)


class AdminLLMStates(StatesGroup):
    waiting_for_custom_persona = State()
    waiting_for_api_key = State()
    waiting_for_model = State()
    waiting_for_base_url = State()
    waiting_for_context = State()
    waiting_for_tokens = State()
    waiting_for_random_chance = State()


class AdminSTTStates(StatesGroup):
    waiting_for_api_key = State()


class AdminModStates(StatesGroup):
    waiting_for_custom_words = State()
    waiting_for_whitelist_words = State()


async def _render_llm_settings(conn, settings: Settings, is_subadmin: bool = False) -> tuple[str, bool, dict]:
    config_repo = ConfigRepository(conn)
    conf = await config_repo.get_llm_config(
        default_enabled=settings.LLM_ENABLED,
        default_api_key=settings.LLM_API_KEY,
        default_base_url=settings.LLM_BASE_URL,
        default_model=settings.LLM_MODEL,
    )
    is_on = conf["llm_enabled"]
    raw_key = conf["llm_api_key"]
    if len(raw_key) > 10:
        key_masked = f"<code>{raw_key[:5]}...{raw_key[-4:]}</code>"
    elif raw_key:
        key_masked = "<i>(установлен)</i>"
    else:
        key_masked = "❌ <i>Не установлен</i>"

    status_str = "🟢 <b>АКТИВЕН</b>" if is_on else "⚪ <b>ОТКЛЮЧЕН</b>"
    div = "━━━━━━━━━━━━━━━━━━━━━━"

    ctx = conf.get("companion_context_limit", 15)
    toks = conf.get("companion_max_tokens", 800)
    temp = conf.get("companion_temperature", 0.7)
    persona = conf.get("companion_persona", "student")
    persona_map = {
        "student": "🎓 Студент-сокурсник",
        "expert": "💼 Деловой эксперт",
        "sarcastic": "😈 Дерзкий / Остроумный",
        "concise": "⚡ Краткий / По делу",
        "custom": "✍️ Свой системный промпт",
    }
    persona_str = persona_map.get(persona, "🎓 Студент-сокурсник")

    trigger = conf.get("companion_trigger_mode", "name_and_reply")
    trigger_str = "🗣️ Имя («Ричард») + Реплай" if trigger == "name_and_reply" else "📢 Все упоминания"

    typing_on = conf.get("companion_typing_indicator", True)
    typing_str = "🟢 ВКЛ" if typing_on else "⚪ ВЫКЛ"

    rand_chance = conf.get("companion_random_reply_chance", 0)
    rand_str = "Выключено" if rand_chance == 0 else f"{rand_chance}%"

    if is_subadmin:
        top_lines = [
            "🤖 <b>Панель управления ИИ (Ричард)</b>",
            div,
            f"• ⚡ <b>Статус ИИ:</b> {status_str}",
            f"• 🧠 <b>Модель:</b> <code>{conf['llm_model']}</code>",
            "• 🌐 <b>Сервер нейросети:</b> 🟢 Подключен",
            div,
        ]
    else:
        top_lines = [
            "🤖 <b>Панель управления ИИ (Ричард & LLM)</b>",
            div,
            f"• ⚡ <b>Статус ИИ:</b> {status_str}",
            f"• 🧠 <b>Модель:</b> <code>{conf['llm_model']}</code>",
            f"• 🌐 <b>Эндпоинт (URL/IP):</b> <code>{conf['llm_base_url']}</code>",
            f"• 🔑 <b>API-ключ:</b> {key_masked}",
            div,
        ]

    lines = top_lines + [
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
    ]
    return "\n".join(lines), is_on, conf


@router.message(Command("llm"))
@router.callback_query(F.data == "admin_llm_settings")
async def cmd_admin_llm_settings(
    event: Message | CallbackQuery,
    db: Database,
    settings: Settings,
    is_admin: bool = False,
    is_subadmin: bool = False,
    state: Optional[FSMContext] = None,
) -> None:
    if not is_admin:
        if isinstance(event, CallbackQuery):
            await event.answer("⚠️ Доступ только для администраторов.", show_alert=True)
        return

    if state:
        await state.clear()

    async with db.connect() as conn:
        text, is_on, conf = await _render_llm_settings(conn, settings, is_subadmin=is_subadmin)

    kb = llm_settings_kb(is_on, conf, is_subadmin=is_subadmin)
    if isinstance(event, CallbackQuery):
        await event.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
        await event.answer()
    else:
        await event.answer(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data == "llm_toggle_enabled")
async def cb_llm_toggle_enabled(
    callback: CallbackQuery,
    db: Database,
    settings: Settings,
    profanity_detector: ProfanityDetector,
    is_admin: bool = False,
) -> None:
    if not is_admin:
        await callback.answer("⚠️ Доступ только для администраторов.", show_alert=True)
        return

    async with db.connect() as conn:
        config_repo = ConfigRepository(conn)
        curr = await config_repo.get_llm_config(default_enabled=settings.LLM_ENABLED)
        new_val = not curr["llm_enabled"]
        await config_repo.set_llm_config(enabled=new_val)
        text, is_on, conf = await _render_llm_settings(conn, settings)

    profanity_detector.set_llm_enabled(new_val)
    await callback.message.edit_text(text, reply_markup=llm_settings_kb(is_on, conf), parse_mode="HTML")
    state_desc = "включен" if new_val else "отключен"
    await callback.answer(f"ИИ {state_desc}")


@router.callback_query(F.data == "llm_set_key")
async def cb_llm_set_key(callback: CallbackQuery, state: FSMContext, is_admin: bool = False, is_subadmin: bool = False) -> None:
    if not is_admin or is_subadmin:
        await callback.answer("⛔ Доступ к API-ключам разрешён только старшему администратору.", show_alert=True)
        return
        await callback.answer("⚠️ Доступ только для администраторов.", show_alert=True)
        return

    await state.set_state(AdminLLMStates.waiting_for_api_key)
    lines = [
        "🔑 <b>Ввод нового API-ключа</b>\n",
        "Отправьте ваш API-ключ сообщением в этот чат (например <code>sk-proj-...</code> для OpenAI или ключ Google AI Studio).",
        "<i>В целях безопасности ваше сообщение с ключом будет сразу удалено после сохранения.</i>",
    ]
    await callback.message.edit_text("\n".join(lines), reply_markup=llm_cancel_kb(), parse_mode="HTML")
    await callback.answer()


@router.message(AdminLLMStates.waiting_for_api_key)
async def proc_admin_llm_api_key(
    message: Message,
    state: FSMContext,
    db: Database,
    settings: Settings,
    llm_client: LLMClient,
    is_admin: bool = False,
) -> None:
    if not is_admin:
        return

    new_key = message.text.strip() if message.text else ""
    await state.clear()

    try:
        await message.delete()
    except Exception:
        pass

    if not new_key or len(new_key) < 5:
        await message.answer("❌ Ключ слишком короткий или пустой. Попробуйте снова через /llm", reply_markup=admin_panel_kb())
        return

    async with db.connect() as conn:
        config_repo = ConfigRepository(conn)
        await config_repo.set_llm_config(api_key=new_key)
        text, is_on, conf = await _render_llm_settings(conn, settings)

    llm_client.update_config(api_key=new_key)
    await message.answer(f"✅ <b>API-ключ успешно обновлен и сохранён!</b>\n\n{text}", reply_markup=llm_settings_kb(is_on, conf), parse_mode="HTML")


@router.callback_query(F.data == "llm_select_model")
async def cb_llm_select_model(callback: CallbackQuery, is_admin: bool = False) -> None:
    if not is_admin:
        await callback.answer("⚠️ Доступ только для администраторов.", show_alert=True)
        return

    lines = [
        "🧠 <b>Выбор модели ИИ</b>\n",
        "Выберите готовую модель из списка или введите точное название вручную:",
    ]
    await callback.message.edit_text("\n".join(lines), reply_markup=llm_models_select_kb(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("llm_preset_model:"))
async def cb_llm_preset_model(
    callback: CallbackQuery,
    db: Database,
    settings: Settings,
    llm_client: LLMClient,
    is_admin: bool = False,
) -> None:
    if not is_admin:
        await callback.answer("⚠️ Доступ только для администраторов.", show_alert=True)
        return

    model_name = callback.data.split(":", 1)[1]
    async with db.connect() as conn:
        config_repo = ConfigRepository(conn)
        await config_repo.set_llm_config(model=model_name)
        text, is_on, conf = await _render_llm_settings(conn, settings)

    llm_client.update_config(model=model_name)
    await callback.message.edit_text(text, reply_markup=llm_settings_kb(is_on, conf), parse_mode="HTML")
    await callback.answer(f"Модель изменена на {model_name}")


@router.callback_query(F.data == "llm_custom_model")
async def cb_llm_custom_model(callback: CallbackQuery, state: FSMContext, is_admin: bool = False) -> None:
    if not is_admin:
        await callback.answer("⚠️ Доступ только для администраторов.", show_alert=True)
        return

    await state.set_state(AdminLLMStates.waiting_for_model)
    lines = [
        "✏️ <b>Ручной ввод названия модели</b>\n",
        "Отправьте сообщением название модели (например, <code>gpt-4o</code>, <code>claude-3-haiku</code>, <code>llama3.1</code>):",
    ]
    await callback.message.edit_text("\n".join(lines), reply_markup=llm_cancel_kb(), parse_mode="HTML")
    await callback.answer()


@router.message(AdminLLMStates.waiting_for_model)
async def proc_admin_llm_custom_model(
    message: Message,
    state: FSMContext,
    db: Database,
    settings: Settings,
    llm_client: LLMClient,
    is_admin: bool = False,
) -> None:
    if not is_admin:
        return

    model_name = message.text.strip() if message.text else ""
    await state.clear()

    if not model_name:
        await message.answer("❌ Название модели не может быть пустым.", reply_markup=admin_panel_kb())
        return

    async with db.connect() as conn:
        config_repo = ConfigRepository(conn)
        await config_repo.set_llm_config(model=model_name)
        text, is_on, conf = await _render_llm_settings(conn, settings)

    llm_client.update_config(model=model_name)
    await message.answer(f"✅ <b>Модель установлена:</b> <code>{model_name}</code>\n\n{text}", reply_markup=llm_settings_kb(is_on, conf), parse_mode="HTML")


@router.callback_query(F.data == "llm_select_url")
async def cb_llm_select_url(callback: CallbackQuery, is_admin: bool = False, is_subadmin: bool = False) -> None:
    if not is_admin or is_subadmin:
        await callback.answer("⛔ Доступ к эндпоинтам серверов разрешён только старшему администратору.", show_alert=True)
        return
        await callback.answer("⚠️ Доступ только для администраторов.", show_alert=True)
        return

    lines = [
        "🌐 <b>Выбор Base URL / IP адреса сервера</b>\n",
        "Выберите стандартный эндпоинт или введите произвольный URL/IP:",
    ]
    await callback.message.edit_text("\n".join(lines), reply_markup=llm_base_urls_select_kb(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("llm_preset_url:"))
async def cb_llm_preset_url(
    callback: CallbackQuery,
    db: Database,
    settings: Settings,
    llm_client: LLMClient,
    is_admin: bool = False,
) -> None:
    if not is_admin:
        await callback.answer("⚠️ Доступ только для администраторов.", show_alert=True)
        return

    url = callback.data.split(":", 1)[1]
    async with db.connect() as conn:
        config_repo = ConfigRepository(conn)
        await config_repo.set_llm_config(base_url=url)
        text, is_on, conf = await _render_llm_settings(conn, settings)

    llm_client.update_config(base_url=url)
    await callback.message.edit_text(text, reply_markup=llm_settings_kb(is_on, conf), parse_mode="HTML")
    await callback.answer("URL эндпоинта обновлен")


@router.callback_query(F.data == "llm_custom_url")
async def cb_llm_custom_url(callback: CallbackQuery, state: FSMContext, is_admin: bool = False) -> None:
    if not is_admin:
        await callback.answer("⚠️ Доступ только для администраторов.", show_alert=True)
        return

    await state.set_state(AdminLLMStates.waiting_for_base_url)
    lines = [
        "🌐 <b>Ввод произвольного Base URL / IP-адреса</b>\n",
        "Отправьте полный адрес OpenAI-совместимого эндпоинта, например:",
        "• <code>http://192.168.1.50:11434/v1</code> (локальная Ollama)",
        "• <code>http://18.135.101.212:8000/v1</code> (свой сервер vLLM)",
        "• <code>https://api.openai.com/v1</code>",
    ]
    await callback.message.edit_text("\n".join(lines), reply_markup=llm_cancel_kb(), parse_mode="HTML")
    await callback.answer()


@router.message(AdminLLMStates.waiting_for_base_url)
async def proc_admin_llm_custom_url(
    message: Message,
    state: FSMContext,
    db: Database,
    settings: Settings,
    llm_client: LLMClient,
    is_admin: bool = False,
) -> None:
    if not is_admin:
        return

    url = message.text.strip() if message.text else ""
    await state.clear()

    if not url.startswith("http://") and not url.startswith("https://"):
        await message.answer("❌ Адрес должен начинаться с http:// или https://. Попробуйте снова через /llm", reply_markup=admin_panel_kb())
        return

    async with db.connect() as conn:
        config_repo = ConfigRepository(conn)
        await config_repo.set_llm_config(base_url=url)
        text, is_on, conf = await _render_llm_settings(conn, settings)

    llm_client.update_config(base_url=url)
    await message.answer(f"✅ <b>Эндпоинт сохранён:</b> <code>{url}</code>\n\n{text}", reply_markup=llm_settings_kb(is_on, conf), parse_mode="HTML")


@router.callback_query(F.data == "llm_test_ping")
async def cb_llm_test_ping(
    callback: CallbackQuery,
    llm_client: LLMClient,
    is_admin: bool = False,
) -> None:
    if not is_admin:
        await callback.answer("⚠️ Доступ только для администраторов.", show_alert=True)
        return

    await callback.answer("⏳ Тестирование соединения с ИИ...", show_alert=False)
    success, msg, latency_ms = await llm_client.test_connection()

    if success:
        result_text = (
            f"✅ <b>Тест подключения успешен!</b>\n\n"
            f"• <b>Модель:</b> <code>{llm_client.model}</code>\n"
            f"• <b>Задержка:</b> <code>{latency_ms:.0f} мс</code>\n"
            f"• <b>Ответ API:</b> <i>{msg}</i>"
        )
    else:
        result_text = (
            f"❌ <b>Ошибка при проверке связи!</b>\n\n"
            f"• <b>Эндпоинт:</b> <code>{llm_client.base_url}</code>\n"
            f"• <b>Модель:</b> <code>{llm_client.model}</code>\n"
            f"• <b>Причина:</b> <i>{msg}</i>"
        )

    await callback.message.answer(result_text, parse_mode="HTML")

# ==================== STRICTNESS & CUSTOM WORDS ====================

@router.callback_query(F.data.startswith("mod_select_strictness:"))
async def cb_mod_select_strictness(callback: CallbackQuery, is_admin: bool = False) -> None:
    if not is_admin:
        await callback.answer("⚠️ Доступ только для администраторов.", show_alert=True)
        return

    chat_id = int(callback.data.split(":")[1])
    text = (
        "🎯 <b>Выберите уровень строгости фильтрации матов:</b>\n\n"
        "1. 🤬 <b>Только жесткий мат</b> (Hard):\n"
        "• Реагирует на: <i>сука, пидор, гандон, хуй, пизда, ебать, блядь</i> и их производные/маскировки.\n"
        "• Бытовые слова (<i>блин, тупой, дурак</i>) разрешены.\n\n"
        "2. ⚠️ <b>Жесткий мат + грубые оскорбления</b> (Medium):\n"
        "• Всё выше + слова: <i>урод, тварь, дебил, даун, мразь, гнида</i>.\n\n"
        "3. 🛑 <b>Максимальная строгость</b> (All):\n"
        "• Полная фильтрация: всё выше + легкая брань: <i>блин, тупой, дурак, чмо, лох</i>."
    )
    await callback.message.edit_text(text, reply_markup=mod_strictness_select_kb(chat_id), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("mod_set_strict:"))
async def cb_mod_set_strict(callback: CallbackQuery, db: Database, is_admin: bool = False) -> None:
    if not is_admin:
        await callback.answer("⚠️ Доступ только для администраторов.", show_alert=True)
        return

    parts = callback.data.split(":")
    chat_id = int(parts[1])
    strictness = parts[2]

    async with db.connect() as conn:
        chat_repo = ChatRepository(conn)
        await chat_repo.set_strictness(chat_id, strictness)

    await callback.answer("Строгость сохранена")
    await cb_chat_moderation_view(callback, db, is_admin=is_admin)


@router.callback_query(F.data.startswith("mod_custom_words:"))
async def cb_mod_custom_words(callback: CallbackQuery, db: Database, is_admin: bool = False) -> None:
    if not is_admin:
        await callback.answer("⚠️ Доступ только для администраторов.", show_alert=True)
        return

    import json
    chat_id = int(callback.data.split(":")[1])
    async with db.connect() as conn:
        chat_repo = ChatRepository(conn)
        chat = await chat_repo.get_chat(chat_id)

    raw_cw = chat.get("custom_profanity_words", "[]") if chat else "[]"
    try:
        cw_list = json.loads(raw_cw) if isinstance(raw_cw, str) else (raw_cw or [])
    except Exception:
        cw_list = []

    words_str = ", ".join(cw_list) if cw_list else "<i>(список пуст)</i>"
    text = (
        f"📝 <b>Свои стоп-слова для чата #{chat_id}:</b>\n\n"
        f"Текущий список: {words_str}\n\n"
        "<i>💡 Если сообщение участника содержит любое из этих слов, бот зарегистрирует нарушение "
        "и применит предупреждение или удаление в зависимости от настроек чата.</i>"
    )
    await callback.message.edit_text(text, reply_markup=mod_custom_words_kb(chat_id, bool(cw_list)), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("mod_cw_edit:"))
async def cb_mod_cw_edit(callback: CallbackQuery, state: FSMContext, is_admin: bool = False) -> None:
    if not is_admin:
        await callback.answer("⚠️ Доступ только для администраторов.", show_alert=True)
        return

    chat_id = int(callback.data.split(":")[1])
    await state.set_state(AdminModStates.waiting_for_custom_words)
    await state.update_data(mod_chat_id=chat_id)

    await callback.message.answer(
        "✏️ <b>Введите стоп-слова через запятую:</b>\n\n"
        "<i>Пример: спам, казино, реклама, мошенники</i>",
        reply_markup=llm_cancel_kb(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(AdminModStates.waiting_for_custom_words)
async def proc_mod_save_custom_words(message: Message, state: FSMContext, db: Database, is_admin: bool = False) -> None:
    if not is_admin:
        return

    data = await state.get_data()
    chat_id = data.get("mod_chat_id")
    await state.clear()

    if not chat_id:
        await message.answer("Ошибка: чат не определен.")
        return

    raw_text = message.text or ""
    words = [w.strip() for w in raw_text.split(",") if w.strip()]

    async with db.connect() as conn:
        chat_repo = ChatRepository(conn)
        await chat_repo.set_custom_words(chat_id, words)
        chat = await chat_repo.get_chat(chat_id)

    await message.answer(
        f"✅ <b>Сохранено {len(words)} стоп-слов для чата!</b>",
        reply_markup=chat_moderation_detail_kb(chat) if chat else None,
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("mod_cw_clear:"))
async def cb_mod_cw_clear(callback: CallbackQuery, db: Database, is_admin: bool = False) -> None:
    if not is_admin:
        await callback.answer("⚠️ Доступ только для администраторов.", show_alert=True)
        return

    chat_id = int(callback.data.split(":")[1])
    async with db.connect() as conn:
        chat_repo = ChatRepository(conn)
        await chat_repo.set_custom_words(chat_id, [])
        chat = await chat_repo.get_chat(chat_id)

    await callback.answer("Стоп-слова очищены!")
    text = (
        f"📝 <b>Свои стоп-слова для чата #{chat_id}:</b>\n\n"
        "Текущий список: <i>(список пуст)</i>"
    )
    await callback.message.edit_text(text, reply_markup=mod_custom_words_kb(chat_id, False), parse_mode="HTML")


# ==================== LLM CONTEXT & GENERATION SETTINGS ====================

@router.callback_query(F.data == "llm_select_context")
async def cb_llm_select_context(callback: CallbackQuery, is_admin: bool = False) -> None:
    if not is_admin:
        await callback.answer("⚠️ Доступ только для администраторов.", show_alert=True)
        return

    text = (
        "📚 <b>Размер контекста чата (история сообщений):</b>\n\n"
        "Определяет, сколько недавних сообщений из чата Ричард держит в памяти при ответе на теги и вопросы.\n\n"
        "• ⚡ <b>5 сообщ.</b> — минимально / экономно по токенам\n"
        "• 📌 <b>10 сообщ.</b> — короткий контекст\n"
        "• 📗 <b>15 сообщ.</b> — стандартное значение\n"
        "• 📚 <b>25 сообщ.</b> — глубокий контекст диалога\n"
        "• 📖 <b>40 сообщ.</b> — максимальный охват дискуссии\n\n"
        "Выберите пресет или введите точное число:"
    )
    await callback.message.edit_text(text, reply_markup=llm_context_select_kb(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("llm_preset_ctx:"))
async def cb_llm_preset_ctx(
    callback: CallbackQuery,
    db: Database,
    settings: Settings,
    companion: Optional[ChatCompanion] = None,
    is_admin: bool = False,
) -> None:
    if not is_admin:
        await callback.answer("⚠️ Доступ только для администраторов.", show_alert=True)
        return

    ctx_val = int(callback.data.split(":")[1])
    async with db.connect() as conn:
        config_repo = ConfigRepository(conn)
        await config_repo.set_llm_config(context_limit=ctx_val)
        text, is_on, conf = await _render_llm_settings(conn, settings)

    if companion:
        companion.update_config(context_limit=ctx_val)

    await callback.message.edit_text(text, reply_markup=llm_settings_kb(is_on, conf), parse_mode="HTML")
    await callback.answer(f"Контекст: {ctx_val} сообщений")


@router.callback_query(F.data == "llm_custom_ctx")
async def cb_llm_custom_ctx(callback: CallbackQuery, state: FSMContext, is_admin: bool = False) -> None:
    if not is_admin:
        await callback.answer("⚠️ Доступ только для администраторов.", show_alert=True)
        return

    await state.set_state(AdminLLMStates.waiting_for_context)
    await callback.message.edit_text(
        "✏️ <b>Введите размер контекста (число сообщений от 1 до 100):</b>",
        reply_markup=llm_cancel_kb(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(AdminLLMStates.waiting_for_context)
async def proc_llm_custom_ctx(
    message: Message,
    state: FSMContext,
    db: Database,
    settings: Settings,
    companion: Optional[ChatCompanion] = None,
    is_admin: bool = False,
) -> None:
    if not is_admin:
        return

    try:
        val = int(message.text.strip())
        if val < 1 or val > 150:
            raise ValueError()
    except ValueError:
        await message.answer("❌ Введите целое число от 1 до 150. Попробуйте снова через /llm", reply_markup=admin_panel_kb())
        await state.clear()
        return

    await state.clear()
    async with db.connect() as conn:
        config_repo = ConfigRepository(conn)
        await config_repo.set_llm_config(context_limit=val)
        text, is_on, conf = await _render_llm_settings(conn, settings)

    if companion:
        companion.update_config(context_limit=val)

    await message.answer(f"✅ <b>Контекст установлен:</b> <code>{val}</code> сообщ.\n\n{text}", reply_markup=llm_settings_kb(is_on, conf), parse_mode="HTML")


@router.callback_query(F.data == "llm_select_tokens")
async def cb_llm_select_tokens(callback: CallbackQuery, is_admin: bool = False) -> None:
    if not is_admin:
        await callback.answer("⚠️ Доступ только для администраторов.", show_alert=True)
        return

    text = (
        "📝 <b>Максимальная длина ответов Ричарда (max_tokens):</b>\n\n"
        "Определяет лимит длины генерации одного сообщения нейросетью:\n\n"
        "• ⚡ <b>Краткий (~250 токенов)</b> — быстрые лаконичные реплики\n"
        "• 📝 <b>Средний (~600 токенов)</b> — обычные ответы (1-2 абзаца)\n"
        "• 📖 <b>Развернутый (~1000 токенов)</b> — подробные объяснения и темы\n"
        "• 📚 <b>Большой (~1500 токенов)</b> — длинные доклады/рефераты\n"
        "• 🚀 <b>Максимум (~2500 токенов)</b> — практически без ограничений\n\n"
        "Выберите пресет или введите число вручную:"
    )
    await callback.message.edit_text(text, reply_markup=llm_tokens_select_kb(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("llm_preset_tokens:"))
async def cb_llm_preset_tokens(
    callback: CallbackQuery,
    db: Database,
    settings: Settings,
    companion: Optional[ChatCompanion] = None,
    is_admin: bool = False,
) -> None:
    if not is_admin:
        await callback.answer("⚠️ Доступ только для администраторов.", show_alert=True)
        return

    tok_val = int(callback.data.split(":")[1])
    async with db.connect() as conn:
        config_repo = ConfigRepository(conn)
        await config_repo.set_llm_config(max_tokens=tok_val)
        text, is_on, conf = await _render_llm_settings(conn, settings)

    if companion:
        companion.update_config(max_tokens=tok_val)

    await callback.message.edit_text(text, reply_markup=llm_settings_kb(is_on, conf), parse_mode="HTML")
    await callback.answer(f"Длина: {tok_val} токенов")


@router.callback_query(F.data == "llm_custom_tokens")
async def cb_llm_custom_tokens(callback: CallbackQuery, state: FSMContext, is_admin: bool = False) -> None:
    if not is_admin:
        await callback.answer("⚠️ Доступ только для администраторов.", show_alert=True)
        return

    await state.set_state(AdminLLMStates.waiting_for_tokens)
    await callback.message.edit_text(
        "✏️ <b>Введите максимальное количество токенов (число от 50 до 4000):</b>",
        reply_markup=llm_cancel_kb(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(AdminLLMStates.waiting_for_tokens)
async def proc_llm_custom_tokens(
    message: Message,
    state: FSMContext,
    db: Database,
    settings: Settings,
    companion: Optional[ChatCompanion] = None,
    is_admin: bool = False,
) -> None:
    if not is_admin:
        return

    try:
        val = int(message.text.strip())
        if val < 50 or val > 4096:
            raise ValueError()
    except ValueError:
        await message.answer("❌ Введите целое число от 50 до 4096. Попробуйте снова через /llm", reply_markup=admin_panel_kb())
        await state.clear()
        return

    await state.clear()
    async with db.connect() as conn:
        config_repo = ConfigRepository(conn)
        await config_repo.set_llm_config(max_tokens=val)
        text, is_on, conf = await _render_llm_settings(conn, settings)

    if companion:
        companion.update_config(max_tokens=val)

    await message.answer(f"✅ <b>Лимит длины установлен:</b> <code>{val}</code> токенов\n\n{text}", reply_markup=llm_settings_kb(is_on, conf), parse_mode="HTML")


@router.callback_query(F.data == "llm_select_temp")
async def cb_llm_select_temp(callback: CallbackQuery, is_admin: bool = False) -> None:
    if not is_admin:
        await callback.answer("⚠️ Доступ только для администраторов.", show_alert=True)
        return

    text = (
        "🌡️ <b>Креативность ответов (Temperature):</b>\n\n"
        "• 🎯 <b>Точный (0.2)</b> — строгие факты, минимум фантазии и выдумок\n"
        "• ⚖️ <b>Сбалансированный (0.7)</b> — стандарт, естественный живой диалог\n"
        "• 🎨 <b>Креативный (1.0)</b> — яркий юмор, образность, свободная беседы\n\n"
        "Выберите уровень температуры:"
    )
    await callback.message.edit_text(text, reply_markup=llm_temp_select_kb(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("llm_preset_temp:"))
async def cb_llm_preset_temp(
    callback: CallbackQuery,
    db: Database,
    settings: Settings,
    companion: Optional[ChatCompanion] = None,
    is_admin: bool = False,
) -> None:
    if not is_admin:
        await callback.answer("⚠️ Доступ только для администраторов.", show_alert=True)
        return

    temp_val = float(callback.data.split(":")[1])
    async with db.connect() as conn:
        config_repo = ConfigRepository(conn)
        await config_repo.set_llm_config(temperature=temp_val)
        text, is_on, conf = await _render_llm_settings(conn, settings)

    if companion:
        companion.update_config(temperature=temp_val)

    await callback.message.edit_text(text, reply_markup=llm_settings_kb(is_on, conf), parse_mode="HTML")
    await callback.answer(f"Температура: {temp_val}")



# ==================== NEW MODERATION & LLM HANDLERS ====================

@router.callback_query(F.data.startswith("mod_autodel_cycle:"))
async def cb_mod_autodel_cycle(callback: CallbackQuery, db: Database, is_admin: bool = False) -> None:
    if not is_admin:
        await callback.answer("⚠️ Доступ только для администраторов.", show_alert=True)
        return
    cid = int(callback.data.split(":")[1])
    async with db.connect() as conn:
        chat_repo = ChatRepository(conn)
        new_sec = await chat_repo.cycle_delete_warn_seconds(cid)
    label = f"{new_sec} сек." if new_sec > 0 else "Выключено"
    await callback.answer(f"Автоудаление предупреждений: {label}")
    await cb_chat_moderation_view(callback, db, is_admin=is_admin)


@router.callback_query(F.data.startswith("mod_automute_cycle:"))
async def cb_mod_automute_cycle(callback: CallbackQuery, db: Database, is_admin: bool = False) -> None:
    if not is_admin:
        await callback.answer("⚠️ Доступ только для администраторов.", show_alert=True)
        return
    cid = int(callback.data.split(":")[1])
    async with db.connect() as conn:
        chat_repo = ChatRepository(conn)
        new_val = await chat_repo.cycle_auto_mute(cid)
    label = "Выкл" if new_val == 0 else (f"{new_val//60} мин." if new_val < 3600 else f"{new_val//3600} ч.")
    await callback.answer(f"Авто-мут при 3 нарушениях: {label}")
    await cb_chat_moderation_view(callback, db, is_admin=is_admin)


@router.callback_query(F.data.startswith("mod_clear_mem:"))
async def cb_mod_clear_mem(
    callback: CallbackQuery,
    db: Database,
    companion: Optional[ChatCompanion] = None,
    is_admin: bool = False,
) -> None:
    if not is_admin:
        await callback.answer("⚠️ Доступ только для администраторов.", show_alert=True)
        return
    cid = int(callback.data.split(":")[1])
    async with db.connect() as conn:
        await ChatRepository(conn).clear_companion_history(cid)
    if companion:
        companion.context_buffer.clear(cid)
    await callback.answer("Память диалогов для этого чата очищена!", show_alert=True)
    await cb_chat_moderation_view(callback, db, is_admin=is_admin)


@router.callback_query(F.data.startswith("mod_wl_menu:"))
async def cb_mod_wl_menu(callback: CallbackQuery, db: Database, is_admin: bool = False) -> None:
    if not is_admin:
        await callback.answer("⚠️ Доступ только для администраторов.", show_alert=True)
        return
    cid = int(callback.data.split(":")[1])
    import json
    async with db.connect() as conn:
        chat = await ChatRepository(conn).get_chat(cid)
    raw_wl = chat.get("custom_whitelist_words", "[]") if chat else "[]"
    try:
        w_list = json.loads(raw_wl) if isinstance(raw_wl, str) else (raw_wl or [])
    except Exception:
        w_list = []
    lines = [
        f"⚪ <b>Белый список слов для чата #{cid} (Исключения)</b>\n",
        "Слова из этого списка бот <b>никогда не будет считать матом</b> в этом чате.\n",
        f"Текущий белый список: <b>{', '.join(w_list) if w_list else '<i>(пуст)</i>'}</b>",
    ]
    await callback.message.edit_text("\n".join(lines), reply_markup=mod_whitelist_kb(cid, bool(w_list)), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("mod_wl_edit:"))
async def cb_mod_wl_edit(callback: CallbackQuery, state: FSMContext, is_admin: bool = False) -> None:
    if not is_admin:
        await callback.answer("⚠️ Доступ только для администраторов.", show_alert=True)
        return
    cid = int(callback.data.split(":")[1])
    await state.set_state(AdminModStates.waiting_for_whitelist_words)
    await state.update_data(mod_chat_id=cid)
    text = (
        f"✏️ <b>Введите белый список слов для чата #{cid}:</b>\n\n"
        "Отправьте слова через запятую (например: <code>дебил, урод, блин</code>).\n"
        "Эти слова не будут блокироваться в этом чате."
    )
    await callback.message.edit_text(text, reply_markup=llm_cancel_kb(), parse_mode="HTML")
    await callback.answer()


@router.message(AdminModStates.waiting_for_whitelist_words)
async def proc_mod_whitelist_words(
    message: Message,
    state: FSMContext,
    db: Database,
    is_admin: bool = False,
) -> None:
    if not is_admin:
        return
    data = await state.get_data()
    cid = data.get("mod_chat_id")
    await state.clear()
    raw = message.text.strip() if message.text else ""
    words = [w.strip().lower() for w in raw.split(",") if w.strip()]
    if cid:
        async with db.connect() as conn:
            chat_repo = ChatRepository(conn)
            await chat_repo.set_whitelist_words(cid, words)
            chat = await chat_repo.get_chat(cid)
    await message.answer(f"✅ <b>Белый список сохранён ({len(words)} слов)!</b>", reply_markup=chat_moderation_detail_kb(chat), parse_mode="HTML")


@router.callback_query(F.data.startswith("mod_wl_clear:"))
async def cb_mod_wl_clear(callback: CallbackQuery, db: Database, is_admin: bool = False) -> None:
    if not is_admin:
        await callback.answer("⚠️ Доступ только для администраторов.", show_alert=True)
        return
    cid = int(callback.data.split(":")[1])
    async with db.connect() as conn:
        chat_repo = ChatRepository(conn)
        await chat_repo.set_whitelist_words(cid, [])
        chat = await chat_repo.get_chat(cid)
    await callback.answer("Белый список очищен!")
    await cb_chat_moderation_view(callback, db, is_admin=is_admin)


@router.callback_query(F.data == "llm_select_persona")
async def cb_llm_select_persona(callback: CallbackQuery, is_admin: bool = False) -> None:
    if not is_admin:
        await callback.answer("⚠️ Доступ только для администраторов.", show_alert=True)
        return
    text = (
        "🎭 <b>Выбор характера и личности Ричарда:</b>\n\n"
        "• 🎓 <b>Студент-сокурсник</b> — живой, понимает пары, сессии, дружелюбный и отзывчивый\n"
        "• 💼 <b>Деловой эксперт</b> — вежливый, точный, без лишнего сленга и шуток\n"
        "• 😈 <b>Дерзкий / Остроумный</b> — черный юмор, сарказм и подколы\n"
        "• ⚡ <b>Краткий / По делу</b> — 1-2 предложения, максимум сути\n"
        "• ✍️ <b>Свой промпт</b> — задайте любую свою инструкцию для нейросети\n\n"
        "Выберите пресет:"
    )
    await callback.message.edit_text(text, reply_markup=llm_persona_select_kb(), parse_mode="HTML")
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
    async with db.connect() as conn:
        config_repo = ConfigRepository(conn)
        await config_repo.set_llm_config(persona=persona_code)
        text, is_on, conf = await _render_llm_settings(conn, settings)
    if companion:
        companion.update_config(persona=persona_code)
    await callback.message.edit_text(text, reply_markup=llm_settings_kb(is_on, conf), parse_mode="HTML")
    await callback.answer(f"Характер: {persona_code}")


@router.callback_query(F.data == "llm_custom_persona")
async def cb_llm_custom_persona(callback: CallbackQuery, state: FSMContext, is_admin: bool = False) -> None:
    if not is_admin:
        await callback.answer("⚠️ Доступ только для администраторов.", show_alert=True)
        return
    await state.set_state(AdminLLMStates.waiting_for_custom_persona)
    text = (
        "✍️ <b>Ввод пользовательского системного промпта для Ричарда:</b>\n\n"
        "Отправьте сообщением подробную инструкцию (роль, правила, манера речи)."
    )
    await callback.message.edit_text(text, reply_markup=llm_cancel_kb(), parse_mode="HTML")
    await callback.answer()


@router.message(AdminLLMStates.waiting_for_custom_persona)
async def proc_llm_custom_persona(
    message: Message,
    state: FSMContext,
    db: Database,
    settings: Settings,
    companion: Optional[ChatCompanion] = None,
    is_admin: bool = False,
) -> None:
    if not is_admin:
        return
    prompt_text = message.text.strip() if message.text else ""
    await state.clear()
    if not prompt_text:
        await message.answer("❌ Промпт не может быть пустым.", reply_markup=admin_panel_kb())
        return
    async with db.connect() as conn:
        config_repo = ConfigRepository(conn)
        await config_repo.set_llm_config(persona="custom", custom_prompt=prompt_text)
        text, is_on, conf = await _render_llm_settings(conn, settings)
    if companion:
        companion.update_config(persona="custom", custom_prompt=prompt_text)
    await message.answer(f"✅ <b>Пользовательский характер сохранен!</b>\n\n{text}", reply_markup=llm_settings_kb(is_on, conf), parse_mode="HTML")


@router.callback_query(F.data == "llm_select_trigger")
async def cb_llm_select_trigger(callback: CallbackQuery, is_admin: bool = False) -> None:
    if not is_admin:
        await callback.answer("⚠️ Доступ только для администраторов.", show_alert=True)
        return
    text = (
        "🎯 <b>Режим реакции Ричарда в группах:</b>\n\n"
        "• 🗣️ <b>Только имя и реплай</b> — реагирует на 'Ричард', 'Richard' или ответ на его сообщение\n"
        "• 📢 <b>Все упоминания</b> — реагирует также на @теги бота\n\n"
        "Выберите режим:"
    )
    await callback.message.edit_text(text, reply_markup=llm_trigger_select_kb(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("llm_set_trigger:"))
async def cb_llm_set_trigger(
    callback: CallbackQuery,
    db: Database,
    settings: Settings,
    companion: Optional[ChatCompanion] = None,
    is_admin: bool = False,
) -> None:
    if not is_admin:
        await callback.answer("⚠️ Доступ только для администраторов.", show_alert=True)
        return
    trig = callback.data.split(":", 1)[1]
    async with db.connect() as conn:
        config_repo = ConfigRepository(conn)
        await config_repo.set_llm_config(trigger_mode=trig)
        text, is_on, conf = await _render_llm_settings(conn, settings)
    if companion:
        companion.update_config(trigger_mode=trig)
    await callback.message.edit_text(text, reply_markup=llm_settings_kb(is_on, conf), parse_mode="HTML")
    await callback.answer(f"Режим триггера: {trig}")


@router.callback_query(F.data == "llm_toggle_typing")
async def cb_llm_toggle_typing(
    callback: CallbackQuery,
    db: Database,
    settings: Settings,
    companion: Optional[ChatCompanion] = None,
    is_admin: bool = False,
) -> None:
    if not is_admin:
        await callback.answer("⚠️ Доступ только для администраторов.", show_alert=True)
        return
    async with db.connect() as conn:
        config_repo = ConfigRepository(conn)
        curr = await config_repo.get_llm_config()
        new_val = not curr.get("companion_typing_indicator", True)
        await config_repo.set_llm_config(typing_indicator=new_val)
        text, is_on, conf = await _render_llm_settings(conn, settings)
    if companion:
        companion.update_config(typing_indicator=new_val)
    await callback.message.edit_text(text, reply_markup=llm_settings_kb(is_on, conf), parse_mode="HTML")
    label = "ВКЛ" if new_val else "ВЫКЛ"
    await callback.answer(f"Статус «Печатает...»: {label}")


@router.callback_query(F.data == "llm_cycle_random")
async def cb_llm_cycle_random(
    callback: CallbackQuery,
    db: Database,
    settings: Settings,
    companion: Optional[ChatCompanion] = None,
    is_admin: bool = False,
) -> None:
    if not is_admin:
        await callback.answer("⚠️ Доступ только для администраторов.", show_alert=True)
        return
    cycle_map = {0: 3, 3: 5, 5: 10, 10: 0}
    async with db.connect() as conn:
        config_repo = ConfigRepository(conn)
        curr = await config_repo.get_llm_config()
        c_rand = curr.get("companion_random_reply_chance", 0)
        new_rand = cycle_map.get(c_rand, 0)
        await config_repo.set_llm_config(random_reply_chance=new_rand)
        text, is_on, conf = await _render_llm_settings(conn, settings)
    if companion:
        companion.update_config(random_reply_chance=new_rand)
    await callback.message.edit_text(text, reply_markup=llm_settings_kb(is_on, conf), parse_mode="HTML")
    await callback.answer(f"Шанс случайного ответа: {new_rand}%" if new_rand > 0 else "Случайные ответы выключены")


@router.callback_query(F.data == "llm_clear_all_mem")
async def cb_llm_clear_all_mem(
    callback: CallbackQuery,
    db: Database,
    companion: Optional[ChatCompanion] = None,
    is_admin: bool = False,
) -> None:
    if not is_admin:
        await callback.answer("⚠️ Доступ только для администраторов.", show_alert=True)
        return
    async with db.connect() as conn:
        await ChatRepository(conn).clear_all_companion_history()
    if companion:
        companion.context_buffer._buffers.clear()
    await callback.answer("Вся память диалогов Ричарда во всех чатах очищена!", show_alert=True)


@router.callback_query(F.data.startswith("mod_view_history:"))
async def cb_mod_view_history(callback: CallbackQuery, db: Database, is_admin: bool = False) -> None:
    if not is_admin:
        await callback.answer("⚠️ Доступ только для администраторов.", show_alert=True)
        return

    cid = int(callback.data.split(":")[1])
    async with db.connect() as conn:
        history = await ChatRepository(conn).get_companion_history(cid, limit=12)

    if not history:
        text = (
            f"📜 <b>Память диалогов Ричарда в чате #{cid}:</b>\n\n"
            "<i>(История пуста — Ричард пока не общался в этом чате или память была очищена)</i>"
        )
    else:
        div = "━━━━━━━━━━━━━━━━━━━━━━"
        lines = [
            f"📜 <b>Память диалогов Ричарда в чате #{cid}:</b>",
            f"<i>Показаны последние {len(history)} реплик из базы данных:</i>",
            div,
        ]
        for msg in history:
            is_bot = bool(msg.get("is_bot"))
            sender = "🤖 Ричард" if is_bot else (msg.get("user_name") or f"ID {msg.get('user_id')}")
            uname = f" (@{msg['username']})" if msg.get("username") and not is_bot else ""
            txt = (msg.get("text") or "").strip()
            if len(txt) > 100:
                txt = txt[:97] + "..."
            lines.append(f"• <b>{sender}{uname}:</b> {txt}")
        lines.append(div)
        lines.append("💡 <i>Вы можете очистить память для этого чата кнопкой ниже:</i>")
        text = "\n".join(lines)

    await callback.message.edit_text(text, reply_markup=mod_history_kb(cid), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "noop")
async def cb_noop(callback: CallbackQuery) -> None:
    await callback.answer("👑 Это аккаунт Главного владельца системы. Он полностью защищён от блокировок и сброса.", show_alert=True)


# ==================== RANDOM REPLIES MENU ====================

@router.callback_query(F.data == "llm_select_random")
async def cb_llm_select_random(callback: CallbackQuery, db: Database, is_admin: bool = False) -> None:
    if not is_admin:
        await callback.answer("⚠️ Доступ только для администраторов.", show_alert=True)
        return

    async with db.connect() as conn:
        curr = await ConfigRepository(conn).get_llm_config()
    rand_chance = curr.get("companion_random_reply_chance", 0)

    text = (
        "🎲 <b>Спонтанные реплики Ричарда в групповых чатах:</b>\n\n"
        "Определяет, с какой вероятностью Ричард будет <b>сам вступать в разговор участников</b> без прямого обращения по имени и без Reply:\n\n"
        "• ⚪ <b>0% (Выключено)</b> — Ричард отвечает ТОЛЬКО когда его зовут по имени («Ричард») или делают Reply\n"
        "• 🟢 <b>1% (Очень редко)</b> — ~1 реплика на 100 сообщений\n"
        "• 🟢 <b>3% (Редко)</b> — ~1 реплика на 30 сообщений\n"
        "• 🟡 <b>5% (Умеренно)</b> — живой участник (~1 на 20 сообщений)\n"
        "• 🟠 <b>10% (Активно)</b> — ~1 реплика на 10 сообщений\n"
        "• 🔴 <b>20% (Часто)</b> — активный участник беседы\n"
        "• ✏️ <b>Свой %</b> — точная настройка от 0% до 50%\n\n"
        f"Текущая вероятность: <b>{rand_chance}%</b>"
    )
    await callback.message.edit_text(text, reply_markup=llm_random_select_kb(rand_chance), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("llm_set_random:"))
async def cb_llm_set_random(
    callback: CallbackQuery,
    db: Database,
    settings: Settings,
    companion: Optional[ChatCompanion] = None,
    is_admin: bool = False,
) -> None:
    if not is_admin:
        await callback.answer("⚠️ Доступ только для администраторов.", show_alert=True)
        return

    val = int(callback.data.split(":")[1])
    async with db.connect() as conn:
        config_repo = ConfigRepository(conn)
        await config_repo.set_llm_config(random_reply_chance=val)

    if companion:
        companion.update_config(random_reply_chance=val)

    text = (
        "🎲 <b>Спонтанные реплики Ричарда в групповых чатах:</b>\n\n"
        "Определяет, с какой вероятностью Ричард будет <b>сам вступать в разговор участников</b> без прямого обращения по имени и без Reply:\n\n"
        "• ⚪ <b>0% (Выключено)</b> — Ричард отвечает ТОЛЬКО когда его зовут по имени («Ричард») или делают Reply\n"
        "• 🟢 <b>1% (Очень редко)</b> — ~1 реплика на 100 сообщений\n"
        "• 🟢 <b>3% (Редко)</b> — ~1 реплика на 30 сообщений\n"
        "• 🟡 <b>5% (Умеренно)</b> — живой участник (~1 на 20 сообщений)\n"
        "• 🟠 <b>10% (Активно)</b> — ~1 реплика на 10 сообщений\n"
        "• 🔴 <b>20% (Часто)</b> — активный участник беседы\n"
        "• ✏️ <b>Свой %</b> — точная настройка от 0% до 50%\n\n"
        f"Текущая вероятность: <b>{val}%</b>"
    )
    await callback.message.edit_text(text, reply_markup=llm_random_select_kb(val), parse_mode="HTML")
    desc = f"{val}%" if val > 0 else "Выключено"
    await callback.answer(f"✅ Установлено: {desc}")


@router.callback_query(F.data == "llm_custom_random")
async def cb_llm_custom_random(callback: CallbackQuery, state: FSMContext, is_admin: bool = False) -> None:
    if not is_admin:
        await callback.answer("⚠️ Доступ только для администраторов.", show_alert=True)
        return

    await state.set_state(AdminLLMStates.waiting_for_random_chance)
    await callback.message.edit_text(
        "✏️ <b>Введите желаемую вероятность инициативы Ричарда (число от 0 до 50%):</b>\n\n"
        "<i>Например: 3, 7, 15</i>",
        reply_markup=llm_cancel_kb(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(AdminLLMStates.waiting_for_random_chance)
async def proc_llm_custom_random(
    message: Message,
    state: FSMContext,
    db: Database,
    settings: Settings,
    companion: Optional[ChatCompanion] = None,
    is_admin: bool = False,
) -> None:
    if not is_admin:
        return

    try:
        val = int(message.text.strip().rstrip("%"))
        if val < 0 or val > 50:
            raise ValueError()
    except ValueError:
        await message.answer("❌ Введите целое число от 0 до 50. Попробуйте снова через /llm", reply_markup=admin_panel_kb())
        await state.clear()
        return

    await state.clear()
    async with db.connect() as conn:
        config_repo = ConfigRepository(conn)
        await config_repo.set_llm_config(random_reply_chance=val)
        text, is_on, conf = await _render_llm_settings(conn, settings)

    if companion:
        companion.update_config(random_reply_chance=val)

    await message.answer(f"✅ <b>Вероятность инициативы установлена:</b> <code>{val}%</code>\n\n{text}", reply_markup=llm_settings_kb(is_on, conf), parse_mode="HTML")


# ==================== PER-USER CONTEXT & MEMORY ====================

@router.callback_query(F.data.startswith("mod_users_ctx:"))
async def cb_mod_users_ctx(callback: CallbackQuery, db: Database, is_admin: bool = False) -> None:
    if not is_admin:
        await callback.answer("⚠️ Доступ только для администраторов.", show_alert=True)
        return

    cid = int(callback.data.split(":")[1])
    async with db.connect() as conn:
        chat_repo = ChatRepository(conn)
        participants = await chat_repo.get_companion_participants(cid)

    if not participants:
        text = (
            f"👥 <b>Контекст участников в чате #{cid}:</b>\n\n"
            "<i>(В этом чате пока нет зафиксированных сообщений участников в памяти Ричарда)</i>"
        )
        kb = mod_participants_list_kb(cid, [])
    else:
        div = "━━━━━━━━━━━━━━━━━━━━━━"
        lines = [
            f"👥 <b>Контекст участников в чате #{cid}:</b>",
            f"<i>Зафиксировано участников: <b>{len(participants)}</b></i>",
            div,
        ]
        for p in participants[:8]:
            uname = f" (@{p['username']})" if p.get("username") else ""
            lines.append(f"• 👤 <b>{p['user_name']}</b>{uname}: <code>{p['msg_count']}</code> сообщ.")
        lines.append(div)
        lines.append("👇 <i>Нажмите на участника ниже, чтобы посмотреть его историю или сбросить контекст:</i>")
        text = "\n".join(lines)
        kb = mod_participants_list_kb(cid, participants)

    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("mod_user_ctx:"))
async def cb_mod_user_ctx(callback: CallbackQuery, db: Database, is_admin: bool = False) -> None:
    if not is_admin:
        await callback.answer("⚠️ Доступ только для администраторов.", show_alert=True)
        return

    parts = callback.data.split(":")
    cid = int(parts[1])
    uid = int(parts[2])

    async with db.connect() as conn:
        chat_repo = ChatRepository(conn)
        msgs = await chat_repo.get_companion_user_history(cid, uid, limit=10)

    if not msgs:
        text = f"👤 <b>История участника ID {uid} в чате #{cid} пуста.</b>"
    else:
        first_m = msgs[0]
        uname = f" (@{first_m['username']})" if first_m.get("username") else ""
        div = "━━━━━━━━━━━━━━━━━━━━━━"
        lines = [
            f"👤 <b>Контекст участника {first_m['user_name']}{uname}</b>",
            f"🆔 <code>{uid}</code>  •  Чат: <code>#{cid}</code>",
            div,
            f"<i>Последние сохранённые реплики ({len(msgs)} шт.):</i>",
        ]
        for m in msgs:
            txt = (m.get("text") or "").strip()
            if len(txt) > 90:
                txt = txt[:87] + "..."
            lines.append(f"• <i>{txt}</i>")
        lines.append(div)
        text = "\n".join(lines)

    await callback.message.edit_text(text, reply_markup=mod_user_history_kb(cid, uid), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("mod_clear_user_ctx:"))
async def cb_mod_clear_user_ctx(
    callback: CallbackQuery,
    db: Database,
    companion: Optional[ChatCompanion] = None,
    is_admin: bool = False,
) -> None:
    if not is_admin:
        await callback.answer("⚠️ Доступ только для администраторов.", show_alert=True)
        return

    parts = callback.data.split(":")
    cid = int(parts[1])
    uid = int(parts[2])

    async with db.connect() as conn:
        chat_repo = ChatRepository(conn)
        await chat_repo.clear_companion_user_history(cid, uid)

    if companion:
        companion.context_buffer.clear_user(cid, uid)

    await callback.answer("Контекст участника успешно очищен!", show_alert=True)
    await cb_mod_users_ctx(callback, db, is_admin=is_admin)

# ─── NVIDIA STT (SPEECH-TO-TEXT) SETTINGS ───────────────────────────────────

async def _render_stt_settings(conn, settings: Settings, is_subadmin: bool = False) -> tuple[str, dict]:
    config_repo = ConfigRepository(conn)
    conf = await config_repo.get_stt_config(
        default_enabled=settings.STT_ENABLED,
        default_api_key=settings.STT_API_KEY,
        default_function_id=settings.STT_FUNCTION_ID,
        default_uri=settings.STT_URI,
        default_language=settings.STT_LANGUAGE,
    )
    is_on = conf.get("stt_enabled", True)
    api_key = conf.get("stt_api_key", "")
    lang = conf.get("stt_language", "ru-RU")
    lang_labels = {
        "ru-RU": "🇷🇺 Русский (ru-RU)",
        "multi": "🌐 Мультиязычный (multi)",
        "en-US": "🇺🇸 Английский (en-US)",
    }
    lang_str = lang_labels.get(lang, lang)

    if api_key:
        if is_subadmin:
            masked_key = "••••••••••••••••••••••••••••••••"
        else:
            masked_key = f"{api_key[:10]}...{api_key[-4:]}" if len(api_key) > 14 else "••••••••"
    else:
        masked_key = "<i>(не задан)</i>"

    lines = [
        "🎙️ <b>Распознавание речи (NVIDIA Whisper Large v3)</b>",
        "━━━━━━━━━━━━━━━━━━━━━━",
        f"• ⚡ <b>Статус:</b> {'🟢 Включено' if is_on else '⚪ Выключено'}",
        f"• 🧠 <b>Модель:</b> <code>openai/whisper-large-v3</code> (NVIDIA Riva)",
        f"• 🌐 <b>Сервер:</b> <code>{conf.get('stt_uri', 'grpc.nvcf.nvidia.com:443')}</code>",
        f"• 🔑 <b>API-ключ:</b> <code>{masked_key}</code>",
        f"• 🗣️ <b>Язык по умолчанию:</b> <b>{lang_str}</b>",
        "━━━━━━━━━━━━━━━━━━━━━━",
        "💡 <b>Возможности:</b>",
        "• Распознает голосовые сообщения (voice) и видео-кружочки (video_note)",
        "• Точность распознавания речи достигает <b>99%</b>",
        "• Текст автоматически поступает в память ИИ (Ричард понимает кружки и голосовые)",
        "• Пользователи могут запрашивать расшифровку в чате (реплика <code>/transcribe</code> или <code>текст</code>)",
    ]
    return "\n".join(lines), conf


@router.message(Command("stt"))
@router.callback_query(F.data == "admin_stt_settings")
async def cmd_admin_stt_settings(
    event: Message | CallbackQuery,
    db: Database,
    settings: Settings,
    is_admin: bool = False,
    is_subadmin: bool = False,
    state: Optional[FSMContext] = None,
) -> None:
    if not is_admin:
        if isinstance(event, CallbackQuery):
            await event.answer("⚠️ Доступ только для администраторов.", show_alert=True)
        return

    if state:
        await state.clear()

    async with db.connect() as conn:
        text, conf = await _render_stt_settings(conn, settings, is_subadmin=is_subadmin)

    kb = stt_settings_kb(conf, is_subadmin=is_subadmin)
    if isinstance(event, CallbackQuery):
        await event.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
        await event.answer()
    else:
        await event.answer(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data == "stt_toggle_enabled")
async def cb_stt_toggle_enabled(
    callback: CallbackQuery,
    db: Database,
    settings: Settings,
    stt_service: Optional[Any] = None,
    is_admin: bool = False,
    is_subadmin: bool = False,
) -> None:
    if not is_admin:
        await callback.answer("⚠️ Доступ только для администраторов.", show_alert=True)
        return

    async with db.connect() as conn:
        config_repo = ConfigRepository(conn)
        curr = await config_repo.get_stt_config(default_enabled=settings.STT_ENABLED)
        new_val = not curr["stt_enabled"]
        await config_repo.set_stt_config(enabled=new_val)
        if stt_service:
            stt_service.update_config(enabled=new_val)
        text, conf = await _render_stt_settings(conn, settings, is_subadmin=is_subadmin)

    await callback.message.edit_text(text, reply_markup=stt_settings_kb(conf, is_subadmin=is_subadmin), parse_mode="HTML")
    state_desc = "включено" if new_val else "выключено"
    await callback.answer(f"Распознавание речи {state_desc}")


@router.callback_query(F.data == "stt_cycle_lang")
async def cb_stt_cycle_lang(
    callback: CallbackQuery,
    db: Database,
    settings: Settings,
    stt_service: Optional[Any] = None,
    is_admin: bool = False,
    is_subadmin: bool = False,
) -> None:
    if not is_admin:
        await callback.answer("⚠️ Доступ только для администраторов.", show_alert=True)
        return

    lang_cycle = {"ru-RU": "multi", "multi": "en-US", "en-US": "ru-RU"}
    async with db.connect() as conn:
        config_repo = ConfigRepository(conn)
        curr = await config_repo.get_stt_config()
        current_lang = curr.get("stt_language", "ru-RU")
        new_lang = lang_cycle.get(current_lang, "ru-RU")
        await config_repo.set_stt_config(language=new_lang)
        if stt_service:
            stt_service.update_config(language_code=new_lang)
        text, conf = await _render_stt_settings(conn, settings, is_subadmin=is_subadmin)

    await callback.message.edit_text(text, reply_markup=stt_settings_kb(conf, is_subadmin=is_subadmin), parse_mode="HTML")
    await callback.answer(f"Язык изменен на: {new_lang}")


@router.callback_query(F.data == "stt_set_key")
async def cb_stt_set_key(
    callback: CallbackQuery,
    state: FSMContext,
    is_admin: bool = False,
    is_subadmin: bool = False,
) -> None:
    if not is_admin or is_subadmin:
        await callback.answer("⛔ Доступ к API-ключам разрешён только старшему администратору.", show_alert=True)
        return

    await state.set_state(AdminSTTStates.waiting_for_api_key)
    lines = [
        "🔑 <b>Ввод нового API-ключа NVIDIA (Whisper Large v3)</b>\n",
        "Отправьте ваш API-ключ сообщением в этот чат (например <code>nvapi-...</code>).",
        "<i>В целях безопасности ваше сообщение с ключом будет сразу удалено после сохранения.</i>",
    ]
    await callback.message.edit_text("\n".join(lines), reply_markup=llm_cancel_kb(), parse_mode="HTML")
    await callback.answer()


@router.message(AdminSTTStates.waiting_for_api_key)
async def proc_admin_stt_api_key(
    message: Message,
    state: FSMContext,
    db: Database,
    settings: Settings,
    stt_service: Optional[Any] = None,
    is_admin: bool = False,
    is_subadmin: bool = False,
) -> None:
    if not is_admin or is_subadmin:
        await state.clear()
        return

    raw_key = (message.text or "").strip()
    try:
        await message.delete()
    except Exception:
        pass

    if not raw_key:
        await message.answer("⚠️ Ключ не может быть пустым.")
        return

    async with db.connect() as conn:
        config_repo = ConfigRepository(conn)
        await config_repo.set_stt_config(api_key=raw_key)
        if stt_service:
            stt_service.update_config(api_key=raw_key)
        text, conf = await _render_stt_settings(conn, settings, is_subadmin=is_subadmin)

    await state.clear()
    await message.answer("✅ <b>API-ключ NVIDIA успешно сохранён!</b>\n\n" + text, reply_markup=stt_settings_kb(conf, is_subadmin=is_subadmin), parse_mode="HTML")


@router.callback_query(F.data == "stt_test")
async def cb_stt_test(
    callback: CallbackQuery,
    stt_service: Optional[Any] = None,
    is_admin: bool = False,
) -> None:
    if not is_admin:
        await callback.answer("⚠️ Доступ только для администраторов.", show_alert=True)
        return

    if not stt_service or not stt_service.is_available():
        await callback.answer("❌ STT сервис не активен или не задан API-ключ.", show_alert=True)
        return

    await callback.answer("⏳ Тестирование подключения к NVIDIA Riva...")
    try:
        # Generate 0.5s silent/sine WAV PCM
        import wave, io, struct, math
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            samples = [int(1000 * math.sin(2 * math.pi * 440 * i / 16000)) for i in range(8000)]
            wf.writeframes(struct.pack(f"<{len(samples)}h", *samples))
        test_wav = buf.getvalue()

        loop = asyncio.get_running_loop()
        res = await asyncio.to_thread(stt_service._sync_recognize, test_wav, "ru-RU")
        await callback.message.answer(
            "✅ <b>Тест NVIDIA Riva Whisper успешно пройден!</b>\n\n"
            f"• Статус соединения: <b>OK</b>\n"
            f"• Модель: <code>whisper-large-v3</code>\n"
            f"• Результат теста: <i>соединение активно</i>",
            parse_mode="HTML",
        )
    except Exception as e:
        logger.warning("STT Test failed: %s", e)
        await callback.message.answer(
            f"⚠️ <b>Ошибка при тестировании NVIDIA Whisper:</b>\n<code>{html.escape(str(e))}</code>",
            parse_mode="HTML",
        )
