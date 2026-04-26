"""Shortlist candidate highlight chunks via vector search."""
from dataclasses import dataclass
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.embedding_service import EmbeddingService
from app.services.vector_search_service import vector_search_service, SearchResult

Tier = Literal["quick", "thorough"]

CATEGORY_QUERIES: dict[str, str] = {
    "findings": "key findings, main results, conclusions, statistical outcomes, novel contribution",
    "methods": "methodology, experimental setup, approach, procedure, techniques, parameters",
    "definitions": "definitions of key terms, formal definitions, terminology introduced",
    "limitations": "limitations, caveats, threats to validity, future work, open problems",
    "background": "background, related work, prior research, motivation, foundational context",
}

_K_PER_CAT = {"quick": 6, "thorough": 15}


@dataclass
class CandidateChunk:
    chunk_id: str
    content: str
    page_number: int
    end_page_number: int | None
    section_title: str | None
    categories: list[str]
    best_score: float


class HighlightShortlistService:
    def __init__(self, embedding_service: EmbeddingService | None = None):
        self._embeddings = embedding_service or EmbeddingService()

    async def shortlist_chunks(
        self,
        pdf_id: str,
        user_id: str,
        categories: list[str],
        pages: list[int],
        tier: Tier,
        db: AsyncSession,
        custom_queries: dict[str, str] | None = None,
    ) -> list[CandidateChunk]:
        k = _K_PER_CAT[tier]
        pages_set = set(pages)
        merged: dict[str, CandidateChunk] = {}

        for cat in categories:
            query = CATEGORY_QUERIES.get(cat)
            if not query:
                continue
            # Augment with paper-specific query if available
            custom = (custom_queries or {}).get(cat)
            if custom:
                query = f"{query} | {custom}"
            vec = await self._embeddings.embed_query(query, db=db)
            results: list[SearchResult] = await vector_search_service.search_pdf(
                query_vector=vec,
                pdf_id=pdf_id,
                user_id=user_id,
                top_k=k,
                db=db,
                query_text=query,
            )
            for r in results:
                chunk_pages = set(range(r.page_number, (r.end_page_number or r.page_number) + 1))
                if pages_set and not chunk_pages & pages_set:
                    continue
                cid = r.chunk_id or ""
                if cid in merged:
                    merged[cid].categories.append(cat)
                    merged[cid].best_score = max(merged[cid].best_score, r.score)
                else:
                    merged[cid] = CandidateChunk(
                        chunk_id=cid,
                        content=r.content,
                        page_number=r.page_number,
                        end_page_number=r.end_page_number,
                        section_title=r.section_title,
                        categories=[cat],
                        best_score=r.score,
                    )

        return sorted(merged.values(), key=lambda c: c.best_score, reverse=True)


highlight_shortlist_service = HighlightShortlistService()
