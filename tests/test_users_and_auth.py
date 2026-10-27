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
