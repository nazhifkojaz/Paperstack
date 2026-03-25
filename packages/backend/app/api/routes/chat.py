"""Chat routes: conversations, SSE streaming, and semantic search."""
import json
import logging
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select, text as sql_text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.core.config import settings
from app.db.models import (
    Annotation,
    AnnotationSet,
    ChatConversation,
    ChatMessage,
    Pdf,
    PdfChunk,
    PdfIndexStatus,
    User,
)
from app.middleware.rate_limit import limiter
from app.services.api_key_service import QuotaType, api_key_service
from app.services.chat_service import COLLECTION_SYSTEM_PROMPT, chat_service
from app.services.embedding_service import embedding_service
from app.services.exceptions import (
    ApiKeyNotFoundError,
    EmbeddingError,
    IndexInProgressError,
    IndexingError,
    QuotaExhaustedError,
)
from app.services.indexing_service import STALE_INDEXING_MINUTES, get_indexing_service
from app.services.llm_service import llm_service
from app.services.pdf_download_service import pdf_download_service
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

# Initialize indexing service with download service
indexing_service = get_indexing_service(pdf_download_service)


# ---------------------------------------------------------------------------
# Vector Search Helpers
# ---------------------------------------------------------------------------

async def _vector_search(
    query_vector: list[float],
    pdf_id: uuid.UUID,
    user_id: uuid.UUID,
    top_k: int,
    db: AsyncSession,
) -> list[dict]:
    """Return top-k chunks for a single PDF."""
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
        {
            "chunk_id": str(r.id),
            "page_number": r.page_number,
            "content": r.content,
            "score": float(r.score),
        }
        for r in rows
    ]


async def _vector_search_collection(
    query_vector: list[float],
    collection_id: uuid.UUID,
    user_id: uuid.UUID,
    top_k: int,
    db: AsyncSession,
) -> list[dict]:
    """Return top-k chunks across all indexed PDFs in a collection."""
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
        {
            "chunk_id": str(r.id),
            "pdf_id": str(r.pdf_id),
            "pdf_title": r.pdf_title,
            "page_number": r.page_number,
            "content": r.content,
            "score": r.score,
        }
        for r in rows
    ]


async def _vector_search(
    query_vector: list[float],
    pdf_id: uuid.UUID,
    user_id: uuid.UUID,
    top_k: int,
    db: AsyncSession,
) -> list[dict]:
    """Return top-k chunks for a single PDF ordered by cosine similarity."""
    vec_str = f"[{','.join(str(x) for x in query_vector)}]"
    rows = await db.execute(
        sql_text("""
            SELECT id, page_number, content,
                   1 - (embedding <=> CAST(:vec AS vector)) AS score
            FROM pdf_chunks
            WHERE pdf_id = :pdf_id AND user_id = :user_id
            ORDER BY embedding <=> CAST(:vec AS vector)
            LIMIT :k
        """),
        {
            "vec": vec_str,
            "pdf_id": str(pdf_id),
            "user_id": str(user_id),
            "k": top_k,
        },
    )
    return [
        {"chunk_id": str(r.id), "page_number": r.page_number, "content": r.content, "score": r.score}
        for r in rows
    ]


async def _save_assistant_message(
    conversation_id: uuid.UUID,
    content: str,
    context_chunks: list[dict],
) -> None:
    """Persist the completed assistant message (called as a background task)."""
    from app.db.engine import SessionLocal
    async with SessionLocal() as bg_db:
        msg = ChatMessage(
            conversation_id=conversation_id,
            role="assistant",
            content=content,
            context_chunks=[
                {
                    "chunk_id": c["chunk_id"],
                    "page_number": c["page_number"],
                    "snippet": c["content"][:200],
                    **({"pdf_id": c["pdf_id"], "pdf_title": c["pdf_title"]} if c.get("pdf_id") else {}),
                }
                for c in context_chunks
            ],
        )
        bg_db.add(msg)
        await bg_db.commit()


# ---------------------------------------------------------------------------
# Conversation endpoints
# ---------------------------------------------------------------------------

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
        raise HTTPException(status_code=422, detail="Either pdf_id or collection_id is required.")

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


@router.get("/conversations/{conversation_id}/messages", response_model=list[MessageResponse])
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
                    "snippet": c["snippet"],
                    **({"pdf_id": c["pdf_id"], "pdf_title": c["pdf_title"]} if c.get("pdf_id") else {}),
                }
                for c in msg.context_chunks
            ]
        out.append(MessageResponse(
            id=msg.id,
            role=msg.role,
            content=msg.content,
            context_chunks=chunks,
            created_at=msg.created_at,
        ))
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
    await db.execute(delete(ChatConversation).where(ChatConversation.id == conversation_id))
    await db.commit()


# ---------------------------------------------------------------------------
# Streaming endpoint
# ---------------------------------------------------------------------------

@router.post("/conversations/{conversation_id}/stream")
@limiter.limit(settings.RATE_LIMIT_CHAT_MESSAGE)
async def stream_message(
    request: Request,
    conversation_id: uuid.UUID,
    data: MessageCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Send a chat message and stream the assistant reply via SSE."""
    # 1. Verify conversation ownership
    conv_result = await db.execute(
        select(ChatConversation).where(
            ChatConversation.id == conversation_id,
            ChatConversation.user_id == current_user.id,
        )
    )
    conv = conv_result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found.")

    # 2. Resolve API key using service
    try:
        resolution = await api_key_service.resolve_for_chat(current_user, db)
    except (QuotaExhaustedError, ApiKeyNotFoundError) as e:
        raise HTTPException(status_code=402, detail=str(e))
    provider = resolution.provider
    api_key = resolution.api_key
    is_in_house = resolution.is_in_house

    # 3. Decrement quota BEFORE streaming (optimistic decrement)
    # This fixes the bug where quota decrement in a generator can be lost
    if is_in_house:
        background_tasks.add_task(
            api_key_service.decrement_quota,
            str(current_user.id),
            QuotaType.CHAT,
            db,
        )

    # 4. Embed query
    try:
        query_vector = await embedding_service.embed_query(data.content)
    except EmbeddingError as exc:
        raise HTTPException(status_code=502, detail=f"Embedding failed: {exc}")

    # 5. PDF path: verify ownership, lazy-index if needed, single-PDF search
    #    Collection path: multi-PDF search across indexed collection chunks
    if conv.pdf_id is not None:
        pdf_result = await db.execute(
            select(Pdf).where(Pdf.id == conv.pdf_id, Pdf.user_id == current_user.id)
        )
        pdf_row = pdf_result.scalar_one_or_none()
        if not pdf_row:
            raise HTTPException(status_code=404, detail="PDF not found.")

        # Get or create index status
        index_status = await indexing_service.get_or_create_index_status(
            str(conv.pdf_id), str(current_user.id), db
        )

        # Handle stale/active indexing
        try:
            was_reset = await indexing_service.reset_if_stale(index_status, db)
        except IndexInProgressError as e:
            raise HTTPException(status_code=409, detail=str(e))

        # Handle failed indexing
        if index_status.status == "failed":
            logger.info(
                "Resetting failed index status for pdf %s (user %s) to allow re-index retry",
                conv.pdf_id, current_user.id,
            )
            index_status.status = "not_indexed"
            index_status.error_message = None
            await db.flush()

        # Lazy index if needed
        if index_status.status == "not_indexed":
            try:
                await indexing_service.index_pdf(pdf_row, current_user, index_status, db)
                await db.commit()
            except (EmbeddingError, IndexingError) as exc:
                await db.commit()
                raise HTTPException(status_code=502, detail=f"Indexing failed: {exc}")

        top_chunks = await _vector_search(query_vector, conv.pdf_id, current_user.id, top_k=6, db=db)
        context = chat_service.build_context(
            [{"page_number": c["page_number"], "content": c["content"]} for c in top_chunks]
        )
    else:
        # Collection chat: search across all indexed PDFs in the collection
        if conv.collection_id is None:
            raise HTTPException(status_code=422, detail="Conversation has neither pdf_id nor collection_id.")

        top_chunks = await _vector_search_collection(
            query_vector, conv.collection_id, current_user.id, top_k=8, db=db
        )
        if not top_chunks:
            raise HTTPException(
                status_code=422,
                detail="No indexed PDFs found in this collection. Open each PDF in the viewer and send a message to index it first.",
            )
        context_parts = [
            f"[{c['pdf_title']}, Page {c['page_number']}]\n{c['content']}"
            for c in top_chunks
        ]
        context = "\n\n---\n\n".join(context_parts)

    history_result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.conversation_id == conversation_id)
        .order_by(ChatMessage.created_at.asc())
    )
    history = [{"role": m.role, "content": m.content} for m in history_result.scalars().all()]
    system_prompt, messages = chat_service.build_messages(
        context, history, data.content,
        base_prompt=COLLECTION_SYSTEM_PROMPT if conv.collection_id else None,
    )

    # 6. Save user message (and auto-title the conversation on first message)
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

    # 7. Build context_chunks payload for SSE done event
    context_chunks_payload = [
        {
            "chunk_id": c["chunk_id"],
            "page_number": c["page_number"],
            "snippet": c["content"][:200],
            **({"pdf_id": c["pdf_id"], "pdf_title": c["pdf_title"]} if c.get("pdf_id") else {}),
        }
        for c in top_chunks
    ]

    async def event_stream():
        full_reply = []
        assistant_message_id = str(uuid.uuid4())
        try:
            async for token in chat_service.stream_reply(system_prompt, messages, provider, api_key):
                full_reply.append(token)
                yield f"data: {json.dumps({'token': token})}\n\n"

            # Persist assistant message via background task
            background_tasks.add_task(
                _save_assistant_message,
                conversation_id,
                "".join(full_reply),
                top_chunks,
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


# ---------------------------------------------------------------------------
# Semantic search
# ---------------------------------------------------------------------------

@router.post("/semantic-search", response_model=list[SemanticSearchResult])
@limiter.limit(settings.RATE_LIMIT_SEMANTIC_SEARCH)
async def semantic_search(
    request: Request,
    data: SemanticSearchRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Search across indexed PDFs using semantic similarity."""
    try:
        query_vector = await embedding_service.embed_query(data.query)
    except EmbeddingError as exc:
        raise HTTPException(status_code=502, detail=f"Embedding failed: {exc}")

    vec_str = f"[{','.join(str(x) for x in query_vector)}]"

    if data.collection_id is not None:
        rows = await db.execute(
            sql_text("""
                SELECT pc.pdf_id, p.title AS pdf_title, pc.page_number, pc.content,
                       1 - (pc.embedding <=> CAST(:vec AS vector)) AS score
                FROM pdf_chunks pc
                JOIN pdfs p ON p.id = pc.pdf_id
                JOIN pdf_collections pcol ON pcol.pdf_id = pc.pdf_id
                WHERE pc.user_id = :user_id
                  AND pcol.collection_id = :collection_id
                ORDER BY pc.embedding <=> CAST(:vec AS vector)
                LIMIT :limit
            """),
            {
                "vec": vec_str,
                "user_id": str(current_user.id),
                "collection_id": str(data.collection_id),
                "limit": data.limit * 3,  # over-fetch to allow dedup by pdf_id
            },
        )
    else:
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
                "user_id": str(current_user.id),
                "limit": data.limit * 3,
            },
        )

    # Deduplicate: keep best-scoring chunk per PDF
    seen: dict[str, SemanticSearchResult] = {}
    for r in rows:
        pdf_id_str = str(r.pdf_id)
        if pdf_id_str not in seen:
            seen[pdf_id_str] = SemanticSearchResult(
                pdf_id=r.pdf_id,
                pdf_title=r.pdf_title,
                page_number=r.page_number,
                snippet=r.content[:300],
                score=r.score,
            )
        if len(seen) >= data.limit:
            break

    return list(seen.values())


# ---------------------------------------------------------------------------
# Explain annotation
# ---------------------------------------------------------------------------

EXPLAIN_SYSTEM_PROMPT = (
    "You are a research assistant. Explain the following highlighted passage "
    "from an academic paper in clear, concise language. "
    "Use the context excerpts provided to enrich your explanation — include why "
    "the passage matters and how it connects to the paper's broader argument. "
    "Keep the explanation under 200 words. Use plain language. "
    "You may use **bold** for key terms. Cite page numbers as [p.N] when relevant."
)


# ---------------------------------------------------------------------------
# Explain endpoint
# ---------------------------------------------------------------------------

@router.post("/explain", response_model=ExplainResponse)
@limiter.limit(settings.RATE_LIMIT_CHAT_EXPLAIN)
async def explain_annotation(
    request: Request,
    data: ExplainRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Explain a highlighted passage using RAG and save the explanation as an annotation note."""
    # 1. Verify annotation ownership (join through annotation_sets for user_id check)
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
    existing_note_content = annotation.note_content  # capture before any intermediate commit

    # 2. Verify PDF ownership
    pdf_result = await db.execute(
        select(Pdf).where(Pdf.id == data.pdf_id, Pdf.user_id == current_user.id)
    )
    pdf_row = pdf_result.scalar_one_or_none()
    if not pdf_row:
        raise HTTPException(status_code=404, detail="PDF not found.")

    # 3. Resolve LLM key using service
    try:
        resolution = await api_key_service.resolve_for_explain(current_user, db)
    except (QuotaExhaustedError, ApiKeyNotFoundError) as e:
        raise HTTPException(status_code=402, detail=str(e))
    provider = resolution.provider
    api_key = resolution.api_key
    is_in_house = resolution.is_in_house

    # 4. Lazy-index PDF if needed
    index_status = await indexing_service.get_or_create_index_status(
        str(data.pdf_id), str(current_user.id), db
    )

    # Handle stale/active indexing
    try:
        was_reset = await indexing_service.reset_if_stale(index_status, db)
    except IndexInProgressError as e:
        raise HTTPException(
            status_code=409,
            detail="Indexing paper first, might take some time. Please try again shortly.",
        )

    # Handle failed indexing
    if index_status.status == "failed":
        index_status.status = "not_indexed"
        index_status.error_message = None
        await db.flush()

    # Lazy index if needed
    if index_status.status == "not_indexed":
        logger.info("explain: indexing pdf %s for user %s", data.pdf_id, current_user.id)
        try:
            await indexing_service.index_pdf(pdf_row, current_user, index_status, db)
            await db.commit()
            await db.refresh(annotation)  # re-attach after commit expiry
            logger.info("explain: indexing complete for pdf %s", data.pdf_id)
        except (EmbeddingError, IndexingError) as exc:
            logger.exception("explain: indexing failed for pdf %s: %s", data.pdf_id, exc)
            await db.commit()
            raise HTTPException(status_code=502, detail=f"Indexing failed: {exc}")

    # 5. Embed selected text as query vector
    try:
        query_vector = await embedding_service.embed_query(data.selected_text)
    except EmbeddingError as exc:
        raise HTTPException(status_code=502, detail=f"Embedding failed: {exc}")

    # 6. Vector search for context (top 4 — tighter query than chat's 6)
    top_chunks = await _vector_search(query_vector, data.pdf_id, current_user.id, top_k=4, db=db)
    context = chat_service.build_context(
        [{"page_number": c["page_number"], "content": c["content"]} for c in top_chunks]
    )

    # 7. Build prompt and call LLM (non-streaming)
    system_prompt = EXPLAIN_SYSTEM_PROMPT + "\n\n## Context from the paper:\n\n" + context
    user_message = (
        f'Explain this passage from page {data.page_number}:\n\n'
        f'"{data.selected_text}"'
    )

    try:
        call_method = getattr(llm_service, f"call_{provider}")
        explanation = await call_method(system_prompt, user_message, api_key)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"LLM call failed: {str(exc)}")

    # 8. Append explanation to annotation note_content
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    new_block = f"[AI Explanation — {timestamp}]\n{explanation}"
    final_note = (
        f"{existing_note_content}\n\n{new_block}"
        if existing_note_content
        else new_block
    )
    annotation.note_content = final_note

    # 9. Decrement explain quota if using in-house key
    remaining = -1  # -1 signals unlimited (own API key)
    if is_in_house:
        remaining = await api_key_service.decrement_quota(
            str(current_user.id), QuotaType.EXPLAIN, db
        )

    await db.commit()

    return ExplainResponse(
        explanation=explanation,
        note_content=final_note,
        explain_uses_remaining=remaining,
    )
