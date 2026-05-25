"""Tests for the Google OAuth helper functions."""

import pytest
import respx
from httpx import Response
from unittest.mock import patch

from app.core.google import (
    get_google_tokens,
    get_google_user,
    _redirect_uri,
    ensure_drive_folder,
    upload_to_drive,
    download_from_drive,
    download_from_drive_to_tempfile,
    delete_from_drive,
)


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


# ---------------------------------------------------------------------------
# Drive helpers
# ---------------------------------------------------------------------------


class TestEnsureDriveFolder:

    async def test_existing_folder_returned(self):
        with respx.mock as mock:
            mock.get("https://www.googleapis.com/drive/v3/files").mock(
                return_value=Response(
                    200,
                    json={"files": [{"id": "existing-folder-id", "name": "Paperstack"}]},
                )
            )

            result = await ensure_drive_folder("valid-token")

        assert result == "existing-folder-id"

    async def test_creates_folder_when_missing(self):
        with respx.mock as mock:
            mock.get("https://www.googleapis.com/drive/v3/files").mock(
                return_value=Response(200, json={"files": []})
            )
            mock.post("https://www.googleapis.com/drive/v3/files").mock(
                return_value=Response(200, json={"id": "new-folder-id"})
            )

            result = await ensure_drive_folder("valid-token")

        assert result == "new-folder-id"


class TestUploadToDrive:

    async def test_upload_returns_file_id(self):
        test_bytes = b"fake pdf content"

        with respx.mock as mock:
            mock.post("https://www.googleapis.com/upload/drive/v3/files").mock(
                return_value=Response(200, json={"id": "uploaded-file-id"})
            )

            result = await upload_to_drive(
                "valid-token", "folder-id", "test.pdf", test_bytes
            )

        assert result == "uploaded-file-id"


class TestDownloadFromDrive:

    async def test_download_returns_bytes(self):
        test_content = b"downloaded file content"

        with respx.mock as mock:
            mock.get("https://www.googleapis.com/drive/v3/files/file-123").mock(
                return_value=Response(200, content=test_content)
            )

            result = await download_from_drive("valid-token", "file-123")

        assert result == test_content


class TestDownloadFromDriveToTempfile:

    async def test_download_streams_to_tempfile(self):
        test_content = b"streamed file content"

        with respx.mock as mock:
            mock.get("https://www.googleapis.com/drive/v3/files/file-456").mock(
                return_value=Response(200, content=test_content)
            )

            tmp_path = await download_from_drive_to_tempfile("valid-token", "file-456")

        try:
            assert tmp_path.exists()
            assert tmp_path.read_bytes() == test_content
        finally:
            tmp_path.unlink(missing_ok=True)


class TestDeleteFromDrive:

    async def test_delete_204_succeeds(self):
        with respx.mock as mock:
            mock.delete("https://www.googleapis.com/drive/v3/files/file-789").mock(
                return_value=Response(204)
            )

            await delete_from_drive("valid-token", "file-789")

    async def test_delete_non_success_raises(self):
        with respx.mock as mock:
            mock.delete("https://www.googleapis.com/drive/v3/files/file-789").mock(
                return_value=Response(404)
            )

            with pytest.raises(Exception):
                await delete_from_drive("valid-token", "file-789")
