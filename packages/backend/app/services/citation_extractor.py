"""
Citation extraction service.

Pipeline:
1. extract_pdf_metadata() — read pypdf info dict / XMP for title, author, DOI etc.
2. extract_doi_from_text() — regex scan first 3 pages for a DOI pattern
3. lookup_doi_crossref() — fetch BibTeX + CSL-JSON from CrossRef via DOI
4. auto_extract_citation() — orchestrate the full pipeline and return a dict
"""
import logging
import re
from io import BytesIO
from typing import Optional

import httpx
from pypdf import PdfReader

logger = logging.getLogger(__name__)


# Exceptions

class CitationNotFoundError(Exception):
    """Raised when a citation (DOI/ISBN) is not found in external services."""
    pass


# Helpers

DOI_REGEX = re.compile(
    r"\b(10\.\d{4,9}/[-._;()/:A-Z0-9]+)\b",
    re.IGNORECASE,
)


def validate_doi(doi: str) -> str:
    """Validate DOI format.

    A valid DOI starts with 10. followed by 4-9 digits, then /, then any characters.
    See: https://www.doi.org/doi_handbook/2_Numbering.html#2.2

    Args:
        doi: DOI string

    Returns:
        The DOI string if valid

    Raises:
        ValueError: If DOI format is invalid
    """
    if not doi:
        raise ValueError("DOI cannot be empty")

    # Basic DOI format validation: 10.{4,9}/...
    doi_pattern = re.compile(r"^10\.\d{4,9}/[-._;()/:A-Z0-9]+$", re.IGNORECASE)
    if not doi_pattern.match(doi):
        raise ValueError(f"Invalid DOI format: {doi}")

    return doi


def validate_isbn(isbn: str) -> str:
    """Validate ISBN-10 or ISBN-13 format and checksum.

    Args:
        isbn: ISBN string, hyphens are allowed and will be stripped

    Returns:
        Cleaned ISBN string without hyphens

    Raises:
        ValueError: If ISBN format is invalid or checksum fails
    """
    # Strip hyphens and spaces, and convert x to X for consistency
    clean = isbn.replace("-", "").replace(" ", "").upper()

    # Check if it's valid format (digits only, or digits + X at end for ISBN-10)
    # X is only valid as check digit in ISBN-10 (position 10)
    if not clean.replace("X", "").isdigit() or clean.count("X") > 1 or (clean.endswith("X") and len(clean) != 10):
        raise ValueError(f"Invalid ISBN format: {isbn}")

    # ISBN-10: 10 digits
    if len(clean) == 10:
        # Checksum: sum(digit * (10 - position)) mod 11 == 0
        # Check digit 'X' represents 10
        total = 0
        for i, char in enumerate(clean):
            if char == "X":
                digit = 10
            else:
                digit = int(char)
            total += digit * (10 - i)

        if total % 11 != 0:
            raise ValueError(f"Invalid ISBN checksum: {isbn}")
        return clean

    # ISBN-13: 13 digits
    if len(clean) == 13:
        # Checksum: sum(digit * (1 if position is odd else 3)) mod 10 == 0
        total = 0
        for i, char in enumerate(clean):
            digit = int(char)
            # Positions are 1-indexed for checksum calculation
            weight = 1 if (i + 1) % 2 == 1 else 3
            total += digit * weight

        if total % 10 != 0:
            raise ValueError(f"Invalid ISBN checksum: {isbn}")
        return clean

    raise ValueError(f"Invalid ISBN length: {isbn} (must be 10 or 13 digits)")


def extract_pdf_metadata(pdf_bytes: bytes) -> dict:
    """Read embedded metadata from a PDF using pypdf."""
    reader = PdfReader(BytesIO(pdf_bytes))
    meta = reader.metadata or {}

    def clean(value):
        return str(value).strip() if value else None

    title = clean(meta.get("/Title"))
    author = clean(meta.get("/Author"))
    doi = clean(meta.get("/DOI"))  # some producers embed DOI in XMP

    # Extract year from /Date, /Created, or /CreationDate
    year = None
    for key in ("/Date", "/Created", "/CreationDate"):
        raw = clean(meta.get(key))
        if raw:
            year_match = re.search(r"\b(19|20)\d{2}\b", raw)
            if year_match:
                year = int(year_match.group(0))
                break

    return {"title": title, "authors": author, "doi": doi, "year": year}


def extract_doi_from_text(pdf_bytes: bytes, max_pages: int = 3) -> Optional[str]:
    """Scan the first `max_pages` of the PDF text for a DOI pattern."""
    reader = PdfReader(BytesIO(pdf_bytes))
    for i, page in enumerate(reader.pages):
        if i >= max_pages:
            break
        text = page.extract_text() or ""
        match = DOI_REGEX.search(text)
        if match:
            return match.group(1)
    return None


async def lookup_doi_crossref(doi: str) -> dict:
    """
    Fetch metadata from CrossRef using content negotiation.

    Args:
        doi: DOI string to lookup

    Returns:
        dict with keys: doi, title, authors, year, bibtex, csl_json, source
        (isbn is always None for DOI lookups)

    Raises:
        ValueError: Invalid DOI format
        httpx.HTTPStatusError: DOI not found or API error
    """
    # Validate DOI format first
    validated_doi = validate_doi(doi)

    headers_bibtex = {"Accept": "application/x-bibtex"}
    headers_json = {"Accept": "application/vnd.citationstyles.csl+json"}
    url = f"https://doi.org/{validated_doi}"

    async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
        # Fetch BibTeX
        bibtex_resp = await client.get(url, headers=headers_bibtex)
        bibtex_resp.raise_for_status()
        bibtex = bibtex_resp.text

        # Fetch CSL-JSON
        json_resp = await client.get(url, headers=headers_json)
        json_resp.raise_for_status()
        csl_json = json_resp.json()

        title = csl_json.get("title")
        if isinstance(title, list):
            title = title[0] if title else None

        author_list = csl_json.get("author", [])
        authors = ", ".join(
            f"{a.get('given', '')} {a.get('family', '')}".strip()
            for a in author_list
        ) or None

        issued = csl_json.get("issued", {})
        date_parts = issued.get("date-parts", [[]])
        year = date_parts[0][0] if date_parts and date_parts[0] else None

    return {
        "doi": validated_doi,
        "isbn": None,
        "title": title,
        "authors": authors,
        "year": year,
        "bibtex": bibtex,
        "csl_json": csl_json,
        "source": "crossref",
    }


async def lookup_isbn_openlibrary(isbn: str) -> dict:
    """
    Fetch metadata from Open Library API by ISBN.

    Args:
        isbn: ISBN-10 or ISBN-13 string

    Returns:
        dict with keys: isbn, title, authors, year, bibtex, csl_json, source
        (doi is always None for ISBN lookups)

    Raises:
        ValueError: Invalid ISBN format
        CitationNotFoundError: ISBN not found in Open Library
        httpx.HTTPStatusError: API error (non-404 HTTP status)
    """
    # Validate ISBN first
    validated_isbn = validate_isbn(isbn)

    url = f"https://openlibrary.org/api/books?bibkeys=ISBN:{validated_isbn}&format=json&jscmd=data"

    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.get(url)
        response.raise_for_status()

        data = response.json()

        # Check if ISBN was found (empty dict = not found)
        key = f"ISBN:{validated_isbn}"
        if key not in data or not data[key]:
            raise CitationNotFoundError(f"ISBN not found: {validated_isbn}")

        book_data = data[key]

        # Extract fields
        title = book_data.get("title")
        authors_list = book_data.get("authors", [])
        authors = ", ".join(a.get("name", "") for a in authors_list) if authors_list else None

        # Parse year from publish_date
        year = None
        publish_date = book_data.get("publish_date", "")
        if publish_date:
            # Extract first 4-digit year (re module already imported at file top)
            year_match = re.search(r"\b(19|20)\d{2}\b", str(publish_date))
            if year_match:
                year = int(year_match.group(0))

        # Generate BibTeX as @book entry
        first_author_last = authors_list[0].get("name", "").split()[-1] if authors_list else "unknown"
        citation_key_base = re.sub(r"[^a-zA-Z0-9]", "", first_author_last)
        citation_key = f"{citation_key_base}{year}" if year else citation_key_base
        bibtex = f"@book{{{citation_key},\n"
        if title:
            bibtex += f"  title = {{{title}}},\n"
        if authors:
            bibtex += f"  author = {{{authors}}},\n"
        if year:
            bibtex += f"  year = {{{year}}},\n"
        publisher = book_data.get("publishers", [{}])[0].get("name") if book_data.get("publishers") else None
        if publisher:
            bibtex += f"  publisher = {{{publisher}}},\n"
        bibtex += f"  isbn = {{{validated_isbn}}},\n"
        bibtex += "}"

        # Build CSL-JSON like structure
        csl_json = {
            "type": "book",
            "title": title,
            "author": [{"name": a.get("name")} for a in authors_list] if authors_list else [],
            "issued": {"date-parts": [[year]]} if year else None,
            "publisher": publisher,
            "ISBN": validated_isbn,
        }

        return {
            "doi": None,
            "isbn": validated_isbn,
            "title": title,
            "authors": authors,
            "year": year,
            "bibtex": bibtex,
            "csl_json": csl_json,
            "source": "openlibrary",
        }


async def search_semantic_scholar(title: str, authors: Optional[str] = None) -> Optional[dict]:
    """
    Search Semantic Scholar for a paper by title.
    Returns a dict with doi, title, authors, year if a match is found, else None.
    Uses the /match endpoint which returns a single best result.
    """
    url = "https://api.semanticscholar.org/graph/v1/paper/search/match"
    params = {
        "query": title,
        "fields": "title,authors,year,externalIds",
    }

    def normalize(s: str) -> str:
        return re.sub(r"[^a-z0-9 ]", "", s.lower()).strip()

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(url, params=params)
            if resp.status_code != 200:
                return None
            data = resp.json()

        items = data.get("data", [])
        if not items:
            return None

        paper = items[0]
        paper_title = paper.get("title", "")

        # Verify title similarity
        if normalize(paper_title) != normalize(title):
            return None

        # Verify author overlap if we have local authors
        if authors:
            s2_authors = paper.get("authors", [])
            s2_names = {a.get("name", "").split()[-1].lower() for a in s2_authors if a.get("name")}
            local_names = {name.strip().split()[-1].lower() for name in authors.split(",") if name.strip()}
            if not (s2_names & local_names):
                return None

        ext_ids = paper.get("externalIds") or {}
        doi = ext_ids.get("DOI")
        arxiv_id = ext_ids.get("ArXiv")

        # If no DOI but has ArXiv ID, construct the arXiv DOI
        if not doi and arxiv_id:
            doi = f"10.48550/arXiv.{arxiv_id}"

        s2_authors_str = ", ".join(
            a.get("name", "") for a in paper.get("authors", [])
        ) or None

        return {
            "doi": doi,
            "title": paper_title,
            "authors": s2_authors_str,
            "year": paper.get("year"),
        }
    except httpx.TimeoutException as exc:
        logger.warning("Semantic Scholar timeout for title '%s': %s", title, exc)
        return None
    except httpx.HTTPStatusError as exc:
        logger.debug(
            "Semantic Scholar returned HTTP %s for title '%s'",
            exc.response.status_code,
            title,
        )
        return None
    except (httpx.RequestError, KeyError, ValueError, IndexError) as exc:
        logger.warning(
            "Unexpected error searching Semantic Scholar for title '%s': %s",
            title,
            exc,
        )
        return None


async def auto_extract_citation(pdf_bytes: bytes, doi_hint: Optional[str] = None) -> dict:
    """
    Full pipeline: try to find a DOI, fall back to embedded metadata,
    then look up CrossRef and return a complete citation dict.
    """
    # Embedded metadata (fast, synchronous)
    meta = extract_pdf_metadata(pdf_bytes)

    # Determine DOI — prefer hint, then embedded, then text scan
    doi = doi_hint or meta.get("doi") or extract_doi_from_text(pdf_bytes)

    # Normalize: strip URL prefixes like https://doi.org/
    if doi:
        doi = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", doi)

    if doi:
        try:
            crossref = await lookup_doi_crossref(doi)
            return {
                "doi": doi,
                "title": crossref.get("title") or meta.get("title"),
                "authors": crossref.get("authors") or meta.get("authors"),
                "year": crossref.get("year") or meta.get("year"),
                "bibtex": crossref.get("bibtex") or _generate_minimal_bibtex(doi),
                "csl_json": crossref.get("csl_json"),
                "source": "crossref",
            }
        except ValueError as exc:
            logger.debug("DOI validation failed for DOI '%s': %s", doi, exc)
            # Fall through to next strategy
        except httpx.TimeoutException as exc:
            logger.warning("CrossRef timeout for DOI '%s': %s", doi, exc)
            # Fall through to next strategy
        except httpx.HTTPStatusError as exc:
            logger.debug(
                "CrossRef lookup failed for DOI '%s': HTTP %s",
                doi,
                exc.response.status_code,
            )
            # Fall through to next strategy

    # No DOI — try Semantic Scholar title search
    if meta.get("title"):
        s2_result = await search_semantic_scholar(meta["title"], meta.get("authors"))
        if s2_result:
            s2_doi = s2_result.get("doi")
            # Try CrossRef with the discovered DOI for BibTeX
            if s2_doi:
                try:
                    crossref = await lookup_doi_crossref(s2_doi)
                    return {
                        "doi": s2_doi,
                        "title": crossref.get("title") or s2_result.get("title") or meta.get("title"),
                        "authors": crossref.get("authors") or s2_result.get("authors") or meta.get("authors"),
                        "year": crossref.get("year") or s2_result.get("year") or meta.get("year"),
                        "bibtex": crossref.get("bibtex") or _generate_minimal_bibtex(s2_doi),
                        "csl_json": crossref.get("csl_json"),
                        "source": "semantic_scholar+crossref",
                    }
                except ValueError as exc:
                    logger.debug(
                        "DOI validation failed for S2 DOI '%s': %s",
                        s2_doi,
                        exc,
                    )
                except httpx.TimeoutException as exc:
                    logger.warning("CrossRef timeout for S2 DOI '%s': %s", s2_doi, exc)
                except httpx.HTTPStatusError as exc:
                    logger.debug(
                        "CrossRef lookup failed for S2 DOI '%s': HTTP %s",
                        s2_doi,
                        exc.response.status_code,
                    )
                # CrossRef lookup failed, use S2 data directly

            # Return Semantic Scholar data with generated BibTeX
            s2_title = s2_result.get("title") or meta.get("title") or "Unknown Title"
            s2_authors = s2_result.get("authors") or meta.get("authors") or "Unknown Author"
            s2_year = s2_result.get("year") or meta.get("year")
            return {
                "doi": s2_doi,
                "title": s2_title,
                "authors": s2_authors,
                "year": s2_year,
                "bibtex": _generate_minimal_bibtex_from_meta(s2_title, s2_authors, s2_year),
                "csl_json": None,
                "source": "semantic_scholar",
            }

    # No DOI, no S2 match — build citation from embedded metadata only
    title = meta.get("title") or "Unknown Title"
    authors = meta.get("authors") or "Unknown Author"
    year = meta.get("year")
    bibtex = _generate_minimal_bibtex_from_meta(title, authors, year)
    return {
        "doi": None,
        "title": title,
        "authors": authors,
        "year": year,
        "bibtex": bibtex,
        "csl_json": None,
        "source": "auto",
    }


# BibTeX helpers

def _generate_minimal_bibtex(doi: str) -> str:
    """Fallback BibTeX when CrossRef is unreachable."""
    key = re.sub(r"[^a-zA-Z0-9]", "", doi)[:16]
    return f"@misc{{{key},\n  doi = {{{doi}}},\n}}"


def _generate_minimal_bibtex_from_meta(title: str, authors: str, year: Optional[int] = None) -> str:
    """Construct a skeleton BibTeX entry from embedded PDF metadata."""
    first_author_last = (
        authors.split(",")[0].split()[-1] if authors else "unknown"
    )
    key = re.sub(r"[^a-zA-Z0-9]", "", first_author_last)
    if year:
        key = f"{key}{year}"
    entry = f"@article{{{key},\n"
    entry += f"  title  = {{{title}}},\n"
    entry += f"  author = {{{authors}}},\n"
    if year:
        entry += f"  year   = {{{year}}},\n"
    entry += "}"
    return entry
