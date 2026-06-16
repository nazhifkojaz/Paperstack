"""OpenRouter free-tier usage tracking service.

Self-tracked request counter with daily UTC rollover.
Warning threshold: GLOBAL_QUOTA_WARNING_PCT of OPENROUTER_FREE_TIER_LIMIT.
"""

import json
import logging
from dataclasses import dataclass
from typing import Optional

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings

logger = logging.getLogger(__name__)

_KEY_URL = "https://openrouter.ai/api/v1/key"


@dataclass(frozen=True)
class GlobalQuotaStatus:
    count_today: int
    limit: int
    threshold_pct: int
    is_near_limit: bool
    warning_message: str | None = None


class OpenRouterUsageService:
    async def record_and_check(self, db: AsyncSession) -> GlobalQuotaStatus:
        """Atomically roll over the usage day if needed and increment the counter."""
        stmt = text("""
            INSERT INTO openrouter_usage_cache (id, request_count_today, day_started_at)
            VALUES (1, 1, (now() AT TIME ZONE 'UTC')::date)
            ON CONFLICT (id) DO UPDATE SET
                request_count_today = CASE
                    WHEN openrouter_usage_cache.day_started_at < (now() AT TIME ZONE 'UTC')::date
                    THEN 1
                    ELSE openrouter_usage_cache.request_count_today + 1
                END,
                day_started_at = CASE
                    WHEN openrouter_usage_cache.day_started_at < (now() AT TIME ZONE 'UTC')::date
                    THEN (now() AT TIME ZONE 'UTC')::date
                    ELSE openrouter_usage_cache.day_started_at
                END,
                last_request_at = now()
            RETURNING openrouter_usage_cache.request_count_today
        """)
        result = await db.execute(stmt)
        new_count = result.scalar_one()
        await db.flush()

        return self._build_status(new_count)

    async def get_status(self, db: AsyncSession) -> GlobalQuotaStatus:
        """Read the current soft global counter without incrementing it."""
        stmt = text("""
            SELECT
                CASE
                    WHEN day_started_at < (now() AT TIME ZONE 'UTC')::date THEN 0
                    ELSE request_count_today
                END AS request_count_today
            FROM openrouter_usage_cache
            WHERE id = 1
        """)
        result = await db.execute(stmt)
        count_today = result.scalar_one_or_none() or 0
        return self._build_status(count_today)

    async def refresh_key_snapshot(
        self, db: AsyncSession, http_client: Optional[httpx.AsyncClient] = None
    ) -> None:
        """Best-effort refresh of cached /api/v1/key payload for operator visibility."""
        if not settings.OPENROUTER_API_KEY:
            return
        headers = {"Authorization": f"Bearer {settings.OPENROUTER_API_KEY}"}
        client = http_client or httpx.AsyncClient(timeout=10.0)
        should_close = http_client is None
        try:
            if should_close:
                async with client:
                    resp = await client.get(_KEY_URL, headers=headers)
            else:
                resp = await client.get(_KEY_URL, headers=headers)
            if resp.status_code != 200:
                logger.warning("OpenRouter /api/v1/key returned %s", resp.status_code)
                return
            payload = resp.json().get("data", resp.json())
            await db.execute(
                text("""
                    UPDATE openrouter_usage_cache
                    SET last_key_response = CAST(:payload AS jsonb),
                        last_key_fetched_at = now()
                    WHERE id = 1
                """),
                {"payload": json.dumps(payload)},
            )
            await db.flush()
        except Exception as exc:
            logger.warning("Failed to refresh OpenRouter key snapshot: %s", exc)

    def _build_status(self, count_today: int) -> GlobalQuotaStatus:
        limit = settings.OPENROUTER_FREE_TIER_LIMIT
        threshold_pct = settings.GLOBAL_QUOTA_WARNING_PCT
        threshold = max(1, int(limit * threshold_pct / 100))
        is_near_limit = count_today >= threshold
        warning = None
        if is_near_limit:
            warning = (
                f"OpenRouter free-tier usage is at {threshold_pct}% or above "
                f"({count_today}/{limit} requests today). Add a personal API key "
                "in Settings for uninterrupted AI features."
            )
        return GlobalQuotaStatus(
            count_today=count_today,
            limit=limit,
            threshold_pct=threshold_pct,
            is_near_limit=is_near_limit,
            warning_message=warning,
        )


openrouter_usage_service = OpenRouterUsageService()
