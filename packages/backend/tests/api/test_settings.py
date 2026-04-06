"""Tests for the settings routes."""
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import security
from app.db.models import User, UserOAuthAccount


class TestGetConnectedAccounts:
    """Tests for GET /settings/connected-accounts"""

    async def test_returns_linked_providers(
        self, client: AsyncClient, auth_headers: dict, db_session: AsyncSession, test_user: User
    ) -> None:
        """Returns providers the user has linked via OAuth."""
        oauth = UserOAuthAccount(
            user_id=test_user.id,
            provider="github",
            provider_user_id="123456",
            encrypted_access_token=security.encrypt_token("gh_token"),
            extra_data={"github_login": "testuser"},
        )
        db_session.add(oauth)
        await db_session.commit()

        resp = await client.get("/v1/settings/connected-accounts", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "accounts" in data
        provider_ids = [a["provider"] for a in data["accounts"]]
        assert "github" in provider_ids

    async def test_returns_empty_when_no_accounts(
        self, client: AsyncClient, auth_headers: dict
    ) -> None:
        """Returns empty list when user has no OAuth accounts."""
        resp = await client.get("/v1/settings/connected-accounts", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["accounts"] == []

    async def test_returns_multiple_providers(
        self, client: AsyncClient, auth_headers: dict, db_session: AsyncSession, test_user: User
    ) -> None:
        """Returns all linked providers when user has multiple OAuth accounts."""
        for provider, uid in [("github", "123456"), ("google", "google-sub-123")]:
            oauth = UserOAuthAccount(
                user_id=test_user.id,
                provider=provider,
                provider_user_id=uid,
                encrypted_access_token=security.encrypt_token(f"{provider}_token"),
            )
            db_session.add(oauth)
        await db_session.commit()

        resp = await client.get("/v1/settings/connected-accounts", headers=auth_headers)
        assert resp.status_code == 200
        provider_ids = [a["provider"] for a in resp.json()["accounts"]]
        assert "github" in provider_ids
        assert "google" in provider_ids

    async def test_includes_display_name(
        self, client: AsyncClient, auth_headers: dict, db_session: AsyncSession, test_user: User
    ) -> None:
        """Each account includes a human-readable display_name."""
        for provider, uid in [("github", "123456"), ("google", "google-sub-123")]:
            oauth = UserOAuthAccount(
                user_id=test_user.id,
                provider=provider,
                provider_user_id=uid,
                encrypted_access_token=security.encrypt_token(f"{provider}_token"),
            )
            db_session.add(oauth)
        await db_session.commit()

        resp = await client.get("/v1/settings/connected-accounts", headers=auth_headers)
        accounts = resp.json()["accounts"]
        github = next(a for a in accounts if a["provider"] == "github")
        google = next(a for a in accounts if a["provider"] == "google")
        assert github["display_name"] == "GitHub"
        assert google["display_name"] == "Google Drive"

    async def test_requires_auth(self, client: AsyncClient) -> None:
        """Returns 401 without authentication."""
        resp = await client.get("/v1/settings/connected-accounts")
        assert resp.status_code == 401


class TestUpdateStorageProvider:
    """Tests for PATCH /settings/storage-provider"""

    async def test_switch_to_linked_provider(
        self, client: AsyncClient, auth_headers: dict, db_session: AsyncSession, test_user: User
    ) -> None:
        """Switches storage provider when user has a matching OAuth account."""
        oauth = UserOAuthAccount(
            user_id=test_user.id,
            provider="github",
            provider_user_id="123456",
            encrypted_access_token=security.encrypt_token("gh_token"),
            extra_data={"github_login": "testuser"},
        )
        db_session.add(oauth)
        await db_session.commit()

        resp = await client.patch(
            "/v1/settings/storage-provider",
            json={"storage_provider": "github"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["storage_provider"] == "github"

        # Verify DB was updated
        await db_session.refresh(test_user)
        assert test_user.storage_provider == "github"

    async def test_rejects_unlinked_provider(
        self, client: AsyncClient, auth_headers: dict, db_session: AsyncSession, test_user: User
    ) -> None:
        """Returns 400 when switching to a provider with no OAuth account."""
        # Only github linked, try to switch to google
        oauth = UserOAuthAccount(
            user_id=test_user.id,
            provider="github",
            provider_user_id="123456",
            encrypted_access_token=security.encrypt_token("gh_token"),
        )
        db_session.add(oauth)
        await db_session.commit()

        resp = await client.patch(
            "/v1/settings/storage-provider",
            json={"storage_provider": "google"},
            headers=auth_headers,
        )
        assert resp.status_code == 400
        assert "No google account connected" in resp.json()["detail"]

    async def test_rejects_invalid_provider(
        self, client: AsyncClient, auth_headers: dict
    ) -> None:
        """Returns 400 for unsupported provider values."""
        resp = await client.patch(
            "/v1/settings/storage-provider",
            json={"storage_provider": "dropbox"},
            headers=auth_headers,
        )
        assert resp.status_code == 400
        assert "Invalid storage provider" in resp.json()["detail"]

    async def test_requires_auth(self, client: AsyncClient) -> None:
        """Returns 401 without authentication."""
        resp = await client.patch(
            "/v1/settings/storage-provider",
            json={"storage_provider": "github"},
        )
        assert resp.status_code == 401

    async def test_switch_between_linked_providers(
        self, client: AsyncClient, auth_headers: dict, db_session: AsyncSession, test_user: User
    ) -> None:
        """Switches from github to google when both are linked."""
        for provider, uid in [("github", "123456"), ("google", "google-sub-123")]:
            oauth = UserOAuthAccount(
                user_id=test_user.id,
                provider=provider,
                provider_user_id=uid,
                encrypted_access_token=security.encrypt_token(f"{provider}_token"),
            )
            db_session.add(oauth)
        await db_session.commit()

        # Default is github, switch to google
        assert test_user.storage_provider == "github"
        resp = await client.patch(
            "/v1/settings/storage-provider",
            json={"storage_provider": "google"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["storage_provider"] == "google"

        # Verify DB was updated
        await db_session.refresh(test_user)
        assert test_user.storage_provider == "google"
