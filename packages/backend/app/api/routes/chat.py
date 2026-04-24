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
    resolve_api_key_with_quota,
)
from app.core.config import settings
from app.db.models import (
    Annotation,
    AnnotationSet,
    ChatConversation,
    ChatMessage,
    Pdf,
    User,
)
from app.middleware.rate_limit import limiter
from app.services.chat_orchestrator import ChatOrchestrator
from app.services.embedding_service import EmbeddingService
from app.services.exceptions import (
    EmbeddingError,
    IndexInProgressError,
    IndexingError,
    LLMRateLimitError,
    OpenRouterQuotaError,
)
from app.services.explain_service import ExplainService
from app.services.llm_service import LLMService
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

    resolution = await resolve_api_key_with_quota(current_user, db, "chat")

    embedding_svc = EmbeddingService(http_client=embedding_client)
    llm_svc = LLMService(http_client=llm_client)
    orchestrator = ChatOrchestrator(
        embedding_service=embedding_svc,
        llm_service=llm_svc,
    )

    # Prepare RAG context (embedding, indexing, vector search, citations)
    try:
        prepared = await orchestrator.prepare_context(
            query=data.content,
            pdf_id=conv.pdf_id,
            collection_id=conv.collection_id,
            user=current_user,
            db=db,
        )
    except OpenRouterQuotaError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except EmbeddingError as exc:
        raise HTTPException(status_code=502, detail=f"Embedding failed: {exc}")
    except IndexInProgressError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except (EmbeddingError, OpenRouterQuotaError, IndexingError) as exc:
        raise HTTPException(status_code=502, detail=f"Indexing failed: {exc}")
    except ValueError as exc:
        msg = str(exc)
        if msg == "PDF not found.":
            raise HTTPException(status_code=404, detail=msg)
        raise HTTPException(status_code=422, detail=msg)

    # Fetch history
    history_result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.conversation_id == conversation_id)
        .order_by(ChatMessage.created_at.asc())
    )
    history = [
        {"role": m.role, "content": m.content} for m in history_result.scalars().all()
    ]

    # Build LLM messages
    prepared_msgs = await orchestrator.build_messages(
        context=prepared.context,
        history=history,
        user_message=data.content,
        collection_id=conv.collection_id,
        paper_metadata=prepared.paper_metadata,
    )

    # Persist user message
    await orchestrator.persist_user_message(
        conversation_id=conversation_id,
        content=data.content,
        conv=conv,
        db=db,
    )

    # Stream response
    async def event_stream():
        async for event in orchestrator.stream_and_save(
            system_prompt=prepared_msgs.system_prompt,
            messages=prepared_msgs.messages,
            provider=resolution.provider,
            api_key=resolution.api_key,
            model=resolution.model,
            conversation_id=conversation_id,
            context_chunks_payload=prepared.context_chunks_payload,
            db=db,
        ):
            yield f"data: {json.dumps(event)}\n\n"

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


    resolution = await resolve_api_key_with_quota(current_user, db, "explain")
    provider = resolution.provider
    api_key = resolution.api_key

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
