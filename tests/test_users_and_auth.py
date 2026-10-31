import pytest
from database.connection import Database
from database.repositories.user_repo import UserRepository
from database.repositories.route_repo import RouteRepository


@pytest.mark.asyncio
async def test_user_repository_crud(test_db: Database):
    async with test_db.connect() as conn:
        repo = UserRepository(conn)

        user = await repo.upsert_user(
            user_id=12345,
            username="test_guest",
            first_name="Guest",
            role="guest",
            is_authorized=False,
        )
        assert user["user_id"] == 12345
        assert user["role"] == "guest"
        assert await repo.is_user_authorized(12345) is False
        assert await repo.is_user_blocked(12345) is False

        await repo.set_authorized(12345, True)
        assert await repo.is_user_authorized(12345) is True

        await repo.set_role(12345, "admin")
        u = await repo.get_user(12345)
        assert u["role"] == "admin"

        await repo.set_blocked(12345, True)
        assert await repo.is_user_blocked(12345) is True


@pytest.mark.asyncio
async def test_access_password_management(test_db: Database):
    async with test_db.connect() as conn:
        repo = UserRepository(conn)

        pw = await repo.get_access_password("changeme")
        assert pw == "changeme"

        await repo.set_access_password("secret_pass_2026")
        new_pw = await repo.get_access_password()
        assert new_pw == "secret_pass_2026"

        assert await repo.is_password_required(True) is True
        await repo.set_password_required(False)
        assert await repo.is_password_required() is False


def test_password_candidate_matching():
    from bot.middlewares.auth import check_password_match

    pw = "changeme"
    assert check_password_match("changeme", pw) is True
    assert check_password_match(" changeme ", pw) is True
    assert check_password_match("/start changeme", pw) is True
    assert check_password_match("/start=changeme", pw) is True
    assert check_password_match("/password changeme", pw) is True
    assert check_password_match("/start", pw) is False
    assert check_password_match("wrong_password", pw) is False
    assert check_password_match("/start wrong", pw) is False


@pytest.mark.asyncio
async def test_user_route_isolation(test_db: Database):
    async with test_db.connect() as conn:
        route_repo = RouteRepository(conn)

        route_a = await route_repo.create_route(
            name="Route User 1",
            source_chat_id=1001,
            destination_chat_id=1002,
            created_by_user_id=111,
        )

        route_b = await route_repo.create_route(
            name="Route User 2",
            source_chat_id=2001,
            destination_chat_id=2002,
            created_by_user_id=222,
        )

        user1_routes = await route_repo.list_routes(user_id=111)
        assert len(user1_routes) == 1
        assert user1_routes[0]["id"] == route_a["id"]

        user2_routes = await route_repo.list_routes(user_id=222)
        assert len(user2_routes) == 1
        assert user2_routes[0]["id"] == route_b["id"]

        all_routes = await route_repo.list_routes(user_id=None)
        assert len(all_routes) == 2


@pytest.mark.asyncio
async def test_subadmin_role_and_ui_isolation(test_db: Database):
    from bot.keyboards.inline import admin_panel_kb, llm_settings_kb, user_card_kb

    async with test_db.connect() as conn:
        repo = UserRepository(conn)
        user = await repo.upsert_user(user_id=777, username="sub_admin_user", role="user")
        assert user["role"] == "user"

        await repo.set_role(777, "subadmin")
        u = await repo.get_user(777)
        assert u["role"] == "subadmin"

    # 1. Admin panel isolation
    kb_sub = admin_panel_kb(is_subadmin=True)
    sub_callbacks = [btn.callback_data for row in kb_sub.inline_keyboard for btn in row]
    assert "admin_hidden_routes" not in sub_callbacks
    assert "admin_password" not in sub_callbacks
    assert "admin_moderation_chats" in sub_callbacks
    assert "admin_llm_settings" in sub_callbacks

    # 2. LLM settings isolation (hide API key and Base URL)
    llm_kb_sub = llm_settings_kb(is_enabled=True, conf={}, is_subadmin=True)
    sub_llm_cbs = [btn.callback_data for row in llm_kb_sub.inline_keyboard for btn in row]
    assert "llm_set_key" not in sub_llm_cbs
    assert "llm_select_url" not in sub_llm_cbs
    assert "llm_select_model" in sub_llm_cbs
    assert "llm_select_persona" in sub_llm_cbs

    llm_kb_full = llm_settings_kb(is_enabled=True, conf={}, is_subadmin=False)
    full_llm_cbs = [btn.callback_data for row in llm_kb_full.inline_keyboard for btn in row]
    assert "llm_set_key" in full_llm_cbs
    assert "llm_select_url" in full_llm_cbs

    # 3. User card protection (subadmin cannot block admins or change roles)
    card_sub_viewing_admin = user_card_kb({"user_id": 999, "role": "admin"}, is_subadmin=True)
    sub_view_cbs = [btn.callback_data for row in card_sub_viewing_admin.inline_keyboard for btn in row]
    assert "user_block:999" not in sub_view_cbs
    assert "user_reset_auth:999" not in sub_view_cbs
    assert "noop" in sub_view_cbs

    card_full_viewing_user = user_card_kb({"user_id": 555, "role": "user"}, is_subadmin=False)
    full_view_cbs = [btn.callback_data for row in card_full_viewing_user.inline_keyboard for btn in row]
    assert "user_role:555:subadmin" in full_view_cbs
    assert "user_role:555:admin" in full_view_cbs
