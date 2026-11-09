def run():
    path = r"c:\Users\sla_5\Programing\Projects\Tg Saver\tests\test_companion.py"
    with open(path, "r", encoding="utf-8") as f:
        c = f.read()

    new_test = """

@pytest.mark.asyncio
async def test_non_admin_pm_summary_and_begging_denial(test_db: Database) -> None:
    from bot.handlers.forward import handle_incoming_message
    from config.settings import Settings
    from database.repositories.user_repo import UserRepository

    settings = Settings(
        BOT_TOKEN="123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11",
        OWNER_ID=911338473,
    )
    mock_engine = MagicMock()
    mock_engine.process_incoming_message = AsyncMock()

    mock_profiler = MagicMock()
    mock_profiler.process_message = AsyncMock()
    mock_llm = MagicMock()
    mock_llm.api_key = "dummy"
    mock_llm.chat_completion = AsyncMock(return_value="Обычный ответ")
    companion = ChatCompanion(llm_client=mock_llm)
    companion._bot_user = MagicMock(id=7761395820, username="RichardHelperBot")

    # Second account with name 'Тимур', but user_id 6205547383 (role: user)
    second_user_id = 6205547383
    async with test_db.connect() as conn:
        u_repo = UserRepository(conn)
        await u_repo.upsert_user(user_id=second_user_id, username="Tymur_zav", role="user", is_authorized=True)

    # 1. Ask for summary in PM
    msg1 = make_mock_message(
        chat_id=second_user_id,
        chat_type="private",
        text="ты давай, поменьше выпендрежа, и сводку по тирамису давай",
        from_user_id=second_user_id,
        from_username="Тимур",
    )
    msg1.reply = AsyncMock()
    msg1.bot = MagicMock()
    msg1.bot.send_chat_action = AsyncMock()

    await handle_incoming_message(
        message=msg1,
        forward_engine=mock_engine,
        style_profiler=mock_profiler,
        settings=settings,
        db=test_db,
        companion=companion,
    )
    msg1.reply.assert_awaited_once()
    assert "только для создателя и админов" in msg1.reply.call_args[0][0]

    # 2. Beg for summary 'Ну пожалуйста' in PM
    msg2 = make_mock_message(
        chat_id=second_user_id,
        chat_type="private",
        text="Ну пожалуйста",
        from_user_id=second_user_id,
        from_username="Тимур",
    )
    msg2.reply = AsyncMock()
    msg2.bot = MagicMock()
    msg2.bot.send_chat_action = AsyncMock()

    await handle_incoming_message(
        message=msg2,
        forward_engine=mock_engine,
        style_profiler=mock_profiler,
        settings=settings,
        db=test_db,
        companion=companion,
    )
    # Must ALSO be denied, not leak summary!
    msg2.reply.assert_awaited_once()
    assert "только для создателя и админов" in msg2.reply.call_args[0][0]
"""

    if "test_non_admin_pm_summary_and_begging_denial" not in c:
        with open(path, "a", encoding="utf-8") as f:
            f.write(new_test)
        print("TEST ADDED")
    else:
        print("TEST ALREADY EXISTS")

if __name__ == "__main__":
    run()
