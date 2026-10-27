from __future__ import annotations

import asyncio
import logging
from typing import Any, Awaitable, Callable, Dict, List

from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject

logger = logging.getLogger(__name__)


class MediaGroupMiddleware(BaseMiddleware):

    def __init__(self, debounce_seconds: float = 0.8) -> None:
        super().__init__()
        self.debounce_seconds = debounce_seconds
        self.albums: Dict[str, List[Message]] = {}
        self.locks: Dict[str, asyncio.Lock] = {}

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        if not isinstance(event, Message) or not event.media_group_id:
            data["album_messages"] = None
            return await handler(event, data)

        group_id = event.media_group_id

        if group_id not in self.albums:
            self.albums[group_id] = [event]
            await asyncio.sleep(self.debounce_seconds)

            collected = self.albums.pop(group_id, [event])
            data["album_messages"] = collected
            return await handler(event, data)

        self.albums[group_id].append(event)
        return None
