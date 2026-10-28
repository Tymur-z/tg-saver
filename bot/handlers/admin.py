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
    admin_panel_kb,
    all_routes_kb,
    chat_moderation_detail_kb,
    llm_base_urls_select_kb,
    llm_cancel_kb,
    llm_models_select_kb,
    llm_settings_kb,
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
            "• /moderation — модерация матов и предупреждения нарушителей",
            "• /llm — настройка ИИ (модель, API-ключ, URL/IP)",
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
    f_on = "🟢 ВКЛ" if chat.get("profanity_filter_enabled") else "⚪ ВЫКЛ"
    w_on = "🟢 ВКЛ" if chat.get("profanity_warn_enabled") else "⚪ ВЫКЛ"
    d_on = "🟢 ВКЛ" if chat.get("profanity_delete_enabled") else "⚪ ВЫКЛ"
    ai_on = "🟢 ВКЛ" if chat.get("chat_ai_enabled") else "⚪ ВЫКЛ"

    lines = [
        f"🛡️ <b>Настройки модерации:</b> {title}",
        f"🆔 ID чата: <code>{chat_id}</code> (тип: <i>{c_type}</i>)\n",
        f"• <b>Фильтр ненормативной лексики:</b> {f_on}",
        f"• <b>Предупреждать нарушителя:</b> {w_on}",
        f"• <b>Удалять сообщения с матом:</b> {d_on}",
        f"• <b>Общение с ИИ (тег/ответ):</b> {ai_on}\n",
        "<i>Нажмите на кнопку ниже, чтобы переключить соответствующий параметр:</i>",
    ]
    text = "\n".join(lines)
    await callback.message.edit_text(text, reply_markup=chat_moderation_detail_kb(chat), parse_mode="HTML")
    await callback.answer()


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
        chat = await chat_repo.get_chat(chat_id)

    if not chat:
        await callback.answer("❌ Ошибка обновления.", show_alert=True)
        return

    title = chat.get("title") or f"ID {chat_id}"
    c_type = chat.get("chat_type", "group")
    f_on = "🟢 ВКЛ" if chat.get("profanity_filter_enabled") else "⚪ ВЫКЛ"
    w_on = "🟢 ВКЛ" if chat.get("profanity_warn_enabled") else "⚪ ВЫКЛ"
    d_on = "🟢 ВКЛ" if chat.get("profanity_delete_enabled") else "⚪ ВЫКЛ"
    ai_on = "🟢 ВКЛ" if chat.get("chat_ai_enabled") else "⚪ ВЫКЛ"

    lines = [
        f"🛡️ <b>Настройки модерации:</b> {title}",
        f"🆔 ID чата: <code>{chat_id}</code> (тип: <i>{c_type}</i>)\n",
        f"• <b>Фильтр ненормативной лексики:</b> {f_on}",
        f"• <b>Предупреждать нарушителя:</b> {w_on}",
        f"• <b>Удалять сообщения с матом:</b> {d_on}",
        f"• <b>Общение с ИИ (тег/ответ):</b> {ai_on}\n",
        "<i>Нажмите на кнопку ниже, чтобы переключить соответствующий параметр:</i>",
    ]
    text = "\n".join(lines)
    await callback.message.edit_text(text, reply_markup=chat_moderation_detail_kb(chat), parse_mode="HTML")
    await callback.answer("✅ Настройка обновлена")


class AdminLLMStates(StatesGroup):
    waiting_for_api_key = State()
    waiting_for_model = State()
    waiting_for_base_url = State()


async def _render_llm_settings(conn, settings: Settings) -> tuple[str, bool]:
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

    lines = [
        "🤖 <b>Панель управления ИИ и нейросетями (LLM)</b>\n",
        f"• <b>Статус ИИ:</b> {status_str}",
        f"• <b>Модель:</b> <code>{conf['llm_model']}</code>",
        f"• <b>Эндпоинт (URL / IP):</b> <code>{conf['llm_base_url']}</code>",
        f"• <b>API-ключ:</b> {key_masked}\n",
        "<i>Вы можете изменять API-ключ, модель или IP-адрес сервера прямо через Telegram без перезапуска бота:</i>",
    ]
    return "\n".join(lines), is_on


@router.message(Command("llm"))
@router.callback_query(F.data == "admin_llm_settings")
async def cmd_admin_llm_settings(
    event: Message | CallbackQuery,
    db: Database,
    settings: Settings,
    is_admin: bool = False,
    state: Optional[FSMContext] = None,
) -> None:
    if not is_admin:
        if isinstance(event, CallbackQuery):
            await event.answer("⚠️ Доступ только для администраторов.", show_alert=True)
        return

    if state:
        await state.clear()

    async with db.connect() as conn:
        text, is_on = await _render_llm_settings(conn, settings)

    kb = llm_settings_kb(is_on)
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
        text, is_on = await _render_llm_settings(conn, settings)

    profanity_detector.set_llm_enabled(new_val)
    await callback.message.edit_text(text, reply_markup=llm_settings_kb(is_on), parse_mode="HTML")
    state_desc = "включен" if new_val else "отключен"
    await callback.answer(f"ИИ {state_desc}")


@router.callback_query(F.data == "llm_set_key")
async def cb_llm_set_key(callback: CallbackQuery, state: FSMContext, is_admin: bool = False) -> None:
    if not is_admin:
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
        text, is_on = await _render_llm_settings(conn, settings)

    llm_client.update_config(api_key=new_key)
    await message.answer(f"✅ <b>API-ключ успешно обновлен и сохранён!</b>\n\n{text}", reply_markup=llm_settings_kb(is_on), parse_mode="HTML")


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
        text, is_on = await _render_llm_settings(conn, settings)

    llm_client.update_config(model=model_name)
    await callback.message.edit_text(text, reply_markup=llm_settings_kb(is_on), parse_mode="HTML")
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
        text, is_on = await _render_llm_settings(conn, settings)

    llm_client.update_config(model=model_name)
    await message.answer(f"✅ <b>Модель установлена:</b> <code>{model_name}</code>\n\n{text}", reply_markup=llm_settings_kb(is_on), parse_mode="HTML")


@router.callback_query(F.data == "llm_select_url")
async def cb_llm_select_url(callback: CallbackQuery, is_admin: bool = False) -> None:
    if not is_admin:
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
        text, is_on = await _render_llm_settings(conn, settings)

    llm_client.update_config(base_url=url)
    await callback.message.edit_text(text, reply_markup=llm_settings_kb(is_on), parse_mode="HTML")
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
        text, is_on = await _render_llm_settings(conn, settings)

    llm_client.update_config(base_url=url)
    await message.answer(f"✅ <b>Эндпоинт сохранён:</b> <code>{url}</code>\n\n{text}", reply_markup=llm_settings_kb(is_on), parse_mode="HTML")


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
