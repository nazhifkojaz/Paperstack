"""Vector search service for semantic similarity queries across PDFs.

This service encapsulates all PostgreSQL pgvector operations for:
1. Searching within a single PDF
2. Searching across a collection of PDFs
3. Searching across all user's PDFs

Services return structured data, never HTTP responses.
Routes handle error translation and HTTP concerns.
"""

import logging
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import text as sql_text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings


logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    """Result from a vector search query."""

    chunk_id: str | None
    pdf_id: str | None
    pdf_title: str | None
    page_number: int
    content: str
    score: float
    end_page_number: int | None = None
    section_title: str | None = None
    section_level: int | None = None


@dataclass
class _SearchScope:
    """Configuration for a vector search scope."""
    extra_joins: str
    where_extra: str
    select_pdf_cols: str
    coalesce_pdf_cols: str
    hybrid_join_on: str
    scope_params: dict


_HYBRID_SQL = """
    WITH vector_results AS (
        SELECT pc.id{select_pdf_cols}, pc.page_number, pc.end_page_number, pc.content,
               pc.section_title, pc.section_level,
               1 - (pc.embedding <=> CAST(:vec AS halfvec)) AS semantic_score
        FROM pdf_chunks pc
        {extra_joins}
        WHERE pc.user_id = :user_id
          {where_extra}
        ORDER BY pc.embedding <=> CAST(:vec AS halfvec)
        LIMIT :limit2
    ),
    keyword_results AS (
        SELECT pc.id{select_pdf_cols}, pc.page_number, pc.end_page_number, pc.content,
               pc.section_title, pc.section_level,
               ts_rank(pc.search_vector, plainto_tsquery('english', :query)) AS keyword_score
        FROM pdf_chunks pc
        {extra_joins}
        WHERE pc.user_id = :user_id
          {where_extra}
          AND pc.search_vector @@ plainto_tsquery('english', :query)
        LIMIT :limit1
    )
    SELECT COALESCE(v.id, k.id) as id{coalesce_pdf_cols},
           COALESCE(v.page_number, k.page_number) as page_number,
           COALESCE(v.end_page_number, k.end_page_number) as end_page_number,
           COALESCE(v.content, k.content) as content,
           COALESCE(v.section_title, k.section_title) as section_title,
           COALESCE(v.section_level, k.section_level) as section_level,
           (COALESCE(v.semantic_score, 0) * :sem_weight +
            COALESCE(k.keyword_score, 0) * :kw_weight) AS combined_score
    FROM vector_results v
    FULL OUTER JOIN keyword_results k {hybrid_join_on}
    ORDER BY combined_score DESC
    LIMIT :limit1
"""

_VECTOR_SQL = """
    SELECT pc.id{select_pdf_cols}, pc.page_number, pc.end_page_number, pc.content,
           pc.section_title, pc.section_level,
           1 - (pc.embedding <=> CAST(:vec AS halfvec)) AS score
    FROM pdf_chunks pc
    {extra_joins}
    WHERE pc.user_id = :user_id
      {where_extra}
    ORDER BY pc.embedding <=> CAST(:vec AS halfvec)
    LIMIT :limit1
"""


class VectorSearchService:
    """Service for semantic vector search operations using pgvector."""

    def _build_hybrid_query(self, scope: _SearchScope) -> str:
        return _HYBRID_SQL.format(
            extra_joins=scope.extra_joins,
            where_extra=scope.where_extra,
            select_pdf_cols=scope.select_pdf_cols,
            coalesce_pdf_cols=scope.coalesce_pdf_cols,
            hybrid_join_on=scope.hybrid_join_on,
        )

    def _build_vector_query(self, scope: _SearchScope) -> str:
        return _VECTOR_SQL.format(
            extra_joins=scope.extra_joins,
            where_extra=scope.where_extra,
            select_pdf_cols=scope.select_pdf_cols,
        )

    async def search_pdf(
        self,
        query_vector: list[float],
        pdf_id: UUID | str,
        user_id: UUID | str,
        top_k: int,
        db: AsyncSession,
        current_page: int | None = None,
        query_text: str | None = None,
    ) -> list[SearchResult]:
        """Search within a single PDF for semantically similar chunks."""
        vec_str = f"[{','.join(str(x) for x in query_vector)}]"

        scope = _SearchScope(
            extra_joins="",
            where_extra="AND pc.pdf_id = :pdf_id",
            select_pdf_cols="",
            coalesce_pdf_cols="",
            hybrid_join_on="ON v.id = k.id",
            scope_params={"pdf_id": str(pdf_id)},
        )

        if query_text:
            rows = await db.execute(
                sql_text(self._build_hybrid_query(scope)),
                {
                    "vec": vec_str,
                    "user_id": str(user_id),
                    "limit1": top_k,
                    "limit2": top_k * 2,
                    "query": query_text,
                    "sem_weight": settings.HYBRID_SEMANTIC_WEIGHT,
                    "kw_weight": settings.HYBRID_KEYWORD_WEIGHT,
                    **scope.scope_params,
                },
            )
        else:
            rows = await db.execute(
                sql_text(self._build_vector_query(scope)),
                {
                    "vec": vec_str,
                    "user_id": str(user_id),
                    "limit1": top_k,
                    **scope.scope_params,
                },
            )

        results = [
            SearchResult(
                chunk_id=str(r.id),
                pdf_id=None,
                pdf_title=None,
                page_number=r.page_number,
                end_page_number=r.end_page_number,
                content=r.content,
                score=float(r.combined_score if query_text else r.score),
                section_title=r.section_title,
                section_level=r.section_level,
            )
            for r in rows
        ]

        if current_page is not None:
            for result in results:
                distance = abs(result.page_number - current_page)
                proximity_boost = max(0, 0.1 * (1 - distance / 10))
                result.score *= 1 + proximity_boost
            results.sort(key=lambda r: r.score, reverse=True)
            results = results[:top_k]

        return results

    async def search_collection(
        self,
        query_vector: list[float],
        collection_id: UUID | str,
        user_id: UUID | str,
        top_k: int,
        db: AsyncSession,
        query_text: str | None = None,
    ) -> list[SearchResult]:
        """Search across all indexed PDFs in a collection."""
        vec_str = f"[{','.join(str(x) for x in query_vector)}]"

        scope = _SearchScope(
            extra_joins="JOIN pdfs p ON p.id = pc.pdf_id\n        JOIN pdf_collections pcol ON pcol.pdf_id = pc.pdf_id",
            where_extra="AND pcol.collection_id = :collection_id",
            select_pdf_cols=", pc.pdf_id, p.title AS pdf_title",
            coalesce_pdf_cols=",\n           COALESCE(v.pdf_id, k.pdf_id) as pdf_id,\n           COALESCE(v.pdf_title, k.pdf_title) as pdf_title",
            hybrid_join_on="ON v.id = k.id",
            scope_params={"collection_id": str(collection_id)},
        )

        if query_text:
            rows = await db.execute(
                sql_text(self._build_hybrid_query(scope)),
                {
                    "vec": vec_str,
                    "user_id": str(user_id),
                    "limit1": top_k,
                    "limit2": top_k * 2,
                    "query": query_text,
                    "sem_weight": settings.HYBRID_SEMANTIC_WEIGHT,
                    "kw_weight": settings.HYBRID_KEYWORD_WEIGHT,
                    **scope.scope_params,
                },
            )
        else:
            rows = await db.execute(
                sql_text(self._build_vector_query(scope)),
                {
                    "vec": vec_str,
                    "user_id": str(user_id),
                    "limit1": top_k,
                    **scope.scope_params,
                },
            )

        return [
            SearchResult(
                chunk_id=str(r.id),
                pdf_id=str(r.pdf_id),
                pdf_title=r.pdf_title,
                page_number=r.page_number,
                end_page_number=r.end_page_number,
                content=r.content,
                score=float(r.combined_score if query_text else r.score),
                section_title=r.section_title,
                section_level=r.section_level,
            )
            for r in rows
        ]

    async def search_all(
        self,
        query_vector: list[float],
        user_id: UUID | str,
        limit: int,
        db: AsyncSession,
        query_text: str | None = None,
    ) -> list[SearchResult]:
        """Search across all of the user's indexed PDFs.

        Deduplicates results to return only the best chunk per PDF.
        """
        vec_str = f"[{','.join(str(x) for x in query_vector)}]"

        scope = _SearchScope(
            extra_joins="JOIN pdfs p ON p.id = pc.pdf_id",
            where_extra="",
            select_pdf_cols=", pc.pdf_id, p.title AS pdf_title",
            coalesce_pdf_cols=",\n           COALESCE(v.pdf_id, k.pdf_id) as pdf_id,\n           COALESCE(v.pdf_title, k.pdf_title) as pdf_title",
            hybrid_join_on="ON v.pdf_id = k.pdf_id",
            scope_params={},
        )

        if query_text:
            rows = await db.execute(
                sql_text(self._build_hybrid_query(scope)),
                {
                    "vec": vec_str,
                    "user_id": str(user_id),
                    "limit1": limit,
                    "limit2": limit * 2,
                    "query": query_text,
                    "sem_weight": settings.HYBRID_SEMANTIC_WEIGHT,
                    "kw_weight": settings.HYBRID_KEYWORD_WEIGHT,
                },
            )
        else:
            rows = await db.execute(
                sql_text(self._build_vector_query(scope)),
                {
                    "vec": vec_str,
                    "user_id": str(user_id),
                    "limit1": limit * 3,
                },
            )

        seen: dict[str, SearchResult] = {}
        for r in rows:
            pdf_id_str = str(r.pdf_id)
            if pdf_id_str not in seen:
                seen[pdf_id_str] = SearchResult(
                    chunk_id=str(r.id) if query_text else None,
                    pdf_id=pdf_id_str,
                    pdf_title=r.pdf_title,
                    page_number=r.page_number,
                    end_page_number=r.end_page_number if query_text else None,
                    content=r.content if query_text else r.content[:300],
                    score=float(r.combined_score if query_text else r.score),
                    section_title=r.section_title,
                    section_level=r.section_level,
                )
            if len(seen) >= limit:
                break

        return list(seen.values())


# Singleton instance for use in routes
vector_search_service = VectorSearchService()
