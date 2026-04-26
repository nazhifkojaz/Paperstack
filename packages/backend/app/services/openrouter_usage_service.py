"""OpenRouter free-tier usage tracking service.

Self-tracked request counter with daily UTC rollover.
Gating threshold: 90% of OPENROUTER_FREE_TIER_LIMIT (default 1000 req/day).
"""
import json
import logging
from typing import Optional

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.services.exceptions import OpenRouterQuotaError

logger = logging.getLogger(__name__)

_KEY_URL = "https://openrouter.ai/api/v1/key"
_GATE_THRESHOLD = 0.90


class OpenRouterUsageService:

    async def record_and_check(self, db: AsyncSession) -> int:
        """Atomically: roll over day if needed, increment counter, raise if gated.

        Returns the post-increment request count. Raises OpenRouterQuotaError
        if the new count is at/above 90% of OPENROUTER_FREE_TIER_LIMIT.
        """
        limit = settings.OPENROUTER_FREE_TIER_LIMIT
        threshold = int(limit * _GATE_THRESHOLD)

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

        if new_count >= threshold:
            raise OpenRouterQuotaError(
                limit=limit,
                count_today=new_count,
                threshold_pct=int(_GATE_THRESHOLD * 100),
            )

        return new_count

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


openrouter_usage_service = OpenRouterUsageService()
