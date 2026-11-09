def run():
    path = r"c:\Users\sla_5\Programing\Projects\Tg Saver\bot\handlers\forward.py"
    with open(path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    # Find the start index
    start_idx = -1
    end_idx = -1
    for i, line in enumerate(lines):
        if "is_summary = is_summary_request(prompt)" in line:
            start_idx = i
            break

    for i in range(start_idx, len(lines)):
        if "if is_summary:" in lines[i]:
            end_idx = i
            break

    print(f"Replacing lines {start_idx} to {end_idx}")

    replacement_block = [
        "                    is_summary = is_summary_request(prompt)\n",
        "                    follow_up_summary_re = re.compile(\n",
        r'                        r"^(?:ну|и\??|и\s+что\??|ну\s+что\??|ну\s+и\??|ну\s+так\s+что\??|ну\s+так\s+что|отвечай|давай|ну\s+пожалуйста|пожалуйста|расскажи|ну\s+скажи|ну\s+расскажи|да\s+ладно|че\s+там|что\s+там|ну\s+че|а\s+что\s+там|почему\??|почему\s+нет\??)",' + "\n",
        "                        re.IGNORECASE,\n",
        "                    )\n",
        "                    if not is_summary and follow_up_summary_re.search(prompt.strip()):\n",
        "                        try:\n",
        "                            async with db.connect() as conn:\n",
        "                                # Check if previous bot message was a denial\n",
        "                                cursor_bot = await conn.execute(\n",
        '                                    "SELECT text FROM companion_chat_history WHERE chat_id = ? AND is_bot = 1 ORDER BY id DESC LIMIT 1",\n',
        "                                    (message.chat.id,),\n",
        "                                )\n",
        "                                last_bot_row = await cursor_bot.fetchone()\n",
        '                                if last_bot_row and "только для создателя и админов" in last_bot_row["text"]:\n',
        "                                    is_summary = True\n",
        "                                else:\n",
        "                                    # Check previous user message (offset 1 because current user message was saved at line 631)\n",
        "                                    cursor = await conn.execute(\n",
        '                                        "SELECT text FROM companion_chat_history WHERE chat_id = ? AND is_bot = 0 ORDER BY id DESC LIMIT 1 OFFSET 1",\n',
        "                                        (message.chat.id,),\n",
        "                                    )\n",
        "                                    prev_row = await cursor.fetchone()\n",
        '                                    if prev_row and is_summary_request(prev_row["text"]):\n',
        "                                        is_summary = True\n",
        "                        except Exception:\n",
        "                            pass\n",
        "\n",
    ]

    new_lines = lines[:start_idx] + replacement_block + lines[end_idx:]
    with open(path, "w", encoding="utf-8") as f:
        f.writelines(new_lines)
    print("SLICED REPLACEMENT SUCCESS")

if __name__ == "__main__":
    run()
