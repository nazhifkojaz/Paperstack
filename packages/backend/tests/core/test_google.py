"""Tests for the Google OAuth helper functions."""

import pytest
import respx
from httpx import Response
from unittest.mock import patch

from app.core.google import get_google_tokens, get_google_user, _redirect_uri


class TestRedirectUri:

    def test_redirect_uri_format(self):
        uri = _redirect_uri()
        assert "google/callback" in uri
        assert uri.startswith("http")


class TestGetGoogleTokens:

    async def test_success(self):
        with respx.mock as mock:
            mock.post("https://oauth2.googleapis.com/token").mock(
                return_value=Response(
                    200,
                    json={
                        "access_token": "google-access-token",
                        "refresh_token": "google-refresh-token",
                        "expires_in": 3600,
                        "token_type": "Bearer",
                    },
                )
            )

            result = await get_google_tokens("auth-code-123")

        assert result is not None
        assert result["access_token"] == "google-access-token"
        assert result["refresh_token"] == "google-refresh-token"
        assert result["expires_in"] == 3600

    async def test_failure(self):
        with respx.mock as mock:
            mock.post("https://oauth2.googleapis.com/token").mock(
                return_value=Response(400, text="invalid_grant")
            )

            result = await get_google_tokens("bad-code")

        assert result is None


class TestGetGoogleUser:

    async def test_success(self):
        with respx.mock as mock:
            mock.get("https://openidconnect.googleapis.com/v1/userinfo").mock(
                return_value=Response(
                    200,
                    json={
                        "sub": "google-sub-123",
                        "email": "test@gmail.com",
                        "name": "Test User",
                        "picture": "https://example.com/photo.jpg",
                    },
                )
            )

            result = await get_google_user("valid-token")

        assert result is not None
        assert result["sub"] == "google-sub-123"
        assert result["email"] == "test@gmail.com"

    async def test_failure_invalid_token(self):
        with respx.mock as mock:
            mock.get("https://openidconnect.googleapis.com/v1/userinfo").mock(
                return_value=Response(401, text="invalid_token")
            )

            result = await get_google_user("bad-token")

        assert result is None


class TestRefreshGoogleToken:

    async def test_success(self):
        from app.core.google import refresh_google_token

        with patch(
            "app.core.google.decrypt_token", return_value="decrypted-refresh-token"
        ):
            with respx.mock as mock:
                mock.post("https://oauth2.googleapis.com/token").mock(
                    return_value=Response(
                        200,
                        json={
                            "access_token": "new-access-token",
                            "expires_in": 3600,
                            "token_type": "Bearer",
                        },
                    )
                )

                access_token, expires_at = await refresh_google_token(
                    "encrypted-refresh-token"
                )

        assert access_token == "new-access-token"
        assert expires_at is not None

    async def test_failure(self):
        from app.core.google import refresh_google_token

        with patch(
            "app.core.google.decrypt_token", return_value="decrypted-refresh-token"
        ):
            with respx.mock as mock:
                mock.post("https://oauth2.googleapis.com/token").mock(
                    return_value=Response(400, text="invalid_grant")
                )

                with pytest.raises(Exception):
                    await refresh_google_token("encrypted-refresh-token")
