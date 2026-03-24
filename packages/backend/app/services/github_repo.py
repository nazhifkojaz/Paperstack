import httpx
import tempfile
from pathlib import Path
from typing import Dict, Any
import base64
from fastapi import HTTPException
from app.core import security

GITHUB_API_URL = "https://api.github.com"
REPO_NAME = "paperstack-library"

async def get_github_client(access_token: str) -> httpx.AsyncClient:
    decrypted_token = security.decrypt_token(access_token)
    return httpx.AsyncClient(
        headers={
            "Authorization": f"Bearer {decrypted_token}",
            "Accept": "application/vnd.github.v3+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        base_url=GITHUB_API_URL,
    )

async def ensure_user_repo(access_token: str, github_login: str) -> bool:
    """Checks if paperstack-library repo exists, creates it if not."""
    async with await get_github_client(access_token) as client:
        # Check if repo exists
        resp = await client.get(f"/repos/{github_login}/{REPO_NAME}")
        if resp.status_code == 200:
            return True
        
        if resp.status_code != 404:
            raise HTTPException(status_code=500, detail="Failed to check GitHub repository status")
            
        # Create repo
        create_resp = await client.post("/user/repos", json={
            "name": REPO_NAME,
            "description": "Private PDF library managed by Paperstack",
            "private": True,
            "auto_init": True
        })
        
        if create_resp.status_code != 201:
            raise HTTPException(status_code=500, detail=f"Failed to create GitHub repository: {create_resp.text}")
            
        return True

async def upload_pdf_to_github(
    access_token: str, 
    github_login: str, 
    filepath: str, 
    file_bytes: bytes, 
    commit_message: str = "Add PDF"
) -> Dict[str, Any]:
    """Uploads a PDF file to the users paperstack-library repo."""
    encoded_content = base64.b64encode(file_bytes).decode("utf-8")
    
    async with await get_github_client(access_token) as client:
        resp = await client.put(f"/repos/{github_login}/{REPO_NAME}/contents/{filepath}", json={
            "message": commit_message,
            "content": encoded_content
        })
        
        if resp.status_code not in (200, 201):
            raise HTTPException(status_code=500, detail=f"Failed to upload to GitHub: {resp.text}")
            
        return resp.json()

async def download_pdf_from_github(access_token: str, github_login: str, filepath: str) -> bytes:
    """Downloads a PDF file from the users paperstack-library repo."""
    async with await get_github_client(access_token) as client:
        # We need to request the raw format
        client.headers.update({"Accept": "application/vnd.github.v3.raw"})
        resp = await client.get(f"/repos/{github_login}/{REPO_NAME}/contents/{filepath}")
        
        if resp.status_code != 200:
            raise HTTPException(status_code=resp.status_code, detail=f"Failed to download from GitHub: {resp.text}")
            
        return resp.content

async def download_pdf_to_tempfile(access_token: str, github_login: str, filepath: str) -> Path:
    """Downloads a PDF file from GitHub to a temporary file.

    Returns the path to the temp file. Caller is responsible for deleting it.
    """
    async with await get_github_client(access_token) as client:
        client.headers.update({"Accept": "application/vnd.github.v3.raw"})

        async with client.stream("GET", f"/repos/{github_login}/{REPO_NAME}/contents/{filepath}") as response:
            if response.status_code != 200:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Failed to download from GitHub: status {response.status_code}"
                )

            tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
            try:
                async for chunk in response.aiter_bytes(chunk_size=8192):
                    tmp.write(chunk)
                tmp.close()
                return Path(tmp.name)
            except Exception:
                tmp.close()
                Path(tmp.name).unlink(missing_ok=True)
                raise


async def delete_pdf_from_github(
    access_token: str,
    github_login: str,
    filepath: str,
    sha: str,
    commit_message: str = "Delete PDF"
) -> bool:
    """Deletes a PDF file from the users paperstack-library repo."""
    import json

    async with await get_github_client(access_token) as client:
        resp = await client.request(
            "DELETE",
            f"/repos/{github_login}/{REPO_NAME}/contents/{filepath}",
            content=json.dumps({
                "message": commit_message,
                "sha": sha
            }),
            headers={"Content-Type": "application/json"}
        )

        if resp.status_code != 200:
            raise HTTPException(status_code=500, detail=f"Failed to delete from GitHub: {resp.text}")

        return True
