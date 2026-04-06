"""Tests for rate limiting on auth endpoints."""

import pytest
from httpx import AsyncClient


@pytest.fixture(autouse=True)
def reset_rate_limit_storage():
    """Reset rate limit storage before each test.

    This ensures tests don't interfere with each other since they all
    use the same in-memory rate limit storage.
    """
    from app.middleware.rate_limit import limiter

    # Clear the in-memory storage before each test
    limiter.limiter.storage.reset()
    yield


class TestRateLimiting:
    """Tests for rate limiting behavior."""

    async def test_within_limit_succeeds(self, client: AsyncClient) -> None:
        """Test that requests within the rate limit succeed."""
        for i in range(5):
            response = await client.get("/v1/auth/github/login", follow_redirects=False)
            assert response.status_code in (307, 302), f"Request {i + 1} failed"

    async def test_rate_limit_exceeded_returns_429(self, client: AsyncClient) -> None:
        """Test that exceeding the rate limit returns 429."""
        responses = []
        for i in range(11):
            response = await client.get("/v1/auth/github/login", follow_redirects=False)
            responses.append(response)

        for i in range(10):
            assert responses[i].status_code in (307, 302), (
                f"Request {i + 1} should succeed"
            )

        assert responses[10].status_code == 429, "11th request should return 429"
        data = responses[10].json()
        assert "retry_after" in data
        assert isinstance(data["retry_after"], int)
        assert data["retry_after"] > 0

    async def test_rate_limit_headers_present(self, client: AsyncClient) -> None:
        """Test that rate limit headers are included in 429 response."""
        for _ in range(11):
            response = await client.get("/v1/auth/github/login", follow_redirects=False)

        assert "X-RateLimit-Limit" in response.headers
        assert "X-RateLimit-Remaining" in response.headers
        assert "Retry-After" in response.headers
        assert response.headers["X-RateLimit-Remaining"] == "0"

    async def test_refresh_rate_limit_independent(self, client: AsyncClient) -> None:
        """Test that refresh endpoint has its own rate limit."""
        for _ in range(11):
            await client.get("/v1/auth/github/login", follow_redirects=False)

        response = await client.post(
            "/v1/auth/refresh", json={"refresh_token": "invalid"}
        )
        assert response.status_code == 401


class TestRateLimitingChat:
    """Tests for rate limiting on chat endpoints."""

    async def test_semantic_search_rate_limit(
        self, client: AsyncClient, auth_headers
    ) -> None:
        """Test that semantic search is rate limited."""
        from app.middleware.rate_limit import limiter
        from app.main import app
        from app.core.http_client import HTTPClientState

        limiter.limiter.storage.reset()

        if not hasattr(app.state, "embedding_http_client"):
            HTTPClientState.init_http_clients(app)

        responses = []
        for i in range(12):
            response = await client.post(
                "/v1/chat/semantic-search",
                json={"query": "test"},
                headers=auth_headers,
            )
            responses.append(response)

        # First 10 should succeed (or fail with non-429), 11th should be 429
        for i in range(10):
            assert responses[i].status_code != 429, (
                f"Request {i + 1} should not be rate limited"
            )

        assert responses[10].status_code == 429, "11th request should return 429"
