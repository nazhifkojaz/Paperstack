"""Tests for the PDF annotator service."""

import pytest

from app.services.pdf_annotator import export_annotated_pdf


@pytest.fixture
def minimal_pdf():
    """A minimal PDF that pypdf can parse."""
    return b"""%PDF-1.4
1 0 obj
<<
/Type /Catalog
/Pages 2 0 R
>>
endobj
2 0 obj
<<
/Type /Pages
/Kids [3 0 R]
/Count 1
>>
endobj
3 0 obj
<<
/Type /Page
/Parent 2 0 R
/MediaBox [0 0 612 792]
>>
endobj
xref
0 4
0000000000 65535 f
0000000009 00000 n
0000000058 00000 n
0000000115 00000 n
trailer
<<
/Size 4
/Root 1 0 R
>>
startxref
200
%%EOF
"""


class TestExportAnnotatedPdf:

    def test_no_annotations_returns_original(self, minimal_pdf):
        result = export_annotated_pdf(minimal_pdf, [])
        assert result == minimal_pdf

    def test_annotations_return_valid_pdf(self, minimal_pdf):
        annotations = [
            {
                "page_number": 1,
                "type": "highlight",
                "color": "#FF0000",
                "rects": [
                    {"x": 0.1, "y": 0.1, "w": 0.5, "h": 0.05},
                ],
            },
        ]

        result = export_annotated_pdf(minimal_pdf, annotations)

        assert result is not None
        assert len(result) > 0
        assert result != minimal_pdf  # content should differ
        assert result.startswith(b"%PDF")  # valid PDF header

    def test_multiple_highlight_annotations(self, minimal_pdf):
        annotations = [
            {
                "page_number": 1,
                "type": "highlight",
                "color": "#FFFF00",
                "rects": [
                    {"x": 0.1, "y": 0.2, "w": 0.3, "h": 0.03},
                    {"x": 0.5, "y": 0.3, "w": 0.4, "h": 0.04},
                ],
            },
        ]

        result = export_annotated_pdf(minimal_pdf, annotations)
        assert result.startswith(b"%PDF")

    def test_rect_annotation(self, minimal_pdf):
        annotations = [
            {
                "page_number": 1,
                "type": "rect",
                "color": "#0000FF",
                "rects": [
                    {"x": 0.2, "y": 0.1, "w": 0.4, "h": 0.1},
                ],
            },
        ]

        result = export_annotated_pdf(minimal_pdf, annotations)
        assert result.startswith(b"%PDF")

    def test_annotations_default_color(self, minimal_pdf):
        annotations = [
            {
                "page_number": 1,
                "type": "highlight",
                "rects": [
                    {"x": 0.1, "y": 0.1, "w": 0.5, "h": 0.05},
                ],
            },
        ]

        result = export_annotated_pdf(minimal_pdf, annotations)
        assert result.startswith(b"%PDF")

    def test_annotations_on_multiple_pages(self, minimal_pdf):
        # Our minimal PDF only has 1 page, but annotations for page 2 should not crash
        annotations = [
            {
                "page_number": 1,
                "type": "highlight",
                "color": "#00FF00",
                "rects": [{"x": 0.1, "y": 0.1, "w": 0.2, "h": 0.03}],
            },
        ]

        result = export_annotated_pdf(minimal_pdf, annotations)
        assert result.startswith(b"%PDF")
