from __future__ import annotations

import asyncio
import json
import logging
import random
from datetime import datetime, timedelta
from typing import Any, List, Optional

from aiogram import Router
from aiogram.types import ChatPermissions, Message, CallbackQuery
from aiogram import F
import html
from moderation.stt_service import NvidiaSTTService

from config.settings import Settings
from database.connection import Database
from database.repositories.chat_repo import ChatRepository
from database.repositories.route_repo import RouteRepository
from database.repositories.user_repo import UserRepository
from forwarder.engine import ForwardEngine
from forwarder.media_handler import MediaHandler
from analytics.profiler import StyleProfiler
from moderation.companion import ChatCompanion, format_companion_html
from moderation.profanity import ProfanityDetector

logger = logging.getLogger(__name__)
router = Router(name="forward_router")


async def delete_message_later(msg: Message, delay: int) -> None:
    try:
        await asyncio.sleep(delay)
        await msg.delete()
    except Exception:
        pass


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
    stt_service: Optional[NvidiaSTTService] = None,
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

    # Auto-register/update user information in database for clean analytics display
    if message.from_user:
        try:
            async with db.connect() as conn:
                u_repo = UserRepository(conn)
                await u_repo.upsert_user(
                    user_id=message.from_user.id,
                    username=message.from_user.username,
                    first_name=message.from_user.first_name,
                    last_name=message.from_user.last_name,
                )
        except Exception:
            pass

    msg_text = message.text or message.caption
    raw_incoming_text = msg_text or ""

    # Check for manual speech-to-text transcription request
    lower_text = raw_incoming_text.strip().lower()
    transcribe_triggers = {
        "/transcribe", "/stt", "/speech", "текст", "переведи", "расшифруй",
        "расшифровка", "что там", "что в кружке", "что в голосовом", "transcribe",
        "что тут", "что он сказал", "что она сказала"
    }
    if message.reply_to_message and (lower_text in transcribe_triggers or lower_text.startswith(("/transcribe", "/stt"))):
        replied = message.reply_to_message
        if getattr(replied, "voice", None) or getattr(replied, "video_note", None):
            media_obj = getattr(replied, "voice", None) or getattr(replied, "video_note", None)
            suffix = ".oga" if getattr(replied, "voice", None) else ".mp4"
            tag = "Голосовое" if getattr(replied, "voice", None) else "Кружок"
            if stt_service and stt_service.is_available():
                transcript = await stt_service.transcribe_telegram_file(
                    bot=message.bot,
                    file_id=media_obj.file_id,
                    file_unique_id=media_obj.file_unique_id,
                    suffix=suffix,
                )
                if transcript:
                    await message.reply(f"📝 <b>Расшифровка ({tag}):</b>\n\n{html.escape(transcript)}", parse_mode="HTML")
                    return
                else:
                    await message.reply(f"⚠️ Не удалось расшифровать {tag.lower()} (возможно тишина или сильный шум).")
                    return
            else:
                await message.reply("⚠️ Распознавание речи отключено или не настроен API-ключ.")
                return

    # Ignore other slash commands
    if msg_text and msg_text.startswith("/"):
        return

    chat = None
    is_profane = False
    transcribed_speech = None

    has_priv_audio = bool(getattr(message, "voice", None) or getattr(message, "video_note", None))
    if message.chat.type == "private" and has_priv_audio and stt_service and stt_service.is_available():
        media_obj = getattr(message, "voice", None) or getattr(message, "video_note", None)
        suffix = ".oga" if getattr(message, "voice", None) else ".mp4"
        tag = "Голосовое" if getattr(message, "voice", None) else "Кружок"
        try:
            transcribed_speech = await stt_service.transcribe_telegram_file(
                bot=message.bot,
                file_id=media_obj.file_id,
                file_unique_id=media_obj.file_unique_id,
                suffix=suffix,
            )
            if transcribed_speech:
                msg_text = f"🗣️ [{tag}]: {transcribed_speech}"
        except Exception as priv_stt_err:
            logger.warning("Private STT error: %s", priv_stt_err)

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
        except Exception as e:
            logger.warning("Could not fetch chat %s: %s", message.chat.id, e)

        # Auto-transcribe audio/video_note if STT is available and enabled
        has_group_audio = bool(getattr(message, "voice", None) or getattr(message, "video_note", None))
        if has_group_audio and stt_service and stt_service.is_available():
            should_stt = True
            if chat:
                should_stt = bool(chat.get("stt_enabled", 1))

            if should_stt:
                media_obj = getattr(message, "voice", None) or getattr(message, "video_note", None)
                suffix = ".oga" if getattr(message, "voice", None) else ".mp4"
                tag = "Голосовое" if getattr(message, "voice", None) else "Кружок"
                try:
                    transcribed_speech = await stt_service.transcribe_telegram_file(
                        bot=message.bot,
                        file_id=media_obj.file_id,
                        file_unique_id=media_obj.file_unique_id,
                        suffix=suffix,
                    )
                    if transcribed_speech:
                        msg_text = f"🗣️ [{tag}]: {transcribed_speech}"
                        if chat and chat.get("stt_auto_transcribe", 0):
                            try:
                                await message.reply(f"📝 <b>Расшифровка ({tag}):</b>\n\n{html.escape(transcribed_speech)}", parse_mode="HTML")
                            except Exception as auto_err:
                                logger.warning("Could not post auto-transcription: %s", auto_err)
                except Exception as stt_err:
                    logger.warning("Error during automatic STT for msg %s: %s", message.message_id, stt_err)

        try:
            if chat and chat.get("profanity_filter_enabled") and profanity_detector:
                text_to_check = MediaHandler.get_text_or_caption(message)
                if text_to_check and text_to_check.strip():
                    strictness = chat.get("profanity_strictness", "hard")
                    raw_cw = chat.get("custom_profanity_words", "[]")
                    raw_wl = chat.get("custom_whitelist_words", "[]")
                    try:
                        custom_words = json.loads(raw_cw) if isinstance(raw_cw, str) else (raw_cw or [])
                    except Exception:
                        custom_words = []
                    try:
                        whitelist_words = json.loads(raw_wl) if isinstance(raw_wl, str) else (raw_wl or [])
                    except Exception:
                        whitelist_words = []

                    prof_result = await profanity_detector.check_text(
                        text_to_check,
                        strictness=strictness,
                        custom_words=custom_words,
                        whitelist_words=whitelist_words,
                    )
                    if prof_result.is_profane:
                        is_profane = True
                        logger.info(
                            "Profanity detected in chat %s from user %s: %s (%s)",
                            message.chat.id,
                            message.from_user.id if message.from_user else "unknown",
                            prof_result.reason,
                            prof_result.method,
                        )

                        # Record violation
                        try:
                            async with db.connect() as conn:
                                await ChatRepository(conn).record_violation(
                                    chat_id=message.chat.id,
                                    user_id=message.from_user.id if message.from_user else 0,
                                    reason=prof_result.reason,
                                    severity=prof_result.severity,
                                )
                        except Exception:
                            pass

                        # Auto-mute check
                        auto_mute_sec = int(chat.get("auto_mute_duration", 0))
                        if auto_mute_sec > 0 and message.from_user:
                            try:
                                async with db.connect() as conn:
                                    v_count = await ChatRepository(conn).count_recent_violations(
                                        chat_id=message.chat.id,
                                        user_id=message.from_user.id,
                                        hours=24,
                                    )
                                if v_count >= 3:
                                    until_date = datetime.now() + timedelta(seconds=auto_mute_sec)
                                    await message.bot.restrict_chat_member(
                                        chat_id=message.chat.id,
                                        user_id=message.from_user.id,
                                        permissions=ChatPermissions(can_send_messages=False),
                                        until_date=until_date,
                                    )
                                    mute_mins = auto_mute_sec // 60
                                    user_mention = message.from_user.mention_html()
                                    await message.answer(
                                        f"🔇 {user_mention} временно ограничен в отправке сообщений на {mute_mins} мин. за повторные нарушения правил чата."
                                    )
                            except Exception as mute_err:
                                logger.debug("Could not auto-mute user in %s: %s", message.chat.id, mute_err)

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
                                warn_msg = await message.answer(warn_text)
                                warn_sec = int(chat.get("profanity_delete_warn_seconds", 0))
                                if warn_sec > 0:
                                    asyncio.create_task(delete_message_later(warn_msg, warn_sec))
                            except Exception as warn_err:
                                logger.warning("Could not send warning in %s: %s", message.chat.id, warn_err)
        except Exception as mod_err:
            logger.exception("Error during chat settings check for message %s: %s", message.message_id, mod_err)

    # Save to context buffer for companion awareness (RAM + Persistent SQLite)
    if companion and not is_profane and msg_text:
        u_name = message.from_user.full_name if message.from_user else "Участник"
        u_username = message.from_user.username if message.from_user else None
        companion.context_buffer.add_message(
            chat_id=message.chat.id,
            user_id=message.from_user.id if message.from_user else 0,
            user_name=u_name,
            username=u_username,
            text=msg_text,
            is_bot=False,
        )
        try:
            async with db.connect() as conn:
                await ChatRepository(conn).add_companion_message(
                    chat_id=message.chat.id,
                    user_id=message.from_user.id if message.from_user else 0,
                    user_name=u_name,
                    username=u_username,
                    text=msg_text,
                    is_bot=False,
                )
        except Exception:
            pass

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
                    override_text=transcribed_speech,
                )

                # Random reply if not triggered directly
                if not triggered and message.chat.type in ("group", "supergroup") and msg_text:
                    if companion.random_reply_chance > 0 and len(msg_text) >= 2:
                        if random.randint(1, 100) <= companion.random_reply_chance:
                            triggered = True
                            prompt = msg_text

                if triggered and prompt:
                    if companion.typing_indicator:
                        await message.bot.send_chat_action(chat_id=message.chat.id, action="typing")
                    caller_name = message.from_user.first_name if message.from_user else "Собеседник"
                    is_owner = bool(settings.OWNER_ID > 0 and message.from_user and message.from_user.id == settings.OWNER_ID)

                    # Ensure RAM buffer has persistent history if buffer is empty
                    if not companion.context_buffer.get_context(message.chat.id):
                        try:
                            async with db.connect() as conn:
                                hist = await ChatRepository(conn).get_companion_history(message.chat.id, limit=companion.context_limit)
                                for item in hist:
                                    companion.context_buffer.add_message(
                                        chat_id=message.chat.id,
                                        user_id=item["user_id"],
                                        user_name=item["user_name"] or "Участник",
                                        username=item.get("username"),
                                        text=item["text"],
                                        is_bot=bool(item["is_bot"]),
                                    )
                        except Exception:
                            pass

                    # Check if user asks what a specific participant wrote
                    import re
                    target_user_match = re.search(
                        r"(?:что\s+(?:писал|написал)[а-я]*|сообщени[ея]\s+от|last\s+message\s+(?:that\s+)?|last\s+message\s+(?:from|by)\s+|message\s+(?:that\s+)?|did\s+)\s*@?([a-zA-Z0-9_а-яА-ЯёЁ]+)",
                        prompt,
                        re.IGNORECASE,
                    )
                    extra_context = ""
                    if target_user_match:
                        target_nick = target_user_match.group(1).strip()
                        bot_names = {"ты", "ричард", "richard", "you"}
                        if bot_user.username:
                            bot_names.add(bot_user.username.lower())
                        if bot_user.first_name:
                            bot_names.add(bot_user.first_name.lower())

                        if target_nick.lower() in bot_names:
                            try:
                                async with db.connect() as conn:
                                    cursor = await conn.execute(
                                        "SELECT * FROM companion_chat_history WHERE chat_id = ? AND is_bot = 1 ORDER BY id DESC LIMIT 1",
                                        (message.chat.id,),
                                    )
                                    row = await cursor.fetchone()
                                    if row:
                                        extra_context = f"[Справка из базы данных чата: твоё (Ричард) предыдущее сообщение в этом чате было: \"{row['text']}\"]"
                            except Exception:
                                pass
                        else:
                            try:
                                async with db.connect() as conn:
                                    last_msg = await ChatRepository(conn).get_last_message_from_user(message.chat.id, target_nick)
                                    if last_msg:
                                        u_display = f"{last_msg['user_name']}" + (f" (@{last_msg['username']})" if last_msg.get("username") else "")
                                        extra_context = f"[Справка из базы данных чата: последнее найденное сообщение от {u_display}: \"{last_msg['text']}\"]"
                            except Exception:
                                pass

                    reply_text = await companion.generate_reply(
                        chat_id=message.chat.id,
                        user_name=caller_name,
                        user_prompt=prompt,
                        is_owner=is_owner,
                        extra_context=extra_context,
                    )
                    if reply_text:
                        # Save companion reply to persistent DB
                        try:
                            async with db.connect() as conn:
                                await ChatRepository(conn).add_companion_message(
                                    chat_id=message.chat.id,
                                    user_id=0,
                                    user_name="Ричард",
                                    text=reply_text,
                                    is_bot=True,
                                )
                        except Exception:
                            pass

                        formatted_reply = format_companion_html(reply_text)
                        try:
                            sent_reply = await message.reply(formatted_reply, parse_mode="HTML")
                        except Exception as html_err:
                            logger.debug("Could not send reply with HTML parse_mode: %s, falling back to plain", html_err)
                            clean_plain = re.sub(r'^(?:#{1,6})\s*', '', reply_text, flags=re.MULTILINE)
                            clean_plain = clean_plain.replace('**', '').replace('__', '')
                            sent_reply = await message.reply(clean_plain, parse_mode=None)
                        # Mirror reply to destination chats if active routes exist
                        try:
                            await forward_engine.process_incoming_message(sent_reply)
                        except Exception as fwd_err:
                            logger.debug("Could not mirror companion reply to routes: %s", fwd_err)
            except Exception as e:
                logger.warning("Error in companion handler for message %s: %s", message.message_id, e)


@router.callback_query(F.data.startswith("stt_transcribe:"))
async def cb_stt_transcribe(
    callback: CallbackQuery,
    stt_service: Optional[NvidiaSTTService] = None,
) -> None:
    if not stt_service or not stt_service.is_available():
        await callback.answer("⚠️ Распознавание речи временно недоступно.", show_alert=True)
        return

    msg = callback.message
    media_obj = None
    suffix = ".oga"
    tag = "Голосовое"
    if msg:
        if msg.voice:
            media_obj = msg.voice
        elif msg.video_note:
            media_obj = msg.video_note
            suffix = ".mp4"
            tag = "Кружок"
        elif msg.reply_to_message:
            if msg.reply_to_message.voice:
                media_obj = msg.reply_to_message.voice
            elif msg.reply_to_message.video_note:
                media_obj = msg.reply_to_message.video_note
                suffix = ".mp4"
                tag = "Кружок"

    if not media_obj:
        await callback.answer("⚠️ Аудиофайл не найден.", show_alert=True)
        return

    await callback.answer("⏳ Расшифровываю речь...")
    try:
        transcript = await stt_service.transcribe_telegram_file(
            bot=callback.bot,
            file_id=media_obj.file_id,
            file_unique_id=media_obj.file_unique_id,
            suffix=suffix,
        )
        if transcript:
            await msg.reply(f"📝 <b>Расшифровка ({tag}):</b>\n\n{html.escape(transcript)}", parse_mode="HTML")
        else:
            await callback.message.reply(f"⚠️ Не удалось расшифровать {tag.lower()} (возможно тишина).")
    except Exception as e:
        logger.warning("Error handling stt_transcribe callback: %s", e)
        await callback.answer("❌ Ошибка при расшифровке.", show_alert=True)
