import uuid
from collections import namedtuple
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient
from tests.fixtures import (
    create_test_pdf,
    create_test_annotation_set,
)

_Passage = namedtuple("_Passage", ["content"])


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


# ---------------------------------------------------------------------------
# _validate_highlights_against_chunks
# ---------------------------------------------------------------------------


class TestValidateHighlightsAgainstChunks:

    def test_exact_match_passes(self):
        from app.api.routes.auto_highlight import _validate_highlights_against_chunks

        passages = [_Passage("The algorithm achieves 95% accuracy on the test set.")]
        highlights = [{"text": "The algorithm achieves 95% accuracy on the test set."}]

        result = _validate_highlights_against_chunks(highlights, passages)

        assert len(result) == 1
        assert result[0]["text"] == highlights[0]["text"]

    def test_fuzzy_match_passes(self):
        from app.api.routes.auto_highlight import _validate_highlights_against_chunks

        passages = [_Passage("  The algorithm  achieves\n95% accuracy on the   test set.  ")]
        highlights = [{"text": "the algorithm achieves 95% accuracy on the test set."}]

        result = _validate_highlights_against_chunks(highlights, passages)

        assert len(result) == 1

    def test_short_quote_rejected(self):
        from app.api.routes.auto_highlight import _validate_highlights_against_chunks

        passages = [_Passage("This is a short quote")]
        highlights = [{"text": "short"}]

        result = _validate_highlights_against_chunks(highlights, passages)

        assert len(result) == 0

    def test_unmatched_quote_rejected(self):
        from app.api.routes.auto_highlight import _validate_highlights_against_chunks

        passages = [_Passage("The results show significant improvement.")]
        highlights = [{"text": "completely unrelated text that does not appear anywhere"}]

        result = _validate_highlights_against_chunks(highlights, passages)

        assert len(result) == 0

    def test_mixed_valid_and_invalid(self):
        from app.api.routes.auto_highlight import _validate_highlights_against_chunks

        passages = [_Passage("The model achieves state-of-the-art performance on benchmark X.")]
        highlights = [
            {"text": "state-of-the-art performance on benchmark X"},
            {"text": "unrelated text not in passages"},
            {"text": "hi"},
        ]

        result = _validate_highlights_against_chunks(highlights, passages)

        assert len(result) == 1
        assert result[0]["text"] == "state-of-the-art performance on benchmark X"

    def test_empty_highlights_returns_empty(self):
        from app.api.routes.auto_highlight import _validate_highlights_against_chunks

        result = _validate_highlights_against_chunks([], [_Passage("some text")])

        assert result == []

    def test_empty_passages_returns_empty(self):
        from app.api.routes.auto_highlight import _validate_highlights_against_chunks

        result = _validate_highlights_against_chunks([{"text": "some text"}], [])

        assert result == []


# ---------------------------------------------------------------------------
# _run_analysis_background
# ---------------------------------------------------------------------------


def _mock_session(return_scalars=None):
    session = MagicMock()

    def _add_side_effect(obj):
        if hasattr(obj, "id") and obj.id is None:
            obj.id = uuid.uuid4()

    session.add = MagicMock(side_effect=_add_side_effect)
    session.flush = AsyncMock()
    session.commit = AsyncMock()

    if return_scalars is not None:
        scalar_result = MagicMock()
        scalar_result.scalars = MagicMock(return_value=MagicMock())
        scalar_result.scalar_one_or_none = MagicMock(return_value=return_scalars)
        session.execute = AsyncMock(return_value=scalar_result)
    else:
        session.execute = AsyncMock()

    return session


@pytest.mark.asyncio
async def test_run_analysis_background_quick_success():
    from app.api.routes.auto_highlight import _run_analysis_background

    pdf_id = uuid.uuid4()
    user_id = uuid.uuid4()
    cache_id = uuid.uuid4()

    mock_user = MagicMock()
    mock_pdf = MagicMock()
    mock_pdf.id = pdf_id
    mock_pdf.title = "Test Paper"
    mock_pdf.user_id = user_id

    mock_cache = MagicMock()
    mock_cache.id = cache_id
    mock_cache.status = "pending"
    mock_cache.annotation_set_id = None
    mock_cache.progress_pct = 0

    mock_idx_status = MagicMock()
    mock_idx_status.status = "indexed"

    shortlist_chunk = MagicMock()
    shortlist_chunk.page_number = 1
    shortlist_chunk.end_page_number = None
    shortlist_chunk.content = "This is a key finding from the research paper."

    mock_highlight = {
        "text": "key finding from the research paper",
        "page": 1,
        "category": "findings",
        "reason": "Important result",
    }

    with patch(
        "app.api.routes.auto_highlight.SessionLocal"
    ) as mock_sl, patch(
        "app.api.routes.auto_highlight.IndexingService"
    ) as mock_idx_cls, patch(
        "app.api.routes.auto_highlight.LLMService"
    ) as mock_llm_cls, patch(
        "app.api.routes.auto_highlight.highlight_shortlist_service.shortlist_chunks",
        new_callable=AsyncMock,
    ) as mock_shortlist, patch(
        "app.api.routes.auto_highlight._extract_abstract_text",
        new_callable=AsyncMock,
    ) as mock_extract_abstract:
        mock_session = _mock_session()

        def _execute_results(*args, **kwargs):
            from sqlalchemy.sql.selectable import Select

            stmt = args[0] if args else None
            scalar_result = MagicMock()

            if stmt is not None and isinstance(stmt, Select):
                stmt_str = str(stmt)
                if "users" in stmt_str:
                    scalar_result.scalar_one_or_none = MagicMock(
                        return_value=mock_user
                    )
                elif "pdfs" in stmt_str and "auto_highlight_cache" not in stmt_str:
                    scalar_result.scalar_one_or_none = MagicMock(
                        return_value=mock_pdf
                    )
                elif "chunks" in stmt_str:
                    scalar_result.scalars = MagicMock()
                    scalar_result.scalars.return_value.all = MagicMock(
                        return_value=[]
                    )
                elif "auto_highlight_cache" in stmt_str:
                    scalar_result.scalar_one_or_none = MagicMock(
                        return_value=mock_cache
                    )
                    scalar_result.scalar_one = MagicMock(
                        return_value=mock_cache
                    )
                else:
                    scalar_result.scalar_one_or_none = MagicMock(return_value=None)
                scalar_result.scalars = MagicMock()
                scalar_result.scalars.return_value.all = MagicMock(return_value=[])

            return scalar_result

        mock_session.execute = AsyncMock(side_effect=_execute_results)
        mock_sl.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_sl.return_value.__aexit__ = AsyncMock(return_value=None)

        mock_idx_svc = MagicMock()
        mock_idx_svc.get_or_create_status = AsyncMock(return_value=mock_idx_status)
        mock_idx_svc.ensure_indexed = AsyncMock(return_value=mock_idx_status)
        mock_idx_cls.return_value = mock_idx_svc

        mock_llm_svc = MagicMock()
        mock_llm_svc.extract_highlights_from_passages = AsyncMock(
            return_value=[mock_highlight]
        )
        mock_llm_svc.generate_paper_queries = AsyncMock(return_value=None)
        mock_llm_svc.last_reasoning_trace = None
        mock_llm_cls.return_value = mock_llm_svc

        mock_shortlist.return_value = [shortlist_chunk]
        mock_extract_abstract.return_value = "This is the abstract text with enough content for query generation plus more."

        await _run_analysis_background(
            cache_id=cache_id,
            pdf_id=pdf_id,
            user_id=user_id,
            categories=["findings"],
            pages=[1, 2],
            provider="openrouter",
            api_key="test-key",
            model=None,
            tier="quick",
            llm_client=MagicMock(),
        )

        assert mock_cache.status == "complete"
        assert mock_cache.progress_pct == 100
        assert mock_cache.llm_response == [mock_highlight]
        assert mock_cache.annotation_set_id is not None

        from app.db.models import Annotation

        added_objects = [call.args[0] for call in mock_session.add.call_args_list]
        assert any(isinstance(obj, Annotation) for obj in added_objects)


@pytest.mark.asyncio
async def test_run_analysis_background_setup_failure_no_shortlist():
    from app.api.routes.auto_highlight import _run_analysis_background

    pdf_id = uuid.uuid4()
    user_id = uuid.uuid4()
    cache_id = uuid.uuid4()

    mock_user = MagicMock()
    mock_pdf = MagicMock()
    mock_pdf.id = pdf_id
    mock_pdf.title = "Test Paper"

    mock_idx_status = MagicMock()
    mock_idx_status.status = "not_indexed"

    with patch(
        "app.api.routes.auto_highlight.SessionLocal"
    ) as mock_sl, patch(
        "app.api.routes.auto_highlight.IndexingService"
    ) as mock_idx_cls, patch(
        "app.api.routes.auto_highlight.highlight_shortlist_service.shortlist_chunks",
        new_callable=AsyncMock,
    ) as mock_shortlist, patch(
        "app.api.routes.auto_highlight._extract_abstract_text",
        new_callable=AsyncMock,
    ) as mock_extract_abstract, patch(
        "app.api.routes.auto_highlight._mark_cache_failed",
        new_callable=AsyncMock,
    ) as mock_mark_failed:
        mock_session = _mock_session()

        def _execute_results(*args, **kwargs):
            from sqlalchemy.sql.selectable import Select

            stmt = args[0] if args else None
            scalar_result = MagicMock()

            if stmt is not None and isinstance(stmt, Select):
                stmt_str = str(stmt)
                if "users" in stmt_str:
                    scalar_result.scalar_one_or_none = MagicMock(
                        return_value=mock_user
                    )
                elif "pdfs" in stmt_str:
                    scalar_result.scalar_one_or_none = MagicMock(
                        return_value=mock_pdf
                    )
                elif "chunks" in stmt_str:
                    scalar_result.scalars = MagicMock()
                    scalar_result.scalars.return_value.all = MagicMock(return_value=[])
                else:
                    scalar_result.scalar_one_or_none = MagicMock(return_value=None)
                scalar_result.scalars = MagicMock()
                scalar_result.scalars.return_value.all = MagicMock(return_value=[])

            return scalar_result

        mock_session.execute = AsyncMock(side_effect=_execute_results)
        mock_sl.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_sl.return_value.__aexit__ = AsyncMock(return_value=None)

        mock_idx_svc = MagicMock()
        mock_idx_svc.get_or_create_status = AsyncMock(return_value=mock_idx_status)
        mock_idx_svc.ensure_indexed = AsyncMock(return_value=mock_idx_status)
        mock_idx_cls.return_value = mock_idx_svc

        mock_shortlist.return_value = []
        mock_extract_abstract.return_value = ""

        await _run_analysis_background(
            cache_id=cache_id,
            pdf_id=pdf_id,
            user_id=user_id,
            categories=["findings"],
            pages=[1, 2],
            provider="openrouter",
            api_key="test-key",
            model=None,
            tier="quick",
            llm_client=MagicMock(),
        )

        mock_mark_failed.assert_called_once()
