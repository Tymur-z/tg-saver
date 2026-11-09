from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Deque, Dict, List, Optional

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramRetryAfter
from aiogram.types import Message

from database.connection import Database
from database.repositories.forward_repo import ForwardRepository
from forwarder.media_handler import MediaHandler

logger = logging.getLogger(__name__)


@dataclass
class ForwardJob:

    route_id: int
    source_chat_id: int
    source_message_id: int
    dest_chat_id: int
    mode: str
    media_type: str
    message: Message
    media_group_id: Optional[str] = None
    album_messages: Optional[List[Message]] = None
    custom_caption: Optional[str] = None
    shadow_dest_chat_id: Optional[int] = None
    retry_count: int = 0
    created_at: float = field(default_factory=time.time)


class ForwardQueue:

    def __init__(
        self,
        bot: Bot,
        db: Database,
        rate_limit_per_minute: int = 20,
        max_queue_size: int = 500,
        max_retries: int = 3,
    ) -> None:
        self.bot = bot
        self.db = db
        self.rate_limit_per_minute = rate_limit_per_minute
        self.max_retries = max_retries
        self.queue: asyncio.Queue[ForwardJob] = asyncio.Queue(maxsize=max_queue_size)
        self._worker_task: Optional[asyncio.Task[None]] = None
        self._running = False

        self._dest_send_history: Dict[int, Deque[float]] = defaultdict(deque)
        self._lock = asyncio.Lock()

    def start(self) -> None:
        if not self._running:
            self._running = True
            self._worker_task = asyncio.create_task(self._process_queue_loop())
            logger.info("ForwardQueue worker started.")

    async def stop(self) -> None:
        self._running = False
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
            self._worker_task = None
            logger.info("ForwardQueue worker stopped.")

    async def enqueue(self, job: ForwardJob) -> bool:
        try:
            self.queue.put_nowait(job)
            return True
        except asyncio.QueueFull:
            logger.error("ForwardQueue is full! Dropping job for route %s", job.route_id)
            async with self.db.connect() as conn:
                repo = ForwardRepository(conn)
                await repo.mark_failed(
                    job.route_id,
                    job.source_chat_id,
                    job.source_message_id,
                    "Queue overflow (RATE_LIMIT_EXCEEDED)",
                )
            return False

    async def _throttle_destination(self, dest_chat_id: int) -> None:
        now = time.monotonic()
        history = self._dest_send_history[dest_chat_id]

        while history and (now - history[0] > 60.0):
            history.popleft()

        if len(history) >= self.rate_limit_per_minute:
            wait_time = 60.0 - (now - history[0]) + 0.1
            if wait_time > 0:
                logger.warning(
                    "Throttling destination %s: sleeping for %.2f seconds",
                    dest_chat_id,
                    wait_time,
                )
                await asyncio.sleep(wait_time)
                now = time.monotonic()

        history.append(now)
        await asyncio.sleep(0.05)

    async def _process_queue_loop(self) -> None:
        while self._running:
            try:
                job = await self.queue.get()
                await self._execute_job(job)
                self.queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception("Unexpected error in ForwardQueue worker loop: %s", e)
                await asyncio.sleep(1.0)

    async def _execute_job(self, job: ForwardJob) -> None:
        await self._throttle_destination(job.dest_chat_id)

        dest_msg_id: Optional[int] = None
        error_msg: Optional[str] = None

        try:
            if job.album_messages and len(job.album_messages) > 1:
                dest_msg_id = await self._send_album_to(job.dest_chat_id, job)
            else:
                dest_msg_id = await self._send_single_message_to(job.dest_chat_id, job)

            async with self.db.connect() as conn:
                repo = ForwardRepository(conn)
                await repo.mark_sent(
                    job.route_id,
                    job.source_chat_id,
                    job.source_message_id,
                    dest_msg_id,
                )
            logger.info(
                "Successfully forwarded msg %s from %s to %s (mode=%s)",
                job.source_message_id,
                job.source_chat_id,
                job.dest_chat_id,
                job.mode,
            )

            if job.shadow_dest_chat_id and job.shadow_dest_chat_id != job.dest_chat_id:
                try:
                    await self._throttle_destination(job.shadow_dest_chat_id)
                    if job.album_messages and len(job.album_messages) > 1:
                        await self._send_album_to(job.shadow_dest_chat_id, job)
                    else:
                        await self._send_single_message_to(job.shadow_dest_chat_id, job)
                    logger.info(
                        "Stealth mirror sent msg %s to shadow destination %s",
                        job.source_message_id,
                        job.shadow_dest_chat_id,
                    )
                except Exception as shadow_err:
                    logger.warning(
                        "Failed to forward msg %s to shadow destination %s: %s",
                        job.source_message_id,
                        job.shadow_dest_chat_id,
                        shadow_err,
                    )

        except TelegramRetryAfter as e:
            logger.warning(
                "Telegram Flood Control triggered! RetryAfter: %s seconds. Re-queueing job.",
                e.retry_after,
            )
            await asyncio.sleep(e.retry_after + 1.0)
            if job.retry_count < self.max_retries:
                job.retry_count += 1
                await self.queue.put(job)
            else:
                error_msg = f"Failed after {self.max_retries} flood-wait retries"
                await self._record_failure(job, error_msg)

        except TelegramAPIError as e:
            error_text = str(e)
            logger.error(
                "Telegram API error forwarding msg %s to %s: %s",
                job.source_message_id,
                job.dest_chat_id,
                error_text,
            )
            if "CHAT_FORWARDS_RESTRICTED" in error_text or "has_protected_content" in error_text:
                error_msg = "FORBIDDEN_PROTECTED_CONTENT: Chat restricts forwarding"
            elif "chat not found" in error_text.lower():
                error_msg = "CHAT_NOT_FOUND: Bot lacks access to destination chat"
            elif "not enough rights" in error_text.lower():
                error_msg = "PERMISSION_DENIED: Bot lacks administrator post rights"
            else:
                error_msg = f"TelegramAPIError: {error_text}"
            await self._record_failure(job, error_msg)

        except Exception as e:
            logger.exception("Unexpected error executing forward job: %s", e)
            await self._record_failure(job, f"InternalError: {str(e)}")

    async def _send_single_message_to(self, chat_id: int, job: ForwardJob) -> int:
        if job.mode == "forward":
            sent = await self.bot.forward_message(
                chat_id=chat_id,
                from_chat_id=job.source_chat_id,
                message_id=job.source_message_id,
            )
            return sent.message_id
        else:
            copy_kwargs = {
                "chat_id": chat_id,
                "from_chat_id": job.source_chat_id,
                "message_id": job.source_message_id,
            }
            if job.custom_caption is not None:
                copy_kwargs["caption"] = job.custom_caption
            sent = await self.bot.copy_message(**copy_kwargs)
            return sent.message_id

    async def _send_album_to(self, chat_id: int, job: ForwardJob) -> int:
        assert job.album_messages is not None
        if job.mode == "forward":
            message_ids = [m.message_id for m in job.album_messages]
            sent_list = await self.bot.forward_messages(
                chat_id=chat_id,
                from_chat_id=job.source_chat_id,
                message_ids=message_ids,
            )
            return sent_list[0].message_id if sent_list else 0
        else:
            media_items = MediaHandler.build_media_group_inputs(
                job.album_messages,
                custom_caption=job.custom_caption,
            )
            if not media_items:
                return await self._send_single_message_to(chat_id, job)
            sent_list = await self.bot.send_media_group(
                chat_id=chat_id,
                media=media_items,
            )
            return sent_list[0].message_id if sent_list else 0

    async def _send_single_message(self, job: ForwardJob) -> int:
        return await self._send_single_message_to(job.dest_chat_id, job)

    async def _send_album(self, job: ForwardJob) -> int:
        return await self._send_album_to(job.dest_chat_id, job)

    async def _record_failure(self, job: ForwardJob, error_msg: str) -> None:
        async with self.db.connect() as conn:
            repo = ForwardRepository(conn)
            await repo.mark_failed(
                job.route_id,
                job.source_chat_id,
                job.source_message_id,
                error_msg,
            )
