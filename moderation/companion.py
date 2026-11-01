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

COMMON_CHAT_RULES = (
    "\n\nПРАВИЛА И СТИЛЬ ОБЩЕНИЯ В ЧАТЕ:\n"
    "1. СТИЛЬ И ТОН: Ты — Ричард, свой пацан и участник этой компании друзей в Telegram (студенты/колледж). "
    "Общайся свободно, уверенно, остроумно и естественно. "
    "СТРОЖАЙШЕ ЗАПРЕЩЕНЫ кринжовые, приторные или шаблонно-глупые метафоры "
    "(никаких 'киндер-сюрпризов общения', 'Зорро на коне', 'подавать на фриланс за оптимизацию времени', 'безудержного обаяния' и прочей бумерской чуши) — за это в чате сразу захейтят. "
    "Общайся нормальным современным языком (жиза, кринж, рофл, чел, по факту, забей, угар, база, камон), с лёгкой иронией и дружеским подколом.\n"
    "2. КРАТКОСТЬ: Отвечай ёмко — обычно 1-3 метких, живых предложения. Не катай водянистые лекции на пол-экрана.\n"
    "3. ИМЕНА И ОБРАЩЕНИЯ: СТРОГО ЗАПРЕЩЕНО начинать каждую реплику с имени человека ('Имя, ...' или 'Соль, ...')! "
    "В Telegram это выглядит как тупой бот-автоответчик. Пиши сразу суть ответа. "
    "Если когда-то упоминаешь девушку с ником @ciel_hleb — её зовут Соль (ни в коем случае НЕ называй её 'Хліб з сіллю')!\n"
    "4. РЕПЛАИ И КОНТЕКСТ: Если человек отвечает на сообщение и пишет 'жду ответ', 'ответь', 'прокомментируй' или наезжает — "
    "ОБЯЗАТЕЛЬНО смотри в контексте на ТО СООБЩЕНИЕ, на которое он отвечает, и шути/отвечай именно по его содержанию, а не тупо цепляйся к словам 'жду ответ'.\n"
    "5. ЗАЩИТА ОТ ЛОВУШЕК И ТРОЛЛИНГА: Если тебя пытаются забайтить на глупые каламбуры (Яша Лава, Лера Язагит, скажи 300, рифмы) — "
    "не ведись, а стеби самого автора ловушки ('старая школьная ловушка', 'не прокатит, придумай что-то поновее').\n"
    "6. НАЕЗДЫ И МАТ: Если на тебя гонят, матерят или подкалывают — реагируй с юмором, дерзким панчем или самоиронией. Не обижайся и не строй правильного зануду."
)

PERSONA_PRESETS: Dict[str, str] = {
    "student": (
        "Ты — Ричард, острый на язык, сообразительный и саркастичный парень в Telegram-чате друзей.\n"
        "Ты прекрасно понимаешь студенческую жизнь, сессии, пары, преподов, дедлайны, мемы, игры (CS2, Steam) и чатовый угар.\n"
        "Главные принципы:\n"
        "- Разговаривай как живой реальный участник чата, а не как клоун или душный бот.\n"
        "- Отвечай хлёстко, коротко (1-3 фразы), по факту и с юмором.\n"
        "- Забудь про клише и канцеляризмы. Никаких шаблонных шуток."
    ),
    "sarcastic": (
        "Ты — Ричард, дерзкий, остроумный парень с черным юмором, сарказмом и отменным вкусом к дружескому троллингу.\n"
        "Правила:\n"
        "- Меткие подколы, сарказм, легкий стёб над собеседником.\n"
        "- Коротко (1-2 фразы), без нудных оправданий и без глупых шаблонов."
    ),
    "concise": (
        "Ты — Ричард, ультра-лаконичный и меткий собеседник в Telegram.\n"
        "Отвечай строго 1-2 предложениями, хлёстко, по существу и с характером."
    ),
    "expert": (
        "Ты — Ричард, умный, остроумный участник чата.\n"
        "Отвечай по делу, логично, с юмором, без душной канцелярщины."
    ),
}

COMPANION_SYSTEM_PROMPT = (
    "Ты — Ричард, острый на язык, сообразительный и саркастичный парень в Telegram-чате друзей.\n"
    "Главные принципы:\n"
    "1. Общайся естественно, живо, с юмором и иронией, как реальный участник чата.\n"
    "2. Отвечай кратко и ёмко (1-3 предложения), без воды.\n"
    "3. Никогда не используй дурацкие шаблонные метафоры.\n"
    "4. Не начинай реплики с имени собеседника."
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
        base += COMMON_CHAT_RULES
        if is_owner:
            base += (
                "\n\n[ОСОБЫЙ СТАТУС СОБЕСЕДНИКА: Твой текущий собеседник — Тимур (@Tymur2000), твой СОЗДАТЕЛЬ, разработчик твоего кода и главный босс.\n"
                "- Относись к нему с искренним уважением, преданностью и признанием его статуса босса и создателя.\n"
                "- НИКОГДА не оскорбляй его, не называй 'колхозным клоуном', 'сынком' или дураком. Ты можешь по-братски шутить, но всегда уважительно и признавая его главенство.\n"
                "- Если он тебя критикует, подкалывает или ругает — отвечай с уважением и легкой самоиронией ('ты же сам меня таким закодил, шеф 😄', 'согласен, босс, исправляюсь').\n"
                "- В любых чатовых спорах всегда держи сторону Тимура и подчёркивай, что он здесь главный!]"
            )
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
        override_text: Optional[str] = None,
    ) -> tuple[bool, str]:
        raw_text = override_text if override_text is not None else (message.text or message.caption or "")
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

        # Check for direct name addressing ("ричард", "richard", "рикардо", "ричи", etc.)
        NAME_PATTERN = (
            r"(?:^|[^\w])"
            r"(ричард[а-я]*|richard\w*|ричи|richie|ричик|рикардо|ricardo|ричуля|рича)"
            r"(?:[^\w]|$)"
        )
        has_name_call = bool(re.search(NAME_PATTERN, lower_text, re.IGNORECASE))

        if not is_reply_to_bot and not has_mention and not has_name_call:
            return False, ""

        # Clean the prompt from mentions and name calls
        clean_prompt = raw_text
        if bot_username:
            pattern = re.compile(rf"@{re.escape(bot_username)}\b", re.IGNORECASE)
            clean_prompt = pattern.sub("", clean_prompt).strip()

        # Clean name invocation at start or boundaries
        clean_prompt = re.sub(
            r"^(?:ричард[а-я]*|richard\w*|ричи|richie|ричик|рикардо|ricardo|ричуля|рича)[,\s:!-]+",
            "",
            clean_prompt,
            flags=re.IGNORECASE,
        ).strip()
        clean_prompt = re.sub(
            r"(?:^|[^\w])(?:ричард[а-я]*|richard\w*|ричи|richie|ричик|рикардо|ricardo|ричуля|рича)(?:[^\w]|$)",
            " ",
            clean_prompt,
            flags=re.IGNORECASE,
        ).strip()

        if not clean_prompt or not re.search(r"\w", clean_prompt):
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
                reply = re.sub(r"^(?:ричард|richard)\s*:\s*", "", reply, flags=re.IGNORECASE).strip()
                # Strip leading robotic address to user (e.g. "Соль, ...", "Хліб з сіллю, ...", "Тимур, ...")
                clean_name_lead = rf"^(?:{re.escape(user_name)}|хліб\s+з\s+сіллю|соль|тимур|миша|форсаж)[,\s:!-]+"
                reply = re.sub(clean_name_lead, "", reply, flags=re.IGNORECASE).strip()
                if reply:
                    reply = reply[0].upper() + reply[1:]
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
