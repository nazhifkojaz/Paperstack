"""API key resolution and quota management service.

This service centralizes the logic for:
1. Resolving which LLM API key to use (user's key vs in-house key)
2. Checking and managing usage quotas
3. Supporting multiple quota types (chat, explain, free/auto-highlight)

Services raise custom exceptions, never HTTPException. Route handlers
are responsible for translating to appropriate HTTP status codes.
"""

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Literal

from sqlalchemy import case, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import decrypt_token
from app.db.models import User, UserApiKey, UserUsageQuota
from app.services.exceptions import ApiKeyNotFoundError, QuotaExhaustedError


logger = logging.getLogger(__name__)


QuotaField = Literal["chat_uses_remaining", "explain_uses_remaining", "free_uses_remaining"]
Provider = Literal["openai", "anthropic", "gemini", "glm", "openrouter"]


class QuotaType(Enum):
    """Quota types for different features."""
    CHAT = "chat_uses_remaining"
    EXPLAIN = "explain_uses_remaining"
    FREE = "free_uses_remaining"


@dataclass
class ApiKeyResolution:
    """Result of API key resolution.

    Attributes:
        provider: The LLM provider ('openai', 'anthropic', 'gemini', 'glm', 'openrouter')
        api_key: The decrypted API key
        is_in_house: True if using in-house key (quota applies), False if user's own key
        quota_remaining: Remaining quota if in_house, None if unlimited (user's key)
    """
    provider: str
    api_key: str
    is_in_house: bool
    quota_remaining: int | None


class ApiKeyService:
    """Service for resolving API keys and managing quotas."""

    # Default provider priorities for different features
    AUTO_HIGHLIGHT_PRIORITY: list[Provider] = ["glm", "gemini"]
    CHAT_PRIORITY: list[Provider] = ["openai", "anthropic", "gemini", "glm"]
    EXPLAIN_PRIORITY: list[Provider] = ["openai", "anthropic", "gemini", "glm"]

    # In-house provider priority (used when user has no key)
    IN_HOUSE_PRIORITY: list[Provider] = ["openrouter", "gemini", "glm"]

    async def resolve_for_chat(
        self,
        user: User,
        db: AsyncSession,
    ) -> ApiKeyResolution:
        """Resolve API key for chat operations.

        Priority: user's keys (openai > anthropic > gemini > glm) →
                  in-house fallback (gemini > glm) with chat quota check.

        Args:
            user: The authenticated user
            db: Database session

        Returns:
            ApiKeyResolution with provider, key, and quota info

        Raises:
            QuotaExhaustedError: If in-house quota is exhausted
            ApiKeyNotFoundError: If no provider is available
        """
        return await self._resolve_api_key(
            user=user,
            db=db,
            quota_field=QuotaType.CHAT.value,
            provider_priority=self.CHAT_PRIORITY,
        )

    async def resolve_for_explain(
        self,
        user: User,
        db: AsyncSession,
    ) -> ApiKeyResolution:
        """Resolve API key for explain operations.

        Same priority as chat, but checks explain quota.

        Args:
            user: The authenticated user
            db: Database session

        Returns:
            ApiKeyResolution with provider, key, and quota info

        Raises:
            QuotaExhaustedError: If in-house quota is exhausted
            ApiKeyNotFoundError: If no provider is available
        """
        return await self._resolve_api_key(
            user=user,
            db=db,
            quota_field=QuotaType.EXPLAIN.value,
            provider_priority=self.EXPLAIN_PRIORITY,
        )

    async def resolve_for_auto_highlight(
        self,
        user: User,
        db: AsyncSession,
    ) -> ApiKeyResolution:
        """Resolve API key for auto-highlight operations.

        Priority: user's keys (glm > gemini) →
                  in-house fallback (glm > gemini) with free quota check.

        Args:
            user: The authenticated user
            db: Database session

        Returns:
            ApiKeyResolution with provider, key, and quota info

        Raises:
            QuotaExhaustedError: If in-house quota is exhausted
            ApiKeyNotFoundError: If no provider is available
        """
        return await self._resolve_api_key(
            user=user,
            db=db,
            quota_field=QuotaType.FREE.value,
            provider_priority=self.AUTO_HIGHLIGHT_PRIORITY,
        )

    async def resolve_paid_fallback(
        self,
        user: User,
        db: AsyncSession,
        quota_field: QuotaField,
        feature_priority: list[Provider],
    ) -> ApiKeyResolution:
        """Resolve a paid in-house key, skipping OpenRouter.

        Used when OpenRouter returns 429 and we need to fall back to paid keys.
        Checks quota and returns the first available paid in-house provider.

        Raises:
            QuotaExhaustedError: If quota is exhausted
            ApiKeyNotFoundError: If no paid provider is available
        """
        paid_priority = [p for p in feature_priority if p in self.IN_HOUSE_PRIORITY and p != "openrouter"]

        quota_row = await self._get_or_create_quota(user.id, db, quota_field)
        current_quota = getattr(quota_row, quota_field, 0)

        if current_quota <= 0:
            raise QuotaExhaustedError(quota_field, remaining=current_quota)

        for provider in paid_priority:
            api_key = getattr(settings, f"{provider.upper()}_API_KEY")
            if api_key:
                logger.info(
                    "Using paid fallback %s key for user %s (%s uses remaining)",
                    provider,
                    user.id,
                    current_quota,
                )
                return ApiKeyResolution(
                    provider=provider,
                    api_key=api_key,
                    is_in_house=True,
                    quota_remaining=current_quota,
                )

        raise ApiKeyNotFoundError(quota_field.replace("_", " "))

    async def _resolve_api_key(
        self,
        user: User,
        db: AsyncSession,
        quota_field: QuotaField,
        provider_priority: list[Provider],
    ) -> ApiKeyResolution:
        """Internal method to resolve API key with given parameters.

        Args:
            user: The authenticated user
            db: Database session
            quota_field: Which quota field to check for in-house usage
            provider_priority: Order to check user's stored keys

        Returns:
            ApiKeyResolution with provider, key, and quota info

        Raises:
            QuotaExhaustedError: If in-house quota is exhausted
            ApiKeyNotFoundError: If no provider is available
        """
        # 1. Check user's own keys in priority order
        result = await db.execute(
            select(UserApiKey)
            .where(UserApiKey.user_id == user.id)
            .order_by(
                case(
                    *[(UserApiKey.provider == p, i) for i, p in enumerate(provider_priority)],
                    else_=len(provider_priority),
                )
            )
        )
        user_keys = result.scalars().all()

        for key_row in user_keys:
            decrypted = decrypt_token(key_row.encrypted_key)
            logger.info(
                "Using user-provided %s key (ending ...%s) for user %s",
                key_row.provider,
                decrypted[-4:],
                user.id,
            )
            return ApiKeyResolution(
                provider=key_row.provider,
                api_key=decrypted,
                is_in_house=False,
                quota_remaining=None,
            )

        # 2. No user keys - check in-house quota
        logger.info("No user API keys found for user %s, checking in-house quota", user.id)

        quota_row = await self._get_or_create_quota(user.id, db, quota_field)
        current_quota = getattr(quota_row, quota_field, 0)

        if current_quota <= 0:
            raise QuotaExhaustedError(quota_field, remaining=current_quota)

        # 3. Use in-house key by priority (respects feature-specific ordering)
        for provider in provider_priority:
            if provider not in self.IN_HOUSE_PRIORITY:
                continue
            api_key = getattr(settings, f"{provider.upper()}_API_KEY")
            if api_key:
                logger.info(
                    "Using in-house %s key for user %s (%s uses remaining)",
                    provider,
                    user.id,
                    current_quota,
                )
                return ApiKeyResolution(
                    provider=provider,
                    api_key=api_key,
                    is_in_house=True,
                    quota_remaining=current_quota,
                )

        # 4. No provider available
        raise ApiKeyNotFoundError(quota_field.replace("_", " "))

    async def _get_or_create_quota(
        self,
        user_id: str,
        db: AsyncSession,
        quota_field: QuotaField,
    ) -> UserUsageQuota:
        """Get or create user quota row.

        Args:
            user_id: The user's ID
            db: Database session
            quota_field: Which quota field we're checking

        Returns:
            UserUsageQuota row (created if missing)
        """
        result = await db.execute(
            select(UserUsageQuota).where(UserUsageQuota.user_id == user_id)
        )
        quota_row = result.scalar_one_or_none()

        if quota_row is None:
            # Always initialise all three fields so no column is left NULL
            quota_row = UserUsageQuota(
                user_id=user_id,
                free_uses_remaining=5,
                chat_uses_remaining=20,
                explain_uses_remaining=20,
            )
            db.add(quota_row)
            await db.flush()

        return quota_row

    async def decrement_quota(
        self,
        user_id: str,
        quota_type: QuotaType,
        db: AsyncSession,
    ) -> int:
        """Decrement a quota field and return the new value.

        Args:
            user_id: The user's ID
            quota_type: Which quota to decrement
            db: Database session (will be committed by caller)

        Returns:
            The updated quota value (0 if exhausted), or -1 if quota row doesn't exist

        Note:
            This should be called AFTER the API call succeeds for non-streaming.
            For streaming, call it BEFORE starting the stream (optimistic decrement).
        """
        result = await db.execute(
            select(UserUsageQuota).where(UserUsageQuota.user_id == user_id)
        )
        quota_row = result.scalar_one_or_none()

        if quota_row:
            quota_field = quota_type.value
            current_value = getattr(quota_row, quota_field, 0)
            new_value = max(0, current_value - 1)
            setattr(quota_row, quota_field, new_value)
            logger.info(
                "Decremented %s for user %s: %d -> %d",
                quota_field,
                user_id,
                current_value,
                new_value,
            )
            return new_value

        return -1


# Singleton instance for use in routes
api_key_service = ApiKeyService()
