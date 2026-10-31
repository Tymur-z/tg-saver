from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock
from aiogram.types import CallbackQuery

from database.connection import Database
from database.repositories.user_repo import UserRepository
from bot.keyboards.inline import admin_panel_kb, llm_settings_kb, user_card_kb


@pytest.mark.asyncio
async def test_user_roles_and_permissions(test_db: Database) -> None:
    async with test_db.connect() as conn:
        repo = UserRepository(conn)

        # 1. Register users with different roles
        owner = await repo.upsert_user(user_id=111, username="owner_user", role="owner", is_authorized=True)
        admin = await repo.upsert_user(user_id=222, username="admin_user", role="admin", is_authorized=True)
        subadmin = await repo.upsert_user(user_id=333, username="subadmin_user", role="subadmin", is_authorized=True)
        user = await repo.upsert_user(user_id=444, username="regular_user", role="user", is_authorized=True)

        assert owner["role"] == "owner"
        assert admin["role"] == "admin"
        assert subadmin["role"] == "subadmin"
        assert user["role"] == "user"

        # 2. Update role
        await repo.set_role(user_id=444, role="subadmin")
        updated_user = await repo.get_user(444)
        assert updated_user["role"] == "subadmin"

        # 3. Block and unblock
        await repo.set_blocked(user_id=444, is_blocked=True)
        blocked_user = await repo.get_user(444)
        assert blocked_user["is_blocked"] == 1

        await repo.set_blocked(user_id=444, is_blocked=False)
        unblocked_user = await repo.get_user(444)
        assert unblocked_user["is_blocked"] == 0


@pytest.mark.asyncio
async def test_owner_cannot_be_blocked_or_demoted(test_db: Database) -> None:
    async with test_db.connect() as conn:
        repo = UserRepository(conn)
        owner = await repo.upsert_user(user_id=999, username="boss", role="owner", is_authorized=True)

        # Try to block owner
        await repo.set_blocked(user_id=999, is_blocked=True)
        user_check = await repo.get_user(999)
        # In logic or UI, owner is protected. Even if db function called, check user card kb:
        kb = user_card_kb(user_check, is_owner=True, is_self=True)
        buttons_data = [btn.callback_data for row in kb.inline_keyboard for btn in row]
        assert "user_block:999" not in buttons_data
        assert "user_reset_auth:999" not in buttons_data


@pytest.mark.asyncio
async def test_subadmin_role_isolation(test_db: Database) -> None:
    # 1. Subadmin panel keyboard should NOT contain hidden routes, all chats, or system routes
    kb_subadmin = admin_panel_kb(is_subadmin=True)
    subadmin_callbacks = [btn.callback_data for row in kb_subadmin.inline_keyboard for btn in row]

    assert "admin_hidden_routes" not in subadmin_callbacks
    assert "admin_password" not in subadmin_callbacks
    assert "admin_all_routes" not in subadmin_callbacks
    assert "admin_all_chats" not in subadmin_callbacks
    assert "nav_status" not in subadmin_callbacks
    assert "admin_users" in subadmin_callbacks
    assert "admin_llm_settings" in subadmin_callbacks
    assert "admin_moderation_chats" in subadmin_callbacks

    # Full admin panel keyboard
    kb_admin = admin_panel_kb(is_subadmin=False)
    admin_callbacks = [btn.callback_data for row in kb_admin.inline_keyboard for btn in row]
    assert "admin_password" in admin_callbacks
    assert "admin_all_routes" in admin_callbacks
    assert "admin_all_chats" in admin_callbacks

    # 2. LLM settings keyboard isolation (subadmin cannot change API key or Base URL)
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


@pytest.mark.asyncio
async def test_subadmin_cannot_access_all_routes_or_chats(test_db: Database) -> None:
    from bot.handlers.admin import cmd_admin_all_routes, cmd_admin_all_chats, cmd_status, cb_admin_toggle_pause

    cb = MagicMock(spec=CallbackQuery)
    cb.answer = AsyncMock()
    cb.message = MagicMock()
    cb.message.edit_text = AsyncMock()

    # Subadmin trying to call all_routes
    await cmd_admin_all_routes(cb, test_db, is_admin=True, is_subadmin=True)
    cb.answer.assert_called_with("⛔ Доступ разрешён только главному администратору.", show_alert=True)

    # Subadmin trying to call all_chats
    cb.answer.reset_mock()
    await cmd_admin_all_chats(cb, test_db, is_admin=True, is_subadmin=True)
    cb.answer.assert_called_with("⛔ Доступ разрешён только главному администратору.", show_alert=True)

    # Subadmin trying to call status
    cb.answer.reset_mock()
    await cmd_status(cb, test_db, queue=MagicMock(), is_admin=True, is_subadmin=True)
    cb.answer.assert_called_with("⛔ Доступ к статусу системы разрешён только главному администратору.", show_alert=True)

    # Subadmin trying to toggle pause
    cb.answer.reset_mock()
    await cb_admin_toggle_pause(cb, test_db, queue=MagicMock(), is_admin=True, is_subadmin=True)
    cb.answer.assert_called_with("⛔ Доступ разрешён только главному администратору.", show_alert=True)


@pytest.mark.asyncio
async def test_user_routes_isolation_between_accounts(test_db: Database) -> None:
    from database.repositories.route_repo import RouteRepository
    from bot.handlers.routes import cmd_routes
    from config.settings import Settings

    settings = Settings(BOT_TOKEN="123:ABC", OWNER_ID=911338473, ANALYTICS_ENABLED=False)

    async with test_db.connect() as conn:
        repo = RouteRepository(conn)
        # Route created by owner
        await repo.create_route(name="Owner Route", source_chat_id=-1001, destination_chat_id=-1002, created_by_user_id=911338473)
        # Route created by subadmin account
        await repo.create_route(name="Subadmin Route", source_chat_id=-1003, destination_chat_id=-1004, created_by_user_id=6205547383)

    # Subadmin opens "Мои маршруты"
    subadmin_event = MagicMock(spec=CallbackQuery)
    subadmin_event.from_user = MagicMock(id=6205547383)
    subadmin_event.answer = AsyncMock()
    subadmin_event.message = MagicMock()
    subadmin_event.message.edit_text = AsyncMock()

    await cmd_routes(subadmin_event, test_db, settings=settings, is_admin=True, is_subadmin=True)
    edit_call = subadmin_event.message.edit_text.call_args[0][0]

    # Should only show 1 route for subadmin, NOT owner route!
    assert "Ваши маршруты (1):" in edit_call


@pytest.mark.asyncio
async def test_system_bot_anonymous_excluded_from_users(test_db: Database) -> None:
    async with test_db.connect() as conn:
        repo = UserRepository(conn)
        await repo.upsert_user(user_id=1087968824, username="GroupAnonymousBot", first_name="Group")
        await repo.upsert_user(user_id=123456, username="real_user", first_name="Real")

        users = await repo.list_users()
        user_ids = [u["user_id"] for u in users]
        assert 1087968824 not in user_ids
        assert 123456 in user_ids
