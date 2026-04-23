from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_current_user
from app.db.models import User, UserOAuthAccount, UserLLMPreferences
from app.schemas.auth import UserResponse
from app.services.llm_service import FREE_MODELS

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


# --- LLM model preferences ---


class LLMModelResponse(BaseModel):
    id: str
    label: str
    description: str


class LLMModelsListResponse(BaseModel):
    models: List[LLMModelResponse]


class LLMPreferencesResponse(BaseModel):
    chat_model: Optional[str] = None
    auto_highlight_model: Optional[str] = None
    explain_model: Optional[str] = None


class LLMPreferencesUpdate(BaseModel):
    chat_model: Optional[str] = None
    auto_highlight_model: Optional[str] = None
    explain_model: Optional[str] = None


VALID_MODEL_IDS = {m["id"] for m in FREE_MODELS}


def _validate_model(value: Optional[str], field: str) -> None:
    if value is not None and value not in VALID_MODEL_IDS:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid model for {field}: {value}. Must be one of: {', '.join(sorted(VALID_MODEL_IDS))}",
        )


async def _get_or_create_prefs(
    user_id, db: AsyncSession
) -> UserLLMPreferences:
    result = await db.execute(
        select(UserLLMPreferences).where(UserLLMPreferences.user_id == user_id)
    )
    prefs = result.scalar_one_or_none()
    if prefs is None:
        prefs = UserLLMPreferences(user_id=user_id)
        db.add(prefs)
        await db.flush()
    return prefs


@router.get("/llm-models", response_model=LLMModelsListResponse)
async def get_llm_models():
    """Return the curated list of available free-tier LLM models."""
    return LLMModelsListResponse(
        models=[LLMModelResponse(**m) for m in FREE_MODELS]
    )


@router.get("/llm-preferences", response_model=LLMPreferencesResponse)
async def get_llm_preferences(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return the user's current LLM model preferences per feature."""
    prefs = await _get_or_create_prefs(current_user.id, db)
    return LLMPreferencesResponse(
        chat_model=prefs.chat_model,
        auto_highlight_model=prefs.auto_highlight_model,
        explain_model=prefs.explain_model,
    )


@router.patch("/llm-preferences", response_model=LLMPreferencesResponse)
async def update_llm_preferences(
    data: LLMPreferencesUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update the user's LLM model preferences. Null = use default provider resolution.

    Only fields present in the request body are updated. To reset a field
    to "auto" (default provider resolution), send it as null.
    """
    updates = data.model_dump(exclude_unset=True)
    for field, value in updates.items():
        _validate_model(value, field)

    prefs = await _get_or_create_prefs(current_user.id, db)

    for field, value in updates.items():
        setattr(prefs, field, value)

    await db.commit()
    await db.refresh(prefs)

    return LLMPreferencesResponse(
        chat_model=prefs.chat_model,
        auto_highlight_model=prefs.auto_highlight_model,
        explain_model=prefs.explain_model,
    )
