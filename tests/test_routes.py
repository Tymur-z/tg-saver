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
