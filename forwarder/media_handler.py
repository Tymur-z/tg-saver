from __future__ import annotations

import logging
from typing import Any, List, Optional, Union

from aiogram.types import (
    InputMediaAudio,
    InputMediaDocument,
    InputMediaPhoto,
    InputMediaVideo,
    Message,
)

logger = logging.getLogger(__name__)

MediaGroupItem = Union[InputMediaPhoto, InputMediaVideo, InputMediaAudio, InputMediaDocument]


class MediaHandler:

    @staticmethod
    def clean_and_format_text(
        text: str,
        clean_links: bool = False,
        clean_tags: bool = False,
        clean_mentions: bool = False,
        append_source_link: bool = False,
        source_title: Optional[str] = None,
        source_username: Optional[str] = None,
    ) -> str:
        import re

        result = text or ""
        if clean_links:
            result = re.sub(r"https?://\S+", "", result)
        if clean_tags:
            result = re.sub(r"#\w+", "", result)
        if clean_mentions:
            result = re.sub(r"@\w+", "", result)

        result = result.strip()

        if append_source_link and (source_title or source_username):
            credit = f"@{source_username}" if source_username else source_title
            result = f"{result}\n\n📌 <i>Источник: {credit}</i>".strip()

        return result

    @staticmethod
    def detect_type(message: Message) -> str:
        if message.text is not None:
            return "text"
        if message.photo:
            return "photo"
        if message.video:
            return "video"
        if message.video_note:
            return "video_note"
        if message.voice:
            return "voice"
        if message.audio:
            return "audio"
        if message.document:
            return "document"
        if message.sticker:
            return "sticker"
        if message.animation:
            return "animation"
        if message.poll:
            return "poll"
        if message.location:
            return "location"
        if message.contact:
            return "contact"
        return "other"

    @staticmethod
    def get_text_or_caption(message: Message) -> str:
        return message.text or message.caption or ""

    @staticmethod
    def build_media_group_inputs(
        messages: List[Message],
        custom_caption: Optional[str] = None,
    ) -> List[MediaGroupItem]:
        group: List[MediaGroupItem] = []
        caption_applied = False

        for msg in messages:
            caption = None
            caption_entities = None
            if not caption_applied:
                if custom_caption is not None:
                    caption = custom_caption
                    caption_applied = True
                elif msg.caption:
                    caption = msg.caption
                    caption_entities = msg.caption_entities
                    caption_applied = True

            if msg.photo:
                largest_photo = msg.photo[-1]
                group.append(
                    InputMediaPhoto(
                        media=largest_photo.file_id,
                        caption=caption,
                        caption_entities=caption_entities,
                    )
                )
            elif msg.video:
                group.append(
                    InputMediaVideo(
                        media=msg.video.file_id,
                        caption=caption,
                        caption_entities=caption_entities,
                        width=msg.video.width,
                        height=msg.video.height,
                        duration=msg.video.duration,
                    )
                )
            elif msg.audio:
                group.append(
                    InputMediaAudio(
                        media=msg.audio.file_id,
                        caption=caption,
                        caption_entities=caption_entities,
                        duration=msg.audio.duration,
                        performer=msg.audio.performer,
                        title=msg.audio.title,
                    )
                )
            elif msg.document:
                group.append(
                    InputMediaDocument(
                        media=msg.document.file_id,
                        caption=caption,
                        caption_entities=caption_entities,
                    )
                )
            else:
                logger.warning(
                    "Message %s in album %s cannot be part of InputMediaGroup",
                    msg.message_id,
                    msg.media_group_id,
                )

        return group
