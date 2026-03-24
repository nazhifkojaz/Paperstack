"""GitHub API test fixtures and helpers."""
from typing import Any


def mock_github_user_response(
    github_id: int = 123456,
    login: str = "testuser",
    name: str | None = "Test User",
    email: str | None = "test@example.com",
    avatar_url: str | None = "https://example.com/avatar.png",
) -> dict[str, Any]:
    """Generate a mock GitHub user API response."""
    response: dict[str, Any] = {
        "id": github_id,
        "login": login,
    }
    if name:
        response["name"] = name
    if email:
        response["email"] = email
    if avatar_url:
        response["avatar_url"] = avatar_url
    return response


def mock_github_repo_response(
    name: str = "paperstack-library",
    full_name: str = "testuser/paperstack-library",
    private: bool = False,
) -> dict[str, Any]:
    """Generate a mock GitHub repository API response."""
    return {
        "name": name,
        "full_name": full_name,
        "private": private,
        "html_url": f"https://github.com/{full_name}",
        "url": f"https://api.github.com/repos/{full_name}",
    }


def mock_github_content_response(
    sha: str = "abc123def456",
    name: str = "test.pdf",
    size: int = 12345,
) -> dict[str, Any]:
    """Generate a mock GitHub Contents API response."""
    return {
        "sha": sha,
        "name": name,
        "size": size,
        "type": "file",
        "download_url": f"https://raw.githubusercontent.com/user/repo/main/{name}",
    }
