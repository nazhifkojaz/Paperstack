from typing import List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_current_user
from app.db.models import User, UserOAuthAccount
from app.schemas.auth import UserResponse

router = APIRouter()

PROVIDER_LABELS = {"github": "GitHub", "google": "Google Drive"}


class StorageProviderUpdate(BaseModel):
    storage_provider: str


class ConnectedAccount(BaseModel):
    provider: str
    display_name: str


class ConnectedAccountsResponse(BaseModel):
    accounts: List[ConnectedAccount]


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


@router.get("/connected-accounts", response_model=ConnectedAccountsResponse)
async def get_connected_accounts(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return the list of OAuth providers the user has linked."""
    result = await db.execute(
        select(UserOAuthAccount.provider).where(
            UserOAuthAccount.user_id == current_user.id,
        )
    )
    providers = [row[0] for row in result.all()]

    return ConnectedAccountsResponse(
        accounts=[
            ConnectedAccount(
                provider=p,
                display_name=PROVIDER_LABELS.get(p, p),
            )
            for p in providers
        ]
    )
