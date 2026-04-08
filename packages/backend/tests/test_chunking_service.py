"""Tests for the chunking service (Phase 2: paragraph-aware, section-aware)."""

import pytest
from app.services.chunking_service import (
    Chunk,
    chunk_text_with_pages,
    _parse_headings,
    _find_sentence_boundary,
    _find_sentence_boundary_reverse,
    _is_quality_chunk,
    _get_page_for_offset,
    _get_section_at_offset,
    _is_heading_marker,
    _is_reference_heading,
    _SECTION_KEYWORDS,
    _REFERENCE_HEADINGS,
)


# --- Chunk dataclass ---


def test_chunk_has_section_fields():
    c = Chunk(
        chunk_index=0,
        page_number=1,
        end_page_number=1,
        content="test content",
        section_title="Introduction",
        section_level=1,
    )
    assert c.section_title == "Introduction"
    assert c.section_level == 1


def test_chunk_section_fields_default_none():
    c = Chunk(chunk_index=0, page_number=1, end_page_number=1, content="test content")
    assert c.section_title is None
    assert c.section_level is None


def test_chunk_end_page_number_field():
    c = Chunk(
        chunk_index=0,
        page_number=3,
        end_page_number=5,
        content="test content",
    )
    assert c.page_number == 3
    assert c.end_page_number == 5


# --- _find_sentence_boundary ---


def test_find_sentence_boundary_period():
    text = "First sentence. Second sentence."
    pos = _find_sentence_boundary(text, 0, len(text))
    assert pos != -1
    assert text[:pos].endswith("sentence. ")


def test_find_sentence_boundary_exclamation():
    text = "Wow! What a result."
    pos = _find_sentence_boundary(text, 0, len(text))
    assert pos != -1
    assert text[:pos].endswith("Wow! ")


def test_find_sentence_boundary_question():
    text = "Is this true? Yes it is."
    pos = _find_sentence_boundary(text, 0, len(text))
    assert pos != -1
    assert text[:pos].endswith("true? ")


def test_find_sentence_boundary_avoids_abbreviations():
    text = "See e.g. Smith (2020). Next sentence."
    pos = _find_sentence_boundary(text, 0, len(text))
    # Should skip "e.g." and find the real sentence boundary
    assert pos != -1
    assert "Next" in text[pos:]


def test_find_sentence_boundary_no_boundary():
    text = "this is just a fragment without any sentence ending"
    pos = _find_sentence_boundary(text, 0, len(text))
    assert pos == -1


# --- _find_sentence_boundary_reverse ---


def test_find_sentence_boundary_reverse_finds_last():
    text = "First. Second. Third."
    pos = _find_sentence_boundary_reverse(text, 0, len(text))
    assert pos != -1
    # Should find the boundary before "Third"
    assert "Third" in text[pos:]


def test_find_sentence_boundary_reverse_none():
    text = "no sentence ending here"
    pos = _find_sentence_boundary_reverse(text, 0, len(text))
    assert pos == -1


# --- _is_quality_chunk ---


def test_is_quality_chunk_good_content():
    assert (
        _is_quality_chunk(
            "This is a proper sentence with enough content. It has multiple sentences."
        )
        is True
    )


def test_is_quality_chunk_too_short():
    assert _is_quality_chunk("Short.") is False


def test_is_quality_chunk_empty():
    assert _is_quality_chunk("") is False
    assert _is_quality_chunk("   ") is False


def test_is_quality_chunk_no_sentence_ending():
    assert (
        _is_quality_chunk("this is a fragment without any punctuation at the end")
        is False
    )


def test_is_quality_chunk_few_words():
    assert _is_quality_chunk("This is a sentence. But very few words here.") is False


def test_is_quality_chunk_table_exempt():
    # Must be >=50 chars to pass the length check before structured-content exemption
    assert _is_quality_chunk("[TABLE]\n" + "x" * 60 + "\n[/TABLE]") is True


def test_is_quality_chunk_figure_caption_exempt():
    # Must be >=50 chars to pass the length check before structured-content exemption
    assert (
        _is_quality_chunk(
            "[FIGURE CAPTION] Figure 1: Overview of the model architecture"
        )
        is True
    )


def test_is_quality_chunk_footer_rejected():
    assert _is_quality_chunk("Page 42") is False


# --- _get_page_for_offset ---


def test_get_page_for_offset_first_page():
    boundaries = [(0, 1), (500, 2), (1000, 3)]
    assert _get_page_for_offset(0, boundaries) == 1
    assert _get_page_for_offset(250, boundaries) == 1
    assert _get_page_for_offset(499, boundaries) == 1


def test_get_page_for_offset_second_page():
    boundaries = [(0, 1), (500, 2), (1000, 3)]
    assert _get_page_for_offset(500, boundaries) == 2
    assert _get_page_for_offset(750, boundaries) == 2


def test_get_page_for_offset_last_page():
    boundaries = [(0, 1), (500, 2), (1000, 3)]
    assert _get_page_for_offset(1000, boundaries) == 3
    assert _get_page_for_offset(2000, boundaries) == 3


# --- _get_section_at_offset ---


def test_get_section_at_offset_before_any_heading():
    headings = [(100, "Introduction", 1), (500, "Methods", 1)]
    title, level = _get_section_at_offset(50, headings)
    assert title is None
    assert level is None


def test_get_section_at_offset_after_first_heading():
    headings = [(100, "Introduction", 1), (500, "Methods", 1)]
    title, level = _get_section_at_offset(200, headings)
    assert title == "Introduction"
    assert level == 1


def test_get_section_at_offset_after_second_heading():
    headings = [(100, "Introduction", 1), (500, "Methods", 1)]
    title, level = _get_section_at_offset(600, headings)
    assert title == "Methods"
    assert level == 1


# --- _is_heading_marker ---


def test_is_heading_marker_matches():
    is_h, text, level = _is_heading_marker("[HEADING L2] Introduction")
    assert is_h is True
    assert text == "Introduction"
    assert level == 2


def test_is_heading_marker_no_match():
    is_h, text, level = _is_heading_marker("Regular paragraph text.")
    assert is_h is False
    assert text is None
    assert level is None


# --- _parse_headings ---


def test_parse_headings_font_markers():
    text = "Some text\n\n[HEADING L1] Introduction\n\nBody text here."
    headings = _parse_headings(text)
    assert len(headings) >= 1
    offsets = [h[0] for h in headings]
    titles = [h[1] for h in headings]
    assert "Introduction" in titles


def test_parse_headings_keyword_detection():
    text = "Previous paragraph.\n\nIntroduction\n\nBody text here."
    headings = _parse_headings(text)
    titles = [h[1] for h in headings]
    assert "Introduction" in titles


def test_parse_headings_numbered_detection():
    # Pattern requires at least one dot in the number: "1.1", "3.2", not "1."
    text = "Previous.\n\n1.1 First Section\n\nContent here."
    headings = _parse_headings(text)
    titles = [h[1] for h in headings]
    assert "First Section" in titles


def test_parse_headings_filters_running_headers():
    # Simulate a running header that appears on every page
    parts = []
    for i in range(10):
        parts.append(
            f"--- PAGE {i + 1} ---\n\nPaper Title\n\nSome content on page {i + 1}."
        )
    text = "\n\n".join(parts)
    headings = _parse_headings(text)
    titles = [h[1] for h in headings]
    # "Paper Title" should be filtered as a running header (>3 occurrences)
    assert "Paper Title" not in titles


# --- chunk_text_with_pages (integration) ---


def test_chunk_text_with_pages_basic():
    text = "--- PAGE 1 ---\n\nThis is the first paragraph with enough content. It has multiple sentences.\n\nSecond paragraph also has sufficient content. More text here for length."
    chunks = chunk_text_with_pages(text)
    assert len(chunks) >= 1
    assert all(isinstance(c, Chunk) for c in chunks)
    assert all(c.page_number == 1 for c in chunks)


def test_chunk_text_with_pages_multi_page():
    # Each page needs enough content to form its own chunk (>800 chars)
    page1_text = " ".join(
        f"This is sentence number {i} on page one with enough words." for i in range(20)
    )
    page2_text = " ".join(
        f"This is sentence number {i} on page two with enough words." for i in range(20)
    )
    text = f"--- PAGE 1 ---\n\n{page1_text}\n\n--- PAGE 2 ---\n\n{page2_text}"
    chunks = chunk_text_with_pages(text)
    assert len(chunks) >= 2
    # Check page spans cover both pages (page_number is start, end_page_number is end)
    all_pages = set()
    for c in chunks:
        for p in range(c.page_number, c.end_page_number + 1):
            all_pages.add(p)
    assert 1 in all_pages
    assert 2 in all_pages


def test_chunk_text_with_pages_section_metadata():
    text = "--- PAGE 1 ---\n\nIntroduction\n\nThis is the introduction paragraph. It has enough content to pass quality checks. Multiple sentences are included here."
    chunks = chunk_text_with_pages(text)
    assert len(chunks) >= 1
    # At least some chunks should have section metadata
    sections = [c.section_title for c in chunks if c.section_title]
    assert len(sections) > 0


def test_chunk_text_with_pages_empty():
    assert chunk_text_with_pages("") == []
    assert chunk_text_with_pages("--- PAGE 1 ---\n\n") == []


def test_chunk_text_with_pages_quality_filtering():
    # Add a very short paragraph that should be filtered
    text = "--- PAGE 1 ---\n\n" + "A" * 20
    chunks = chunk_text_with_pages(text)
    assert len(chunks) == 0


def test_chunk_text_with_pages_reindexing():
    text = "--- PAGE 1 ---\n\n" + "\n\n".join(
        f"This is paragraph {i} with enough content to pass quality checks. It has multiple sentences and sufficient length."
        for i in range(10)
    )
    chunks = chunk_text_with_pages(text)
    # Chunk indices should be sequential starting from 0
    indices = [c.chunk_index for c in chunks]
    assert indices == list(range(len(chunks)))


def test_chunk_text_with_pages_heading_as_hard_boundary():
    # Two long paragraphs with a heading between them.
    # Each paragraph has sentence endings so it passes quality.
    para_a = " ".join(f"This is sentence {i} with enough content." for i in range(15))
    para_b = " ".join(f"That is sentence {i} with enough content." for i in range(15))
    text = f"--- PAGE 1 ---\n\n{para_a}\n\nIntroduction\n\n{para_b}"
    chunks = chunk_text_with_pages(text)
    # The heading should cause a chunk boundary, producing at least 2 chunks
    assert len(chunks) >= 2
    # The second chunk should have "Introduction" as its section
    intro_chunks = [c for c in chunks if c.section_title == "Introduction"]
    assert len(intro_chunks) >= 1


# --- _is_reference_heading (Phase 3.2) ---


def test_is_reference_heading_exact_match():
    for heading in _REFERENCE_HEADINGS:
        assert _is_reference_heading(heading) is True


def test_is_reference_heading_case_insensitive():
    assert _is_reference_heading("References") is True
    assert _is_reference_heading("REFERENCES") is True
    assert _is_reference_heading("bibliography") is True


def test_is_reference_heading_with_numbering():
    assert _is_reference_heading("6. References") is True
    assert _is_reference_heading("References.") is True


def test_is_reference_heading_non_reference():
    assert _is_reference_heading("Introduction") is False
    assert _is_reference_heading("Methods") is False
    assert _is_reference_heading("Results and Discussion") is False


# --- Reference section skipping in chunking (Phase 3.2) ---


def test_chunk_text_skips_reference_section():
    """Content after a reference heading should not appear in any chunk."""
    para = " ".join(f"This is sentence {i} with enough content." for i in range(15))
    text = f"--- PAGE 1 ---\n\n{para}\n\nReferences\n\nSmith J. 2020. A paper title. Journal 1:1-10.\n\nJones K. 2021. Another paper title. Journal 2:20-30."
    chunks = chunk_text_with_pages(text)
    all_content = " ".join(c.content for c in chunks)
    # The reference entries should not appear
    assert "Smith J." not in all_content
    assert "Jones K." not in all_content


def test_chunk_text_skips_bibliography_section():
    """Content after 'Bibliography' heading should not appear in any chunk."""
    para = " ".join(f"This is sentence {i} with enough content." for i in range(15))
    text = f"--- PAGE 1 ---\n\n{para}\n\nBibliography\n\nAuthor A. 2019. Some work. Publisher."
    chunks = chunk_text_with_pages(text)
    all_content = " ".join(c.content for c in chunks)
    assert "Author A." not in all_content


def test_chunk_text_includes_content_before_references():
    """Content before reference section should still be chunked normally."""
    intro = " ".join(f"This is introduction sentence {i}." for i in range(15))
    text = f"--- PAGE 1 ---\n\nIntroduction\n\n{intro}\n\nReferences\n\nCitation here."
    chunks = chunk_text_with_pages(text)
    all_content = " ".join(c.content for c in chunks)
    assert "Introduction" in all_content or "introduction" in all_content.lower()


# --- Configurable chunk parameters (Phase 1.4 / TG-1) ---


def test_chunk_size_configurable_smaller(monkeypatch):
    """Smaller CHUNK_SIZE should produce more chunks."""
    monkeypatch.setattr("app.core.config.settings.CHUNK_SIZE", 300)
    monkeypatch.setattr("app.core.config.settings.CHUNK_OVERLAP", 50)

    paras = "\n\n".join(
        f"Paragraph number {i}. "
        + "This paragraph has enough words to be meaningful. " * 3
        for i in range(10)
    )
    text = f"--- PAGE 1 ---\n\n{paras}"

    # With default CHUNK_SIZE=800, this would produce ~2-3 chunks
    # With CHUNK_SIZE=300, we should get significantly more
    chunks = chunk_text_with_pages(text)
    assert len(chunks) >= 4


def test_chunk_size_configurable_larger(monkeypatch):
    """Larger CHUNK_SIZE should produce fewer, bigger chunks."""
    monkeypatch.setattr("app.core.config.settings.CHUNK_SIZE", 2000)
    monkeypatch.setattr("app.core.config.settings.CHUNK_OVERLAP", 200)

    paras = "\n\n".join(
        f"Paragraph number {i}. "
        + "This paragraph has enough words to be meaningful. " * 2
        for i in range(10)
    )
    text = f"--- PAGE 1 ---\n\n{paras}"

    chunks = chunk_text_with_pages(text)
    # With CHUNK_SIZE=2000, all content should fit in very few chunks
    assert len(chunks) <= 3
    # Each chunk should be substantially larger than the default would allow
    for c in chunks:
        assert len(c.content) > 400


def test_chunk_overlap_configurable(monkeypatch):
    """CHUNK_OVERLAP affects how much text is shared between consecutive chunks."""
    monkeypatch.setattr("app.core.config.settings.CHUNK_SIZE", 400)
    monkeypatch.setattr("app.core.config.settings.CHUNK_OVERLAP", 100)

    paras = "\n\n".join(
        f"Paragraph {i}. " + "Repeated sentence for content. " * 5 for i in range(8)
    )
    text = f"--- PAGE 1 ---\n\n{paras}"

    chunks = chunk_text_with_pages(text)
    assert len(chunks) >= 2

    # Verify overlap exists: consecutive chunks should share some text
    for i in range(len(chunks) - 1):
        words_curr = set(chunks[i].content.lower().split())
        words_next = set(chunks[i + 1].content.lower().split())
        shared = words_curr & words_next
        # With overlap of 100 chars, there should be some shared words
        assert len(shared) > 0


def test_chunk_size_default_not_broken(monkeypatch):
    """Verify chunking still works with default config values."""
    # Explicitly set to defaults to ensure no regression
    monkeypatch.setattr("app.core.config.settings.CHUNK_SIZE", 800)
    monkeypatch.setattr("app.core.config.settings.CHUNK_OVERLAP", 150)

    paras = "\n\n".join(
        f"This is paragraph {i}. " + "It contains multiple sentences. " * 4
        for i in range(5)
    )
    text = f"--- PAGE 1 ---\n\n{paras}"

    chunks = chunk_text_with_pages(text)
    assert len(chunks) >= 1
    assert all(c.chunk_index == i for i, c in enumerate(chunks))
    assert all(c.page_number == 1 for c in chunks)
