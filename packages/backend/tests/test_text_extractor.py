import io
from pypdf import PdfWriter
from app.services.text_extractor import (
    extract_text_with_pages,
    _truncate_text,
    is_text_pdf,
    validate_extraction,
    _is_multi_column,
    _sort_blocks_column_then_row,
    _annotate_captions,
)


def _make_pdf(page_texts: list[str]) -> io.BytesIO:
    """Create a minimal in-memory PDF with blank pages (no text extraction needed for structure tests)."""
    writer = PdfWriter()
    for _ in page_texts:
        writer.add_blank_page(width=612, height=792)
    buf = io.BytesIO()
    writer.write(buf)
    buf.seek(0)
    return buf


def test_extract_text_with_pages_returns_page_markers():
    buf = _make_pdf(["page one", "page two"])
    text, total_pages, pages_analyzed = extract_text_with_pages(buf)
    assert total_pages == 2
    assert "--- PAGE 1 ---" in text
    assert "--- PAGE 2 ---" in text
    assert pages_analyzed == "all"


def test_extract_text_with_pages_empty_pdf():
    buf = _make_pdf([""])
    text, total_pages, pages_analyzed = extract_text_with_pages(buf)
    assert total_pages == 1
    assert "--- PAGE 1 ---" in text
    assert pages_analyzed == "all"


def test_truncate_text_short_text_unchanged():
    text = "--- PAGE 1 ---\nsome content\n\n--- PAGE 2 ---\nmore content"
    result, pages_note = _truncate_text(text, max_length=10000, total_pages=2)
    assert result == text
    assert pages_note == "all"


def test_truncate_text_cuts_at_page_boundary():
    # Build a long text with two page markers
    page1 = "--- PAGE 1 ---\n" + ("x" * 500)
    page2 = "--- PAGE 2 ---\n" + ("y" * 500)
    text = page1 + "\n\n" + page2

    # Truncate before page 2 starts
    result, pages_note = _truncate_text(text, max_length=len(page1) + 5, total_pages=2)
    assert "--- PAGE 2 ---" not in result
    assert "1-1 of 2" in pages_note


def test_truncate_text_note_when_no_page_marker():
    text = "x" * 2000
    result, pages_note = _truncate_text(text, max_length=1000, total_pages=0)
    assert len(result) <= 1000
    assert "partial" in pages_note


def test_is_text_pdf_with_content():
    text = "--- PAGE 1 ---\n" + "Some real text content. " * 10
    assert is_text_pdf(text) is True


def test_is_text_pdf_empty():
    text = "--- PAGE 1 ---\n\n--- PAGE 2 ---\n"
    assert is_text_pdf(text) is False


# --- validate_extraction ---


def test_validate_extraction_short_text():
    quality = validate_extraction("--- PAGE 1 ---\nshort")
    assert quality.is_usable is False
    assert quality.score == 0.0
    assert len(quality.warnings) == 1


def test_validate_extraction_good_text():
    text = "--- PAGE 1 ---\n" + "The quick brown fox jumps over the lazy dog. " * 20
    quality = validate_extraction(text)
    assert quality.is_usable is True
    assert quality.score >= 0.5


def test_validate_extraction_garbled_text():
    text = "--- PAGE 1 ---\n" + "x7k!@#m2$ " * 100
    quality = validate_extraction(text)
    assert quality.is_usable is False


def test_validate_extraction_high_repetition():
    # Single-character repetition with symbols triggers both low alpha and repetition warnings
    text = "--- PAGE 1 ---\n" + "x7!@# " * 200
    quality = validate_extraction(text)
    assert quality.is_usable is False
    assert any("repetition" in w.lower() for w in quality.warnings)


# --- _is_multi_column ---


def test_is_multi_column_detects_two_columns():
    page_width = 600.0
    blocks = [
        (50, 100, 150, 120, "left text 1", 0, 0),
        (50, 200, 150, 220, "left text 2", 0, 0),
        (50, 300, 150, 320, "left text 3", 0, 0),
        (50, 400, 150, 420, "left text 4", 0, 0),
        (400, 100, 550, 120, "right text 1", 0, 0),
        (400, 200, 550, 220, "right text 2", 0, 0),
        (400, 300, 550, 320, "right text 3", 0, 0),
        (400, 400, 550, 420, "right text 4", 0, 0),
    ]
    assert _is_multi_column(blocks, page_width) is True


def test_is_multi_column_single_column():
    page_width = 600.0
    blocks = [
        (50, 100, 550, 120, "full width 1", 0, 0),
        (50, 200, 550, 220, "full width 2", 0, 0),
        (50, 300, 550, 320, "full width 3", 0, 0),
    ]
    assert _is_multi_column(blocks, page_width) is False


def test_is_multi_column_empty_blocks():
    assert _is_multi_column([], 600.0) is False


# --- _sort_blocks_column_then_row ---


def test_sort_blocks_column_then_row_left_first():
    page_width = 600.0
    blocks = [
        (400, 100, 550, 120, "right top", 0, 0),
        (50, 100, 150, 120, "left top", 0, 0),
        (400, 200, 550, 220, "right bottom", 0, 0),
        (50, 200, 150, 220, "left bottom", 0, 0),
    ]
    sorted_blocks = _sort_blocks_column_then_row(blocks, page_width)
    texts = [b[4] for b in sorted_blocks]
    assert texts == ["left top", "left bottom", "right top", "right bottom"]


# --- _annotate_captions ---


def test_annotate_captions_figure():
    elements = [{"content": "Figure 1: Model architecture overview", "type": "text"}]
    result = _annotate_captions(elements)
    assert result[0]["type"] == "figure_caption"
    assert "[FIGURE CAPTION]" in result[0]["content"]


def test_annotate_captions_table():
    elements = [{"content": "Table 2: Results comparison", "type": "text"}]
    result = _annotate_captions(elements)
    assert result[0]["type"] == "table_caption"
    assert "[TABLE CAPTION]" in result[0]["content"]


def test_annotate_captions_ignores_non_caption():
    elements = [
        {
            "content": "This is just regular text about figures in general.",
            "type": "text",
        }
    ]
    result = _annotate_captions(elements)
    assert result[0]["type"] == "text"
