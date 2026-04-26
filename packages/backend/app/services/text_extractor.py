"""PDF text extraction with page markers, using PyMuPDF for layout-aware extraction."""

import logging
import re
from dataclasses import dataclass
from io import BytesIO
from typing import BinaryIO, Optional, Union

import pymupdf  # PyMuPDF >= 1.27

logger = logging.getLogger(__name__)

MAX_TEXT_LENGTH = 500_000

_FIGURE_CAPTION_RE = re.compile(
    r"^((?:Figure|Fig\.?)\s*\d+[.:)\-]\s*.+)", re.IGNORECASE | re.MULTILINE
)
_TABLE_CAPTION_RE = re.compile(
    r"^((?:Table|Tab\.?)\s*\d+[.:)\-]\s*.+)", re.IGNORECASE | re.MULTILINE
)


def extract_text_with_pages(
    pdf_file: Union[BinaryIO, BytesIO],
    pages: Optional[list[int]] = None,
) -> tuple[str, int, str]:
    """Extract text from PDF with page markers, respecting column layout.

    Args:
        pages: Specific page numbers to extract (1-indexed). None = all pages.

    Returns:
        tuple of (text_with_page_markers, total_pages, pages_analyzed_note)
        pages_analyzed_note is "all" or a description like "1, 4, 5 of 20".
    """
    with pymupdf.open(stream=pdf_file.read(), filetype="pdf") as doc:
        total_pages = len(doc)
        parts: list[str] = []

        if pages is not None:
            page_indices = sorted({max(0, min(p - 1, total_pages - 1)) for p in pages})
        else:
            page_indices = list(range(total_pages))

        for page_idx in page_indices:
            page = doc[page_idx]
            page_text = _extract_page_in_reading_order(page)
            parts.append(f"--- PAGE {page_idx + 1} ---\n{page_text}")

        full_text = "\n\n".join(parts)

        if pages is not None and len(page_indices) < total_pages:
            page_nums = sorted(set(pages))
            count = len(page_nums)
            if count <= 5:
                pages_note = f"{count} pages ({', '.join(str(p) for p in page_nums)} of {total_pages})"
            else:
                pages_note = f"{count} pages ({page_nums[0]}–{page_nums[-1]} of {total_pages})"
        else:
            truncated_text, pages_note = _truncate_text(
                full_text, MAX_TEXT_LENGTH, total_pages
            )
            return truncated_text, total_pages, pages_note

        truncated_text, _ = _truncate_text(full_text, MAX_TEXT_LENGTH, total_pages)
        return truncated_text, total_pages, pages_note


def _extract_page_with_headings(page: pymupdf.Page) -> list[dict]:
    """Extract page text with heading annotations using font metadata.

    Returns list of {"type": "heading"|"text", "level": int, "content": str, "y": float}
    """
    blocks = page.get_text("dict")["blocks"]

    # First pass: determine the median font size (body text size)
    font_sizes = []
    for block in blocks:
        if block["type"] != 0:  # skip image blocks
            continue
        for line in block["lines"]:
            for span in line["spans"]:
                if span["text"].strip():
                    font_sizes.append(span["size"])

    if not font_sizes:
        return []

    median_size = sorted(font_sizes)[len(font_sizes) // 2]

    # Second pass: extract text with heading detection
    elements = []
    for block in blocks:
        if block["type"] != 0:
            continue

        block_lines = []
        is_heading = False
        heading_level = 0

        for line in block["lines"]:
            line_text = ""
            for span in line["spans"]:
                text = span["text"].strip()
                if not text:
                    continue

                size = span["size"]
                is_bold = (
                    "bold" in span["font"].lower() or "heavy" in span["font"].lower()
                )

                # Heading detection: font size significantly larger than body text
                if size > median_size * 1.3 and is_bold:
                    is_heading = True
                    if size > median_size * 2.0:
                        heading_level = 1  # Title
                    elif size > median_size * 1.6:
                        heading_level = 2  # Section heading
                    else:
                        heading_level = 3  # Subsection heading

                line_text += span["text"]

            if line_text.strip():
                block_lines.append(line_text.strip())

        content = " ".join(block_lines)
        if not content:
            continue

        if is_heading and heading_level > 0:
            elements.append(
                {
                    "type": "heading",
                    "level": heading_level,
                    "content": content,
                    "y": block["bbox"][1],
                    "x": block["bbox"][0],
                }
            )
        else:
            elements.append(
                {
                    "type": "text",
                    "level": 0,
                    "content": content,
                    "y": block["bbox"][1],
                    "x": block["bbox"][0],
                }
            )

    return elements


def _extract_tables_from_page(page: pymupdf.Page) -> list[dict]:
    """Detect and extract tables from a PDF page.

    Returns list of {"bbox": (x0,y0,x1,y1), "markdown": str} for each table found.
    """
    tables = []

    try:
        tab = page.find_tables()
        for table in tab.tables:
            md = table.to_markdown()
            bbox = table.bbox
            tables.append(
                {
                    "bbox": bbox,
                    "markdown": md,
                }
            )
    except Exception as exc:
        logger.debug("Table detection failed on page: %s", exc)

    return tables


def _annotate_captions(elements: list[dict]) -> list[dict]:
    """Mark figure/table captions in extracted elements."""
    for elem in elements:
        text = elem["content"].strip()
        if _FIGURE_CAPTION_RE.match(text):
            elem["type"] = "figure_caption"
            elem["content"] = f"\n[FIGURE CAPTION] {elem['content']}\n"
        elif _TABLE_CAPTION_RE.match(text):
            elem["type"] = "table_caption"
            elem["content"] = f"\n[TABLE CAPTION] {elem['content']}\n"
    return elements


def _extract_page_in_reading_order(page: pymupdf.Page) -> str:
    """Extract text with tables, headings, and proper column reading order."""
    blocks = page.get_text("blocks")
    tables = _extract_tables_from_page(page)
    heading_elements = _extract_page_with_headings(page)

    if not blocks:
        return ""

    # Filter out image blocks and text blocks that overlap with detected tables
    text_blocks = []
    for b in blocks:
        if b[6] == 0:  # text block
            block_rect = pymupdf.Rect(b[:4])
            is_table_content = any(
                pymupdf.Rect(t["bbox"]).intersects(block_rect) for t in tables
            )
            if not is_table_content:
                text_blocks.append(b)

    if not text_blocks and not tables:
        return ""

    # Apply multi-column reading order to the remaining text blocks
    if _is_multi_column(text_blocks, page.rect.width):
        sorted_text_blocks = _sort_blocks_column_then_row(text_blocks, page.rect.width)
    else:
        sorted_text_blocks = sorted(text_blocks, key=lambda b: (b[1], b[0]))

    # Build unified element list: sorted text blocks + table elements + heading elements
    elements = []
    for b in sorted_text_blocks:
        elements.append({"type": "text", "y": b[1], "x": b[0], "content": b[4].strip()})

    for t in tables:
        elements.append(
            {
                "type": "table",
                "y": t["bbox"][1],
                "x": t["bbox"][0],
                "content": f"\n[TABLE]\n{t['markdown']}\n[/TABLE]\n",
            }
        )

    # Add heading annotations from font analysis
    for h in heading_elements:
        if h["type"] == "heading":
            elements.append(
                {
                    "type": "heading",
                    "level": h["level"],
                    "y": h["y"],
                    "x": h.get("x", 0),
                    "content": f"\n[HEADING L{h['level']}] {h['content']}\n",
                }
            )

    # Annotate figure/table captions
    elements = _annotate_captions(elements)

    # Tables and headings are inserted at their y-position among already-sorted text blocks.
    # Since text blocks are already in reading order, only sort tables/headings into position.
    text_elems = [e for e in elements if e["type"] == "text"]
    structural_elems = sorted(
        [
            e
            for e in elements
            if e["type"] in ("table", "heading", "figure_caption", "table_caption")
        ],
        key=lambda e: e["y"],
    )

    # Merge: insert each structural element after the last text element with y <= its y
    result = []
    struct_idx = 0
    for te in text_elems:
        while (
            struct_idx < len(structural_elems)
            and structural_elems[struct_idx]["y"] <= te["y"]
        ):
            result.append(structural_elems[struct_idx]["content"])
            struct_idx += 1
        result.append(te["content"])
    # Append remaining structural elements
    while struct_idx < len(structural_elems):
        result.append(structural_elems[struct_idx]["content"])
        struct_idx += 1

    return "\n\n".join(c for c in result if c)


def _is_multi_column(blocks: list, page_width: float) -> bool:
    """Detect if the page has a multi-column layout.

    Strategy: Check if text blocks cluster into distinct horizontal groups
    (left column and right column) with a gap in between.
    """
    if not blocks:
        return False

    mid_page = page_width / 2
    left_centers = []
    right_centers = []

    for b in blocks:
        x_center = (b[0] + b[2]) / 2
        block_width = b[2] - b[0]
        # Skip full-width blocks (headers, titles)
        if block_width > page_width * 0.8:
            continue
        if x_center < mid_page:
            left_centers.append(x_center)
        else:
            right_centers.append(x_center)

    # Multi-column if there are significant numbers of blocks on both sides
    if len(left_centers) < 3 or len(right_centers) < 3:
        return False

    # Check that left and right clusters are well-separated
    left_max = max(left_centers)
    right_min = min(right_centers)
    gap = right_min - left_max

    return gap > page_width * 0.05  # At least 5% page width gap between columns


def _sort_blocks_column_then_row(blocks: list, page_width: float) -> list:
    """Sort blocks for multi-column reading: left column top-to-bottom, then right.

    Full-width blocks act as column separators — they are emitted at their
    y-position relative to both columns. Between two full-width blocks, all
    left-column blocks are emitted (top-to-bottom) before right-column blocks.
    """
    mid_page = page_width / 2
    left_blocks = []
    right_blocks = []
    full_width_blocks = []

    for b in blocks:
        x_center = (b[0] + b[2]) / 2
        block_width = b[2] - b[0]
        if block_width > page_width * 0.8:
            full_width_blocks.append(b)
        elif x_center < mid_page:
            left_blocks.append(b)
        else:
            right_blocks.append(b)

    # Sort each group by y-position (top to bottom)
    left_blocks.sort(key=lambda b: b[1])
    right_blocks.sort(key=lambda b: b[1])
    full_width_blocks.sort(key=lambda b: b[1])

    # Use full-width blocks as "fences" that separate column groups.
    fences = [b[1] for b in full_width_blocks]  # y-positions of full-width blocks
    fences = [-float("inf")] + fences + [float("inf")]

    result = []
    for i in range(len(fences) - 1):
        lo, hi = fences[i], fences[i + 1]

        # Emit the full-width block at this fence (if any, skip sentinel)
        if i > 0:
            result.append(full_width_blocks[i - 1])

        # Emit left-column blocks in this band, then right-column blocks
        for b in left_blocks:
            if lo <= b[1] < hi:
                result.append(b)
        for b in right_blocks:
            if lo <= b[1] < hi:
                result.append(b)

    return result


def _truncate_text(text: str, max_length: int, total_pages: int = 0) -> tuple[str, str]:
    """Truncate text at max_length, breaking at page boundaries.

    Returns (truncated_text, pages_note).
    """
    if len(text) <= max_length:
        return text, "all"

    markers = [
        (m.start(), int(m.group(1))) for m in re.finditer(r"--- PAGE (\d+) ---", text)
    ]
    if not markers:
        return text[:max_length], f"partial (truncated at {max_length} chars)"

    last_complete_page = 0
    cut_pos = 0
    for i, (pos, page_num) in enumerate(markers):
        if pos >= max_length:
            break
        next_marker_pos = markers[i + 1][0] if i + 1 < len(markers) else len(text)
        if next_marker_pos <= max_length:
            last_complete_page = page_num
            cut_pos = next_marker_pos
        else:
            cut_pos = pos
            break

    if last_complete_page == 0:
        return text[:max_length], f"partial (truncated at {max_length} chars)"

    pages_note = (
        f"1-{last_complete_page} of {total_pages}"
        if total_pages
        else f"1-{last_complete_page}"
    )
    return text[:cut_pos].rstrip(), pages_note


def is_text_pdf(text: str) -> bool:
    """Check if extracted text indicates a text-based PDF (not scanned/image)."""
    clean = text.replace("--- PAGE ", "").strip()
    clean = re.sub(r"\d+ ---", "", clean).strip()
    return len(clean) >= 100


@dataclass
class ExtractionQuality:
    """Quality assessment of extracted text."""

    score: float
    is_usable: bool
    warnings: list[str]


def validate_extraction(text: str) -> ExtractionQuality:
    """Check if extracted text is good enough for chunking and embedding."""
    warnings = []
    clean = text.replace("--- PAGE ", "").strip()
    clean = re.sub(r"\d+ ---", "", clean).strip()

    if len(clean) < 100:
        return ExtractionQuality(
            0.0, False, ["Extracted text is too short (<100 chars)"]
        )

    # Check alphabetic ratio (should be >60% for readable text)
    alpha_chars = sum(1 for c in clean if c.isalpha() or c.isspace())
    alpha_ratio = alpha_chars / len(clean) if clean else 0
    if alpha_ratio < 0.5:
        warnings.append(
            f"Low alphabetic ratio ({alpha_ratio:.0%}) — may be garbled or symbol-heavy"
        )

    # Check average line length (interleaved columns produce very short lines)
    lines = [ln for ln in clean.split("\n") if ln.strip()]
    if lines:
        avg_line_len = sum(len(ln) for ln in lines) / len(lines)
        if avg_line_len < 30:
            warnings.append(
                f"Short average line length ({avg_line_len:.0f} chars) — possible column interleaving"
            )

    # Check for excessive repetition (broken extraction loops)
    words = clean.lower().split()
    if len(words) > 50:
        unique_ratio = len(set(words)) / len(words)
        if unique_ratio < 0.2:
            warnings.append(
                f"High word repetition (unique ratio {unique_ratio:.0%}) — possible extraction artifact"
            )

    # Compute score
    score = 1.0
    if warnings:
        score -= 0.2 * len(warnings)
    if alpha_ratio < 0.6:
        score -= 0.3
    score = max(0.0, min(1.0, score))

    return ExtractionQuality(
        score=score,
        is_usable=score >= 0.4,
        warnings=warnings,
    )
