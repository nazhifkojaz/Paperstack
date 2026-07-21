"""Minimal OpenAlex client for the related-work recommender (C2).

Requests are serialized and include the polite-pool ``mailto`` parameter to
reduce rate-limit pressure. Reference lists are batch-fetched and cached on
``PdfSummary`` by the caller.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

import httpx

from app.core.config import settings

_BASE_URL = "https://api.openalex.org"
_SEMAPHORE = asyncio.Semaphore(1)
_MAX_BATCH_SIZE = 50


@dataclass
class OpenAlexWork:
    openalex_id: str  # short form, e.g. "W2741809807"
    title: str | None = None
    authors: list[str] = field(default_factory=list)  # display names, first 5
    year: int | None = None
    doi: str | None = None  # bare DOI, e.g. "10.1234/abc" (strip URL prefix)
    referenced_works: list[str] = field(default_factory=list)  # short ids


def _short_id(url_or_id: str) -> str:
    """'https://openalex.org/W123' -> 'W123' (already-short ids pass through)."""
    return url_or_id.rsplit("/", 1)[-1]


def normalize_doi(doi: str) -> str:
    """Return a lowercase bare DOI suitable for OpenAlex filters/cache keys."""
    normalized = doi.strip()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if normalized.lower().startswith(prefix):
            normalized = normalized[len(prefix) :]
            break
    return normalized.lower()


def _parse_work(data: dict) -> OpenAlexWork:
    doi = data.get("doi")
    if doi and doi.startswith("https://doi.org/"):
        doi = doi[len("https://doi.org/") :]
    return OpenAlexWork(
        openalex_id=_short_id(data["id"]),
        title=data.get("display_name"),
        authors=[
            a["author"]["display_name"]
            for a in (data.get("authorships") or [])[:5]
            if a.get("author", {}).get("display_name")
        ],
        year=data.get("publication_year"),
        doi=doi,
        referenced_works=[_short_id(w) for w in data.get("referenced_works") or []],
    )


async def fetch_works_by_dois(dois: list[str]) -> dict[str, OpenAlexWork]:
    """Resolve up to 50 DOIs in one request, keyed by normalized bare DOI."""
    normalized_dois: list[str] = []
    for doi in dois:
        normalized = normalize_doi(doi)
        if normalized and normalized not in normalized_dois:
            normalized_dois.append(normalized)
        if len(normalized_dois) == _MAX_BATCH_SIZE:
            break
    if not normalized_dois:
        return {}

    params = {
        "mailto": settings.OPENALEX_MAILTO,
        "filter": f"doi:{'|'.join(normalized_dois)}",
        "per-page": _MAX_BATCH_SIZE,
        "select": "id,display_name,authorships,publication_year,doi,referenced_works",
    }
    async with _SEMAPHORE:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(f"{_BASE_URL}/works", params=params)
    resp.raise_for_status()

    works = [_parse_work(work) for work in resp.json().get("results", [])]
    return {normalize_doi(work.doi): work for work in works if work.doi}


async def fetch_works_batch(openalex_ids: list[str]) -> list[OpenAlexWork]:
    """Resolve up to 50 OpenAlex ids to display metadata in one request."""
    if not openalex_ids:
        return []
    ids = "|".join(openalex_ids[:_MAX_BATCH_SIZE])
    params = {
        "mailto": settings.OPENALEX_MAILTO,
        "filter": f"ids.openalex:{ids}",
        "per-page": _MAX_BATCH_SIZE,
        # referenced_works excluded: batch results are for display only.
        "select": "id,display_name,authorships,publication_year,doi",
    }
    async with _SEMAPHORE:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(f"{_BASE_URL}/works", params=params)
    resp.raise_for_status()
    return [_parse_work(w) for w in resp.json().get("results", [])]
