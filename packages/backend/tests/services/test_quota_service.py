"""Tests for daily per-user quota management."""
from datetime import date

import pytest
from sqlalchemy import select

from app.core.security import encrypt_token
from app.db.models import UserApiKey, UserUsageQuota
from app.services.exceptions import QuotaExhaustedError
from app.services.quota_service import QuotaService


@pytest.fixture
def quota_service():
    return QuotaService()


@pytest.mark.asyncio
class TestQuotaService:
    async def test_creates_row_and_decrements_chat_quota(
        self, db_session, test_user, quota_service, monkeypatch
    ):
        monkeypatch.setattr("app.core.config.settings.QUOTA_CHAT_DAILY", 50)

        result = await quota_service.check_and_decrement(
            test_user.id,
            db_session,
            "chat",
        )

        assert result.remaining == 49
        assert result.unlimited is False

        row_result = await db_session.execute(
            select(UserUsageQuota).where(UserUsageQuota.user_id == test_user.id)
        )
        quota_row = row_result.scalar_one()
        assert quota_row.chat_uses_remaining == 49

    async def test_exhaustion_does_not_persist_negative_counter(
        self, db_session, test_user, quota_service
    ):
        today = date.today()
        quota_row = UserUsageQuota(
            user_id=test_user.id,
            chat_uses_remaining=0,
            explain_uses_remaining=30,
            auto_highlight_quick_remaining=5,
            auto_highlight_thorough_remaining=3,
            reset_at=today,
        )
        db_session.add(quota_row)
        await db_session.commit()

        with pytest.raises(QuotaExhaustedError):
            await quota_service.check_and_decrement(test_user.id, db_session, "chat")

        await db_session.refresh(quota_row)
        assert quota_row.chat_uses_remaining == 0

    async def test_stale_quota_resets_before_decrement(
        self, db_session, test_user, quota_service, monkeypatch
    ):
        monkeypatch.setattr("app.core.config.settings.QUOTA_CHAT_DAILY", 50)
        quota_row = UserUsageQuota(
            user_id=test_user.id,
            chat_uses_remaining=0,
            explain_uses_remaining=0,
            auto_highlight_quick_remaining=0,
            auto_highlight_thorough_remaining=0,
            reset_at=date(2020, 1, 1),
        )
        db_session.add(quota_row)
        await db_session.commit()

        result = await quota_service.check_and_decrement(
            test_user.id,
            db_session,
            "chat",
        )

        assert result.remaining == 49
        assert result.was_reset is True
        await db_session.refresh(quota_row)
        assert quota_row.chat_uses_remaining == 49
        assert quota_row.reset_at != date(2020, 1, 1)

    async def test_get_all_quotas_resets_stale_row_and_includes_key_status(
        self, db_session, test_user, quota_service, monkeypatch
    ):
        monkeypatch.setattr("app.core.config.settings.QUOTA_CHAT_DAILY", 50)
        monkeypatch.setattr("app.core.config.settings.QUOTA_EXPLAIN_PARAPHRASE_DAILY", 30)
        monkeypatch.setattr("app.core.config.settings.QUOTA_AUTO_HIGHLIGHT_QUICK_DAILY", 5)
        monkeypatch.setattr("app.core.config.settings.QUOTA_AUTO_HIGHLIGHT_THOROUGH_DAILY", 3)

        db_session.add(
            UserUsageQuota(
                user_id=test_user.id,
                chat_uses_remaining=0,
                explain_uses_remaining=0,
                auto_highlight_quick_remaining=0,
                auto_highlight_thorough_remaining=0,
                reset_at=date(2020, 1, 1),
            )
        )
        db_session.add(
            UserApiKey(
                user_id=test_user.id,
                provider="openrouter",
                encrypted_key=encrypt_token("sk-test"),
            )
        )
        await db_session.commit()

        snapshot = await quota_service.get_all_quotas(test_user.id, db_session)

        assert snapshot.chat_remaining == 50
        assert snapshot.explain_paraphrase_remaining == 30
        assert snapshot.auto_highlight_quick_remaining == 5
        assert snapshot.auto_highlight_thorough_remaining == 3
        assert snapshot.has_own_key is True
        assert snapshot.providers == ["openrouter"]
        assert snapshot.openrouter_key_mode == "app"

    async def test_get_all_quotas_ignores_legacy_non_openrouter_keys(
        self, db_session, test_user, quota_service
    ):
        db_session.add(
            UserApiKey(
                user_id=test_user.id,
                provider="gemini",
                encrypted_key=encrypt_token("legacy-key"),
            )
        )
        await db_session.commit()

        snapshot = await quota_service.get_all_quotas(test_user.id, db_session)

        assert snapshot.has_own_key is False
        assert snapshot.providers == []
        assert snapshot.openrouter_key_mode == "app"
