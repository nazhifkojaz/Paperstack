"""Factory for resolving the correct StorageBackend for a given user."""

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User, UserOAuthAccount
from app.services.storage.base import StorageBackend
from app.services.storage.github_storage import GitHubStorageBackend
from app.services.storage.google_drive_storage import GoogleDriveStorageBackend


async def get_storage_backend(user: User, db: AsyncSession) -> StorageBackend:
    """Resolve the correct StorageBackend for the user's active storage provider.

    Raises:
        HTTPException 400: If no OAuth account exists for the user's storage provider.
        HTTPException 400: If the provider is unknown.
    """
    stmt = select(UserOAuthAccount).where(
        UserOAuthAccount.user_id == user.id,
        UserOAuthAccount.provider == user.storage_provider,
    )
    result = await db.execute(stmt)
    oauth_account = result.scalar_one_or_none()

    if not oauth_account:
        raise HTTPException(
            status_code=400,
            detail=f"No {user.storage_provider} account linked. Please reconnect via Settings.",
        )

    if user.storage_provider == "github":
        github_login = (oauth_account.extra_data or {}).get("github_login")
        if not github_login:
            raise HTTPException(
                status_code=400,
                detail="GitHub account is missing login info. Please reconnect.",
            )
        return GitHubStorageBackend(
            encrypted_access_token=oauth_account.encrypted_access_token,
            github_login=github_login,
        )

    if user.storage_provider == "google":
        return GoogleDriveStorageBackend(oauth_account=oauth_account, db=db)

    raise HTTPException(status_code=400, detail=f"Unknown storage provider: {user.storage_provider}")
