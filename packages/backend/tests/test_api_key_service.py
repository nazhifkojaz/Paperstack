"""Unit tests for API key resolution and quota management service."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.api_key_service import ApiKeyService, Provider
from app.services.exceptions import ApiKeyNotFoundError, QuotaExhaustedError


class TestInHousePriority:
    """Tests for IN_HOUSE_PRIORITY configuration."""

    def test_openrouter_is_first(self):
        svc = ApiKeyService()
        assert svc.IN_HOUSE_PRIORITY[0] == "openrouter"

    def test_paid_providers_follow(self):
        svc = ApiKeyService()
        assert svc.IN_HOUSE_PRIORITY == ["openrouter", "gemini", "glm"]


class TestResolvePaidFallback:
    """Tests for resolve_paid_fallback method."""

    @pytest.fixture
    def svc(self):
        return ApiKeyService()

    @pytest.fixture
    def mock_user(self):
        user = MagicMock()
        user.id = "test-user-id"
        return user

    @pytest.fixture
    def mock_db(self):
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_returns_paid_provider_skipping_openrouter(self, svc, mock_user, mock_db):
        """resolve_paid_fallback should skip openrouter and return gemini."""
        mock_quota = MagicMock()
        mock_quota.chat_uses_remaining = 10

        with patch.object(svc, "_get_or_create_quota", new=AsyncMock(return_value=mock_quota)), \
             patch("app.services.api_key_service.settings") as mock_settings:
            mock_settings.GEMINI_API_KEY = "gemini-key"
            mock_settings.OPENROUTER_API_KEY = "openrouter-key"

            result = await svc.resolve_paid_fallback(
                mock_user, mock_db,
                quota_field="chat_uses_remaining",
                feature_priority=["openrouter", "gemini", "glm"],
            )

        assert result.provider == "gemini"
        assert result.api_key == "gemini-key"
        assert result.is_in_house is True

    @pytest.mark.asyncio
    async def test_raises_quota_exhausted_when_zero(self, svc, mock_user, mock_db):
        """resolve_paid_fallback should raise QuotaExhaustedError when quota is 0."""
        mock_quota = MagicMock()
        mock_quota.chat_uses_remaining = 0

        with patch.object(svc, "_get_or_create_quota", new=AsyncMock(return_value=mock_quota)):
            with pytest.raises(QuotaExhaustedError):
                await svc.resolve_paid_fallback(
                    mock_user, mock_db,
                    quota_field="chat_uses_remaining",
                    feature_priority=["openrouter", "gemini", "glm"],
                )

    @pytest.mark.asyncio
    async def test_raises_not_found_when_no_paid_keys(self, svc, mock_user, mock_db):
        """resolve_paid_fallback should raise ApiKeyNotFoundError when no paid keys configured."""
        mock_quota = MagicMock()
        mock_quota.chat_uses_remaining = 10

        with patch.object(svc, "_get_or_create_quota", new=AsyncMock(return_value=mock_quota)), \
             patch("app.services.api_key_service.settings") as mock_settings:
            mock_settings.GEMINI_API_KEY = None
            mock_settings.GLM_API_KEY = None

            with pytest.raises(ApiKeyNotFoundError):
                await svc.resolve_paid_fallback(
                    mock_user, mock_db,
                    quota_field="chat_uses_remaining",
                    feature_priority=["openrouter", "gemini", "glm"],
                )


class TestResolveApiKeyOpenRouter:
    """Tests for _resolve_api_key OpenRouter-specific behavior."""

    @pytest.fixture
    def svc(self):
        return ApiKeyService()

    @pytest.fixture
    def mock_user(self):
        user = MagicMock()
        user.id = "test-user-id"
        return user

    @pytest.fixture
    def mock_db(self):
        db = AsyncMock()
        # Default: no user keys stored
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        db.execute = AsyncMock(return_value=mock_result)
        return db

    @pytest.mark.asyncio
    async def test_user_own_key_takes_priority_over_openrouter(self, svc, mock_user, mock_db):
        """When user has their own key, it should be returned instead of OpenRouter."""
        from app.db.models import UserApiKey
        from app.core.security import encrypt_token

        # Simulate a user-stored API key
        mock_key_row = MagicMock()
        mock_key_row.provider = "openai"
        mock_key_row.encrypted_key = encrypt_token("user-own-key")
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_key_row]
        mock_db.execute = AsyncMock(return_value=mock_result)

        with patch("app.services.api_key_service.settings") as mock_settings:
            mock_settings.OPENROUTER_API_KEY = "openrouter-key"

            result = await svc._resolve_api_key(
                mock_user, mock_db,
                quota_field="chat_uses_remaining",
                provider_priority=["openai", "anthropic", "gemini", "glm"],
            )

        assert result.provider == "openai"
        assert result.is_in_house is False

    @pytest.mark.asyncio
    async def test_no_openrouter_key_returns_gemini(self, svc, mock_user, mock_db):
        """When OPENROUTER_API_KEY is not set, should return Gemini/GLM instead."""
        mock_quota = MagicMock()
        mock_quota.chat_uses_remaining = 10

        with patch.object(svc, "_get_or_create_quota", new=AsyncMock(return_value=mock_quota)), \
             patch("app.services.api_key_service.settings") as mock_settings:
            mock_settings.OPENROUTER_API_KEY = None
            mock_settings.GEMINI_API_KEY = "gemini-key"

            result = await svc._resolve_api_key(
                mock_user, mock_db,
                quota_field="chat_uses_remaining",
                provider_priority=["openrouter", "gemini", "glm"],
            )

        assert result.provider == "gemini"
        assert result.api_key == "gemini-key"
        assert result.is_in_house is True
