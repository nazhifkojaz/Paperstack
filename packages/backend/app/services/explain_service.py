"""Service for explaining annotations using RAG.

This service handles the complete workflow for explaining highlighted passages:
1. Ensure PDF is indexed (lazy indexing)
2. Embed the selected text as query
3. Vector search for relevant context
4. Build prompt and call LLM

Services raise custom exceptions, never HTTPException.
Route handlers translate to appropriate HTTP status codes.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Pdf, PdfIndexStatus, User
from app.services.chat_service import ChatService
from app.services.embedding_service import EmbeddingService
from app.services.exceptions import EmbeddingError, IndexingError
from app.services.indexing_service import IndexingService, get_indexing_service
from app.services.llm_service import LLMService
from app.services.pdf_download_service import pdf_download_service
from app.services.vector_search_service import SearchResult, vector_search_service


logger = logging.getLogger(__name__)


EXPLAIN_SYSTEM_PROMPT = (
    "You are a research assistant. Explain the following highlighted passage "
    "from an academic paper in clear, concise language. "
    "Use the context excerpts provided to enrich your explanation — include why "
    "the passage matters and how it connects to the paper's broader argument. "
    "Keep the explanation under 200 words. Use plain language. "
    "You may use **bold** for key terms. Cite page numbers as [p.N] when relevant."
)


@dataclass
class ExplainResult:
    """Result of an annotation explanation.

    Attributes:
        explanation: The AI-generated explanation text
        context_chunks: The chunks used as context for the explanation
        note_content: Full note content including timestamp
    """
    explanation: str
    context_chunks: list[dict]
    note_content: str


class ExplainService:
    """Service for explaining highlighted passages using RAG.

    Accepts optional service instances for dependency injection.
    """

    def __init__(
        self,
        embedding_service: Optional[EmbeddingService] = None,
        llm_service: Optional[LLMService] = None,
        chat_service: Optional[ChatService] = None,
        indexing_service: Optional[IndexingService] = None,
    ):
        """Initialize explain service with optional injected services.

        Args:
            embedding_service: EmbeddingService for query embedding
            llm_service: LLMService for LLM calls
            chat_service: ChatService for context building
            indexing_service: IndexingService for lazy indexing
        """
        self._embedding_service = embedding_service or EmbeddingService()
        self._llm_service = llm_service or LLMService()
        self._chat_service = chat_service or ChatService()
        self._indexing_service = indexing_service or get_indexing_service(pdf_download_service)

    async def explain_with_provider(
        self,
        selected_text: str,
        page_number: int,
        pdf_row: Pdf,
        user: User,
        provider: str,
        api_key: str,
        db: AsyncSession,
    ) -> ExplainResult:
        """Generate explanation with explicit provider and API key.

        This is the main entry point for routes.

        Args:
            selected_text: The highlighted text to explain
            page_number: Page number of the annotation
            pdf_row: The PDF containing the annotation
            user: The user who owns the annotation
            provider: LLM provider to use
            api_key: API key for the provider
            db: Database session

        Returns:
            ExplainResult with explanation and context

        Raises:
            EmbeddingError: If query embedding fails
            IndexingError: If PDF indexing fails
        """
        # 1. Ensure PDF is indexed
        index_status = await self._indexing_service.get_or_create_status(
            str(pdf_row.id), str(user.id), db
        )

        # Handle stale/active indexing
        await self._indexing_service.reset_if_stale(index_status, db)

        # Handle failed indexing - reset to retry
        if index_status.status == "failed":
            index_status.status = "not_indexed"
            index_status.error_message = None
            await db.flush()

        # Lazy index if needed
        if index_status.status == "not_indexed":
            logger.info("explain: indexing pdf %s for user %s", pdf_row.id, user.id)
            try:
                await self._indexing_service.index_pdf(pdf_row, user, index_status, db)
                await db.commit()
                logger.info("explain: indexing complete for pdf %s", pdf_row.id)
            except Exception:
                # Persist the failed status set by index_pdf before re-raising
                await db.commit()
                raise

        # 2. Embed selected text as query vector
        query_vector = await self._embedding_service.embed_query(selected_text)

        # 3. Vector search for context (top 4 — tighter than chat's 6)
        top_chunks = await vector_search_service.search_pdf(
            query_vector=query_vector,
            pdf_id=pdf_row.id,
            user_id=user.id,
            top_k=4,
            db=db,
        )

        # 4. Build context
        context = self._chat_service.build_context(
            [{"page_number": c.page_number, "content": c.content} for c in top_chunks]
        )

        # 5. Build prompt and call LLM (non-streaming)
        system_prompt = EXPLAIN_SYSTEM_PROMPT + "\n\n## Context from the paper:\n\n" + context
        user_message = (
            f'Explain this passage from page {page_number}:\n\n'
            f'"{selected_text}"'
        )

        call_method = getattr(self._llm_service, f"call_{provider}")
        explanation = await call_method(system_prompt, user_message, api_key)

        # 6. Build context_chunks payload
        context_chunks_payload = [
            {
                "chunk_id": c.chunk_id,
                "page_number": c.page_number,
                "snippet": c.content[:200],
            }
            for c in top_chunks
        ]

        # 7. Build note content with timestamp
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        new_block = f"[AI Explanation — {timestamp}]\n{explanation}"

        return ExplainResult(
            explanation=explanation,
            context_chunks=context_chunks_payload,
            note_content=new_block,
        )


# Singleton instance for use in routes (will be replaced with DI in routes)
explain_service = ExplainService()
