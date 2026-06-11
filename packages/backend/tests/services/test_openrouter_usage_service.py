"""Tests for OpenRouterUsageService — request counter and gating logic."""
import pytest
import respx
from datetime import date
from httpx import Response

from sqlalchemy import text

from app.services.openrouter_usage_service import OpenRouterUsageService


@pytest.fixture
def usage_service():
    return OpenRouterUsageService()


@pytest.fixture
async def seed_usage_row(db_session):
    """Insert the singleton row required by the service."""
    today = date.today()
    await db_session.execute(
        text(
            "INSERT INTO openrouter_usage_cache (id, request_count_today, day_started_at) "
            "VALUES (1, 0, :today)"
        ),
        {"today": today},
    )
    await db_session.commit()


@pytest.mark.asyncio
class TestRecordAndCheck:
    async def test_increments_counter(
        self, db_session, usage_service, seed_usage_row, monkeypatch
    ):
        monkeypatch.setattr("app.core.config.settings.OPENROUTER_FREE_TIER_LIMIT", 1000)
        status = await usage_service.record_and_check(db_session)
        assert status.count_today == 1
        status = await usage_service.record_and_check(db_session)
        assert status.count_today == 2
        assert status.warning_message is None

    async def test_returns_warning_at_threshold(
        self, db_session, usage_service, seed_usage_row, monkeypatch
    ):
        monkeypatch.setattr("app.core.config.settings.OPENROUTER_FREE_TIER_LIMIT", 100)
        monkeypatch.setattr("app.core.config.settings.GLOBAL_QUOTA_WARNING_PCT", 90)
        threshold = 90  # 90% of 100
        # Set counter to just below threshold
        await db_session.execute(
            text("UPDATE openrouter_usage_cache SET request_count_today = :c WHERE id = 1"),
            {"c": threshold - 1},
        )
        await db_session.commit()

        # This increment hits the warning threshold but does not raise.
        status = await usage_service.record_and_check(db_session)
        assert status.count_today == threshold
        assert status.limit == 100
        assert status.is_near_limit is True
        assert status.warning_message is not None

    async def test_resets_on_new_day(
        self, db_session, usage_service, monkeypatch
    ):
        monkeypatch.setattr("app.core.config.settings.OPENROUTER_FREE_TIER_LIMIT", 1000)
        yesterday = date(2020, 1, 1)
        await db_session.execute(
            text(
                "INSERT INTO openrouter_usage_cache (id, request_count_today, day_started_at) "
                "VALUES (1, 500, :yesterday)"
            ),
            {"yesterday": yesterday},
        )
        await db_session.commit()

        status = await usage_service.record_and_check(db_session)
        assert status.count_today == 1  # Reset to 1 on new day

    async def test_get_status_does_not_increment(
        self, db_session, usage_service, seed_usage_row, monkeypatch
    ):
        monkeypatch.setattr("app.core.config.settings.OPENROUTER_FREE_TIER_LIMIT", 1000)

        status = await usage_service.get_status(db_session)
        assert status.count_today == 0

        row = await db_session.execute(
            text("SELECT request_count_today FROM openrouter_usage_cache WHERE id = 1")
        )
        assert row.scalar_one() == 0


@pytest.mark.asyncio
class TestRefreshKeySnapshot:
    async def test_skips_when_no_api_key(
        self, db_session, usage_service, seed_usage_row, monkeypatch
    ):
        monkeypatch.setattr("app.core.config.settings.OPENROUTER_API_KEY", None)
        # Should not raise and should not make any HTTP calls
        await usage_service.refresh_key_snapshot(db_session)

    @respx.mock
    async def test_updates_cache_on_success(
        self, db_session, usage_service, seed_usage_row, monkeypatch
    ):
        monkeypatch.setattr("app.core.config.settings.OPENROUTER_API_KEY", "test-key")

        respx.get("https://openrouter.ai/api/v1/key").mock(
            return_value=Response(200, json={"data": {"limit": 1000}})
        )

        import httpx

        async with httpx.AsyncClient() as client:
            await usage_service.refresh_key_snapshot(db_session, http_client=client)

        row = await db_session.execute(
            text("SELECT last_key_response FROM openrouter_usage_cache WHERE id = 1")
        )
        result = row.scalar_one()
        assert result is not None
        assert result["limit"] == 1000

    @respx.mock
    async def test_graceful_on_api_failure(
        self, db_session, usage_service, seed_usage_row, monkeypatch
    ):
        monkeypatch.setattr("app.core.config.settings.OPENROUTER_API_KEY", "test-key")

        respx.get("https://openrouter.ai/api/v1/key").mock(
            return_value=Response(500, text="Internal Server Error")
        )

        # Should not raise
        await usage_service.refresh_key_snapshot(db_session)
