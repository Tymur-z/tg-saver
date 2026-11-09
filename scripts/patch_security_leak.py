import re

def patch_forward():
    path = r"c:\Users\sla_5\Programing\Projects\Tg Saver\bot\handlers\forward.py"
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    # 1. Update upfront is_admin_user computation and follow-up regex + denial logging
    target1 = """                    caller_name = resolve_friendly_name(message.from_user)
                    is_owner = bool(settings.OWNER_ID > 0 and message.from_user and message.from_user.id == settings.OWNER_ID)

                    # Check for chat summary request (strictly restricted to owner and admins)
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

                    if is_summary:
                        is_admin_user = is_owner
                        if not is_admin_user and message.from_user:
                            async with db.connect() as conn:
                                u = await UserRepository(conn).get_user(message.from_user.id)
                                if u and u.get("role") in ("owner", "admin"):
                                    is_admin_user = True

                        if not is_admin_user:
                            denial = "Сводка по чату и доступ к внутренней хронике открыты только для создателя и админов. Тебе сюда доступ закрыт."
                            await message.reply(denial)
                            return"""

    repl1 = """                    caller_name = resolve_friendly_name(message.from_user)
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
                        r"^(?:ну|и\??|и\s+что\??|ну\s+что\??|ну\s+и\??|ну\s+так\s+что\??|ну\s+так\s+что|отвечай|давай|ну\s+пожалуйста|пожалуйста|расскажи|ну\s+скажи|ну\s+расскажи|да\s+ладно|че\s+там|что\s+там|ну\s+че|а\s+что\s+там|почему\??|почему\s+нет\??)\b",
                        re.IGNORECASE,
                    )
                    if not is_summary and follow_up_summary_re.search(prompt.strip()):
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
                            return"""

    # 2. Update line 930: NEVER load group memory in PM for non-admin!
    target2 = """                        async with db.connect() as conn:
                            d_mem = await ChatRepository(conn).get_daily_memory(message.chat.id, today_str)
                            if not d_mem and message.chat.type == "private":
                                d_mem = await ChatRepository(conn).get_daily_memory(-1002255156347, today_str)
                            if d_mem:
                                daily_summary = d_mem.get("summary", "")
                                daily_facts = d_mem.get("key_facts", [])"""

    repl2 = """                        async with db.connect() as conn:
                            d_mem = await ChatRepository(conn).get_daily_memory(message.chat.id, today_str)
                            # CRITICAL SECURITY: in PM, only load group memory if user is verified OWNER or ADMIN!
                            if not d_mem and message.chat.type == "private" and is_admin_user:
                                d_mem = await ChatRepository(conn).get_daily_memory(-1002255156347, today_str)
                            if d_mem:
                                daily_summary = d_mem.get("summary", "")
                                daily_facts = d_mem.get("key_facts", [])"""

    # 3. Pass is_admin and is_private to companion.generate_reply
    target3 = """                    reply_text = await companion.generate_reply(
                        chat_id=message.chat.id,
                        user_name=caller_name,
                        user_prompt=prompt,
                        is_owner=is_owner,
                        extra_context=extra_context,
                        user_id=message.from_user.id if message.from_user else None,
                        username=message.from_user.username if message.from_user else None,
                        daily_memory_summary=daily_summary,
                        daily_memory_facts=daily_facts,
                    )"""

    repl3 = """                    reply_text = await companion.generate_reply(
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
                    )"""

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

def patch_companion():
    path = r"c:\Users\sla_5\Programing\Projects\Tg Saver\moderation\companion.py"
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    # 1. Update get_effective_system_prompt signature and PM mode
    target1 = """    def get_effective_system_prompt(self, is_owner: bool = False) -> str:
        if self.persona == "custom" and self.custom_prompt:
            base = self.custom_prompt
        else:
            base = PERSONA_PRESETS.get(self.persona, self.system_prompt)
        base += COMMON_CHAT_RULES
        if is_owner:
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
            )
        return base"""

    repl1 = """    def get_effective_system_prompt(self, is_owner: bool = False, is_admin: bool = False, is_private: bool = False) -> str:
        if self.persona == "custom" and self.custom_prompt:
            base = self.custom_prompt
        else:
            base = PERSONA_PRESETS.get(self.persona, self.system_prompt)
        base += COMMON_CHAT_RULES
        if is_owner:
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
            )
        elif is_private and not is_admin:
            base += (
                "\\n\\n[РЕЖИМ ЛИЧНЫХ СООБЩЕНИЙ С ОБЫЧНЫМ ПОЛЬЗОВАТЕЛЕМ (НЕ АДМИН):\\n"
                "- Собеседник НЕ является создателем или администратором бота (даже если у него имя или ник 'Тимур').\\n"
                "- Тебе КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО раскрывать события, переписки, участников или сводки закрытой группы 'TiraMMMiSu'!\\n"
                "- Если пользователь просит сводку, выведывает что в чате, умоляет ('ну пожалуйста') или спрашивает, что там было — ТВЁРДО ОТКАЗЫВАЙ: "
                "'Сводка и хроника чата закрыты. Доступ только у создателя и админов.']"
            )
        return base"""

    # 2. Update generate_reply signature and call to get_effective_system_prompt
    target2 = """    async def generate_reply(
        self,
        chat_id: int,
        user_name: str,
        user_prompt: str,
        is_owner: bool = False,
        extra_context: str = "",
        user_id: Optional[int] = None,
        username: Optional[str] = None,
        daily_memory_summary: str = "",
        daily_memory_facts: Optional[List[str]] = None,
    ) -> Optional[str]:
        if not self.llm_client or not self.llm_client.api_key:
            logger.debug("ChatCompanion: LLMClient is not configured or missing API key.")
            return None

        context_str = self.context_buffer.format_context(chat_id, limit=self.context_limit)
        effective_prompt = self.get_effective_system_prompt(is_owner=is_owner)"""

    repl2 = """    async def generate_reply(
        self,
        chat_id: int,
        user_name: str,
        user_prompt: str,
        is_owner: bool = False,
        is_admin: bool = False,
        is_private: bool = False,
        extra_context: str = "",
        user_id: Optional[int] = None,
        username: Optional[str] = None,
        daily_memory_summary: str = "",
        daily_memory_facts: Optional[List[str]] = None,
    ) -> Optional[str]:
        if not self.llm_client or not self.llm_client.api_key:
            logger.debug("ChatCompanion: LLMClient is not configured or missing API key.")
            return None

        context_str = self.context_buffer.format_context(chat_id, limit=self.context_limit)
        effective_prompt = self.get_effective_system_prompt(is_owner=is_owner, is_admin=is_admin, is_private=is_private)"""

    # 3. Fix participant_reminder: strictly check user_id == 911338473 or is_owner!
    target3 = """        # Add participant-specific micro-priming based on dossier
        participant_reminder = ""
        u_lower = (username or "").lower()
        if is_owner or user_id == 911338473 or u_lower == "tymur2000" or "тимур" in user_name.lower():
            participant_reminder = (
                "[Собеседник — Тимур (@Tymur2000), твой создатель и разработчик. "
                "СТРОГОЕ ПРАВИЛО: Общайся спокойно, по-братски, без выпендрежа, без сарказма и пререканий. "
                "Никаких 'верных псов', 'слуг', собак и 'шефов'! "
                "СТРОГО ЗАПРЕЩЕНЫ детские стрелки, обиды на прошлые слова ('снова будем разбирать мои дешевые стрелки', 'твои угрозы') и смайлы '😂'/'🐶'/'😏'! "
                "Не путай факты: в ушки и хвост горничной наряжался MixaRed, а не Тимур! "
                "КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО писать про тирамису как десерт или еду! Если просит сводку или факты — выдавай реальные события чата (про Соль, кружки, балаклаву, стримы).]"
            )"""

    repl3 = """        # Add participant-specific micro-priming based on dossier
        participant_reminder = ""
        u_lower = (username or "").lower()
        # STRICT SECURITY: Identify as Creator/Developer ONLY if user_id == OWNER_ID (911338473) or is_owner is True!
        # NEVER match by first name 'Тимур' or arbitrary substring!
        if is_owner or (user_id is not None and user_id == 911338473):
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
    patch_forward()
    patch_companion()
