from __future__ import annotations

import logging
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from config.settings import Settings
from database.connection import Database
from database.repositories.profile_repo import ProfileRepository
from analytics.comparator import StyleComparator
from analytics.report_generator import ReportGenerator
from bot.keyboards.inline import main_menu_kb

logger = logging.getLogger(__name__)
router = Router(name="analytics_router")


@router.message(Command("analytics"))
@router.callback_query(F.data == "nav_analytics")
async def cmd_analytics(event: Message | CallbackQuery, db: Database, settings: Settings, is_admin: bool = False) -> None:
    user_id = event.from_user.id if event.from_user else 0

    if not is_admin:
        async with db.connect() as conn:
            repo = ProfileRepository(conn)
            profile = await repo.get_profile(user_id, chat_id=0)

        if not profile:
            text = (
                "📊 <b>Ваш профиль стиля общения:</b>\n\n"
                "ℹ️ Данные пока не сформированы. Отправьте несколько сообщений в подключенные группы."
            )
        else:
            text = ReportGenerator.generate_profile_report(profile, user_label="Ваш личный стиль")

        if isinstance(event, Message):
            await event.answer(text, reply_markup=main_menu_kb(is_admin=False), parse_mode="HTML")
        else:
            await event.message.edit_text(text, reply_markup=main_menu_kb(is_admin=False), parse_mode="HTML")
            await event.answer()
        return

    async with db.connect() as conn:
        repo = ProfileRepository(conn)
        profiles = await repo.list_profiles(limit=25)

    lines = ["📊 <b>Анализ стилей общения участников (Админ-обзор)</b>\n"]
    if not profiles:
        lines.append("Данные стилометрии ещё не накоплены.")
        lines.append("\n<i>💡 Отправьте сообщения в подключенные группы или импортируйте историю чата.</i>")
    else:
        lines.append("Выберите пользователя для просмотра отчёта:\n")
        for p in profiles:
            owner_mark = " 👑 [Владелец]" if p.get("is_owner") else ""
            lines.append(
                f"• ID: <code>{p['user_id']}</code>{owner_mark} — "
                f"Сообщений: <b>{p['sample_count']}</b>, "
                f"Слов/предл: <b>{p.get('avg_sentence_len', 0):.1f}</b> "
                f"(<code>/profile {p['user_id']}</code>)"
            )

    text = "\n".join(lines)
    if isinstance(event, Message):
        await event.answer(text, reply_markup=main_menu_kb(is_admin=True), parse_mode="HTML")
    else:
        await event.message.edit_text(text, reply_markup=main_menu_kb(is_admin=True), parse_mode="HTML")
        await event.answer()


@router.message(Command("profile"))
async def cmd_profile(message: Message, db: Database, settings: Settings, is_admin: bool = False) -> None:
    parts = message.text.strip().split(maxsplit=1)
    target_user_id = message.from_user.id if message.from_user else 0

    if is_admin and len(parts) > 1 and parts[1].strip().isdigit():
        target_user_id = int(parts[1].strip())

    async with db.connect() as conn:
        repo = ProfileRepository(conn)
        profile = await repo.get_profile(target_user_id, chat_id=0)

    if not profile:
        await message.answer(
            f"ℹ️ Профиль для пользователя <code>{target_user_id}</code> пока не сформирован (нет данных).",
            parse_mode="HTML",
        )
        return

    is_owner = (target_user_id == settings.OWNER_ID)
    label = "Владелец бота" if is_owner else (f"Ваш стиль" if target_user_id == message.from_user.id else f"ID {target_user_id}")
    report_html = ReportGenerator.generate_profile_report(profile, user_label=label)

    await message.answer(report_html, parse_mode="HTML")


@router.message(Command("compare"))
async def cmd_compare(message: Message, db: Database, settings: Settings) -> None:
    parts = message.text.strip().split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        await message.answer(
            "ℹ️ <b>Использование:</b> <code>/compare &lt;текст для сравнения&gt;</code>\n\n"
            "Команда сравнивает стилистику переданного текста с вашим базовым профилем.",
            parse_mode="HTML",
        )
        return

    candidate_text = parts[1].strip()

    async with db.connect() as conn:
        repo = ProfileRepository(conn)
        baseline = await repo.get_profile(settings.OWNER_ID, chat_id=0)

    if not baseline or baseline.get("sample_count", 0) < 10:
        await message.answer(
            "⚠️ Для сравнения недостаточно базовых данных владельца (нужно минимум 10 сообщений в базе).",
            parse_mode="HTML",
        )
        return

    result = StyleComparator.compare(candidate_text, baseline)

    lines = [
        f"🔍 <b>Результат сравнения со стилем владельца:</b>",
        f"• Соответствие стилю: <b>{result['similarity_score']}%</b>\n",
        "<b>Наблюдения и отличия:</b>",
    ]
    for obs in result["observations"]:
        lines.append(f"• {obs}")

    lines.append("\n<i>Параметры оцениваемого фрагмента:</i>")
    stats = result["candidate_stats"]
    lines.append(f"Слов: {stats['words']}, Слов/предл: {stats['avg_sentence_len']:.1f}, Точка в конце: {'Да' if stats['has_trailing_dot'] else 'Нет'}")

    await message.answer("\n".join(lines), parse_mode="HTML")


@router.message(Command("mimic"))
async def cmd_mimic(message: Message, db: Database, settings: Settings) -> None:
    async with db.connect() as conn:
        repo = ProfileRepository(conn)
        baseline = await repo.get_profile(settings.OWNER_ID, chat_id=0)

    if not baseline or baseline.get("sample_count", 0) < 10:
        await message.answer(
            "⚠️ Базовый профиль владельца ещё не накоплен (нужно от 10 сообщений).",
            parse_mode="HTML",
        )
        return

    guidelines = StyleComparator.generate_mimicry_prompt(baseline)
    await message.answer(f"<pre>{guidelines}</pre>", parse_mode="HTML")
