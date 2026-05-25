"""API-level tests for auto-highlight routes."""

import asyncio
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


def _make_analyze_resolution(provider="openrouter", api_key="test-key"):
    resolution = MagicMock()
    resolution.provider = provider
    resolution.api_key = api_key
    resolution.model = None
    return resolution


def _make_create_task_stub(real_create_task):
    background_tasks = []

    def _create_task(coro):
        coro_name = getattr(getattr(coro, "cr_code", None), "co_name", None)
        if coro_name == "_run_analysis_background":
            background_tasks.append(coro)
            coro.close()
            return MagicMock()
        return real_create_task(coro)

    _create_task.background_tasks = background_tasks
    return _create_task


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

        assert response.status_code == 402

    async def test_analyze_creates_pending_cache(
        self, client: AsyncClient, auth_headers, db_session, test_user
    ):
        _setup_http_mocks()

        pdf = await create_test_pdf(
            db_session, user_id=test_user.id, title="Test", filename="test.pdf"
        )
        await db_session.commit()
        create_task_stub = _make_create_task_stub(asyncio.create_task)

        with (
            patch(
                "app.api.routes.auto_highlight.resolve_api_key_with_quota",
                new_callable=AsyncMock,
            ) as mock_resolve,
            patch(
                "app.api.routes.auto_highlight.asyncio.create_task"
            ) as mock_create_task,
        ):
            mock_resolve.return_value = _make_analyze_resolution()
            mock_create_task.side_effect = create_task_stub

            response = await client.post(
                "/v1/auto-highlight/analyze",
                json={
                    "pdf_id": str(pdf.id),
                    "categories": ["findings"],
                    "pages": [1, 2],
                    "tier": "quick",
                },
                headers=auth_headers,
            )

        assert response.status_code == 202
        data = response.json()
        assert data["from_cache"] is False
        assert data["highlights_count"] == 0
        assert len(create_task_stub.background_tasks) == 1

        from app.db.models import AutoHighlightCache
        from sqlalchemy import select

        result = await db_session.execute(
            select(AutoHighlightCache).where(AutoHighlightCache.id == data["cache_id"])
        )
        cache = result.scalar_one_or_none()
        assert cache is not None
        assert cache.status == "pending"
        assert cache.pdf_id == pdf.id
        assert cache.user_id == test_user.id
        assert cache.categories == ["findings"]

    async def test_analyze_pending_cache_returns_409(
        self, client: AsyncClient, auth_headers, db_session, test_user
    ):
        _setup_http_mocks()

        pdf = await create_test_pdf(
            db_session, user_id=test_user.id, title="Test", filename="test.pdf"
        )
        await db_session.commit()

        from app.db.models import AutoHighlightCache

        cache = AutoHighlightCache(
            pdf_id=pdf.id,
            user_id=test_user.id,
            categories=["findings", "methods"],
            pages=[1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
            status="pending",
        )
        db_session.add(cache)
        await db_session.commit()

        with patch(
            "app.api.routes.auto_highlight.resolve_api_key_with_quota",
            new_callable=AsyncMock,
        ) as mock_resolve:
            mock_resolve.return_value = _make_analyze_resolution()

            response = await client.post(
                "/v1/auto-highlight/analyze",
                json={
                    "pdf_id": str(pdf.id),
                    "categories": ["findings", "methods"],
                    "pages": [],
                    "tier": "quick",
                },
                headers=auth_headers,
            )

        assert response.status_code == 409

    async def test_analyze_running_cache_returns_409(
        self, client: AsyncClient, auth_headers, db_session, test_user
    ):
        _setup_http_mocks()

        pdf = await create_test_pdf(
            db_session, user_id=test_user.id, title="Test", filename="test.pdf"
        )
        await db_session.commit()

        from app.db.models import AutoHighlightCache

        cache = AutoHighlightCache(
            pdf_id=pdf.id,
            user_id=test_user.id,
            categories=["findings"],
            pages=[1, 2],
            status="running",
        )
        db_session.add(cache)
        await db_session.commit()

        with patch(
            "app.api.routes.auto_highlight.resolve_api_key_with_quota",
            new_callable=AsyncMock,
        ) as mock_resolve:
            mock_resolve.return_value = _make_analyze_resolution()

            response = await client.post(
                "/v1/auto-highlight/analyze",
                json={
                    "pdf_id": str(pdf.id),
                    "categories": ["findings"],
                    "pages": [1, 2],
                    "tier": "quick",
                },
                headers=auth_headers,
            )

        assert response.status_code == 409

    async def test_analyze_failed_cache_is_reset(
        self, client: AsyncClient, auth_headers, db_session, test_user
    ):
        _setup_http_mocks()

        pdf = await create_test_pdf(
            db_session, user_id=test_user.id, title="Test", filename="test.pdf"
        )
        await db_session.commit()

        from app.db.models import AutoHighlightCache

        cache = AutoHighlightCache(
            pdf_id=pdf.id,
            user_id=test_user.id,
            categories=["findings"],
            pages=[1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
            status="failed",
            llm_response={"error": "Setup failed"},
        )
        db_session.add(cache)
        await db_session.commit()
        create_task_stub = _make_create_task_stub(asyncio.create_task)

        with (
            patch(
                "app.api.routes.auto_highlight.resolve_api_key_with_quota",
                new_callable=AsyncMock,
            ) as mock_resolve,
            patch(
                "app.api.routes.auto_highlight.asyncio.create_task"
            ) as mock_create_task,
        ):
            mock_resolve.return_value = _make_analyze_resolution()
            mock_create_task.side_effect = create_task_stub

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

        assert response.status_code == 202
        assert len(create_task_stub.background_tasks) == 1
        await db_session.refresh(cache)
        assert cache.status == "pending"
        assert cache.llm_response is None

    async def test_analyze_page_less_than_1_returns_400(
        self, client: AsyncClient, auth_headers
    ):
        _setup_http_mocks()

        response = await client.post(
            "/v1/auto-highlight/analyze",
            json={
                "pdf_id": str(uuid.uuid4()),
                "categories": ["findings"],
                "pages": [0, 1],
                "tier": "quick",
            },
            headers=auth_headers,
        )

        assert response.status_code == 400
        assert "Page numbers must be >= 1" in response.json()["detail"]

    async def test_analyze_more_than_100_pages_returns_400(
        self, client: AsyncClient, auth_headers
    ):
        _setup_http_mocks()

        response = await client.post(
            "/v1/auto-highlight/analyze",
            json={
                "pdf_id": str(uuid.uuid4()),
                "categories": ["findings"],
                "pages": list(range(1, 102)),
                "tier": "quick",
            },
            headers=auth_headers,
        )

        assert response.status_code == 400
        assert "100" in response.json()["detail"]


class TestAutoHighlightCache:
    async def test_cache_requires_auth(self, client: AsyncClient):
        response = await client.get(f"/v1/auto-highlight/cache/{uuid.uuid4()}")
        assert response.status_code == 401

    async def test_cache_empty_for_nonexistent_pdf(
        self, client: AsyncClient, auth_headers
    ):
        response = await client.get(
            f"/v1/auto-highlight/cache/{uuid.uuid4()}",
            headers=auth_headers,
        )

        assert response.status_code == 200
        assert response.json() == []

    async def test_delete_cache_requires_auth(self, client: AsyncClient):
        response = await client.delete(f"/v1/auto-highlight/cache/{uuid.uuid4()}")
        assert response.status_code == 401

    async def test_get_cache_entry_success(
        self, client: AsyncClient, auth_headers, db_session, test_user
    ):
        pdf = await create_test_pdf(
            db_session, user_id=test_user.id, title="Test", filename="test.pdf"
        )
        await db_session.commit()

        from app.db.models import AutoHighlightCache

        cache = AutoHighlightCache(
            pdf_id=pdf.id,
            user_id=test_user.id,
            categories=["findings"],
            pages=[1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
            status="complete",
            tier="quick",
            progress_pct=100,
        )
        db_session.add(cache)
        await db_session.commit()

        response = await client.get(
            f"/v1/auto-highlight/cache/entry/{cache.id}",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(cache.id)
        assert data["status"] == "complete"
        assert data["categories"] == ["findings"]

    async def test_get_cache_entry_other_user_returns_404(
        self, client: AsyncClient, auth_headers, db_session, test_user, test_user_2
    ):
        pdf = await create_test_pdf(
            db_session, user_id=test_user_2.id, title="Other", filename="other.pdf"
        )
        await db_session.commit()

        from app.db.models import AutoHighlightCache

        cache = AutoHighlightCache(
            pdf_id=pdf.id,
            user_id=test_user_2.id,
            categories=["findings"],
            pages=[1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
            status="complete",
        )
        db_session.add(cache)
        await db_session.commit()

        response = await client.get(
            f"/v1/auto-highlight/cache/entry/{cache.id}",
            headers=auth_headers,
        )

        assert response.status_code == 404

    async def test_get_cache_entry_not_found_returns_404(
        self, client: AsyncClient, auth_headers
    ):
        response = await client.get(
            f"/v1/auto-highlight/cache/entry/{uuid.uuid4()}",
            headers=auth_headers,
        )

        assert response.status_code == 404
