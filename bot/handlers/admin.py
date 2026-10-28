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
from bot.keyboards.inline import (
    admin_panel_kb,
    all_routes_kb,
    main_menu_kb,
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

    text = (
        f"👋 <b>Добро пожаловать, {user_name}!</b> [{role_badge}]\n\n"
        "Ваш персональный кабинет управления пересылкой и аналитикой Telegram:\n"
        "1. <b>Индивидуальные маршруты:</b> настройка собственных пайплайнов пересылки.\n"
        "2. <b>Фильтрация контента:</b> выбор конкретных типов медиа, стоп-слов и очистка текста.\n"
        "3. <b>Аналитика стиля:</b> изучение собственной письменной речи и генерация промптов тональности.\n\n"
        "Используйте кнопки меню ниже для перехода:"
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
            "• /all_routes — просмотр всех маршрутов всех пользователей",
            "• /all_chats — просмотр всех каналов и групп бота",
            "• /status — статус очередей, пауза и статистика",
        ])

    await message.answer("\n".join(lines), parse_mode="HTML")


@router.message(Command("admin"))
@router.callback_query(F.data == "nav_admin")
async def cmd_admin_panel(event: Message | CallbackQuery, db: Database, settings: Settings, is_admin: bool = False) -> None:
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

    text = (
        "👑 <b>Панель Супер-Администратора</b>\n\n"
        f"• Пользователей в системе: <code>{users_cnt}</code>\n"
        f"• Всего маршрутов (все авторы): <code>{routes_cnt}</code>\n"
        f"• Подключенных чатов и каналов: <code>{chats_cnt}</code>\n"
        f"• Пароль доступа: {pw_status}\n\n"
        "Выберите нужный раздел для управления:"
    )

    if isinstance(event, Message):
        await event.answer(text, reply_markup=admin_panel_kb(), parse_mode="HTML")
    else:
        await event.message.edit_text(text, reply_markup=admin_panel_kb(), parse_mode="HTML")
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
async def cb_user_view(callback: CallbackQuery, db: Database, is_admin: bool = False) -> None:
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

    await callback.message.edit_text(
        text,
        reply_markup=user_card_kb(target, is_owner=(target.get("role") == "owner")),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("user_block:"))
async def cb_user_block(callback: CallbackQuery, db: Database, is_admin: bool = False) -> None:
    if not is_admin:
        return
    target_id = int(callback.data.split(":")[1])
    async with db.connect() as conn:
        user_repo = UserRepository(conn)
        await user_repo.set_blocked(target_id, True)

    await callback.answer("🚫 Пользователь заблокирован!", show_alert=True)
    await cb_user_view(callback, db, is_admin=True)


@router.callback_query(F.data.startswith("user_unblock:"))
async def cb_user_unblock(callback: CallbackQuery, db: Database, is_admin: bool = False) -> None:
    if not is_admin:
        return
    target_id = int(callback.data.split(":")[1])
    async with db.connect() as conn:
        user_repo = UserRepository(conn)
        await user_repo.set_blocked(target_id, False)

    await callback.answer("✅ Пользователь разблокирован!", show_alert=True)
    await cb_user_view(callback, db, is_admin=True)


@router.callback_query(F.data.startswith("user_role:"))
async def cb_user_role(callback: CallbackQuery, db: Database, is_admin: bool = False) -> None:
    if not is_admin:
        return
    parts = callback.data.split(":")
    target_id = int(parts[1])
    new_role = parts[2]

    async with db.connect() as conn:
        user_repo = UserRepository(conn)
        await user_repo.set_role(target_id, new_role)

    await callback.answer(f"Роль изменена на: {new_role}!", show_alert=True)
    await cb_user_view(callback, db, is_admin=True)


@router.callback_query(F.data.startswith("user_reset_auth:"))
async def cb_user_reset_auth(callback: CallbackQuery, db: Database, is_admin: bool = False) -> None:
    if not is_admin:
        return
    target_id = int(callback.data.split(":")[1])
    async with db.connect() as conn:
        user_repo = UserRepository(conn)
        await user_repo.set_authorized(target_id, False)

    await callback.answer("🔑 Авторизация сброшена. Пользователь должен ввести пароль повторно.", show_alert=True)
    await cb_user_view(callback, db, is_admin=True)


@router.message(Command("all_routes"))
@router.callback_query(F.data == "admin_all_routes")
async def cmd_admin_all_routes(event: Message | CallbackQuery, db: Database, is_admin: bool = False) -> None:
    if not is_admin:
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
async def cmd_admin_all_chats(event: Message | CallbackQuery, db: Database, is_admin: bool = False) -> None:
    if not is_admin:
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
async def cmd_admin_password(event: Message | CallbackQuery, db: Database, settings: Settings, is_admin: bool = False) -> None:
    if not is_admin:
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
async def cb_admin_toggle_pw_req(callback: CallbackQuery, db: Database, settings: Settings, is_admin: bool = False) -> None:
    if not is_admin:
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
async def cmd_status(event: Message | CallbackQuery, db: Database, queue: ForwardQueue, is_admin: bool = False) -> None:
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

    text = (
        f"⚙️ <b>Статус системы</b>\n\n"
        f"• Режим работы: {status_str}\n"
        f"• Пользователей: <code>{users_cnt}</code>\n"
        f"• Активных маршрутов: <code>{active_routes_cnt}</code> (всего: <code>{len(routes)}</code>)\n"
        f"• Сообщений в очереди отправки: <code>{queue_len}</code>\n\n"
        f"📈 <b>Статистика пересылки (Forward Logs):</b>\n"
        f"• Успешно отправлено: <code>{stats.get('SENT', 0)}</code>\n"
        f"• Отфильтровано: <code>{stats.get('FILTERED', 0)}</code>\n"
        f"• Ошибок отправки: <code>{stats.get('FAILED', 0)}</code>\n"
        f"• Всего зарегистрировано: <code>{stats.get('TOTAL', 0)}</code>"
    )

    kb = admin_panel_kb() if is_admin else main_menu_kb(is_admin=False)
    if isinstance(event, Message):
        await event.answer(text, reply_markup=kb, parse_mode="HTML")
    else:
        await event.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
        await event.answer()


@router.message(Command("pause"))
async def cmd_pause(message: Message, db: Database, is_admin: bool = False) -> None:
    if not is_admin:
        await message.answer("⛔ Команда доступна только администраторам.")
        return
    async with db.connect() as conn:
        repo = ProfileRepository(conn)
        await repo.set_system_paused(True)
    await message.answer("⏸️ <b>Обработка сообщений и пересылка временно приостановлены.</b>", parse_mode="HTML")


@router.message(Command("resume"))
async def cmd_resume(message: Message, db: Database, is_admin: bool = False) -> None:
    if not is_admin:
        await message.answer("⛔ Команда доступна только администраторам.")
        return
    async with db.connect() as conn:
        repo = ProfileRepository(conn)
        await repo.set_system_paused(False)
    await message.answer("▶️ <b>Обработка сообщений возобновлена.</b>", parse_mode="HTML")


@router.callback_query(F.data == "nav_main")
async def cb_main_menu(callback: CallbackQuery, is_admin: bool = False) -> None:
    await callback.message.edit_text(
        "Главная панель управления:",
        reply_markup=main_menu_kb(is_admin=is_admin),
    )
    await callback.answer()
