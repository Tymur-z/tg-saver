from __future__ import annotations

import logging
from typing import Optional
from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from config.settings import Settings
from database.connection import Database
from database.repositories.user_repo import UserRepository
from database.repositories.config_repo import ConfigRepository
from database.schema import init_db
from forwarder.engine import ForwardEngine
from forwarder.queue import ForwardQueue
from analytics.profiler import StyleProfiler
from moderation.llm_client import LLMClient
from moderation.profanity import ProfanityDetector
from moderation.companion import ChatCompanion
from moderation.stt_service import NvidiaSTTService
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
    profanity_detector: Optional[ProfanityDetector] = None,
    llm_client: Optional[LLMClient] = None,
    companion: Optional[ChatCompanion] = None,
    stt_service: Optional[NvidiaSTTService] = None,
) -> Dispatcher:
    dp = Dispatcher(storage=MemoryStorage())

    dp["settings"] = settings
    dp["db"] = db
    dp["queue"] = queue
    dp["forward_engine"] = forward_engine
    dp["style_profiler"] = style_profiler
    if profanity_detector:
        dp["profanity_detector"] = profanity_detector
    if llm_client:
        dp["llm_client"] = llm_client
    if companion:
        dp["companion"] = companion
    if stt_service:
        dp["stt_service"] = stt_service

    auth_middleware = UserAuthMiddleware(db=db, settings=settings)
    dp.message.outer_middleware(auth_middleware)
    dp.callback_query.outer_middleware(auth_middleware)

    album_middleware = MediaGroupMiddleware(debounce_seconds=settings.ALBUM_DEBOUNCE_SECONDS)
    forward_router.message.middleware(album_middleware)
    forward_router.channel_post.middleware(album_middleware)

    for r in (admin_router, routes_router, analytics_router, privacy_router):
        r.message.filter(F.chat.type == "private")
        r.callback_query.filter(F.message.chat.type == "private")

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

        config_repo = ConfigRepository(conn)
        llm_conf = await config_repo.get_llm_config(
            default_enabled=settings.LLM_ENABLED,
            default_api_key=settings.LLM_API_KEY,
            default_base_url=settings.LLM_BASE_URL,
            default_model=settings.LLM_MODEL,
        )
        stt_conf = await config_repo.get_stt_config(
            default_enabled=settings.STT_ENABLED,
            default_api_key=settings.STT_API_KEY,
            default_function_id=settings.STT_FUNCTION_ID,
            default_uri=settings.STT_URI,
            default_language=settings.STT_LANGUAGE,
        )

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

    llm_client = LLMClient(
        api_key=llm_conf["llm_api_key"],
        base_url=llm_conf["llm_base_url"],
        model=llm_conf["llm_model"],
    )
    profanity_detector = ProfanityDetector(
        llm_client=llm_client,
        llm_enabled=llm_conf["llm_enabled"],
    )
    companion = ChatCompanion(
        llm_client=llm_client,
        context_limit=llm_conf.get("companion_context_limit", 15),
        max_tokens=llm_conf.get("companion_max_tokens", 800),
        temperature=llm_conf.get("companion_temperature", 0.7),
        persona=llm_conf.get("companion_persona", "student"),
        custom_prompt=llm_conf.get("companion_custom_prompt", ""),
        trigger_mode=llm_conf.get("companion_trigger_mode", "name_and_reply"),
        typing_indicator=llm_conf.get("companion_typing_indicator", True),
        random_reply_chance=llm_conf.get("companion_random_reply_chance", 0),
    )
    stt_service = NvidiaSTTService(
        api_key=stt_conf.get("stt_api_key", ""),
        function_id=stt_conf.get("stt_function_id", "b702f636-f60c-4a3d-a6f4-f3568c13bd7d"),
        uri=stt_conf.get("stt_uri", "grpc.nvcf.nvidia.com:443"),
        language_code=stt_conf.get("stt_language", "ru-RU"),
        enabled=stt_conf.get("stt_enabled", True),
    )

    dp = create_dispatcher(
        settings=settings,
        db=db,
        queue=queue,
        forward_engine=forward_engine,
        style_profiler=style_profiler,
        profanity_detector=profanity_detector,
        llm_client=llm_client,
        companion=companion,
        stt_service=stt_service,
    )

    queue.start()
    logger.info("Starting Telegram Bot long-polling...")

    try:
        await dp.start_polling(bot, allowed_updates=["message", "channel_post", "callback_query"])
    finally:
        logger.info("Shutting down application...")
        await queue.stop()
        await bot.session.close()
        logger.info("Application shut down cleanly.")
