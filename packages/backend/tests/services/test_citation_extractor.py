"""Tests for citation extractor service."""
import pytest


class TestExtractPdfMetadata:
    """Tests for extract_pdf_metadata function."""

    def test_extract_metadata_from_pdf(self) -> None:
        """Test extracting metadata from PDF with metadata."""
        from app.services.citation_extractor import extract_pdf_metadata

        # Create a valid minimal PDF with metadata in the document info section
        pdf_with_metadata = b"""%PDF-1.4
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
/Info <<
/Title (Test Paper Title)
/Author (John Doe)
/DOI (10.1234/test.doi)
>>
>>
startxref
200
%%EOF
"""

        result = extract_pdf_metadata(pdf_with_metadata)

        assert result["title"] == "Test Paper Title"
        assert result["authors"] == "John Doe"
        assert result["doi"] == "10.1234/test.doi"

    def test_extract_metadata_from_pdf_without_metadata(self) -> None:
        """Test extracting metadata from PDF without metadata."""
        from app.services.citation_extractor import extract_pdf_metadata

        pdf_without_metadata = b"""%PDF-1.4
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

        result = extract_pdf_metadata(pdf_without_metadata)

        assert result["title"] is None
        assert result["authors"] is None
        assert result["doi"] is None


class TestExtractDoiFromText:
    """Tests for extract_doi_from_text function."""

    def test_extract_doi_from_text(self) -> None:
        """Test extracting DOI from PDF text."""
        from app.services.citation_extractor import extract_doi_from_text

        # PDF with proper font resources and content stream
        pdf_with_doi = b"""%PDF-1.4
1 0 obj
<<
/Type /Font
/Subtype /Type1
/BaseFont /Helvetica
>>
endobj
2 0 obj
<<
/Type /Catalog
/Pages 3 0 R
>>
endobj
3 0 obj
<<
/Type /Pages
/Kids [4 0 R]
/Count 1
>>
endobj
4 0 obj
<<
/Type /Page
/Parent 3 0 R
/MediaBox [0 0 612 792]
/Contents 5 0 R
/Resources <<
/Font <<
/F1 1 0 R
>>
>>
>>
endobj
5 0 obj
<<
/Length 44
>>
stream
BT
/F1 12 Tf
100 700 Td
(DOI: 10.1234/test.doi.5678) Tj
ET
endstream
endobj
xref
0 6
0000000000 65535 f
0000000009 00000 n
0000000086 00000 n
0000000177 00000 n
0000000268 00000 n
0000000451 00000 n
trailer
<<
/Size 6
/Root 2 0 R
>>
startxref
550
%%EOF
"""

        result = extract_doi_from_text(pdf_with_doi)

        assert result == "10.1234/test.doi.5678"

    def test_extract_doi_not_found_returns_none(self) -> None:
        """Test that PDF without DOI returns None."""
        from app.services.citation_extractor import extract_doi_from_text

        pdf_without_doi = b"""%PDF-1.4
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

        result = extract_doi_from_text(pdf_without_doi)

        assert result is None


class TestLookupDoiCrossref:
    """Tests for lookup_doi_crossref function."""

    @pytest.mark.asyncio
    async def test_lookup_doi_success(self, mock_crossref_api) -> None:
        """Test successful DOI lookup."""
        from app.services.citation_extractor import lookup_doi_crossref

        result = await lookup_doi_crossref("10.1234/test.doi.12345")

        assert "bibtex" in result
        assert result["doi"] == "10.1234/test.doi.12345"
        assert result["source"] == "crossref"
        assert result["title"] == "Test Paper Title"
        assert result["authors"] == "John Doe, Jane Smith"
        assert result["year"] == 2024
        assert result["isbn"] is None

    @pytest.mark.asyncio
    async def test_lookup_doi_handles_errors(self, mock_crossref_api) -> None:
        """Test that lookup returns data with proper mock."""
        from app.services.citation_extractor import lookup_doi_crossref

        # With proper mocking, should return structured data
        result = await lookup_doi_crossref("10.1234/test.doi.12345")

        assert "bibtex" in result
        assert result["doi"] == "10.1234/test.doi.12345"
        assert result["source"] == "crossref"

    @pytest.mark.asyncio
    async def test_lookup_doi_invalid_format(self):
        """Test invalid DOI format raises ValueError."""
        from app.services.citation_extractor import lookup_doi_crossref

        with pytest.raises(ValueError, match="Invalid DOI format"):
            await lookup_doi_crossref("not-a-doi")

    @pytest.mark.asyncio
    async def test_lookup_doi_not_found_raises(self, mock_crossref_api_not_found):
        """Test DOI not found raises HTTPStatusError."""
        from app.services.citation_extractor import lookup_doi_crossref
        from httpx import HTTPStatusError

        with pytest.raises(HTTPStatusError) as exc_info:
            await lookup_doi_crossref("10.9999/nonexistent")

        assert exc_info.value.response.status_code == 404


class TestAutoExtractCitation:
    """Tests for auto_extract_citation function."""

    @pytest.mark.asyncio
    async def test_auto_extract_with_doi_hint(self, mock_crossref_api) -> None:
        """Test auto-extract with DOI hint."""
        from app.services.citation_extractor import auto_extract_citation

        # Use a minimal valid PDF
        pdf_bytes = b"""%PDF-1.4
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

        result = await auto_extract_citation(
            pdf_bytes=pdf_bytes,
            doi_hint="10.1234/test.doi.12345"
        )

        assert result["doi"] == "10.1234/test.doi.12345"
        assert result["source"] == "crossref"
        assert "bibtex" in result

    @pytest.mark.asyncio
    async def test_auto_extract_fallback_to_metadata(self) -> None:
        """Test auto-extract falls back to embedded metadata."""
        from app.services.citation_extractor import auto_extract_citation

        pdf_with_metadata = b"""%PDF-1.4
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
/Info <<
/Title (Fallback Title)
/Author (Fallback Author)
>>
>>
startxref
200
%%EOF
"""

        result = await auto_extract_citation(pdf_bytes=pdf_with_metadata)

        assert result["doi"] is None
        assert result["title"] == "Fallback Title"
        assert result["authors"] == "Fallback Author"
        assert result["source"] == "auto"


class TestBibtexHelpers:
    """Tests for BibTeX generation helper functions."""

    def test_generate_minimal_bibtex(self) -> None:
        """Test minimal BibTeX generation from DOI."""
        from app.services.citation_extractor import _generate_minimal_bibtex

        result = _generate_minimal_bibtex("10.1234/test.doi")

        assert "@misc{" in result
        assert "10.1234/test.doi" in result

    def test_generate_minimal_bibtex_from_meta(self) -> None:
        """Test minimal BibTeX generation from metadata."""
        from app.services.citation_extractor import _generate_minimal_bibtex_from_meta

        result = _generate_minimal_bibtex_from_meta("Test Title", "Doe, John")

        assert "@article{" in result
        assert "Test Title" in result
        assert "Doe, John" in result


class TestIsbnValidation:
    """Tests for ISBN validation helper function."""

    def test_validate_isbn10_valid(self):
        """Test valid ISBN-10 passes validation."""
        from app.services.citation_extractor import validate_isbn
        result = validate_isbn("0262033844")
        assert result == "0262033844"

    def test_validate_isbn10_with_x_check_digit(self):
        """Test valid ISBN-10 with X check digit passes validation."""
        from app.services.citation_extractor import validate_isbn
        result = validate_isbn("080442957X")
        assert result == "080442957X"

    def test_validate_isbn10_with_x_and_hyphens(self):
        """Test ISBN-10 with X check digit and hyphens is handled correctly."""
        from app.services.citation_extractor import validate_isbn
        result = validate_isbn("0-8044-2957-X")
        assert result == "080442957X"

    def test_validate_isbn10_with_lowercase_x(self):
        """Test ISBN-10 with lowercase x check digit is converted to uppercase."""
        from app.services.citation_extractor import validate_isbn
        result = validate_isbn("080442957x")
        assert result == "080442957X"

    def test_validate_isbn10_with_hyphens(self):
        """Test ISBN-10 with hyphens is stripped and validated."""
        from app.services.citation_extractor import validate_isbn
        result = validate_isbn("0-262-03384-4")
        assert result == "0262033844"

    def test_validate_isbn13_valid(self):
        """Test valid ISBN-13 passes validation."""
        from app.services.citation_extractor import validate_isbn
        result = validate_isbn("9780262033848")
        assert result == "9780262033848"

    def test_validate_isbn13_with_hyphens(self):
        """Test ISBN-13 with hyphens is stripped and validated."""
        from app.services.citation_extractor import validate_isbn
        result = validate_isbn("978-0-262-03384-8")
        assert result == "9780262033848"

    def test_validate_isbn10_invalid_checksum(self):
        """Test ISBN-10 with invalid checksum raises ValueError."""
        from app.services.citation_extractor import validate_isbn
        with pytest.raises(ValueError, match="Invalid ISBN checksum"):
            validate_isbn("0262033845")

    def test_validate_isbn13_invalid_checksum(self):
        """Test ISBN-13 with invalid checksum raises ValueError."""
        from app.services.citation_extractor import validate_isbn
        with pytest.raises(ValueError, match="Invalid ISBN checksum"):
            validate_isbn("9780262033849")

    def test_validate_isbn_invalid_format(self):
        """Test invalid ISBN format raises ValueError."""
        from app.services.citation_extractor import validate_isbn
        with pytest.raises(ValueError, match="Invalid ISBN format"):
            validate_isbn("not-an-isbn")

    def test_validate_isbn_empty_string(self):
        """Test empty string raises ValueError."""
        from app.services.citation_extractor import validate_isbn
        with pytest.raises(ValueError, match="Invalid ISBN format"):
            validate_isbn("")


class TestLookupIsbnOpenlibrary:
    """Tests for lookup_isbn_openlibrary function."""

    @pytest.mark.asyncio
    async def test_lookup_isbn_success(self, mock_openlibrary_api):
        """Test successful ISBN lookup."""
        from app.services.citation_extractor import lookup_isbn_openlibrary

        result = await lookup_isbn_openlibrary("0262033844")

        assert result["isbn"] == "0262033844"
        assert result["doi"] is None
        assert result["title"] == "Introduction to Algorithms"
        assert result["authors"] == "Thomas H. Cormen"
        assert result["year"] == 2009
        assert result["source"] == "openlibrary"
        assert "@book{" in result["bibtex"]

    @pytest.mark.asyncio
    async def test_lookup_isbn_not_found(self, mock_openlibrary_api_not_found):
        """Test ISBN not found raises CitationNotFoundError."""
        from app.services.citation_extractor import lookup_isbn_openlibrary, CitationNotFoundError

        with pytest.raises(CitationNotFoundError) as exc_info:
            await lookup_isbn_openlibrary("9999999999")

        # The error should mention "not found"
        assert "not found" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_lookup_isbn_invalid_format(self):
        """Test invalid ISBN format raises ValueError."""
        from app.services.citation_extractor import lookup_isbn_openlibrary

        with pytest.raises(ValueError, match="Invalid ISBN"):
            await lookup_isbn_openlibrary("not-an-isbn")
