"""Tests for the chat service context formatting (Phase 1.3)."""

from app.services.chat_service import ChatService, _count_tokens, _truncate_to_tokens


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
