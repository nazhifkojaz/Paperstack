import pytest
import tempfile
from pathlib import Path
from httpx import AsyncClient
from unittest.mock import AsyncMock, MagicMock, patch
from tests.fixtures import (
    create_test_pdf,
    create_test_annotation_set,
)


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
async def test_analyze_no_key_no_quota(
    client: AsyncClient, auth_headers, db_session, test_user, mock_llm_response
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


class TestAutoHighlightOpenRouterFallback:
    """Tests for OpenRouter 429 → paid fallback in auto-highlight."""

    async def test_analyze_openrouter_429_falls_back_to_paid(
        self, client: AsyncClient, auth_headers, db_session, test_user
    ):
        """When OpenRouter 429s on auto-highlight, fall back to paid provider."""
        _init_http_clients()

        from app.services.exceptions import LLMRateLimitError

        pdf = await create_test_pdf(
            db_session,
            user_id=test_user.id,
            title="Analyze Fallback PDF",
            filename="analyze_fb.pdf",
            github_sha="sha_analyze_fb",
        )
        await db_session.commit()

        # Create a temp file for the download mock
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(b"%PDF-1.4 test content")
            tmp_path = Path(tmp.name)

        try:
            mock_highlights = [
                {
                    "text": "Key finding",
                    "page": 1,
                    "category": "findings",
                    "reason": "Important",
                },
            ]

            mock_backend = AsyncMock()
            mock_backend.download_to_tempfile = AsyncMock(return_value=tmp_path)

            with patch(
                "app.api.routes.auto_highlight.api_key_service.resolve_for_auto_highlight",
                new_callable=AsyncMock,
            ) as mock_resolve, patch(
                "app.api.routes.auto_highlight.api_key_service.resolve_paid_fallback",
                new_callable=AsyncMock,
            ) as mock_paid_resolve, patch(
                "app.api.routes.auto_highlight.api_key_service.decrement_quota",
                new_callable=AsyncMock,
                return_value=4,
            ) as mock_decrement, patch(
                "app.services.storage.factory.get_storage_backend",
                new_callable=AsyncMock,
                return_value=mock_backend,
            ), patch(
                "app.api.routes.auto_highlight.extract_text_with_pages",
                return_value=("Paper text content", 5, 5),
            ), patch(
                "app.api.routes.auto_highlight.is_text_pdf",
                return_value=True,
            ), patch(
                "app.api.routes.auto_highlight.LLMService",
            ) as mock_llm_cls:
                mock_resolve.return_value = MagicMock(
                    provider="openrouter",
                    api_key="openrouter-key",
                    is_in_house=True,
                    quota_remaining=5,
                )
                mock_paid_resolve.return_value = MagicMock(
                    provider="gemini",
                    api_key="gemini-key",
                    is_in_house=True,
                    quota_remaining=5,
                )

                mock_llm = MagicMock()
                mock_llm.analyze_paper = AsyncMock(
                    side_effect=[
                        LLMRateLimitError("openrouter"),
                        mock_highlights,
                    ]
                )
                mock_llm_cls.return_value = mock_llm

                resp = await client.post(
                    "/v1/auto-highlight/analyze",
                    json={"pdf_id": str(pdf.id), "categories": ["findings"]},
                    headers=auth_headers,
                )

                assert resp.status_code == 200
                data = resp.json()
                assert data["provider_fallback"] is True
                assert data["highlights_count"] == 1

                mock_paid_resolve.assert_called_once()
                mock_decrement.assert_called_once()
        finally:
            tmp_path.unlink(missing_ok=True)

    async def test_analyze_openrouter_429_no_paid_fallback_returns_402(
        self, client: AsyncClient, auth_headers, db_session, test_user
    ):
        """When OpenRouter 429s and no paid fallback available, return 402."""
        _init_http_clients()

        from app.services.exceptions import LLMRateLimitError, QuotaExhaustedError

        pdf = await create_test_pdf(
            db_session,
            user_id=test_user.id,
            title="Analyze No Fallback PDF",
            filename="analyze_nofb.pdf",
            github_sha="sha_analyze_nofb",
        )
        await db_session.commit()

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(b"%PDF-1.4 test content")
            tmp_path = Path(tmp.name)

        try:
            mock_backend = AsyncMock()
            mock_backend.download_to_tempfile = AsyncMock(return_value=tmp_path)

            with patch(
                "app.api.routes.auto_highlight.api_key_service.resolve_for_auto_highlight",
                new_callable=AsyncMock,
            ) as mock_resolve, patch(
                "app.api.routes.auto_highlight.api_key_service.resolve_paid_fallback",
                new_callable=AsyncMock,
            ) as mock_paid_resolve, patch(
                "app.services.storage.factory.get_storage_backend",
                new_callable=AsyncMock,
                return_value=mock_backend,
            ), patch(
                "app.api.routes.auto_highlight.extract_text_with_pages",
                return_value=("Paper text content", 5, 5),
            ), patch(
                "app.api.routes.auto_highlight.is_text_pdf",
                return_value=True,
            ), patch(
                "app.api.routes.auto_highlight.LLMService",
            ) as mock_llm_cls:
                mock_resolve.return_value = MagicMock(
                    provider="openrouter",
                    api_key="openrouter-key",
                    is_in_house=True,
                    quota_remaining=5,
                )
                mock_paid_resolve.side_effect = QuotaExhaustedError(
                    "free_uses_remaining", remaining=0
                )

                mock_llm = MagicMock()
                mock_llm.analyze_paper = AsyncMock(
                    side_effect=LLMRateLimitError("openrouter")
                )
                mock_llm_cls.return_value = mock_llm

                resp = await client.post(
                    "/v1/auto-highlight/analyze",
                    json={"pdf_id": str(pdf.id), "categories": ["findings"]},
                    headers=auth_headers,
                )

                assert resp.status_code == 402
        finally:
            tmp_path.unlink(missing_ok=True)

    async def test_analyze_openrouter_no_quota_decrement(
        self, client: AsyncClient, auth_headers, db_session, test_user
    ):
        """When OpenRouter succeeds, quota should NOT be decremented."""
        _init_http_clients()

        pdf = await create_test_pdf(
            db_session,
            user_id=test_user.id,
            title="Analyze OpenRouter OK",
            filename="analyze_or_ok.pdf",
            github_sha="sha_analyze_or_ok",
        )
        await db_session.commit()

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(b"%PDF-1.4 test content")
            tmp_path = Path(tmp.name)

        try:
            mock_highlights = [
                {
                    "text": "A finding",
                    "page": 1,
                    "category": "findings",
                    "reason": "Result",
                },
            ]

            mock_backend = AsyncMock()
            mock_backend.download_to_tempfile = AsyncMock(return_value=tmp_path)

            with patch(
                "app.api.routes.auto_highlight.api_key_service.resolve_for_auto_highlight",
                new_callable=AsyncMock,
            ) as mock_resolve, patch(
                "app.api.routes.auto_highlight.api_key_service.decrement_quota",
                new_callable=AsyncMock,
                return_value=4,
            ) as mock_decrement, patch(
                "app.services.storage.factory.get_storage_backend",
                new_callable=AsyncMock,
                return_value=mock_backend,
            ), patch(
                "app.api.routes.auto_highlight.extract_text_with_pages",
                return_value=("Paper text content", 5, 5),
            ), patch(
                "app.api.routes.auto_highlight.is_text_pdf",
                return_value=True,
            ), patch(
                "app.api.routes.auto_highlight.LLMService",
            ) as mock_llm_cls:
                mock_resolve.return_value = MagicMock(
                    provider="openrouter",
                    api_key="openrouter-key",
                    is_in_house=True,
                    quota_remaining=5,
                )

                mock_llm = MagicMock()
                mock_llm.analyze_paper = AsyncMock(return_value=mock_highlights)
                mock_llm_cls.return_value = mock_llm

                resp = await client.post(
                    "/v1/auto-highlight/analyze",
                    json={"pdf_id": str(pdf.id), "categories": ["findings"]},
                    headers=auth_headers,
                )

                assert resp.status_code == 200
                data = resp.json()
                assert data["provider_fallback"] is False
                # Quota should NOT be decremented for free OpenRouter
                mock_decrement.assert_not_called()
        finally:
            tmp_path.unlink(missing_ok=True)
