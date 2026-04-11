"""Tests for context chunk field propagation through schema and deserialization.

Validates that end_page_number, section_title, and section_level survive
the full round-trip: payload -> DB storage -> deserialization -> Pydantic schema.
"""

from datetime import datetime, timezone
from uuid import uuid4

from app.schemas.chat import ContextChunkResponse, MessageResponse


def _make_chunk(**overrides):
    """Build a minimal context_chunks JSONB dict with sensible defaults."""
    base = {
        "chunk_id": str(uuid4()),
        "page_number": 1,
        "snippet": "Test snippet.",
    }
    base.update(overrides)
    return base


# --- ContextChunkResponse schema tests ---


def test_context_chunk_response_required_fields_only():
    """Schema accepts a chunk with only required fields."""
    chunk = ContextChunkResponse(
        chunk_id="abc",
        page_number=5,
        snippet="Hello",
    )
    assert chunk.end_page_number is None
    assert chunk.section_title is None
    assert chunk.section_level is None


def test_context_chunk_response_with_section_metadata():
    """Schema accepts and serialises all new optional fields."""
    chunk = ContextChunkResponse(
        chunk_id="abc",
        page_number=3,
        snippet="Content",
        end_page_number=5,
        section_title="Methods",
        section_level=2,
    )
    assert chunk.end_page_number == 5
    assert chunk.section_title == "Methods"
    assert chunk.section_level == 2

    data = chunk.model_dump()
    assert data["end_page_number"] == 5
    assert data["section_title"] == "Methods"
    assert data["section_level"] == 2


def test_context_chunk_response_section_title_without_level():
    """section_title can be set while section_level remains None."""
    chunk = ContextChunkResponse(
        chunk_id="abc",
        page_number=1,
        snippet="X",
        section_title="Introduction",
    )
    assert chunk.section_title == "Introduction"
    assert chunk.section_level is None


def test_context_chunk_response_end_page_equals_start():
    """end_page_number can equal page_number (single-page chunk)."""
    chunk = ContextChunkResponse(
        chunk_id="abc",
        page_number=7,
        snippet="X",
        end_page_number=7,
    )
    assert chunk.end_page_number == 7


# --- Deserialization round-trip tests ---
# These mirror the dict transformation in get_messages (chat.py lines 143-158)
# and verify that MessageResponse accepts the result.


def _deserialise_chunks(stored_chunks):
    """Replicate the get_messages deserialization logic."""
    return [
        {
            "chunk_id": c["chunk_id"],
            "page_number": c["page_number"],
            "end_page_number": c.get("end_page_number"),
            "snippet": c["snippet"],
            "section_title": c.get("section_title"),
            "section_level": c.get("section_level"),
            **(
                {"pdf_id": c["pdf_id"], "pdf_title": c["pdf_title"]}
                if c.get("pdf_id")
                else {}
            ),
        }
        for c in stored_chunks
    ]


def test_deserialise_old_chunks_without_new_fields():
    """Old stored chunks missing the new fields should deserialise without error."""
    stored = [
        {
            "chunk_id": "old-1",
            "page_number": 2,
            "snippet": "Legacy content.",
        }
    ]
    deserialised = _deserialise_chunks(stored)
    assert len(deserialised) == 1
    assert deserialised[0]["end_page_number"] is None
    assert deserialised[0]["section_title"] is None
    assert deserialised[0]["section_level"] is None

    # Verify Pydantic accepts it
    chunk = ContextChunkResponse(**deserialised[0])
    assert chunk.page_number == 2
    assert chunk.end_page_number is None


def test_deserialise_new_chunks_with_all_fields():
    """New chunks with all fields should round-trip correctly."""
    stored = [
        {
            "chunk_id": "new-1",
            "page_number": 3,
            "end_page_number": 5,
            "snippet": "Multi-page content.",
            "section_title": "Results",
            "section_level": 1,
            "pdf_id": str(uuid4()),
            "pdf_title": "Important Paper",
        }
    ]
    deserialised = _deserialise_chunks(stored)
    assert deserialised[0]["end_page_number"] == 5
    assert deserialised[0]["section_title"] == "Results"
    assert deserialised[0]["section_level"] == 1
    assert deserialised[0]["pdf_id"] == stored[0]["pdf_id"]

    # Verify Pydantic accepts it
    chunk = ContextChunkResponse(**deserialised[0])
    assert chunk.section_title == "Results"


def test_deserialise_mixed_old_and_new_chunks():
    """A message with both old-format and new-format chunks deserialises correctly."""
    stored = [
        {"chunk_id": "old-1", "page_number": 1, "snippet": "Old."},
        {
            "chunk_id": "new-1",
            "page_number": 2,
            "snippet": "New.",
            "end_page_number": 3,
            "section_title": "Discussion",
            "section_level": 2,
        },
    ]
    deserialised = _deserialise_chunks(stored)
    assert len(deserialised) == 2
    assert deserialised[0]["section_title"] is None
    assert deserialised[1]["section_title"] == "Discussion"

    # Both should be valid ContextChunkResponse instances
    for d in deserialised:
        ContextChunkResponse(**d)


def test_message_response_with_new_chunk_fields():
    """Full MessageResponse round-trip with chunks containing the new fields."""
    chunks = [
        {
            "chunk_id": "c1",
            "page_number": 1,
            "end_page_number": 2,
            "snippet": "Span content.",
            "section_title": "Abstract",
            "section_level": 1,
        }
    ]
    msg = MessageResponse(
        id=uuid4(),
        role="assistant",
        content="Here is the answer.",
        context_chunks=[ContextChunkResponse(**c) for c in chunks],
        created_at=datetime.now(timezone.utc),
    )
    assert msg.context_chunks[0].section_title == "Abstract"
    assert msg.context_chunks[0].end_page_number == 2

    dumped = msg.model_dump()
    assert dumped["context_chunks"][0]["section_level"] == 1


def test_deserialise_chunk_with_pdf_info():
    """Chunks with pdf_id/pdf_title include those fields after deserialization."""
    pdf_id = str(uuid4())
    stored = [
        {
            "chunk_id": "c1",
            "page_number": 4,
            "snippet": "Content.",
            "pdf_id": pdf_id,
            "pdf_title": "My Paper",
        }
    ]
    deserialised = _deserialise_chunks(stored)
    assert deserialised[0]["pdf_id"] == pdf_id
    assert deserialised[0]["pdf_title"] == "My Paper"
    assert "pdf_id" not in _deserialise_chunks(
        [{"chunk_id": "c", "page_number": 1, "snippet": "X"}]
    )[0]
