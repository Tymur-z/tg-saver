from __future__ import annotations

import logging
from typing import List

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from config.settings import Settings
from database.connection import Database
from database.repositories.profile_repo import ProfileRepository
from analytics.comparator import StyleComparator
from analytics.report_generator import ReportGenerator, make_progress_bar
from bot.keyboards.inline import main_menu_kb, my_style_kb

logger = logging.getLogger(__name__)
router = Router(name="analytics_router")


@router.message(Command("analytics"))
@router.callback_query(F.data == "nav_analytics")
async def cmd_analytics(event: Message | CallbackQuery, db: Database, settings: Settings, is_admin: bool = False) -> None:
    user_id = event.from_user.id if event.from_user else 0

    async with db.connect() as conn:
        repo = ProfileRepository(conn)
        profile = await repo.get_profile(user_id, chat_id=0)

    is_owner = bool(settings.OWNER_ID > 0 and user_id == settings.OWNER_ID)
    user_label = "Владелец бота" if is_owner else "Ваш личный стиль"

    if not profile or profile.get("sample_count", 0) == 0:
        text = (
            "📊 <b>Ваш профиль стиля общения:</b>\n\n"
            "ℹ️ Данные пока не сформированы.\n"
            "Бот анализирует вашу письменную речь по сообщениям, отправленным в <b>подключенные группы и каналы</b>.\n\n"
            "<i>Отправьте сообщения в чаты, где присутствует бот, чтобы сформировать стиль.</i>"
        )
    else:
        text = ReportGenerator.generate_profile_report(profile, user_label=user_label)

    kb = my_style_kb(is_admin=is_admin)

    if isinstance(event, Message):
        await event.answer(text, reply_markup=kb, parse_mode="HTML")
    else:
        await event.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
        await event.answer()


@router.callback_query(F.data == "admin_all_profiles")
@router.message(Command("all_profiles"))
async def cb_admin_all_profiles(event: Message | CallbackQuery, db: Database, is_admin: bool = False) -> None:
    if not is_admin:
        if isinstance(event, CallbackQuery):
            await event.answer("⛔ Доступ разрешён только администраторам.", show_alert=True)
        else:
            await event.answer("⛔ <b>Доступ разрешён только администраторам.</b>", parse_mode="HTML")
        return

    async with db.connect() as conn:
        repo = ProfileRepository(conn)
        profiles = await repo.list_profiles(limit=50)

    lines = [
        "📊 <b>Анализ стилей общения участников (Админ-обзор)</b>",
        f"👥 Всего сформировано профилей: <b>{len(profiles)}</b>\n",
    ]
    buttons: List[List[InlineKeyboardButton]] = []

    if not profiles:
        lines.append("<i>Данные стилометрии ещё не сформированы. Бот анализирует сообщения из групп.</i>")
    else:
        lines.append("Выберите участника для просмотра речевого портрета:\n")
        bot = event.bot
        from database.repositories.user_repo import UserRepository

        TELEGRAM_SYSTEM_BOT_IDS = {1087968824, 777000, 136817688}
        display_idx = 1
        for p in profiles:
            uid = p["user_id"]
            if uid in TELEGRAM_SYSTEM_BOT_IDS:
                continue
            idx = display_idx
            display_idx += 1
            first_name = p.get("first_name") or ""
            last_name = p.get("last_name") or ""
            full_name = f"{first_name} {last_name}".strip()
            uname = f"@{p['username']}" if p.get("username") else ""

            # Try to resolve user name if missing
            if not full_name and not uname and bot:
                try:
                    chat_info = await bot.get_chat(uid)
                    if chat_info:
                        full_name = chat_info.full_name or ""
                        if chat_info.username:
                            uname = f"@{chat_info.username}"
                        async with db.connect() as conn:
                            await UserRepository(conn).upsert_user(
                                user_id=uid,
                                username=chat_info.username,
                                first_name=chat_info.first_name,
                                last_name=chat_info.last_name,
                            )
                except Exception:
                    pass

            is_owner = bool(p.get("is_owner"))
            role_icon = "👑" if is_owner else "👤"
            owner_badge = " <b>[Владелец]</b>" if is_owner else ""

            if full_name and uname:
                name_header = f"<b>{full_name}</b> ({uname})"
                btn_name = full_name
            elif full_name:
                name_header = f"<b>{full_name}</b>"
                btn_name = full_name
            elif uname:
                name_header = f"<b>{uname}</b>"
                btn_name = uname
            else:
                name_header = f"ID: <code>{uid}</code>"
                btn_name = f"ID {uid}"

            samples = p.get("sample_count", 0)
            avg_len = p.get("avg_sentence_len", 0.0)

            lines.append(
                f"{idx}. {role_icon} {name_header}{owner_badge}\n"
                f"    └ ID: <code>{uid}</code> • Сообщений: <b>{samples}</b> • Слов/предл: <b>{avg_len:.1f}</b>"
            )

            # Clean button text
            short_name = btn_name if len(btn_name) <= 18 else btn_name[:17] + "…"
            btn_label = f"{role_icon} {short_name} ({samples})"
            buttons.append([InlineKeyboardButton(text=btn_label, callback_data=f"view_profile:{uid}")])

    buttons.append([
        InlineKeyboardButton(text="🔄 Обновить", callback_data="admin_all_profiles"),
        InlineKeyboardButton(text="📊 Мой личный стиль", callback_data="nav_analytics"),
    ])
    buttons.append([
        InlineKeyboardButton(text="⬅️ В админ-панель", callback_data="nav_admin"),
    ])
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    text = "\n".join(lines)

    if isinstance(event, Message):
        await event.answer(text, reply_markup=kb, parse_mode="HTML")
    else:
        await event.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
        await event.answer()


@router.callback_query(F.data.startswith("view_profile:"))
async def cb_admin_view_profile(callback: CallbackQuery, db: Database, settings: Settings, is_admin: bool = False) -> None:
    if not is_admin:
        await callback.answer("⛔ Доступ только для администраторов.", show_alert=True)
        return

    target_uid = int(callback.data.split(":")[1])
    async with db.connect() as conn:
        repo = ProfileRepository(conn)
        profile = await repo.get_profile(target_uid, chat_id=0)

    if not profile:
        await callback.answer("❌ Профиль не найден в базе.", show_alert=True)
        return

    is_owner = bool(settings.OWNER_ID > 0 and target_uid == settings.OWNER_ID)
    fn = profile.get("first_name") or ""
    ln = profile.get("last_name") or ""
    full_name = f"{fn} {ln}".strip()
    un = f"@{profile['username']}" if profile.get("username") else ""
    if full_name and un:
        u_display = f"{full_name} ({un})"
    elif full_name:
        u_display = full_name
    elif un:
        u_display = un
    else:
        u_display = f"ID {target_uid}"

    label = f"{u_display} [ID: {target_uid}]" + (" 👑 [Владелец]" if is_owner else "")
    report_html = ReportGenerator.generate_profile_report(profile, user_label=label)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Ко всем профилям", callback_data="admin_all_profiles")],
        [InlineKeyboardButton(text="⬅️ В админ-панель", callback_data="nav_admin")],
    ])
    await callback.message.edit_text(report_html, reply_markup=kb, parse_mode="HTML")
    await callback.answer()


@router.message(Command("profile"))
async def cmd_profile(message: Message, db: Database, settings: Settings, is_admin: bool = False) -> None:
    parts = message.text.strip().split(maxsplit=1)
    caller_id = message.from_user.id if message.from_user else 0
    target_user_id = caller_id

    if is_admin and len(parts) > 1 and parts[1].strip().isdigit():
        target_user_id = int(parts[1].strip())

    async with db.connect() as conn:
        repo = ProfileRepository(conn)
        profile = await repo.get_profile(target_user_id, chat_id=0)

    if not profile or profile.get("sample_count", 0) == 0:
        who = "вашего стиля" if target_user_id == caller_id else f"пользователя <code>{target_user_id}</code>"
        await message.answer(
            f"ℹ️ Профиль для {who} пока не сформирован (нет данных из подключенных групп).",
            parse_mode="HTML",
        )
        return

    is_owner = (target_user_id == settings.OWNER_ID)
    label = "Владелец бота" if is_owner else ("Ваш личный стиль" if target_user_id == caller_id else f"ID {target_user_id}")
    report_html = ReportGenerator.generate_profile_report(profile, user_label=label)

    await message.answer(report_html, reply_markup=my_style_kb(is_admin=is_admin), parse_mode="HTML")


@router.message(Command("compare"))
async def cmd_compare(message: Message, db: Database, settings: Settings, is_admin: bool = False) -> None:
    parts = message.text.strip().split(maxsplit=2)
    caller_id = message.from_user.id if message.from_user else 0
    target_user_id = caller_id
    candidate_text = ""

    if is_admin and len(parts) >= 3 and parts[1].strip().isdigit():
        target_user_id = int(parts[1].strip())
        candidate_text = parts[2].strip()
    elif len(parts) >= 2:
        candidate_text = message.text.strip().split(maxsplit=1)[1].strip()

    if not candidate_text:
        await message.answer(
            "ℹ️ <b>Использование:</b> <code>/compare &lt;текст для сравнения&gt;</code>\n\n"
            "Команда сравнивает стилистику переданного текста с вашим накопленным стилем речи.",
            parse_mode="HTML",
        )
        return

    async with db.connect() as conn:
        repo = ProfileRepository(conn)
        baseline = await repo.get_profile(target_user_id, chat_id=0)

    if not baseline or baseline.get("sample_count", 0) < 10:
        who = "вашего стиля" if target_user_id == caller_id else f"пользователя {target_user_id}"
        await message.answer(
            f"⚠️ Для сравнения недостаточно базовых данных {who} (нужно минимум 10 сообщений в подключенных группах).",
            parse_mode="HTML",
        )
        return

    result = StyleComparator.compare(candidate_text, baseline)

    sim = result["similarity_score"]
    bar = make_progress_bar(int(sim), 100, length=10)
    div = "━━━━━━━━━━━━━━━━━━━━━━"
    target_label = "вашим стилем" if target_user_id == caller_id else f"стилем ID {target_user_id}"
    stats = result["candidate_stats"]
    dot_str = "Да" if stats["has_trailing_dot"] else "Нет"

    lines = [
        f"🔍 <b>Сравнение текста с {target_label}:</b>\n{div}",
        f"📊 <b>Соответствие стилю:</b> <code>[{bar}] {sim:.1f}%</code>\n{div}",
        "💡 <b>Особенности и отличия:</b>",
    ]
    for obs in result["observations"]:
        lines.append(f"• {obs}")

    lines.extend([
        div,
        f"📏 <b>Параметры фрагмента:</b> <code>{stats['words']} слов</code> • <code>{stats['avg_sentence_len']:.1f} сл/предл</code> • Точка: <i>{dot_str}</i>",
    ])

    await message.answer("\n".join(lines), parse_mode="HTML")


@router.message(Command("mimic"))
async def cmd_mimic(message: Message, db: Database, settings: Settings, is_admin: bool = False) -> None:
    parts = message.text.strip().split(maxsplit=1)
    caller_id = message.from_user.id if message.from_user else 0
    target_user_id = caller_id

    if is_admin and len(parts) > 1 and parts[1].strip().isdigit():
        target_user_id = int(parts[1].strip())

    async with db.connect() as conn:
        repo = ProfileRepository(conn)
        baseline = await repo.get_profile(target_user_id, chat_id=0)

    if not baseline or baseline.get("sample_count", 0) < 10:
        who = "вашего стиля" if target_user_id == caller_id else f"пользователя {target_user_id}"
        await message.answer(
            f"⚠️ Базовый профиль {who} ещё не накоплен (нужно от 10 сообщений в подключенных группах).",
            parse_mode="HTML",
        )
        return

    div = "━━━━━━━━━━━━━━━━━━━━━━"
    who_label = "вашего стиля" if target_user_id == caller_id else f"пользователя ID {target_user_id}"
    guidelines = StyleComparator.generate_mimicry_prompt(baseline)
    text = (
        f"🎭 <b>Промпт имитации тональности ({who_label}):</b>\n{div}\n"
        "<i>Скопируйте блок ниже в System Prompt нейросети:</i>\n\n"
        f"<pre>{guidelines}</pre>"
    )
    await message.answer(text, parse_mode="HTML")
