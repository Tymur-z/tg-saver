from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, List, Optional

from aiogram import Router
from aiogram.types import Message

from config.settings import Settings
from forwarder.engine import ForwardEngine
from forwarder.media_handler import MediaHandler
from analytics.profiler import StyleProfiler

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
    album_messages: Optional[List[Message]] = None,
) -> None:
    if message.text and message.text.startswith("/"):
        return

    try:
        await forward_engine.process_incoming_message(message, album_messages=album_messages)
    except Exception as e:
        logger.exception("Error forwarding message %s: %s", message.message_id, e)

    if settings.ANALYTICS_ENABLED and message.from_user:
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
