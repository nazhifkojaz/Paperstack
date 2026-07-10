"""Tests for the vector search service (Phase 3.3: proximity boosting, Phase 4.1: hybrid search)."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from app.services.vector_search_service import VectorSearchService


# ---------------------------------------------------------------------------
# Module-level row factories (shared across test classes)
# ---------------------------------------------------------------------------


def _make_row(id_, page, content, score):
    row = MagicMock()
    row.id = id_
    row.page_number = page
    row.content = content
    row.score = score
    return row


def _make_hybrid_row(id_, page, content, score, end_page_number=None):
    row = MagicMock()
    row.id = id_
    row.page_number = page
    row.end_page_number = end_page_number
    row.content = content
    row.combined_score = score
    return row


def _make_hybrid_collection_row(
    id_, pdf_id, pdf_title, page, content, score, end_page_number=None
):
    row = MagicMock()
    row.id = id_
    row.pdf_id = pdf_id
    row.pdf_title = pdf_title
    row.page_number = page
    row.end_page_number = end_page_number
    row.content = content
    row.combined_score = score
    return row


def _make_hybrid_all_row(pdf_id, pdf_title, page, content, score):
    row = MagicMock()
    row.id = uuid4()
    row.pdf_id = pdf_id
    row.pdf_title = pdf_title
    row.page_number = page
    row.end_page_number = None
    row.content = content
    row.combined_score = score
    return row


def _make_row_all(pdf_id, pdf_title, page, content, score):
    row = MagicMock()
    row.pdf_id = pdf_id
    row.pdf_title = pdf_title
    row.page_number = page
    row.content = content
    row.score = score
    return row


def _execute_returning(mock_db, rows):
    """Helper: configure mock_db.execute to return an iterable of rows."""
    mock_result = MagicMock()
    mock_result.__iter__ = lambda self: iter(rows)
    mock_db.execute = AsyncMock(return_value=mock_result)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_rows():
    """Mock DB rows for search results."""
    return [
        _make_row(uuid4(), i + 1, f"Content on page {i + 1}", 0.8 - i * 0.05)
        for i in range(5)
    ]


@pytest.fixture
def sample_rows_collection():
    """Mock DB rows for collection search results."""
    rows = []
    for i in range(3):
        row = MagicMock()
        row.id = uuid4()
        row.pdf_id = uuid4()
        row.pdf_title = f"Paper {i + 1}"
        row.page_number = i + 1
        row.content = f"Content from paper {i + 1}, page {i + 1}"
        row.score = 0.9 - i * 0.1
        rows.append(row)
    return rows


class TestSearchPdfProximityBoost:
    """Tests for page proximity boosting in search_pdf (Phase 3.3)."""

    async def test_proximity_boost_exact_page(self, sample_rows):
        """Chunks on the same page should get the maximum boost."""
        mock_db = AsyncMock()
        _execute_returning(mock_db, sample_rows)

        service = VectorSearchService()
        results = await service.search_pdf(
            query_vector=[0.1] * 384,
            pdf_id=uuid4(),
            user_id=uuid4(),
            top_k=5,
            db=mock_db,
            current_page=1,
        )

        assert len(results) == 5
        assert results[0].page_number == 1
        assert abs(results[0].score - 0.8 * 1.1) < 0.001

    async def test_proximity_boost_decay(self, sample_rows):
        """Boost should decay linearly with distance."""
        mock_db = AsyncMock()
        _execute_returning(mock_db, sample_rows)

        service = VectorSearchService()
        results = await service.search_pdf(
            query_vector=[0.1] * 384,
            pdf_id=uuid4(),
            user_id=uuid4(),
            top_k=5,
            db=mock_db,
            current_page=3,
        )

        page3 = next(r for r in results if r.page_number == 3)
        assert abs(page3.score - 0.7 * 1.1) < 0.001
        page4 = next(r for r in results if r.page_number == 4)
        assert abs(page4.score - 0.65 * 1.09) < 0.001

    async def test_proximity_boost_beyond_window(self, sample_rows):
        """Chunks beyond 10 pages should get no boost."""
        mock_db = AsyncMock()
        _execute_returning(mock_db, sample_rows)

        service = VectorSearchService()
        results = await service.search_pdf(
            query_vector=[0.1] * 384,
            pdf_id=uuid4(),
            user_id=uuid4(),
            top_k=5,
            db=mock_db,
            current_page=20,
        )

        for r in results:
            distance = abs(r.page_number - 20)
            assert distance >= 10
            original = 0.8 - (r.page_number - 1) * 0.05
            assert abs(r.score - original) < 0.001

    async def test_proximity_boost_none_current_page(self, sample_rows):
        """When current_page is None, behavior should be unchanged."""
        mock_db = AsyncMock()
        _execute_returning(mock_db, sample_rows)

        service = VectorSearchService()
        results = await service.search_pdf(
            query_vector=[0.1] * 384,
            pdf_id=uuid4(),
            user_id=uuid4(),
            top_k=5,
            db=mock_db,
            current_page=None,
        )

        for r in results:
            original = 0.8 - (r.page_number - 1) * 0.05
            assert abs(r.score - original) < 0.001

    async def test_proximity_boost_reorders_results(self):
        """Proximity boost should reorder results when a lower-scoring page is closer."""
        mock_db = AsyncMock()
        rows = [
            _make_row(uuid4(), 10, "Page 10 content", 0.93),
            _make_row(uuid4(), 1, "Page 1 content", 0.91),
        ]
        _execute_returning(mock_db, rows)

        service = VectorSearchService()
        results = await service.search_pdf(
            query_vector=[0.1] * 384,
            pdf_id=uuid4(),
            user_id=uuid4(),
            top_k=2,
            db=mock_db,
            current_page=1,
        )

        assert results[0].page_number == 1
        assert abs(results[0].score - 0.91 * 1.1) < 0.001
        assert results[1].page_number == 10
        assert abs(results[1].score - 0.93 * 1.01) < 0.001


class TestSearchCollection:
    """Tests for collection search (no proximity boost)."""

    async def test_search_collection_returns_pdf_metadata(self, sample_rows_collection):
        """Collection search should include pdf_id and pdf_title."""
        mock_db = AsyncMock()
        _execute_returning(mock_db, sample_rows_collection)

        service = VectorSearchService()
        results = await service.search_collection(
            query_vector=[0.1] * 384,
            collection_id=uuid4(),
            user_id=uuid4(),
            top_k=3,
            db=mock_db,
        )

        assert len(results) == 3
        for r in results:
            assert r.pdf_id is not None
            assert r.pdf_title is not None
            assert r.content is not None


class TestHybridSearchPdf:
    """Tests for hybrid search (Phase 4.1: keyword + semantic)."""

    async def test_hybrid_search_uses_combined_score(self):
        """Hybrid search should use combined_score column from CTE query."""
        mock_db = AsyncMock()
        _execute_returning(
            mock_db,
            [
                _make_hybrid_row(uuid4(), 1, "BERT model content", 0.85),
                _make_hybrid_row(uuid4(), 3, "Neural network content", 0.72),
                _make_hybrid_row(uuid4(), 5, "Other content", 0.60),
            ],
        )

        service = VectorSearchService()
        results = await service.search_pdf(
            query_vector=[0.1] * 384,
            pdf_id=uuid4(),
            user_id=uuid4(),
            top_k=3,
            db=mock_db,
            query_text="BERT model",
        )

        assert len(results) == 3
        assert results[0].content == "BERT model content"
        assert results[0].score == 0.85

    async def test_hybrid_search_falls_back_to_vector_only(self, sample_rows):
        """Without query_text, should use pure vector search."""
        mock_db = AsyncMock()
        _execute_returning(mock_db, sample_rows)

        service = VectorSearchService()
        results = await service.search_pdf(
            query_vector=[0.1] * 384,
            pdf_id=uuid4(),
            user_id=uuid4(),
            top_k=5,
            db=mock_db,
        )

        assert len(results) == 5
        for r in results:
            original = 0.8 - (r.page_number - 1) * 0.05
            assert abs(r.score - original) < 0.001

    async def test_hybrid_search_with_proximity_boost(self):
        """Hybrid search should still support proximity boosting."""
        mock_db = AsyncMock()
        _execute_returning(
            mock_db,
            [
                _make_hybrid_row(uuid4(), 1, "Page 1 content", 0.80),
                _make_hybrid_row(uuid4(), 2, "Page 2 content", 0.60),
            ],
        )

        service = VectorSearchService()
        results = await service.search_pdf(
            query_vector=[0.1] * 384,
            pdf_id=uuid4(),
            user_id=uuid4(),
            top_k=2,
            db=mock_db,
            query_text="test",
            current_page=1,
        )

        assert len(results) == 2
        assert results[0].page_number == 1
        assert abs(results[0].score - 0.80 * 1.1) < 0.001


class TestHybridSearchCollection:
    """Tests for hybrid search in collection (Phase 4.1)."""

    async def test_hybrid_collection_search_uses_combined_score(self):
        """Hybrid collection search should use combined_score column."""
        mock_db = AsyncMock()
        _execute_returning(
            mock_db,
            [
                _make_hybrid_collection_row(
                    uuid4(), uuid4(), "Paper 1", 1, "BERT transformer content", 0.88
                ),
                _make_hybrid_collection_row(
                    uuid4(), uuid4(), "Paper 2", 3, "Neural network content", 0.75
                ),
            ],
        )

        service = VectorSearchService()
        results = await service.search_collection(
            query_vector=[0.1] * 384,
            collection_id=uuid4(),
            user_id=uuid4(),
            top_k=2,
            db=mock_db,
            query_text="BERT transformer",
        )

        assert len(results) == 2
        assert results[0].pdf_title == "Paper 1"
        assert results[0].score == 0.88
        assert results[0].pdf_id is not None

    async def test_hybrid_collection_falls_back_to_vector_only(
        self, sample_rows_collection
    ):
        """Without query_text, collection search should use pure vector."""
        mock_db = AsyncMock()
        _execute_returning(mock_db, sample_rows_collection)

        service = VectorSearchService()
        results = await service.search_collection(
            query_vector=[0.1] * 384,
            collection_id=uuid4(),
            user_id=uuid4(),
            top_k=3,
            db=mock_db,
        )

        assert len(results) == 3
        for r in results:
            assert r.pdf_id is not None
            assert r.pdf_title is not None


class TestHybridSearchAll:
    """Tests for hybrid search across all PDFs (Phase 4.1)."""

    async def test_hybrid_all_search_uses_combined_score(self):
        """Hybrid all-PDF search should use combined_score column."""
        mock_db = AsyncMock()
        _execute_returning(
            mock_db,
            [
                _make_hybrid_all_row(uuid4(), "Paper A", 5, "BERT model results", 0.90),
                _make_hybrid_all_row(
                    uuid4(), "Paper B", 2, "Transformer architecture", 0.82
                ),
            ],
        )

        service = VectorSearchService()
        results = await service.search_all(
            query_vector=[0.1] * 384,
            user_id=uuid4(),
            limit=2,
            db=mock_db,
            query_text="BERT model",
        )

        assert len(results) == 2
        assert results[0].pdf_title == "Paper A"
        assert results[0].score == 0.90

    async def test_hybrid_all_search_deduplicates_by_pdf_id(self):
        """Should deduplicate results to one chunk per PDF."""
        mock_db = AsyncMock()
        pdf_a = uuid4()
        pdf_b = uuid4()
        _execute_returning(
            mock_db,
            [
                _make_hybrid_all_row(pdf_a, "Paper A", 1, "Content A1", 0.90),
                _make_hybrid_all_row(pdf_a, "Paper A", 3, "Content A2", 0.85),
                _make_hybrid_all_row(pdf_b, "Paper B", 2, "Content B1", 0.80),
            ],
        )

        service = VectorSearchService()
        results = await service.search_all(
            query_vector=[0.1] * 384,
            user_id=uuid4(),
            limit=5,
            db=mock_db,
            query_text="test",
        )

        pdf_ids = {r.pdf_id for r in results}
        assert len(pdf_ids) == 2
        assert str(pdf_a) in pdf_ids
        assert str(pdf_b) in pdf_ids

    async def test_hybrid_all_falls_back_to_vector_only(self):
        """Without query_text, should use pure vector with dedup."""
        mock_db = AsyncMock()
        pdf_id = uuid4()
        _execute_returning(
            mock_db,
            [
                _make_row_all(pdf_id, "Paper A", 1, "Content A", 0.90),
                _make_row_all(pdf_id, "Paper A", 3, "Content A2", 0.85),
                _make_row_all(uuid4(), "Paper B", 2, "Content B", 0.80),
            ],
        )

        service = VectorSearchService()
        results = await service.search_all(
            query_vector=[0.1] * 384,
            user_id=uuid4(),
            limit=5,
            db=mock_db,
        )

        assert len(results) == 2
        for r in results:
            assert r.chunk_id is None


class TestHybridSearchWeights:
    """Tests for configurable hybrid search weights (CQ-3)."""

    @pytest.mark.parametrize(
        "method_name,method_kwargs",
        [
            ("search_pdf", {"pdf_id": "uuid4", "user_id": "uuid4", "top_k": 3}),
            (
                "search_collection",
                {"collection_id": "uuid4", "user_id": "uuid4", "top_k": 3},
            ),
            ("search_all", {"user_id": "uuid4", "limit": 3}),
        ],
    )
    async def test_hybrid_passes_weight_params(self, method_name, method_kwargs):
        """All hybrid search methods should pass sem_weight and kw_weight to SQL."""
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.__iter__ = lambda self: iter([])
        mock_db.execute = AsyncMock(return_value=mock_result)

        service = VectorSearchService()
        method = getattr(service, method_name)

        # Build kwargs dynamically, using uuid4() where needed
        kwargs = {
            "query_vector": [0.1] * 384,
            "db": mock_db,
            "query_text": "test query",
        }
        for k, v in method_kwargs.items():
            kwargs[k] = uuid4() if v == "uuid4" else v

        await method(**kwargs)

        call_args = mock_db.execute.call_args
        params = call_args[0][1]
        assert params["sem_weight"] == 0.7
        assert params["kw_weight"] == 0.3

    async def test_search_pdf_vector_only_no_weight_params(self):
        """Pure vector search should NOT pass weight params."""
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.__iter__ = lambda self: iter([])
        mock_db.execute = AsyncMock(return_value=mock_result)

        service = VectorSearchService()
        await service.search_pdf(
            query_vector=[0.1] * 384,
            pdf_id=uuid4(),
            user_id=uuid4(),
            top_k=3,
            db=mock_db,
        )

        call_args = mock_db.execute.call_args
        params = call_args[0][1]
        assert "sem_weight" not in params
        assert "kw_weight" not in params


class TestErrorHandling:
    """Negative / edge-case tests for error handling (TG-2).

    The service has no internal try/except — exceptions from the DB layer
    propagate to callers.  These tests verify that behavior so callers know
    what to expect and future changes don't silently swallow errors.
    """

    # --- Database errors propagate -------------------------------------------------

    @pytest.mark.parametrize(
        "method_name,method_kwargs,error_msg",
        [
            (
                "search_pdf",
                {"pdf_id": "uuid4", "user_id": "uuid4", "top_k": 3},
                "connection lost",
            ),
            (
                "search_collection",
                {"collection_id": "uuid4", "user_id": "uuid4", "top_k": 3},
                "timeout",
            ),
            ("search_all", {"user_id": "uuid4", "limit": 3}, "deadlock"),
        ],
    )
    async def test_db_error_propagates(self, method_name, method_kwargs, error_msg):
        """DB errors should propagate from all search methods (not be swallowed)."""
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(side_effect=Exception(error_msg))

        service = VectorSearchService()
        method = getattr(service, method_name)
        kwargs = {"query_vector": [0.1] * 384, "db": mock_db}
        for k, v in method_kwargs.items():
            kwargs[k] = uuid4() if v == "uuid4" else v

        with pytest.raises(Exception, match=error_msg):
            await method(**kwargs)

    # --- Empty query vector --------------------------------------------------------

    async def test_empty_vector_formats_as_empty_brackets(self):
        """An empty query_vector should produce a vec_str and hit the DB."""
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.__iter__ = lambda self: iter([])
        mock_db.execute = AsyncMock(return_value=mock_result)

        service = VectorSearchService()
        results = await service.search_pdf(
            query_vector=[],
            pdf_id=uuid4(),
            user_id=uuid4(),
            top_k=3,
            db=mock_db,
        )

        assert results == []
        assert mock_db.execute.call_args[0][1]["vec"] == "[]"

    # --- Non-UUID string identifiers -----------------------------------------------

    async def test_string_user_id_forwarded_as_is(self):
        """String (non-UUID) user_id should be forwarded to SQL without error."""
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.__iter__ = lambda self: iter([])
        mock_db.execute = AsyncMock(return_value=mock_result)

        service = VectorSearchService()
        results = await service.search_pdf(
            query_vector=[0.1] * 384,
            pdf_id=uuid4(),
            user_id="not-a-uuid",
            top_k=3,
            db=mock_db,
        )

        assert results == []
        assert mock_db.execute.call_args[0][1]["user_id"] == "not-a-uuid"

    async def test_string_pdf_id_forwarded_as_is(self):
        """String (non-UUID) pdf_id should be forwarded to SQL without error."""
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.__iter__ = lambda self: iter([])
        mock_db.execute = AsyncMock(return_value=mock_result)

        service = VectorSearchService()
        results = await service.search_pdf(
            query_vector=[0.1] * 384,
            pdf_id="invalid-pdf-id",
            user_id=uuid4(),
            top_k=3,
            db=mock_db,
        )

        assert results == []
        assert mock_db.execute.call_args[0][1]["pdf_id"] == "invalid-pdf-id"

    # --- query_text edge cases -----------------------------------------------------

    async def test_empty_query_text_uses_vector_path(self):
        """Empty string query_text is falsy, so it should use the vector-only path."""
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.__iter__ = lambda self: iter([])
        mock_db.execute = AsyncMock(return_value=mock_result)

        service = VectorSearchService()
        results = await service.search_pdf(
            query_vector=[0.1] * 384,
            pdf_id=uuid4(),
            user_id=uuid4(),
            top_k=3,
            db=mock_db,
            query_text="",
        )

        params = mock_db.execute.call_args[0][1]
        assert "query" not in params
        assert results == []

    async def test_special_characters_in_query_text(self):
        """Special SQL characters in query_text should be passed as params (not injected)."""
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.__iter__ = lambda self: iter([])
        mock_db.execute = AsyncMock(return_value=mock_result)

        service = VectorSearchService()
        malicious = "'; DROP TABLE pdf_chunks; --"
        await service.search_pdf(
            query_vector=[0.1] * 384,
            pdf_id=uuid4(),
            user_id=uuid4(),
            top_k=3,
            db=mock_db,
            query_text=malicious,
        )

        assert mock_db.execute.call_args[0][1]["query"] == malicious

    async def test_unicode_query_text(self):
        """Unicode characters in query_text should pass through unchanged."""
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.__iter__ = lambda self: iter([])
        mock_db.execute = AsyncMock(return_value=mock_result)

        service = VectorSearchService()
        unicode_query = "données de recherche 日本語"
        await service.search_pdf(
            query_vector=[0.1] * 384,
            pdf_id=uuid4(),
            user_id=uuid4(),
            top_k=3,
            db=mock_db,
            query_text=unicode_query,
        )

        assert mock_db.execute.call_args[0][1]["query"] == unicode_query

    # --- Vector formatting edge cases ----------------------------------------------

    async def test_single_element_vector(self):
        """A 1-element vector should format correctly."""
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.__iter__ = lambda self: iter([])
        mock_db.execute = AsyncMock(return_value=mock_result)

        service = VectorSearchService()
        await service.search_pdf(
            query_vector=[0.5],
            pdf_id=uuid4(),
            user_id=uuid4(),
            top_k=3,
            db=mock_db,
        )

        assert mock_db.execute.call_args[0][1]["vec"] == "[0.5]"

    async def test_vector_with_negative_values(self):
        """Vectors with negative values should format correctly."""
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.__iter__ = lambda self: iter([])
        mock_db.execute = AsyncMock(return_value=mock_result)

        service = VectorSearchService()
        await service.search_pdf(
            query_vector=[-0.3, 0.1, -0.9],
            pdf_id=uuid4(),
            user_id=uuid4(),
            top_k=3,
            db=mock_db,
        )

        assert mock_db.execute.call_args[0][1]["vec"] == "[-0.3,0.1,-0.9]"

    # --- Empty result sets ---------------------------------------------------------

    @pytest.mark.parametrize(
        "method_name,method_kwargs",
        [
            ("search_pdf", {"pdf_id": "uuid4", "user_id": "uuid4", "top_k": 5}),
            (
                "search_collection",
                {"collection_id": "uuid4", "user_id": "uuid4", "top_k": 5},
            ),
            ("search_all", {"user_id": "uuid4", "limit": 5}),
        ],
    )
    async def test_empty_results(self, method_name, method_kwargs):
        """All search methods should return [] when DB returns no rows."""
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.__iter__ = lambda self: iter([])
        mock_db.execute = AsyncMock(return_value=mock_result)

        service = VectorSearchService()
        method = getattr(service, method_name)
        kwargs = {"query_vector": [0.1] * 384, "db": mock_db}
        for k, v in method_kwargs.items():
            kwargs[k] = uuid4() if v == "uuid4" else v

        results = await method(**kwargs)
        assert results == []


class TestHybridSearchEdgeCases:
    """Tests for FULL OUTER JOIN edge cases in hybrid search (TG-4)."""

    # --- search_pdf edge cases ----------------------------------------------------

    async def test_search_pdf_vector_only_no_keyword_match(self):
        """Row from vector CTE only — keyword CTE had no match for this chunk."""
        mock_db = AsyncMock()
        _execute_returning(
            mock_db, [_make_hybrid_row(uuid4(), 5, "vector-only content", 0.56)]
        )

        service = VectorSearchService()
        results = await service.search_pdf(
            query_vector=[0.1] * 384,
            pdf_id=uuid4(),
            user_id=uuid4(),
            top_k=3,
            db=mock_db,
            query_text="obscure term not in any chunk",
        )

        assert len(results) == 1
        assert results[0].content == "vector-only content"
        assert results[0].score == 0.56

    async def test_search_pdf_keyword_only_no_vector_match(self):
        """Row from keyword CTE only — vector CTE had no match for this chunk."""
        mock_db = AsyncMock()
        _execute_returning(
            mock_db, [_make_hybrid_row(uuid4(), 3, "keyword-only content", 0.15)]
        )

        service = VectorSearchService()
        results = await service.search_pdf(
            query_vector=[0.1] * 384,
            pdf_id=uuid4(),
            user_id=uuid4(),
            top_k=3,
            db=mock_db,
            query_text="exact keyword match",
        )

        assert len(results) == 1
        assert results[0].content == "keyword-only content"
        assert results[0].score == 0.15

    async def test_search_pdf_mixed_vector_and_keyword_only(self):
        """Mixed results from vector-only, keyword-only, and both CTEs."""
        mock_db = AsyncMock()
        _execute_returning(
            mock_db,
            [
                _make_hybrid_row(uuid4(), 1, "both match (highest)", 0.88),
                _make_hybrid_row(uuid4(), 5, "vector-only match", 0.56),
                _make_hybrid_row(uuid4(), 8, "keyword-only match", 0.12),
            ],
        )

        service = VectorSearchService()
        results = await service.search_pdf(
            query_vector=[0.1] * 384,
            pdf_id=uuid4(),
            user_id=uuid4(),
            top_k=3,
            db=mock_db,
            query_text="mixed query",
        )

        assert len(results) == 3
        assert results[0].score == 0.88
        assert results[1].score == 0.56
        assert results[2].score == 0.12

    async def test_search_pdf_hybrid_zero_combined_score(self):
        """Row with combined_score of 0.0 should still produce a SearchResult."""
        mock_db = AsyncMock()
        _execute_returning(
            mock_db, [_make_hybrid_row(uuid4(), 1, "zero score content", 0.0)]
        )

        service = VectorSearchService()
        results = await service.search_pdf(
            query_vector=[0.1] * 384,
            pdf_id=uuid4(),
            user_id=uuid4(),
            top_k=3,
            db=mock_db,
            query_text="no match at all",
        )

        assert len(results) == 1
        assert results[0].score == 0.0

    async def test_search_pdf_hybrid_preserves_end_page_number(self):
        """Hybrid search results should include end_page_number from DB rows."""
        mock_db = AsyncMock()
        _execute_returning(
            mock_db,
            [_make_hybrid_row(uuid4(), 2, "spanning content", 0.75, end_page_number=4)],
        )

        service = VectorSearchService()
        results = await service.search_pdf(
            query_vector=[0.1] * 384,
            pdf_id=uuid4(),
            user_id=uuid4(),
            top_k=3,
            db=mock_db,
            query_text="spanning",
        )

        assert len(results) == 1
        assert results[0].end_page_number == 4

    # --- search_collection edge cases ---------------------------------------------

    async def test_search_collection_keyword_only_results(self):
        """Collection search returning only keyword-matched results."""
        mock_db = AsyncMock()
        _execute_returning(
            mock_db,
            [
                _make_hybrid_collection_row(
                    uuid4(),
                    uuid4(),
                    "Paper with exact term",
                    2,
                    "keyword matched",
                    0.21,
                ),
            ],
        )

        service = VectorSearchService()
        results = await service.search_collection(
            query_vector=[0.1] * 384,
            collection_id=uuid4(),
            user_id=uuid4(),
            top_k=3,
            db=mock_db,
            query_text="exact term",
        )

        assert len(results) == 1
        assert results[0].pdf_title == "Paper with exact term"
        assert results[0].score == 0.21

    async def test_search_collection_hybrid_preserves_end_page_number(self):
        """Hybrid collection search results should include end_page_number."""
        mock_db = AsyncMock()
        _execute_returning(
            mock_db,
            [
                _make_hybrid_collection_row(
                    uuid4(), uuid4(), "Paper", 3, "content", 0.8, end_page_number=5
                )
            ],
        )

        service = VectorSearchService()
        results = await service.search_collection(
            query_vector=[0.1] * 384,
            collection_id=uuid4(),
            user_id=uuid4(),
            top_k=3,
            db=mock_db,
            query_text="test",
        )

        assert len(results) == 1
        assert results[0].end_page_number == 5

    # --- search_all edge cases ----------------------------------------------------

    async def test_search_all_keyword_only_across_pdfs(self):
        """search_all with keyword-only matches across multiple PDFs."""
        mock_db = AsyncMock()
        pdf_a, pdf_b = uuid4(), uuid4()
        _execute_returning(
            mock_db,
            [
                _make_hybrid_all_row(pdf_a, "Paper A", 3, "exact match in A", 0.18),
                _make_hybrid_all_row(pdf_b, "Paper B", 1, "exact match in B", 0.09),
            ],
        )

        service = VectorSearchService()
        results = await service.search_all(
            query_vector=[0.1] * 384,
            user_id=uuid4(),
            limit=5,
            db=mock_db,
            query_text="exact match",
        )

        assert len(results) == 2
        pdf_ids = {r.pdf_id for r in results}
        assert str(pdf_a) in pdf_ids
        assert str(pdf_b) in pdf_ids
        for r in results:
            assert r.chunk_id is not None

    async def test_search_all_dedup_keeps_highest_score(self):
        """When same PDF appears from both CTEs, dedup keeps first (highest score)."""
        mock_db = AsyncMock()
        pdf_a = uuid4()
        _execute_returning(
            mock_db,
            [
                _make_hybrid_all_row(pdf_a, "Paper A", 2, "high score", 0.90),
                _make_hybrid_all_row(pdf_a, "Paper A", 7, "low score", 0.45),
            ],
        )

        service = VectorSearchService()
        results = await service.search_all(
            query_vector=[0.1] * 384,
            user_id=uuid4(),
            limit=5,
            db=mock_db,
            query_text="test",
        )

        assert len(results) == 1
        assert results[0].score == 0.90
        assert results[0].page_number == 2

    async def test_search_all_hybrid_respects_limit(self):
        """Hybrid search_all should stop after collecting `limit` unique PDFs."""
        mock_db = AsyncMock()
        _execute_returning(
            mock_db,
            [
                _make_hybrid_all_row(
                    uuid4(), f"Paper {i}", 1, f"Content {i}", 0.9 - i * 0.1
                )
                for i in range(10)
            ],
        )

        service = VectorSearchService()
        results = await service.search_all(
            query_vector=[0.1] * 384,
            user_id=uuid4(),
            limit=3,
            db=mock_db,
            query_text="test",
        )

        assert len(results) == 3

    async def test_search_all_hybrid_content_not_truncated(self):
        """In hybrid path, full content is returned (not truncated to 300 chars)."""
        mock_db = AsyncMock()
        long_content = "x" * 500
        _execute_returning(
            mock_db,
            [
                _make_hybrid_all_row(uuid4(), "Paper", 1, long_content, 0.8),
            ],
        )

        service = VectorSearchService()
        results = await service.search_all(
            query_vector=[0.1] * 384,
            user_id=uuid4(),
            limit=5,
            db=mock_db,
            query_text="test",
        )

        assert len(results) == 1
        assert len(results[0].content) == 500


class TestChunkTypeFilter:
    """Tests for Phase 5 chunk_type filtering in retrieval."""

    @pytest.mark.parametrize(
        "method_name,method_kwargs",
        [
            ("search_pdf", {"pdf_id": "uuid4", "user_id": "uuid4", "top_k": 3}),
            (
                "search_collection",
                {"collection_id": "uuid4", "user_id": "uuid4", "top_k": 3},
            ),
            ("search_all", {"user_id": "uuid4", "limit": 3}),
        ],
    )
    async def test_chunk_type_filter_appends_clause_and_params(
        self, method_name, method_kwargs
    ):
        """When chunk_type_filter is provided, SQL includes ANY(:chunk_types)."""
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.__iter__ = lambda self: iter([])
        mock_db.execute = AsyncMock(return_value=mock_result)

        service = VectorSearchService()
        method = getattr(service, method_name)

        kwargs = {
            "query_vector": [0.1] * 384,
            "db": mock_db,
            "query_text": "test query",
            "chunk_type_filter": ["paragraph", "table"],
        }
        for k, v in method_kwargs.items():
            kwargs[k] = uuid4() if v == "uuid4" else v

        await method(**kwargs)

        call_args = mock_db.execute.call_args
        params = call_args[0][1]
        sql = call_args[0][0].text

        assert "pc.chunk_type = ANY(:chunk_types)" in sql
        assert params["chunk_types"] == ["paragraph", "table"]

    @pytest.mark.parametrize(
        "method_name,method_kwargs,filter_value",
        [
            ("search_pdf", {"pdf_id": "uuid4", "user_id": "uuid4", "top_k": 3}, None),
            ("search_pdf", {"pdf_id": "uuid4", "user_id": "uuid4", "top_k": 3}, []),
            (
                "search_collection",
                {"collection_id": "uuid4", "user_id": "uuid4", "top_k": 3},
                None,
            ),
            ("search_all", {"user_id": "uuid4", "limit": 3}, None),
        ],
    )
    async def test_no_chunk_type_filter_omits_clause(
        self, method_name, method_kwargs, filter_value
    ):
        """When chunk_type_filter is absent or empty, no chunk_type SQL is emitted."""
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.__iter__ = lambda self: iter([])
        mock_db.execute = AsyncMock(return_value=mock_result)

        service = VectorSearchService()
        method = getattr(service, method_name)

        kwargs = {
            "query_vector": [0.1] * 384,
            "db": mock_db,
            "chunk_type_filter": filter_value,
        }
        for k, v in method_kwargs.items():
            kwargs[k] = uuid4() if v == "uuid4" else v

        await method(**kwargs)

        call_args = mock_db.execute.call_args
        params = call_args[0][1]
        sql = call_args[0][0].text

        assert "pc.chunk_type" not in sql
        assert "chunk_types" not in params
