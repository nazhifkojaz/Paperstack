"""Chat routes: conversations, SSE streaming, and semantic search."""

import json
import logging
import uuid

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    get_current_user,
    get_db,
    get_llm_http_client,
    get_embedding_http_client,
)
from app.core.config import settings
from app.db.models import (
    Annotation,
    AnnotationSet,
    ChatConversation,
    ChatMessage,
    Citation,
    Pdf,
    User,
    UserLLMPreferences,
)
from app.middleware.rate_limit import limiter
from app.services.api_key_service import api_key_service
from app.services.chat_service import ChatService, COLLECTION_SYSTEM_PROMPT
from app.services.embedding_service import EmbeddingService
from app.services.exceptions import (
    ApiKeyNotFoundError,
    EmbeddingError,
    IndexInProgressError,
    IndexingError,
    LLMRateLimitError,
    OpenRouterQuotaError,
    QuotaExhaustedError,
)
from app.services.explain_service import ExplainService
from app.services.indexing_service import IndexingService
from app.services.llm_service import LLMService
from app.services.openrouter_usage_service import openrouter_usage_service
from app.services.pdf_download_service import pdf_download_service
from app.services.vector_search_service import vector_search_service
from app.schemas.chat import (
    ConversationCreate,
    ConversationResponse,
    ExplainRequest,
    ExplainResponse,
    MessageCreate,
    MessageResponse,
    SemanticSearchRequest,
    SemanticSearchResult,
)

logger = logging.getLogger(__name__)

router = APIRouter()




@router.post("/conversations", response_model=ConversationResponse, status_code=201)
@limiter.limit(settings.RATE_LIMIT_CHAT_CONVERSATIONS)
async def create_conversation(
    request: Request,
    data: ConversationCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new chat conversation scoped to a PDF or collection."""
    if data.pdf_id is None and data.collection_id is None:
        raise HTTPException(
            status_code=422, detail="Either pdf_id or collection_id is required."
        )

    conv = ChatConversation(
        user_id=current_user.id,
        pdf_id=data.pdf_id,
        collection_id=data.collection_id,
    )
    db.add(conv)
    await db.commit()
    await db.refresh(conv)
    return conv


@router.get("/conversations", response_model=list[ConversationResponse])
@limiter.limit(settings.RATE_LIMIT_CHAT_CONVERSATIONS)
async def list_conversations(
    request: Request,
    pdf_id: uuid.UUID | None = None,
    collection_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List conversations for the current user, filtered by pdf_id or collection_id."""
    q = select(ChatConversation).where(ChatConversation.user_id == current_user.id)
    if pdf_id is not None:
        q = q.where(ChatConversation.pdf_id == pdf_id)
    if collection_id is not None:
        q = q.where(ChatConversation.collection_id == collection_id)
    q = q.order_by(ChatConversation.updated_at.desc())
    result = await db.execute(q)
    return result.scalars().all()


@router.get(
    "/conversations/{conversation_id}/messages", response_model=list[MessageResponse]
)
@limiter.limit(settings.RATE_LIMIT_CHAT_CONVERSATIONS)
async def get_messages(
    request: Request,
    conversation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return full message history for a conversation."""
    conv_result = await db.execute(
        select(ChatConversation).where(
            ChatConversation.id == conversation_id,
            ChatConversation.user_id == current_user.id,
        )
    )
    if not conv_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Conversation not found.")

    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.conversation_id == conversation_id)
        .order_by(ChatMessage.created_at.asc())
    )
    messages = result.scalars().all()

    # Deserialise context_chunks JSONB into ContextChunkResponse-compatible dicts
    out = []
    for msg in messages:
        chunks = None
        if msg.context_chunks:
            chunks = [
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
                for c in msg.context_chunks
            ]
        out.append(
            MessageResponse(
                id=msg.id,
                role=msg.role,
                content=msg.content,
                context_chunks=chunks,
                created_at=msg.created_at,
            )
        )
    return out


@router.delete("/conversations/{conversation_id}", status_code=204)
@limiter.limit(settings.RATE_LIMIT_CHAT_CONVERSATIONS)
async def delete_conversation(
    request: Request,
    conversation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a conversation and all its messages."""
    result = await db.execute(
        select(ChatConversation).where(
            ChatConversation.id == conversation_id,
            ChatConversation.user_id == current_user.id,
        )
    )
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    await db.execute(
        delete(ChatConversation).where(ChatConversation.id == conversation_id)
    )
    await db.commit()




@router.post("/conversations/{conversation_id}/stream")
@limiter.limit(settings.RATE_LIMIT_CHAT_MESSAGE)
async def stream_message(
    request: Request,
    conversation_id: uuid.UUID,
    data: MessageCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    llm_client: httpx.AsyncClient = Depends(get_llm_http_client),
    embedding_client: httpx.AsyncClient = Depends(get_embedding_http_client),
):
    """Send a chat message and stream the assistant reply via SSE."""
    conv_result = await db.execute(
        select(ChatConversation).where(
            ChatConversation.id == conversation_id,
            ChatConversation.user_id == current_user.id,
        )
    )
    conv = conv_result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found.")


    chat_prefs_result = await db.execute(
        select(UserLLMPreferences.chat_model).where(
            UserLLMPreferences.user_id == current_user.id
        )
    )
    chat_preferred_model = chat_prefs_result.scalar_one_or_none()

    try:
        resolution = await api_key_service.resolve_for_chat(
            current_user, db, force_free_model=chat_preferred_model
        )
    except (QuotaExhaustedError, ApiKeyNotFoundError) as e:
        raise HTTPException(status_code=402, detail=str(e))
    provider = resolution.provider
    api_key = resolution.api_key
    is_in_house = resolution.is_in_house

    if is_in_house and provider == "openrouter":
        try:
            await openrouter_usage_service.record_and_check(db)
        except OpenRouterQuotaError as exc:
            raise HTTPException(status_code=503, detail=str(exc))

    # Quota decrement: OpenRouter (free) has no per-user quota.
    # BYOK users have unlimited usage. In-house paid tiers are gone.
    # No quota decrement needed anymore.

    embedding_svc = EmbeddingService(http_client=embedding_client)
    llm_svc = LLMService(http_client=llm_client)
    local_chat_service = ChatService(llm_service=llm_svc)
    local_indexing_service = IndexingService(
        download_service=pdf_download_service,
        embedding_service=embedding_svc,
    )

    try:
        query_vector = await embedding_svc.embed_query(data.content, db=db)
    except OpenRouterQuotaError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except EmbeddingError as exc:
        raise HTTPException(status_code=502, detail=f"Embedding failed: {exc}")

    # PDF path: verify ownership, lazy-index if needed, single-PDF search
    # Collection path: multi-PDF search across indexed collection chunks
    if conv.pdf_id is not None:
        pdf_result = await db.execute(
            select(Pdf).where(Pdf.id == conv.pdf_id, Pdf.user_id == current_user.id)
        )
        pdf_row = pdf_result.scalar_one_or_none()
        if not pdf_row:
            raise HTTPException(status_code=404, detail="PDF not found.")


        index_status = await local_indexing_service.get_or_create_status(
            str(conv.pdf_id), str(current_user.id), db
        )


        try:
            was_reset = await local_indexing_service.reset_if_stale(index_status, db)  # noqa: F841
        except IndexInProgressError as e:
            raise HTTPException(status_code=409, detail=str(e))


        if index_status.status == "failed":
            logger.info(
                "Resetting failed index status for pdf %s (user %s) to allow re-index retry",
                conv.pdf_id,
                current_user.id,
            )
            index_status.status = "not_indexed"
            index_status.error_message = None
            await db.flush()


        if index_status.status == "not_indexed":
            try:
                await local_indexing_service.index_pdf(
                    pdf_row, current_user, index_status, db
                )
                await db.commit()
            except (EmbeddingError, OpenRouterQuotaError, IndexingError) as exc:
                await db.commit()
                raise HTTPException(status_code=502, detail=f"Indexing failed: {exc}")

        top_chunks = await vector_search_service.search_pdf(
            query_vector=query_vector,
            pdf_id=conv.pdf_id,
            user_id=current_user.id,
            top_k=settings.CHAT_TOP_K_SINGLE_PDF,
            db=db,
            query_text=data.content,
        )
        context = local_chat_service.build_context(
            [{"page_number": c.page_number, "end_page_number": c.end_page_number, "content": c.content, "section_title": c.section_title} for c in top_chunks]
        )

        # Fetch citation metadata (authors, year) for this PDF
        paper_metadata = None
        citation_result = await db.execute(
            select(Citation).where(
                Citation.pdf_id == conv.pdf_id,
                Citation.user_id == current_user.id,
            )
        )
        citation_row = citation_result.scalar_one_or_none()
        if citation_row:
            paper_metadata = {
                "title": pdf_row.title,
                "authors": citation_row.authors,
                "year": citation_row.year,
            }
        elif pdf_row.title:
            paper_metadata = {"title": pdf_row.title}
    else:
        # Collection chat: search across all indexed PDFs in the collection
        if conv.collection_id is None:
            raise HTTPException(
                status_code=422,
                detail="Conversation has neither pdf_id nor collection_id.",
            )

        top_chunks = await vector_search_service.search_collection(
            query_vector=query_vector,
            collection_id=conv.collection_id,
            user_id=current_user.id,
            top_k=settings.CHAT_TOP_K_COLLECTION,
            db=db,
            query_text=data.content,
        )
        if not top_chunks:
            raise HTTPException(
                status_code=422,
                detail="No indexed PDFs found in this collection. Open each PDF in the viewer and send a message to index it first.",
            )
        context_parts = []
        for c in top_chunks:
            end_page = getattr(c, "end_page_number", None)
            if end_page and end_page > c.page_number:
                page_label = f"Pages {c.page_number}-{end_page}"
            else:
                page_label = f"Page {c.page_number}"
            context_parts.append(f"[{c.pdf_title}, {page_label}]\n{c.content}")
        context = "\n\n---\n\n".join(context_parts)

        # Fetch citation metadata for all unique PDFs in the collection results
        unique_pdf_ids = {c.pdf_id for c in top_chunks if c.pdf_id}
        paper_metadata = None
        if unique_pdf_ids:
            citation_rows = await db.execute(
                select(Citation).where(
                    Citation.pdf_id.in_(unique_pdf_ids),
                    Citation.user_id == current_user.id,
                )
            )
            citation_by_pdf = {
                str(c.pdf_id): c for c in citation_rows.scalars().all()
            }
            seen_titles = set()
            metadata_list = []
            for c in top_chunks:
                if not c.pdf_id or c.pdf_title in seen_titles:
                    continue
                seen_titles.add(c.pdf_title)
                entry: dict = {"title": c.pdf_title}
                cit = citation_by_pdf.get(str(c.pdf_id))
                if cit:
                    if cit.authors:
                        entry["authors"] = cit.authors
                    if cit.year:
                        entry["year"] = cit.year
                metadata_list.append(entry)
            if metadata_list:
                paper_metadata = metadata_list

    history_result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.conversation_id == conversation_id)
        .order_by(ChatMessage.created_at.asc())
    )
    history = [
        {"role": m.role, "content": m.content} for m in history_result.scalars().all()
    ]
    system_prompt, messages = local_chat_service.build_messages(
        context,
        history,
        data.content,
        base_prompt=COLLECTION_SYSTEM_PROMPT if conv.collection_id else None,
        paper_metadata=paper_metadata,
    )


    user_msg = ChatMessage(
        conversation_id=conversation_id,
        role="user",
        content=data.content,
    )
    db.add(user_msg)
    if not conv.title:
        truncated = data.content.strip()
        conv.title = truncated[:60] + ("…" if len(truncated) > 60 else "")
    await db.commit()


    context_chunks_payload = [
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

    async def event_stream():
        full_reply = []
        assistant_message_id = str(uuid.uuid4())
        try:
            try:
                async for token in local_chat_service.stream_reply(
                    system_prompt, messages, provider, api_key,
                    model=resolution.model,
                ):
                    full_reply.append(token)
                    yield f"data: {json.dumps({'token': token})}\n\n"
            except LLMRateLimitError:
                yield f"data: {json.dumps({'error': 'Free tier rate limited. Please try again later or use your own API key.', 'code': 'rate_limited'})}\n\n"
                return

            # Persist assistant message synchronously before sending `done`.
            # Saving as a background task (after the response is sent) created a race
            # condition: if the user sent a second message before the task ran, the
            # backend fetched history without the assistant reply and passed an invalid
            # conversation thread to the LLM.
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

            yield f"data: {json.dumps({'done': True, 'message_id': assistant_message_id, 'context_chunks': context_chunks_payload})}\n\n"

        except Exception as exc:
            logger.exception("Streaming error for conversation %s", conversation_id)
            yield f"data: {json.dumps({'error': str(exc), 'code': 'stream_error'})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )




@router.post("/semantic-search", response_model=list[SemanticSearchResult])
@limiter.limit(settings.RATE_LIMIT_SEMANTIC_SEARCH)
async def semantic_search(
    request: Request,
    data: SemanticSearchRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    embedding_client: httpx.AsyncClient = Depends(get_embedding_http_client),
):
    """Search across indexed PDFs using semantic similarity."""
    try:
        embedding_svc = EmbeddingService(http_client=embedding_client)
        query_vector = await embedding_svc.embed_query(data.query, db=db)
    except OpenRouterQuotaError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except EmbeddingError as exc:
        raise HTTPException(status_code=502, detail=f"Embedding failed: {exc}")

    if data.collection_id is not None:
        results = await vector_search_service.search_collection(
            query_vector=query_vector,
            collection_id=data.collection_id,
            user_id=current_user.id,
            top_k=data.limit * 3,  # over-fetch for dedup
            db=db,
            query_text=data.query,
        )
    else:
        results = await vector_search_service.search_all(
            query_vector=query_vector,
            user_id=current_user.id,
            limit=data.limit,
            db=db,
            query_text=data.query,
        )

    # Convert SearchResult to SemanticSearchResult
    return [
        SemanticSearchResult(
            pdf_id=uuid.UUID(r.pdf_id) if r.pdf_id else None,
            pdf_title=r.pdf_title or "",
            page_number=r.page_number,
            snippet=r.content[:300] if r.content else "",
            score=r.score,
        )
        for r in results
    ]




@router.post("/explain", response_model=ExplainResponse)
@limiter.limit(settings.RATE_LIMIT_CHAT_EXPLAIN)
async def explain_annotation(
    request: Request,
    data: ExplainRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    llm_client: httpx.AsyncClient = Depends(get_llm_http_client),
    embedding_client: httpx.AsyncClient = Depends(get_embedding_http_client),
):
    """Explain a highlighted passage using RAG and save the explanation as an annotation note."""
    # Verify annotation ownership (join through annotation_sets for user_id check)
    ann_result = await db.execute(
        select(Annotation, AnnotationSet)
        .join(AnnotationSet, Annotation.set_id == AnnotationSet.id)
        .where(
            Annotation.id == data.annotation_id,
            AnnotationSet.user_id == current_user.id,
        )
    )
    row = ann_result.first()
    if not row:
        raise HTTPException(status_code=404, detail="Annotation not found.")
    annotation, _ = row
    existing_note_content = (
        annotation.note_content
    )  # capture before any intermediate commit

    pdf_result = await db.execute(
        select(Pdf).where(Pdf.id == data.pdf_id, Pdf.user_id == current_user.id)
    )
    pdf_row = pdf_result.scalar_one_or_none()
    if not pdf_row:
        raise HTTPException(status_code=404, detail="PDF not found.")


    explain_prefs_result = await db.execute(
        select(UserLLMPreferences.explain_model).where(
            UserLLMPreferences.user_id == current_user.id
        )
    )
    explain_preferred_model = explain_prefs_result.scalar_one_or_none()

    try:
        resolution = await api_key_service.resolve_for_explain(
            current_user, db, force_free_model=explain_preferred_model
        )
    except (QuotaExhaustedError, ApiKeyNotFoundError) as e:
        raise HTTPException(status_code=402, detail=str(e))
    provider = resolution.provider
    api_key = resolution.api_key
    is_in_house = resolution.is_in_house

    if is_in_house and provider == "openrouter":
        try:
            await openrouter_usage_service.record_and_check(db)
        except OpenRouterQuotaError as exc:
            raise HTTPException(status_code=503, detail=str(exc))

    # Use explain_service for RAG pipeline (indexing, embedding, search, LLM)
    embedding_svc = EmbeddingService(http_client=embedding_client)
    llm_svc = LLMService(http_client=llm_client)
    local_explain_service = ExplainService(
        embedding_service=embedding_svc,
        llm_service=llm_svc,
    )

    try:
        result = await local_explain_service.explain_with_provider(
            selected_text=data.selected_text,
            page_number=data.page_number,
            pdf_row=pdf_row,
            user=current_user,
            provider=provider,
            api_key=api_key,
            db=db,
            model=resolution.model,
        )
    except LLMRateLimitError:
        raise HTTPException(status_code=429, detail="Free tier rate limited. Please try again later or use your own API key.")
    except IndexInProgressError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except OpenRouterQuotaError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except (EmbeddingError, IndexingError) as exc:
        raise HTTPException(status_code=502, detail=f"Explanation failed: {exc}")

    final_note = (
        f"{existing_note_content}\n\n{result.note_content}"
        if existing_note_content
        else result.note_content
    )
    annotation.note_content = final_note

    # OpenRouter (free) has no per-user quota. BYOK = unlimited.
    remaining = -1  # signals unlimited

    await db.commit()

    return ExplainResponse(
        explanation=result.explanation,
        note_content=final_note,
        explain_uses_remaining=remaining,
    )
