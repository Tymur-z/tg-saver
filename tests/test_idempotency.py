import pytest
from database.connection import Database
from database.repositories.chat_repo import ChatRepository
from database.repositories.forward_repo import ForwardRepository
from database.repositories.route_repo import RouteRepository


@pytest.mark.asyncio
async def test_idempotent_duplicate_prevention(test_db: Database):
    async with test_db.connect() as conn:
        chat_repo = ChatRepository(conn)
        await chat_repo.upsert_chat(10, "Source", "supergroup", is_source=True)
        await chat_repo.upsert_chat(20, "Dest", "channel", is_destination=True)

        route_repo = RouteRepository(conn)
        route = await route_repo.create_route("Route 1", 10, 20)
        route_id = route["id"]

        forward_repo = ForwardRepository(conn)

        assert await forward_repo.is_already_forwarded(route_id, 10, 555) is False

        await forward_repo.record_pending(route_id, 10, 555, 20)
        assert await forward_repo.is_already_forwarded(route_id, 10, 555) is True

        await forward_repo.mark_sent(route_id, 10, 555, dest_message_id=999)
        assert await forward_repo.is_already_forwarded(route_id, 10, 555) is True

        record = await forward_repo.get_forward_record(route_id, 10, 555)
        assert record is not None
        assert record["status"] == "SENT"
        assert record["dest_message_id"] == 999


@pytest.mark.asyncio
async def test_forward_failure_and_retry(test_db: Database):
    async with test_db.connect() as conn:
        chat_repo = ChatRepository(conn)
        await chat_repo.upsert_chat(10, "Source", "channel", is_source=True)
        await chat_repo.upsert_chat(20, "Dest", "channel", is_destination=True)

        route_repo = RouteRepository(conn)
        route = await route_repo.create_route("Route 1", 10, 20)
        route_id = route["id"]

        forward_repo = ForwardRepository(conn)

        await forward_repo.record_pending(route_id, 10, 777, 20)
        await forward_repo.mark_failed(
            route_id,
            10,
            777,
            "CHAT_FORWARDS_RESTRICTED: Content protected by owner",
        )

        record = await forward_repo.get_forward_record(route_id, 10, 777)
        assert record is not None
        assert record["status"] == "FAILED"
        assert "CHAT_FORWARDS_RESTRICTED" in record["error_message"]

        stats = await forward_repo.get_stats()
        assert stats["FAILED"] == 1
        assert stats["TOTAL"] == 1
