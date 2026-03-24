import httpx
from typing import Any, Dict, Optional
from app.core.config import settings

GITHUB_OAUTH_URL = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_USER_URL = "https://api.github.com/user"

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
