import uuid
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_current_user
from app.constants.colors import DEFAULT_COLOR_LABELS, VALID_ANNOTATION_COLORS
from app.db.models import User, UserApiKey, UserOAuthAccount, UserLLMPreferences
from app.schemas.auth import UserResponse
from app.services.llm_service import (
    OPENROUTER_BYOK_MODEL_IDS,
    OPENROUTER_MODEL_IDS,
    OPENROUTER_MODELS,
)

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




class LLMModelResponse(BaseModel):
    id: str
    label: str
    description: str
    requires_byok: bool = False


class LLMModelsListResponse(BaseModel):
    models: List[LLMModelResponse]


class LLMPreferencesResponse(BaseModel):
    chat_model: Optional[str] = None
    auto_highlight_model: Optional[str] = None
    explain_model: Optional[str] = None
    openrouter_key_mode: Literal["app", "byok"] = "app"


class LLMPreferencesUpdate(BaseModel):
    chat_model: Optional[str] = None
    auto_highlight_model: Optional[str] = None
    explain_model: Optional[str] = None
    openrouter_key_mode: Literal["app", "byok"] = "app"


VALID_MODEL_IDS = OPENROUTER_MODEL_IDS
MODEL_PREFERENCE_FIELDS = {
    "chat_model",
    "auto_highlight_model",
    "explain_model",
}


def _validate_model(value: Optional[str], field: str) -> None:
    if value is not None and value not in VALID_MODEL_IDS:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid model for {field}: {value}. Must be one of: {', '.join(sorted(VALID_MODEL_IDS))}",
        )


async def _get_or_create_prefs(
    user_id: uuid.UUID, db: AsyncSession
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


async def _has_openrouter_key(user_id: uuid.UUID, db: AsyncSession) -> bool:
    result = await db.execute(
        select(UserApiKey.id).where(
            UserApiKey.user_id == user_id,
            UserApiKey.provider == "openrouter",
        )
    )
    return result.scalar_one_or_none() is not None


def _selected_models(prefs: UserLLMPreferences, updates: dict) -> list[str]:
    selected: list[str] = []
    for field in MODEL_PREFERENCE_FIELDS:
        value = updates.get(field, getattr(prefs, field))
        if value:
            selected.append(value)
    return selected


@router.get("/llm-models", response_model=LLMModelsListResponse)
async def get_llm_models():
    """Return the curated list of available OpenRouter LLM models."""
    return LLMModelsListResponse(
        models=[LLMModelResponse(**m) for m in OPENROUTER_MODELS]
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
        openrouter_key_mode=prefs.openrouter_key_mode,
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
        if field in MODEL_PREFERENCE_FIELDS:
            _validate_model(value, field)

    prefs = await _get_or_create_prefs(current_user.id, db)
    effective_key_mode = updates.get(
        "openrouter_key_mode",
        prefs.openrouter_key_mode,
    )
    selected_models = _selected_models(prefs, updates)
    byok_models = [m for m in selected_models if m in OPENROUTER_BYOK_MODEL_IDS]
    has_openrouter_key = await _has_openrouter_key(current_user.id, db)

    if effective_key_mode == "byok" and not has_openrouter_key:
        raise HTTPException(
            status_code=400,
            detail="OpenRouter API key required for BYOK mode.",
        )

    if effective_key_mode == "app" and byok_models:
        raise HTTPException(
            status_code=400,
            detail="BYOK-only models require BYOK mode.",
        )

    for field, value in updates.items():
        setattr(prefs, field, value)

    await db.commit()
    await db.refresh(prefs)

    return LLMPreferencesResponse(
        chat_model=prefs.chat_model,
        auto_highlight_model=prefs.auto_highlight_model,
        explain_model=prefs.explain_model,
        openrouter_key_mode=prefs.openrouter_key_mode,
    )


class ColorLabelsResponse(BaseModel):
    labels: dict[str, str]


class ColorLabelsUpdate(BaseModel):
    labels: dict[str, str]


@router.get("/color-labels", response_model=ColorLabelsResponse)
async def get_color_labels(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    merged = dict(DEFAULT_COLOR_LABELS)
    if current_user.color_labels:
        merged.update(current_user.color_labels)
    return ColorLabelsResponse(labels=merged)


@router.patch("/color-labels", response_model=ColorLabelsResponse)
async def update_color_labels(
    data: ColorLabelsUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    invalid = set(data.labels.keys()) - VALID_ANNOTATION_COLORS
    if invalid:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid color keys: {', '.join(sorted(invalid))}. Must be one of: {', '.join(sorted(VALID_ANNOTATION_COLORS))}",
        )

    current = dict(current_user.color_labels or {})
    current.update(data.labels)
    current_user.color_labels = current
    db.add(current_user)
    await db.commit()
    await db.refresh(current_user)

    merged = dict(DEFAULT_COLOR_LABELS)
    if current_user.color_labels:
        merged.update(current_user.color_labels)
    return ColorLabelsResponse(labels=merged)
