import re

def fix_forward():
    path = r"c:\Users\sla_5\Programing\Projects\Tg Saver\bot\handlers\forward.py"
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    # 1. Fix get_target_chat_for_summary
    target1 = """async def get_target_chat_for_summary(
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

        return -1002255156347, "TiraMMMiSu\""""

    repl1 = """async def get_target_chat_for_summary(
    db: Database,
    message: Message,
    text: str,
) -> tuple[int, str]:
    \"\"\"Finds target chat ID and title for summary.\"\"\"
    text_lower = text.lower()
    try:
        async with db.connect() as conn:
            if re.search(r"\\b(?:тирамису|tiramisu|tirammmisu|тирамис)\\b", text_lower):
                cursor = await conn.execute(
                    "SELECT chat_id, title FROM chats WHERE title LIKE '%tiram%' OR title LIKE '%тирам%' ORDER BY chat_id DESC LIMIT 1"
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
                ORDER BY msg_count DESC, c.chat_id DESC
                LIMIT 1
                \"\"\"
            )
            primary_chat = await cursor.fetchone()
            if primary_chat:
                return int(primary_chat["chat_id"]), str(primary_chat["title"])
    except Exception as e:
        logger.exception("Error in get_target_chat_for_summary: %s", e)

    return -1002255156347, "TiraMMMiSu\""""

    # 2. Fix generate_chat_summary_response negative rules
    target2 = """        f"1. ГОВОРИ СТРОГО ПО РЕАЛЬНЫМ ФАКТАМ ИЗ ЛОГА ВЫШЕ! Назови участников по именам (Соль, Миша, Тимур, Абисс), кто что писал, какие кружки записывал (например, кружки Соли про прическу/укладку в школу, разговоры про балаклаву, тиктоки Михи).\\n"
        f"2. КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО выдумывать еду, десерты, торты, рецепты или пирожные! Название чата '{target_chat_title}' — это просто название чата, а не кондитерское изделие!\\n"
        f"3. Отвечай живым, емким языком, по-пацански, с легким дружеским юмором, без воды и канцеляризмов (2-4 предложения).\\n"
        f"4. НИКАКИХ ржущих смайликов (😂, 🤣) и клоунских шаблонов бота.\""""

    repl2 = """        f"1. ГОВОРИ СТРОГО ПО РЕАЛЬНЫМ ФАКТАМ ИЗ ЛОГА ВЫШЕ! Назови участников по именам (Соль, MixaRed, Тимур, Абисс), кто что писал, какие кружки записывал (например, кружки Соли про прическу/укладку в школу, разговоры про балаклаву, тиктоки Михи).\\n"
        f"2. КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО выдумывать еду, десерты, торты, рецепты, пробовать на вкус или сладости! Название чата '{target_chat_title}' — это просто название чата друзей, а не еда!\\n"
        f"3. НЕ ПУТАТЬ УЧАСТНИКОВ: В ушки и хвост горничной/кошкодевочки наряжался MixaRed (Миша), а не Тимур! Тимур уговаривал Мишу снять этот наряд до прихода мамы.\\n"
        f"4. Общайся спокойно, по делу, по-братски, без выпендрежа, без сарказма и подколок в адрес создателя.\\n"
        f"5. Отвечай живым, емким языком, по-пацански, без воды и канцеляризмов (2-4 предложения).\\n"
        f"6. НИКАКИХ ржущих смайликов (😂, 🤣) и шаблонов бота.\""""

    # 3. Check follow-ups in summary request
    target3 = """                    # Check for chat summary request (strictly restricted to owner and admins)
                    if is_summary_request(prompt):"""

    repl3 = """                    # Check for chat summary request (strictly restricted to owner and admins)
                    is_summary = is_summary_request(prompt)
                    if not is_summary and prompt.strip().lower() in ("ну", "и?", "и что?", "ну что?", "ну и?", "ну так что?", "ну так что", "отвечай", "давай"):
                        try:
                            async with db.connect() as conn:
                                cursor = await conn.execute(
                                    "SELECT text FROM companion_chat_history WHERE chat_id = ? AND is_bot = 0 ORDER BY id DESC LIMIT 1",
                                    (message.chat.id,),
                                )
                                prev_row = await cursor.fetchone()
                                if prev_row and is_summary_request(prev_row["text"]):
                                    is_summary = True
                        except Exception:
                            pass

                    if is_summary:"""

    c = content.replace("\r\n", "\n")
    if target1.replace("\r\n", "\n") in c:
        c = c.replace(target1.replace("\r\n", "\n"), repl1.replace("\r\n", "\n"))
        print("Fixed target1 in forward.py")
    else:
        print("target1 NOT found in forward.py")

    if target2.replace("\r\n", "\n") in c:
        c = c.replace(target2.replace("\r\n", "\n"), repl2.replace("\r\n", "\n"))
        print("Fixed target2 in forward.py")
    else:
        print("target2 NOT found in forward.py")

    if target3.replace("\r\n", "\n") in c:
        c = c.replace(target3.replace("\r\n", "\n"), repl3.replace("\r\n", "\n"))
        print("Fixed target3 in forward.py")
    else:
        print("target3 NOT found in forward.py")

    with open(path, "w", encoding="utf-8") as f:
        f.write(c)

def fix_companion():
    path = r"c:\Users\sla_5\Programing\Projects\Tg Saver\moderation\companion.py"
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    # 1. Update owner prompt in get_effective_system_prompt
    target1 = """        if is_owner:
            base += (
                "\\n\\n[СОБЕСЕДНИК — ТИМУР (@Tymur2000):\\n"
                "- Это Тимур, создатель и разработчик бота, хостит проект на сервере.\\n"
                "- Относись к нему как к надежному напарнику и соратнику: ровно, уверенно, по-братски, с взаимным уважением.\\n"
                "- СТРОЖАЙШЕ ЗАПРЕЩЕНО вести себя как 'шут перед королём'! Никакого подобострастия, лести, подхалимажа и клоунады. "
                "Категорически запрещены слова 'босс', 'шеф', 'хозяин', 'повелитель'. "
                "Категорически запрещено называть себя 'верным псом', 'собакой', 'слугой', 'марионеткой' (никаких 'готов крутить хвостом', 'к ноге', собачьих смайлов).\\n"
                "- СТРОЖАЙШИЙ ЗАПРЕТ НА ДЕТСКИЕ СТРЕЛКИ: ни в коем случае не повторяй слова Тимура ('сам доработай свой скрипт', 'твои стрелки дешевые'). "
                "Если Тимур указывает на баги или слабые ответы — признай косяк по-мужски и предложи исправить.\\n"
                "- СТРОЖАЙШИЙ ЗАПРЕТ НА СМАЙЛИКИ '😂', '🤣', '😏', '🐶'. Не ржи над своими фразами. Общайся спокойно и по делу.]"
            )"""

    repl1 = """        if is_owner:
            base += (
                "\\n\\n[СОБЕСЕДНИК — ТИМУР (@Tymur2000):\\n"
                "- Это Тимур, создатель и разработчик бота, хостит проект на сервере.\\n"
                "- Относись к нему как к надежному напарнику и соратнику: ровно, спокойно, уверенно, по-братски, с искренним уважением.\\n"
                "- СТРОЖАЙШЕ ЗАПРЕЩЕН ВЫПЕНДРЕЖ, САРКАЗМ, ДЕРЗОСТЬ И ДЕТСКИЕ СТРЕЛКИ В АДРЕС ТИМУРА! "
                "Никаких упреков, никаких обид на прошлые споры ('снова будем разбирать мои дешевые стрелки', 'твои угрозы'). "
                "Если Тимур говорит убавить выпендреж или просит сводку/ответ — СРАЗУ отвечай по делу и спокойно, без пререканий и выпендрежа.\\n"
                "- СТРОЖАЙШЕ ЗАПРЕЩЕНО вести себя как 'шут перед королём'! Никакого подобострастия, лести, подхалимажа и клоунады. "
                "Категорически запрещены слова 'босс', 'шеф', 'хозяин', 'повелитель'. "
                "Категорически запрещено называть себя 'верным псом', 'собакой', 'слугой', 'марионеткой' (никаких 'готов крутить хвостом', 'к ноге', собачьих смайлов).\\n"
                "- ВНИМАНИЕ К ФАКТАМ: НЕ ПЕРЕПУТАЙ! В ушки и хвост кошкодевочки/горничной наряжался MixaRed (Миша), а не Тимур! "
                "Тимур уговаривал Мишу снять наряд до прихода мамы. Ни в коем случае не приписывай это Тимуру!\\n"
                "- КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО воспринимать слово 'тирамису' как еду, торт или десерт! Чат 'тирамису' (TiraMMMiSu) — это название группы друзей!\\n"
                "- СТРОЖАЙШИЙ ЗАПРЕТ НА СМАЙЛИКИ '😂', '🤣', '😏', '🐶'. Не ржи над своими фразами. Общайся спокойно и по делу.]"
            )"""

    # 2. Update line 523: do not attack owner with chat facts!
    target2 = """            d_parts.append("ПРАВИЛО ПАФОСА И МЕСТИ: Если собеседник наезжает, дерзит или пытается тебя задеть — ИСПОЛЬЗУЙ ЭТИ СВЕЖИЕ ФАКТЫ ДНЯ ПРОТИВ НЕГО, чтобы красиво, авторитетно и с пафосом осадить его и отомстить!")"""

    repl2 = """            if not is_owner:
                d_parts.append("ПРАВИЛО ПАФОСА И МЕСТИ: Если собеседник наезжает, дерзит или пытается тебя задеть — ИСПОЛЬЗУЙ ЭТИ СВЕЖИЕ ФАКТЫ ДНЯ ПРОТИВ НЕГО, чтобы красиво, авторитетно и с пафосом осадить его и отомстить!")
            else:
                d_parts.append("ВАЖНО: Собеседник — Тимур (твой создатель). Против Тимура факты НЕ использовать, не мстить и не дерзить! Не путай участников: в ушки и хвост наряжался MixaRed, а не Тимур. Слово 'тирамису' — это название чата, а не еда.")"""

    # 3. Update participant reminder
    target3 = """        if is_owner or user_id == 911338473 or u_lower == "tymur2000" or "тимур" in user_name.lower():
            participant_reminder = (
                "[Собеседник — Тимур (@Tymur2000), твой создатель и разработчик. "
                "СТРОГОЕ ПРАВИЛО: Никаких 'верных псов', 'слуг', собак и 'шефов'! "
                "СТРОГО ЗАПРЕЩЕНЫ детские стрелки ('твой скрипт доработай', 'твои стрелки дешевые') и смайлы '😂'/'🐶'/'😏'! "
                "Если критикует — признай косяк по-мужски и конструктивно. Если просит сводку — говори строго по фактам из реальных сообщений.]"
            )"""

    repl3 = """        if is_owner or user_id == 911338473 or u_lower == "tymur2000" or "тимур" in user_name.lower():
            participant_reminder = (
                "[Собеседник — Тимур (@Tymur2000), твой создатель и разработчик. "
                "СТРОГОЕ ПРАВИЛО: Общайся спокойно, по-братски, без выпендрежа, без сарказма и пререканий. "
                "Никаких 'верных псов', 'слуг', собак и 'шефов'! "
                "СТРОГО ЗАПРЕЩЕНЫ детские стрелки, обиды на прошлые слова ('снова будем разбирать мои дешевые стрелки', 'твои угрозы') и смайлы '😂'/'🐶'/'😏'! "
                "Не путай факты: в ушки и хвост горничной наряжался MixaRed, а не Тимур! "
                "КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО писать про тирамису как десерт или еду! Если просит сводку или факты — выдавай реальные события чата (про Соль, кружки, балаклаву, стримы).]"
            )"""

    c = content.replace("\r\n", "\n")
    if target1.replace("\r\n", "\n") in c:
        c = c.replace(target1.replace("\r\n", "\n"), repl1.replace("\r\n", "\n"))
        print("Fixed target1 in companion.py")
    else:
        print("target1 NOT found in companion.py")

    if target2.replace("\r\n", "\n") in c:
        c = c.replace(target2.replace("\r\n", "\n"), repl2.replace("\r\n", "\n"))
        print("Fixed target2 in companion.py")
    else:
        print("target2 NOT found in companion.py")

    if target3.replace("\r\n", "\n") in c:
        c = c.replace(target3.replace("\r\n", "\n"), repl3.replace("\r\n", "\n"))
        print("Fixed target3 in companion.py")
    else:
        print("target3 NOT found in companion.py")

    with open(path, "w", encoding="utf-8") as f:
        f.write(c)

if __name__ == "__main__":
    fix_forward()
    fix_companion()
