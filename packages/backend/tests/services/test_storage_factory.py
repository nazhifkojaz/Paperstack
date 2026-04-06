"""Tests for the storage backend factory."""
import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import security
from app.db.models import User, UserOAuthAccount
from app.services.storage.factory import get_storage_backend
from app.services.storage.github_storage import GitHubStorageBackend
from app.services.storage.google_drive_storage import GoogleDriveStorageBackend


class TestGetStorageBackend:
    """Tests for get_storage_backend factory function."""

    async def test_resolves_github(
        self, db_session: AsyncSession, test_user: User
    ) -> None:
        """Returns GitHubStorageBackend when storage_provider is 'github'."""
        # test_user fixture already has a github OAuth account
        test_user.storage_provider = "github"
        await db_session.commit()

        backend = await get_storage_backend(test_user, db_session)
        assert isinstance(backend, GitHubStorageBackend)

    async def test_resolves_google(
        self, db_session: AsyncSession, test_user: User
    ) -> None:
        """Returns GoogleDriveStorageBackend when storage_provider is 'google'."""
        test_user.storage_provider = "google"
        oauth = UserOAuthAccount(
            user_id=test_user.id,
            provider="google",
            provider_user_id="google-sub-unique-456",
            encrypted_access_token=security.encrypt_token("google_token"),
        )
        db_session.add(oauth)
        await db_session.commit()

        backend = await get_storage_backend(test_user, db_session)
        assert isinstance(backend, GoogleDriveStorageBackend)

    async def test_errors_on_missing_oauth_account(
        self, db_session: AsyncSession, test_user: User
    ) -> None:
        """Raises 400 when no OAuth account exists for the storage provider."""
        test_user.storage_provider = "google"
        # test_user fixture only has github OAuth, not google

        with pytest.raises(HTTPException) as exc_info:
            await get_storage_backend(test_user, db_session)
        assert exc_info.value.status_code == 400
        assert "No google account linked" in str(exc_info.value.detail)

    async def test_errors_on_unknown_provider(
        self, db_session: AsyncSession, test_user: User
    ) -> None:
        """Raises 400 for an unsupported storage provider."""
        test_user.storage_provider = "dropbox"
        oauth = UserOAuthAccount(
            user_id=test_user.id,
            provider="dropbox",
            provider_user_id="dropbox-unique-789",
            encrypted_access_token=security.encrypt_token("db_token"),
        )
        db_session.add(oauth)
        await db_session.commit()

        with pytest.raises(HTTPException) as exc_info:
            await get_storage_backend(test_user, db_session)
        assert exc_info.value.status_code == 400
        assert "Unknown storage provider" in str(exc_info.value.detail)

    async def test_errors_on_missing_github_login(
        self, db_session: AsyncSession, test_user: User
    ) -> None:
        """Raises 400 when GitHub OAuth account is missing github_login in extra_data."""
        test_user.storage_provider = "github"
        # Update the existing github OAuth account to remove github_login
        from sqlalchemy import select, update

        await db_session.execute(
            update(UserOAuthAccount)
            .where(
                UserOAuthAccount.user_id == test_user.id,
                UserOAuthAccount.provider == "github",
            )
            .values(extra_data={})
        )
        await db_session.commit()

        with pytest.raises(HTTPException) as exc_info:
            await get_storage_backend(test_user, db_session)
        assert exc_info.value.status_code == 400
        assert "missing login info" in str(exc_info.value.detail)
