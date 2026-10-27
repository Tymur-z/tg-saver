from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from bot.keyboards.inline import main_menu_kb
from config.settings import Settings
from database.connection import Database
from database.repositories.user_repo import UserRepository

logger = logging.getLogger(__name__)


def check_password_match(candidate: str, expected_password: str) -> bool:
    candidate = candidate.strip()
    if candidate == expected_password:
        return True
    if candidate.startswith("/start"):
        parts = candidate.split(maxsplit=1)
        if len(parts) > 1 and parts[1].strip() == expected_password:
            return True
        if "=" in candidate:
            parts = candidate.split("=", 1)
            if len(parts) > 1 and parts[1].strip() == expected_password:
                return True
    if candidate.startswith("/password"):
        parts = candidate.split(maxsplit=1)
        if len(parts) > 1 and parts[1].strip() == expected_password:
            return True
    return False


class UserAuthMiddleware(BaseMiddleware):

    def __init__(self, db: Database, settings: Settings) -> None:
        super().__init__()
        self.db = db
        self.settings = settings

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        if isinstance(event, Message) and event.chat.type == "channel":
            return await handler(event, data)

        if isinstance(event, Message) and event.chat.type in ("group", "supergroup"):
            return await handler(event, data)

        user = None
        if isinstance(event, Message) and event.from_user:
            user = event.from_user
        elif isinstance(event, CallbackQuery) and event.from_user:
            user = event.from_user

        if not user:
            return await handler(event, data)

        user_id = user.id
        is_owner = bool(self.settings.OWNER_ID > 0 and user_id == self.settings.OWNER_ID)

        if is_owner:
            async with self.db.connect() as conn:
                user_repo = UserRepository(conn)
                await user_repo.upsert_user(
                    user_id=user_id,
                    username=user.username,
                    first_name=user.first_name,
                    last_name=user.last_name,
                    role="owner",
                    is_authorized=True,
                    is_blocked=False,
                )
            data["user_role"] = "owner"
            data["is_admin"] = True
            data["is_owner"] = True
            return await handler(event, data)

        async with self.db.connect() as conn:
            user_repo = UserRepository(conn)
            db_user = await user_repo.get_user(user_id)
            password_required = await user_repo.is_password_required(self.settings.PASSWORD_REQUIRED)
            current_pw = await user_repo.get_access_password(self.settings.ACCESS_PASSWORD)

        if db_user and db_user.get("is_blocked"):
            if isinstance(event, Message):
                await event.answer("⛔ <b>Ваш аккаунт заблокирован администратором.</b>", parse_mode="HTML")
            elif isinstance(event, CallbackQuery):
                await event.answer("⛔ Ваш аккаунт заблокирован администратором.", show_alert=True)
            return None

        is_authorized = bool(db_user.get("is_authorized")) if db_user else False

        if password_required and not is_authorized:
            if isinstance(event, Message) and event.text:
                candidate = event.text.strip()
                if check_password_match(candidate, current_pw):
                    async with self.db.connect() as conn:
                        user_repo = UserRepository(conn)
                        await user_repo.upsert_user(
                            user_id=user_id,
                            username=user.username,
                            first_name=user.first_name,
                            last_name=user.last_name,
                            role="user",
                            is_authorized=True,
                            is_blocked=False,
                        )
                    await event.answer(
                        "🎉 <b>Пароль верный! Доступ успешно открыт.</b>\n\n"
                        "Добро пожаловать в систему управления пересылкой и аналитикой Telegram.\n"
                        "Выберите нужный раздел в меню ниже:",
                        reply_markup=main_menu_kb(is_admin=False),
                        parse_mode="HTML",
                    )
                    return None
                else:
                    async with self.db.connect() as conn:
                        user_repo = UserRepository(conn)
                        await user_repo.upsert_user(
                            user_id=user_id,
                            username=user.username,
                            first_name=user.first_name,
                            last_name=user.last_name,
                            role="guest",
                            is_authorized=False,
                            is_blocked=False,
                        )
                    if candidate == "/start" or candidate.startswith("/start"):
                        await event.answer(
                            "🔒 <b>Бот защищён паролем.</b>\n\n"
                            "Для получения доступа введите пароль в этот диалог:\n"
                            "<i>(Если вы не знаете пароль, обратитесь к администратору)</i>",
                            parse_mode="HTML",
                        )
                    else:
                        await event.answer(
                            "❌ <b>Неверный пароль.</b> Попробуйте ещё раз:",
                            parse_mode="HTML",
                        )
                    return None
            elif isinstance(event, CallbackQuery):
                await event.answer("🔒 Требуется ввод пароля доступа.", show_alert=True)
                return None

        role = db_user.get("role", "user") if db_user else "user"
        is_admin = role in ("admin", "owner") or (user_id in self.settings.admin_id_list)

        async with self.db.connect() as conn:
            user_repo = UserRepository(conn)
            await user_repo.upsert_user(
                user_id=user_id,
                username=user.username,
                first_name=user.first_name,
                last_name=user.last_name,
                role=role,
                is_authorized=True,
            )

        data["user_role"] = role
        data["is_admin"] = is_admin
        data["is_owner"] = False

        return await handler(event, data)
