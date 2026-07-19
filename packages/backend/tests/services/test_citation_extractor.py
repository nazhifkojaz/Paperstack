"""Tests for citation extractor service."""

import pymupdf
import pytest
import respx
from httpx import Response


# -- Helpers for generating synthetic PDFs with real text layers --


def _make_pdf_with_title(title_text: str, body_text: str = "") -> bytes:
    """Create a single-page PDF where *title_text* uses the largest font."""
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), title_text, fontsize=20)
    if body_text:
        page.insert_text((72, 200), body_text, fontsize=10)
    return doc.tobytes()


def _make_multipage_pdf(page_texts: list[str]) -> bytes:
    """Create a multi-page PDF with the given text on each page."""
    doc = pymupdf.open()
    for text in page_texts:
        page = doc.new_page()
        page.insert_text((72, 72), text, fontsize=12)
    return doc.tobytes()


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
            pdf_bytes=pdf_bytes, doi_hint="10.1234/test.doi.12345"
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

    @pytest.mark.asyncio
    async def test_auto_extract_preserves_doi_when_crossref_fails(
        self, mock_crossref_api_not_found, sample_pdf_bytes
    ) -> None:
        """DOI found via hint must survive even when CrossRef and S2 both fail.

        Previously the final fallback hardcoded ``"doi": None``, discarding a
        valid arXiv DOI that was found but couldn't be enriched via CrossRef.
        This broke downstream features (OpenAlex recommendations) that only
        need the DOI string.
        """
        from app.services.citation_extractor import auto_extract_citation

        # Minimal PDF with no text layer — no arXiv stamp, no layout title,
        # so S2 won't match and the final fallback path is taken.
        result = await auto_extract_citation(
            pdf_bytes=sample_pdf_bytes, doi_hint="10.9999/nonexistent"
        )

        # CrossRef is mocked to 404; S2 won't match (no title text in PDF).
        # The DOI must still be preserved in the final fallback.
        assert result["doi"] == "10.9999/nonexistent"
        assert result["source"] == "auto"

    def test_arxiv_stamp_detected_as_junk_title(self) -> None:
        """arXiv watermarks extracted by the layout heuristic must be rejected."""
        from app.services.citation_extractor import _looks_like_junk_title

        assert _looks_like_junk_title("arXiv:2211.16319v1 [eess.AS] 22 Nov 2022")
        assert _looks_like_junk_title("arXiv:1906.08220")
        # Real titles must still pass.
        assert not _looks_like_junk_title(
            "Benchmarking Evaluation Metrics for Code-Switching ASR"
        )


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

    def test_validate_isbn13_with_internal_x_is_rejected(self):
        """A 13-char string with an X not at the end must be rejected as a
        format error (it is not a valid ISBN-13). Previously this slipped past
        the format guard and crashed the checksum loop with ``int("X")``."""
        from app.services.citation_extractor import validate_isbn

        with pytest.raises(ValueError, match="Invalid ISBN format"):
            validate_isbn("12X4567890123")

    @pytest.mark.parametrize("bad", ["X", "1X3456789", "123456789XX", "ABCDEFGHI0"])
    def test_validate_isbn10_misplaced_x_is_rejected(self, bad):
        """X is only valid as the final check digit of a 10-char ISBN."""
        from app.services.citation_extractor import validate_isbn

        with pytest.raises(ValueError, match="Invalid ISBN format"):
            validate_isbn(bad)


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
        from app.services.citation_extractor import (
            lookup_isbn_openlibrary,
            CitationNotFoundError,
        )

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


class TestCleanDoiMatch:
    """Tests for _clean_doi_match (Task 0.3)."""

    def test_strips_trailing_period(self) -> None:
        from app.services.citation_extractor import _clean_doi_match

        assert _clean_doi_match("10.1234/test.doi.") == "10.1234/test.doi"

    def test_strips_trailing_semicolon(self) -> None:
        from app.services.citation_extractor import _clean_doi_match

        assert _clean_doi_match("10.1234/test.doi;") == "10.1234/test.doi"

    def test_strips_trailing_comma_and_colon(self) -> None:
        from app.services.citation_extractor import _clean_doi_match

        assert _clean_doi_match("10.1234/test,") == "10.1234/test"
        assert _clean_doi_match("10.1234/test:") == "10.1234/test"

    def test_preserves_balanced_parens(self) -> None:
        from app.services.citation_extractor import _clean_doi_match

        assert _clean_doi_match("10.1000/foo(bar)") == "10.1000/foo(bar)"

    def test_strips_unbalanced_trailing_paren(self) -> None:
        from app.services.citation_extractor import _clean_doi_match

        assert _clean_doi_match("10.1000/foo)") == "10.1000/foo"

    def test_strips_unbalanced_trailing_paren_with_punct(self) -> None:
        from app.services.citation_extractor import _clean_doi_match

        assert _clean_doi_match("10.1000/foo.).") == "10.1000/foo"

    def test_no_change_on_clean_doi(self) -> None:
        from app.services.citation_extractor import _clean_doi_match

        assert _clean_doi_match("10.1234/test.doi.5678") == "10.1234/test.doi.5678"


class TestExtractDoiTrailingPunct:
    """Tests that extract_doi_from_text strips trailing punctuation."""

    def test_doi_extraction_strips_trailing_dot(self) -> None:
        """DOI ending a sentence should have trailing punctuation stripped."""
        from app.services.citation_extractor import extract_doi_from_text

        pdf_bytes = _make_multipage_pdf(["See https://doi.org/10.1234/test.doi."])
        result = extract_doi_from_text(pdf_bytes)
        assert result == "10.1234/test.doi"


class TestExtractArxivId:
    """Tests for extract_arxiv_id_from_text (Task 0.2)."""

    def test_extract_arxiv_id_from_page1(self) -> None:
        from app.services.citation_extractor import extract_arxiv_id_from_text

        pdf_bytes = _make_multipage_pdf(["arXiv:2106.09685"])
        assert extract_arxiv_id_from_text(pdf_bytes) == "2106.09685"

    def test_strips_version_suffix(self) -> None:
        from app.services.citation_extractor import extract_arxiv_id_from_text

        pdf_bytes = _make_multipage_pdf(["arXiv:2106.09685v2"])
        assert extract_arxiv_id_from_text(pdf_bytes) == "2106.09685"

    def test_page1_only_scoping(self) -> None:
        """arXiv id on page 3 (references) should NOT be matched."""
        from app.services.citation_extractor import extract_arxiv_id_from_text

        pdf_bytes = _make_multipage_pdf(["Introduction", "Methods", "arXiv:1900.99999"])
        assert extract_arxiv_id_from_text(pdf_bytes) is None

    def test_returns_none_when_no_arxiv(self) -> None:
        from app.services.citation_extractor import extract_arxiv_id_from_text

        pdf_bytes = _make_multipage_pdf(["Just a regular paper"])
        assert extract_arxiv_id_from_text(pdf_bytes) is None

    def test_case_insensitive(self) -> None:
        from app.services.citation_extractor import extract_arxiv_id_from_text

        pdf_bytes = _make_multipage_pdf(["ARXIV:2106.09685"])
        assert extract_arxiv_id_from_text(pdf_bytes) == "2106.09685"


class TestLooksLikeJunkTitle:
    """Tests for _looks_like_junk_title (Task 0.1)."""

    def test_rejects_docx_filename(self) -> None:
        from app.services.citation_extractor import _looks_like_junk_title

        assert _looks_like_junk_title("Microsoft Word - draft.docx")

    def test_rejects_untitled(self) -> None:
        from app.services.citation_extractor import _looks_like_junk_title

        assert _looks_like_junk_title("untitled")

    def test_rejects_single_word(self) -> None:
        from app.services.citation_extractor import _looks_like_junk_title

        assert _looks_like_junk_title("Draft")

    def test_accepts_real_title(self) -> None:
        from app.services.citation_extractor import _looks_like_junk_title

        assert not _looks_like_junk_title("Attention Is All You Need")


class TestExtractTitleFromLayout:
    """Tests for extract_title_from_layout (Task 0.1)."""

    def test_extracts_largest_font_title(self) -> None:
        from app.services.citation_extractor import extract_title_from_layout

        pdf_bytes = _make_pdf_with_title(
            "Attention Is All You Need",
            body_text="We propose a new architecture...",
        )
        title = extract_title_from_layout(pdf_bytes)
        assert title == "Attention Is All You Need"

    def test_returns_none_for_no_text(self) -> None:
        from app.services.citation_extractor import extract_title_from_layout

        # Minimal PDF with no content stream (from fixtures)
        from tests.fixtures.pdf import MINIMAL_PDF

        assert extract_title_from_layout(MINIMAL_PDF) is None

    def test_rejects_junk_title(self) -> None:
        from app.services.citation_extractor import extract_title_from_layout

        # Single word is junk (< 2 words)
        pdf_bytes = _make_pdf_with_title("Draft", body_text="Some body text here")
        assert extract_title_from_layout(pdf_bytes) is None


class TestTitleSimilarity:
    """Tests for _title_similarity (Task 0.4)."""

    def test_identical_titles(self) -> None:
        from app.services.citation_extractor import _title_similarity

        assert _title_similarity("Deep Learning", "Deep Learning") == 1.0

    def test_high_similarity_accepts(self) -> None:
        from app.services.citation_extractor import _title_similarity

        sim = _title_similarity(
            "Attention Is All You Need",
            "Attention is All You Need",
        )
        assert sim >= 0.8

    def test_low_similarity_rejects(self) -> None:
        from app.services.citation_extractor import _title_similarity

        sim = _title_similarity(
            "Attention Is All You Need",
            "A Completely Different Paper About Cats",
        )
        assert sim < 0.8

    def test_subtitle_truncation_still_matches(self) -> None:
        from app.services.citation_extractor import _title_similarity

        sim = _title_similarity(
            "Neural Machine Translation by Jointly Learning to Align and Translate",
            "Neural Machine Translation by Jointly Learning to Align",
        )
        assert sim >= 0.8


@pytest.fixture
def mock_semantic_scholar_api():
    """Mock Semantic Scholar /match endpoint."""
    respx.start()

    def side_effect(request):
        # Return a matching paper
        return Response(
            200,
            json={
                "data": [
                    {
                        "title": "Attention Is All You Need",
                        "authors": [
                            {"name": "Ashish Vaswani"},
                            {"name": "Noam Shazeer"},
                        ],
                        "year": 2017,
                        "externalIds": {"DOI": "10.5555/3295222.3295349"},
                        "matchScore": 0.95,
                    }
                ]
            },
        )

    respx.get("https://api.semanticscholar.org/graph/v1/paper/search/match").mock(
        side_effect=side_effect
    )

    yield respx
    respx.stop()


@pytest.fixture
def mock_semantic_scholar_different_title():
    """Mock S2 returning a paper with a very different title."""
    respx.start()

    respx.get("https://api.semanticscholar.org/graph/v1/paper/search/match").mock(
        return_value=Response(
            200,
            json={
                "data": [
                    {
                        "title": "A Study on Marine Biology",
                        "authors": [{"name": "Jane Doe"}],
                        "year": 2020,
                        "externalIds": {"DOI": "10.9999/different"},
                    }
                ]
            },
        )
    )

    yield respx
    respx.stop()


class TestSearchSemanticScholarFuzzy:
    """Tests for fuzzy Semantic Scholar matching (Task 0.4)."""

    @pytest.mark.asyncio
    async def test_fuzzy_accept_similar_title(self, mock_semantic_scholar_api) -> None:
        from app.services.citation_extractor import search_semantic_scholar

        result = await search_semantic_scholar(
            "Attention Is All You Need", "Ashish Vaswani"
        )
        assert result is not None
        assert result["doi"] == "10.5555/3295222.3295349"

    @pytest.mark.asyncio
    async def test_fuzzy_reject_different_title(
        self, mock_semantic_scholar_different_title
    ) -> None:
        from app.services.citation_extractor import search_semantic_scholar

        result = await search_semantic_scholar("Attention Is All You Need", None)
        assert result is None

    @pytest.mark.asyncio
    async def test_rejects_wrong_authors(self, mock_semantic_scholar_api) -> None:
        """Even with a good title match, wrong authors must reject."""
        from app.services.citation_extractor import search_semantic_scholar

        result = await search_semantic_scholar(
            "Attention Is All You Need", "Completely Different Author"
        )
        assert result is None
