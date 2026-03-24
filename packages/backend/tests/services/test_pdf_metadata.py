"""Tests for PDF metadata service."""
import pytest


class TestExtractPageCount:
    """Tests for extract_page_count function."""

    def test_extract_page_count_valid_pdf(self) -> None:
        """Test extracting page count from valid PDF."""
        from app.services.pdf_metadata import extract_page_count

        # Minimal 2-page PDF
        two_page_pdf = b"""%PDF-1.4
1 0 obj
<<
/Type /Catalog
/Pages 2 0 R
>>
endobj
2 0 obj
<<
/Type /Pages
/Kids [3 0 R 4 0 R]
/Count 2
>>
endobj
3 0 obj
<<
/Type /Page
/Parent 2 0 R
/MediaBox [0 0 612 792]
>>
endobj
4 0 obj
<<
/Type /Page
/Parent 2 0 R
/MediaBox [0 0 612 792]
>>
endobj
xref
0 5
0000000000 65535 f
0000000009 00000 n
0000000058 00000 n
0000000125 00000 n
0000000196 00000 n
trailer
<<
/Size 5
/Root 1 0 R
>>
startxref
267
%%EOF
"""

        result = extract_page_count(two_page_pdf)

        assert result == 2

    def test_extract_page_count_invalid_pdf_returns_none(self) -> None:
        """Test extracting page count from invalid PDF returns None."""
        from app.services.pdf_metadata import extract_page_count

        invalid_pdf = b"This is not a PDF"

        result = extract_page_count(invalid_pdf)

        assert result is None

    def test_extract_page_count_single_page(self) -> None:
        """Test extracting page count from single-page PDF."""
        from app.services.pdf_metadata import extract_page_count

        single_page_pdf = b"""%PDF-1.4
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
0000000125 00000 n
trailer
<<
/Size 4
/Root 1 0 R
>>
startxref
196
%%EOF
"""

        result = extract_page_count(single_page_pdf)

        assert result == 1


class TestGetPdfFileSize:
    """Tests for get_pdf_file_size function."""

    def test_get_pdf_file_size(self) -> None:
        """Test getting PDF file size."""
        from app.services.pdf_metadata import get_pdf_file_size

        pdf_bytes = b"%PDF-1.4\n%%EOF"

        result = get_pdf_file_size(pdf_bytes)

        # %PDF-1.4 (8) + \n (1) + %%EOF (5) = 14 bytes
        assert result == 14

    def test_get_pdf_file_size_large_file(self) -> None:
        """Test getting file size of larger PDF."""
        from app.services.pdf_metadata import get_pdf_file_size

        large_pdf = b"%PDF-1.4\n" + b"x" * 10000 + b"\n%%EOF"

        result = get_pdf_file_size(large_pdf)

        assert result > 10000
