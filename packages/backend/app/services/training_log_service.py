"""Structured RAG interaction logging for future model training datasets."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import uuid
from dataclasses import dataclass
from typing import Any, Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.engine import SessionLocal
from app.db.models import TrainingChunkFeedback, TrainingRagInteraction
from app.schemas.types import ChatMessageDict


logger = logging.getLogger(__name__)

ScopeType = Literal["single_pdf", "collection"]

_COLLECTION_CITATION_RE = re.compile(r"\[([^\[\],]+?)\s*,\s*p\.\s*(\d+)\]", re.I)
_SINGLE_PDF_CITATION_RE = re.compile(r"\[p\.\s*(\d+)\]", re.I)


@dataclass(frozen=True)
class TrainingLogContext:
    user_id: uuid.UUID
    conversation_id: uuid.UUID
    user_message_id: uuid.UUID
    query_text: str
    query_embedding: list[float] | None
    embedding_model: str
    embedding_dimensions: int
    scope_type: ScopeType
    pdf_id: uuid.UUID | None
    collection_id: uuid.UUID | None
    retrieved_chunks: list[dict[str, Any]]
    retrieval_top_k: int
    retrieval_config: dict[str, Any]
    prompt_context: str
    system_prompt: str
    prompt_messages: list[ChatMessageDict]
    llm_provider: str
    llm_model: str
    generation_config: dict[str, Any]
    training_eligible: bool = False
    consent_version: str | None = None


def hash_system_prompt(system_prompt: str) -> str:
    return hashlib.sha256(system_prompt.encode("utf-8")).hexdigest()


def _uuid_or_none(value: Any) -> uuid.UUID | None:
    if value is None:
        return None
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError):
        return None


def _normalise_title(value: str | None) -> str:
    if not value:
        return ""
    return " ".join(re.findall(r"[a-z0-9]+", value.lower()))


def _title_matches(citation_title: str | None, pdf_title: str | None) -> bool:
    citation = _normalise_title(citation_title)
    title = _normalise_title(pdf_title)
    if not citation or not title:
        return False
    if citation in title or title in citation:
        return True
    citation_words = set(citation.split())
    title_words = set(title.split())
    if not citation_words or not title_words:
        return False
    return len(citation_words & title_words) / len(citation_words) >= 0.5


def _page_in_chunk(page: int, chunk: dict[str, Any]) -> bool:
    start = int(chunk["page_number"])
    end = chunk.get("end_page_number") or start
    return start <= page <= int(end)


def _find_matching_chunks(
    *,
    page: int,
    citation_title: str | None,
    scope_type: ScopeType,
    retrieved_chunks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    matches = []
    for chunk in retrieved_chunks:
        if not chunk.get("chunk_id") or not _page_in_chunk(page, chunk):
            continue
        if scope_type == "collection" and not _title_matches(
            citation_title, chunk.get("pdf_title")
        ):
            continue
        matches.append(chunk)
    return matches


def _overlaps(span: tuple[int, int], spans: list[tuple[int, int]]) -> bool:
    start, end = span
    return any(
        start < existing_end and end > existing_start
        for existing_start, existing_end in spans
    )


def extract_citation_events(
    assistant_reply: str,
    retrieved_chunks: list[dict[str, Any]],
    scope_type: ScopeType,
) -> list[dict[str, Any]]:
    """Extract citation events and conservatively map them to retrieved chunks."""
    events: list[dict[str, Any]] = []
    collection_spans: list[tuple[int, int]] = []

    def add_event(raw: str, page: int, title: str | None) -> None:
        matches = _find_matching_chunks(
            page=page,
            citation_title=title,
            scope_type=scope_type,
            retrieved_chunks=retrieved_chunks,
        )
        matched_chunk_ids = [str(chunk["chunk_id"]) for chunk in matches]
        if len(matches) == 1:
            status = "matched"
        elif len(matches) > 1:
            status = "ambiguous"
        else:
            status = "unmatched"
        events.append(
            {
                "raw": raw,
                "page": page,
                "title": title,
                "matched_chunk_ids": matched_chunk_ids,
                "status": status,
                "citation_rank": len(events) + 1,
            }
        )

    for match in _COLLECTION_CITATION_RE.finditer(assistant_reply):
        collection_spans.append(match.span())
        add_event(
            raw=match.group(0),
            page=int(match.group(2)),
            title=match.group(1).strip(),
        )

    for match in _SINGLE_PDF_CITATION_RE.finditer(assistant_reply):
        if _overlaps(match.span(), collection_spans):
            continue
        add_event(raw=match.group(0), page=int(match.group(1)), title=None)

    return events


def citation_parse_status(events: list[dict[str, Any]]) -> str:
    if not events:
        return "no_citations"
    statuses = {str(event["status"]) for event in events}
    if "ambiguous" in statuses:
        return "ambiguous"
    if "unmatched" in statuses:
        return "partial"
    return "parsed"


def _first_matched_citation_by_chunk(
    events: list[dict[str, Any]],
) -> dict[uuid.UUID, dict[str, Any]]:
    matched: dict[uuid.UUID, dict[str, Any]] = {}
    for event in events:
        if event.get("status") != "matched":
            continue
        chunk_ids = event.get("matched_chunk_ids") or []
        if not chunk_ids:
            continue
        chunk_id = _uuid_or_none(chunk_ids[0])
        if chunk_id is not None and chunk_id not in matched:
            matched[chunk_id] = event
    return matched


class TrainingLogService:
    def __init__(self, session_factory=SessionLocal):
        self._session_factory = session_factory

    def schedule_interaction_log(
        self,
        context: TrainingLogContext | None,
        *,
        assistant_message_id: uuid.UUID,
        assistant_reply: str,
        latency_ms: int | None,
        token_count: int | None,
    ) -> asyncio.Task | None:
        if context is None or not settings.TRAINING_DATA_LOGGING_ENABLED:
            return None

        return asyncio.create_task(
            self._log_interaction_safely(
                context,
                assistant_message_id=assistant_message_id,
                assistant_reply=assistant_reply,
                latency_ms=latency_ms,
                token_count=token_count,
            )
        )

    async def _log_interaction_safely(
        self,
        context: TrainingLogContext,
        *,
        assistant_message_id: uuid.UUID,
        assistant_reply: str,
        latency_ms: int | None,
        token_count: int | None,
    ) -> None:
        try:
            async with self._session_factory() as db:
                try:
                    await self.log_interaction(
                        db,
                        context,
                        assistant_message_id=assistant_message_id,
                        assistant_reply=assistant_reply,
                        latency_ms=latency_ms,
                        token_count=token_count,
                    )
                except Exception:
                    await db.rollback()
                    raise
        except Exception:
            logger.exception(
                "Failed to log training data for conversation %s",
                context.conversation_id,
            )

    async def log_interaction(
        self,
        db: AsyncSession,
        context: TrainingLogContext,
        *,
        assistant_message_id: uuid.UUID,
        assistant_reply: str,
        latency_ms: int | None,
        token_count: int | None,
    ) -> TrainingRagInteraction:
        citation_events = extract_citation_events(
            assistant_reply,
            context.retrieved_chunks,
            context.scope_type,
        )
        matched_by_chunk = _first_matched_citation_by_chunk(citation_events)
        cited_chunk_ids = list(matched_by_chunk)
        cited_page_nums = list(
            dict.fromkeys(int(event["page"]) for event in citation_events)
        )

        interaction = TrainingRagInteraction(
            id=uuid.uuid4(),
            user_id=context.user_id,
            conversation_id=context.conversation_id,
            user_message_id=context.user_message_id,
            assistant_message_id=assistant_message_id,
            query_text=context.query_text,
            query_embedding=context.query_embedding,
            embedding_model=context.embedding_model,
            embedding_dimensions=context.embedding_dimensions,
            scope_type=context.scope_type,
            pdf_id=context.pdf_id,
            collection_id=context.collection_id,
            retrieved_chunks=context.retrieved_chunks,
            retrieval_top_k=context.retrieval_top_k,
            retrieval_config=context.retrieval_config,
            prompt_context=context.prompt_context,
            system_prompt=context.system_prompt,
            system_prompt_hash=hash_system_prompt(context.system_prompt),
            prompt_messages=list(context.prompt_messages),
            llm_model=context.llm_model,
            llm_provider=context.llm_provider,
            generation_config=context.generation_config,
            assistant_reply=assistant_reply,
            cited_chunk_ids=cited_chunk_ids or None,
            cited_page_nums=cited_page_nums or None,
            citation_events=citation_events,
            citation_parse_status=citation_parse_status(citation_events),
            latency_ms=latency_ms,
            token_count=token_count,
            training_eligible=context.training_eligible,
            consent_version=context.consent_version,
        )
        db.add(interaction)
        await db.flush()

        for chunk in context.retrieved_chunks:
            chunk_id = _uuid_or_none(chunk.get("chunk_id"))
            if chunk_id is None:
                continue
            citation_event = matched_by_chunk.get(chunk_id)
            db.add(
                TrainingChunkFeedback(
                    id=uuid.uuid4(),
                    interaction_id=interaction.id,
                    chunk_id=chunk_id,
                    retrieval_rank=int(chunk["retrieval_rank"]),
                    retrieval_score=float(chunk["retrieval_score"]),
                    included_in_prompt=bool(chunk.get("included_in_prompt", False)),
                    prompt_rank=chunk.get("prompt_rank"),
                    was_cited=citation_event is not None,
                    citation_rank=(
                        int(citation_event["citation_rank"])
                        if citation_event is not None
                        else None
                    ),
                    citation_text=(
                        str(citation_event["raw"])
                        if citation_event is not None
                        else None
                    ),
                )
            )

        await db.commit()
        return interaction


training_log_service = TrainingLogService()
