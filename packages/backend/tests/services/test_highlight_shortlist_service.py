"""Tests for the highlight shortlist service."""

import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.highlight_shortlist_service import (
    HighlightShortlistService,
    CandidateChunk,
)


@pytest.fixture
def mock_embedding():
    svc = MagicMock()
    svc.embed_query = AsyncMock(return_value=[0.1] * 384)
    return svc


@pytest.fixture
def shortlist_service(mock_embedding):
    return HighlightShortlistService(embedding_service=mock_embedding)


@pytest.fixture
def mock_db():
    return MagicMock()


@pytest.fixture
def sample_search_results():
    def _build(cid, page, content, score):
        r = MagicMock()
        r.chunk_id = cid
        r.page_number = page
        r.end_page_number = None
        r.content = content
        r.score = score
        r.section_title = None
        return r

    return [
        _build(str(uuid.uuid4()), 1, "key findings and results here", 0.85),
        _build(str(uuid.uuid4()), 3, "methodology and approach detailed", 0.72),
        _build(str(uuid.uuid4()), 2, "limitations discussed further", 0.60),
    ]


class TestShortlistChunks:

    async def test_shortlist_returns_deduplicated_results(
        self, shortlist_service, mock_db, sample_search_results
    ):
        pdf_id = str(uuid.uuid4())
        user_id = str(uuid.uuid4())

        with patch(
            "app.services.highlight_shortlist_service.vector_search_service.search_pdf",
            new_callable=AsyncMock,
        ) as mock_search:
            mock_search.return_value = sample_search_results

            results = await shortlist_service.shortlist_chunks(
                pdf_id=pdf_id,
                user_id=user_id,
                categories=["findings", "methods"],
                pages=[],
                tier="quick",
                db=mock_db,
            )

        assert len(results) == 3
        assert all(isinstance(c, CandidateChunk) for c in results)
        # Results should be sorted by best_score descending
        assert results[0].best_score >= results[-1].best_score

    async def test_shortlist_filters_by_pages(
        self, shortlist_service, mock_db, sample_search_results
    ):
        pdf_id = str(uuid.uuid4())

        with patch(
            "app.services.highlight_shortlist_service.vector_search_service.search_pdf",
            new_callable=AsyncMock,
        ) as mock_search:
            mock_search.return_value = sample_search_results

            results = await shortlist_service.shortlist_chunks(
                pdf_id=pdf_id,
                user_id=str(uuid.uuid4()),
                categories=["findings"],
                pages=[1],
                tier="quick",
                db=mock_db,
            )

        # Only page 1 should be included
        for c in results:
            assert c.page_number == 1

    async def test_shortlist_empty_pages_allows_all(
        self, shortlist_service, mock_db, sample_search_results
    ):
        with patch(
            "app.services.highlight_shortlist_service.vector_search_service.search_pdf",
            new_callable=AsyncMock,
        ) as mock_search:
            mock_search.return_value = sample_search_results

            results = await shortlist_service.shortlist_chunks(
                pdf_id=str(uuid.uuid4()),
                user_id=str(uuid.uuid4()),
                categories=["findings"],
                pages=[],
                tier="thorough",
                db=mock_db,
            )

        assert len(results) == 3

    async def test_shortlist_invalid_category_skipped(
        self, shortlist_service, mock_db
    ):
        with patch(
            "app.services.highlight_shortlist_service.vector_search_service.search_pdf",
            new_callable=AsyncMock,
        ) as mock_search:
            mock_search.return_value = []

            results = await shortlist_service.shortlist_chunks(
                pdf_id=str(uuid.uuid4()),
                user_id=str(uuid.uuid4()),
                categories=["nonexistent_category"],
                pages=[],
                tier="quick",
                db=mock_db,
            )

        assert results == []

    async def test_shortlist_merges_same_chunk_across_categories(
        self, shortlist_service, mock_db
    ):
        chunk_id = str(uuid.uuid4())
        r = MagicMock()
        r.chunk_id = chunk_id
        r.page_number = 1
        r.end_page_number = None
        r.content = "content appearing in multiple categories"
        r.score = 0.80
        r.section_title = None

        with patch(
            "app.services.highlight_shortlist_service.vector_search_service.search_pdf",
            new_callable=AsyncMock,
        ) as mock_search:
            mock_search.return_value = [r]

            results = await shortlist_service.shortlist_chunks(
                pdf_id=str(uuid.uuid4()),
                user_id=str(uuid.uuid4()),
                categories=["findings", "methods", "background"],
                pages=[],
                tier="quick",
                db=mock_db,
            )

        # Same chunk appearing in multiple categories should be merged
        assert len(results) == 1
        assert set(results[0].categories) == {"findings", "methods", "background"}
        assert results[0].best_score == 0.80
