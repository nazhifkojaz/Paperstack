"""Minimal OpenAlex client for the related-work recommender (C2).

One serialized request at a time (module semaphore) with a polite-pool
``mailto`` param, so we never trip OpenAlex rate limits. Reference lists
are fetched once per paper and cached on ``PdfSummary`` by the caller.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.openalex.org"
_SEMAPHORE = asyncio.Semaphore(1)


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


async def fetch_work_by_doi(doi: str) -> OpenAlexWork | None:
    """Resolve a DOI to an OpenAlex work. Returns None on 404 (not indexed)."""
    params = {"mailto": settings.OPENALEX_MAILTO}
    async with _SEMAPHORE:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(f"{_BASE_URL}/works/doi:{doi}", params=params)
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return _parse_work(resp.json())


async def fetch_works_batch(openalex_ids: list[str]) -> list[OpenAlexWork]:
    """Resolve up to 50 OpenAlex ids to display metadata in one request."""
    if not openalex_ids:
        return []
    ids = "|".join(openalex_ids[:50])
    params = {
        "mailto": settings.OPENALEX_MAILTO,
        "filter": f"ids.openalex:{ids}",
        "per-page": 50,
        # referenced_works excluded: batch results are for display only.
        "select": "id,display_name,authorships,publication_year,doi",
    }
    async with _SEMAPHORE:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(f"{_BASE_URL}/works", params=params)
    resp.raise_for_status()
    return [_parse_work(w) for w in resp.json().get("results", [])]
