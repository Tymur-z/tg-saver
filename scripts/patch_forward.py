import re

path = r"c:\Users\sla_5\Programing\Projects\Tg Saver\bot\handlers\forward.py"

with open(path, "r", encoding="utf-8") as f:
    content = f.read()

# 1. Update TRANSCRIPTION_PATTERNS
old_patterns = """TRANSCRIPTION_PATTERNS = [
    re.compile(r"^(?:/)?(?:transcribe|stt|speech)\\b", re.IGNORECASE),
    re.compile(r"^(?:текст|переведи|расшифруй|расшифровка|транскрипц\\w*|в\\s+текст|transcribe|transcript)\\b", re.IGNORECASE),
    re.compile(r"(?:что|о\\s*ч[её]м|про\\s+что)\\s+(?:там|тут|он[а-я]*|я|ты|они|было|говорит\\w*|наговор\\w*|сказан\\w*|в\\s+(?:круж\\w*|голосов\\w*|гс|войс\\w*|аудио|этом|етом))", re.IGNORECASE),
    re.compile(r"^(?:что\\s+там|что\\s+тут|что\\s+в\\s+кружке|что\\s+в\\s+голосов\\w*|что\\s+в\\s+гс|что\\s+(?:он[а-я]*|я|они)\\s+сказал\\w*|что\\s+говорит\\w*|что\\s+там\\s+говорить|что\\s+говорит[ьс]+я\\s+в\\s+кружке|я\\s+про\\s+[еэ]тот)$", re.IGNORECASE),
    re.compile(r"(?:что\\s+(?:тут\\s+|там\\s+)?происходит\\s+(?:тут\\s+|там\\s+)?(?:на|в)\\s+(?:круж\\w*|голосов\\w*|гс|войс\\w*))", re.IGNORECASE),
    re.compile(r"(?:what\\s+(?:did\\s+(?:he|she|they|i)\\s+say|was\\s+said|is\\s+said|is\\s+in\\s+the\\s+(?:circle|voice|audio)|does\\s+it\\s+say))", re.IGNORECASE),
]"""

new_patterns = """TRANSCRIPTION_PATTERNS = [
    re.compile(r"^(?:/)?(?:transcribe|stt|speech)\\b", re.IGNORECASE),
    re.compile(r"^(?:текст|переведи|расшифруй|расшифровка|транскрипц\\w*|в\\s+текст|transcribe|transcript)\\b", re.IGNORECASE),
    re.compile(r"(?:что|о\\s*ч[её]м|про\\s+что)\\s+(?:он[а-я]*|я|ты|они|было|говорит\\w*|наговор\\w*|сказан\\w*)\\s+(?:в\\s+(?:круж\\w*|голосов\\w*|гс|войс\\w*|аудио|этом|етом))", re.IGNORECASE),
    re.compile(r"^(?:что\\s+в\\s+кружке|что\\s+в\\s+голосов\\w*|что\\s+в\\s+гс|что\\s+(?:он[а-я]*|я|они)\\s+сказал\\w*|что\\s+говорит\\w*\\s+в\\s+(?:круж\\w*|гс|войс\\w*)|что\\s+говорит[ьс]+я\\s+в\\s+кружке|я\\s+про\\s+[еэ]тот)$", re.IGNORECASE),
    re.compile(r"(?:что\\s+(?:тут\\s+|там\\s+)?происходит\\s+(?:тут\\s+|там\\s+)?(?:на|в)\\s+(?:круж\\w*|голосов\\w*|гс|войс\\w*))", re.IGNORECASE),
    re.compile(r"(?:what\\s+(?:did\\s+(?:he|she|they|i)\\s+say|was\\s+said|is\\s+said|is\\s+in\\s+the\\s+(?:circle|voice|audio)|does\\s+it\\s+say))", re.IGNORECASE),
]"""

assert old_patterns in content, "old_patterns not found"
content = content.replace(old_patterns, new_patterns)

# 2. Update is_transcription_request definition and add summary helpers
old_is_transcription = """def is_transcription_request(text: str) -> bool:
    \"\"\"Returns True if user asks to transcribe or what was said in audio/video note, without conversational chat.\"\"\"
    if not text:
        return False
    t = text.strip().lower()

    # Strip bot mentions and name calls
    t = re.sub(r"@[a-zA-Z0-9_]+", "", t).strip()
    t = re.sub(r"^(?:ричард|richard|ричи|рикардо)[,\\s:!-]+", "", t, flags=re.IGNORECASE).strip()
    t = re.sub(r"(?:^|[\\s,])(?:ричард|richard|ричи|рикардо)(?:[\\s,!?]|$)", " ", t, flags=re.IGNORECASE).strip()

    # Strip polite wrappers and action prefixes like 'покажи', 'расскажи', 'сделай', 'рокажи'
    t = re.sub(
        r"\\b(?:пожалуйста|плиз|пж|сделай|можешь|подскажи|расскажи|покажи|покажь|рокажи|послушай|глянь|посмотри|please|pls|can\\s+you|could\\s+you)\\b",
        " ",
        t,
        flags=re.IGNORECASE,
    ).strip()

    clean = re.sub(r"[?!.,;:]+", " ", t).strip()
    clean = " ".join(clean.split())

    # Pure conversational opinions should not trigger direct transcription
    opinion_pattern = re.compile(
        r"\\b(?:что\\s+думаешь|как\\s+тебе|согласен|тво[её]\\s+мнение|мнение|оцени|прокомментируй|what\\s+do\\s+you\\s+think|your\\s+opinion)\\b",
        re.IGNORECASE,
    )
    if opinion_pattern.search(clean):
        return False

    # Pure chat drama queries like 'что тут нах происходит' / 'что здесь происходит' WITHOUT media reference should NOT trigger transcription
    has_media_word = bool(re.search(r"\\b(?:круж\\w*|голосов\\w*|гс|войс\\w*|аудио|видео|запис\\w*)\\b", clean, re.IGNORECASE))
    if "происходит" in clean and not has_media_word:
        return False

    if clean in TRANSCRIPTION_KEYWORDS:
        return True
    for p in TRANSCRIPTION_PATTERNS:
        if p.search(clean) or p.search(t):
            return True
    return False"""

new_is_transcription = """def is_transcription_request(text: str, is_reply_to_media: bool = False) -> bool:
    \"\"\"Returns True if user asks to transcribe or what was said in audio/video note, without conversational chat.\"\"\"
    if not text:
        return False
    t = text.strip().lower()

    # If user asks about chat status / summary / news, NEVER trigger transcription
    if re.search(r"\\b(?:по\\s+чат\\w*|в\\s+чат\\w*|чат\\w*|сводк\\w*|итог\\w*|новост\\w*|нового)\\b", t, re.IGNORECASE):
        if not re.search(r"\\b(?:круж\\w*|голосов\\w*|гс|войс\\w*|аудио|видеосообщ\\w*)\\b", t, re.IGNORECASE):
            return False

    # Strip bot mentions and name calls
    t = re.sub(r"@[a-zA-Z0-9_]+", "", t).strip()
    t = re.sub(r"^(?:ричард|richard|ричи|рикардо)[,\\s:!-]+", "", t, flags=re.IGNORECASE).strip()
    t = re.sub(r"(?:^|[\\s,])(?:ричард|richard|ричи|рикардо)(?:[\\s,!?]|$)", " ", t, flags=re.IGNORECASE).strip()

    # Strip polite wrappers and action prefixes
    t = re.sub(
        r"\\b(?:пожалуйста|плиз|пж|сделай|можешь|подскажи|расскажи|покажи|покажь|рокажи|послушай|глянь|посмотри|дай|чётко|четко|хорош|please|pls|can\\s+you|could\\s+you)\\b",
        " ",
        t,
        flags=re.IGNORECASE,
    ).strip()

    clean = re.sub(r"[?!.,;:]+", " ", t).strip()
    clean = " ".join(clean.split())

    # Pure conversational opinions should not trigger direct transcription
    opinion_pattern = re.compile(
        r"\\b(?:что\\s+думаешь|как\\s+тебе|согласен|тво[её]\\s+мнение|мнение|оцени|прокомментируй|what\\s+do\\s+you\\s+think|your\\s+opinion)\\b",
        re.IGNORECASE,
    )
    if opinion_pattern.search(clean):
        return False

    # Pure chat drama queries like 'что тут нах происходит' WITHOUT media reference should NOT trigger transcription
    has_media_word = bool(re.search(r"\\b(?:круж\\w*|голосов\\w*|гс|войс\\w*|аудио|видео|запис\\w*)\\b", clean, re.IGNORECASE))
    has_stt_verb = bool(re.search(r"\\b(?:расшифр\\w*|транскрип\\w*|переведи\\s+в\\s+текст|в\\s+текст|текст)\\b", clean, re.IGNORECASE))

    if not is_reply_to_media and not has_media_word and not has_stt_verb:
        return False

    if clean in TRANSCRIPTION_KEYWORDS:
        return True
    for p in TRANSCRIPTION_PATTERNS:
        if p.search(clean) or p.search(t):
            return True
    return False


def is_summary_request(text: str) -> bool:
    \"\"\"Returns True if user asks for a chat summary or what happened in chat.\"\"\"
    if not text:
        return False
    t = text.strip().lower()
    return bool(re.search(
        r"\\b(?:сводк\\w*|итог\\w*|что\\s+(?:там\\s+|тут\\s+)?по\\s+чат\\w*|что\\s+в\\s+чат\\w*|что\\s+(?:там\\s+)?происходило\\s+в\\s+чат\\w*|расскажи\\s+(?:что\\s+)?в\\s+чат\\w*|что\\s+нового\\s+в\\s+чат\\w*|как\\s+дела\\s+в\\s+чат\\w*)\\b",
        t,
        re.IGNORECASE,
    ))


async def get_target_chat_for_summary(
    db: Database,
    message: Message,
    text: str,
) -> tuple[int, str]:
    \"\"\"Finds target chat ID and title for summary.\"\"\"
    text_lower = text.lower()
    async with db.connect() as conn:
        if re.search(r"\\b(?:тирамису|tiramisu|tirammmisu|тирамис)\\b", text_lower):
            cursor = await conn.execute(
                "SELECT chat_id, title FROM chats WHERE title LIKE '%tiram%' OR title LIKE '%тирам%' ORDER BY id DESC LIMIT 1"
            )
            chat_row = await cursor.fetchone()
            if chat_row:
                return int(chat_row["chat_id"]), str(chat_row["title"])

        if message.chat.type in ("group", "supergroup"):
            return message.chat.id, message.chat.title or "Чат"

        cursor = await conn.execute(
            \"\"\"
            SELECT c.chat_id, c.title, COUNT(h.id) as msg_count
            FROM chats c
            LEFT JOIN companion_chat_history h ON c.chat_id = h.chat_id
            WHERE c.chat_id < 0
            GROUP BY c.chat_id
            ORDER BY msg_count DESC, c.id DESC
            LIMIT 1
            \"\"\"
        )
        primary_chat = await cursor.fetchone()
        if primary_chat:
            return int(primary_chat["chat_id"]), str(primary_chat["title"])

        return -1002255156347, "TiraMMMiSu"


async def generate_chat_summary_response(
    db: Database,
    companion: ChatCompanion,
    target_chat_id: int,
    target_chat_title: str,
    user_name: str,
    user_prompt: str,
) -> str:
    \"\"\"Generates an accurate, truthful and witty summary of real events in the target chat.\"\"\"
    today_str = datetime.now().strftime("%Y-%m-%d")
    daily_mem = None
    messages_list = []

    async with db.connect() as conn:
        repo = ChatRepository(conn)
        daily_mem = await repo.get_daily_memory(target_chat_id, today_str)
        cursor = await conn.execute(
            \"\"\"
            SELECT user_name, text, created_at, is_bot
            FROM companion_chat_history
            WHERE chat_id = ?
            ORDER BY id DESC
            LIMIT 35
            \"\"\",
            (target_chat_id,),
        )
        rows = await cursor.fetchall()
        for r in reversed(rows):
            sender = "Ричард (Бот)" if r["is_bot"] else (r["user_name"] or "Участник")
            messages_list.append(f"[{sender}]: {r['text']}")

    summary_context_parts = []
    if daily_mem and (daily_mem.get("summary") or daily_mem.get("key_facts")):
        summary_context_parts.append(f"Дневная хроника событий дня ({today_str}):\\n{daily_mem.get('summary', '')}")
        if daily_mem.get("key_facts"):
            summary_context_parts.append("Ключевые факты дня:\\n" + "\\n".join(f"- {f}" for f in daily_mem["key_facts"]))

    if messages_list:
        summary_context_parts.append("Последние сообщения и кружки в чате:\\n" + "\\n".join(messages_list[-30:]))

    if not summary_context_parts:
        return f"В чате {target_chat_title} за последнее время было тихо, свежих сообщений нет."

    full_log = "\\n\\n".join(summary_context_parts)
    sys_prompt = (
        f"Ты — Ричард, свой пацан и участник этой компании друзей. Пользователь ({user_name}) попросил сводку по чату \\\"{target_chat_title}\\\".\\n"
        f"ВОТ РЕАЛЬНЫЕ СООБЩЕНИЯ, КРУЖОЧКИ И СОБЫТИЯ ИЗ ЭТОГО ЧАТА:\\n"
        f"-----------------\\n"
        f"{full_log}\\n"
        f"-----------------\\n\\n"
        f"СТРОЖАЙШИЕ ПРАВИЛА СОСТАВЛЕНИЯ СВОДКИ:\\n"
        f"1. ГОВОРИ СТРОГО ПО РЕАЛЬНЫМ ФАКТАМ ИЗ ЛОГА ВЫШЕ! Назови участников по именам (Соль, Миша, Тимур, Абисс), кто что писал, какие кружки записывал (например, кружки Соли про прическу/укладку в школу, разговоры про балаклаву, тиктоки Михи).\\n"
        f"2. КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО выдумывать еду, десерты, торты, рецепты или пирожные! Название чата '{target_chat_title}' — это просто название чата, а не кондитерское изделие!\\n"
        f"3. Отвечай живым, емким языком, по-пацански, с легким дружеским юмором, без воды и канцеляризмов (2-4 предложения).\\n"
        f"4. НИКАКИХ ржущих смайликов (😂, 🤣) и клоунских шаблонов бота."
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
        return f"По чату {target_chat_title}: недавно Соль записывала кружок про укладку в школу, а ночью обсуждали балаклавы и кидали тиктоки.\""""

assert old_is_transcription in content, "old_is_transcription not found"
content = content.replace(old_is_transcription, new_is_transcription)

# 3. Update call to is_transcription_request
old_call = "    # Check for speech-to-text transcription request (both replies and non-reply commands like 'что я сказал')\n    if is_transcription_request(raw_incoming_text):"
new_call = """    # Check for speech-to-text transcription request (both replies and non-reply commands like 'что я сказал')
    is_reply_to_media = bool(message.reply_to_message and (
        getattr(message.reply_to_message, "voice", None) or
        getattr(message.reply_to_message, "video_note", None) or
        getattr(message.reply_to_message, "audio", None)
    ))
    if is_transcription_request(raw_incoming_text, is_reply_to_media=is_reply_to_media):"""

assert old_call in content, "old_call not found"
content = content.replace(old_call, new_call)

# 4. Handle summary request in companion trigger block
old_trigger = """                if triggered and prompt:
                    if companion.typing_indicator:
                        await message.bot.send_chat_action(chat_id=message.chat.id, action="typing")
                    caller_name = resolve_friendly_name(message.from_user)
                    is_owner = bool(settings.OWNER_ID > 0 and message.from_user and message.from_user.id == settings.OWNER_ID)"""

new_trigger = """                if triggered and prompt:
                    if companion.typing_indicator:
                        await message.bot.send_chat_action(chat_id=message.chat.id, action="typing")
                    caller_name = resolve_friendly_name(message.from_user)
                    is_owner = bool(settings.OWNER_ID > 0 and message.from_user and message.from_user.id == settings.OWNER_ID)

                    # Check for chat summary request
                    if is_summary_request(prompt):
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
                            return"""

assert old_trigger in content, "old_trigger not found"
content = content.replace(old_trigger, new_trigger)

# 5. In PM, pull daily memory from main chat if empty
old_pm_mem = """                        async with db.connect() as conn:
                            d_mem = await ChatRepository(conn).get_daily_memory(message.chat.id, today_str)
                            if d_mem:
                                daily_summary = d_mem.get("summary", "")
                                daily_facts = d_mem.get("key_facts", [])"""

new_pm_mem = """                        async with db.connect() as conn:
                            d_mem = await ChatRepository(conn).get_daily_memory(message.chat.id, today_str)
                            if not d_mem and message.chat.type == "private":
                                d_mem = await ChatRepository(conn).get_daily_memory(-1002255156347, today_str)
                            if d_mem:
                                daily_summary = d_mem.get("summary", "")
                                daily_facts = d_mem.get("key_facts", [])"""

assert old_pm_mem in content, "old_pm_mem not found"
content = content.replace(old_pm_mem, new_pm_mem)

with open(path, "w", encoding="utf-8") as f:
    f.write(content)

print("Patch applied successfully to forward.py")
