from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import uuid

from app.api import deps
from app.core import security, github
from app.core.config import settings
from app.db.models import User
from app.schemas.auth import Token, RefreshTokenRequest, UserResponse
from app.middleware.rate_limit import limiter

router = APIRouter()

@router.get("/github/login")
@limiter.limit(settings.RATE_LIMIT_AUTH_OAUTH)
async def github_login(request: Request):
    """Redirect to GitHub OAuth consent."""
    url = (
        f"https://github.com/login/oauth/authorize"
        f"?client_id={settings.GITHUB_CLIENT_ID}"
        f"&scope=repo,user"
    )
    return RedirectResponse(url)

@router.get("/github/callback")
@limiter.limit(settings.RATE_LIMIT_AUTH_OAUTH)
async def github_callback(request: Request, code: str, db: AsyncSession = Depends(deps.get_db)):
    """Exchange code for token, upsert user, issue JWT."""
    github_token = await github.get_github_access_token(code)
    if not github_token:
        raise HTTPException(status_code=400, detail="Invalid GitHub code")

    github_user_data = await github.get_github_user(github_token)
    if not github_user_data:
        raise HTTPException(status_code=400, detail="Failed to fetch GitHub user")

    # Upsert user
    stmt = select(User).where(User.github_id == github_user_data["id"])
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    encrypted_token = security.encrypt_token(github_token)

    if user:
        user.github_login = github_user_data["login"]
        user.display_name = github_user_data.get("name")
        user.avatar_url = github_user_data.get("avatar_url")
        user.access_token = encrypted_token
    else:
        user = User(
            github_id=github_user_data["id"],
            github_login=github_user_data["login"],
            display_name=github_user_data.get("name"),
            avatar_url=github_user_data.get("avatar_url"),
            access_token=encrypted_token,
        )
        db.add(user)

    await db.commit()
    await db.refresh(user)

    # Issue our own tokens
    access_token = security.create_access_token(user.id)
    refresh_token = security.create_refresh_token(user.id)

    # Redirect back to frontend using URL fragments (hash) to prevent token leakage
    # Fragments are not sent to the server and don't appear in referrer headers
    redirect_url = (
        f"{settings.FRONTEND_URL}/Paperstack/auth/callback"
        f"#access_token={access_token}"
        f"&refresh_token={refresh_token}"
    )
    return RedirectResponse(redirect_url)

@router.post("/refresh", response_model=Token)
@limiter.limit(settings.RATE_LIMIT_AUTH_REFRESH)
async def refresh_token(request: Request, req: RefreshTokenRequest):
    """Refresh JWT using refresh token."""
    user_id = security.verify_refresh_token(req.refresh_token)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    
    access_token = security.create_access_token(user_id)
    new_refresh_token = security.create_refresh_token(user_id)
    
    return {
        "access_token": access_token,
        "refresh_token": new_refresh_token,
        "token_type": "bearer",
    }

@router.get("/me", response_model=UserResponse)
@limiter.limit(settings.RATE_LIMIT_AUTH_ME)
async def get_me(request: Request, current_user: User = Depends(deps.get_current_user)):
    """Return current user profile."""
    return current_user

@router.post("/logout")
@limiter.limit(settings.RATE_LIMIT_AUTH_LOGOUT)
async def logout(request: Request):
    """Sign out current user."""
    return {"message": "Successfully logged out"}
