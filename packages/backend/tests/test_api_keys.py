import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_api_key(admin_client: AsyncClient, auth_headers):
    resp = await admin_client.post(
        "/v1/settings/api-keys",
        json={"provider": "openrouter", "api_key": "test-key-12345"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["provider"] == "openrouter"
    assert "••••" in data["key_preview"]
    assert "test-key" not in data["key_preview"]  # Key should be masked


@pytest.mark.asyncio
async def test_create_api_key_invalid_provider(admin_client: AsyncClient, auth_headers):
    resp = await admin_client.post(
        "/v1/settings/api-keys",
        json={"provider": "gemini", "api_key": "test"},
        headers=auth_headers,
    )
    assert resp.status_code == 422  # Validation error


@pytest.mark.asyncio
async def test_create_api_key_upsert(admin_client: AsyncClient, auth_headers):
    """Creating a key for the same provider should update it."""
    await admin_client.post(
        "/v1/settings/api-keys",
        json={"provider": "openrouter", "api_key": "old-key"},
        headers=auth_headers,
    )
    resp = await admin_client.post(
        "/v1/settings/api-keys",
        json={"provider": "openrouter", "api_key": "new-key"},
        headers=auth_headers,
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_delete_api_key(admin_client: AsyncClient, auth_headers):
    # Create first
    await admin_client.post(
        "/v1/settings/api-keys",
        json={"provider": "openrouter", "api_key": "to-delete"},
        headers=auth_headers,
    )
    # Delete
    resp = await admin_client.delete(
        "/v1/settings/api-keys/openrouter", headers=auth_headers
    )
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_delete_api_key_resets_byok_preferences(
    admin_client: AsyncClient, auth_headers
):
    await admin_client.post(
        "/v1/settings/api-keys",
        json={"provider": "openrouter", "api_key": "to-delete"},
        headers=auth_headers,
    )
    prefs_resp = await admin_client.patch(
        "/v1/settings/llm-preferences",
        json={
            "openrouter_key_mode": "byok",
            "chat_model": "anthropic/claude-fable-5",
        },
        headers=auth_headers,
    )
    assert prefs_resp.status_code == 200

    resp = await admin_client.delete(
        "/v1/settings/api-keys/openrouter", headers=auth_headers
    )
    assert resp.status_code == 204

    final_prefs = await admin_client.get(
        "/v1/settings/llm-preferences",
        headers=auth_headers,
    )
    assert final_prefs.status_code == 200
    data = final_prefs.json()
    assert data["openrouter_key_mode"] == "app"
    assert data["chat_model"] is None


@pytest.mark.asyncio
async def test_delete_api_key_not_found(admin_client: AsyncClient, auth_headers):
    resp = await admin_client.delete(
        "/v1/settings/api-keys/openrouter", headers=auth_headers
    )
    assert resp.status_code == 404
