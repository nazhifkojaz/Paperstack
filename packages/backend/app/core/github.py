import httpx
from typing import Any, Dict, Optional
from app.core.config import settings

GITHUB_OAUTH_URL = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_USER_URL = "https://api.github.com/user"
GITHUB_EMAILS_URL = "https://api.github.com/user/emails"


async def get_github_access_token(code: str) -> Optional[str]:
    async with httpx.AsyncClient() as client:
        response = await client.post(
            GITHUB_TOKEN_URL,
            data={
                "client_id": settings.GITHUB_CLIENT_ID,
                "client_secret": settings.GITHUB_CLIENT_SECRET,
                "code": code,
            },
            headers={"Accept": "application/json"},
        )
        if response.status_code != 200:
            return None
        data = response.json()
        return data.get("access_token")


async def get_github_user(access_token: str) -> Optional[Dict[str, Any]]:
    async with httpx.AsyncClient() as client:
        response = await client.get(
            GITHUB_USER_URL,
            headers={
                "Authorization": f"token {access_token}",
                "Accept": "application/json",
            },
        )
        if response.status_code != 200:
            return None
        return response.json()


async def get_github_emails(access_token: str) -> Optional[str]:
    """Fetch the user's primary email from GitHub.

    GitHub's /user endpoint returns email as null for users with private
    email settings. The /user/emails endpoint returns all verified emails.
    Returns the primary email address, or None if not found.
    """
    async with httpx.AsyncClient() as client:
        response = await client.get(
            GITHUB_EMAILS_URL,
            headers={
                "Authorization": f"token {access_token}",
                "Accept": "application/json",
            },
        )
        if response.status_code != 200:
            return None
        emails = response.json()
        for email in emails:
            if email.get("primary") and email.get("verified"):
                return email["email"]
        return None
