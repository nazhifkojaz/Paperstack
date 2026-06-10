"""API key resolution service.

This service centralizes the logic for:
1. Resolving which LLM API key to use (user's key vs in-house key)

Services raise custom exceptions, never HTTPException. Route handlers
are responsible for translating to appropriate HTTP status codes.
"""

import logging
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import case, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import decrypt_token
from app.db.models import User, UserApiKey
from app.services.exceptions import ApiKeyNotFoundError


logger = logging.getLogger(__name__)


Provider = Literal["openai", "anthropic", "openrouter"]  # gemini/glm removed - no BYOK users


@dataclass
class ApiKeyResolution:
    """Result of API key resolution.

    Attributes:
        provider: The LLM provider ('openai', 'anthropic', 'gemini', 'glm', 'openrouter')
        api_key: The decrypted API key
        is_in_house: True if using in-house key (quota applies), False if user's own key
        model: Specific model ID to use (set when user forces a free-tier model)
    """
    provider: str
    api_key: str
    is_in_house: bool
    model: str | None = None


class ApiKeyService:
    """Service for resolving API keys."""

    # Provider priorities for BYOK user keys
    AUTO_HIGHLIGHT_PRIORITY: list[Provider] = ["openai", "anthropic"]
    CHAT_PRIORITY: list[Provider] = ["openai", "anthropic"]
    EXPLAIN_PRIORITY: list[Provider] = ["openai", "anthropic"]

    # In-house provider — only OpenRouter free tier
    IN_HOUSE_PRIORITY: list[Provider] = ["openrouter"]

    async def resolve_for_chat(
        self,
        user: User,
        db: AsyncSession,
        force_free_model: str | None = None,
    ) -> ApiKeyResolution:
        """Resolve API key for chat operations.

        Args:
            user: The authenticated user
            db: Database session
            force_free_model: If set, skip BYOK keys and force OpenRouter with this model

        Returns:
            ApiKeyResolution with provider, key, and optional model

        Raises:
            ApiKeyNotFoundError: If no provider is available
        """
        return await self._resolve_api_key(
            user=user,
            db=db,
            provider_priority=self.CHAT_PRIORITY,
            force_free_model=force_free_model,
            feature_name="chat",
        )

    async def resolve_for_explain(
        self,
        user: User,
        db: AsyncSession,
        force_free_model: str | None = None,
    ) -> ApiKeyResolution:
        """Resolve API key for explain operations.

        Args:
            user: The authenticated user
            db: Database session
            force_free_model: If set, skip BYOK keys and force OpenRouter with this model

        Returns:
            ApiKeyResolution with provider, key, and optional model

        Raises:
            ApiKeyNotFoundError: If no provider is available
        """
        return await self._resolve_api_key(
            user=user,
            db=db,
            provider_priority=self.EXPLAIN_PRIORITY,
            force_free_model=force_free_model,
            feature_name="explain",
        )

    async def resolve_for_auto_highlight(
        self,
        user: User,
        db: AsyncSession,
        force_free_model: str | None = None,
    ) -> ApiKeyResolution:
        """Resolve API key for auto-highlight operations.

        Args:
            user: The authenticated user
            db: Database session
            force_free_model: If set, skip BYOK keys and force OpenRouter with this model

        Returns:
            ApiKeyResolution with provider, key, and optional model

        Raises:
            ApiKeyNotFoundError: If no provider is available
        """
        return await self._resolve_api_key(
            user=user,
            db=db,
            provider_priority=self.AUTO_HIGHLIGHT_PRIORITY,
            force_free_model=force_free_model,
            feature_name="auto highlight",
        )

    async def _resolve_api_key(
        self,
        user: User,
        db: AsyncSession,
        provider_priority: list[Provider],
        force_free_model: str | None = None,
        feature_name: str = "general",
    ) -> ApiKeyResolution:
        """Internal method to resolve API key with given parameters.

        Args:
            user: The authenticated user
            db: Database session
            provider_priority: Order to check user's stored keys
            force_free_model: If set, skip BYOK keys and force OpenRouter with this model

        Returns:
            ApiKeyResolution with provider, key, and optional model

        Raises:
            ApiKeyNotFoundError: If no provider is available
        """
        # 0. If user explicitly chose a free model, skip BYOK and go straight to in-house
        if force_free_model:
            logger.info(
                "User %s forced free-tier model %s for %s",
                user.id, force_free_model, feature_name,
            )
            api_key = getattr(settings, "OPENROUTER_API_KEY")
            if not api_key:
                raise ApiKeyNotFoundError("openrouter")

            return ApiKeyResolution(
                provider="openrouter",
                api_key=api_key,
                is_in_house=True,
                model=force_free_model,
            )

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
            )

        # 2. No user keys - use in-house key. Quotas are enforced by QuotaService.
        logger.info("No user API keys found for user %s, using in-house key", user.id)

        for provider in self.IN_HOUSE_PRIORITY:
            api_key = getattr(settings, f"{provider.upper()}_API_KEY")
            if api_key:
                logger.info(
                    "Using in-house %s key for user %s",
                    provider,
                    user.id,
                )
                return ApiKeyResolution(
                    provider=provider,
                    api_key=api_key,
                    is_in_house=True,
                )

        # 3. No provider available
        raise ApiKeyNotFoundError(feature_name)



# Singleton instance for use in routes
api_key_service = ApiKeyService()
