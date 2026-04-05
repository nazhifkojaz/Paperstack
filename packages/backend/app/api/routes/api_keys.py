from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert

from app.api.deps import get_db, get_current_user
from app.core.security import encrypt_token, decrypt_token
from app.db.models import User, UserApiKey, UserOAuthAccount
from app.schemas.api_key import ApiKeyCreate, ApiKeyResponse
from app.schemas.auth import UserResponse
from app.middleware.rate_limit import limiter
from app.core.config import settings

router = APIRouter()


def mask_key(key: str) -> str:
    """Mask API key for display: show last 4 chars only."""
    if len(key) <= 4:
        return "••••"
    return "••••" + key[-4:]


@router.post("/api-keys", response_model=ApiKeyResponse)
@limiter.limit(settings.RATE_LIMIT_API_KEYS)
async def create_api_key(
    request: Request,
    data: ApiKeyCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Store an encrypted API key. Upserts if provider key already exists."""
    encrypted = encrypt_token(data.api_key)

    # Upsert: insert or update on conflict
    stmt = insert(UserApiKey).values(
        user_id=current_user.id,
        provider=data.provider,
        encrypted_key=encrypted,
    ).on_conflict_do_update(
        constraint="uq_user_api_keys_user_provider",
        set_={"encrypted_key": encrypted},
    ).returning(UserApiKey)

    result = await db.execute(stmt)
    await db.commit()
    key_row = result.scalars().first()

    return ApiKeyResponse(
        provider=data.provider,
        key_preview=mask_key(data.api_key),
        created_at=key_row.created_at,
    )


@router.delete("/api-keys/{provider}", status_code=204)
async def delete_api_key(
    provider: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Remove a stored API key."""
    result = await db.execute(
        delete(UserApiKey).where(
            UserApiKey.user_id == current_user.id,
            UserApiKey.provider == provider,
        )
    )
    await db.commit()

    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="API key not found")


class StorageProviderUpdate(BaseModel):
    storage_provider: str


@router.patch("/storage-provider", response_model=UserResponse)
async def update_storage_provider(
    data: StorageProviderUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Switch the active storage backend for the current user.

    Validates that the user has a connected OAuth account for the requested
    provider before updating the preference.
    """
    if data.storage_provider not in ("github", "google"):
        raise HTTPException(status_code=400, detail="Invalid storage provider. Must be 'github' or 'google'.")

    result = await db.execute(
        select(UserOAuthAccount).where(
            UserOAuthAccount.user_id == current_user.id,
            UserOAuthAccount.provider == data.storage_provider,
        )
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=400,
            detail=f"No {data.storage_provider} account connected. Please log in with {data.storage_provider} first.",
        )

    current_user.storage_provider = data.storage_provider
    db.add(current_user)
    await db.commit()
    await db.refresh(current_user)
    return current_user
