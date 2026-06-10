from typing import AsyncGenerator, Literal
import uuid
import httpx
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core import security
from app.core.http_client import HTTPClientState
from app.db.engine import SessionLocal
from app.db.models import User, UserLLMPreferences

reusable_oauth2 = OAuth2PasswordBearer(
    tokenUrl="/v1/auth/github/login"  # Used for OpenAPI docs; actual auth is OAuth flow
)

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session

async def get_current_user(
    db: AsyncSession = Depends(get_db), token: str = Depends(reusable_oauth2)
) -> User:
    user_id = security.verify_access_token(token)
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
        )
    
    stmt = select(User).where(User.id == uuid.UUID(user_id))
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return user


async def get_llm_http_client(
    request: Request,
) -> AsyncGenerator[httpx.AsyncClient, None]:
    """Dependency that provides shared LLM HTTP client.

    Yields the app-level LLM client configured for connection pooling.
    Used by chat and auto-highlight services.
    """
    client = HTTPClientState.get_llm_client(request.app)
    yield client


async def get_embedding_http_client(
    request: Request,
) -> AsyncGenerator[httpx.AsyncClient, None]:
    """Dependency that provides shared embedding HTTP client.

    Yields the app-level embedding client configured for connection pooling.
    Used by vector search and indexing services.
    """
    client = HTTPClientState.get_embedding_client(request.app)
    yield client


_PREFERENCE_MAP = {
    "chat": "chat_model",
    "explain_paraphrase": "explain_model",
    "auto_highlight_quick": "auto_highlight_model",
    "auto_highlight_thorough": "auto_highlight_model",
}

_RESOLVER_MAP = {
    "chat": "resolve_for_chat",
    "explain_paraphrase": "resolve_for_explain",
    "auto_highlight_quick": "resolve_for_auto_highlight",
    "auto_highlight_thorough": "resolve_for_auto_highlight",
}


async def resolve_api_key_with_quota(
    user: User,
    db: AsyncSession,
    feature: Literal[
        "chat",
        "explain_paraphrase",
        "auto_highlight_quick",
        "auto_highlight_thorough",
    ],
):
    """Resolve API key for a feature, check quotas, raise HTTPException on errors.

    Queries UserLLMPreferences for the preferred model, resolves the key
    via api_key_service, and decrements daily quotas for in-house OpenRouter.
    """
    from app.services.api_key_service import api_key_service
    from app.services.exceptions import (
        ApiKeyNotFoundError,
        QuotaExhaustedError,
    )
    from app.services.openrouter_usage_service import openrouter_usage_service
    from app.services.quota_service import quota_service

    pref_column = _PREFERENCE_MAP[feature]
    prefs_result = await db.execute(
        select(getattr(UserLLMPreferences, pref_column)).where(
            UserLLMPreferences.user_id == user.id
        )
    )
    preferred_model = prefs_result.scalar_one_or_none()

    resolve_fn = getattr(api_key_service, _RESOLVER_MAP[feature])
    try:
        resolution = await resolve_fn(user, db, force_free_model=preferred_model)
    except (QuotaExhaustedError, ApiKeyNotFoundError) as e:
        raise HTTPException(status_code=402, detail=str(e))

    if not (resolution.is_in_house and resolution.provider == "openrouter"):
        return resolution, quota_service.unlimited()

    try:
        quota_result = await quota_service.check_and_decrement(user.id, db, feature)
    except QuotaExhaustedError as exc:
        raise HTTPException(status_code=402, detail=str(exc))

    global_status = await openrouter_usage_service.record_and_check(db)
    await db.commit()
    return resolution, quota_result.with_global_warning(global_status.warning_message)
