"""Unit tests for API key resolution and quota management service."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.api_key_service import ApiKeyService
from app.services.exceptions import ApiKeyNotFoundError


class TestProviderPriority:
    """Tests for _PROVIDER_PRIORITY configuration."""

    def test_openrouter_is_only_provider(self):
        svc = ApiKeyService()
        assert svc._PROVIDER_PRIORITY == ["openrouter"]


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
    async def test_app_mode_uses_in_house_key_even_when_user_key_exists(
        self, svc, mock_user, mock_db
    ):
        """App-key mode does not spend the user's OpenRouter key."""
        from app.core.security import encrypt_token

        mock_key_row = MagicMock()
        mock_key_row.provider = "openrouter"
        mock_key_row.encrypted_key = encrypt_token("user-own-key")
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_key_row
        mock_db.execute = AsyncMock(return_value=mock_result)

        with patch("app.services.api_key_service.settings") as mock_settings:
            mock_settings.OPENROUTER_API_KEY = "openrouter-key"

            result = await svc.resolve_for_chat(mock_user, mock_db)

        assert result.provider == "openrouter"
        assert result.api_key == "openrouter-key"
        assert result.is_in_house is True

    @pytest.mark.asyncio
    async def test_byok_mode_uses_user_openrouter_key(
        self, svc, mock_user, mock_db
    ):
        """BYOK mode uses the user's OpenRouter key for all models."""
        from app.core.security import encrypt_token

        mock_key_row = MagicMock()
        mock_key_row.provider = "openrouter"
        mock_key_row.encrypted_key = encrypt_token("user-own-key")
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_key_row
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await svc.resolve_for_chat(
            mock_user,
            mock_db,
            preferred_model="openrouter/owl-alpha",
            openrouter_key_mode="byok",
        )

        assert result.provider == "openrouter"
        assert result.api_key == "user-own-key"
        assert result.is_in_house is False
        assert result.model == "openrouter/owl-alpha"

    @pytest.mark.asyncio
    async def test_free_preferred_model_uses_in_house_key(self, svc, mock_user, mock_db):
        """Free/OpenRouter-owned model preferences do not require BYOK."""
        with patch("app.services.api_key_service.settings") as mock_settings:
            mock_settings.OPENROUTER_API_KEY = "openrouter-key"

            result = await svc.resolve_for_chat(
                mock_user,
                mock_db,
                preferred_model="openrouter/owl-alpha",
            )

        assert result.provider == "openrouter"
        assert result.api_key == "openrouter-key"
        assert result.is_in_house is True
        assert result.model == "openrouter/owl-alpha"

    @pytest.mark.asyncio
    async def test_byok_preferred_model_uses_user_openrouter_key(
        self, svc, mock_user, mock_db
    ):
        """BYOK-only model preferences use the user's OpenRouter key."""
        from app.core.security import encrypt_token

        mock_key_row = MagicMock()
        mock_key_row.provider = "openrouter"
        mock_key_row.encrypted_key = encrypt_token("user-openrouter-key")
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_key_row
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await svc.resolve_for_chat(
            mock_user,
            mock_db,
            preferred_model="anthropic/claude-fable-5",
            openrouter_key_mode="byok",
        )

        assert result.provider == "openrouter"
        assert result.api_key == "user-openrouter-key"
        assert result.is_in_house is False
        assert result.model == "anthropic/claude-fable-5"

    @pytest.mark.asyncio
    async def test_byok_preferred_model_without_user_key_raises(
        self, svc, mock_user, mock_db
    ):
        """BYOK-only model preferences are not allowed in app-key mode."""
        with pytest.raises(ApiKeyNotFoundError):
            await svc.resolve_for_chat(
                mock_user,
                mock_db,
                preferred_model="anthropic/claude-fable-5",
            )

    @pytest.mark.asyncio
    async def test_byok_mode_without_user_key_raises(
        self, svc, mock_user, mock_db
    ):
        """BYOK mode requires a stored OpenRouter key."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        with pytest.raises(ApiKeyNotFoundError):
            await svc.resolve_for_chat(
                mock_user,
                mock_db,
                openrouter_key_mode="byok",
            )

    @pytest.mark.asyncio
    async def test_no_openrouter_key_raises_not_found(self, svc, mock_user, mock_db):
        """When OPENROUTER_API_KEY is not set, should raise ApiKeyNotFoundError."""
        with patch("app.services.api_key_service.settings") as mock_settings:
            mock_settings.OPENROUTER_API_KEY = None

            with pytest.raises(ApiKeyNotFoundError):
                await svc.resolve_for_chat(mock_user, mock_db)
