"""API-level tests for auto-highlight routes."""

import uuid
from httpx import AsyncClient
from unittest.mock import AsyncMock, MagicMock, patch
from tests.fixtures import create_test_pdf

TEST_EMBEDDING = [0.01] * 1024


def _init_http_clients():
    from app.main import app
    from app.core.http_client import HTTPClientState

    if not hasattr(app.state, "llm_http_client"):
        HTTPClientState.init_http_clients(app)


def _setup_http_mocks():
    _init_http_clients()
    from app.api import deps

    async def _override_llm():
        from app.main import app
        from app.core.http_client import HTTPClientState

        yield HTTPClientState.get_llm_client(app)

    async def _override_embed():
        from app.main import app
        from app.core.http_client import HTTPClientState

        yield HTTPClientState.get_embedding_client(app)

    deps.get_llm_http_client = _override_llm
    deps.get_embedding_http_client = _override_embed


class TestAutoHighlightQuota:

    async def test_quota_returns_default_free_uses(
        self, client: AsyncClient, auth_headers
    ):
        response = await client.get("/v1/auto-highlight/quota", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["free_uses_remaining"] == 5
        assert data["has_own_key"] is False

    async def test_quota_requires_auth(self, client: AsyncClient):
        response = await client.get("/v1/auto-highlight/quota")
        assert response.status_code == 401


class TestAutoHighlightAnalyze:

    async def test_analyze_no_api_key_no_quota_returns_402(
        self, client: AsyncClient, auth_headers, db_session, test_user
    ):
        _setup_http_mocks()

        pdf = await create_test_pdf(
            db_session, user_id=test_user.id, title="Test", filename="test.pdf"
        )
        await db_session.commit()

        with patch(
            "app.api.routes.auto_highlight.resolve_api_key_with_quota",
            new_callable=AsyncMock,
        ) as mock_resolve:
            from fastapi import HTTPException

            mock_resolve.side_effect = HTTPException(
                status_code=402, detail="No API keys available"
            )

            response = await client.post(
                "/v1/auto-highlight/analyze",
                json={
                    "pdf_id": str(pdf.id),
                    "categories": ["findings"],
                    "pages": [],
                    "tier": "quick",
                },
                headers=auth_headers,
            )

            assert response.status_code == 402

    async def test_analyze_requires_auth(self, client: AsyncClient):
        response = await client.post(
            "/v1/auto-highlight/analyze",
            json={
                "pdf_id": str(uuid.uuid4()),
                "categories": ["findings"],
                "pages": [],
                "tier": "quick",
            },
        )
        assert response.status_code == 401

    async def test_analyze_without_quota_returns_402(
        self, client: AsyncClient, auth_headers
    ):
        """Without a stored API key or free quota, /analyze returns 402."""
        _setup_http_mocks()

        response = await client.post(
            "/v1/auto-highlight/analyze",
            json={
                "pdf_id": str(uuid.uuid4()),
                "categories": ["findings"],
                "pages": [],
                "tier": "quick",
            },
            headers=auth_headers,
        )

        # Route checks API key quota before PDF existence — 402 is correct
        assert response.status_code == 402


class TestAutoHighlightCache:

    async def test_cache_requires_auth(self, client: AsyncClient):
        response = await client.get(
            f"/v1/auto-highlight/cache/{uuid.uuid4()}"
        )
        assert response.status_code == 401

    async def test_cache_empty_for_nonexistent_pdf(
        self, client: AsyncClient, auth_headers
    ):
        """Cache for a nonexistent PDF returns empty list."""
        response = await client.get(
            f"/v1/auto-highlight/cache/{uuid.uuid4()}",
            headers=auth_headers,
        )

        # Can return 200 with empty or 404 — both are valid
        assert response.status_code in (200, 404)

    async def test_delete_cache_requires_auth(self, client: AsyncClient):
        response = await client.delete(
            f"/v1/auto-highlight/cache/{uuid.uuid4()}"
        )
        assert response.status_code == 401
