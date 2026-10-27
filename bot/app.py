from __future__ import annotations

import logging
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from config.settings import Settings
from database.connection import Database
from database.repositories.user_repo import UserRepository
from database.schema import init_db
from forwarder.engine import ForwardEngine
from forwarder.queue import ForwardQueue
from analytics.profiler import StyleProfiler
from bot.middlewares.auth import UserAuthMiddleware
from bot.middlewares.album import MediaGroupMiddleware
from bot.handlers import (
    admin_router,
    analytics_router,
    forward_router,
    privacy_router,
    routes_router,
)

logger = logging.getLogger(__name__)


def create_bot(settings: Settings) -> Bot:
    return Bot(
        token=settings.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )


def create_dispatcher(
    settings: Settings,
    db: Database,
    queue: ForwardQueue,
    forward_engine: ForwardEngine,
    style_profiler: StyleProfiler,
) -> Dispatcher:
    dp = Dispatcher(storage=MemoryStorage())

    dp["settings"] = settings
    dp["db"] = db
    dp["queue"] = queue
    dp["forward_engine"] = forward_engine
    dp["style_profiler"] = style_profiler

    auth_middleware = UserAuthMiddleware(db=db, settings=settings)
    dp.message.outer_middleware(auth_middleware)
    dp.callback_query.outer_middleware(auth_middleware)

    album_middleware = MediaGroupMiddleware(debounce_seconds=settings.ALBUM_DEBOUNCE_SECONDS)
    forward_router.message.middleware(album_middleware)
    forward_router.channel_post.middleware(album_middleware)

    dp.include_router(admin_router)
    dp.include_router(routes_router)
    dp.include_router(analytics_router)
    dp.include_router(privacy_router)
    dp.include_router(forward_router)

    return dp


async def start_application(settings: Settings) -> None:
    settings.ensure_directories()
    db = Database(settings.DATABASE_PATH)

    async with db.connect() as conn:
        await init_db(conn)
        user_repo = UserRepository(conn)
        row = await conn.execute("SELECT value FROM app_state WHERE key = 'access_password'")
        if not await row.fetchone():
            await user_repo.set_access_password(settings.ACCESS_PASSWORD)
        row = await conn.execute("SELECT value FROM app_state WHERE key = 'password_required'")
        if not await row.fetchone():
            await user_repo.set_password_required(settings.PASSWORD_REQUIRED)

    bot = create_bot(settings)
    queue = ForwardQueue(
        bot=bot,
        db=db,
        rate_limit_per_minute=settings.FORWARD_RATE_LIMIT_PER_MINUTE,
        max_queue_size=settings.QUEUE_MAX_SIZE,
        max_retries=settings.MAX_RETRY_ATTEMPTS,
    )
    forward_engine = ForwardEngine(bot=bot, db=db, queue=queue)
    style_profiler = StyleProfiler(db=db)

    dp = create_dispatcher(settings, db, queue, forward_engine, style_profiler)

    queue.start()
    logger.info("Starting Telegram Bot long-polling...")

    try:
        await dp.start_polling(bot, allowed_updates=["message", "channel_post", "callback_query"])
    finally:
        logger.info("Shutting down application...")
        await queue.stop()
        await bot.session.close()
        logger.info("Application shut down cleanly.")
