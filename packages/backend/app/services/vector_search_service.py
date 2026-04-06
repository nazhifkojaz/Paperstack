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


logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    """Result from a vector search query.

    Attributes:
        chunk_id: Unique identifier for the chunk (None for multi-PDF search)
        pdf_id: PDF ID (None for single-PDF search)
        pdf_title: PDF title (None for single-PDF search)
        page_number: Page number where chunk appears
        content: The chunk text content
        score: Cosine similarity score (0-1, higher is better)
    """
    chunk_id: str | None
    pdf_id: str | None
    pdf_title: str | None
    page_number: int
    content: str
    score: float


class VectorSearchService:
    """Service for semantic vector search operations using pgvector."""

    async def search_pdf(
        self,
        query_vector: list[float],
        pdf_id: UUID | str,
        user_id: UUID | str,
        top_k: int,
        db: AsyncSession,
    ) -> list[SearchResult]:
        """Search within a single PDF for semantically similar chunks.

        Args:
            query_vector: Embedding vector for the query text
            pdf_id: The PDF to search within
            user_id: The user ID (for ownership check)
            top_k: Maximum number of results to return
            db: Database session

        Returns:
            List of SearchResult ordered by similarity (highest first)
        """
        vec_str = f"[{','.join(str(x) for x in query_vector)}]"
        rows = await db.execute(
            sql_text("""
                SELECT pc.id, pc.page_number, pc.content,
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

        return [
            SearchResult(
                chunk_id=str(r.id),
                pdf_id=None,
                pdf_title=None,
                page_number=r.page_number,
                content=r.content,
                score=float(r.score),
            )
            for r in rows
        ]

    async def search_collection(
        self,
        query_vector: list[float],
        collection_id: UUID | str,
        user_id: UUID | str,
        top_k: int,
        db: AsyncSession,
    ) -> list[SearchResult]:
        """Search across all indexed PDFs in a collection.

        Args:
            query_vector: Embedding vector for the query text
            collection_id: The collection to search within
            user_id: The user ID (for ownership check)
            top_k: Maximum number of results to return
            db: Database session

        Returns:
            List of SearchResult ordered by similarity (highest first),
            with pdf_id and pdf_title populated
        """
        vec_str = f"[{','.join(str(x) for x in query_vector)}]"
        rows = await db.execute(
            sql_text("""
                SELECT pc.id, pc.pdf_id, pc.page_number, pc.content, p.title AS pdf_title,
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
                content=r.content,
                score=float(r.score),
            )
            for r in rows
        ]

    async def search_all(
        self,
        query_vector: list[float],
        user_id: UUID | str,
        limit: int,
        db: AsyncSession,
    ) -> list[SearchResult]:
        """Search across all of the user's indexed PDFs.

        Deduplicates results to return only the best chunk per PDF.

        Args:
            query_vector: Embedding vector for the query text
            user_id: The user ID
            limit: Maximum number of PDFs to return (not chunks)
            db: Database session

        Returns:
            List of SearchResult, one per PDF, ordered by similarity
        """
        vec_str = f"[{','.join(str(x) for x in query_vector)}]"
        rows = await db.execute(
            sql_text("""
                SELECT pc.pdf_id, p.title AS pdf_title, pc.page_number, pc.content,
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
                "limit": limit * 3,  # Over-fetch to allow dedup by pdf_id
            },
        )

        # Deduplicate: keep best-scoring chunk per PDF
        seen: dict[str, SearchResult] = {}
        for r in rows:
            pdf_id_str = str(r.pdf_id)
            if pdf_id_str not in seen:
                seen[pdf_id_str] = SearchResult(
                    chunk_id=None,  # We don't return chunk_id for multi-PDF search
                    pdf_id=pdf_id_str,
                    pdf_title=r.pdf_title,
                    page_number=r.page_number,
                    content=r.content[:300],  # Snippet for preview
                    score=float(r.score),
                )
            if len(seen) >= limit:
                break

        return list(seen.values())


# Singleton instance for use in routes
vector_search_service = VectorSearchService()
