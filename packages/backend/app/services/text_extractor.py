"""PDF text extraction with page markers for LLM analysis."""
import re
from io import BytesIO
from typing import BinaryIO, Union

from pypdf import PdfReader

MAX_TEXT_LENGTH = 120_000


def extract_text_with_pages(pdf_file: Union[BinaryIO, BytesIO]) -> tuple[str, int, str]:
    """Extract text from PDF with page markers.

    Returns:
        tuple of (text_with_page_markers, total_pages, pages_analyzed_note)
        pages_analyzed_note is "all" or "1-N of M" if truncated.
    """
    reader = PdfReader(pdf_file)
    total_pages = len(reader.pages)
    parts: list[str] = []

    for i, page in enumerate(reader.pages, 1):
        text = page.extract_text() or ""
        parts.append(f"--- PAGE {i} ---\n{text}")

    full_text = "\n\n".join(parts)
    truncated_text, pages_note = _truncate_text(full_text, MAX_TEXT_LENGTH, total_pages)

    return truncated_text, total_pages, pages_note


def _truncate_text(text: str, max_length: int, total_pages: int = 0) -> tuple[str, str]:
    """Truncate text at max_length, breaking at page boundaries.

    Returns (truncated_text, pages_note).
    """
    if len(text) <= max_length:
        return text, "all"

    # Find all page markers in the full text (search full text, not truncated,
    # so we know whether a page's content fits completely before max_length)
    markers = [(m.start(), int(m.group(1))) for m in re.finditer(r"--- PAGE (\d+) ---", text)]

    if not markers:
        return text[:max_length], f"partial (truncated at {max_length} chars)"

    last_complete_page = 0
    cut_pos = 0

    for i, (pos, page_num) in enumerate(markers):
        if pos >= max_length:
            break  # This page doesn't start within our limit

        next_marker_pos = markers[i + 1][0] if i + 1 < len(markers) else len(text)

        if next_marker_pos <= max_length:
            # The next page marker fits → this page's content is complete
            last_complete_page = page_num
            cut_pos = next_marker_pos
        else:
            # This page's content is truncated → cut before it starts (if we have complete pages)
            # or include truncated content (if this is the first page)
            cut_pos = pos
            break

    if last_complete_page == 0:
        # No complete page fits within the limit; include truncated content of first page
        return text[:max_length], f"partial (truncated at {max_length} chars)"

    pages_note = f"1-{last_complete_page} of {total_pages}" if total_pages else f"1-{last_complete_page}"
    return text[:cut_pos].rstrip(), pages_note


def is_text_pdf(text: str) -> bool:
    """Check if extracted text indicates a text-based PDF (not scanned/image)."""
    clean = text.replace("--- PAGE ", "").strip()
    clean = re.sub(r"\d+ ---", "", clean).strip()
    return len(clean) >= 100
