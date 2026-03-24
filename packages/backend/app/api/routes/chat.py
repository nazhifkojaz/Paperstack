"""Chat routes: conversations, SSE streaming, and semantic search."""
import json
import logging
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import case, delete, select, text as sql_text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.core.config import settings
from app.core.security import decrypt_token
from app.db.models import (
    Annotation,
    AnnotationSet,
    ChatConversation,
    ChatMessage,
    Pdf,
    PdfChunk,
    PdfIndexStatus,
    User,
    UserApiKey,
    UserUsageQuota,
)
from app.middleware.rate_limit import limiter
from app.services.chat_service import COLLECTION_SYSTEM_PROMPT
from app.services.llm_service import llm_service
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
from app.services.chat_service import chat_service
from app.services.chunking_service import chunk_text_with_pages
from app.services.embedding_service import embedding_service
from app.services.exceptions import EmbeddingError, IndexingError
from app.services.github_repo import download_pdf_to_tempfile
from app.services.text_extractor import extract_text_with_pages

logger = logging.getLogger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

STALE_INDEXING_MINUTES = 10


async def _resolve_chat_api_key(
    user: User, db: AsyncSession
) -> tuple[str, str, bool]:
    """Return (provider, api_key, is_in_house).

    Priority: user's stored key (openai > anthropic > gemini > glm) →
              in-house fallback (gemini or glm) subject to chat quota.
    """
    result = await db.execute(
        select(UserApiKey)
        .where(UserApiKey.user_id == user.id)
        .order_by(
            case(
                (UserApiKey.provider == "openai", 0),
                (UserApiKey.provider == "anthropic", 1),
                (UserApiKey.provider == "gemini", 2),
                (UserApiKey.provider == "glm", 3),
                else_=4,
            )
        )
    )
    user_keys = result.scalars().all()
    for key_row in user_keys:
        decrypted = decrypt_token(key_row.encrypted_key)
        logger.info(
            "Using user-provided %s key (ending ...%s) for user %s",
            key_row.provider, decrypted[-4:], user.id,
        )
        return key_row.provider, decrypted, False

    # In-house fallback — check chat quota
    quota_result = await db.execute(
        select(UserUsageQuota).where(UserUsageQuota.user_id == user.id)
    )
    quota_row = quota_result.scalar_one_or_none()
    if quota_row is None:
        quota_row = UserUsageQuota(user_id=user.id)
        db.add(quota_row)
        await db.flush()

    if quota_row.chat_uses_remaining <= 0:
        raise HTTPException(
            status_code=402,
            detail="Chat quota exhausted. Please add an API key.",
        )

    if settings.GEMINI_API_KEY:
        return "gemini", settings.GEMINI_API_KEY, True
    if settings.GLM_API_KEY:
        return "glm", settings.GLM_API_KEY, True

    raise HTTPException(status_code=503, detail="No LLM provider available.")


async def _get_or_create_index_status(
    pdf_id: uuid.UUID, user_id: uuid.UUID, db: AsyncSession
) -> PdfIndexStatus:
    """Return the PdfIndexStatus row, creating it with 'not_indexed' if absent."""
    result = await db.execute(
        select(PdfIndexStatus).where(
            PdfIndexStatus.pdf_id == pdf_id,
            PdfIndexStatus.user_id == user_id,
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        row = PdfIndexStatus(pdf_id=pdf_id, user_id=user_id, status="not_indexed")
        db.add(row)
        await db.flush()
    return row


async def _lazy_index_pdf(
    pdf_row: Pdf,
    user: User,
    index_status: PdfIndexStatus,
    db: AsyncSession,
) -> None:
    """Download, chunk, embed, and store chunks for a PDF.

    Sets index_status.status to 'indexed' on success, 'failed' on error.
    Caller must commit the session.
    """
    index_status.status = "indexing"
    index_status.updated_at = datetime.now(timezone.utc)
    await db.flush()

    tmp_path: Path | None = None
    try:
        # Download PDF
        if pdf_row.source_url and not pdf_row.github_sha:
            import httpx
            async with httpx.AsyncClient(follow_redirects=True, timeout=60) as client:
                resp = await client.get(pdf_row.source_url)
                if resp.status_code != 200:
                    raise IndexingError(f"Failed to download linked PDF: HTTP {resp.status_code}")
                tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
                try:
                    tmp.write(resp.content)
                    tmp.close()
                    tmp_path = Path(tmp.name)
                except Exception:
                    tmp.close()
                    Path(tmp.name).unlink(missing_ok=True)
                    raise
        else:
            tmp_path = await download_pdf_to_tempfile(
                user.access_token, user.github_login, pdf_row.filename
            )

        # Extract text
        with open(tmp_path, "rb") as f:
            text_with_pages, _total_pages, _pages_analyzed = extract_text_with_pages(f)

        if not text_with_pages.strip():
            raise IndexingError("PDF has no extractable text (may be image-only).")

        # Chunk
        chunks = chunk_text_with_pages(text_with_pages)
        if not chunks:
            raise IndexingError("No chunks produced from PDF text.")

        # Embed (batch)
        texts = [c.content for c in chunks]
        embeddings = await embedding_service.embed_texts(texts)

        # Delete stale chunks (retry scenario) and insert fresh ones
        await db.execute(
            delete(PdfChunk).where(
                PdfChunk.pdf_id == pdf_row.id,
                PdfChunk.user_id == user.id,
            )
        )

        for chunk, embedding in zip(chunks, embeddings):
            db.add(PdfChunk(
                pdf_id=pdf_row.id,
                user_id=user.id,
                chunk_index=chunk.chunk_index,
                page_number=chunk.page_number,
                content=chunk.content.replace('\x00', ''),
                embedding=embedding,
            ))

        now = datetime.now(timezone.utc)
        index_status.status = "indexed"
        index_status.chunk_count = len(chunks)
        index_status.indexed_at = now
        index_status.updated_at = now
        index_status.error_message = None

    except (EmbeddingError, IndexingError) as exc:
        index_status.status = "failed"
        index_status.error_message = str(exc)
        index_status.updated_at = datetime.now(timezone.utc)
        raise
    except Exception as exc:
        index_status.status = "failed"
        index_status.error_message = f"Unexpected error: {exc}"
        index_status.updated_at = datetime.now(timezone.utc)
        raise IndexingError(str(exc)) from exc
    finally:
        if tmp_path:
            tmp_path.unlink(missing_ok=True)


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

    # 2. Resolve API key
    provider, api_key, is_in_house = await _resolve_chat_api_key(current_user, db)

    # 3. Embed query
    try:
        query_vector = await embedding_service.embed_query(data.content)
    except EmbeddingError as exc:
        raise HTTPException(status_code=502, detail=f"Embedding failed: {exc}")

    # 4. PDF path: verify ownership, lazy-index if needed, single-PDF search
    #    Collection path: multi-PDF search across indexed collection chunks
    if conv.pdf_id is not None:
        pdf_result = await db.execute(
            select(Pdf).where(Pdf.id == conv.pdf_id, Pdf.user_id == current_user.id)
        )
        pdf_row = pdf_result.scalar_one_or_none()
        if not pdf_row:
            raise HTTPException(status_code=404, detail="PDF not found.")

        index_status = await _get_or_create_index_status(conv.pdf_id, current_user.id, db)

        if index_status.status == "indexing":
            stale_cutoff = datetime.now(timezone.utc) - timedelta(minutes=STALE_INDEXING_MINUTES)
            if index_status.updated_at and index_status.updated_at < stale_cutoff:
                index_status.status = "not_indexed"
                await db.flush()
            else:
                raise HTTPException(status_code=409, detail="PDF indexing is in progress. Please try again shortly.")

        if index_status.status == "failed":
            logger.info(
                "Resetting failed index status for pdf %s (user %s) to allow re-index retry",
                conv.pdf_id, current_user.id,
            )
            index_status.status = "not_indexed"
            index_status.error_message = None
            await db.flush()

        if index_status.status == "not_indexed":
            try:
                await _lazy_index_pdf(pdf_row, current_user, index_status, db)
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

    # 8. Save user message (and auto-title the conversation on first message)
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

    # 9. Build context_chunks payload for SSE done event
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

            # Decrement chat quota if using in-house key
            if is_in_house:
                from app.db.engine import SessionLocal
                async with SessionLocal() as quota_db:
                    quota_result = await quota_db.execute(
                        select(UserUsageQuota).where(UserUsageQuota.user_id == current_user.id)
                    )
                    quota_row = quota_result.scalar_one_or_none()
                    if quota_row:
                        quota_row.chat_uses_remaining = max(0, quota_row.chat_uses_remaining - 1)
                        await quota_db.commit()

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


async def _resolve_explain_api_key(
    user: User, db: AsyncSession
) -> tuple[str, str, bool]:
    """Return (provider, api_key, is_in_house) for explain calls.

    Same key priority as chat but checks explain_uses_remaining for in-house fallback.
    """
    result = await db.execute(
        select(UserApiKey)
        .where(UserApiKey.user_id == user.id)
        .order_by(
            case(
                (UserApiKey.provider == "openai", 0),
                (UserApiKey.provider == "anthropic", 1),
                (UserApiKey.provider == "gemini", 2),
                (UserApiKey.provider == "glm", 3),
                else_=4,
            )
        )
    )
    user_keys = result.scalars().all()
    for key_row in user_keys:
        decrypted = decrypt_token(key_row.encrypted_key)
        return key_row.provider, decrypted, False

    # In-house fallback — check explain quota
    quota_result = await db.execute(
        select(UserUsageQuota).where(UserUsageQuota.user_id == user.id)
    )
    quota_row = quota_result.scalar_one_or_none()
    if quota_row is None:
        quota_row = UserUsageQuota(user_id=user.id)
        db.add(quota_row)
        await db.flush()

    if quota_row.explain_uses_remaining <= 0:
        raise HTTPException(
            status_code=402,
            detail="Explain quota exhausted. Please add an API key in Settings.",
        )

    if settings.GEMINI_API_KEY:
        return "gemini", settings.GEMINI_API_KEY, True
    if settings.GLM_API_KEY:
        return "glm", settings.GLM_API_KEY, True

    raise HTTPException(status_code=503, detail="No LLM provider available.")


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

    # 3. Resolve LLM key (checks explain quota for in-house fallback)
    provider, api_key, is_in_house = await _resolve_explain_api_key(current_user, db)

    # 4. Lazy-index PDF if needed
    index_status = await _get_or_create_index_status(data.pdf_id, current_user.id, db)

    if index_status.status == "indexing":
        stale_cutoff = datetime.now(timezone.utc) - timedelta(minutes=STALE_INDEXING_MINUTES)
        if index_status.updated_at and index_status.updated_at < stale_cutoff:
            index_status.status = "not_indexed"
            await db.flush()
        else:
            raise HTTPException(
                status_code=409,
                detail="Indexing paper first, might take some time. Please try again shortly.",
            )

    if index_status.status == "failed":
        index_status.status = "not_indexed"
        index_status.error_message = None
        await db.flush()

    if index_status.status == "not_indexed":
        logger.info("explain: indexing pdf %s for user %s", data.pdf_id, current_user.id)
        try:
            await _lazy_index_pdf(pdf_row, current_user, index_status, db)
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
        quota_result = await db.execute(
            select(UserUsageQuota).where(UserUsageQuota.user_id == current_user.id)
        )
        quota_row = quota_result.scalar_one_or_none()
        if quota_row:
            quota_row.explain_uses_remaining = max(0, quota_row.explain_uses_remaining - 1)
            remaining = quota_row.explain_uses_remaining

    await db.commit()

    return ExplainResponse(
        explanation=explanation,
        note_content=final_note,
        explain_uses_remaining=remaining,
    )
