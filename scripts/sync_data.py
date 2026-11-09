"""Скрипт полной синхронизации данных чата 'Тирамису', участников и настроек с базой данных бота."""

from __future__ import annotations

import asyncio
import glob
import logging
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from bs4 import BeautifulSoup

# Ensure project root is in path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.settings import Settings
from database.connection import Database
from database.schema import init_db
from database.repositories.chat_repo import ChatRepository
from database.repositories.route_repo import RouteRepository
from database.repositories.user_repo import UserRepository
from database.repositories.config_repo import ConfigRepository
from analytics.profiler import StyleProfiler

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("sync_data")

SOURCE_CHAT_ID = -1002255156347  # Чат «Тирамису»
DEST_CHAT_ID = -1004479083851    # Канал/архив «Richard»

VERIFIED_USERS = [
    {
        "user_id": 911338473,
        "username": "Tymur2000",
        "first_name": "Тимур",
        "last_name": None,
        "role": "owner",
        "is_authorized": 1,
    },
    {
        "user_id": 5956803305,
        "username": "MixaRed",
        "first_name": "MixaRed",
        "last_name": None,
        "role": "admin",
        "is_authorized": 1,
    },
    {
        "user_id": 5848551858,
        "username": "MSVP2055",
        "first_name": "· : :·:·:",
        "last_name": None,
        "role": "user",
        "is_authorized": 1,
    },
    {
        "user_id": 5985808271,
        "username": "ishowdealer",
        "first_name": "forsazh",
        "last_name": None,
        "role": "user",
        "is_authorized": 1,
    },
    {
        "user_id": 1696889505,
        "username": "ciel_hleb",
        "first_name": "Соль",
        "last_name": None,
        "role": "user",
        "is_authorized": 1,
    },
]

NAME_TO_USER_ID = {
    "тимур": 911338473,
    "mixared": 5956803305,
    "миша": 5956803305,
    "⠁⠃⠽⠎⠎": 5848551858,
    "msvp2055": 5848551858,
    "abyss": 5848551858,
    "forsazh": 5985808271,
    "соль": 1696889505,
    "richard": 7761395820,
}


async def sync_all():
    env_file = Path(__file__).parent.parent / ".env"
    settings = Settings(_env_file=str(env_file)) if env_file.exists() else Settings()
    settings.ensure_directories()
    db = Database(settings.DATABASE_PATH)

    logger.info("1. Инициализация схемы базы данных: %s", settings.DATABASE_PATH)
    async with db.connect() as conn:
        await init_db(conn)

    logger.info("2. Синхронизация верифицированных пользователей...")
    async with db.connect() as conn:
        u_repo = UserRepository(conn)
        for u in VERIFIED_USERS:
            await u_repo.upsert_user(
                user_id=u["user_id"],
                username=u["username"],
                first_name=u["first_name"],
                last_name=u["last_name"],
            )
            # Update role and authorization
            await conn.execute(
                """
                UPDATE users
                SET role = ?, is_authorized = ?, updated_at = CURRENT_TIMESTAMP
                WHERE user_id = ?
                """,
                (u["role"], u["is_authorized"], u["user_id"]),
            )
        await conn.commit()

    logger.info("3. Синхронизация чатов и параметров...")
    async with db.connect() as conn:
        chat_repo = ChatRepository(conn)
        # Исходный чат «Тирамису»
        await chat_repo.upsert_chat(
            chat_id=SOURCE_CHAT_ID,
            title="Тирамису",
            chat_type="supergroup",
            is_source=True,
            is_destination=False,
        )
        await conn.execute(
            """
            UPDATE chats
            SET chat_ai_enabled = 1, stt_enabled = 1, stt_auto_transcribe = 0,
                profanity_filter_enabled = 0, profanity_strictness = 'soft',
                updated_at = CURRENT_TIMESTAMP
            WHERE chat_id = ?
            """,
            (SOURCE_CHAT_ID,),
        )

        # Канал/архив назначения «Richard»
        await chat_repo.upsert_chat(
            chat_id=DEST_CHAT_ID,
            title="Архив / Richard",
            chat_type="channel",
            is_source=False,
            is_destination=True,
        )
        await conn.commit()

    logger.info("4. Синхронизация маршрута пересылки...")
    async with db.connect() as conn:
        route_repo = RouteRepository(conn)
        cursor = await conn.execute(
            "SELECT id FROM routes WHERE source_chat_id = ? AND destination_chat_id = ?",
            (SOURCE_CHAT_ID, DEST_CHAT_ID),
        )
        existing_route = await cursor.fetchone()
        if not existing_route:
            await route_repo.create_route(
                name="Тирамису -> Архив",
                source_chat_id=SOURCE_CHAT_ID,
                destination_chat_id=DEST_CHAT_ID,
                created_by_user_id=settings.OWNER_ID,
                mode="forward",
            )
        else:
            await conn.execute(
                "UPDATE routes SET is_active = 1, mode = 'forward' WHERE source_chat_id = ? AND destination_chat_id = ?",
                (SOURCE_CHAT_ID, DEST_CHAT_ID),
            )
            await conn.commit()

    logger.info("5. Синхронизация глобальных настроек ИИ и STT...")
    async with db.connect() as conn:
        config_repo = ConfigRepository(conn)
        await config_repo.set_llm_config(
            enabled=True,
            model="gpt-4o-mini",
            base_url="https://api.openai.com/v1",
            persona="student",
            trigger_mode="name_and_reply",
            typing_indicator=True,
            context_limit=15,
            max_tokens=800,
            temperature=0.7,
            random_reply_chance=0,
            custom_prompt="Ты — Ричард, сообразительный и саркастичный парень в Telegram-чате друзей. Отвечай хлёстко, по факту, 1-3 фразы, без занудства и без клоунады.",
        )
        await config_repo.set_stt_config(
            enabled=True,
            language="ru-RU",
        )
        await conn.commit()

    logger.info("6. Импорт сообщений экспорта в аналитику (StyleProfiler) и историю собеседника...")
    export_dir = r"c:\Users\sla_5\Downloads\Telegram Desktop\ChatExport_2026-11-02"
    html_files = sorted(glob.glob(os.path.join(export_dir, "messages*.html")))
    
    if html_files:
        profiler = StyleProfiler(db=db)
        parsed_messages = []

        for hf in html_files:
            with open(hf, "r", encoding="utf-8") as fp:
                soup = BeautifulSoup(fp.read(), "html.parser")
            for m in soup.find_all("div", class_="message"):
                fwd = m.find("div", class_="forwarded body")
                if fwd:
                    fn_el = fwd.find("div", class_="from_name")
                    text_el = fwd.find("div", class_="text")
                    date_el = fwd.find("span", class_="date") or m.find("div", class_="date")
                else:
                    fn_el = m.find("div", class_="from_name")
                    text_el = m.find("div", class_="text")
                    date_el = m.find("div", class_="date")

                raw_name = fn_el.get_text().strip() if fn_el else ""
                txt = text_el.get_text().strip() if text_el else ""
                date_str = date_el.get("title", "") if date_el else ""

                if not txt:
                    continue

                # Parse author
                author_lower = raw_name.lower().split()[0] if raw_name else ""
                user_id = 0
                clean_name = "Участник"
                for alias, uid in NAME_TO_USER_ID.items():
                    if alias in author_lower:
                        user_id = uid
                        if uid == 911338473:
                            clean_name = "Тимур"
                        elif uid == 5956803305:
                            clean_name = "MixaRed"
                        elif uid == 5848551858:
                            clean_name = "⠁⠃⠽⠎⠎"
                        elif uid == 5985808271:
                            clean_name = "forsazh"
                        elif uid == 1696889505:
                            clean_name = "Соль"
                        elif uid == 7761395820:
                            clean_name = "Ричард"
                        break

                dt = datetime.now()
                if date_str:
                    try:
                        clean_dt = date_str.split(" GMT")[0].strip()
                        dt = datetime.strptime(clean_dt, "%d.%m.%Y %H:%M:%S")
                    except Exception:
                        pass

                is_bot = (user_id == 7761395820)
                parsed_messages.append({
                    "user_id": user_id,
                    "user_name": clean_name,
                    "text": txt,
                    "dt": dt,
                    "is_bot": is_bot,
                })

        logger.info("Разобрано %d текстовых сообщений из экспорта.", len(parsed_messages))

        # 6a. Process into StyleProfiler
        profiled_count = 0
        for pm in parsed_messages:
            if pm["user_id"] > 0 and not pm["is_bot"]:
                is_owner = (pm["user_id"] == settings.OWNER_ID)
                await profiler.process_message(
                    user_id=pm["user_id"],
                    chat_id=SOURCE_CHAT_ID,
                    text=pm["text"],
                    created_at=pm["dt"],
                    is_reply=False,
                    is_owner=is_owner,
                )
                profiled_count += 1
        logger.info("Профиль стилометрии построен по %d сообщениям участников.", profiled_count)

        # 6b. Insert recent messages into companion_chat_history
        recent_for_history = parsed_messages[-50:]
        async with db.connect() as conn:
            for item in recent_for_history:
                await conn.execute(
                    """
                    INSERT INTO companion_chat_history (chat_id, user_id, user_name, text, is_bot, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        SOURCE_CHAT_ID,
                        item["user_id"],
                        item["user_name"],
                        item["text"][:500],
                        1 if item["is_bot"] else 0,
                        item["dt"].strftime("%Y-%m-%d %H:%M:%S"),
                    ),
                )
            await conn.commit()
        logger.info("Последние %d сообщений добавлены в контекстную память Ричарда.", len(recent_for_history))

    logger.info("=== Синхронизация данных с настройками бота успешно завершена! ===")


if __name__ == "__main__":
    asyncio.run(sync_all())
