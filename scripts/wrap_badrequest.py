path = r'C:\Users\sla_5\Programing\Projects\Tg Saver\bot\handlers\admin.py'
with open(path, 'r', encoding='utf-8') as f:
    text = f.read()

old1 = '''    await callback.message.edit_text(text, reply_markup=llm_persona_select_kb(current_persona=current_persona), parse_mode="HTML")
    await callback.answer()'''
new1 = '''    try:
        await callback.message.edit_text(text, reply_markup=llm_persona_select_kb(current_persona=current_persona), parse_mode="HTML")
    except TelegramBadRequest:
        pass
    await callback.answer()'''

old2 = '''    await callback.message.edit_text(text, reply_markup=llm_settings_kb(is_on, conf), parse_mode="HTML")
    await callback.answer(f"✅ Характер: {p_label}")'''
new2 = '''    try:
        await callback.message.edit_text(text, reply_markup=llm_settings_kb(is_on, conf), parse_mode="HTML")
    except TelegramBadRequest:
        pass
    await callback.answer(f"✅ Характер: {p_label}")'''

if old1 not in text:
    print('old1 not found')
if old2 not in text:
    print('old2 not found')

if old1 in text and old2 in text:
    text = text.replace(old1, new1).replace(old2, new2)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(text)
    print('Updated successfully!')
