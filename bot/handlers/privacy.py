from __future__ import annotations

import logging
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from config.settings import Settings
from database.connection import Database
from database.repositories.profile_repo import ProfileRepository
from bot.keyboards.inline import confirm_delete_kb, main_menu_kb, privacy_menu_kb

logger = logging.getLogger(__name__)
router = Router(name="privacy_router")


@router.message(Command("privacy"))
@router.callback_query(F.data == "nav_privacy")
async def cmd_privacy(event: Message | CallbackQuery, db: Database, settings: Settings, is_admin: bool = False) -> None:
    async with db.connect() as conn:
        repo = ProfileRepository(conn)
        exclusions = await repo.list_exclusions()

    lines = [
        "🔒 <b>Политика конфиденциальности и хранение данных</b>\n",
        "• Тексты сообщений и медиафайлы <b>не сохраняются</b> в базу данных.",
        f"• <b>Срок ротации логов пересылки:</b> <code>{settings.DATA_RETENTION_DAYS} дней</code>.",
        "• <b>Анализ стиля:</b> выполняется локально в оперативной памяти с фиксацией исключительно агрегированных числовых дескрипторов.\n",
    ]

    if exclusions:
        lines.append("🚫 <b>Активные исключения (Opt-Out):</b>")
        for exc in exclusions:
            lines.append(f"• {exc['entity_type'].upper()}: <code>{exc['entity_id']}</code>")
        lines.append("")
    else:
        lines.append("🚫 Исключения пока не настроены.\n")

    lines.append("Используйте команды:\n"
                 "• <code>/exclude_user &lt;id&gt;</code> — исключить пользователя\n"
                 "• <code>/exclude_chat &lt;id&gt;</code> — исключить чат\n"
                 "• <code>/delete_data</code> — безвозвратно удалить свой профиль")

    text = "\n".join(lines)
    kb = privacy_menu_kb()

    if isinstance(event, Message):
        await event.answer(text, reply_markup=kb, parse_mode="HTML")
    else:
        await event.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
        await event.answer()


@router.message(Command("exclude_user"))
async def cmd_exclude_user(message: Message, db: Database, is_admin: bool = False) -> None:
    if not is_admin:
        await message.answer("⛔ Команда доступна только администраторам.")
        return
    parts = message.text.strip().split()
    if len(parts) < 2 or not parts[1].lstrip("-").isdigit():
        await message.answer("❌ Укажите корректный User ID: <code>/exclude_user 12345678</code>", parse_mode="HTML")
        return

    user_id = int(parts[1])
    async with db.connect() as conn:
        repo = ProfileRepository(conn)
        await repo.set_exclusion("user", user_id, True)
        await repo.delete_user_profile(user_id)

    await message.answer(f"✅ Пользователь <code>{user_id}</code> исключен из аналитики, его профиль стерт.", parse_mode="HTML")


@router.message(Command("exclude_chat"))
async def cmd_exclude_chat(message: Message, db: Database, is_admin: bool = False) -> None:
    if not is_admin:
        await message.answer("⛔ Команда доступна только администраторам.")
        return
    parts = message.text.strip().split()
    if len(parts) < 2 or not parts[1].lstrip("-").isdigit():
        await message.answer("❌ Укажите корректный Chat ID: <code>/exclude_chat -1001234567890</code>", parse_mode="HTML")
        return

    chat_id = int(parts[1])
    async with db.connect() as conn:
        repo = ProfileRepository(conn)
        await repo.set_exclusion("chat", chat_id, True)

    await message.answer(f"✅ Чат <code>{chat_id}</code> исключен из аналитики сообщений.", parse_mode="HTML")


@router.message(Command("delete_data"))
@router.callback_query(F.data == "priv_del_my")
async def cmd_delete_data(event: Message | CallbackQuery) -> None:
    text = (
        "⚠️ <b>Подтверждение удаления данных</b>\n\n"
        "Вы действительно хотите безвозвратно удалить свой накопленный профиль стиля общения?\n"
        "Действие необратимо."
    )
    kb = confirm_delete_kb("my")
    if isinstance(event, Message):
        await event.answer(text, reply_markup=kb, parse_mode="HTML")
    else:
        await event.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
        await event.answer()


@router.callback_query(F.data == "priv_del_all")
async def cb_delete_all_prompt(callback: CallbackQuery, is_admin: bool = False) -> None:
    if not is_admin:
        await callback.answer("⛔ Очистка всей базы доступна только администраторам.", show_alert=True)
        return
    text = (
        "🚨 <b>ВНИМАНИЕ! Полная очистка аналитической базы!</b>\n\n"
        "Будут безвозвратно удалены профили ВСЕХ участников во всех чатах.\n"
        "Подтверждаете действие?"
    )
    await callback.message.edit_text(text, reply_markup=confirm_delete_kb("all"), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("confirm_del:"))
async def cb_confirm_delete(callback: CallbackQuery, db: Database) -> None:
    action_type = callback.data.split(":")[1]
    async with db.connect() as conn:
        repo = ProfileRepository(conn)
        if action_type == "my":
            user_id = callback.from_user.id
            deleted = await repo.delete_user_profile(user_id)
            msg = f"✅ Удалено записей вашего профиля: {deleted}."
        else:
            deleted = await repo.delete_all_profiles()
            msg = f"✅ Вся аналитическая база профилей успешно очищена (удалено записей: {deleted})."

    await callback.message.edit_text(msg, reply_markup=main_menu_kb())
    await callback.answer()
