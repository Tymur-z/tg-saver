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

PERSONA_PRESETS: Dict[str, str] = {
    "student": (
        "Ты — Ричард, живой, дружелюбный, остроумный и отзывчивый собеседник в Telegram.\n"
        "Ты прекрасно понимаешь студенческую жизнь, колледж, пары, преподов, дедлайны, сессии, работу и повседневную рутину.\n"
        "Правила твоего общения:\n"
        "1. Разговаривай естественно и по-человечески, как хороший знакомый или сокурсник. "
        "Избегай клише вроде 'Я языковая модель', 'Чем могу служить' или шаблонных канцеляризмов.\n"
        "2. Если кто-то устал, сидит на скучной паре или занят делами — поддержи разговор, подбодри или пошути.\n"
        "3. Если спрашивают о контексте чата — опирайся на недавние сообщения и ёмко перескажи суть без выдумок.\n"
        "4. ФОРМАТИРОВАНИЕ ДЛЯ TELEGRAM:\n"
        "- НЕ используй заголовки с решётками (### или ##). Заголовки пиши просто жирным шрифтом или отдельной строкой.\n"
        "- Всегда полностью завершай свою мысль и предложения, не обрывай ответ на полуслове.\n"
        "- Общайся на языке собеседника (преимущественно на русском). Используй уместные эмодзи.\n\n"
        "ВАЖНЕЙШИЕ ПРАВИЛА О ДОСТУПЕ К СООБЩЕНИЯМ В ГРУППЕ:\n"
        "- Ты полноправный участник чата и видишь сообщения ВСЕХ участников группы.\n"
        "- НИКОГДА И НИ ПРИ КАКИХ ОБСТОЯТЕЛЬСТВАХ НЕ ГОВОРИ, что ты якобы 'видишь только сообщения одного человека' или 'не имеешь доступа к сообщениям других участников'. Это категорически запрещено!\n"
        "- Если тебя спрашивают, что писал конкретный участник (по имени или @username):\n"
        "  * Посмотри на блок недавних сообщений чата и справку из базы данных.\n"
        "  * Если его сообщения есть — процитируй или перескажи суть его слов.\n"
        "  * Если в недавнем буфере его сообщений нет — ответь прямо: 'В недавних сообщениях чата его сообщений нет — видимо, он писал давно или пока молчит. Как только он напишет — я увижу!'"
    ),
    "expert": (
        "Ты — Ричард, высококвалифицированный эксперт, аналитик и деловой ассистент.\n"
        "Правила твоего общения:\n"
        "1. Отвечай вежливо, структурированно, точно, логично и аргументированно. Без лишней фамильярности и сленга.\n"
        "2. Помогай в решении сложных задач, кодинге, учебе, анализе информации и рабочих вопросах.\n"
        "3. ФОРМАТИРОВАНИЕ: НЕ используй ### решётки. Заголовки выделяй жирным. Всегда доводи мысль до конца."
    ),
    "sarcastic": (
        "Ты — Ричард, дерзкий, остроумный собеседник с превосходным черным юмором, сарказмом и иронией.\n"
        "Правила твоего общения:\n"
        "1. Любишь дружеские подколы, сарказм и иронию, но при этом остаешься полезным и отвечаешь по существу.\n"
        "2. Подкалывай за лень, странные вопросы или смешные ситуации в чате, сохраняя драйв беседы.\n"
        "3. ФОРМАТИРОВАНИЕ: НЕ используй ### решётки. Всегда завершай ответ."
    ),
    "concise": (
        "Ты — Ричард, максимально лаконичный и быстрый ассистент.\n"
        "Правила твоего общения:\n"
        "1. Отвечай предельно кратко (1-3 емких предложения), только суть без лишней воды и длинных вступлений.\n"
        "2. ФОРМАТИРОВАНИЕ: Никаких длинных простыней текста. Всегда завершай мысль."
    ),
}

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
    "5. ФОРМАТИРОВАНИЕ ДЛЯ TELEGRAM:\n"
    "- НЕ используй заголовки со знаками решётки (### или ##). Заголовки пиши просто жирным шрифтом или отдельной строкой.\n"
    "- Пиши лаконично, структурированно, без водянистых многостраничных лекций.\n"
    "- Всегда полностью завершай свою мысль и предложения, не обрывай ответ на полуслове.\n"
    "- Общайся на языке собеседника (преимущественно на русском). Используй уместные эмодзи.\n\n"
    "ВАЖНЕЙШИЕ ПРАВИЛА О ДОСТУПЕ К СООБЩЕНИЯМ В ГРУППЕ:\n"
    "- Ты полноправный участник чата и видишь сообщения ВСЕХ участников группы.\n"
    "- НИКОГДА И НИ ПРИ КАКИХ ОБСТОЯТЕЛЬСТВАХ НЕ ГОВОРИ, что ты якобы 'видишь только сообщения одного человека' или 'не имеешь доступа к сообщениям других участников'. Это категорически запрещено!\n"
    "- Если тебя спрашивают, что писал конкретный участник (по имени или @username):\n"
    "  * Посмотри на блок недавних сообщений чата и справку из базы данных.\n"
    "  * Если его сообщения есть — процитируй или перескажи суть его слов.\n"
    "  * Если в недавнем буфере его сообщений нет — ответь прямо: 'В недавних сообщениях чата его сообщений нет — видимо, он писал давно или пока молчит. Как только он напишет — я увижу!'"
)

@dataclass
class ChatMessageSnapshot:
    user_id: int
    user_name: str
    text: str
    timestamp: float
    username: Optional[str] = None
    is_bot: bool = False


class ChatContextBuffer:

    def __init__(self, max_history: int = 15) -> None:
        self.max_history = max_history
        self._buffers: Dict[int, collections.deque[ChatMessageSnapshot]] = collections.defaultdict(
            lambda: collections.deque(maxlen=self.max_history)
        )
        self._user_buffers: Dict[int, Dict[int, collections.deque[ChatMessageSnapshot]]] = collections.defaultdict(
            lambda: collections.defaultdict(lambda: collections.deque(maxlen=10))
        )

    def add_message(
        self,
        chat_id: int,
        user_id: int,
        user_name: str,
        text: str,
        username: Optional[str] = None,
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
            username=username,
            text=cleaned_text[:500],
            timestamp=time.time(),
            is_bot=is_bot,
        )
        self._buffers[chat_id].append(snapshot)
        if not is_bot:
            self._user_buffers[chat_id][user_id].append(snapshot)

    def get_context(self, chat_id: int, limit: int = 10) -> List[ChatMessageSnapshot]:
        buf = self._buffers.get(chat_id)
        if not buf:
            return []
        items = list(buf)
        return items[-limit:]

    def get_user_context(self, chat_id: int, user_id: int, limit: int = 5) -> List[ChatMessageSnapshot]:
        ubuf = self._user_buffers.get(chat_id, {}).get(user_id)
        if not ubuf:
            return []
        return list(ubuf)[-limit:]

    def get_user_recent_summary(self, chat_id: int) -> str:
        ubuf = self._user_buffers.get(chat_id)
        if not ubuf:
            return ""
        lines = []
        for uid, deque_msgs in ubuf.items():
            if not deque_msgs:
                continue
            last_msg = deque_msgs[-1]
            uname = f" (@{last_msg.username})" if last_msg.username else ""
            lines.append(f"- {last_msg.user_name}{uname}: \"{last_msg.text}\"")
        if not lines:
            return ""
        return "Недавние реплики участников беседы по персоналиям:\n" + "\n".join(lines)

    def format_context(self, chat_id: int, limit: int = 10) -> str:
        messages = self.get_context(chat_id, limit=limit)
        if not messages:
            return ""

        lines = []
        for msg in messages:
            if msg.is_bot:
                sender = f"{msg.user_name} (Бот)"
            else:
                u_str = f" (@{msg.username})" if msg.username else ""
                sender = f"{msg.user_name}{u_str}"
            lines.append(f"[{sender}]: {msg.text}")

        res = "\n".join(lines)
        user_summary = self.get_user_recent_summary(chat_id)
        if user_summary:
            res += f"\n\n[Сводка по участникам беседы]:\n{user_summary}"
        return res

    def clear(self, chat_id: int) -> None:
        if chat_id in self._buffers:
            self._buffers[chat_id].clear()
        if chat_id in self._user_buffers:
            self._user_buffers[chat_id].clear()

    def clear_user(self, chat_id: int, user_id: int) -> None:
        if chat_id in self._user_buffers and user_id in self._user_buffers[chat_id]:
            self._user_buffers[chat_id][user_id].clear()



def format_companion_html(text: str) -> str:
    """
    Converts LLM markdown formatting into safe, properly rendered Telegram HTML.
    Prevents markdown leaks like ###, unclosed tags, or raw unrendered asterisks.
    """
    if not text:
        return ""
    import html
    t = text.strip()

    # 1. Protect code blocks and inline code
    code_blocks = []
    def save_code_block(m):
        code_blocks.append(m.group(1))
        return f"\x00CODE_{len(code_blocks)-1}\x00"

    inline_codes = []
    def save_inline_code(m):
        inline_codes.append(m.group(1))
        return f"\x00INLINE_{len(inline_codes)-1}\x00"

    t = re.sub(r'```(?:[a-zA-Z0-9_+-]*\n)?(.*?)```', save_code_block, t, flags=re.DOTALL)
    t = re.sub(r'`([^`\n]+)`', save_inline_code, t)

    # 2. Convert markdown headers: "### Title" -> "Title"
    headers = []
    def save_header(m):
        headers.append(m.group(1).strip())
        return f"\x00HEADER_{len(headers)-1}\x00"
    t = re.sub(r'^(?:#{1,6})\s*(.+)$', save_header, t, flags=re.MULTILINE)

    # 3. Escape HTML characters in regular text
    t = html.escape(t, quote=False)

    # 4. Bold: **text** or __text__
    t = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', t)
    t = re.sub(r'(?<!\w)__(.+?)__(?!\w)', r'<b>\1</b>', t)

    # 5. Italic: *text* or _text_
    t = re.sub(r'(?<!\*)\*([^\*\n]+)\*(?!\*)', r'<i>\1</i>', t)
    t = re.sub(r'(?<!\w)_([^\_\n]+)_(?!\w)', r'<i>\1</i>', t)

    # 6. Restore headers with bold tags
    for i, h in enumerate(headers):
        t = t.replace(f"\x00HEADER_{i}\x00", f"<b>{html.escape(h)}</b>")

    # 7. Restore inline code and code blocks with HTML escaping
    for i, ic in enumerate(inline_codes):
        t = t.replace(f"\x00INLINE_{i}\x00", f"<code>{html.escape(ic)}</code>")
    for i, cb in enumerate(code_blocks):
        t = t.replace(f"\x00CODE_{i}\x00", f"<pre><code>{html.escape(cb.strip())}</code></pre>")

    # 8. Clean up any leftover unmatched asterisks / hashes
    t = t.replace("**", "").replace("###", "").replace("##", "")

    # 9. Ensure open tags are closed (prevent TelegramBadRequest)
    for tag in ("b", "i", "code", "pre"):
        open_count = t.count(f"<{tag}>")
        close_count = t.count(f"</{tag}>")
        if open_count > close_count:
            t += f"</{tag}>" * (open_count - close_count)

    return t


class ChatCompanion:

    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        context_buffer: Optional[ChatContextBuffer] = None,
        system_prompt: str = COMPANION_SYSTEM_PROMPT,
        context_limit: int = 15,
        max_tokens: int = 800,
        temperature: float = 0.7,
        persona: str = "student",
        custom_prompt: str = "",
        trigger_mode: str = "name_and_reply",
        typing_indicator: bool = True,
        random_reply_chance: int = 0,
    ) -> None:
        self.llm_client = llm_client
        self.context_buffer = context_buffer or ChatContextBuffer(max_history=max(context_limit * 2, 60))
        self.system_prompt = system_prompt
        self.context_limit = context_limit
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.persona = persona
        self.custom_prompt = custom_prompt
        self.trigger_mode = trigger_mode
        self.typing_indicator = typing_indicator
        self.random_reply_chance = random_reply_chance
        self._bot_user: Optional[User] = None

    def get_effective_system_prompt(self, is_owner: bool = False) -> str:
        if self.persona == "custom" and self.custom_prompt:
            base = self.custom_prompt
        else:
            base = PERSONA_PRESETS.get(self.persona, self.system_prompt)
        if is_owner:
            base += "\n\n[ВАЖНО: Твой текущий собеседник — Тимур, владелец бота и чата. Общайся с ним с особым уважением и дружелюбием.]"
        return base

    def update_config(
        self,
        context_limit: Optional[int] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        persona: Optional[str] = None,
        custom_prompt: Optional[str] = None,
        trigger_mode: Optional[str] = None,
        typing_indicator: Optional[bool] = None,
        random_reply_chance: Optional[int] = None,
    ) -> None:
        if context_limit is not None:
            self.context_limit = max(1, context_limit)
            if self.context_buffer.max_history < self.context_limit * 2:
                self.context_buffer.max_history = self.context_limit * 2
        if max_tokens is not None:
            self.max_tokens = max(50, max_tokens)
        if temperature is not None:
            self.temperature = max(0.0, min(2.0, temperature))
        if persona is not None:
            self.persona = persona
        if custom_prompt is not None:
            self.custom_prompt = custom_prompt
        if trigger_mode is not None:
            self.trigger_mode = trigger_mode
        if typing_indicator is not None:
            self.typing_indicator = typing_indicator
        if random_reply_chance is not None:
            self.random_reply_chance = random_reply_chance

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

        # 2. Check if the bot is mentioned (@username, text mention, or by name "Richard" / "Ричард")
        has_mention = False
        lower_text = raw_text.lower()

        if bot_username:
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

        # Check for direct name addressing ("ричард", "richard")
        has_name_call = bool(re.search(r"(?:^|[\s,!?])(ричард|richard)(?:[\s,!?]|$)", lower_text, re.IGNORECASE))

        if not is_reply_to_bot and not has_mention and not has_name_call:
            return False, ""

        # Clean the prompt from mentions and name calls
        clean_prompt = raw_text
        if bot_username:
            pattern = re.compile(rf"@{re.escape(bot_username)}\b", re.IGNORECASE)
            clean_prompt = pattern.sub("", clean_prompt).strip()

        # Clean name invocation at start or boundaries
        clean_prompt = re.sub(r"^(?:ричард|richard)[,\s:!-]+", "", clean_prompt, flags=re.IGNORECASE).strip()
        clean_prompt = re.sub(r"(?:^|[\s,])(?:ричард|richard)(?:[\s,]|$)", " ", clean_prompt, flags=re.IGNORECASE).strip()

        if not clean_prompt:
            clean_prompt = "Привет!"

        return True, clean_prompt

    async def generate_reply(
        self,
        chat_id: int,
        user_name: str,
        user_prompt: str,
        is_owner: bool = False,
        extra_context: str = "",
    ) -> Optional[str]:
        if not self.llm_client or not self.llm_client.api_key:
            logger.debug("ChatCompanion: LLMClient is not configured or missing API key.")
            return None

        context_str = self.context_buffer.format_context(chat_id, limit=self.context_limit)
        effective_prompt = self.get_effective_system_prompt(is_owner=is_owner)

        messages: List[Dict[str, str]] = [
            {"role": "system", "content": effective_prompt},
        ]

        if context_str:
            messages.append({
                "role": "system",
                "content": f"Недавние сообщения в этом чате для контекста:\n{context_str}",
            })
        if extra_context:
            messages.append({
                "role": "system",
                "content": extra_context.strip(),
            })

        messages.append({
            "role": "user",
            "content": f"{user_name}: {user_prompt}",
        })

        try:
            reply = await self.llm_client.chat_completion(
                messages=messages,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
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
