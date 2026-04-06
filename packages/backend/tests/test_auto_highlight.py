import pytest
from httpx import AsyncClient


@pytest.fixture
def mock_llm_response():
    return [
        {
            "text": "We found significant improvements in accuracy.",
            "page": 1,
            "category": "findings",
            "reason": "Primary result of the study",
        },
        {
            "text": "The model uses a transformer architecture.",
            "page": 3,
            "category": "methods",
            "reason": "Core methodology description",
        },
    ]


@pytest.mark.asyncio
async def test_get_quota_default(admin_client: AsyncClient, auth_headers):
    """New user should have 5 free uses."""
    resp = await admin_client.get("/v1/auto-highlight/quota", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["free_uses_remaining"] == 5
    assert data["has_own_key"] is False
    assert data["providers"] == []


@pytest.mark.asyncio
async def test_get_quota_with_key(admin_client: AsyncClient, auth_headers):
    """User with stored key should show it."""
    await admin_client.post(
        "/v1/settings/api-keys",
        json={"provider": "gemini", "api_key": "test-key"},
        headers=auth_headers,
    )
    resp = await admin_client.get("/v1/auto-highlight/quota", headers=auth_headers)
    data = resp.json()
    assert data["has_own_key"] is True
    assert "gemini" in data["providers"]


@pytest.mark.asyncio
async def test_analyze_no_key_no_quota(admin_client: AsyncClient, auth_headers, test_user):
    """Should fail if no key and no quota."""
    # Create a PDF record first
    # Exhaust quota by setting to 0 — done via direct DB manipulation in fixture
    # For simplicity, this test assumes quota starts at 5 and in-house keys are not set
    # The actual test would need a PDF fixture and mock the GitHub download
    pass  # Placeholder — full implementation depends on PDF fixtures


@pytest.mark.asyncio
async def test_cache_list_empty(admin_client: AsyncClient, auth_headers):
    """Cache should be empty for a new PDF."""
    import uuid
    pdf_id = str(uuid.uuid4())
    resp = await admin_client.get(
        f"/v1/auto-highlight/cache/{pdf_id}", headers=auth_headers
    )
    assert resp.status_code == 200
    assert resp.json() == []
