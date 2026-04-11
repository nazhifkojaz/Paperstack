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
    """Result from a vector search query.

    Attributes:
        chunk_id: Unique identifier for the chunk (None for multi-PDF search)
        pdf_id: PDF ID (None for single-PDF search)
        pdf_title: PDF title (None for single-PDF search)
        page_number: Page number where chunk appears
        end_page_number: End page number (same as page_number if single page)
        content: The chunk text content
        score: Cosine similarity score (0-1, higher is better)
    """

    chunk_id: str | None
    pdf_id: str | None
    pdf_title: str | None
    page_number: int
    content: str
    score: float
    end_page_number: int | None = None
    section_title: str | None = None
    section_level: int | None = None


class VectorSearchService:
    """Service for semantic vector search operations using pgvector."""

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
        """Search within a single PDF for semantically similar chunks.

        Uses hybrid search (vector + full-text) when query_text is provided,
        otherwise falls back to pure vector similarity.

        Args:
            query_vector: Embedding vector for the query text
            pdf_id: The PDF to search within
            user_id: The user ID (for ownership check)
            top_k: Maximum number of results to return
            db: Database session
            current_page: Optional current page for proximity boosting
            query_text: Optional raw query text for full-text search (enables hybrid)

        Returns:
            List of SearchResult ordered by similarity (highest first)
        """
        vec_str = f"[{','.join(str(x) for x in query_vector)}]"

        if query_text:
            rows = await db.execute(
                sql_text("""
                    WITH vector_results AS (
                        SELECT id, page_number, end_page_number, content,
                               section_title, section_level,
                               1 - (embedding <=> CAST(:vec AS vector)) AS semantic_score
                        FROM pdf_chunks
                        WHERE user_id = :user_id
                          AND pdf_id = :pdf_id
                        ORDER BY embedding <=> CAST(:vec AS vector)
                        LIMIT :k2
                    ),
                    keyword_results AS (
                        SELECT id, page_number, end_page_number, content,
                               section_title, section_level,
                               ts_rank(search_vector, plainto_tsquery('english', :query)) AS keyword_score
                        FROM pdf_chunks
                        WHERE user_id = :user_id
                          AND pdf_id = :pdf_id
                          AND search_vector @@ plainto_tsquery('english', :query)
                        LIMIT :k
                    )
                    SELECT COALESCE(v.id, k.id) as id,
                           COALESCE(v.page_number, k.page_number) as page_number,
                           COALESCE(v.end_page_number, k.end_page_number) as end_page_number,
                           COALESCE(v.content, k.content) as content,
                           COALESCE(v.section_title, k.section_title) as section_title,
                           COALESCE(v.section_level, k.section_level) as section_level,
                           (COALESCE(v.semantic_score, 0) * :sem_weight +
                            COALESCE(k.keyword_score, 0) * :kw_weight) AS combined_score
                    FROM vector_results v
                    FULL OUTER JOIN keyword_results k ON v.id = k.id
                    ORDER BY combined_score DESC
                    LIMIT :k
                """),
                {
                    "vec": vec_str,
                    "user_id": str(user_id),
                    "pdf_id": str(pdf_id),
                    "k": top_k,
                    "k2": top_k * 2,
                    "query": query_text,
                    "sem_weight": settings.HYBRID_SEMANTIC_WEIGHT,
                    "kw_weight": settings.HYBRID_KEYWORD_WEIGHT,
                },
            )
        else:
            rows = await db.execute(
                sql_text("""
                    SELECT pc.id, pc.page_number, pc.end_page_number, pc.content,
                           pc.section_title, pc.section_level,
                           1 - (pc.embedding <=> CAST(:vec AS vector)) AS score
                    FROM pdf_chunks pc
                    WHERE pc.user_id = :user_id
                      AND pc.pdf_id = :pdf_id
                    ORDER BY pc.embedding <=> CAST(:vec AS vector)
                    LIMIT :k
                """),
                {
                    "vec": vec_str,
                    "user_id": str(user_id),
                    "pdf_id": str(pdf_id),
                    "k": top_k,
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
        """Search across all indexed PDFs in a collection.

        Uses hybrid search (vector + full-text) when query_text is provided,
        otherwise falls back to pure vector similarity.

        Args:
            query_vector: Embedding vector for the query text
            collection_id: The collection to search within
            user_id: The user ID (for ownership check)
            top_k: Maximum number of results to return
            db: Database session
            query_text: Optional raw query text for full-text search (enables hybrid)

        Returns:
            List of SearchResult ordered by similarity (highest first),
            with pdf_id and pdf_title populated
        """
        vec_str = f"[{','.join(str(x) for x in query_vector)}]"

        if query_text:
            rows = await db.execute(
                sql_text("""
                    WITH vector_results AS (
                        SELECT pc.id, pc.pdf_id, pc.page_number, pc.end_page_number, pc.content, p.title AS pdf_title,
                               pc.section_title, pc.section_level,
                               1 - (pc.embedding <=> CAST(:vec AS vector)) AS semantic_score
                        FROM pdf_chunks pc
                        JOIN pdfs p ON p.id = pc.pdf_id
                        JOIN pdf_collections pcol ON pcol.pdf_id = pc.pdf_id
                        WHERE pc.user_id = :user_id
                          AND pcol.collection_id = :collection_id
                        ORDER BY pc.embedding <=> CAST(:vec AS vector)
                        LIMIT :k2
                    ),
                    keyword_results AS (
                        SELECT pc.id, pc.pdf_id, pc.page_number, pc.end_page_number, pc.content, p.title AS pdf_title,
                               pc.section_title, pc.section_level,
                               ts_rank(pc.search_vector, plainto_tsquery('english', :query)) AS keyword_score
                        FROM pdf_chunks pc
                        JOIN pdfs p ON p.id = pc.pdf_id
                        JOIN pdf_collections pcol ON pcol.pdf_id = pc.pdf_id
                        WHERE pc.user_id = :user_id
                          AND pcol.collection_id = :collection_id
                          AND pc.search_vector @@ plainto_tsquery('english', :query)
                        LIMIT :k
                    )
                    SELECT COALESCE(v.id, k.id) as id,
                           COALESCE(v.pdf_id, k.pdf_id) as pdf_id,
                           COALESCE(v.page_number, k.page_number) as page_number,
                           COALESCE(v.end_page_number, k.end_page_number) as end_page_number,
                           COALESCE(v.content, k.content) as content,
                           COALESCE(v.pdf_title, k.pdf_title) as pdf_title,
                           COALESCE(v.section_title, k.section_title) as section_title,
                           COALESCE(v.section_level, k.section_level) as section_level,
                           (COALESCE(v.semantic_score, 0) * :sem_weight +
                            COALESCE(k.keyword_score, 0) * :kw_weight) AS combined_score
                    FROM vector_results v
                    FULL OUTER JOIN keyword_results k ON v.id = k.id
                    ORDER BY combined_score DESC
                    LIMIT :k
                """),
                {
                    "vec": vec_str,
                    "collection_id": str(collection_id),
                    "user_id": str(user_id),
                    "k": top_k,
                    "k2": top_k * 2,
                    "query": query_text,
                    "sem_weight": settings.HYBRID_SEMANTIC_WEIGHT,
                    "kw_weight": settings.HYBRID_KEYWORD_WEIGHT,
                },
            )
        else:
            rows = await db.execute(
                sql_text("""
                    SELECT pc.id, pc.pdf_id, pc.page_number, pc.end_page_number, pc.content, p.title AS pdf_title,
                           pc.section_title, pc.section_level,
                           1 - (pc.embedding <=> CAST(:vec AS vector)) AS score
                    FROM pdf_chunks pc
                    JOIN pdfs p ON p.id = pc.pdf_id
                    JOIN pdf_collections pcol ON pcol.pdf_id = pc.pdf_id
                    WHERE pc.user_id = :user_id
                      AND pcol.collection_id = :collection_id
                    ORDER BY pc.embedding <=> CAST(:vec AS vector)
                    LIMIT :k
                """),
                {
                    "vec": vec_str,
                    "collection_id": str(collection_id),
                    "user_id": str(user_id),
                    "k": top_k,
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

        Uses hybrid search (vector + full-text) when query_text is provided,
        otherwise falls back to pure vector similarity.

        Deduplicates results to return only the best chunk per PDF.

        Args:
            query_vector: Embedding vector for the query text
            user_id: The user ID
            limit: Maximum number of PDFs to return (not chunks)
            db: Database session
            query_text: Optional raw query text for full-text search (enables hybrid)

        Returns:
            List of SearchResult, one per PDF, ordered by similarity
        """
        vec_str = f"[{','.join(str(x) for x in query_vector)}]"

        if query_text:
            rows = await db.execute(
                sql_text("""
                    WITH vector_results AS (
                        SELECT pc.id, pc.pdf_id, p.title AS pdf_title, pc.page_number, pc.end_page_number, pc.content,
                               pc.section_title, pc.section_level,
                               1 - (pc.embedding <=> CAST(:vec AS vector)) AS semantic_score
                        FROM pdf_chunks pc
                        JOIN pdfs p ON p.id = pc.pdf_id
                        WHERE pc.user_id = :user_id
                        ORDER BY pc.embedding <=> CAST(:vec AS vector)
                        LIMIT :limit2
                    ),
                    keyword_results AS (
                        SELECT pc.id, pc.pdf_id, p.title AS pdf_title, pc.page_number, pc.end_page_number, pc.content,
                               pc.section_title, pc.section_level,
                               ts_rank(pc.search_vector, plainto_tsquery('english', :query)) AS keyword_score
                        FROM pdf_chunks pc
                        JOIN pdfs p ON p.id = pc.pdf_id
                        WHERE pc.user_id = :user_id
                          AND pc.search_vector @@ plainto_tsquery('english', :query)
                        LIMIT :limit
                    )
                    SELECT COALESCE(v.id, k.id) as id,
                           COALESCE(v.pdf_id, k.pdf_id) as pdf_id,
                           COALESCE(v.pdf_title, k.pdf_title) as pdf_title,
                           COALESCE(v.page_number, k.page_number) as page_number,
                           COALESCE(v.end_page_number, k.end_page_number) as end_page_number,
                           COALESCE(v.content, k.content) as content,
                           COALESCE(v.section_title, k.section_title) as section_title,
                           COALESCE(v.section_level, k.section_level) as section_level,
                           (COALESCE(v.semantic_score, 0) * :sem_weight +
                            COALESCE(k.keyword_score, 0) * :kw_weight) AS combined_score
                    FROM vector_results v
                    FULL OUTER JOIN keyword_results k ON v.pdf_id = k.pdf_id
                    ORDER BY combined_score DESC
                    LIMIT :limit
                """),
                {
                    "vec": vec_str,
                    "user_id": str(user_id),
                    "limit": limit,
                    "limit2": limit * 2,
                    "query": query_text,
                    "sem_weight": settings.HYBRID_SEMANTIC_WEIGHT,
                    "kw_weight": settings.HYBRID_KEYWORD_WEIGHT,
                },
            )
        else:
            rows = await db.execute(
                sql_text("""
                    SELECT pc.id, pc.pdf_id, p.title AS pdf_title, pc.page_number, pc.end_page_number, pc.content,
                           pc.section_title, pc.section_level,
                           1 - (pc.embedding <=> CAST(:vec AS vector)) AS score
                    FROM pdf_chunks pc
                    JOIN pdfs p ON p.id = pc.pdf_id
                    WHERE pc.user_id = :user_id
                    ORDER BY pc.embedding <=> CAST(:vec AS vector)
                    LIMIT :limit
                """),
                {
                    "vec": vec_str,
                    "user_id": str(user_id),
                    "limit": limit * 3,
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
