"""Tests for the OpenAlex client (C2 related-work recommender)."""

import httpx
import pytest
import respx
from httpx import Response

from app.services.openalex_client import (
    OpenAlexWork,
    _parse_work,
    fetch_work_by_doi,
    fetch_works_batch,
)

_BASE_URL = "https://api.openalex.org"


def _work_payload(
    *,
    openalex_id: str = "https://openalex.org/W2741809807",
    title: str | None = "Attention Is All You Need",
    doi: str | None = "https://doi.org/10.48550/arXiv.1706.03762",
    authorships: list | None = None,
    year: int | None = 2017,
    referenced_works: list | None = None,
) -> dict:
    if authorships is None:
        authorships = [
            {
                "author": {"display_name": "Ashish Vaswani"},
            },
            {
                "author": {"display_name": "Noam Shazeer"},
            },
        ]
    return {
        "id": openalex_id,
        "display_name": title,
        "doi": doi,
        "authorships": authorships,
        "publication_year": year,
        "referenced_works": referenced_works or [],
    }


class TestParseWork:
    def test_strips_openalex_and_doi_prefixes(self):
        w = _parse_work(
            _work_payload(
                referenced_works=[
                    "https://openalex.org/W1",
                    "https://openalex.org/W2",
                ]
            )
        )
        assert w.openalex_id == "W2741809807"
        assert w.doi == "10.48550/arXiv.1706.03762"
        assert w.title == "Attention Is All You Need"
        assert w.year == 2017
        assert w.authors == ["Ashish Vaswani", "Noam Shazeer"]
        assert w.referenced_works == ["W1", "W2"]

    def test_missing_fields_tolerated(self):
        w = _parse_work({"id": "https://openalex.org/W9"})
        assert w.openalex_id == "W9"
        assert w.title is None
        assert w.doi is None
        assert w.authors == []
        assert w.year is None
        assert w.referenced_works == []

    def test_short_ids_pass_through(self):
        w = _parse_work(
            {
                "id": "W123",
                "referenced_works": ["W4", "W5"],
            }
        )
        assert w.openalex_id == "W123"
        assert w.referenced_works == ["W4", "W5"]

    def test_authors_capped_at_five(self):
        authorships = [{"author": {"display_name": f"Author {i}"}} for i in range(7)]
        w = _parse_work(_work_payload(authorships=authorships))
        assert len(w.authors) == 5

    def test_doi_without_prefix_kept_as_is(self):
        w = _parse_work(_work_payload(doi="10.1234/abc"))
        assert w.doi == "10.1234/abc"


@pytest.mark.asyncio
class TestFetchWorkByDoi:
    @respx.mock
    async def test_returns_parsed_work(self):
        respx.get(f"{_BASE_URL}/works/doi:10.48550/arXiv.1706.03762").mock(
            return_value=Response(200, json=_work_payload())
        )
        work = await fetch_work_by_doi("10.48550/arXiv.1706.03762")
        assert isinstance(work, OpenAlexWork)
        assert work.openalex_id == "W2741809807"

    @respx.mock
    async def test_404_returns_none(self):
        respx.get(f"{_BASE_URL}/works/doi:10.9999/nope").mock(
            return_value=Response(404, text="not found")
        )
        assert await fetch_work_by_doi("10.9999/nope") is None

    @respx.mock
    async def test_500_raises(self):
        respx.get(f"{_BASE_URL}/works/doi:10.9999/boom").mock(
            return_value=Response(500, text="server error")
        )
        with pytest.raises(httpx.HTTPStatusError):
            await fetch_work_by_doi("10.9999/boom")


@pytest.mark.asyncio
class TestFetchWorksBatch:
    @respx.mock
    async def test_batch_resolves_ids(self):
        route = respx.get(f"{_BASE_URL}/works").mock(
            return_value=Response(
                200,
                json={
                    "results": [
                        _work_payload(
                            openalex_id="https://openalex.org/W1",
                            title="Paper One",
                        ),
                        _work_payload(
                            openalex_id="https://openalex.org/W2",
                            title="Paper Two",
                        ),
                    ]
                },
            )
        )
        works = await fetch_works_batch(["W1", "W2"])
        assert len(works) == 2
        assert {w.openalex_id for w in works} == {"W1", "W2"}
        assert route.called
        # Filter param carries the pipe-separated ids.
        request_url = str(route.calls.last.request.url)
        assert "ids.openalex" in request_url

    async def test_empty_input_returns_empty_without_call(self):
        # No respx route registered -> would raise if a call were made.
        assert await fetch_works_batch([]) == []
