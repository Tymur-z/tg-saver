from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, List, Optional

from aiogram import Router
from aiogram.types import Message

from config.settings import Settings
from database.connection import Database
from database.repositories.chat_repo import ChatRepository
from database.repositories.route_repo import RouteRepository
from forwarder.engine import ForwardEngine
from forwarder.media_handler import MediaHandler
from analytics.profiler import StyleProfiler
from moderation.companion import ChatCompanion
from moderation.profanity import ProfanityDetector

logger = logging.getLogger(__name__)
router = Router(name="forward_router")


@router.channel_post()
async def handle_channel_post(
    message: Message,
    forward_engine: ForwardEngine,
    album_messages: Optional[List[Message]] = None,
) -> None:
    try:
        await forward_engine.process_incoming_message(message, album_messages=album_messages)
    except Exception as e:
        logger.exception("Error processing channel post %s: %s", message.message_id, e)


@router.message()
async def handle_incoming_message(
    message: Message,
    forward_engine: ForwardEngine,
    style_profiler: StyleProfiler,
    settings: Settings,
    db: Database,
    profanity_detector: Optional[ProfanityDetector] = None,
    companion: Optional[ChatCompanion] = None,
    album_messages: Optional[List[Message]] = None,
) -> None:
    if isinstance(getattr(message, "migrate_to_chat_id", None), int):
        try:
            async with db.connect() as conn:
                await RouteRepository(conn).migrate_chat_id(message.chat.id, message.migrate_to_chat_id)
            logger.info("Chat %s migrated to %s, routes updated.", message.chat.id, message.migrate_to_chat_id)
        except Exception as e:
            logger.exception("Could not apply chat migration for %s: %s", message.chat.id, e)
        return

    # Ignore commands
    msg_text = message.text or message.caption
    if msg_text and msg_text.startswith("/"):
        return

    chat = None
    is_profane = False

    if message.chat.type in ("group", "supergroup"):
        try:
            async with db.connect() as conn:
                chat_repo = ChatRepository(conn)
                chat = await chat_repo.get_chat(message.chat.id)
                if not chat:
                    await chat_repo.ensure_chat_exists(
                        chat_id=message.chat.id,
                        title=message.chat.title or f"Chat {message.chat.id}",
                        chat_type=message.chat.type,
                        username=message.chat.username,
                    )
                    chat = await chat_repo.get_chat(message.chat.id)

            if chat and chat.get("profanity_filter_enabled") and profanity_detector:
                text_to_check = MediaHandler.get_text_or_caption(message)
                if text_to_check and text_to_check.strip():
                    prof_result = await profanity_detector.check_text(text_to_check)
                    if prof_result.is_profane:
                        is_profane = True
                        logger.info(
                            "Profanity detected in chat %s from user %s: %s (%s)",
                            message.chat.id,
                            message.from_user.id if message.from_user else "unknown",
                            prof_result.reason,
                            prof_result.method,
                        )
                        if chat.get("profanity_delete_enabled"):
                            try:
                                await message.delete()
                            except Exception as del_err:
                                logger.warning("Could not delete message in %s: %s", message.chat.id, del_err)

                        if chat.get("profanity_warn_enabled"):
                            user_mention = message.from_user.mention_html() if message.from_user else "Участник"
                            warn_text = (
                                f"⚠️ <b>Предупреждение о нарушении правил</b>\n\n"
                                f"{user_mention}, пожалуйста, соблюдайте культуру общения и воздержитесь от ненормативной лексики."
                            )
                            try:
                                await message.answer(warn_text)
                            except Exception as warn_err:
                                logger.warning("Could not send warning in %s: %s", message.chat.id, warn_err)
        except Exception as mod_err:
            logger.exception("Error during chat settings check for message %s: %s", message.message_id, mod_err)

    # Save to context buffer for companion awareness
    if companion and not is_profane and msg_text:
        u_name = message.from_user.full_name if message.from_user else "Участник"
        companion.context_buffer.add_message(
            chat_id=message.chat.id,
            user_id=message.from_user.id if message.from_user else 0,
            user_name=u_name,
            text=msg_text,
            is_bot=False,
        )

    try:
        await forward_engine.process_incoming_message(message, album_messages=album_messages)
    except Exception as e:
        logger.exception("Error forwarding message %s: %s", message.message_id, e)

    if settings.ANALYTICS_ENABLED and message.from_user and not is_profane:
        is_profileable = message.chat.type in ("group", "supergroup", "channel")
        if not is_profileable and message.chat.type == "private":
            try:
                async with db.connect() as conn:
                    r_repo = RouteRepository(conn)
                    active_src_routes = await r_repo.get_routes_for_source(message.chat.id, active_only=True)
                    is_profileable = bool(active_src_routes)
            except Exception:
                is_profileable = False

        if is_profileable:
            text = MediaHandler.get_text_or_caption(message)
            if text.strip():
                user_id = message.from_user.id
                chat_id = message.chat.id
                is_owner = bool(settings.OWNER_ID > 0 and user_id == settings.OWNER_ID)
                is_reply = bool(message.reply_to_message is not None)
                created_at = message.date if message.date else datetime.now()

                try:
                    await style_profiler.process_message(
                        user_id=user_id,
                        chat_id=chat_id,
                        text=text,
                        created_at=created_at,
                        is_reply=is_reply,
                        is_owner=is_owner,
                    )
                except Exception as e:
                    logger.exception("Error profiling message %s: %s", message.message_id, e)

    # Companion conversation handler
    if companion and not is_profane:
        is_chat_ai_allowed = False
        if message.chat.type in ("group", "supergroup"):
            if chat:
                is_chat_ai_allowed = bool(chat.get("chat_ai_enabled", 0))
        elif message.chat.type == "private":
            is_chat_ai_allowed = True

        if is_chat_ai_allowed:
            try:
                bot_user = await companion.get_bot_user(message.bot)
                triggered, prompt = companion.is_triggered(
                    message,
                    bot_username=bot_user.username,
                    bot_id=bot_user.id,
                )
                if triggered and prompt:
                    await message.bot.send_chat_action(chat_id=message.chat.id, action="typing")
                    caller_name = message.from_user.first_name if message.from_user else "Собеседник"
                    reply_text = await companion.generate_reply(
                        chat_id=message.chat.id,
                        user_name=caller_name,
                        user_prompt=prompt,
                    )
                    if reply_text:
                        await message.reply(reply_text, parse_mode=None)
            except Exception as e:
                logger.warning("Error in companion handler for message %s: %s", message.message_id, e)
