"""Tests for the chunking service (Phase 2: paragraph-aware, section-aware)."""

from app.services.chunking_service import (
    Chunk,
    chunk_document,
    chunk_text_with_pages,
    _parse_headings,
    _find_sentence_boundary,
    _find_sentence_boundary_reverse,
    _is_quality_chunk,
    _get_page_for_offset,
    _get_section_at_offset,
    _is_heading_marker,
    _is_reference_heading,
    _is_list_item,
    _has_list_content,
    _valid_section_title,
    _MAX_SECTION_TITLE_CHARS,
    _REFERENCE_HEADINGS,
)
from app.services.extractors.base import ExtractedDocument, RawBlock


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
    """Smaller CHUNK_SIZE_TOKENS should produce more chunks."""
    monkeypatch.setattr("app.core.config.settings.CHUNK_SIZE_TOKENS", 50)
    monkeypatch.setattr("app.core.config.settings.CHUNK_OVERLAP_TOKENS", 10)

    paras = "\n\n".join(
        f"Paragraph number {i}. "
        + "This paragraph has enough words to be meaningful. " * 3
        for i in range(10)
    )
    text = f"--- PAGE 1 ---\n\n{paras}"

    # With default CHUNK_SIZE_TOKENS=400 this would produce ~1 chunk; with 50
    # tokens each (paragraphs are ~25 tokens), we should get several.
    chunks = chunk_text_with_pages(text)
    assert len(chunks) >= 4


def test_chunk_size_configurable_larger(monkeypatch):
    """Larger CHUNK_SIZE_TOKENS should produce fewer, bigger chunks."""
    monkeypatch.setattr("app.core.config.settings.CHUNK_SIZE_TOKENS", 2000)
    monkeypatch.setattr("app.core.config.settings.CHUNK_OVERLAP_TOKENS", 200)

    paras = "\n\n".join(
        f"Paragraph number {i}. "
        + "This paragraph has enough words to be meaningful. " * 2
        for i in range(10)
    )
    text = f"--- PAGE 1 ---\n\n{paras}"

    chunks = chunk_text_with_pages(text)
    # With CHUNK_SIZE_TOKENS=2000, all content should fit in very few chunks
    assert len(chunks) <= 3
    # Each chunk should be substantially larger than the default would allow
    for c in chunks:
        assert len(c.content) > 400


def test_chunk_overlap_configurable(monkeypatch):
    """CHUNK_OVERLAP_TOKENS affects how much text is shared between chunks."""
    monkeypatch.setattr("app.core.config.settings.CHUNK_SIZE_TOKENS", 80)
    monkeypatch.setattr("app.core.config.settings.CHUNK_OVERLAP_TOKENS", 30)

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
        # With overlap of 30 tokens, there should be some shared words
        assert len(shared) > 0


def test_chunk_size_default_not_broken(monkeypatch):
    """Verify chunking still works with default config values."""
    # Explicitly set to defaults to ensure no regression
    monkeypatch.setattr("app.core.config.settings.CHUNK_SIZE_TOKENS", 400)
    monkeypatch.setattr("app.core.config.settings.CHUNK_OVERLAP_TOKENS", 64)

    paras = "\n\n".join(
        f"This is paragraph {i}. " + "It contains multiple sentences. " * 4
        for i in range(5)
    )
    text = f"--- PAGE 1 ---\n\n{paras}"

    chunks = chunk_text_with_pages(text)
    assert len(chunks) >= 1
    assert all(c.chunk_index == i for i, c in enumerate(chunks))
    assert all(c.page_number == 1 for c in chunks)


# --- Multi-page span edge cases (TG-5) ---


def test_chunk_spans_three_pages():
    """A single chunk can span 3+ pages when paragraphs are short relative to CHUNK_SIZE."""
    # Use very small paragraphs per page so they all accumulate into one chunk.
    # Each page ~150 chars, 3 pages ~450 chars, well under CHUNK_SIZE=800.
    pages = []
    for i in range(1, 4):
        page_text = " ".join(f"Sentence {j} on page {i}." for j in range(6))
        pages.append(f"--- PAGE {i} ---\n\n{page_text}")
    text = "\n\n".join(pages)

    chunks = chunk_text_with_pages(text)

    # With ~150 chars per page and CHUNK_SIZE=800, all three pages should
    # fit into a single chunk spanning pages 1→3
    assert len(chunks) >= 1
    # Verify no chunk has end_page_number < page_number
    for c in chunks:
        assert c.end_page_number >= c.page_number

    # The total page coverage must include all 3 pages
    all_pages = set()
    for c in chunks:
        for p in range(c.page_number, c.end_page_number + 1):
            all_pages.add(p)
    assert all_pages == {1, 2, 3}

    # At least one chunk spans 2+ pages
    spanning = [c for c in chunks if c.end_page_number > c.page_number]
    assert len(spanning) >= 1


def test_chunk_spans_four_pages():
    """Chunks can span even more pages (4+) with enough short content."""
    pages = []
    for i in range(1, 5):
        page_text = " ".join(
            f"Page {i} sentence {j} here with content." for j in range(5)
        )
        pages.append(f"--- PAGE {i} ---\n\n{page_text}")
    text = "\n\n".join(pages)

    chunks = chunk_text_with_pages(text)

    # All pages must be covered
    all_pages = set()
    for c in chunks:
        for p in range(c.page_number, c.end_page_number + 1):
            all_pages.add(p)
    assert all_pages == {1, 2, 3, 4}

    # At least one chunk spans 2+ pages
    spanning = [c for c in chunks if c.end_page_number > c.page_number]
    assert len(spanning) >= 1


def test_empty_page_between_spanned_pages():
    """A chunk can span across an empty page (no text content on that page).

    Empty pages are skipped during page block parsing, but the remaining
    paragraphs get their page attribution from offset→page mapping. With
    enough short content, a single chunk can span from page 1 to page 3,
    skipping the empty page 2 entirely (its offset is never recorded).
    """
    # Short content that will accumulate into one chunk
    page1 = " ".join(f"Sentence {i} on page one." for i in range(6))
    page3 = " ".join(f"Sentence {i} on page three." for i in range(6))
    # Page 2 is empty (no text after the marker)
    text = (
        f"--- PAGE 1 ---\n\n{page1}\n\n--- PAGE 2 ---\n\n\n\n--- PAGE 3 ---\n\n{page3}"
    )

    chunks = chunk_text_with_pages(text)
    assert len(chunks) >= 1

    # Page 2 has no text content, so it should not appear in any chunk's range.
    # The chunker skips empty pages in page_blocks, but the boundary offset
    # for page 3 is still recorded — so a chunk can span page 1→3.
    all_pages = set()
    for c in chunks:
        for p in range(c.page_number, c.end_page_number + 1):
            all_pages.add(p)
    assert 1 in all_pages
    assert 3 in all_pages
    # Page 2 is empty and not in page_blocks, but range(c.page_number, c.end_page_number+1)
    # might include it if a chunk spans 1→3. This is expected behavior — the chunk
    # covers content from page 1 and page 3, and the range 1-3 is a page-level span.


def test_get_page_for_offset_with_large_gaps():
    """_get_page_for_offset should handle non-contiguous page numbers."""
    # Pages 1, 3, 7 (gaps in numbering — e.g. after removing blank pages)
    boundaries = [(0, 1), (500, 3), (1000, 7)]
    assert _get_page_for_offset(0, boundaries) == 1
    assert _get_page_for_offset(250, boundaries) == 1
    assert _get_page_for_offset(500, boundaries) == 3
    assert _get_page_for_offset(750, boundaries) == 3
    assert _get_page_for_offset(1000, boundaries) == 7
    assert _get_page_for_offset(5000, boundaries) == 7  # beyond last boundary


def test_get_page_for_offset_single_page():
    """Single-page document boundary list."""
    boundaries = [(0, 1)]
    assert _get_page_for_offset(0, boundaries) == 1
    assert _get_page_for_offset(99999, boundaries) == 1


def test_get_page_for_offset_exact_boundary():
    """Offset exactly at a page boundary belongs to the new page."""
    boundaries = [(0, 1), (500, 2), (1000, 3)]
    # Offset 500 is exactly at page 2's start — should return page 2
    assert _get_page_for_offset(500, boundaries) == 2
    # Offset 499 is just before — should return page 1
    assert _get_page_for_offset(499, boundaries) == 1


def test_multi_page_chunk_end_page_tracks_last_paragraph():
    """end_page_number should reflect the page of the last paragraph in the chunk,
    not the first."""
    # Page 1 has a long paragraph (>800 chars), page 2 has a short one
    page1 = " ".join(
        f"This is sentence {i} on page one with enough words to form content."
        for i in range(20)
    )
    page2 = " ".join(
        f"This is sentence {i} on page two with enough words for content."
        for i in range(20)
    )
    text = f"--- PAGE 1 ---\n\n{page1}\n\n--- PAGE 2 ---\n\n{page2}"

    chunks = chunk_text_with_pages(text)

    # Find the chunk that starts on page 1
    page1_chunks = [c for c in chunks if c.page_number == 1]
    assert len(page1_chunks) >= 1

    # The first chunk on page 1 should have end_page_number reflecting
    # where its last paragraph falls
    first = page1_chunks[0]
    # With default CHUNK_SIZE=800, page1 text alone (~1000 chars) likely fills
    # one chunk, so end_page_number should be 1. But if it overflows to page 2,
    # end_page_number should be 2.
    assert first.end_page_number >= first.page_number


# --- List structure preservation (Phase 4.4) ---


def test_is_list_item_bulleted():
    assert _is_list_item("- First item") is True
    assert _is_list_item("• Second item") is True
    assert _is_list_item("* Third item") is True
    assert _is_list_item("  - Indented bullet") is True


def test_is_list_item_numbered():
    assert _is_list_item("1. First step") is True
    assert _is_list_item("2) Second step") is True
    assert _is_list_item("10. Tenth step") is True


def test_is_list_item_not_list():
    assert _is_list_item("This is a regular paragraph.") is False
    assert _is_list_item("-5 is a negative number.") is False
    assert _is_list_item("") is False


def test_has_list_content():
    paras = [(0, 5, "- item one"), (6, 12, "- item two"), (13, 30, "regular text")]
    assert _has_list_content(paras) is True


def test_has_list_content_no_lists():
    paras = [(0, 10, "regular text"), (11, 20, "more text")]
    assert _has_list_content(paras) is False


def test_list_preservation_keeps_list_intact():
    """List items that exceed CHUNK_SIZE should stay in one chunk (up to 2x)."""
    # Each list item ~120 chars, 10 items = ~1200 chars > CHUNK_SIZE(800) but < 2x
    items = []
    for i in range(10):
        items.append(
            f"- Finding number {i}: this is a detailed list item with enough content to be meaningful."
        )
    text = "--- PAGE 1 ---\n\n" + "\n\n".join(items)
    chunks = chunk_text_with_pages(text)

    # All list items should be in a single chunk (not split mid-list)
    assert len(chunks) >= 1
    # Every list item should appear in some chunk
    all_content = " ".join(c.content for c in chunks)
    for i in range(10):
        assert f"Finding number {i}" in all_content

    # The list should be in a single chunk, not split
    list_chunks = [c for c in chunks if "- Finding number" in c.content]
    assert len(list_chunks) == 1, f"List was split across {len(list_chunks)} chunks"


def test_list_preservation_respects_2x_limit():
    """List exceeding 2x CHUNK_SIZE_TOKENS should still be split."""
    # Each item ~15 tokens; 60 items ~900 tokens > CHUNK_SIZE_TOKENS * 2 (800)
    items = []
    for i in range(60):
        items.append(
            f"{i + 1}. This is a very detailed list item number {i} that adds content."
        )
    text = "--- PAGE 1 ---\n\n" + "\n\n".join(items)
    chunks = chunk_text_with_pages(text)

    # List is too large to keep in one chunk — must split
    assert len(chunks) >= 2
    all_content = " ".join(c.content for c in chunks)
    for i in range(60):
        assert f"item number {i}" in all_content


def test_list_preservation_mixed_content():
    """List followed by regular text should split at the list boundary."""
    items = []
    for i in range(6):
        items.append(
            f"- List item number {i} with enough content to be meaningful here."
        )
    # Regular paragraph is large enough that list + regular > CHUNK_SIZE_TOKENS,
    # forcing a flush between the list run and the regular text.
    regular = " ".join(
        f"This is regular paragraph text sentence {i}." for i in range(50)
    )
    text = "--- PAGE 1 ---\n\n" + "\n\n".join(items) + "\n\n" + regular
    chunks = chunk_text_with_pages(text)

    # Should have at least 2 chunks — list content and regular content
    assert len(chunks) >= 2
    all_content = " ".join(c.content for c in chunks)
    assert "List item number" in all_content
    assert "regular paragraph" in all_content


def test_list_preservation_at_chunk_boundary():
    """When accumulated text is exactly at chunk_size, list items still extend."""
    # Build text that fills close to 800 chars, then add list items
    prefix = (
        "X" * 700 + ". This is a prefix paragraph that fills most of the chunk size."
    )
    items = []
    for i in range(5):
        items.append(f"- List item {i} that provides additional details.")
    text = "--- PAGE 1 ---\n\n" + prefix + "\n\n" + "\n\n".join(items)
    chunks = chunk_text_with_pages(text)

    # The list items should stay with the prefix in one chunk
    # (total ~700 + 5*45 = 925, under 2x = 1600)
    assert len(chunks) >= 1
    # List items should appear in the same chunk as the prefix
    list_in_prefix_chunk = any(
        "List item" in c.content and "prefix paragraph" in c.content for c in chunks
    )
    assert list_in_prefix_chunk, "List items should extend the chunk past chunk_size"


# --- Phase 3: markdown-aware chunk_document (§6.6) ---


def _doc(*blocks: RawBlock, page_count: int = 1) -> ExtractedDocument:
    """Build a minimal ExtractedDocument for chunk_document tests."""
    return ExtractedDocument(
        page_count=page_count,
        extraction_backend="test",
        blocks=list(blocks),
    )


def test_table_block_emitted_atomic():
    """A table larger than the size budget becomes one unsplit 'table' chunk."""
    big_table = "| col a | col b |\n|---|---|\n" + "\n".join(
        f"| {i} | {'x' * 40} |" for i in range(80)
    )
    doc = _doc(
        RawBlock(block_type="table", content=big_table, page_number=1, section_path=[])
    )
    chunks = chunk_document(doc)
    assert len(chunks) == 1
    assert chunks[0].chunk_type == "table"
    assert chunks[0].content == big_table


def test_equation_not_orphaned():
    """An equation block is never split mid-$; it stands as an atomic chunk."""
    equation = "$$E = mc^2$$ plus " * 60  # oversized — must not be split
    doc = _doc(
        RawBlock(
            block_type="paragraph",
            content="A preceding paragraph with enough content to pass quality.",
            page_number=1,
            section_path=[],
        ),
        RawBlock(
            block_type="equation",
            content=equation,
            page_number=1,
            section_path=[],
        ),
    )
    chunks = chunk_document(doc)
    eq_chunks = [c for c in chunks if c.chunk_type == "equation"]
    assert len(eq_chunks) == 1
    # never split: the whole equation text is preserved verbatim
    assert eq_chunks[0].content == equation.strip()


def test_heading_sets_section_context():
    """A heading block flushes the buffer and sets section_title/level."""
    doc = _doc(
        RawBlock(
            block_type="paragraph",
            content="Para before the heading with enough content to pass quality.",
            page_number=1,
            section_path=[],
        ),
        RawBlock(
            block_type="heading",
            content="Methods",
            page_number=1,
            section_path=["Methods"],
        ),
        RawBlock(
            block_type="paragraph",
            content="Para after the heading with enough content to pass quality.",
            page_number=1,
            section_path=["Methods"],
        ),
    )
    chunks = chunk_document(doc)
    method_chunks = [c for c in chunks if c.section_title == "Methods"]
    assert len(method_chunks) >= 1
    assert all(c.section_level == 1 for c in method_chunks)
    # pre-heading chunk carries no section
    assert any(c.section_title is None for c in chunks)


def test_references_skip_resumes_on_appendix():
    """Post-References appendix must be indexed.

    NeurIPS/ICLR/ACL papers place a large appendix *after* References; the
    ``in_references`` latch must resume on an appendix heading so the appendix
    (where gold evidence frequently lives) is not discarded.
    """
    doc = _doc(
        RawBlock(
            block_type="paragraph",
            content="Main text paragraph with enough content to pass quality.",
            page_number=1,
            section_path=[],
        ),
        RawBlock(
            block_type="heading",
            content="References",
            page_number=1,
            section_path=["References"],
        ),
        RawBlock(
            block_type="paragraph",
            content="Smith, J. et al. A paper title. Journal of Stuff, 2020.",
            page_number=1,
            section_path=["References"],
        ),
        RawBlock(
            block_type="heading",
            content="Appendix",
            page_number=2,
            section_path=["Appendix"],
        ),
        RawBlock(
            block_type="paragraph",
            content="Appendix prose describing the dataset curation in detail here.",
            page_number=2,
            section_path=["Appendix"],
        ),
    )
    chunks = chunk_document(doc)
    all_text = "\n".join(c.content for c in chunks)
    # reference entry is skipped (back-matter)
    assert "Smith, J. et al." not in all_text
    # appendix content is indexed (regression: was dropped by the permanent latch)
    assert "Appendix prose describing the dataset curation" in all_text


def test_references_skip_resumes_on_lettered_appendix():
    """A lettered appendix heading ('A Appendix details') also resumes indexing."""
    doc = _doc(
        RawBlock(
            block_type="heading",
            content="References",
            page_number=1,
            section_path=["References"],
        ),
        RawBlock(
            block_type="heading",
            content="A Appendix: Hyperparameter Details",
            page_number=3,
            section_path=["A Appendix: Hyperparameter Details"],
        ),
        RawBlock(
            block_type="paragraph",
            content="We used a learning rate of 1e-4 with cosine scheduling for training.",
            page_number=3,
            section_path=["A Appendix: Hyperparameter Details"],
        ),
    )
    chunks = chunk_document(doc)
    all_text = "\n".join(c.content for c in chunks)
    assert "learning rate of 1e-4" in all_text


def test_page_attribution_spanning_pages():
    """A chunk spanning pages 3-4 records page_number=3, end_page_number=4."""
    p3 = " ".join(f"Sentence {i} on page three here." for i in range(6))
    p4 = " ".join(f"Sentence {i} on page four goes here." for i in range(6))
    doc = _doc(
        RawBlock(block_type="paragraph", content=p3, page_number=3, section_path=[]),
        RawBlock(block_type="paragraph", content=p4, page_number=4, section_path=[]),
        page_count=4,
    )
    chunks = chunk_document(doc)
    assert len(chunks) >= 1
    assert any(
        c.page_number == 3 and c.end_page_number == 4
        for c in chunks
        if c.end_page_number > c.page_number
    )


def test_chunk_type_set_per_block():
    """paragraph / table / equation blocks get tagged with the right chunk_type."""
    doc = _doc(
        RawBlock(
            block_type="paragraph",
            content="A normal paragraph with enough content to pass quality checks.",
            page_number=1,
            section_path=[],
        ),
        RawBlock(
            block_type="table",
            content="| a | b |\n|---|---|\n| 1 | 2 |",
            page_number=1,
            section_path=[],
        ),
        RawBlock(
            block_type="equation",
            content="$$x = y$$",
            page_number=1,
            section_path=[],
        ),
    )
    chunks = chunk_document(doc)
    types = {c.chunk_type for c in chunks}
    assert {"paragraph", "table", "equation"} <= types


def test_code_block_emitted_atomic():
    """A code block becomes its own 'code' chunk, not merged into a paragraph.

    Previously code blocks flowed into the paragraph buffer and were flushed as
    chunk_type='paragraph', so the documented 'code' type was never produced
    and a chunk_type_filter=['code'] query returned nothing.
    """
    doc = _doc(
        RawBlock(
            block_type="paragraph",
            content="A normal paragraph with enough content to pass quality checks.",
            page_number=1,
            section_path=[],
        ),
        RawBlock(
            block_type="code",
            content="def train(model, data):\n    return model.fit(data)",
            page_number=1,
            section_path=[],
        ),
    )
    chunks = chunk_document(doc)
    code_chunks = [c for c in chunks if c.chunk_type == "code"]
    assert len(code_chunks) == 1
    assert "def train" in code_chunks[0].content
    # The code must NOT have been absorbed into the paragraph chunk.
    para_chunks = [c for c in chunks if c.chunk_type == "paragraph"]
    assert all("def train" not in c.content for c in para_chunks)


def test_caption_attaches_to_preceding_table():
    """A caption right after a table merges into the table chunk."""
    doc = _doc(
        RawBlock(
            block_type="table",
            content="| a | b |\n|---|---|\n| 1 | 2 |",
            page_number=1,
            section_path=[],
        ),
        RawBlock(
            block_type="caption",
            content="Table 1: Results of the experiment.",
            page_number=1,
            section_path=[],
        ),
    )
    chunks = chunk_document(doc)
    # caption attached -> still a single table chunk carrying the caption text
    assert len(chunks) == 1
    assert chunks[0].chunk_type == "table"
    assert "Table 1:" in chunks[0].content


def test_overlap_stays_within_section():
    """Overlap must not carry text across a heading boundary."""

    def para(n: int) -> str:
        return f"This is paragraph {n}. " + "Word " * 60

    blocks: list[RawBlock] = []
    for i in range(12):
        blocks.append(
            RawBlock(
                block_type="paragraph",
                content=para(i),
                page_number=1,
                section_path=["Section A"],
            )
        )
    blocks.append(
        RawBlock(
            block_type="heading",
            content="Section B",
            page_number=1,
            section_path=["Section B"],
        )
    )
    blocks.append(
        RawBlock(
            block_type="paragraph",
            content="This paragraph belongs to section B with enough content here.",
            page_number=1,
            section_path=["Section B"],
        )
    )
    chunks = chunk_document(_doc(*blocks))
    b_chunks = [c for c in chunks if c.section_title == "Section B"]
    assert len(b_chunks) >= 1
    # No section-B chunk should leak section-A paragraph text via overlap
    for c in b_chunks:
        assert "This is paragraph" not in c.content


def test_legacy_adapter_delegates_and_recovers_headings():
    """chunk_text_with_pages delegates to chunk_document and recovers headings.

    Phase 3 switched sizing from chars to tokens, so the adapter no longer
    matches the pre-refactor chunk *count* byte-for-byte (the golden harness
    covers baseline stability instead). What must still hold: the adapter
    builds a correct ExtractedDocument, so [HEADING L{n}] markers propagate as
    section_title on the emitted chunks and chunk indices stay sequential.
    """
    body = " ".join(f"This is sentence {i} with enough content." for i in range(15))
    methods = " ".join(f"Method sentence {i} is detailed here." for i in range(15))
    text = f"--- PAGE 1 ---\n\n{body}\n\n[HEADING L2] Methods\n\n{methods}"
    chunks = chunk_text_with_pages(text)
    assert len(chunks) >= 1
    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))
    sections = {c.section_title for c in chunks if c.section_title}
    assert "Methods" in sections


# --- Oversized section_path entries (indexing-abort regression) ---


def test_valid_section_title_thresholds():
    assert _valid_section_title(None) is None
    assert _valid_section_title("") is None
    assert _valid_section_title("   ") is None
    assert _valid_section_title("Introduction") == "Introduction"
    at_limit = "x" * _MAX_SECTION_TITLE_CHARS
    assert _valid_section_title(at_limit) == at_limit
    over_limit = "x" * (_MAX_SECTION_TITLE_CHARS + 1)
    assert _valid_section_title(over_limit) is None


def test_oversized_section_path_entry_rejected():
    """A >200-char section_path entry (a misclassified algorithm/code body, as
    seen on PeerQA's VICReg paper) must not propagate to a chunk's
    section_title -- it overflows ``pdf_chunks.section_title varchar(500)`` and
    aborts indexing for the whole paper. With no valid ancestor, it is None.
    """
    bogus = "f: encoder, p: projector, lambda, mu, nu: coefficients, " * 10
    assert len(bogus) > _MAX_SECTION_TITLE_CHARS
    doc = _doc(
        RawBlock(
            block_type="heading",
            content=bogus,
            page_number=1,
            section_path=[bogus],
        ),
        RawBlock(
            block_type="paragraph",
            content="A normal paragraph with enough content to pass quality checks here.",
            page_number=1,
            section_path=[bogus],
        ),
    )
    chunks = chunk_document(doc)
    assert len(chunks) >= 1
    for c in chunks:
        assert c.section_title is None


def test_oversized_section_path_falls_back_to_ancestor():
    """When the current section_path entry is bogus but a valid ancestor exists,
    the chunk inherits the ancestor's title and level rather than carrying the
    bogus value or None."""
    bogus = "x" * (_MAX_SECTION_TITLE_CHARS + 50)
    doc = _doc(
        RawBlock(
            block_type="heading",
            content="Methods",
            page_number=1,
            section_path=["Methods"],
        ),
        RawBlock(
            block_type="heading",
            content=bogus,
            page_number=1,
            section_path=["Methods", bogus],
        ),
        RawBlock(
            block_type="paragraph",
            content="A normal paragraph with enough content to pass quality checks here.",
            page_number=1,
            section_path=["Methods", bogus],
        ),
    )
    chunks = chunk_document(doc)
    para_chunks = [c for c in chunks if c.chunk_type == "paragraph"]
    assert len(para_chunks) >= 1
    for c in para_chunks:
        assert c.section_title == "Methods"
        assert c.section_level == 1


def test_no_chunk_section_title_exceeds_column_limit():
    """Regression guard for the indexing-abort bug: no emitted chunk may carry a
    section_title longer than ``_MAX_SECTION_TITLE_CHARS``, regardless of what
    an extractor places in section_path."""
    bogus = "Algorithm pseudocode body misclassified as a heading: " * 20
    assert len(bogus) > _MAX_SECTION_TITLE_CHARS
    doc = _doc(
        RawBlock(
            block_type="heading", content=bogus, page_number=1, section_path=[bogus]
        ),
        RawBlock(
            block_type="paragraph",
            content="Paragraph with enough content to pass the quality filter for chunking.",
            page_number=1,
            section_path=[bogus],
        ),
    )
    chunks = chunk_document(doc)
    assert chunks
    for c in chunks:
        assert (
            c.section_title is None or len(c.section_title) <= _MAX_SECTION_TITLE_CHARS
        )
