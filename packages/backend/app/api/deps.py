from typing import AsyncGenerator
import uuid
import httpx
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core import security
from app.core.http_client import HTTPClientState
from app.db.engine import SessionLocal
from app.db.models import User

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
