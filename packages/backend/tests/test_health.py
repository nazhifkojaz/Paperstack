"""Tests for health endpoint."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_returns_200(client: AsyncClient) -> None:
    """Test that the health check endpoint returns 200."""
    resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert "status" in data
    assert data["status"] == "ok"


@pytest.mark.asyncio
async def test_health_no_auth_required(client: AsyncClient) -> None:
    """Test that the health check endpoint does not require authentication."""
    resp = await client.get("/health")
    assert resp.status_code == 200
