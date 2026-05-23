"""Tests for the explain service."""

import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.explain_service import ExplainService, ExplainResult
from app.services.exceptions import (
    EmbeddingError,
    LLMRateLimitError,
)

TEST_EMBEDDING = [0.01] * 1024


@pytest.fixture
def mock_embedding():
    svc = MagicMock()
    svc.embed_query = AsyncMock(return_value=TEST_EMBEDDING)
    return svc


@pytest.fixture
def mock_llm():
    svc = MagicMock()
    svc.call_gemini = AsyncMock(return_value="This is an explanation.")
    return svc


@pytest.fixture
def mock_chat():
    svc = MagicMock()
    svc.build_context = MagicMock(return_value="[Page 1] context text")
    return svc


@pytest.fixture
def mock_indexing():
    svc = MagicMock()
    svc.get_or_create_status = AsyncMock(return_value=MagicMock(status="indexed"))
    svc.ensure_indexed = AsyncMock(return_value=MagicMock(status="indexed"))
    return svc


@pytest.fixture
def explain_service(mock_embedding, mock_llm, mock_chat, mock_indexing):
    return ExplainService(
        embedding_service=mock_embedding,
        llm_service=mock_llm,
        chat_service=mock_chat,
        indexing_service=mock_indexing,
    )


@pytest.fixture
def mock_db():
    db = MagicMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    return db


# ---------------------------------------------------------------------------
# explain_with_provider
# ---------------------------------------------------------------------------

class TestExplainWithProvider:

    async def test_explain_success(
        self, explain_service, mock_db, mock_llm
    ):
        pdf_row = MagicMock()
        pdf_row.id = uuid.uuid4()
        pdf_row.title = "Test Paper"

        user = MagicMock()
        user.id = uuid.uuid4()

        search_result = MagicMock()
        search_result.page_number = 1
        search_result.end_page_number = None
        search_result.content = "surrounding context"
        search_result.chunk_id = str(uuid.uuid4())

        with patch(
            "app.services.explain_service.vector_search_service.search_pdf",
            new_callable=AsyncMock,
        ) as mock_search:
            mock_search.return_value = [search_result]

            result = await explain_service.explain_with_provider(
                selected_text="test passage",
                page_number=1,
                pdf_row=pdf_row,
                user=user,
                provider="gemini",
                api_key="test-key",
                db=mock_db,
            )

        assert isinstance(result, ExplainResult)
        assert result.explanation == "This is an explanation."
        assert "[AI Explanation" in result.note_content
        assert len(result.context_chunks) == 1

    async def test_explain_embedding_error(
        self, explain_service, mock_db, mock_embedding
    ):
        mock_embedding.embed_query = AsyncMock(
            side_effect=EmbeddingError("embedding failed")
        )
        pdf_row = MagicMock()
        pdf_row.id = uuid.uuid4()
        user = MagicMock()

        with pytest.raises(EmbeddingError, match="embedding failed"):
            await explain_service.explain_with_provider(
                selected_text="test",
                page_number=1,
                pdf_row=pdf_row,
                user=user,
                provider="gemini",
                api_key="test-key",
                db=mock_db,
            )

    async def test_explain_indexing_error(
        self, explain_service, mock_db, mock_indexing
    ):
        mock_indexing.ensure_indexed = AsyncMock(
            side_effect=Exception("indexing failure")
        )
        pdf_row = MagicMock()
        pdf_row.id = uuid.uuid4()
        user = MagicMock()

        with pytest.raises(Exception, match="indexing failure"):
            await explain_service.explain_with_provider(
                selected_text="test",
                page_number=1,
                pdf_row=pdf_row,
                user=user,
                provider="gemini",
                api_key="test-key",
                db=mock_db,
            )

    async def test_explain_with_openrouter(
        self, explain_service, mock_db, mock_llm
    ):
        mock_llm.call_openrouter = AsyncMock(return_value="OpenRouter explanation.")
        pdf_row = MagicMock()
        pdf_row.id = uuid.uuid4()
        user = MagicMock()

        search_result = MagicMock()
        search_result.page_number = 1
        search_result.end_page_number = None
        search_result.content = "context"
        search_result.chunk_id = str(uuid.uuid4())

        with patch(
            "app.services.explain_service.vector_search_service.search_pdf",
            new_callable=AsyncMock,
        ) as mock_search:
            mock_search.return_value = [search_result]

            result = await explain_service.explain_with_provider(
                selected_text="passage",
                page_number=2,
                pdf_row=pdf_row,
                user=user,
                provider="openrouter",
                api_key="or-key",
                db=mock_db,
                model="test-model",
            )

        assert result.explanation == "OpenRouter explanation."
        mock_llm.call_openrouter.assert_called_once()

    async def test_explain_no_search_results(
        self, explain_service, mock_db, mock_llm
    ):
        pdf_row = MagicMock()
        pdf_row.id = uuid.uuid4()
        user = MagicMock()

        with patch(
            "app.services.explain_service.vector_search_service.search_pdf",
            new_callable=AsyncMock,
        ) as mock_search:
            mock_search.return_value = []

            result = await explain_service.explain_with_provider(
                selected_text="passage",
                page_number=1,
                pdf_row=pdf_row,
                user=user,
                provider="gemini",
                api_key="test-key",
                db=mock_db,
            )

        assert isinstance(result, ExplainResult)
        assert result.context_chunks == []
