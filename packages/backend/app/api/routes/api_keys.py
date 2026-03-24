from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert

from app.api.deps import get_db, get_current_user
from app.core.security import encrypt_token, decrypt_token
from app.db.models import User, UserApiKey
from app.schemas.api_key import ApiKeyCreate, ApiKeyResponse
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
