from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.api import deps
from app.core import github, google, security
from app.core.config import settings
from app.db.models import User, UserOAuthAccount
from app.schemas.auth import Token, RefreshTokenRequest, UserResponse
from app.middleware.rate_limit import limiter

router = APIRouter()




async def _upsert_oauth_user(
    db: AsyncSession,
    *,
    provider: str,
    provider_user_id: str,
    provider_email: Optional[str],
    display_name: Optional[str],
    avatar_url: Optional[str],
    encrypted_access_token: str,
    encrypted_refresh_token: Optional[str],
    token_expires_at: Optional[datetime],
    extra_data: dict[str, Any],
) -> User:
    """Upsert user and linked OAuth account. Returns existing or new User."""
    stmt = select(UserOAuthAccount).where(
        UserOAuthAccount.provider == provider,
        UserOAuthAccount.provider_user_id == provider_user_id,
    )
    result = await db.execute(stmt)
    oauth_account = result.scalar_one_or_none()

    if oauth_account:
        # Update tokens and profile
        oauth_account.encrypted_access_token = encrypted_access_token
        if encrypted_refresh_token:
            oauth_account.encrypted_refresh_token = encrypted_refresh_token
        oauth_account.token_expires_at = token_expires_at
        oauth_account.email = provider_email
        oauth_account.extra_data = {**(oauth_account.extra_data or {}), **extra_data}
        db.add(oauth_account)

        user_stmt = select(User).where(User.id == oauth_account.user_id)
        user = (await db.execute(user_stmt)).scalar_one()

        # Keep legacy columns in sync for GitHub users (used by sharing.py)
        if provider == "github":
            user.github_id = int(provider_user_id)
            user.github_login = extra_data.get("github_login")
            user.access_token = encrypted_access_token
        user.display_name = display_name or user.display_name
        user.avatar_url = user.avatar_url or avatar_url
        if provider_email and not user.email:
            user.email = provider_email
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return user

    user: Optional[User] = None
    if provider_email:
        email_stmt = select(User).where(User.email == provider_email)
        user = (await db.execute(email_stmt)).scalar_one_or_none()

    if not user:
        user = User(
            email=provider_email,
            display_name=display_name,
            avatar_url=avatar_url,
            storage_provider=provider,
        )
        # Populate legacy fields for GitHub so sharing.py works without changes
        if provider == "github":
            user.github_id = int(provider_user_id)
            user.github_login = extra_data.get("github_login")
            user.access_token = encrypted_access_token
            user.repo_created = False  # new account — no repo yet
        db.add(user)
        await db.flush()  # get user.id before creating the OAuth account
    else:
        # Existing user — update profile if richer data is available
        user.display_name = display_name or user.display_name
        user.avatar_url = user.avatar_url or avatar_url
        if provider_email and not user.email:
            user.email = provider_email
        # Keep legacy fields in sync for GitHub
        if provider == "github":
            user.github_id = int(provider_user_id)
            user.github_login = extra_data.get("github_login")
            user.access_token = encrypted_access_token
        db.add(user)

    # Create the OAuth account row
    new_account = UserOAuthAccount(
        user_id=user.id,
        provider=provider,
        provider_user_id=provider_user_id,
        email=provider_email,
        encrypted_access_token=encrypted_access_token,
        encrypted_refresh_token=encrypted_refresh_token,
        token_expires_at=token_expires_at,
        extra_data=extra_data,
    )
    db.add(new_account)

    await db.commit()
    await db.refresh(user)
    return user


def _redirect_with_tokens(user: User) -> RedirectResponse:
    """Issue app JWTs and redirect to the frontend callback page."""
    access_token = security.create_access_token(user.id)
    refresh_token = security.create_refresh_token(user.id)
    redirect_url = (
        f"{settings.FRONTEND_URL}/Paperstack/auth/callback"
        f"#access_token={access_token}"
        f"&refresh_token={refresh_token}"
    )
    return RedirectResponse(redirect_url)




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
async def github_callback(
    request: Request, code: str, db: AsyncSession = Depends(deps.get_db)
):
    """Exchange GitHub code for token, upsert user, issue JWT."""
    github_token = await github.get_github_access_token(code)
    if not github_token:
        raise HTTPException(status_code=400, detail="Invalid GitHub code")

    github_user_data = await github.get_github_user(github_token)
    if not github_user_data:
        raise HTTPException(status_code=400, detail="Failed to fetch GitHub user")

    email = github_user_data.get("email")
    if not email:
        email = await github.get_github_emails(github_token)

    user = await _upsert_oauth_user(
        db,
        provider="github",
        provider_user_id=str(github_user_data["id"]),
        provider_email=email,
        display_name=github_user_data.get("name"),
        avatar_url=github_user_data.get("avatar_url"),
        encrypted_access_token=security.encrypt_token(github_token),
        encrypted_refresh_token=None,  # GitHub tokens don't expire
        token_expires_at=None,
        extra_data={"github_login": github_user_data["login"]},
    )
    return _redirect_with_tokens(user)




@router.get("/google/login")
@limiter.limit(settings.RATE_LIMIT_AUTH_OAUTH)
async def google_login(request: Request):
    """Redirect to Google OAuth consent."""
    redirect_uri = f"{settings.BACKEND_URL}/v1/auth/google/callback"
    url = (
        "https://accounts.google.com/o/oauth2/v2/auth"
        f"?client_id={settings.GOOGLE_CLIENT_ID}"
        f"&redirect_uri={redirect_uri}"
        "&response_type=code"
        "&scope=openid+email+profile+https://www.googleapis.com/auth/drive.file"
        "&access_type=offline"
        "&prompt=consent"
    )
    return RedirectResponse(url)


@router.get("/google/callback")
@limiter.limit(settings.RATE_LIMIT_AUTH_OAUTH)
async def google_callback(
    request: Request, code: str, db: AsyncSession = Depends(deps.get_db)
):
    """Exchange Google code for tokens, upsert user, issue JWT."""
    tokens = await google.get_google_tokens(code)
    if not tokens or "access_token" not in tokens:
        raise HTTPException(status_code=400, detail="Invalid Google code")

    google_user_data = await google.get_google_user(tokens["access_token"])
    if not google_user_data:
        raise HTTPException(status_code=400, detail="Failed to fetch Google user")

    expires_in = tokens.get("expires_in", 3600)
    token_expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

    refresh_token = tokens.get("refresh_token")

    user = await _upsert_oauth_user(
        db,
        provider="google",
        provider_user_id=google_user_data["sub"],
        provider_email=google_user_data.get("email"),
        display_name=google_user_data.get("name"),
        avatar_url=google_user_data.get("picture"),
        encrypted_access_token=security.encrypt_token(tokens["access_token"]),
        encrypted_refresh_token=security.encrypt_token(refresh_token)
        if refresh_token
        else None,
        token_expires_at=token_expires_at,
        extra_data={},
    )
    return _redirect_with_tokens(user)




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
