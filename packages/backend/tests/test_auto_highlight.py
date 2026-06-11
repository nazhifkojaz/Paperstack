import uuid
from collections import namedtuple
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient
from tests.fixtures import (
    create_test_pdf,
    create_test_annotation_set,
)

from tests.helpers import make_resolve_result as _make_resolve_result, init_http_clients

_Passage = namedtuple("_Passage", ["content"])


@pytest.mark.asyncio
async def test_get_quota_with_key(admin_client: AsyncClient, auth_headers):
    """User with stored key should show it."""
    await admin_client.post(
        "/v1/settings/api-keys",
        json={"provider": "openrouter", "api_key": "test-key"},
        headers=auth_headers,
    )
    resp = await admin_client.get("/v1/auto-highlight/quota", headers=auth_headers)
    data = resp.json()
    assert data["has_own_key"] is True
    assert "openrouter" in data["providers"]
    assert data["openrouter_key_mode"] == "app"


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


class TestAutoHighlightOpenRouterRateLimit:
    """Tests for OpenRouter error handling in auto-highlight."""

    async def test_analyze_openrouter_429_returns_202(
        self, client: AsyncClient, auth_headers, db_session, test_user
    ):
        """When OpenRouter 429s in background, POST still returns 202."""
        init_http_clients()

        from app.services.exceptions import LLMRateLimitError

        pdf = await create_test_pdf(
            db_session,
            user_id=test_user.id,
            title="Analyze Rate Limit PDF",
            filename="analyze_rl.pdf",
            github_sha="sha_analyze_rl",
        )
        await db_session.commit()

        with (
            patch(
                "app.api.routes.auto_highlight.resolve_api_key_with_quota",
                new_callable=AsyncMock,
            ) as mock_resolve,
            patch(
                "app.api.routes.auto_highlight.LLMService",
            ) as mock_llm_cls,
            patch(
                "app.api.routes.auto_highlight.IndexingService",
            ) as mock_idx_cls,
        ):
            mock_resolve.return_value = _make_resolve_result(
                provider="openrouter",
                api_key="openrouter-key",
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
        init_http_clients()

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

        with (
            patch(
                "app.api.routes.auto_highlight.resolve_api_key_with_quota",
                new_callable=AsyncMock,
            ) as mock_resolve,
            patch(
                "app.api.routes.auto_highlight.LLMService",
            ) as mock_llm_cls,
            patch(
                "app.api.routes.auto_highlight.IndexingService",
            ) as mock_idx_cls,
        ):
            mock_resolve.return_value = _make_resolve_result(
                provider="openrouter",
                api_key="user-own-key",
                is_in_house=False,
                remaining=-1,
            )

            mock_llm = MagicMock()
            mock_llm.extract_highlights_from_passages = AsyncMock(
                return_value=mock_highlights
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

        passages = [
            _Passage("  The algorithm  achieves\n95% accuracy on the   test set.  ")
        ]
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
        highlights = [
            {"text": "completely unrelated text that does not appear anywhere"}
        ]

        result = _validate_highlights_against_chunks(highlights, passages)

        assert len(result) == 0

    def test_mixed_valid_and_invalid(self):
        from app.api.routes.auto_highlight import _validate_highlights_against_chunks

        passages = [
            _Passage("The model achieves state-of-the-art performance on benchmark X.")
        ]
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
# Extracted auto-highlight pipeline steps
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_llm_analysis_filters_hallucinated_highlights():
    from app.api.routes.auto_highlight import _run_llm_analysis

    cache_id = uuid.uuid4()
    llm_svc = MagicMock()
    llm_svc.extract_highlights_from_passages = AsyncMock(
        return_value=[
            {
                "text": "the model improves accuracy by 20 percent",
                "page": 1,
                "category": "findings",
                "reason": "Supported by the passage",
            },
            {
                "text": "a hallucinated claim that is not in the source passage",
                "page": 1,
                "category": "findings",
                "reason": "Unsupported",
            },
        ]
    )

    result = await _run_llm_analysis(
        llm_svc,
        [_Passage("The paper says the model improves accuracy by 20 percent.")],
        ["findings"],
        "openrouter",
        "test-key",
        None,
        cache_id,
        "quick",
    )

    assert result == [
        {
            "text": "the model improves accuracy by 20 percent",
            "page": 1,
            "category": "findings",
            "reason": "Supported by the passage",
        }
    ]
    llm_svc.extract_highlights_from_passages.assert_awaited_once()


@pytest.mark.asyncio
async def test_run_llm_analysis_marks_cache_failed_on_llm_error():
    from app.api.routes.auto_highlight import _run_llm_analysis

    cache_id = uuid.uuid4()
    llm_svc = MagicMock()
    llm_svc.extract_highlights_from_passages = AsyncMock(
        side_effect=RuntimeError("LLM unavailable")
    )

    with patch(
        "app.api.routes.auto_highlight._mark_cache_failed",
        new_callable=AsyncMock,
    ) as mock_mark_failed:
        result = await _run_llm_analysis(
            llm_svc,
            [_Passage("source passage")],
            ["findings"],
            "openrouter",
            "test-key",
            None,
            cache_id,
            "quick",
        )

    assert result is None
    mock_mark_failed.assert_awaited_once_with(cache_id, "LLM extraction failed")


@pytest.mark.asyncio
async def test_run_llm_analysis_retries_transient_provider_error():
    from app.api.routes.auto_highlight import _run_llm_analysis
    from app.services.exceptions import LLMProviderError

    cache_id = uuid.uuid4()
    llm_svc = MagicMock()
    llm_svc.last_reasoning_trace = None
    llm_svc.extract_highlights_from_passages = AsyncMock(
        side_effect=[
            LLMProviderError("openrouter", 503, "temporarily unavailable"),
            [
                {
                    "text": "the treatment reduced symptoms",
                    "page": 1,
                    "category": "findings",
                    "reason": "Supported by the passage",
                }
            ],
        ]
    )

    with patch("app.api.routes.auto_highlight.asyncio.sleep", new_callable=AsyncMock):
        result = await _run_llm_analysis(
            llm_svc,
            [_Passage("In the trial, the treatment reduced symptoms.")],
            ["findings"],
            "openrouter",
            "test-key",
            None,
            cache_id,
            "quick",
        )

    assert result == [
        {
            "text": "the treatment reduced symptoms",
            "page": 1,
            "category": "findings",
            "reason": "Supported by the passage",
        }
    ]
    assert llm_svc.extract_highlights_from_passages.await_count == 2


@pytest.mark.asyncio
async def test_run_llm_analysis_does_not_retry_auth_error():
    from app.api.routes.auto_highlight import _run_llm_analysis
    from app.services.exceptions import LLMProviderError

    cache_id = uuid.uuid4()
    llm_svc = MagicMock()
    llm_svc.extract_highlights_from_passages = AsyncMock(
        side_effect=LLMProviderError("openrouter", 401, "invalid key")
    )

    with patch(
        "app.api.routes.auto_highlight._mark_cache_failed",
        new_callable=AsyncMock,
    ) as mock_mark_failed:
        result = await _run_llm_analysis(
            llm_svc,
            [_Passage("source passage")],
            ["findings"],
            "openrouter",
            "test-key",
            None,
            cache_id,
            "quick",
        )

    assert result is None
    llm_svc.extract_highlights_from_passages.assert_awaited_once()
    mock_mark_failed.assert_awaited_once_with(
        cache_id,
        "LLM authentication failed. Check the configured API key.",
    )


@pytest.mark.asyncio
async def test_parse_and_store_results_no_highlights_marks_cache_failed():
    from app.api.routes.auto_highlight import _parse_and_store_results

    cache_id = uuid.uuid4()
    cache_row = MagicMock()
    cache_row.status = "pending"
    cache_row.progress_pct = 0
    cache_row.llm_response = None
    mock_session = _mock_session()

    with (
        patch("app.api.routes.auto_highlight.SessionLocal") as mock_sl,
        patch(
            "app.api.routes.auto_highlight._get_cache_row",
            new_callable=AsyncMock,
        ) as mock_get_cache_row,
    ):
        mock_sl.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_sl.return_value.__aexit__ = AsyncMock(return_value=None)
        mock_get_cache_row.return_value = cache_row

        result = await _parse_and_store_results(
            cache_id=cache_id,
            pdf_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            categories=["findings"],
            highlights=[],
            reasoning_trace=None,
        )

    assert result is False
    assert cache_row.status == "failed"
    assert cache_row.progress_pct == 100
    assert cache_row.llm_response == {
        "error": "No highlight-worthy passages found. "
        "Try a wider page range or different categories.",
    }
    mock_session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_augment_shortlist_with_custom_queries_falls_back_to_original():
    from app.api.routes.auto_highlight import _augment_shortlist_with_custom_queries

    original_shortlist = [_Passage("original shortlist passage")]
    mock_session = _mock_session()

    with (
        patch("app.api.routes.auto_highlight.SessionLocal") as mock_sl,
        patch(
            "app.api.routes.auto_highlight._chunk_for_analysis",
            new_callable=AsyncMock,
        ) as mock_chunk_for_analysis,
    ):
        mock_sl.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_sl.return_value.__aexit__ = AsyncMock(return_value=None)
        mock_chunk_for_analysis.return_value = []

        result = await _augment_shortlist_with_custom_queries(
            pdf_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            categories=["findings"],
            pages=[1, 2],
            tier="quick",
            shortlist=original_shortlist,
            custom_queries={"findings": "paper-specific findings query"},
        )

    assert result == original_shortlist
    mock_chunk_for_analysis.assert_awaited_once()


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
    session.refresh = AsyncMock()

    if return_scalars is not None:
        scalar_result = MagicMock()
        scalar_result.scalars = MagicMock(return_value=MagicMock())
        scalar_result.scalar_one_or_none = MagicMock(return_value=return_scalars)
        session.execute = AsyncMock(return_value=scalar_result)
    else:
        session.execute = AsyncMock()

    return session


@pytest.mark.asyncio
async def test_mark_cache_running_updates_status():
    from app.api.routes.auto_highlight import _mark_cache_running

    cache_row = MagicMock()
    cache_row.status = "pending"
    cache_row.progress_pct = 0
    mock_session = _mock_session(return_scalars=cache_row)

    with patch("app.api.routes.auto_highlight.SessionLocal") as mock_sl:
        mock_sl.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_sl.return_value.__aexit__ = AsyncMock(return_value=None)

        result = await _mark_cache_running(uuid.uuid4())

    assert result is True
    assert cache_row.status == "running"
    assert cache_row.progress_pct == 1
    mock_session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_mark_cache_running_does_not_override_cancelled():
    from app.api.routes.auto_highlight import _mark_cache_running

    cache_row = MagicMock()
    cache_row.status = "cancelled"
    cache_row.progress_pct = 100
    mock_session = _mock_session(return_scalars=cache_row)

    with patch("app.api.routes.auto_highlight.SessionLocal") as mock_sl:
        mock_sl.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_sl.return_value.__aexit__ = AsyncMock(return_value=None)

        result = await _mark_cache_running(uuid.uuid4())

    assert result is False
    assert cache_row.status == "cancelled"
    mock_session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_mark_cache_failed_stores_user_visible_error():
    from app.api.routes.auto_highlight import _mark_cache_failed

    cache_row = MagicMock()
    cache_row.status = "running"
    cache_row.progress_pct = 30
    cache_row.llm_response = None
    mock_session = _mock_session(return_scalars=cache_row)

    with patch("app.api.routes.auto_highlight.SessionLocal") as mock_sl:
        mock_sl.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_sl.return_value.__aexit__ = AsyncMock(return_value=None)

        await _mark_cache_failed(uuid.uuid4(), "LLM provider is unavailable")

    assert cache_row.status == "failed"
    assert cache_row.progress_pct == 100
    assert cache_row.llm_response == {"error": "LLM provider is unavailable"}
    mock_session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_mark_cache_failed_does_not_override_cancelled():
    from app.api.routes.auto_highlight import _mark_cache_failed

    cache_row = MagicMock()
    cache_row.status = "cancelled"
    cache_row.progress_pct = 100
    cache_row.llm_response = {"error": "Analysis cancelled."}
    mock_session = _mock_session(return_scalars=cache_row)

    with patch("app.api.routes.auto_highlight.SessionLocal") as mock_sl:
        mock_sl.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_sl.return_value.__aexit__ = AsyncMock(return_value=None)

        await _mark_cache_failed(uuid.uuid4(), "Unexpected analysis failure")

    assert cache_row.status == "cancelled"
    assert cache_row.llm_response == {"error": "Analysis cancelled."}
    mock_session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_mark_cache_cancelled_updates_status():
    from app.api.routes.auto_highlight import _mark_cache_cancelled

    cache_row = MagicMock()
    cache_row.id = uuid.uuid4()
    cache_row.status = "running"
    cache_row.progress_pct = 30
    cache_row.llm_response = None
    cache_row.annotation_set_id = uuid.uuid4()
    mock_session = _mock_session(return_scalars=cache_row)

    with patch("app.api.routes.auto_highlight.SessionLocal") as mock_sl:
        mock_sl.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_sl.return_value.__aexit__ = AsyncMock(return_value=None)

        result = await _mark_cache_cancelled(cache_row.id)

    assert result == cache_row
    assert cache_row.status == "cancelled"
    assert cache_row.progress_pct == 100
    assert cache_row.llm_response == {"error": "Analysis cancelled."}
    assert cache_row.annotation_set_id is None
    mock_session.commit.assert_awaited_once()
    mock_session.refresh.assert_awaited_once_with(cache_row)


@pytest.mark.asyncio
async def test_run_quick_analysis_stops_before_llm_when_cancelled():
    from app.api.routes.auto_highlight import _run_quick_analysis

    cache_id = uuid.uuid4()
    llm_svc = MagicMock()
    llm_svc.extract_highlights_from_passages = AsyncMock(return_value=[])

    with patch(
        "app.api.routes.auto_highlight._is_cache_cancelled",
        new_callable=AsyncMock,
    ) as mock_is_cancelled:
        mock_is_cancelled.return_value = True

        result = await _run_quick_analysis(
            cache_id=cache_id,
            pdf_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            categories=["findings"],
            provider="openrouter",
            api_key="test-key",
            model=None,
            llm_svc=llm_svc,
            shortlist=[_Passage("source passage")],
        )

    assert result is False
    llm_svc.extract_highlights_from_passages.assert_not_awaited()


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

    with (
        patch("app.api.routes.auto_highlight.SessionLocal") as mock_sl,
        patch("app.api.routes.auto_highlight.IndexingService") as mock_idx_cls,
        patch("app.api.routes.auto_highlight.LLMService") as mock_llm_cls,
        patch(
            "app.api.routes.auto_highlight.highlight_shortlist_service.shortlist_chunks",
            new_callable=AsyncMock,
        ) as mock_shortlist,
        patch(
            "app.api.routes.auto_highlight._extract_abstract_text",
            new_callable=AsyncMock,
        ) as mock_extract_abstract,
    ):
        mock_session = _mock_session()

        def _execute_results(*args, **kwargs):
            from sqlalchemy.sql.selectable import Select

            stmt = args[0] if args else None
            scalar_result = MagicMock()

            if stmt is not None and isinstance(stmt, Select):
                stmt_str = str(stmt)
                if "users" in stmt_str:
                    scalar_result.scalar_one_or_none = MagicMock(return_value=mock_user)
                elif "pdfs" in stmt_str and "auto_highlight_cache" not in stmt_str:
                    scalar_result.scalar_one_or_none = MagicMock(return_value=mock_pdf)
                elif "chunks" in stmt_str:
                    scalar_result.scalars = MagicMock()
                    scalar_result.scalars.return_value.all = MagicMock(return_value=[])
                elif "auto_highlight_cache" in stmt_str:
                    scalar_result.scalar_one_or_none = MagicMock(
                        return_value=mock_cache
                    )
                    scalar_result.scalar_one = MagicMock(return_value=mock_cache)
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
async def test_run_analysis_background_thorough_combines_non_empty_reasoning_traces():
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
    mock_cache.reasoning_trace = None

    mock_idx_status = MagicMock()
    mock_idx_status.status = "indexed"

    shortlist = []
    for i in range(11):
        passage = MagicMock()
        passage.content = f"batch {i + 1} source passage with an important finding"
        passage.page_number = i + 1
        passage.end_page_number = None
        shortlist.append(passage)

    with (
        patch("app.api.routes.auto_highlight.SessionLocal") as mock_sl,
        patch("app.api.routes.auto_highlight.IndexingService") as mock_idx_cls,
        patch("app.api.routes.auto_highlight.LLMService") as mock_llm_cls,
        patch(
            "app.api.routes.auto_highlight.highlight_shortlist_service.shortlist_chunks",
            new_callable=AsyncMock,
        ) as mock_shortlist,
        patch(
            "app.api.routes.auto_highlight._extract_abstract_text",
            new_callable=AsyncMock,
        ) as mock_extract_abstract,
    ):
        mock_session = _mock_session()

        def _execute_results(*args, **kwargs):
            from sqlalchemy.sql.selectable import Select

            stmt = args[0] if args else None
            scalar_result = MagicMock()

            if stmt is not None and isinstance(stmt, Select):
                stmt_str = str(stmt)
                if "users" in stmt_str:
                    scalar_result.scalar_one_or_none = MagicMock(return_value=mock_user)
                elif "pdfs" in stmt_str and "auto_highlight_cache" not in stmt_str:
                    scalar_result.scalar_one_or_none = MagicMock(return_value=mock_pdf)
                elif "auto_highlight_cache" in stmt_str:
                    scalar_result.scalar_one_or_none = MagicMock(
                        return_value=mock_cache
                    )
                    scalar_result.scalar_one = MagicMock(return_value=mock_cache)
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

        traces = ["trace one", "  ", "trace three"]
        extract_calls = []
        mock_llm_svc = MagicMock()

        async def _extract(batch, *args, **kwargs):
            idx = len(extract_calls)
            extract_calls.append(batch)
            mock_llm_svc.last_reasoning_trace = traces[idx]
            return [
                {
                    "text": batch[0].content,
                    "page": 1,
                    "category": "findings",
                    "reason": "Important result",
                }
            ]

        mock_llm_svc.extract_highlights_from_passages = AsyncMock(side_effect=_extract)
        mock_llm_svc.generate_paper_queries = AsyncMock(return_value=None)
        mock_llm_svc.last_reasoning_trace = None
        mock_llm_cls.return_value = mock_llm_svc

        mock_shortlist.return_value = shortlist
        mock_extract_abstract.return_value = (
            "This abstract has enough content to trigger query generation."
        )

        await _run_analysis_background(
            cache_id=cache_id,
            pdf_id=pdf_id,
            user_id=user_id,
            categories=["findings"],
            pages=[1, 2],
            provider="openrouter",
            api_key="test-key",
            model=None,
            tier="thorough",
            llm_client=MagicMock(),
        )

        assert len(extract_calls) == 3
        assert mock_cache.status == "complete"
        assert mock_cache.progress_pct == 100
        assert mock_cache.reasoning_trace == (
            "## Batch 1/3\ntrace one\n\n## Batch 3/3\ntrace three"
        )


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

    mock_cache = MagicMock()
    mock_cache.id = cache_id
    mock_cache.status = "pending"
    mock_cache.progress_pct = 0

    mock_idx_status = MagicMock()
    mock_idx_status.status = "not_indexed"

    with (
        patch("app.api.routes.auto_highlight.SessionLocal") as mock_sl,
        patch("app.api.routes.auto_highlight.IndexingService") as mock_idx_cls,
        patch(
            "app.api.routes.auto_highlight.highlight_shortlist_service.shortlist_chunks",
            new_callable=AsyncMock,
        ) as mock_shortlist,
        patch(
            "app.api.routes.auto_highlight._extract_abstract_text",
            new_callable=AsyncMock,
        ) as mock_extract_abstract,
        patch(
            "app.api.routes.auto_highlight._mark_cache_failed",
            new_callable=AsyncMock,
        ) as mock_mark_failed,
    ):
        mock_session = _mock_session()

        def _execute_results(*args, **kwargs):
            from sqlalchemy.sql.selectable import Select

            stmt = args[0] if args else None
            scalar_result = MagicMock()

            if stmt is not None and isinstance(stmt, Select):
                stmt_str = str(stmt)
                if "users" in stmt_str:
                    scalar_result.scalar_one_or_none = MagicMock(return_value=mock_user)
                elif "pdfs" in stmt_str:
                    scalar_result.scalar_one_or_none = MagicMock(return_value=mock_pdf)
                elif "auto_highlight_cache" in stmt_str:
                    scalar_result.scalar_one_or_none = MagicMock(
                        return_value=mock_cache
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
