"""Daily per-user quota management for in-house free-tier AI usage."""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date
from typing import Literal
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import UserApiKey, UserLLMPreferences, UserUsageQuota
from app.services.exceptions import QuotaExhaustedError
from app.services.openrouter_usage_service import openrouter_usage_service


QuotaFeature = Literal[
    "chat",
    "explain_paraphrase",
    "auto_highlight_quick",
    "auto_highlight_thorough",
]


@dataclass(frozen=True)
class QuotaFeatureConfig:
    column: str
    setting_name: str


@dataclass(frozen=True)
class QuotaCheckResult:
    remaining: int
    reset_at: date | None
    was_reset: bool = False
    global_warning: str | None = None
    unlimited: bool = False

    def with_global_warning(self, warning: str | None) -> "QuotaCheckResult":
        return replace(self, global_warning=warning)


@dataclass(frozen=True)
class UserQuotaSnapshot:
    chat_remaining: int
    explain_paraphrase_remaining: int
    auto_highlight_quick_remaining: int
    auto_highlight_thorough_remaining: int
    reset_at: date
    has_own_key: bool
    providers: list[str]
    openrouter_key_mode: str
    global_warning: str | None = None


_FEATURES: dict[QuotaFeature, QuotaFeatureConfig] = {
    "chat": QuotaFeatureConfig("chat_uses_remaining", "QUOTA_CHAT_DAILY"),
    "explain_paraphrase": QuotaFeatureConfig(
        "explain_uses_remaining",
        "QUOTA_EXPLAIN_PARAPHRASE_DAILY",
    ),
    "auto_highlight_quick": QuotaFeatureConfig(
        "auto_highlight_quick_remaining",
        "QUOTA_AUTO_HIGHLIGHT_QUICK_DAILY",
    ),
    "auto_highlight_thorough": QuotaFeatureConfig(
        "auto_highlight_thorough_remaining",
        "QUOTA_AUTO_HIGHLIGHT_THOROUGH_DAILY",
    ),
}


class QuotaService:
    """Service for daily quota reset, decrement, and display snapshots."""

    @staticmethod
    def unlimited() -> QuotaCheckResult:
        return QuotaCheckResult(remaining=-1, reset_at=None, unlimited=True)

    async def check_and_decrement(
        self,
        user_id: UUID,
        db: AsyncSession,
        feature: QuotaFeature,
    ) -> QuotaCheckResult:
        """Atomically reset stale quota rows and decrement one unit for a feature."""
        config = _FEATURES[feature]
        default = self._default_for(feature)

        await self._insert_if_missing(user_id, db)

        stmt = text(f"""
            WITH current_day AS (
                SELECT (now() AT TIME ZONE 'UTC')::date AS today
            ),
            candidate AS (
                SELECT
                    user_usage_quotas.user_id,
                    user_usage_quotas.reset_at < current_day.today AS was_reset
                FROM user_usage_quotas, current_day
                WHERE user_usage_quotas.user_id = :user_id
            ),
            updated AS (
                UPDATE user_usage_quotas
                SET {config.column} = CASE
                        WHEN candidate.was_reset THEN :default - 1
                        ELSE {config.column} - 1
                    END,
                    reset_at = CASE
                        WHEN candidate.was_reset THEN current_day.today
                        ELSE user_usage_quotas.reset_at
                    END,
                    updated_at = now()
                FROM current_day, candidate
                WHERE user_usage_quotas.user_id = candidate.user_id
                  AND (
                      candidate.was_reset
                      OR user_usage_quotas.{config.column} > 0
                  )
                RETURNING
                    user_usage_quotas.{config.column} AS remaining,
                    user_usage_quotas.reset_at AS reset_at,
                    candidate.was_reset AS was_reset
            )
            SELECT remaining, reset_at, was_reset FROM updated
        """)
        result = await db.execute(
            stmt,
            {
                "user_id": user_id,
                "default": default,
            },
        )
        row = result.mappings().one_or_none()
        if row is None:
            current = await self._current_remaining(user_id, db, config.column)
            raise QuotaExhaustedError(feature, remaining=current)

        await db.flush()
        return QuotaCheckResult(
            remaining=row["remaining"],
            reset_at=row["reset_at"],
            was_reset=row["was_reset"],
        )

    async def get_all_quotas(
        self,
        user_id: UUID,
        db: AsyncSession,
    ) -> UserQuotaSnapshot:
        """Return all quota counters, resetting stale rows without consuming usage."""
        await self._insert_if_missing(user_id, db)
        await self._reset_if_stale(user_id, db)

        result = await db.execute(
            select(UserUsageQuota).where(UserUsageQuota.user_id == user_id)
        )
        quota = result.scalar_one()

        keys_result = await db.execute(
            select(UserApiKey.provider).where(
                UserApiKey.user_id == user_id,
                UserApiKey.provider == "openrouter",
            )
        )
        providers = [row[0] for row in keys_result.all()]

        mode_result = await db.execute(
            select(UserLLMPreferences.openrouter_key_mode).where(
                UserLLMPreferences.user_id == user_id
            )
        )
        openrouter_key_mode = mode_result.scalar_one_or_none() or "app"

        global_status = await openrouter_usage_service.get_status(db)
        return UserQuotaSnapshot(
            chat_remaining=quota.chat_uses_remaining,
            explain_paraphrase_remaining=quota.explain_uses_remaining,
            auto_highlight_quick_remaining=quota.auto_highlight_quick_remaining,
            auto_highlight_thorough_remaining=quota.auto_highlight_thorough_remaining,
            reset_at=quota.reset_at,
            has_own_key=bool(providers),
            providers=providers,
            openrouter_key_mode=openrouter_key_mode,
            global_warning=global_status.warning_message,
        )

    async def _insert_if_missing(self, user_id: UUID, db: AsyncSession) -> None:
        await db.execute(
            text("""
                INSERT INTO user_usage_quotas (user_id)
                VALUES (:user_id)
                ON CONFLICT (user_id) DO NOTHING
            """),
            {"user_id": user_id},
        )
        await db.flush()

    async def _reset_if_stale(self, user_id: UUID, db: AsyncSession) -> None:
        await db.execute(
            text("""
                UPDATE user_usage_quotas
                SET chat_uses_remaining = :chat_default,
                    explain_uses_remaining = :explain_default,
                    auto_highlight_quick_remaining = :quick_default,
                    auto_highlight_thorough_remaining = :thorough_default,
                    reset_at = (now() AT TIME ZONE 'UTC')::date,
                    updated_at = now()
                WHERE user_id = :user_id
                  AND reset_at < (now() AT TIME ZONE 'UTC')::date
            """),
            {
                "user_id": user_id,
                "chat_default": self._default_for("chat"),
                "explain_default": self._default_for("explain_paraphrase"),
                "quick_default": self._default_for("auto_highlight_quick"),
                "thorough_default": self._default_for("auto_highlight_thorough"),
            },
        )
        await db.flush()

    async def _current_remaining(
        self,
        user_id: UUID,
        db: AsyncSession,
        column: str,
    ) -> int:
        if column not in {config.column for config in _FEATURES.values()}:
            raise ValueError(f"Unknown quota column: {column}")
        result = await db.execute(
            text(f"""
                SELECT {column}
                FROM user_usage_quotas
                WHERE user_id = :user_id
            """),
            {"user_id": user_id},
        )
        value = result.scalar_one_or_none()
        return int(value or 0)

    def _default_for(self, feature: QuotaFeature) -> int:
        return int(getattr(settings, _FEATURES[feature].setting_name))


quota_service = QuotaService()
