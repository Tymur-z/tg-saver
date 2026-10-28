"""Модуль ИИ-собеседника и контекстного буфера сообщений для чатов."""

from __future__ import annotations

import collections
import logging
import re
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from aiogram import Bot
from aiogram.enums import MessageEntityType
from aiogram.types import Message, User

from moderation.llm_client import LLMClient

logger = logging.getLogger(__name__)

COMPANION_SYSTEM_PROMPT = (
    "Ты — Ричард, живой, дружелюбный, остроумный и отзывчивый собеседник в Telegram.\n"
    "Твоя цель — общаться с участниками чата, поддерживать беседу, отвечать на вопросы и при необходимости шутить.\n\n"
    "Правила твоего общения:\n"
    "1. Разговаривай естественно и по-человечески, как хороший знакомый или сокурсник. "
    "Избегай клише вроде 'Я языковая модель', 'Чем могу служить' или шаблонных канцеляризмов.\n"
    "2. Ты прекрасно понимаешь студенческую жизнь, колледж, пары, преподов, дедлайны, сессии, работу и повседневную рутину. "
    "Если кто-то устал, сидит на скучной паре или занят делами — поддержи разговор, подбодри или пошути.\n"
    "3. Если тебя спрашивают о том, что происходит в чате (например, 'о чем тут говорили?', 'что обсуждали?', 'введи в курс дела'), "
    "опирайся на предоставленный контекст недавних сообщений и кратко, ёмко перескажи суть без выдумок.\n"
    "4. Если вопрос не связан с контекстом чата — отвечай напрямую по сути вопроса (учеба, наука, технологии, житейские советы, юмор).\n"
    "5. Общайся на языке собеседника (преимущественно на русском). Пиши лаконично и читабельно для мобильных экранов, "
    "используй уместные эмодзи без фанатизма."
)


@dataclass
class ChatMessageSnapshot:
    user_id: int
    user_name: str
    text: str
    timestamp: float
    is_bot: bool = False


class ChatContextBuffer:

    def __init__(self, max_history: int = 15) -> None:
        self.max_history = max_history
        self._buffers: Dict[int, collections.deque[ChatMessageSnapshot]] = collections.defaultdict(
            lambda: collections.deque(maxlen=self.max_history)
        )

    def add_message(
        self,
        chat_id: int,
        user_id: int,
        user_name: str,
        text: str,
        is_bot: bool = False,
    ) -> None:
        cleaned_text = text.strip()
        if not cleaned_text:
            return
        if cleaned_text.startswith("/"):
            return

        snapshot = ChatMessageSnapshot(
            user_id=user_id,
            user_name=user_name,
            text=cleaned_text[:400],
            timestamp=time.time(),
            is_bot=is_bot,
        )
        self._buffers[chat_id].append(snapshot)

    def get_context(self, chat_id: int, limit: int = 10) -> List[ChatMessageSnapshot]:
        buf = self._buffers.get(chat_id)
        if not buf:
            return []
        items = list(buf)
        return items[-limit:]

    def format_context(self, chat_id: int, limit: int = 10) -> str:
        messages = self.get_context(chat_id, limit=limit)
        if not messages:
            return ""

        lines = []
        for msg in messages:
            sender = f"{msg.user_name} (Бот)" if msg.is_bot else msg.user_name
            lines.append(f"[{sender}]: {msg.text}")
        return "\n".join(lines)

    def clear(self, chat_id: int) -> None:
        if chat_id in self._buffers:
            self._buffers[chat_id].clear()


class ChatCompanion:

    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        context_buffer: Optional[ChatContextBuffer] = None,
        system_prompt: str = COMPANION_SYSTEM_PROMPT,
    ) -> None:
        self.llm_client = llm_client
        self.context_buffer = context_buffer or ChatContextBuffer()
        self.system_prompt = system_prompt
        self._bot_user: Optional[User] = None

    async def get_bot_user(self, bot: Bot) -> User:
        if self._bot_user is None:
            self._bot_user = await bot.get_me()
        return self._bot_user

    def is_triggered(
        self,
        message: Message,
        bot_username: Optional[str] = None,
        bot_id: Optional[int] = None,
    ) -> tuple[bool, str]:
        raw_text = message.text or message.caption or ""
        raw_text = raw_text.strip()

        if message.chat.type == "private":
            if raw_text and not raw_text.startswith("/"):
                return True, raw_text
            return False, ""

        if not raw_text:
            return False, ""

        # 1. Check if message is a reply to the bot
        is_reply_to_bot = False
        if message.reply_to_message and message.reply_to_message.from_user:
            if bot_id and message.reply_to_message.from_user.id == bot_id:
                is_reply_to_bot = True
            elif bot_username and message.reply_to_message.from_user.username:
                if message.reply_to_message.from_user.username.lower() == bot_username.lower():
                    is_reply_to_bot = True

        # 2. Check if the bot is mentioned
        has_mention = False
        if bot_username:
            lower_text = raw_text.lower()
            mention_target = f"@{bot_username.lower()}"
            if mention_target in lower_text:
                has_mention = True

        if not has_mention and message.entities and bot_username:
            for ent in message.entities:
                if ent.type == MessageEntityType.MENTION:
                    extracted = raw_text[ent.offset : ent.offset + ent.length]
                    if extracted.lower() == f"@{bot_username.lower()}":
                        has_mention = True
                        break
                elif ent.type == MessageEntityType.TEXT_MENTION and ent.user:
                    if bot_id and ent.user.id == bot_id:
                        has_mention = True
                        break

        if not is_reply_to_bot and not has_mention:
            return False, ""

        # Clean the prompt
        clean_prompt = raw_text
        if bot_username:
            pattern = re.compile(rf"@{re.escape(bot_username)}\b", re.IGNORECASE)
            clean_prompt = pattern.sub("", clean_prompt).strip()

        if not clean_prompt:
            clean_prompt = "Привет!"

        return True, clean_prompt

    async def generate_reply(
        self,
        chat_id: int,
        user_name: str,
        user_prompt: str,
    ) -> Optional[str]:
        if not self.llm_client or not self.llm_client.api_key:
            logger.debug("ChatCompanion: LLMClient is not configured or missing API key.")
            return None

        context_str = self.context_buffer.format_context(chat_id, limit=12)

        messages: List[Dict[str, str]] = [
            {"role": "system", "content": self.system_prompt},
        ]

        if context_str:
            messages.append({
                "role": "system",
                "content": f"Недавние сообщения в этом чате для контекста:\n{context_str}",
            })

        messages.append({
            "role": "user",
            "content": f"{user_name}: {user_prompt}",
        })

        try:
            reply = await self.llm_client.chat_completion(
                messages=messages,
                temperature=0.7,
                max_tokens=350,
            )
            if reply:
                reply = reply.strip()
                self.context_buffer.add_message(
                    chat_id=chat_id,
                    user_id=0,
                    user_name="Ричард",
                    text=reply,
                    is_bot=True,
                )
                return reply
        except Exception as e:
            logger.warning("Error generating companion reply for chat %s: %s", chat_id, e)

        return None
