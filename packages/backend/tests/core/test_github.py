"""Tests for the GitHub OAuth helper functions."""

import respx
from httpx import Response

from app.core.github import get_github_access_token, get_github_user, get_github_emails


class TestGetGithubAccessToken:

    async def test_success(self):
        with respx.mock as mock:
            mock.post("https://github.com/login/oauth/access_token").mock(
                return_value=Response(
                    200,
                    json={
                        "access_token": "gh_access_token_123",
                        "token_type": "bearer",
                        "scope": "user",
                    },
                )
            )

            result = await get_github_access_token("auth-code")

        assert result == "gh_access_token_123"

    async def test_failure(self):
        with respx.mock as mock:
            mock.post("https://github.com/login/oauth/access_token").mock(
                return_value=Response(400, text="bad_verification_code")
            )

            result = await get_github_access_token("bad-code")

        assert result is None


class TestGetGithubUser:

    async def test_success(self):
        with respx.mock as mock:
            mock.get("https://api.github.com/user").mock(
                return_value=Response(
                    200,
                    json={
                        "id": 123456,
                        "login": "testuser",
                        "name": "Test User",
                        "avatar_url": "https://avatars.githubusercontent.com/u/123456",
                    },
                )
            )

            result = await get_github_user("valid-token")

        assert result is not None
        assert result["login"] == "testuser"
        assert result["id"] == 123456

    async def test_failure(self):
        with respx.mock as mock:
            mock.get("https://api.github.com/user").mock(
                return_value=Response(401, text="Bad credentials")
            )

            result = await get_github_user("bad-token")

        assert result is None


class TestGetGithubEmails:

    async def test_returns_primary_verified_email(self):
        with respx.mock as mock:
            mock.get("https://api.github.com/user/emails").mock(
                return_value=Response(
                    200,
                    json=[
                        {"email": "test@example.com", "primary": True, "verified": True},
                        {"email": "old@example.com", "primary": False, "verified": True},
                    ],
                )
            )

            result = await get_github_emails("valid-token")

        assert result == "test@example.com"

    async def test_no_primary_verified_returns_none(self):
        with respx.mock as mock:
            mock.get("https://api.github.com/user/emails").mock(
                return_value=Response(
                    200,
                    json=[
                        {"email": "test@example.com", "primary": False, "verified": True},
                    ],
                )
            )

            result = await get_github_emails("valid-token")

        assert result is None

    async def test_failure_returns_none(self):
        with respx.mock as mock:
            mock.get("https://api.github.com/user/emails").mock(
                return_value=Response(401, text="Unauthorized")
            )

            result = await get_github_emails("bad-token")

        assert result is None
