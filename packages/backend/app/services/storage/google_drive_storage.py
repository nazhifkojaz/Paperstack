"""Google Drive storage backend with automatic token refresh."""

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import google, security
from app.db.models import UserOAuthAccount
from app.services.storage.base import StorageBackend, UploadResult

logger = logging.getLogger(__name__)

# Refresh the token when it has fewer than 60 seconds remaining
_REFRESH_BUFFER_SECONDS = 60


class GoogleDriveStorageBackend(StorageBackend):
    """Stores PDFs in the user's Google Drive inside a 'Paperstack' folder.

    Handles token refresh transparently before each API call.
    """

    def __init__(self, oauth_account: UserOAuthAccount, db: AsyncSession) -> None:
        self._account = oauth_account
        self._db = db

    async def _get_valid_token(self) -> str:
        """Return a valid plaintext access token, refreshing from DB if needed."""
        now = datetime.now(timezone.utc)
        expires_at = self._account.token_expires_at

        needs_refresh = (
            expires_at is None
            or expires_at <= now + timedelta(seconds=_REFRESH_BUFFER_SECONDS)
        )

        if needs_refresh:
            if not self._account.encrypted_refresh_token:
                raise HTTPException(
                    status_code=401,
                    detail="Google session expired. Please reconnect your Google account.",
                )
            logger.info("Refreshing Google access token for account %s", self._account.id)
            new_token, new_expires_at = await google.refresh_google_token(
                self._account.encrypted_refresh_token
            )
            self._account.encrypted_access_token = security.encrypt_token(new_token)
            self._account.token_expires_at = new_expires_at
            self._db.add(self._account)
            await self._db.commit()
            return new_token

        return security.decrypt_token(self._account.encrypted_access_token)

    async def _get_folder_id(self) -> str:
        """Get the cached Drive folder ID, creating the folder if needed."""
        extra = self._account.extra_data or {}
        folder_id = extra.get("drive_folder_id")
        if folder_id:
            return folder_id

        token = await self._get_valid_token()
        folder_id = await google.ensure_drive_folder(token)

        self._account.extra_data = {**extra, "drive_folder_id": folder_id}
        self._db.add(self._account)
        await self._db.commit()
        return folder_id

    async def ensure_container(self) -> None:
        await self._get_folder_id()

    async def upload(self, filename: str, file_bytes: bytes, title: str) -> UploadResult:
        token = await self._get_valid_token()
        folder_id = await self._get_folder_id()
        file_id = await google.upload_to_drive(token, folder_id, filename, file_bytes)
        return UploadResult(file_id=file_id, provider="google")

    async def download_bytes(self, file_id: str, filename: str) -> bytes:
        token = await self._get_valid_token()
        return await google.download_from_drive(token, file_id)

    async def download_to_tempfile(self, file_id: str, filename: str) -> Path:
        token = await self._get_valid_token()
        return await google.download_from_drive_to_tempfile(token, file_id)

    async def delete(self, file_id: str, filename: str) -> None:
        token = await self._get_valid_token()
        await google.delete_from_drive(token, file_id)
