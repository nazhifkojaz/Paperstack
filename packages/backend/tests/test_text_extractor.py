import io
from pypdf import PdfWriter
from app.services.text_extractor import extract_text_with_pages, _truncate_text, is_text_pdf


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
