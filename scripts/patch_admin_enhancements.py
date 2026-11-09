import re

# 1. Patch bot/handlers/forward.py to add admin-only check for summary request
forward_path = r"c:\Users\sla_5\Programing\Projects\Tg Saver\bot\handlers\forward.py"
with open(forward_path, "r", encoding="utf-8") as f:
    f_content = f.read()

old_summary_block = """                    # Check for chat summary request
                    if is_summary_request(prompt):
                        target_cid, target_title = await get_target_chat_for_summary(db, message, prompt)"""

new_summary_block = """                    # Check for chat summary request (strictly restricted to owner and admins)
                    if is_summary_request(prompt):
                        is_admin_user = is_owner
                        if not is_admin_user and message.from_user:
                            async with db.connect() as conn:
                                u = await UserRepository(conn).get_user(message.from_user.id)
                                if u and u.get("role") in ("owner", "admin"):
                                    is_admin_user = True

                        if not is_admin_user:
                            denial = "Сводка по чату и доступ к внутренней хронике открыты только для создателя и админов. Тебе сюда доступ закрыт."
                            await message.reply(denial)
                            return

                        target_cid, target_title = await get_target_chat_for_summary(db, message, prompt)"""

assert old_summary_block in f_content, "old_summary_block not found in forward.py"
f_content = f_content.replace(old_summary_block, new_summary_block)

with open(forward_path, "w", encoding="utf-8") as f:
    f.write(f_content)
print("forward.py patched successfully with admin check")

# 2. Patch bot/keyboards/inline.py to add daily memory button to admin_panel_kb and llm_settings_kb
inline_path = r"c:\Users\sla_5\Programing\Projects\Tg Saver\bot\keyboards\inline.py"
with open(inline_path, "r", encoding="utf-8") as f:
    i_content = f.read()

# Update admin_panel_kb
old_admin_row = """            [
                InlineKeyboardButton(text="🛡️ Модерация и чаты", callback_data="admin_moderation_chats"),
            ],"""

new_admin_row = """            [
                InlineKeyboardButton(text="🛡️ Модерация и чаты", callback_data="admin_moderation_chats"),
                InlineKeyboardButton(text="📜 Память и сводки", callback_data="admin_daily_memory"),
            ],"""

assert old_admin_row in i_content, "old_admin_row not found in inline.py"
i_content = i_content.replace(old_admin_row, new_admin_row)

# Update llm_settings_kb bottom rows
old_llm_rows = """            [
                InlineKeyboardButton(text=rand_text, callback_data="llm_select_random"),
                InlineKeyboardButton(text="🧹 Очистить всю память", callback_data="llm_clear_all_mem"),
            ],
            [
                InlineKeyboardButton(text="🔄 Обновить", callback_data="admin_llm_settings"),
                InlineKeyboardButton(text="⬅️ В админ-панель", callback_data="nav_admin"),
            ],"""

new_llm_rows = """            [
                InlineKeyboardButton(text=rand_text, callback_data="llm_select_random"),
                InlineKeyboardButton(text="🧹 Очистить всю память", callback_data="llm_clear_all_mem"),
            ],
            [
                InlineKeyboardButton(text="📜 Дневная память / Сводка", callback_data="admin_daily_memory"),
                InlineKeyboardButton(text="🔄 Обновить", callback_data="admin_llm_settings"),
            ],
            [
                InlineKeyboardButton(text="⬅️ В админ-панель", callback_data="nav_admin"),
            ],"""

assert old_llm_rows in i_content, "old_llm_rows not found in inline.py"
i_content = i_content.replace(old_llm_rows, new_llm_rows)

# Add daily_memory_kb definition at the end if not present
if "def daily_memory_kb" not in i_content:
    daily_memory_def = """

def daily_memory_kb(has_memory: bool = True) -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton(text="🔄 Пересобрать сводку дня", callback_data="daily_mem_regenerate"),
        ],
    ]
    if has_memory:
        buttons.append([
            InlineKeyboardButton(text="🗑️ Очистить память дня", callback_data="daily_mem_clear"),
        ])
    buttons.append([
        InlineKeyboardButton(text="⬅️ Назад в настройки ИИ", callback_data="admin_llm_settings"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)
"""
    i_content += daily_memory_def

with open(inline_path, "w", encoding="utf-8") as f:
    f.write(i_content)
print("inline.py patched successfully")
