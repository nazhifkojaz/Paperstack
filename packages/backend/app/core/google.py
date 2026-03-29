"""Google OAuth helpers — token exchange, user info, and token refresh."""

import json
import logging
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import httpx

from app.core.config import settings
from app.core.security import decrypt_token

logger = logging.getLogger(__name__)

GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"
DRIVE_API = "https://www.googleapis.com/drive/v3"
DRIVE_UPLOAD_API = "https://www.googleapis.com/upload/drive/v3"
PAPERSTACK_FOLDER_NAME = "Paperstack"
CHUNK_SIZE = 8192  # 8 KB streaming chunks


def _redirect_uri() -> str:
    return f"{settings.BACKEND_URL}/v1/auth/google/callback"


async def get_google_tokens(code: str) -> Optional[Dict[str, Any]]:
    """Exchange an authorization code for Google access + refresh tokens.

    Returns a dict with 'access_token', 'refresh_token', 'expires_in', or None on failure.
    """
    async with httpx.AsyncClient() as client:
        response = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "redirect_uri": _redirect_uri(),
                "grant_type": "authorization_code",
            },
        )
        if response.status_code != 200:
            logger.error("Google token exchange failed: %s", response.text)
            return None
        return response.json()


async def get_google_user(access_token: str) -> Optional[Dict[str, Any]]:
    """Fetch Google user profile using an access token.

    Returns a dict with 'sub', 'email', 'name', 'picture', or None on failure.
    """
    async with httpx.AsyncClient() as client:
        response = await client.get(
            GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if response.status_code != 200:
            logger.error("Google userinfo fetch failed: %s", response.text)
            return None
        return response.json()


async def refresh_google_token(encrypted_refresh_token: str) -> Tuple[str, datetime]:
    """Use a stored refresh token to obtain a new access token.

    Args:
        encrypted_refresh_token: Fernet-encrypted refresh token from the DB.

    Returns:
        (plaintext_access_token, token_expires_at)

    Raises:
        httpx.HTTPError: If the refresh request fails.
    """
    refresh_token = decrypt_token(encrypted_refresh_token)
    async with httpx.AsyncClient() as client:
        response = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
        )
        response.raise_for_status()
        data = response.json()

    expires_in = data.get("expires_in", 3600)
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
    return data["access_token"], expires_at


async def ensure_drive_folder(access_token: str) -> str:
    """Get or create the 'Paperstack' folder in the user's Google Drive.

    Uses drive.file scope — only sees files created by this app.
    Returns the folder ID.
    """
    async with httpx.AsyncClient() as client:
        headers = {"Authorization": f"Bearer {access_token}"}

        # Search for existing Paperstack folder
        query = f"name='{PAPERSTACK_FOLDER_NAME}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
        resp = await client.get(
            f"{DRIVE_API}/files",
            headers=headers,
            params={"q": query, "fields": "files(id,name)", "spaces": "drive"},
        )
        resp.raise_for_status()
        files = resp.json().get("files", [])
        if files:
            return files[0]["id"]

        # Create the folder
        create_resp = await client.post(
            f"{DRIVE_API}/files",
            headers={**headers, "Content-Type": "application/json"},
            content=json.dumps({
                "name": PAPERSTACK_FOLDER_NAME,
                "mimeType": "application/vnd.google-apps.folder",
            }),
        )
        create_resp.raise_for_status()
        return create_resp.json()["id"]


async def upload_to_drive(
    access_token: str,
    folder_id: str,
    filename: str,
    file_bytes: bytes,
) -> str:
    """Upload a PDF to Google Drive inside the Paperstack folder.

    Uses multipart upload for files of any size.
    Returns the Drive file ID.
    """
    metadata = json.dumps({
        "name": filename,
        "parents": [folder_id],
    }).encode()

    boundary = "paperstack_boundary_abc123"
    body = (
        f"--{boundary}\r\n"
        f"Content-Type: application/json; charset=UTF-8\r\n\r\n"
    ).encode() + metadata + (
        f"\r\n--{boundary}\r\n"
        f"Content-Type: application/pdf\r\n\r\n"
    ).encode() + file_bytes + f"\r\n--{boundary}--".encode()

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{DRIVE_UPLOAD_API}/files",
            params={"uploadType": "multipart", "fields": "id"},
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": f"multipart/related; boundary={boundary}",
            },
            content=body,
        )
        resp.raise_for_status()
        return resp.json()["id"]


async def download_from_drive(access_token: str, file_id: str) -> bytes:
    """Download a file from Google Drive as bytes."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{DRIVE_API}/files/{file_id}",
            params={"alt": "media"},
            headers={"Authorization": f"Bearer {access_token}"},
        )
        resp.raise_for_status()
        return resp.content


async def download_from_drive_to_tempfile(access_token: str, file_id: str) -> Path:
    """Stream a file from Google Drive into a temporary file.

    Returns the path to the temp file. Caller is responsible for deletion.
    """
    async with httpx.AsyncClient() as client:
        async with client.stream(
            "GET",
            f"{DRIVE_API}/files/{file_id}",
            params={"alt": "media"},
            headers={"Authorization": f"Bearer {access_token}"},
        ) as response:
            response.raise_for_status()

            tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
            try:
                async for chunk in response.aiter_bytes(chunk_size=CHUNK_SIZE):
                    tmp.write(chunk)
                tmp.close()
                return Path(tmp.name)
            except Exception:
                tmp.close()
                Path(tmp.name).unlink(missing_ok=True)
                raise


async def delete_from_drive(access_token: str, file_id: str) -> None:
    """Permanently delete a file from Google Drive."""
    async with httpx.AsyncClient() as client:
        resp = await client.delete(
            f"{DRIVE_API}/files/{file_id}",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if resp.status_code not in (200, 204):
            logger.error("Google Drive delete failed for %s: %s", file_id, resp.text)
            resp.raise_for_status()
