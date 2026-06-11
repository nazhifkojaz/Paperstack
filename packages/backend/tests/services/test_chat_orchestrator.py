"""Tests for the ChatOrchestrator RAG pipeline."""

import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.chat_orchestrator import ChatOrchestrator, PreparedContext, PreparedMessages
from app.services.exceptions import (
    EmbeddingError,
    IndexInProgressError,
    LLMRateLimitError,
)

from tests.helpers import TEST_EMBEDDING


@pytest.fixture
def mock_embedding():
    svc = MagicMock()
    svc.embed_query = AsyncMock(return_value=TEST_EMBEDDING)
    return svc


@pytest.fixture
def mock_llm():
    return MagicMock()


@pytest.fixture
def mock_chat():
    svc = MagicMock()
    svc.build_context = MagicMock(return_value="[Page 1] chunk content")
    svc.build_messages = MagicMock(
        return_value=("system prompt", [{"role": "user", "content": "test"}])
    )
    return svc


@pytest.fixture
def mock_indexing():
    svc = MagicMock()
    svc.get_or_create_status = AsyncMock(return_value=MagicMock(status="indexed"))
    svc.ensure_indexed = AsyncMock(return_value=MagicMock(status="indexed"))
    svc.reset_if_stale = AsyncMock(return_value=False)
    return svc


@pytest.fixture
def orchestrator(mock_embedding, mock_llm, mock_chat, mock_indexing):
    return ChatOrchestrator(
        embedding_service=mock_embedding,
        llm_service=mock_llm,
        chat_service=mock_chat,
        indexing_service=mock_indexing,
    )


@pytest.fixture
def mock_user():
    user = MagicMock()
    user.id = uuid.uuid4()
    user.display_name = "Test User"
    return user


@pytest.fixture
def mock_db():
    db = MagicMock()
    db.execute = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.flush = AsyncMock()
    return db


# ---------------------------------------------------------------------------
# prepare_context — PDF path
# ---------------------------------------------------------------------------

class TestPreparePdfContext:

    async def test_prepare_pdf_context_success(
        self, orchestrator, mock_user, mock_db, mock_indexing
    ):
        pdf_id = uuid.uuid4()
        pdf_row = MagicMock()
        pdf_row.title = "Test Paper"
        pdf_row.id = pdf_id

        # Mock the Pdf lookup
        scalar_result = MagicMock()
        scalar_result.scalar_one_or_none = MagicMock(return_value=pdf_row)
        mock_db.execute = AsyncMock(return_value=scalar_result)

        # Mock vector search
        search_chunk = MagicMock()
        search_chunk.page_number = 1
        search_chunk.end_page_number = None
        search_chunk.content = "chunk text"
        search_chunk.section_title = None
        search_chunk.section_level = None
        search_chunk.chunk_id = str(uuid.uuid4())

        with patch(
            "app.services.chat_orchestrator.vector_search_service.search_pdf",
            new_callable=AsyncMock,
        ) as mock_search:
            mock_search.return_value = [search_chunk]

            result = await orchestrator.prepare_context(
                query="test query",
                pdf_id=pdf_id,
                collection_id=None,
                user=mock_user,
                db=mock_db,
            )

        assert isinstance(result, PreparedContext)
        assert "[Page 1]" in result.context
        assert len(result.top_chunks) == 1
        assert len(result.context_chunks_payload) == 1
        assert result.context_chunks_payload[0]["page_number"] == 1

    async def test_prepare_pdf_context_pdf_not_found(
        self, orchestrator, mock_user, mock_db
    ):
        scalar_result = MagicMock()
        scalar_result.scalar_one_or_none = MagicMock(return_value=None)
        mock_db.execute = AsyncMock(return_value=scalar_result)

        with pytest.raises(ValueError, match="PDF not found"):
            await orchestrator.prepare_context(
                query="test",
                pdf_id=uuid.uuid4(),
                collection_id=None,
                user=mock_user,
                db=mock_db,
            )

    async def test_prepare_pdf_context_embedding_error(
        self, orchestrator, mock_user, mock_db, mock_embedding
    ):
        mock_embedding.embed_query = AsyncMock(
            side_effect=EmbeddingError("embedding failure")
        )

        with pytest.raises(EmbeddingError, match="embedding failure"):
            await orchestrator.prepare_context(
                query="test",
                pdf_id=uuid.uuid4(),
                collection_id=None,
                user=mock_user,
                db=mock_db,
            )

    async def test_prepare_pdf_context_index_in_progress(
        self, orchestrator, mock_user, mock_db, mock_indexing
    ):
        mock_indexing.ensure_indexed = AsyncMock(
            side_effect=IndexInProgressError("pdf-123", mock_db)
        )
        pdf_id = uuid.uuid4()

        scalar_result = MagicMock()
        pdf_row = MagicMock()
        pdf_row.title = "Test"
        pdf_row.id = pdf_id
        scalar_result.scalar_one_or_none = MagicMock(return_value=pdf_row)
        mock_db.execute = AsyncMock(return_value=scalar_result)

        with pytest.raises(IndexInProgressError):
            await orchestrator.prepare_context(
                query="test",
                pdf_id=pdf_id,
                collection_id=None,
                user=mock_user,
                db=mock_db,
            )

    async def test_prepare_pdf_context_no_chunks(
        self, orchestrator, mock_user, mock_db
    ):
        pdf_id = uuid.uuid4()
        pdf_row = MagicMock()
        pdf_row.title = "Test Paper"
        pdf_row.id = pdf_id

        scalar_result = MagicMock()
        scalar_result.scalar_one_or_none = MagicMock(return_value=pdf_row)
        mock_db.execute = AsyncMock(return_value=scalar_result)

        with patch(
            "app.services.chat_orchestrator.vector_search_service.search_pdf",
            new_callable=AsyncMock,
        ) as mock_search:
            mock_search.return_value = []

            result = await orchestrator.prepare_context(
                query="test query",
                pdf_id=pdf_id,
                collection_id=None,
                user=mock_user,
                db=mock_db,
            )

        assert result.top_chunks == []
        assert result.context_chunks_payload == []


# ---------------------------------------------------------------------------
# prepare_context — Collection path
# ---------------------------------------------------------------------------

class TestPrepareCollectionContext:

    async def test_prepare_collection_context_success(
        self, orchestrator, mock_user, mock_db
    ):
        collection_id = uuid.uuid4()

        chunk = MagicMock()
        chunk.pdf_id = str(uuid.uuid4())
        chunk.pdf_title = "Paper One"
        chunk.page_number = 2
        chunk.end_page_number = 4
        chunk.content = "collection chunk text"
        chunk.section_title = "Methods"
        chunk.section_level = 2
        chunk.chunk_id = str(uuid.uuid4())

        # Mock citation fetch: execute returns scalar result with no citations
        cite_scalar_result = MagicMock()
        cite_scalar_result.scalars = MagicMock()
        cite_scalar_result.scalars.return_value.all = MagicMock(return_value=[])
        mock_db.execute = AsyncMock(return_value=cite_scalar_result)

        with patch(
            "app.services.chat_orchestrator.vector_search_service.search_collection",
            new_callable=AsyncMock,
        ) as mock_search:
            mock_search.return_value = [chunk]

            result = await orchestrator.prepare_context(
                query="test query",
                pdf_id=None,
                collection_id=collection_id,
                user=mock_user,
                db=mock_db,
            )

        assert isinstance(result, PreparedContext)
        assert "Paper One" in result.context
        assert "Pages 2-4" in result.context
        assert len(result.top_chunks) == 1
        assert len(result.context_chunks_payload) == 1
        assert result.context_chunks_payload[0]["pdf_title"] == "Paper One"

    async def test_prepare_collection_context_no_collection_id(
        self, orchestrator, mock_user, mock_db
    ):
        with pytest.raises(ValueError, match="neither pdf_id nor collection_id"):
            await orchestrator.prepare_context(
                query="test",
                pdf_id=None,
                collection_id=None,
                user=mock_user,
                db=mock_db,
            )

    async def test_prepare_collection_context_no_results(
        self, orchestrator, mock_user, mock_db
    ):
        with patch(
            "app.services.chat_orchestrator.vector_search_service.search_collection",
            new_callable=AsyncMock,
        ) as mock_search:
            mock_search.return_value = []

            with pytest.raises(ValueError, match="No indexed PDFs found"):
                await orchestrator.prepare_context(
                    query="test",
                    pdf_id=None,
                    collection_id=uuid.uuid4(),
                    user=mock_user,
                    db=mock_db,
                )


# ---------------------------------------------------------------------------
# build_messages
# ---------------------------------------------------------------------------

class TestBuildMessages:

    @pytest.mark.parametrize(
        "collection_id,expected_base_prompt,history,paper_metadata",
        [
            pytest.param(
                None, None,
                [{"role": "user", "content": "previous"}],
                {"title": "Test Paper"},
                id="pdf_context_with_history",
            ),
            pytest.param(
                uuid.uuid4(), "COLLECTION",
                [],
                [{"title": "Paper A"}, {"title": "Paper B"}],
                id="collection_context_no_history",
            ),
            pytest.param(
                None, None,
                [],
                None,
                id="no_history_no_metadata",
            ),
        ],
    )
    async def test_build_messages_passes_base_prompt(
        self, orchestrator, mock_chat, collection_id, expected_base_prompt, history, paper_metadata
    ):
        from app.services.chat_service import COLLECTION_SYSTEM_PROMPT

        result = await orchestrator.build_messages(
            context="[Page 1] chunk",
            history=history,
            user_message="question",
            collection_id=collection_id,
            paper_metadata=paper_metadata,
        )

        assert isinstance(result, PreparedMessages)
        mock_chat.build_messages.assert_called_once()
        call_kwargs = mock_chat.build_messages.call_args[1]
        if expected_base_prompt == "COLLECTION":
            assert call_kwargs["base_prompt"] == COLLECTION_SYSTEM_PROMPT
        else:
            assert call_kwargs["base_prompt"] is None


# ---------------------------------------------------------------------------
# persist_user_message
# ---------------------------------------------------------------------------

class TestPersistUserMessage:

    async def test_persist_user_message_sets_title(
        self, orchestrator, mock_db
    ):
        conv = MagicMock()
        conv.title = None

        await orchestrator.persist_user_message(
            conversation_id=uuid.uuid4(),
            content="What is the main finding of this paper?",
            conv=conv,
            db=mock_db,
        )

        assert conv.title == "What is the main finding of this paper?"
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()

    async def test_persist_user_message_truncates_long_title(
        self, orchestrator, mock_db
    ):
        conv = MagicMock()
        conv.title = None
        long_content = "X" * 100

        await orchestrator.persist_user_message(
            conversation_id=uuid.uuid4(),
            content=long_content,
            conv=conv,
            db=mock_db,
        )

        assert len(conv.title) <= 61  # 60 chars + "…"
        assert conv.title.endswith("…")

    async def test_persist_user_message_keeps_existing_title(
        self, orchestrator, mock_db
    ):
        conv = MagicMock()
        conv.title = "Existing Title"

        await orchestrator.persist_user_message(
            conversation_id=uuid.uuid4(),
            content="New message",
            conv=conv,
            db=mock_db,
        )

        assert conv.title == "Existing Title"


# ---------------------------------------------------------------------------
# stream_and_save — success, rate limit, and error paths
# ---------------------------------------------------------------------------

class TestStreamAndSave:

    async def test_stream_and_save_success(
        self, orchestrator, mock_chat, mock_db
    ):
        async def mock_stream(*args, **kwargs):
            yield "Hello"
            yield " world"

        mock_chat.stream_reply = mock_stream

        conversation_id = uuid.uuid4()
        events = []
        async for event in orchestrator.stream_and_save(
            system_prompt="system",
            messages=[{"role": "user", "content": "hi"}],
            provider="openrouter",
            api_key="test-key",
            model=None,
            conversation_id=conversation_id,
            context_chunks_payload=[],
            db=mock_db,
        ):
            events.append(event)

        assert len(events) == 3  # "Hello", " world", done
        assert events[-1]["done"] is True
        assert "message_id" in events[-1]
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called()

    async def test_stream_and_save_rate_limit(
        self, orchestrator, mock_chat, mock_db
    ):
        async def mock_stream(*args, **kwargs):
            raise LLMRateLimitError("openrouter")
            yield

        mock_chat.stream_reply = mock_stream

        events = []
        async for event in orchestrator.stream_and_save(
            system_prompt="system",
            messages=[{"role": "user", "content": "hi"}],
            provider="openrouter",
            api_key="test-key",
            model=None,
            conversation_id=uuid.uuid4(),
            context_chunks_payload=[],
            db=mock_db,
        ):
            events.append(event)

        # Should yield a rate_limited error then stop
        assert len(events) == 1
        assert events[0]["code"] == "rate_limited"
        # No DB save should have happened
        mock_db.add.assert_not_called()

    async def test_stream_and_save_unexpected_error(
        self, orchestrator, mock_chat, mock_db
    ):
        async def mock_stream(*args, **kwargs):
            raise RuntimeError("unexpected crash")
            yield

        mock_chat.stream_reply = mock_stream

        events = []
        async for event in orchestrator.stream_and_save(
            system_prompt="system",
            messages=[{"role": "user", "content": "hi"}],
            provider="openrouter",
            api_key="test-key",
            model=None,
            conversation_id=uuid.uuid4(),
            context_chunks_payload=[],
            db=mock_db,
        ):
            events.append(event)

        assert len(events) == 1
        assert events[0]["code"] == "stream_error"
