"""Tests for the chat service context formatting (Phase 1.3)."""

from app.services.chat_service import ChatService


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
