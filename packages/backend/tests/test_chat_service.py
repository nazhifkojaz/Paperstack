"""Tests for the chat service context formatting (Phase 1.3)."""

from app.services.chat_service import (
    ChatService,
    _count_tokens,
    _truncate_to_tokens,
    _deduplicate_chunks,
)


def test_build_context_basic():
    service = ChatService()
    chunks = [
        {"page_number": 1, "content": "First chunk content."},
        {"page_number": 3, "content": "Second chunk content."},
    ]
    result = service.build_context(chunks)
    assert "[Page 1]" in result
    assert "[Page 3]" in result
    assert "First chunk content." in result
    assert "Second chunk content." in result
    assert "---" in result


def test_build_context_with_section_title():
    service = ChatService()
    chunks = [
        {
            "page_number": 2,
            "content": "Content about methods.",
            "section_title": "Methods",
        },
        {
            "page_number": 5,
            "content": "Content about results.",
            "section_title": "Results",
        },
    ]
    result = service.build_context(chunks)
    assert "[Page 2 · Methods]" in result
    assert "[Page 5 · Results]" in result


def test_build_context_mixed_section_titles():
    service = ChatService()
    chunks = [
        {"page_number": 1, "content": "No section here."},
        {
            "page_number": 2,
            "content": "Has a section.",
            "section_title": "Introduction",
        },
    ]
    result = service.build_context(chunks)
    assert "[Page 1]" in result
    assert "[Page 2 · Introduction]" in result


def test_build_context_empty():
    service = ChatService()
    result = service.build_context([])
    assert result == ""


# --- Token budget enforcement (Phase 3.1) ---


def test_build_context_respects_token_budget():
    """Chunks that exceed max_tokens should be truncated or dropped."""
    service = ChatService()
    # Each chunk is ~2000 chars, well over a 500-token budget
    chunks = [
        {"page_number": 1, "content": "A" * 2000, "section_title": "Intro"},
        {"page_number": 2, "content": "B" * 2000, "section_title": "Methods"},
        {"page_number": 3, "content": "C" * 2000, "section_title": "Results"},
    ]
    result = service.build_context(chunks, max_tokens=500)
    token_count = _count_tokens(result)
    assert token_count <= 550  # small tolerance for separator tokens


def test_build_context_fits_all_within_budget():
    """When all chunks fit, all should be included."""
    service = ChatService()
    chunks = [
        {"page_number": 1, "content": "Short chunk."},
        {"page_number": 2, "content": "Another short chunk."},
    ]
    result = service.build_context(chunks, max_tokens=4000)
    assert "[Page 1]" in result
    assert "[Page 2]" in result


def test_build_context_truncation_marker():
    """When a chunk is truncated, it should contain [...truncated]."""
    service = ChatService()
    # First chunk fits, second is too large and gets truncated
    chunks = [
        {"page_number": 1, "content": "Fits fine."},
        {"page_number": 2, "content": "X" * 3000},
    ]
    result = service.build_context(chunks, max_tokens=200)
    assert "[...truncated]" in result


def test_count_tokens_nonzero():
    """_count_tokens should return a positive integer for non-empty text."""
    assert _count_tokens("Hello world") > 0


def test_count_tokens_empty():
    """_count_tokens should return 0 for empty string."""
    assert _count_tokens("") == 0


def test_truncate_to_tokens_reduces_length():
    """_truncate_to_tokens should produce text shorter than input when budget is tight."""
    text = "This is a longer piece of text with multiple words. " * 20
    truncated = _truncate_to_tokens(text, max_tokens=30)
    assert len(truncated) < len(text)
    assert "[...truncated]" in truncated


def test_truncate_to_tokens_no_truncation_when_fits():
    """When text fits within budget, it should be returned unchanged."""
    text = "Short text."
    result = _truncate_to_tokens(text, max_tokens=100)
    assert result == text


# --- Context deduplication (Phase 4.3) ---


def test_deduplicate_removes_near_duplicates():
    """Chunks with high Jaccard similarity should be removed."""
    chunks = [
        {"page_number": 1, "content": "The quick brown fox jumps over the lazy dog"},
        {"page_number": 2, "content": "The quick brown fox jumps over the lazy dog"},
        {"page_number": 3, "content": "Completely different content here"},
    ]
    result = _deduplicate_chunks(chunks, similarity_threshold=0.9)
    assert len(result) == 2
    assert result[0]["page_number"] == 1
    assert result[1]["page_number"] == 3


def test_deduplicate_keeps_first_occurrence():
    """When duplicates exist, the first one (highest ranked) should be kept."""
    chunks = [
        {"page_number": 5, "content": "Important finding about attention"},
        {"page_number": 6, "content": "Important finding about attention mechanisms"},
    ]
    result = _deduplicate_chunks(chunks, similarity_threshold=0.5)
    assert len(result) == 1
    assert result[0]["page_number"] == 5


def test_deduplicate_no_duplicates():
    """When all chunks are different, all should be kept."""
    chunks = [
        {"page_number": 1, "content": "Introduction to the topic"},
        {"page_number": 2, "content": "Methods used in the study"},
        {"page_number": 3, "content": "Results of the experiment"},
    ]
    result = _deduplicate_chunks(chunks)
    assert len(result) == 3


def test_deduplicate_empty_content():
    """Chunks with empty content should be filtered out."""
    chunks = [
        {"page_number": 1, "content": "Real content"},
        {"page_number": 2, "content": ""},
        {"page_number": 3, "content": "More real content"},
    ]
    result = _deduplicate_chunks(chunks)
    assert len(result) == 2
    assert all(c["content"] for c in result)


def test_deduplicate_single_chunk():
    """A single chunk should be returned unchanged."""
    chunks = [{"page_number": 1, "content": "Only chunk"}]
    result = _deduplicate_chunks(chunks)
    assert len(result) == 1


def test_deduplicate_empty_list():
    """An empty list should be returned unchanged."""
    result = _deduplicate_chunks([])
    assert result == []


def test_deduplicate_threshold_sensitivity():
    """Higher threshold should allow more similar chunks through."""
    base = "The model achieves state of the art performance"
    similar = "The model achieves state of the art results"
    chunks = [
        {"page_number": 1, "content": base},
        {"page_number": 2, "content": similar},
    ]
    # At high threshold (0.95), both should pass
    result_strict = _deduplicate_chunks(chunks, similarity_threshold=0.95)
    assert len(result_strict) == 2
    # At lower threshold (0.5), the similar one should be removed
    result_loose = _deduplicate_chunks(chunks, similarity_threshold=0.5)
    assert len(result_loose) == 1


def test_build_context_deduplicates():
    """build_context should remove duplicate chunks before formatting."""
    service = ChatService()
    chunks = [
        {"page_number": 1, "content": "Identical content here"},
        {"page_number": 2, "content": "Identical content here"},
        {"page_number": 3, "content": "Different content"},
    ]
    result = service.build_context(chunks)
    # Only 2 unique chunks should appear
    assert result.count("---") == 1  # 2 chunks = 1 separator
    assert "[Page 1]" in result
    assert "[Page 3]" in result


def test_deduplicate_preserves_section_metadata():
    """Deduplication should preserve all metadata from the kept chunk."""
    chunks = [
        {
            "page_number": 1,
            "content": "Important finding about attention",
            "section_title": "Introduction",
        },
        {
            "page_number": 6,
            "content": "Important finding about attention mechanisms",
            "section_title": "Discussion",
        },
    ]
    result = _deduplicate_chunks(chunks, similarity_threshold=0.5)
    assert len(result) == 1
    assert result[0]["section_title"] == "Introduction"
    assert result[0]["page_number"] == 1


def test_deduplicate_whitespace_only_chunks():
    """Chunks with only whitespace should be filtered out."""
    chunks = [
        {"page_number": 1, "content": "Real content"},
        {"page_number": 2, "content": "   \n\t  "},
        {"page_number": 3, "content": "More real content"},
    ]
    result = _deduplicate_chunks(chunks)
    assert len(result) == 2


def test_deduplicate_case_insensitive():
    """Similarity should be case-insensitive."""
    chunks = [
        {"page_number": 1, "content": "The Quick Brown Fox"},
        {"page_number": 2, "content": "the quick brown fox"},
    ]
    result = _deduplicate_chunks(chunks, similarity_threshold=0.9)
    assert len(result) == 1


def test_deduplicate_subset_chunks():
    """When one chunk's words are a subset of another, both should pass (low Jaccard)."""
    chunks = [
        {
            "page_number": 1,
            "content": "attention mechanism transformer neural network deep learning model",
        },
        {"page_number": 2, "content": "attention mechanism"},
    ]
    # Subset has high overlap ratio but low Jaccard (union is large)
    result = _deduplicate_chunks(chunks, similarity_threshold=0.9)
    assert len(result) == 2  # Both kept — Jaccard penalizes subset relationship


def test_deduplicate_preserves_order():
    """Original ranking order should be preserved after dedup."""
    chunks = [
        {"page_number": 10, "content": "First unique topic"},
        {"page_number": 11, "content": "First unique topic repeated"},
        {"page_number": 12, "content": "Second unique topic"},
        {"page_number": 13, "content": "Second unique topic repeated"},
        {"page_number": 14, "content": "Third unique topic"},
    ]
    result = _deduplicate_chunks(chunks, similarity_threshold=0.5)
    assert len(result) == 3
    assert [c["page_number"] for c in result] == [10, 12, 14]
