"""Orchestrates the full RAG pipeline for chat message streaming.

Encapsulates: embedding, indexing, vector search, context building,
citation fetching, message persistence, and LLM streaming.

Services raise custom exceptions, never HTTPException.
Route handlers translate to appropriate HTTP status codes.
"""

import logging
import uuid
from dataclasses import dataclass
from typing import AsyncIterator, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ChatConversation, ChatMessage, Citation, Pdf, User
from app.core.config import settings
from app.schemas.types import ChatMessageDict, PaperMetadata
from app.services.chat_service import ChatService, COLLECTION_SYSTEM_PROMPT
from app.services.embedding_service import EmbeddingService
from app.services.exceptions import (
    EmbeddingError,
    IndexInProgressError,
    IndexingError,
    LLMRateLimitError,
    OpenRouterQuotaError,
)
from app.services.indexing_service import IndexingService, get_indexing_service
from app.services.llm_service import LLMService
from app.services.pdf_download_service import pdf_download_service
from app.services.vector_search_service import vector_search_service


logger = logging.getLogger(__name__)


@dataclass
class PreparedContext:
    context: str
    top_chunks: list
    paper_metadata: PaperMetadata | list[PaperMetadata] | None
    context_chunks_payload: list[dict]


@dataclass
class PreparedMessages:
    system_prompt: str
    messages: list[ChatMessageDict]


class ChatOrchestrator:
    """Orchestrates the full RAG pipeline for chat message streaming.

    Accepts optional service instances for dependency injection.
    """

    def __init__(
        self,
        embedding_service: Optional[EmbeddingService] = None,
        llm_service: Optional[LLMService] = None,
        chat_service: Optional[ChatService] = None,
        indexing_service: Optional[IndexingService] = None,
    ):
        self._embedding_service = embedding_service or EmbeddingService()
        self._llm_service = llm_service or LLMService()
        self._chat_service = chat_service or ChatService(llm_service=self._llm_service)
        self._indexing_service = indexing_service or get_indexing_service(
            pdf_download_service
        )

    async def prepare_context(
        self,
        *,
        query: str,
        pdf_id: uuid.UUID | None,
        collection_id: uuid.UUID | None,
        user: User,
        db: AsyncSession,
    ) -> PreparedContext:
        """Embed query, run vector search, build context, fetch citations."""
        query_vector = await self._embedding_service.embed_query(query, db=db)

        if pdf_id is not None:
            return await self._prepare_pdf_context(
                query_vector=query_vector,
                query_text=query,
                pdf_id=pdf_id,
                user=user,
                db=db,
            )
        else:
            return await self._prepare_collection_context(
                query_vector=query_vector,
                query_text=query,
                collection_id=collection_id,
                user=user,
                db=db,
            )

    async def _prepare_pdf_context(
        self,
        *,
        query_vector: list,
        query_text: str,
        pdf_id: uuid.UUID,
        user: User,
        db: AsyncSession,
    ) -> PreparedContext:
        pdf_result = await db.execute(
            select(Pdf).where(Pdf.id == pdf_id, Pdf.user_id == user.id)
        )
        pdf_row = pdf_result.scalar_one_or_none()
        if not pdf_row:
            raise ValueError("PDF not found.")

        index_status = await self._indexing_service.get_or_create_status(
            str(pdf_id), str(user.id), db
        )

        try:
            await self._indexing_service.ensure_indexed(pdf_row, user, index_status, db)
            await db.commit()
        except IndexInProgressError:
            raise
        except (EmbeddingError, OpenRouterQuotaError, IndexingError):
            await db.commit()
            raise

        top_chunks = await vector_search_service.search_pdf(
            query_vector=query_vector,
            pdf_id=pdf_id,
            user_id=user.id,
            top_k=settings.CHAT_TOP_K_SINGLE_PDF,
            db=db,
            query_text=query_text,
        )
        context = self._chat_service.build_context(
            [{"page_number": c.page_number, "end_page_number": c.end_page_number, "content": c.content, "section_title": c.section_title} for c in top_chunks]
        )

        paper_metadata = await self._fetch_pdf_citation(pdf_id, pdf_row, user, db)

        context_chunks_payload = self._build_chunks_payload(top_chunks)

        return PreparedContext(
            context=context,
            top_chunks=top_chunks,
            paper_metadata=paper_metadata,
            context_chunks_payload=context_chunks_payload,
        )

    async def _prepare_collection_context(
        self,
        *,
        query_vector: list,
        query_text: str,
        collection_id: uuid.UUID | None,
        user: User,
        db: AsyncSession,
    ) -> PreparedContext:
        if collection_id is None:
            raise ValueError("Conversation has neither pdf_id nor collection_id.")

        top_chunks = await vector_search_service.search_collection(
            query_vector=query_vector,
            collection_id=collection_id,
            user_id=user.id,
            top_k=settings.CHAT_TOP_K_COLLECTION,
            db=db,
            query_text=query_text,
        )
        if not top_chunks:
            raise ValueError("No indexed PDFs found in this collection.")

        context_parts = []
        for c in top_chunks:
            end_page = getattr(c, "end_page_number", None)
            if end_page and end_page > c.page_number:
                page_label = f"Pages {c.page_number}-{end_page}"
            else:
                page_label = f"Page {c.page_number}"
            context_parts.append(f"[{c.pdf_title}, {page_label}]\n{c.content}")
        context = "\n\n---\n\n".join(context_parts)

        paper_metadata = await self._fetch_collection_citations(top_chunks, user, db)

        context_chunks_payload = self._build_chunks_payload(top_chunks)

        return PreparedContext(
            context=context,
            top_chunks=top_chunks,
            paper_metadata=paper_metadata,
            context_chunks_payload=context_chunks_payload,
        )

    async def _fetch_pdf_citation(
        self,
        pdf_id: uuid.UUID,
        pdf_row: Pdf,
        user: User,
        db: AsyncSession,
    ) -> PaperMetadata | None:
        citation_result = await db.execute(
            select(Citation).where(
                Citation.pdf_id == pdf_id,
                Citation.user_id == user.id,
            )
        )
        citation_row = citation_result.scalar_one_or_none()
        if citation_row:
            metadata: PaperMetadata = {"title": pdf_row.title}
            if citation_row.authors:
                metadata["authors"] = citation_row.authors
            if citation_row.year:
                metadata["year"] = citation_row.year
            return metadata
        elif pdf_row.title:
            return {"title": pdf_row.title}
        return None

    async def _fetch_collection_citations(
        self,
        top_chunks: list,
        user: User,
        db: AsyncSession,
    ) -> list[PaperMetadata] | None:
        unique_pdf_ids = {c.pdf_id for c in top_chunks if c.pdf_id}
        if not unique_pdf_ids:
            return None

        citation_rows = await db.execute(
            select(Citation).where(
                Citation.pdf_id.in_(unique_pdf_ids),
                Citation.user_id == user.id,
            )
        )
        citation_by_pdf = {
            str(c.pdf_id): c for c in citation_rows.scalars().all()
        }

        seen_titles = set()
        metadata_list: list[PaperMetadata] = []
        for c in top_chunks:
            if not c.pdf_id or c.pdf_title in seen_titles:
                continue
            seen_titles.add(c.pdf_title)
            entry: PaperMetadata = {"title": c.pdf_title}
            cit = citation_by_pdf.get(str(c.pdf_id))
            if cit:
                if cit.authors:
                    entry["authors"] = cit.authors
                if cit.year:
                    entry["year"] = cit.year
            metadata_list.append(entry)

        return metadata_list if metadata_list else None

    def _build_chunks_payload(self, top_chunks: list) -> list[dict]:
        return [
            {
                "chunk_id": c.chunk_id,
                "page_number": c.page_number,
                "end_page_number": c.end_page_number,
                "snippet": c.content[:200],
                "section_title": c.section_title,
                "section_level": c.section_level,
                **({"pdf_id": c.pdf_id, "pdf_title": c.pdf_title} if c.pdf_id else {}),
            }
            for c in top_chunks
        ]

    async def build_messages(
        self,
        *,
        context: str,
        history: list[ChatMessageDict],
        user_message: str,
        collection_id: uuid.UUID | None,
        paper_metadata: PaperMetadata | list[PaperMetadata] | None,
    ) -> PreparedMessages:
        system_prompt, messages = self._chat_service.build_messages(
            context,
            history,
            user_message,
            base_prompt=COLLECTION_SYSTEM_PROMPT if collection_id else None,
            paper_metadata=paper_metadata,
        )
        return PreparedMessages(
            system_prompt=system_prompt,
            messages=messages,
        )

    async def persist_user_message(
        self,
        *,
        conversation_id: uuid.UUID,
        content: str,
        conv: ChatConversation,
        db: AsyncSession,
    ) -> None:
        user_msg = ChatMessage(
            conversation_id=conversation_id,
            role="user",
            content=content,
        )
        db.add(user_msg)
        if not conv.title:
            truncated = content.strip()
            conv.title = truncated[:60] + ("…" if len(truncated) > 60 else "")
        await db.commit()

    async def stream_and_save(
        self,
        *,
        system_prompt: str,
        messages: list[ChatMessageDict],
        provider: str,
        api_key: str,
        model: str | None,
        conversation_id: uuid.UUID,
        context_chunks_payload: list[dict],
        db: AsyncSession,
    ) -> AsyncIterator[dict]:
        """Stream LLM reply, persist assistant message, yield SSE event dicts."""
        full_reply: list[str] = []
        assistant_message_id = str(uuid.uuid4())

        try:
            try:
                async for token in self._chat_service.stream_reply(
                    system_prompt, messages, provider, api_key,
                    model=model,
                ):
                    full_reply.append(token)
                    yield {"token": token}
            except LLMRateLimitError:
                yield {
                    "error": "Free tier rate limited. Please try again later or use your own API key.",
                    "code": "rate_limited",
                }
                return

            msg = ChatMessage(
                id=uuid.UUID(assistant_message_id),
                conversation_id=conversation_id,
                role="assistant",
                content="".join(full_reply),
                context_chunks=[
                    {
                        "chunk_id": c["chunk_id"],
                        "page_number": c["page_number"],
                        "end_page_number": c.get("end_page_number"),
                        "snippet": c["snippet"],
                        "section_title": c.get("section_title"),
                        "section_level": c.get("section_level"),
                        **(
                            {"pdf_id": c["pdf_id"], "pdf_title": c["pdf_title"]}
                            if c.get("pdf_id")
                            else {}
                        ),
                    }
                    for c in context_chunks_payload
                ],
            )
            db.add(msg)
            await db.commit()
            logger.info(
                "Saved assistant message for conversation %s (%d chars, %d chunks)",
                conversation_id,
                len("".join(full_reply)),
                len(context_chunks_payload),
            )

            yield {
                "done": True,
                "message_id": assistant_message_id,
                "context_chunks": context_chunks_payload,
            }

        except Exception:
            logger.exception("Streaming error for conversation %s", conversation_id)
            yield {"error": "Stream interrupted. Please try again.", "code": "stream_error"}
