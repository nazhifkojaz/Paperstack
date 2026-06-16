"""API key resolution service.

This service centralizes the logic for:
1. Resolving which LLM API key to use (user's key vs in-house key)

Services raise custom exceptions, never HTTPException. Route handlers
are responsible for translating to appropriate HTTP status codes.
"""

import logging
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import decrypt_token
from app.db.models import User, UserApiKey, UserLLMPreferences
from app.services.exceptions import ApiKeyNotFoundError
from app.services.llm_service import OPENROUTER_BYOK_MODEL_IDS


logger = logging.getLogger(__name__)


Provider = Literal["openrouter"]
OpenRouterKeyMode = Literal["app", "byok"]


@dataclass
class ApiKeyResolution:
    """Result of API key resolution.

    Attributes:
        provider: The LLM provider ('openrouter')
        api_key: The decrypted API key
        is_in_house: True if using in-house key (quota applies), False if user's own key
        model: Specific OpenRouter model ID selected for the request
    """

    provider: str
    api_key: str
    is_in_house: bool
    model: str | None = None


class ApiKeyService:
    """Service for resolving API keys."""

    _PROVIDER_PRIORITY: list[Provider] = ["openrouter"]

    async def resolve_for_chat(
        self,
        user: User,
        db: AsyncSession,
        preferred_model: str | None = None,
        openrouter_key_mode: OpenRouterKeyMode = "app",
    ) -> ApiKeyResolution:
        """Resolve API key for chat operations.

        Args:
            user: The authenticated user
            db: Database session
            preferred_model: OpenRouter model selected by the user, if any
            openrouter_key_mode: Whether to use the app key or user's BYOK key

        Returns:
            ApiKeyResolution with provider, key, and optional model

        Raises:
            ApiKeyNotFoundError: If no provider is available
        """
        return await self._resolve_api_key(
            user=user,
            db=db,
            provider_priority=self._PROVIDER_PRIORITY,
            preferred_model=preferred_model,
            openrouter_key_mode=openrouter_key_mode,
            feature_name="chat",
        )

    async def resolve_for_explain(
        self,
        user: User,
        db: AsyncSession,
        preferred_model: str | None = None,
        openrouter_key_mode: OpenRouterKeyMode = "app",
    ) -> ApiKeyResolution:
        """Resolve API key for explain operations.

        Args:
            user: The authenticated user
            db: Database session
            preferred_model: OpenRouter model selected by the user, if any
            openrouter_key_mode: Whether to use the app key or user's BYOK key

        Returns:
            ApiKeyResolution with provider, key, and optional model

        Raises:
            ApiKeyNotFoundError: If no provider is available
        """
        return await self._resolve_api_key(
            user=user,
            db=db,
            provider_priority=self._PROVIDER_PRIORITY,
            preferred_model=preferred_model,
            openrouter_key_mode=openrouter_key_mode,
            feature_name="explain",
        )

    async def resolve_for_auto_highlight(
        self,
        user: User,
        db: AsyncSession,
        preferred_model: str | None = None,
        openrouter_key_mode: OpenRouterKeyMode = "app",
    ) -> ApiKeyResolution:
        """Resolve API key for auto-highlight operations.

        Args:
            user: The authenticated user
            db: Database session
            preferred_model: OpenRouter model selected by the user, if any
            openrouter_key_mode: Whether to use the app key or user's BYOK key

        Returns:
            ApiKeyResolution with provider, key, and optional model

        Raises:
            ApiKeyNotFoundError: If no provider is available
        """
        return await self._resolve_api_key(
            user=user,
            db=db,
            provider_priority=self._PROVIDER_PRIORITY,
            preferred_model=preferred_model,
            openrouter_key_mode=openrouter_key_mode,
            feature_name="auto highlight",
        )

    async def get_user_openrouter_key(
        self,
        user: User,
        db: AsyncSession,
    ) -> str | None:
        return await self.get_user_openrouter_key_by_id(user.id, db)

    async def get_user_openrouter_key_by_id(
        self,
        user_id: UUID,
        db: AsyncSession,
    ) -> str | None:
        result = await db.execute(
            select(UserApiKey).where(
                UserApiKey.user_id == user_id,
                UserApiKey.provider == "openrouter",
            )
        )
        key_row = result.scalar_one_or_none()
        if key_row is None:
            return None
        return decrypt_token(key_row.encrypted_key)

    async def get_user_openrouter_key_for_embeddings(
        self,
        user: User,
        db: AsyncSession,
    ) -> str | None:
        return await self.get_user_openrouter_key_for_embeddings_by_id(user.id, db)

    async def get_user_openrouter_key_for_embeddings_by_id(
        self,
        user_id: UUID,
        db: AsyncSession,
    ) -> str | None:
        mode_result = await db.execute(
            select(UserLLMPreferences.openrouter_key_mode).where(
                UserLLMPreferences.user_id == user_id
            )
        )
        if mode_result.scalar_one_or_none() != "byok":
            return None
        return await self.get_user_openrouter_key_by_id(user_id, db)

    async def _resolve_api_key(
        self,
        user: User,
        db: AsyncSession,
        provider_priority: list[Provider],
        preferred_model: str | None = None,
        openrouter_key_mode: OpenRouterKeyMode = "app",
        feature_name: str = "general",
    ) -> ApiKeyResolution:
        """Internal method to resolve API key with given parameters.

        Args:
            user: The authenticated user
            db: Database session
            provider_priority: Order to check user's stored keys
            preferred_model: OpenRouter model selected by the user, if any
            openrouter_key_mode: Whether to use the app key or user's BYOK key

        Returns:
            ApiKeyResolution with provider, key, and optional model

        Raises:
            ApiKeyNotFoundError: If no provider is available
        """
        if openrouter_key_mode == "byok":
            user_key = await self.get_user_openrouter_key(user, db)
            if not user_key:
                logger.info(
                    "User %s selected BYOK mode for %s without an OpenRouter key",
                    user.id,
                    feature_name,
                )
                raise ApiKeyNotFoundError("openrouter")
            logger.info(
                "Using user-provided OpenRouter key for user %s",
                user.id,
            )
            return ApiKeyResolution(
                provider="openrouter",
                api_key=user_key,
                is_in_house=False,
                model=preferred_model,
            )

        if preferred_model in OPENROUTER_BYOK_MODEL_IDS:
            logger.info(
                "User %s selected BYOK-only OpenRouter model %s in app-key mode",
                user.id,
                preferred_model,
            )
            raise ApiKeyNotFoundError("openrouter")

        # App-key mode only allows app-sponsored OpenRouter models.
        if preferred_model:
            logger.info(
                "User %s selected in-house OpenRouter model %s for %s",
                user.id,
                preferred_model,
                feature_name,
            )
        else:
            logger.info("Using in-house OpenRouter key for user %s", user.id)

        for provider in self._PROVIDER_PRIORITY:
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
                    model=preferred_model,
                )

        raise ApiKeyNotFoundError(f"server has no {provider} API key configured")


# Singleton instance for use in routes
api_key_service = ApiKeyService()
