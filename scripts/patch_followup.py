def patch():
    path = r"c:\Users\sla_5\Programing\Projects\Tg Saver\bot\handlers\forward.py"
    with open(path, "r", encoding="utf-8") as f:
        c = f.read()

    target = """                    is_summary = is_summary_request(prompt)
                    follow_up_summary_re = re.compile(
                        r"^(?:ну|и\??|и\s+что\??|ну\s+что\??|ну\s+и\??|ну\s+так\s+что\??|ну\s+так\s+что|отвечай|давай|ну\s+пожалуйста|пожалуйста|расскажи|ну\s+скажи|ну\s+расскажи|да\s+ладно|че\s+там|что\s+там|ну\s+че|а\s+что\s+там|почему\??|почему\s+нет\??) ",
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
                            pass"""

    repl = """                    is_summary = is_summary_request(prompt)
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
                                    # Check previous user message (offset 1 because current user message was already saved at line 631)
                                    cursor = await conn.execute(
                                        "SELECT text FROM companion_chat_history WHERE chat_id = ? AND is_bot = 0 ORDER BY id DESC LIMIT 1 OFFSET 1",
                                        (message.chat.id,),
                                    )
                                    prev_row = await cursor.fetchone()
                                    if prev_row and is_summary_request(prev_row["text"]):
                                        is_summary = True
                        except Exception:
                            pass"""

    c_norm = c.replace("\r\n", "\n")
    target_norm = target.replace("\r\n", "\n")
    repl_norm = repl.replace("\r\n", "\n")

    if target_norm in c_norm:
        c_norm = c_norm.replace(target_norm, repl_norm, 1)
        with open(path, "w", encoding="utf-8") as f:
            f.write(c_norm)
        print("PATCHED")
    else:
        print("TARGET NOT FOUND")

if __name__ == "__main__":
    patch()
