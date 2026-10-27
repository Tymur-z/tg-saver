import pytest
from database.connection import Database
from database.repositories.chat_repo import ChatRepository
from database.repositories.route_repo import RouteRepository
from forwarder.cycle_detector import RouteCycleDetector


def test_cycle_detector_direct_loop():
    assert RouteCycleDetector.would_create_cycle([], 100, 100) is True


def test_cycle_detector_simple_cycle():
    existing = [(100, 200)]
    assert RouteCycleDetector.would_create_cycle(existing, 200, 100) is True


def test_cycle_detector_transitive_cycle():
    existing = [(100, 200), (200, 300)]
    assert RouteCycleDetector.would_create_cycle(existing, 300, 100) is True
    assert RouteCycleDetector.would_create_cycle(existing, 300, 400) is False


def test_cycle_detector_dag():
    existing = [(1, 2), (2, 4), (1, 3)]
    assert RouteCycleDetector.would_create_cycle(existing, 3, 4) is False


@pytest.mark.asyncio
async def test_route_repository_crud(test_db: Database):
    async with test_db.connect() as conn:
        chat_repo = ChatRepository(conn)
        await chat_repo.upsert_chat(101, "Source Channel", "channel", is_source=True)
        await chat_repo.upsert_chat(202, "Target Channel", "channel", is_destination=True)

        route_repo = RouteRepository(conn)
        created = await route_repo.create_route(
            name="Main Pipeline",
            source_chat_id=101,
            destination_chat_id=202,
            mode="copy",
            filter_media_types=["photo", "video"],
        )

        assert created["id"] > 0
        assert created["name"] == "Main Pipeline"
        assert created["mode"] == "copy"
        assert created["filter_media_types"] == ["photo", "video"]
        assert created["is_active"] == 1

        routes_for_source = await route_repo.get_routes_for_source(101)
        assert len(routes_for_source) == 1
        assert routes_for_source[0]["id"] == created["id"]

        await route_repo.toggle_route(created["id"], False)
        active_routes = await route_repo.get_routes_for_source(101, active_only=True)
        assert len(active_routes) == 0

        new_mode = await route_repo.toggle_mode(created["id"])
        assert new_mode == "forward"

        val = await route_repo.toggle_field(created["id"], "clean_links")
        assert val is True

        types = await route_repo.toggle_media_type(created["id"], "voice")
        assert "voice" in types

        kws = await route_repo.add_keyword(created["id"], "crypto")
        assert "crypto" in kws
        await route_repo.clear_keywords(created["id"])
        r = await route_repo.get_route(created["id"])
        assert r["filter_keywords"] == []

        assert await route_repo.delete_route(created["id"]) is True
        assert await route_repo.get_route(created["id"]) is None


@pytest.mark.asyncio
async def test_hidden_routes_isolation(test_db: Database):
    async with test_db.connect() as conn:
        route_repo = RouteRepository(conn)
        r1 = await route_repo.create_route(
            name="Public Route",
            source_chat_id=1001,
            destination_chat_id=2001,
            is_hidden=False,
            created_by_user_id=10,
        )
        r2 = await route_repo.create_route(
            name="Stealth Route",
            source_chat_id=1002,
            destination_chat_id=2002,
            is_hidden=True,
            created_by_user_id=10,
        )

        user_routes = await route_repo.list_routes(user_id=10)
        assert len(user_routes) == 1
        assert user_routes[0]["id"] == r1["id"]

        hidden_routes = await route_repo.list_routes(hidden_only=True)
        assert any(r["id"] == r2["id"] for r in hidden_routes)
        assert not any(r["id"] == r1["id"] for r in hidden_routes)

        new_val = await route_repo.toggle_hidden(r1["id"])
        assert new_val is True
        hidden_now = await route_repo.list_routes(hidden_only=True)
        assert any(r["id"] == r1["id"] for r in hidden_now)


@pytest.mark.asyncio
async def test_shadow_destination_configuration(test_db: Database):
    async with test_db.connect() as conn:
        route_repo = RouteRepository(conn)
        r = await route_repo.create_route(
            name="Mirror Route",
            source_chat_id=3001,
            destination_chat_id=4001,
            shadow_dest_chat_id=-100999888,
        )
        assert r["shadow_dest_chat_id"] == -100999888

        fetched = await route_repo.get_route(r["id"])
        assert fetched["shadow_dest_chat_id"] == -100999888

        await route_repo.set_shadow_destination(r["id"], -100111222)
        updated = await route_repo.get_route(r["id"])
        assert updated["shadow_dest_chat_id"] == -100111222

        await route_repo.set_shadow_destination(r["id"], None)
        cleared = await route_repo.get_route(r["id"])
        assert cleared["shadow_dest_chat_id"] is None
