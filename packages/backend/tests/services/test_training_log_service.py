import uuid
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    ChatConversation,
    ChatMessage,
    Pdf,
    PdfChunk,
    TrainingChunkFeedback,
    TrainingRagInteraction,
    User,
)
from app.services.training_log_service import (
    TrainingLogContext,
    TrainingLogService,
    citation_parse_status,
    extract_citation_events,
)


def _chunk(
    chunk_id: uuid.UUID,
    *,
    page_number: int = 1,
    end_page_number: int | None = None,
    pdf_title: str | None = "Attention Is All You Need",
) -> dict:
    return {
        "chunk_id": str(chunk_id),
        "pdf_id": str(uuid.uuid4()),
        "pdf_title": pdf_title,
        "page_number": page_number,
        "end_page_number": end_page_number,
        "section_title": "Methods",
        "section_level": 2,
        "retrieval_rank": 1,
        "retrieval_score": 0.91,
        "content": "chunk text",
        "snippet": "chunk text",
        "included_in_prompt": True,
        "prompt_rank": 1,
    }


def _context(
    *,
    user_id: uuid.UUID,
    conversation_id: uuid.UUID,
    user_message_id: uuid.UUID,
    pdf_id: uuid.UUID | None,
    retrieved_chunks: list[dict],
) -> TrainingLogContext:
    return TrainingLogContext(
        user_id=user_id,
        conversation_id=conversation_id,
        user_message_id=user_message_id,
        query_text="What is attention?",
        query_embedding=None,
        embedding_model="test-embedding",
        embedding_dimensions=1024,
        scope_type="single_pdf",
        pdf_id=pdf_id,
        collection_id=None,
        retrieved_chunks=retrieved_chunks,
        retrieval_top_k=6,
        retrieval_config={"mode": "hybrid"},
        prompt_context="[Page 4]\nAttention content",
        system_prompt="system",
        prompt_messages=[{"role": "user", "content": "What is attention?"}],
        llm_provider="openrouter",
        llm_model="test-model",
        generation_config={},
        training_eligible=True,
        consent_version="test-v1",
    )


def test_extract_citation_events_single_pdf_matches_page_range():
    chunk_id = uuid.uuid4()

    events = extract_citation_events(
        "The method is described clearly [p.3].",
        [_chunk(chunk_id, page_number=2, end_page_number=4)],
        "single_pdf",
    )

    assert events == [
        {
            "raw": "[p.3]",
            "page": 3,
            "title": None,
            "matched_chunk_ids": [str(chunk_id)],
            "status": "matched",
            "citation_rank": 1,
        }
    ]
    assert citation_parse_status(events) == "parsed"


def test_extract_citation_events_collection_uses_title_match():
    chunk_id = uuid.uuid4()

    events = extract_citation_events(
        "Transformers use scaled dot-product attention [Attention, p.4].",
        [_chunk(chunk_id, page_number=4, pdf_title="Attention Is All You Need")],
        "collection",
    )

    assert events[0]["status"] == "matched"
    assert events[0]["matched_chunk_ids"] == [str(chunk_id)]


def test_extract_citation_events_marks_ambiguous_matches():
    first_id = uuid.uuid4()
    second_id = uuid.uuid4()

    events = extract_citation_events(
        "Both chunks could match this citation [Attention, p.4].",
        [
            _chunk(first_id, page_number=4, pdf_title="Attention Is All You Need"),
            _chunk(second_id, page_number=4, pdf_title="Attention Is All You Need"),
        ],
        "collection",
    )

    assert events[0]["status"] == "ambiguous"
    assert set(events[0]["matched_chunk_ids"]) == {str(first_id), str(second_id)}
    assert citation_parse_status(events) == "ambiguous"


@pytest.mark.asyncio
async def test_log_interaction_inserts_interaction_and_chunk_feedback(
    db_session: AsyncSession,
    test_user: User,
):
    pdf_id = uuid.uuid4()
    chunk_id = uuid.uuid4()
    conversation_id = uuid.uuid4()
    user_message_id = uuid.uuid4()
    assistant_message_id = uuid.uuid4()

    pdf = Pdf(
        id=pdf_id,
        user_id=test_user.id,
        title="Attention Is All You Need",
        filename="attention.pdf",
    )
    chunk = PdfChunk(
        id=chunk_id,
        pdf_id=pdf_id,
        user_id=test_user.id,
        chunk_index=0,
        page_number=4,
        end_page_number=4,
        content="Attention content",
    )
    conversation = ChatConversation(
        id=conversation_id,
        user_id=test_user.id,
        pdf_id=pdf_id,
    )
    user_message = ChatMessage(
        id=user_message_id,
        conversation_id=conversation_id,
        role="user",
        content="What is attention?",
    )
    assistant_message = ChatMessage(
        id=assistant_message_id,
        conversation_id=conversation_id,
        role="assistant",
        content="It is described on [p.4].",
    )
    db_session.add(pdf)
    await db_session.commit()
    db_session.add(chunk)
    await db_session.commit()
    db_session.add_all([conversation, user_message, assistant_message])
    await db_session.commit()

    context = _context(
        user_id=test_user.id,
        conversation_id=conversation_id,
        user_message_id=user_message_id,
        pdf_id=pdf_id,
        retrieved_chunks=[_chunk(chunk_id, page_number=4, pdf_title=pdf.title)],
    )

    interaction = await TrainingLogService().log_interaction(
        db_session,
        context,
        assistant_message_id=assistant_message_id,
        assistant_reply="It is described on [p.4].",
        latency_ms=123,
        token_count=7,
    )

    saved_interaction = await db_session.get(TrainingRagInteraction, interaction.id)
    assert saved_interaction is not None
    assert saved_interaction.training_eligible is True
    assert saved_interaction.cited_chunk_ids == [chunk_id]
    assert saved_interaction.citation_parse_status == "parsed"

    feedback_result = await db_session.execute(
        select(TrainingChunkFeedback).where(
            TrainingChunkFeedback.interaction_id == interaction.id
        )
    )
    feedback = feedback_result.scalar_one()
    assert feedback.chunk_id == chunk_id
    assert feedback.was_cited is True
    assert feedback.citation_rank == 1
    assert feedback.included_in_prompt is True


class _FailingSession:
    def __init__(self) -> None:
        self.rollback = AsyncMock()

    async def __aenter__(self) -> "_FailingSession":
        return self

    async def __aexit__(self, *args) -> None:
        return None


@pytest.mark.asyncio
async def test_background_log_rolls_back_failed_session():
    session = _FailingSession()
    service = TrainingLogService(session_factory=lambda: session)
    service.log_interaction = AsyncMock(side_effect=RuntimeError("boom"))
    conversation_id = uuid.uuid4()
    context = _context(
        user_id=uuid.uuid4(),
        conversation_id=conversation_id,
        user_message_id=uuid.uuid4(),
        pdf_id=uuid.uuid4(),
        retrieved_chunks=[],
    )

    await service._log_interaction_safely(
        context,
        assistant_message_id=uuid.uuid4(),
        assistant_reply="failed",
        latency_ms=None,
        token_count=None,
    )

    session.rollback.assert_awaited_once()
