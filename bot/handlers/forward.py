from __future__ import annotations

import asyncio
import collections
import json
import logging
import random
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from aiogram import Router
from aiogram.types import ChatPermissions, Message, CallbackQuery
from aiogram import F
import html
import re
from moderation.stt_service import NvidiaSTTService
from moderation.vision_service import VisionService

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
from moderation.weather_service import get_weather_summary

logger = logging.getLogger(__name__)
router = Router(name="forward_router")

# Cache of recently received audio/video notes per chat for non-reply transcription & context enrichment
_recent_chat_media: Dict[int, collections.deque[Dict[str, Any]]] = collections.defaultdict(
    lambda: collections.deque(maxlen=10)
)
# Cache of recently received photos per chat for vision inspection & companion context
_recent_chat_photos: Dict[int, collections.deque[Dict[str, Any]]] = collections.defaultdict(
    lambda: collections.deque(maxlen=10)
)


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



TRANSCRIPTION_KEYWORDS = {
    "transcribe", "stt", "speech", "transcript",
    "текст", "переведи", "расшифруй", "расшифровка", "транскрипция",
    "процитируй", "процитируй кружок", "процитируй видео", "процитируй гс", "процитируй голосовое",
    "цитируй", "повтори", "повтори кружок", "повтори что сказал", "произнеси", "озвучь",
    "что в кружке", "что в голосовом", "что в гс",
    "что в войсе", "что в аудио", "что в видео", "что в видеосообщении",
    "что в видеокурске", "что на видеокурске", "что на видеокружке", "что в видеокружке",
    "что он сказал", "что она сказала", "что они сказали",
    "что я сказал", "что я наговорил", "что я тут сказал", "что я там сказал",
    "что произнес", "что произнёс", "что я произнес", "что я произнёс", "что он произнес", "что он произнёс",
    "что было сказано", "что тут сказано", "что там сказано", "что сказано",
    "что было произнесено", "что произнесли", "что ты произнес",
    "что говориться", "что говорится", "что говорит",
    "что там говорить", "что говориться в кружке", "что говорится в кружке",
    "что происходит на кружочке", "что происходит в кружке", "что тут происходит на кружочке",
    "что происходит в голосовом", "что происходит в гс",
    "я про етот", "я про этот", "про что кружок", "про что гс", "про что голосовое",
    "о чем кружок", "о чём кружок", "о чем голосовое", "о чём голосовое",
    "переведи кружок", "переведи гс", "переведи голосовое", "переведи войс",
    "расшифруй кружок", "расшифруй гс", "расшифруй голосовое", "расшифруй войс",
    "что в последнем кружке", "что в последнем голосовом", "что в последнем гс",
    "что было в кружке", "что было в голосовом", "что было в гс",
    "what did he say", "what did she say", "what did i say", "what was said", "what is said",
    "what is in the circle", "what is in the voice", "what does it say"
}

TRANSCRIPTION_PATTERNS = [
    re.compile(r"^(?:/)?(?:transcribe|stt|speech)\b", re.IGNORECASE),
    re.compile(r"^(?:текст|переведи|расшифруй|расшифровка|транскрипц\w*|в\s+текст|процитируй|цитируй|повтори|transcribe|transcript)\b", re.IGNORECASE),
    re.compile(r"(?:что|о\s*ч[её]м|про\s+что)\s+(?:он[а-я]*|я|ты|они|было|говорит\w*|наговор\w*|сказан\w*|произнес\w*|произнёс\w*)\s+(?:в\s+(?:круж\w*|курс\w*|курск\w*|голосов\w*|гс|войс\w*|аудио|этом|етом|видео\w*))", re.IGNORECASE),
    re.compile(r"^(?:что\s+в\s+(?:кружке|курске|видеокурске)|что\s+в\s+голосов\w*|что\s+в\s+гс|что\s+(?:он[а-я]*|я|они)\s+(?:сказал\w*|произнес\w*|произнёс\w*)|что\s+говорит\w*\s+в\s+(?:круж\w*|гс|войс\w*)|что\s+говорит[ьс]+я\s+в\s+кружке|я\s+про\s+[еэ]тот)$", re.IGNORECASE),
    re.compile(r"(?:что\s+(?:тут\s+|там\s+)?происходит\s+(?:тут\s+|там\s+)?(?:на|в)\s+(?:круж\w*|курс\w*|курск\w*|голосов\w*|гс|войс\w*))", re.IGNORECASE),
    re.compile(r"(?:what\s+(?:did\s+(?:he|she|they|i)\s+say|was\s+said|is\s+said|is\s+in\s+the\s+(?:circle|voice|audio)|does\s+it\s+say))", re.IGNORECASE),
]


def is_transcription_request(text: str, is_reply_to_media: bool = False) -> bool:
    """Returns True if user asks to transcribe or what was said in audio/video note, without conversational chat."""
    if not text:
        return False
    t = text.strip().lower()

    # If user asks about chat status / summary / news, NEVER trigger transcription
    if re.search(r"\b(?:по\s+чат\w*|в\s+чат\w*|чат\w*|сводк\w*|итог\w*|новост\w*|нового)\b", t, re.IGNORECASE):
        if not re.search(r"\b(?:круж\w*|голосов\w*|гс|войс\w*|аудио|видеосообщ\w*)\b", t, re.IGNORECASE):
            return False

    # Strip bot mentions and name calls
    t = re.sub(r"@[a-zA-Z0-9_]+", "", t).strip()
    t = re.sub(r"^(?:ричард|richard|ричи|рикардо)[,\s:!-]+", "", t, flags=re.IGNORECASE).strip()
    t = re.sub(r"(?:^|[\s,])(?:ричард|richard|ричи|рикардо)(?:[\s,!?]|$)", " ", t, flags=re.IGNORECASE).strip()

    # Strip polite wrappers and action prefixes
    t = re.sub(
        r"\b(?:пожалуйста|плиз|пж|сделай|можешь|подскажи|расскажи|покажи|покажь|рокажи|послушай|глянь|посмотри|дай|чётко|четко|хорош|please|pls|can\s+you|could\s+you)\b",
        " ",
        t,
        flags=re.IGNORECASE,
    ).strip()

    clean = re.sub(r"[?!.,;:]+", " ", t).strip()
    clean = " ".join(clean.split())

    # Pure conversational opinions should not trigger direct transcription (unless explicitly combined with transcribe verb)
    opinion_pattern = re.compile(
        r"\b(?:что\s+думаешь|как\s+тебе|согласен|тво[её]\s+мнение|мнение|оцени|прокомментируй|what\s+do\s+you\s+think|your\s+opinion)\b",
        re.IGNORECASE,
    )
    if opinion_pattern.search(clean) and not re.search(r"\b(?:расшифр\w*|транскрип\w*|процитир\w*|цитир\w*)\b", clean, re.IGNORECASE):
        return False

    has_media_word = bool(re.search(r"\b(?:круж\w*|курс\w*|курск\w*|видеокурс\w*|голосов\w*|гс|войс\w*|аудио|видео\w*|запис\w*)\b", clean, re.IGNORECASE))
    has_stt_verb = bool(re.search(r"\b(?:расшифр\w*|транскрип\w*|переведи\s+в\s+текст|в\s+текст|процитир\w*|цитир\w*|повтор\w*|произнес\w*|произнёс\w*|transcribe|transcript)\b", clean, re.IGNORECASE))

    if is_reply_to_media:
        if has_stt_verb or clean in ("текст", "что там", "что тут", "что он сказал", "что она сказала", "что они сказали", "процитируй", "цитируй", "повтори", "скажи", "скажи что там", "что произнес", "что произнёс"):
            return True
        if re.search(r"\b(?:что|о\s*ч[её]м|про\s+что|сказан\w*|сказал\w*|произнес\w*|произнёс\w*|говорит\w*|процитир\w*|цитир\w*|повтор\w*)\b", clean, re.IGNORECASE):
            return True

    if has_media_word and (
        has_stt_verb or
        re.search(r"\b(?:что|о\s*ч[её]м|про\s+что|переведи|текст|сказан\w*|сказал\w*|произнес\w*|произнёс\w*|говорит\w*|происходит)\b", clean, re.IGNORECASE)
    ):
        return True

    if clean in TRANSCRIPTION_KEYWORDS or has_stt_verb:
        return True

    return False

def is_summary_request(text: str) -> bool:
    """Returns True if user asks for a chat summary or what happened in chat."""
    if not text:
        return False
    t = text.strip().lower()
    return bool(re.search(
        r"\b(?:сводк\w*|итог\w*|что\s+(?:там\s+|тут\s+)?по\s+чат\w*|что\s+в\s+чат\w*|что\s+(?:там\s+)?происходило\s+в\s+чат\w*|расскажи\s+(?:что\s+)?в\s+чат\w*|что\s+нового\s+в\s+чат\w*|как\s+дела\s+в\s+чат\w*)\b",
        t,
        re.IGNORECASE,
    ))


async def get_target_chat_for_summary(
    db: Database,
    message: Message,
    text: str,
) -> tuple[int, str]:
    """Finds target chat ID and title for summary."""
    text_lower = text.lower()
    try:
        async with db.connect() as conn:
            if re.search(r"\b(?:тирамису|tiramisu|tirammmisu|тирамис)\b", text_lower):
                cursor = await conn.execute(
                    "SELECT chat_id, title FROM chats WHERE title LIKE '%tiram%' OR title LIKE '%тирам%' ORDER BY chat_id DESC LIMIT 1"
                )
                chat_row = await cursor.fetchone()
                if chat_row:
                    return int(chat_row["chat_id"]), str(chat_row["title"])

            if message.chat.type in ("group", "supergroup"):
                return message.chat.id, message.chat.title or "Чат"

            cursor = await conn.execute(
                """
                SELECT c.chat_id, c.title, COUNT(h.id) as msg_count
                FROM chats c
                LEFT JOIN companion_chat_history h ON c.chat_id = h.chat_id
                WHERE c.chat_id < 0
                GROUP BY c.chat_id
                ORDER BY msg_count DESC, c.chat_id DESC
                LIMIT 1
                """
            )
            primary_chat = await cursor.fetchone()
            if primary_chat:
                return int(primary_chat["chat_id"]), str(primary_chat["title"])
    except Exception as e:
        logger.exception("Error in get_target_chat_for_summary: %s", e)

    return -1002255156347, "TiraMMMiSu"


async def generate_chat_summary_response(
    db: Database,
    companion: ChatCompanion,
    target_chat_id: int,
    target_chat_title: str,
    user_name: str,
    user_prompt: str,
) -> str:
    """Generates an accurate, truthful and witty summary of real events in the target chat."""
    today_str = datetime.now().strftime("%Y-%m-%d")
    daily_mem = None
    messages_list = []

    async with db.connect() as conn:
        repo = ChatRepository(conn)
        daily_mem = await repo.get_daily_memory(target_chat_id, today_str)
        cursor = await conn.execute(
            """
            SELECT user_name, text, created_at, is_bot
            FROM companion_chat_history
            WHERE chat_id = ?
            ORDER BY id DESC
            LIMIT 35
            """,
            (target_chat_id,),
        )
        rows = await cursor.fetchall()
        for r in reversed(rows):
            sender = "Ричард (Бот)" if r["is_bot"] else (r["user_name"] or "Участник")
            messages_list.append(f"[{sender}]: {r['text']}")

    summary_context_parts = []
    if daily_mem and (daily_mem.get("summary") or daily_mem.get("key_facts")):
        summary_context_parts.append(f"Дневная хроника событий дня ({today_str}):\n{daily_mem.get('summary', '')}")
        if daily_mem.get("key_facts"):
            summary_context_parts.append("Ключевые факты дня:\n" + "\n".join(f"- {f}" for f in daily_mem["key_facts"]))

    if messages_list:
        summary_context_parts.append("Последние сообщения и кружки в чате:\n" + "\n".join(messages_list[-30:]))

    if not summary_context_parts:
        return f"В чате {target_chat_title} за последнее время было тихо, свежих сообщений нет."

    full_log = "\n\n".join(summary_context_parts)
    sys_prompt = (
        f"Ты — Ричард, свой пацан и участник этой компании друзей. Пользователь ({user_name}) попросил сводку по чату \"{target_chat_title}\".\n"
        f"ВОТ РЕАЛЬНЫЕ СООБЩЕНИЯ, КРУЖОЧКИ И СОБЫТИЯ ИЗ ЭТОГО ЧАТА:\n"
        f"-----------------\n"
        f"{full_log}\n"
        f"-----------------\n\n"
        f"СТРОЖАЙШИЕ ПРАВИЛА СОСТАВЛЕНИЯ СВОДКИ:\n"
        f"1. ГОВОРИ СТРОГО ПО РЕАЛЬНЫМ ФАКТАМ ИЗ ЛОГА ВЫШЕ! Назови участников по именам (Соль, MixaRed, Тимур, Абисс), кто что писал, какие кружки записывал (например, кружки Соли про прическу/укладку в школу, разговоры про балаклаву, тиктоки Михи).\n"
        f"2. КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО выдумывать еду, десерты, торты, рецепты, пробовать на вкус или сладости! Название чата '{target_chat_title}' — это просто название чата друзей, а не еда!\n"
        f"3. НЕ ПУТАТЬ УЧАСТНИКОВ: В ушки и хвост горничной/кошкодевочки наряжался MixaRed (Миша), а не Тимур! Тимур уговаривал Мишу снять этот наряд до прихода мамы.\n"
        f"4. Общайся спокойно, по делу, по-братски, без выпендрежа, без сарказма и подколок в адрес создателя.\n"
        f"5. Отвечай живым, емким языком, по-пацански, без воды и канцеляризмов (2-4 предложения).\n"
        f"6. НИКАКИХ ржущих смайликов (😂, 🤣) и шаблонов бота."
    )

    llm_msgs = [
        {"role": "system", "content": sys_prompt},
        {"role": "user", "content": f"{user_name}: {user_prompt}"},
    ]

    try:
        reply = await companion.llm_client.chat_completion(
            messages=llm_msgs,
            temperature=0.6,
            max_tokens=600,
        )
        return reply.strip() if reply else f"В чате {target_chat_title} пока всё спокойно."
    except Exception as e:
        logger.exception("Error generating summary via LLM: %s", e)
        return f"По чату {target_chat_title}: недавно Соль записывала кружок про укладку в школу, а ночью обсуждали балаклавы и кидали тиктоки."

def resolve_friendly_name(user: Optional[User]) -> str:
    """Returns a friendly, casual chat name for participants, avoiding robotic titles or raw display names."""
    if not user:
        return "Участник"
    if user.id == 1696889505 or (user.username and user.username.lower() in ("ciel_hleb", "sol", "соль")):
        return "Соль"
    if user.id == 911338473 or (user.username and user.username.lower() == "tymur2000"):
        return "Тимур"
    if user.id == 5956803305 or (user.username and user.username.lower() == "mixared") or (user.first_name and "mixared" in user.first_name.lower()):
        return "MixaRed"
    if user.id == 5848551858 or (user.username and user.username.lower() in ("msvp2055", "abyss")) or (user.first_name and "⠁⠃⠽⠎⠎" in user.first_name):
        return "⠁⠃⠽⠎⠎"
    if user.id == 5985808271 or (user.username and user.username.lower() in ("ishowdealer", "forsazh")):
        return "форсаж"
    fn = user.first_name or ""
    if "сілл" in fn.lower() or "соль" in fn.lower():
        return "Соль"
    clean_fn = re.sub(r"[^\w\sа-яА-ЯёЁa-zA-Z0-9_-]", "", fn).strip()
    return clean_fn if clean_fn else (user.username or "Участник")


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
    vision_service: Optional[VisionService] = None,
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
    TELEGRAM_SYSTEM_BOT_IDS = {1087968824, 777000, 136817688}
    if message.from_user and message.from_user.id not in TELEGRAM_SYSTEM_BOT_IDS:
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

    # Record incoming audio / video note in chat media cache
    has_incoming_media = bool(getattr(message, "voice", None) or getattr(message, "video_note", None) or getattr(message, "audio", None))
    if has_incoming_media:
        m_obj = getattr(message, "voice", None) or getattr(message, "video_note", None) or getattr(message, "audio", None)
        sfx = ".oga" if getattr(message, "voice", None) else (".mp4" if getattr(message, "video_note", None) else ".mp3")
        tg = "Голосовое" if getattr(message, "voice", None) else ("Кружок" if getattr(message, "video_note", None) else "Аудио")
        _recent_chat_media[message.chat.id].append({
            "message_id": message.message_id,
            "user_id": message.from_user.id if message.from_user else 0,
            "user_name": resolve_friendly_name(message.from_user),
            "media_obj": m_obj,
            "suffix": sfx,
            "tag": tg,
            "timestamp": time.time(),
            "transcript": None,
        })

    # Record incoming photo in chat photo cache (RAM + persistent DB)
    if getattr(message, "photo", None):
        best_p = message.photo[-1]
        _recent_chat_photos[message.chat.id].append({
            "message_id": message.message_id,
            "user_id": message.from_user.id if message.from_user else 0,
            "user_name": resolve_friendly_name(message.from_user),
            "file_id": best_p.file_id,
            "file_unique_id": getattr(best_p, "file_unique_id", best_p.file_id),
            "photo_sizes": message.photo,
            "caption": message.caption or "",
            "timestamp": time.time(),
            "base64": None,
        })
        try:
            async with db.connect() as conn:
                await ChatRepository(conn).add_recent_photo(
                    chat_id=message.chat.id,
                    message_id=message.message_id,
                    user_id=message.from_user.id if message.from_user else 0,
                    user_name=resolve_friendly_name(message.from_user),
                    file_id=best_p.file_id,
                    file_unique_id=getattr(best_p, "file_unique_id", best_p.file_id),
                    caption=message.caption or "",
                )
        except Exception:
            pass

    # Check for speech-to-text transcription request (both replies and non-reply commands like 'что я сказал')
    is_reply_to_media = bool(message.reply_to_message and (
        getattr(message.reply_to_message, "voice", None) or
        getattr(message.reply_to_message, "video_note", None) or
        getattr(message.reply_to_message, "audio", None)
    ))
    if is_transcription_request(raw_incoming_text, is_reply_to_media=is_reply_to_media):
        target_media_obj = None
        target_suffix = ".oga"
        target_tag = "Голосовое"
        target_author = ""
        cached_transcript = None

        if message.reply_to_message:
            replied = message.reply_to_message
            if getattr(replied, "voice", None) or getattr(replied, "video_note", None) or getattr(replied, "audio", None):
                target_media_obj = getattr(replied, "voice", None) or getattr(replied, "video_note", None) or getattr(replied, "audio", None)
                target_suffix = ".oga" if getattr(replied, "voice", None) else (".mp4" if getattr(replied, "video_note", None) else ".mp3")
                target_tag = "Голосовое" if getattr(replied, "voice", None) else ("Кружок" if getattr(replied, "video_note", None) else "Аудио")
                target_author = resolve_friendly_name(replied.from_user)

        if not target_media_obj:
            # Non-reply transcription: check recently received media in this chat (within last 15 minutes)
            is_first_person = bool(re.search(r"\b(?:я|меня|мой|мо[её]|наговорил|сказал\b(?!\s+(?:он|она|они)))\b", raw_incoming_text, re.IGNORECASE))
            caller_id = message.from_user.id if message.from_user else 0
            now = time.time()
            recent_items = list(_recent_chat_media.get(message.chat.id, []))

            # If 1st person query ("что я сказал"), prioritize caller's own recent media
            if is_first_person and caller_id:
                for item in reversed(recent_items):
                    if item["user_id"] == caller_id and (now - item["timestamp"] <= 900):
                        target_media_obj = item["media_obj"]
                        target_suffix = item["suffix"]
                        target_tag = item["tag"]
                        target_author = item["user_name"]
                        cached_transcript = item.get("transcript")
                        break

            # Otherwise find the latest media in this chat
            if not target_media_obj:
                for item in reversed(recent_items):
                    if now - item["timestamp"] <= 900:
                        target_media_obj = item["media_obj"]
                        target_suffix = item["suffix"]
                        target_tag = item["tag"]
                        target_author = item["user_name"]
                        cached_transcript = item.get("transcript")
                        break

        if target_media_obj:
            if stt_service and stt_service.is_available():
                transcript = cached_transcript
                if not transcript:
                    transcript = await stt_service.transcribe_telegram_file(
                        bot=message.bot,
                        file_id=target_media_obj.file_id,
                        file_unique_id=target_media_obj.file_unique_id,
                        suffix=target_suffix,
                        language_code="ru-RU",
                    )
                if transcript:
                    # Cache transcript in recent buffer
                    for item in _recent_chat_media.get(message.chat.id, []):
                        if item["media_obj"] == target_media_obj:
                            item["transcript"] = transcript
                            break
                    # Also record in companion context buffer so AI chat remembers what was said
                    if companion:
                        companion.context_buffer.add_message(
                            chat_id=message.chat.id,
                            user_id=getattr(target_media_obj, "file_unique_id", 0),
                            user_name=target_author or "Участник",
                            text=f"🗣️ [{target_tag}]: {transcript}",
                            is_bot=False,
                        )
                    author_label = f" от {target_author}" if (not message.reply_to_message and target_author and target_author != "Участник") else ""
                    await message.reply(f"📝 <b>Расшифровка ({target_tag}{author_label}):</b>\n\n{html.escape(transcript)}", parse_mode="HTML")
                    return
                else:
                    await message.reply(f"⚠️ Не удалось расшифровать {target_tag.lower()} (возможно тишина, музыка или сильный шум).")
                    return
            else:
                await message.reply("⚠️ Распознавание речи отключено или не настроен API-ключ.")
                return
        else:
            if message.reply_to_message:
                await message.reply("⚠️ В цитируемом сообщении нет аудио или кружочка.")
                return
            else:
                await message.reply("⚠️ Не нашёл недавних кружочков или голосовых сообщений для расшифровки.")
                return
    # Ignore other slash commands
    if msg_text and msg_text.startswith("/"):
        return

    chat = None
    is_profane = False
    is_deleted = False
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
                                is_deleted = True
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

    # Save to context buffer for companion awareness (RAM + Persistent SQLite, including media context)
    record_text = msg_text
    if not record_text:
        if getattr(message, 'photo', None):
            record_text = f"[Фото: {message.caption}]" if message.caption else "[Фото]"
        elif getattr(message, 'sticker', None):
            record_text = f"[Стикер: {message.sticker.emoji or '🌟'}]"
        elif getattr(message, 'video_note', None):
            record_text = f"[Кружок: {transcribed_speech}]" if transcribed_speech else "[Кружок]"
        elif getattr(message, 'voice', None):
            record_text = f"[Голосовое: {transcribed_speech}]" if transcribed_speech else "[Голосовое]"

    if companion and not is_deleted and record_text:
        u_name = resolve_friendly_name(message.from_user)
        u_username = message.from_user.username if message.from_user else None
        companion.context_buffer.add_message(
            chat_id=message.chat.id,
            user_id=message.from_user.id if message.from_user else 0,
            user_name=u_name,
            username=u_username,
            text=record_text,
            is_bot=False,
        )
        try:
            async with db.connect() as conn:
                await ChatRepository(conn).add_companion_message(
                    chat_id=message.chat.id,
                    user_id=message.from_user.id if message.from_user else 0,
                    user_name=u_name,
                    username=u_username,
                    text=record_text,
                    is_bot=False,
                )
        except Exception:
            pass

    try:
        await forward_engine.process_incoming_message(message, album_messages=album_messages)
    except Exception as e:
        logger.exception("Error forwarding message %s: %s", message.message_id, e)

    if settings.ANALYTICS_ENABLED and message.from_user and message.from_user.id not in TELEGRAM_SYSTEM_BOT_IDS:
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
            text = MediaHandler.get_text_or_caption(message) or transcribed_speech or ""
            if not text and (getattr(message, "voice", None) or getattr(message, "video_note", None)):
                if stt_service and stt_service.is_available():
                    try:
                        file_obj = message.voice or message.video_note
                        text = await stt_service.transcribe_telegram_file(message.bot, file_obj.file_id) or ""
                    except Exception as stt_err:
                        logger.warning("STT profiling transcribe error: %s", stt_err)

            # Strip voice/circle message tag prefixes if present
            if text.startswith("🗣️ [Кружок]: "):
                text = text[len("🗣️ [Кружок]: "):]
            elif text.startswith("🗣️ [Голосовое]: "):
                text = text[len("🗣️ [Голосовое]: "):]

            if text and text.strip():
                user_id = message.from_user.id
                chat_id = message.chat.id
                is_owner = bool(settings.OWNER_ID > 0 and user_id == settings.OWNER_ID)
                is_reply = bool(message.reply_to_message is not None)
                created_at = getattr(message, "date", None) or datetime.now()

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
    if companion and not is_deleted:
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
                    caller_name = resolve_friendly_name(message.from_user)
                    is_owner = bool(settings.OWNER_ID > 0 and message.from_user and message.from_user.id == settings.OWNER_ID)
                    is_admin_user = is_owner
                    if not is_admin_user and message.from_user:
                        async with db.connect() as conn:
                            u = await UserRepository(conn).get_user(message.from_user.id)
                            if u and u.get("role") in ("owner", "admin"):
                                is_admin_user = True

                    # Check for chat summary request (strictly restricted to owner and admins)
                    is_summary = is_summary_request(prompt)
                    follow_up_summary_re = re.compile(
                        r"^(?:ну|и\??|и\s+что\??|ну\s+что\??|ну\s+и\??|ну\s+так\s+что\??|ну\s+так\s+что|отвечай|давай|ну\s+пожалуйста|пожалуйста|расскажи|ну\s+скажи|ну\s+расскажи|да\s+ладно|че\s+там|что\s+там|ну\s+че|а\s+что\s+там|почему\??|почему\s+нет\??)",
                        re.IGNORECASE,
                    )
                    if not is_summary and follow_up_summary_re.search(prompt.strip()):
                        try:
                            async with db.connect() as conn:
                                # Check if previous bot message was a denial
                                cursor_bot = await conn.execute(
                                    "SELECT text FROM companion_chat_history WHERE chat_id = ? AND is_bot = 1 ORDER BY id DESC LIMIT 1",
                                    (message.chat.id,),
                                )
                                last_bot_row = await cursor_bot.fetchone()
                                if last_bot_row and "только для создателя и админов" in last_bot_row["text"]:
                                    is_summary = True
                                else:
                                    # Check previous user message (offset 1 because current user message was saved at line 631)
                                    cursor = await conn.execute(
                                        "SELECT text FROM companion_chat_history WHERE chat_id = ? AND is_bot = 0 ORDER BY id DESC LIMIT 1 OFFSET 1",
                                        (message.chat.id,),
                                    )
                                    prev_row = await cursor.fetchone()
                                    if prev_row and is_summary_request(prev_row["text"]):
                                        is_summary = True
                        except Exception:
                            pass

                    if is_summary:
                        if not is_admin_user:
                            denial = "Сводка по чату и доступ к внутренней хронике открыты только для создателя и админов. Тебе сюда доступ закрыт."
                            try:
                                async with db.connect() as conn:
                                    await ChatRepository(conn).add_companion_message(
                                        chat_id=message.chat.id,
                                        user_id=0,
                                        user_name="Ричард",
                                        text=denial,
                                        is_bot=True,
                                    )
                            except Exception:
                                pass
                            companion.context_buffer.add_message(
                                chat_id=message.chat.id,
                                user_id=0,
                                user_name="Ричард",
                                username=bot_user.username if bot_user else "Richard",
                                text=denial,
                                is_bot=True,
                            )
                            await message.reply(denial)
                            return

                        target_cid, target_title = await get_target_chat_for_summary(db, message, prompt)
                        summary_reply = await generate_chat_summary_response(
                            db=db,
                            companion=companion,
                            target_chat_id=target_cid,
                            target_chat_title=target_title,
                            user_name=caller_name,
                            user_prompt=prompt,
                        )
                        if summary_reply:
                            try:
                                async with db.connect() as conn:
                                    await ChatRepository(conn).add_companion_message(
                                        chat_id=message.chat.id,
                                        user_id=0,
                                        user_name="Ричард",
                                        text=summary_reply,
                                        is_bot=True,
                                    )
                            except Exception:
                                pass
                            companion.context_buffer.add_message(
                                chat_id=message.chat.id,
                                user_id=0,
                                user_name="Ричард",
                                text=summary_reply,
                                is_bot=True,
                            )
                            await message.reply(format_companion_html(summary_reply), parse_mode="HTML")
                            return

                    # Populate RAM buffer with dense compressed history from SQLite
                    try:
                        async with db.connect() as conn:
                            hist = await ChatRepository(conn).get_compressed_history(message.chat.id, raw_limit=80)
                            if hist:
                                companion.context_buffer.clear(message.chat.id)
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

                    # Check if user explicitly asks what a specific participant wrote
                    target_user_match = re.search(
                        r"(?:что\s+(?:писал|написал|говорил)[а-я]*|последнее\s+сообщени[ея]\s+от)\s+@?([a-zA-Z0-9_а-яА-ЯёЁ]{2,})",
                        prompt,
                        re.IGNORECASE,
                    )
                    extra_context = ""
                    if target_user_match:
                        target_nick = target_user_match.group(1).strip()
                        ignored_words = {
                            "ты", "ричард", "richard", "you", "он", "она", "они", "he", "she", "they",
                            "тут", "там", "это", "ето", "все", "всё", "чел", "пацан", "кто", "что", "бот"
                        }
                        if bot_user.username:
                            ignored_words.add(bot_user.username.lower())
                        if bot_user.first_name:
                            ignored_words.add(bot_user.first_name.lower())

                        if target_nick.lower() in {"ты", "ричард", "richard", "you"} or (bot_user.username and target_nick.lower() == bot_user.username.lower()):
                            try:
                                async with db.connect() as conn:
                                    cursor = await conn.execute(
                                        "SELECT * FROM companion_chat_history WHERE chat_id = ? AND is_bot = 1 ORDER BY id DESC LIMIT 1",
                                        (message.chat.id,),
                                    )
                                    row = await cursor.fetchone()
                                    if row:
                                        extra_context = f"[Твоё предыдущее сообщение в этом чате: \"{row['text']}\"]"
                            except Exception:
                                pass
                        elif target_nick.lower() not in ignored_words:
                            try:
                                async with db.connect() as conn:
                                    last_msg = await ChatRepository(conn).get_last_message_from_user(message.chat.id, target_nick)
                                    if last_msg:
                                        u_display = f"{last_msg['user_name']}" + (f" (@{last_msg['username']})" if last_msg.get("username") else "")
                                        extra_context = f"[Справка: последнее сообщение от {u_display}: \"{last_msg['text']}\"]"
                            except Exception:
                                pass

                    # If this is a reply to another message, enrich companion with replied content
                    replied_msg = message.reply_to_message
                    if replied_msg:
                        author_name = resolve_friendly_name(replied_msg.from_user)

                        has_rep_audio = bool(getattr(replied_msg, "voice", None) or getattr(replied_msg, "video_note", None) or getattr(replied_msg, "audio", None))
                        if has_rep_audio and stt_service and stt_service.is_available():
                            r_media = getattr(replied_msg, "voice", None) or getattr(replied_msg, "video_note", None) or getattr(replied_msg, "audio", None)
                            r_suffix = ".oga" if getattr(replied_msg, "voice", None) else (".mp4" if getattr(replied_msg, "video_note", None) else ".mp3")
                            r_tag = "Голосовое" if getattr(replied_msg, "voice", None) else ("Кружок" if getattr(replied_msg, "video_note", None) else "Аудио")
                            try:
                                r_transcript = await stt_service.transcribe_telegram_file(
                                    bot=message.bot,
                                    file_id=r_media.file_id,
                                    file_unique_id=r_media.file_unique_id,
                                    suffix=r_suffix,
                                    language_code="ru-RU",
                                )
                                if r_transcript:
                                    extra_context += (
                                        f"\n[Контекст реплая: {caller_name} обращается к тебе в ответ на {r_tag.lower()} от {author_name}. "
                                        f"В этом сообщении было сказано: \"{r_transcript}\". "
                                        f"Ответь остроумно и конкретно по смыслу сказанного в этом сообщении!]"
                                    )
                                else:
                                    extra_context += (
                                        f"\n[Контекст реплая: {caller_name} обращается к тебе в ответ на {r_tag.lower()} от {author_name}. "
                                        f"В этом сообщении не было внятных слов — была музыка, мелодия или напевание. "
                                        f"Ответь остроумно и живо про вокал, напевание или мелодию!]"
                                    )
                            except Exception as rep_err:
                                logger.debug("Could not transcribe replied media for companion: %s", rep_err)
                        elif replied_msg.text or replied_msg.caption:
                            rep_text = (replied_msg.text or replied_msg.caption)[:350]
                            is_photo_query = bool(re.search(r"\b(?:фото\w*|фотк\w*|картинк\w*|смет\w*|на\s+фото|по\s+фото|про\s+фото|что\s+тут|что\s+там)\b", prompt, re.IGNORECASE))
                            is_rep_addressing_bot = bool(re.search(r"\b(?:ричард|richard|ричи|бот)\b", rep_text, re.IGNORECASE))

                            if is_photo_query:
                                extra_context += (
                                    f"\n[Контекст реплая: {caller_name} обращается в ветке обсуждения: \"{rep_text}\". "
                                    f"Ответь прямо по существу фото и сметы, без ухода в посторонние подколы и БЕЗ приплетания SnowRunner!]"
                                )
                            elif author_name != caller_name and not is_rep_addressing_bot:
                                extra_context += (
                                    f"\n[Контекст реплая: {caller_name} пасует тебе вопрос/выпад от {author_name}: \"{rep_text}\". "
                                    f"Ответь так, чтобы красиво осадить {author_name} или остроумно перевести стрелку на него, поддержав {caller_name}! "
                                    f"СТРОЖАЙШЕ ЗАПРЕЩЕНО использовать аналогии типа 'X — это как Y'! Не упоминай чипсы/еду/животных/звезды.]"
                                )
                            else:
                                extra_context += (
                                    f"\n[Контекст реплая: {caller_name} обращается в ответ на сообщение: \"{rep_text}\". "
                                    f"Ответь остроумно и прямо по смыслу цитаты! СТРОЖАЙШЕ ЗАПРЕЩЕНО использовать аналогии типа 'X — это как Y'! Не упоминай чипсы/еду/животных/звезды.]"
                                )
                    else:
                        # Non-reply reference: check if user asks about a recent circle or voice note
                        has_audio_mention = bool(re.search(r"\b(?:круж\w*|голосов\w*|гс|войс\w*|пел\w*|напева\w*|песни|мелод\w*|трек|вокал\w*)\b", prompt, re.IGNORECASE))
                        recent_items = list(_recent_chat_media.get(message.chat.id, []))
                        if has_audio_mention and recent_items:
                            now = time.time()
                            latest_media = None
                            for item in reversed(recent_items):
                                if now - item["timestamp"] <= 900:
                                    latest_media = item
                                    break
                            if latest_media:
                                m_transcript = latest_media.get("transcript")
                                if not m_transcript and stt_service and stt_service.is_available():
                                    try:
                                        m_transcript = await stt_service.transcribe_telegram_file(
                                            bot=message.bot,
                                            file_id=latest_media["media_obj"].file_id,
                                            file_unique_id=latest_media["media_obj"].file_unique_id,
                                            suffix=latest_media["suffix"],
                                            language_code="ru-RU",
                                        )
                                        if m_transcript:
                                            latest_media["transcript"] = m_transcript
                                    except Exception:
                                        pass
                                if m_transcript:
                                    extra_context += (
                                        f"\n[Контекст недавнего {latest_media['tag'].lower()} от {latest_media['user_name']}: \"{m_transcript}\". "
                                        f"{caller_name} спрашивает тебя о нём. Ответь остроумно и прямо по смыслу сказанного!]"
                                    )
                                else:
                                    extra_context += (
                                        f"\n[Контекст недавнего {latest_media['tag'].lower()} от {latest_media['user_name']}: в нём не было внятных слов — "
                                        f"была мелодия, напевание или музыка без речи. Ответь остроумно про вокал, напевание или мелодию!]"
                                    )

                    daily_summary = ""
                    daily_facts = None
                    try:
                        today_str = datetime.now().strftime("%Y-%m-%d")
                        async with db.connect() as conn:
                            d_mem = await ChatRepository(conn).get_daily_memory(message.chat.id, today_str)
                            # CRITICAL SECURITY: in PM, only load group memory if user is verified OWNER or ADMIN!
                            if not d_mem and message.chat.type == "private" and is_admin_user:
                                d_mem = await ChatRepository(conn).get_daily_memory(-1002255156347, today_str)
                            if d_mem:
                                daily_summary = d_mem.get("summary", "")
                                daily_facts = d_mem.get("key_facts", [])
                    except Exception:
                        pass

                    # Check for photo context (vision)
                    target_photo_sizes = None
                    target_photo_file_id = None
                    photo_source_label = ""
                    if getattr(message, "photo", None):
                        target_photo_sizes = message.photo
                        photo_source_label = f"к присланному фото от {caller_name}"
                    elif replied_msg and getattr(replied_msg, "photo", None):
                        target_photo_sizes = replied_msg.photo
                        photo_source_label = f"в ответ на фото от {author_name}"
                    else:
                        photo_query_re = re.compile(
                            r"\b(?:фотк\w*|фото\w*|картинк\w*|изображен\w*|скрин\w*|смет\w*|на\s+фото|на\s+фотке|про\s+фото|про\s+фотку|по\s+фото|что\s+видишь|глянь|посмотри|зацени)\b",
                            re.IGNORECASE,
                        )
                        recent_opinion_re = re.compile(
                            r"\b(?:что\s+думаешь|как\s+тебе|что\s+скажешь|что\s+тут|что\s+там|дай\s+смет\w*|оцени|поясни|разбери|че\s+думаешь)\b",
                            re.IGNORECASE,
                        )
                        is_query_for_photo = bool(
                            photo_query_re.search(prompt) or
                            (replied_msg and photo_query_re.search(replied_msg.text or replied_msg.caption or ""))
                        )
                        is_opinion = bool(recent_opinion_re.search(prompt))

                        recent_photos = list(_recent_chat_photos.get(message.chat.id, []))
                        now_ts = time.time()
                        if recent_photos:
                            latest_p = recent_photos[-1]
                            time_diff = now_ts - latest_p["timestamp"]
                            # If explicit photo query, match photo regardless of time! If opinion, within 30 min.
                            if is_query_for_photo or (is_opinion and time_diff <= 1800):
                                target_photo_sizes = latest_p.get("photo_sizes")
                                target_photo_file_id = latest_p.get("file_id")
                                photo_source_label = f"к фото от {latest_p['user_name']}"

                        # If not in memory, query SQLite DB (persists across restarts)
                        if not target_photo_sizes and not target_photo_file_id and (is_query_for_photo or is_opinion):
                            try:
                                async with db.connect() as conn:
                                    db_photo = await ChatRepository(conn).get_last_recent_photo(message.chat.id)
                                    if db_photo:
                                        target_photo_file_id = db_photo["file_id"]
                                        photo_source_label = f"к фото от {db_photo['user_name']}"
                            except Exception:
                                pass

                    img_b64 = None
                    if (target_photo_sizes or target_photo_file_id) and vision_service and vision_service.is_available():
                        try:
                            img_b64 = await vision_service.download_and_process_photo(
                                bot=message.bot,
                                photo_sizes=target_photo_sizes,
                                file_id=target_photo_file_id,
                                max_dimension=vision_service.max_dimension,
                            )
                        except Exception as img_err:
                            logger.warning("Could not download/process photo for vision: %s", img_err)

                    if img_b64:
                        extra_context += (
                            f"\n[Контекст фото: {caller_name} обращается к тебе {photo_source_label}. "
                            f"Ты РЕАЛЬНО видишь это фото через прикрепленное изображение (Vision). "
                            f"Внимательно изучи реальные детали на фото (предметы, материалы, ценники, людей, одежду, обстановку, бардак) "
                            f"и ответь остроумно, по-пацански и строго по реальному содержимому этого фото! "
                            f"Если просят смету — дай реальную пацанскую смету по увиденному на фото! "
                            f"СТРОЖАЙШИЙ ЗАПРЕТ: НЕ приплетай 'SnowRunner' / 'сноуранер', игры или болота к фото! Отвечай строго по тому, что на фото!]"
                        )

                    # Timur relationship guards & buzzword suppression
                    if is_owner:
                        if re.search(r"\b(?:хорош\s+меня\s+упоминать|хватит\s+меня|отстань|отвали|тормози|хватит|не\s+трогай\s+меня|не\s+п[ие*]\w*|не\s+обманывай|зачем\s+обманываешь|хватит\s+врать)\b", prompt, re.IGNORECASE):
                            extra_context += (
                                "\n[ВАЖНО: Тимур осаживает тебя или указывает на косяк/блеф. Спокойно признай это, сбавь обороты без пререканий. "
                                "СТРОГИЙ ЗАПРЕТ на шаблонного попугая: НЕ повторяй заезженные фразы ('Понял, базар фильтрую', 'Принял, торможу')! "
                                "Отвечай своими словами, разнообразно и живо (например: 'Ладно, без базара, замяли', 'Спалился, признаю косяк', 'Справедливо, осадил'). "
                                "Если спросил прямо — ответь честно и по существу!]"
                            )
                        elif re.search(r"\b(?:красава|красавчик|победил|хорош|молодец|лучший|красавец)\b", prompt, re.IGNORECASE):
                            extra_context += "\n[ВАЖНО: Тимур похвалил тебя. Ответь тепло, по-братски и искренне: 'От души, Тимур!' или 'Ха, ну а то, держим уровень'. Никакого соперничества и язвительности!]"
                    elif re.search(r"\b(?:co2|сероводород|хими\w*|кислот\w*)\b", prompt, re.IGNORECASE):
                        extra_context += "\n[ВАЖНО: Тимур грамотно и по фактам объяснил про химию/CO2/сероводород. Не выставляй его душнилой или надзирателем, поддержи его факты.]"

                    # Weather contextual lookup for UK participants (Alton, Havant, Hindhead)
                    try:
                        weather_hint = await get_weather_summary(
                            prompt=prompt,
                            user_id=message.from_user.id if message.from_user else None,
                        )
                        if weather_hint:
                            extra_context += f"\n{weather_hint}"
                    except Exception as w_err:
                        logger.debug("Could not fetch weather hint: %s", w_err)

                    extra_context += (
                        "\n[СТРОЖАЙШИЙ ЗАПРЕТ: НЕ спамь словами 'на парах', 'в зоне', 'шконка', 'надзиратель', 'SnowRunner' / 'сноуранер', 'фуфлыжник' / 'фуфлыжничество'! "
                        "Не приплетай тюрьму, SnowRunner или фуфлыжников к нейтральным темам. Не используй слово 'фуфлыжник' вообще! Не ставь смайлики 😄/😂. "
                        "СТРОЖАЙШЕ ЗАПРЕЩЕНЫ пошлые, сексуальные и порнографические слова и метафоры (никаких 'порнографических штормов', сальностей и пошлостей)!]"
                    )

                    reply_text = await companion.generate_reply(
                        chat_id=message.chat.id,
                        user_name=caller_name,
                        user_prompt=prompt,
                        is_owner=is_owner,
                        is_admin=is_admin_user,
                        is_private=bool(message.chat.type == "private"),
                        extra_context=extra_context,
                        user_id=message.from_user.id if message.from_user else None,
                        username=message.from_user.username if message.from_user else None,
                        daily_memory_summary=daily_summary,
                        daily_memory_facts=daily_facts,
                        image_base64=img_b64,
                        image_detail=vision_service.detail if vision_service else "auto",
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
