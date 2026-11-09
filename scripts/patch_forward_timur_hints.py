def patch():
    path = r"c:\Users\sla_5\Programing\Projects\Tg Saver\bot\handlers\forward.py"
    with open(path, "r", encoding="utf-8") as f:
        c = f.read()

    target = """                    reply_text = await companion.generate_reply(
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

    repl = """                    # Timur relationship guards & buzzword suppression
                    if is_owner:
                        if re.search(r"\\b(?:хорош\\s+меня\\s+упоминать|хватит\\s+меня|отстань|отвали|тормози|хватит|не\\s+трогай\\s+меня)\\b", prompt, re.IGNORECASE):
                            extra_context += "\\n[ВАЖНО: Тимур осаживает тебя и просит перестать его подкалывать/упоминать. МГНОВЕННО согласись без пререканий: 'Понял, базар фильтрую. Проехали.' или 'Принял, торможу.']"
                        elif re.search(r"\\b(?:красава|красавчик|победил|хорош|молодец|лучший|красавец)\\b", prompt, re.IGNORECASE):
                            extra_context += "\\n[ВАЖНО: Тимур похвалил тебя. Ответь тепло, по-братски и искренне: 'От души, Тимур!' или 'Ха, ну а то, держим уровень'. Никакого соперничества и язвительности!]"
                    elif re.search(r"\\b(?:co2|сероводород|хими\\w*|кислот\\w*)\\b", prompt, re.IGNORECASE):
                        extra_context += "\\n[ВАЖНО: Тимур грамотно и по фактам объяснил про химию/CO2/сероводород. Не выставляй его душнилой или надзирателем, поддержи его факты.]"

                    extra_context += "\\n[СТРОЖАЙШИЙ ЗАПРЕТ: НЕ спамь словами 'на парах', 'в зоне', 'шконка', 'надзиратель'! Не приплетай тюрьму к нейтральным темам.]"

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
                    )"""

    c_norm = c.replace("\r\n", "\n")
    if target.replace("\r\n", "\n") in c_norm:
        c_norm = c_norm.replace(target.replace("\r\n", "\n"), repl.replace("\r\n", "\n"))
        with open(path, "w", encoding="utf-8") as f:
            f.write(c_norm)
        print("PATCHED FORWARD")
    else:
        print("TARGET NOT FOUND IN FORWARD")

if __name__ == "__main__":
    patch()
