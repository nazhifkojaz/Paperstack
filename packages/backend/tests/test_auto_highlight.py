import pytest
from httpx import AsyncClient
from unittest.mock import AsyncMock, MagicMock, patch
from tests.fixtures import (
    create_test_pdf,
    create_test_annotation_set,
)


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
async def test_analyze_no_key_no_quota(
    client: AsyncClient, auth_headers, db_session, test_user
):
    """Should fail with 402 if no key and no quota."""
    from app.main import app
    from app.core.http_client import HTTPClientState

    if not hasattr(app.state, "llm_http_client"):
        HTTPClientState.init_http_clients(app)

    pdf = await create_test_pdf(
        db_session,
        user_id=test_user.id,
        title="Analyze Test",
        filename="analyze.pdf",
        github_sha="sha_analyze",
        page_count=4,
    )
    await db_session.commit()

    # Exhaust the user's free quota
    from app.db.models import UserUsageQuota
    from sqlalchemy import select

    result = await db_session.execute(
        select(UserUsageQuota).where(UserUsageQuota.user_id == test_user.id)
    )
    quota = result.scalar_one_or_none()
    if quota:
        quota.free_uses_remaining = 0
    else:
        quota = UserUsageQuota(
            user_id=test_user.id,
            free_uses_remaining=0,
            chat_uses_remaining=20,
            explain_uses_remaining=20,
        )
        db_session.add(quota)
    await db_session.commit()

    resp = await client.post(
        "/v1/auto-highlight/analyze",
        json={"pdf_id": str(pdf.id), "categories": ["findings", "methods"]},
        headers=auth_headers,
    )

    assert resp.status_code == 402


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


@pytest.mark.asyncio
async def test_cache_delete(client: AsyncClient, auth_headers, db_session, test_user):
    """Test deleting a cached highlight result."""
    from app.db.models import AutoHighlightCache, AnnotationSet
    import uuid

    pdf = await create_test_pdf(
        db_session,
        user_id=test_user.id,
        title="Cache Delete Test",
        filename="cache_del.pdf",
        github_sha="sha_cache_del",
    )
    ann_set = await create_test_annotation_set(
        db_session, pdf_id=pdf.id, user_id=test_user.id, name="Auto Highlights"
    )
    cache_entry = AutoHighlightCache(
        id=uuid.uuid4(),
        pdf_id=pdf.id,
        user_id=test_user.id,
        annotation_set_id=ann_set.id,
        categories=["findings"],
        pages=[1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
    )
    db_session.add(cache_entry)
    await db_session.commit()

    resp = await client.delete(
        f"/v1/auto-highlight/cache/{cache_entry.id}",
        headers=auth_headers,
    )

    assert resp.status_code == 204

    # Verify cache entry is gone
    from sqlalchemy import select

    result = await db_session.execute(
        select(AutoHighlightCache).where(AutoHighlightCache.id == cache_entry.id)
    )
    assert result.scalar_one_or_none() is None

    # Verify annotation set is also deleted
    result = await db_session.execute(
        select(AnnotationSet).where(AnnotationSet.id == ann_set.id)
    )
    assert result.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_cache_delete_not_found(client: AsyncClient, auth_headers):
    """Test deleting non-existent cache entry returns 404."""
    import uuid

    resp = await client.delete(
        f"/v1/auto-highlight/cache/{uuid.uuid4()}",
        headers=auth_headers,
    )
    assert resp.status_code == 404


def _init_http_clients():
    """Initialize HTTP clients on app state for auto-highlight tests."""
    from app.main import app
    from app.core.http_client import HTTPClientState

    if not hasattr(app.state, "llm_http_client"):
        HTTPClientState.init_http_clients(app)


class TestAutoHighlightOpenRouterRateLimit:
    """Tests for OpenRouter error handling in auto-highlight."""

    async def test_analyze_openrouter_429_returns_202(
        self, client: AsyncClient, auth_headers, db_session, test_user
    ):
        """When OpenRouter 429s in background, POST still returns 202."""
        _init_http_clients()

        from app.services.exceptions import LLMRateLimitError

        pdf = await create_test_pdf(
            db_session,
            user_id=test_user.id,
            title="Analyze Rate Limit PDF",
            filename="analyze_rl.pdf",
            github_sha="sha_analyze_rl",
        )
        await db_session.commit()

        with patch(
            "app.api.routes.auto_highlight.resolve_api_key_with_quota",
            new_callable=AsyncMock,
        ) as mock_resolve, patch(
            "app.api.routes.auto_highlight.LLMService",
        ) as mock_llm_cls, patch(
            "app.api.routes.auto_highlight.IndexingService",
        ) as mock_idx_cls:
            mock_resolve.return_value = MagicMock(
                provider="openrouter",
                api_key="openrouter-key",
                is_in_house=True,
                quota_remaining=5,
            )

            mock_llm = MagicMock()
            mock_llm.extract_highlights_from_passages = AsyncMock(
                side_effect=LLMRateLimitError("openrouter")
            )
            mock_llm_cls.return_value = mock_llm

            mock_idx_svc = MagicMock()
            mock_idx_status = MagicMock()
            mock_idx_status.status = "indexed"
            mock_idx_svc.get_or_create_status = AsyncMock(return_value=mock_idx_status)
            mock_idx_svc.ensure_indexed = AsyncMock(return_value=mock_idx_status)
            mock_idx_cls.return_value = mock_idx_svc

            resp = await client.post(
                "/v1/auto-highlight/analyze",
                json={"pdf_id": str(pdf.id), "categories": ["findings"]},
                headers=auth_headers,
            )

            assert resp.status_code == 202

    async def test_analyze_user_own_key_skips_openrouter(
        self, client: AsyncClient, auth_headers, db_session, test_user
    ):
        """When user has their own key, OpenRouter is never tried for auto-highlight."""
        _init_http_clients()

        pdf = await create_test_pdf(
            db_session,
            user_id=test_user.id,
            title="Analyze User Key PDF",
            filename="analyze_userkey.pdf",
            github_sha="sha_analyze_userkey",
        )
        await db_session.commit()

        mock_highlights = [
            {
                "text": "User key finding",
                "page": 1,
                "category": "findings",
                "reason": "Found by user's model",
            },
        ]

        with patch(
            "app.api.routes.auto_highlight.resolve_api_key_with_quota",
            new_callable=AsyncMock,
        ) as mock_resolve, patch(
            "app.api.routes.auto_highlight.LLMService",
        ) as mock_llm_cls, patch(
            "app.api.routes.auto_highlight.IndexingService",
        ) as mock_idx_cls:
            mock_resolve.return_value = MagicMock(
                provider="anthropic",
                api_key="user-own-key",
                is_in_house=False,
                quota_remaining=None,
            )

            mock_llm = MagicMock()
            mock_llm.extract_highlights_from_passages = AsyncMock(return_value=mock_highlights)
            mock_llm_cls.return_value = mock_llm

            mock_idx_svc = MagicMock()
            mock_idx_status = MagicMock()
            mock_idx_status.status = "indexed"
            mock_idx_svc.get_or_create_status = AsyncMock(return_value=mock_idx_status)
            mock_idx_svc.ensure_indexed = AsyncMock(return_value=mock_idx_status)
            mock_idx_cls.return_value = mock_idx_svc

            resp = await client.post(
                "/v1/auto-highlight/analyze",
                json={"pdf_id": str(pdf.id), "categories": ["findings"]},
                headers=auth_headers,
            )

            assert resp.status_code == 202
