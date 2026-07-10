"""Tests for the pluggable extraction backends (Phase C, Phase 1).

Fast unit tests that exercise ``PyMuPdf4LlmExtractor._parse_page`` and the
inline helpers with synthetic Markdown — no PDF I/O.
"""

from __future__ import annotations

import pytest

from app.services.extractors import (
    ExtractedDocument,
    PyMuPdf4LlmExtractor,
    PyMuPdfExtractor,
    RawBlock,
    get_extractor,
)
from app.services.extractors.pymupdf4llm_extractor import _clean_inline


# ---------------------------------------------------------------------------
# Fast unit tests — synthetic markdown, no PDF extraction
# ---------------------------------------------------------------------------


def test_clean_inline_strips_emphasis():
    assert _clean_inline("**bold** text") == "bold text"
    assert _clean_inline("_italic_ here") == "italic here"
    assert _clean_inline("`code`") == "code"
    assert _clean_inline("a<br>b") == "a b"
    assert _clean_inline("## **7 Conclusion**") == "## 7 Conclusion"


def test_get_extractor_returns_correct_backend():
    assert isinstance(get_extractor("pymupdf"), PyMuPdfExtractor)
    assert isinstance(get_extractor("pymupdf4llm"), PyMuPdf4LlmExtractor)


def test_get_extractor_rejects_unknown_backend():
    with pytest.raises(ValueError, match="Unknown extraction backend"):
        get_extractor("marker")


def test_extracted_document_defaults():
    doc = ExtractedDocument(page_count=0, extraction_backend="pymupdf")
    assert doc.blocks == []
    assert doc.title is None


def test_parse_page_classifies_blocks_and_tracks_sections():
    extractor = PyMuPdf4LlmExtractor()
    markdown = (
        "## **1 Introduction**\n\n"
        "This is the intro paragraph.\n\n"
        "## **2 Method**\n\n"
        "|Col A|Col B|\n"
        "|---|---|\n"
        "|1|2|\n\n"
        "Figure 1: A caption here.\n\n"
        "Some closing body text.\n"
    )
    blocks: list[RawBlock] = []
    section_stack: list[tuple[int, str]] = []
    extractor._parse_page(
        markdown,
        page_number=3,
        section_stack=section_stack,
        out=blocks,
    )

    types = [b.block_type for b in blocks]
    assert types == ["heading", "paragraph", "heading", "table", "caption", "paragraph"]

    # Heading titles cleaned of emphasis markers.
    assert "Introduction" in blocks[0].content
    assert blocks[0].section_path == ["1 Introduction"]
    # Intro paragraph inherits the Introduction section.
    assert blocks[1].section_path == ["1 Introduction"]
    assert blocks[1].page_number == 3
    # Second heading replaces the first (same level pops the stack).
    assert blocks[2].section_path == ["2 Method"]
    # Table, caption, and trailing paragraph all under "2 Method".
    for b in blocks[3:]:
        assert b.section_path == ["2 Method"]
    # Table content is the raw markdown span (atomic).
    assert "|Col A|" in blocks[3].content and "|---|" in blocks[3].content
    # Caption text is cleaned to plain text.
    assert blocks[4].content.startswith("Figure 1:")


def test_parse_page_drops_bare_page_number_folios():
    extractor = PyMuPdf4LlmExtractor()
    markdown = "9\n\nReal content paragraph here.\n"
    blocks: list[RawBlock] = []
    extractor._parse_page(markdown, page_number=9, section_stack=[], out=blocks)
    # The lone "9" must be dropped; only the real paragraph remains.
    assert len(blocks) == 1
    assert blocks[0].block_type == "paragraph"
    assert blocks[0].content == "Real content paragraph here."


def test_parse_page_nested_headings_build_section_path():
    extractor = PyMuPdf4LlmExtractor()
    markdown = (
        "# Title\n\n"
        "## 2 Method\n\n"
        "### 2.1 Setup\n\n"
        "Body under 2.1.\n\n"
        "## 3 Results\n\n"
        "Body under 3.\n"
    )
    blocks: list[RawBlock] = []
    extractor._parse_page(markdown, page_number=1, section_stack=[], out=blocks)
    # The paragraph under 2.1 should carry the full nested path.
    setup_body = next(b for b in blocks if b.content == "Body under 2.1.")
    assert setup_body.section_path == ["Title", "2 Method", "2.1 Setup"]
    # Moving to a level-2 "3 Results" pops 2.1 and 2 Method.
    results_body = next(b for b in blocks if b.content == "Body under 3.")
    assert results_body.section_path == ["Title", "3 Results"]
