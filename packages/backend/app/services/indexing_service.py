"""PDF indexing service for managing index status and coordinating indexing workflow.

This service handles:
1. Index status management (get, create, stale detection)
2. Full indexing workflow (download → extract → chunk → embed)
3. Retry logic for failed indexes
4. Lazy indexing (index on demand when needed)

Services raise custom exceptions. Route handlers translate to HTTP status codes.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Pdf, PdfChunk, PdfIndexStatus, User
from app.services.chunking_service import chunk_text_with_pages
from app.services.embedding_service import EmbeddingService
from app.services.exceptions import (
    ChunkingError,
    EmbeddingError,
    IndexInProgressError,
    IndexingError,
    OpenRouterQuotaError,
    TextExtractionError,
)
from app.services.pdf_download_service import PdfDownloadService, PdfSource
from app.services.storage.factory import get_storage_backend
from app.services.text_extractor import extract_text_with_pages, validate_extraction


logger = logging.getLogger(__name__)


# Stale indexing threshold (minutes)
STALE_INDEXING_MINUTES = 10


@dataclass
class IndexResult:
    status: str
    chunk_count: Optional[int]
    error_message: Optional[str]
    indexed_at: Optional[datetime]


class IndexingService:
    """Service for PDF indexing operations."""

    def __init__(
        self,
        download_service: PdfDownloadService,
        embedding_service: Optional[EmbeddingService] = None,
    ):
        self.download_service = download_service
        self._embedding_service = embedding_service or EmbeddingService()

    async def get_or_create_status(
        self,
        pdf_id: str,
        user_id: str,
        db: AsyncSession,
    ) -> PdfIndexStatus:
        """Get existing index status or create default 'not_indexed'."""
        result = await db.execute(
            select(PdfIndexStatus).where(
                PdfIndexStatus.pdf_id == pdf_id,
                PdfIndexStatus.user_id == user_id,
            )
        )
        row = result.scalar_one_or_none()

        if row is None:
            row = PdfIndexStatus(
                pdf_id=pdf_id,
                user_id=user_id,
                status="not_indexed",
            )
            db.add(row)
            await db.flush()

        return row

    async def reset_if_stale(
        self,
        index_status: PdfIndexStatus,
        db: AsyncSession,
        stale_minutes: int = STALE_INDEXING_MINUTES,
    ) -> bool:
        """Reset status to 'not_indexed' if stale. Raises IndexInProgressError if actively indexing."""
        if index_status.status != "indexing":
            return False

        stale_cutoff = datetime.now(timezone.utc) - timedelta(minutes=stale_minutes)

        if index_status.updated_at and index_status.updated_at >= stale_cutoff:
            # Still actively indexing
            raise IndexInProgressError(
                pdf_id=str(index_status.pdf_id),
                updated_at=index_status.updated_at,
            )

        # Stale - reset to not_indexed
        index_status.status = "not_indexed"
        await db.flush()
        logger.info(
            "Reset stale indexing status for PDF %s (user %s)",
            index_status.pdf_id,
            index_status.user_id,
        )
        return True

    async def index_pdf(
        self,
        pdf_row: Pdf,
        user: User,
        index_status: PdfIndexStatus,
        db: AsyncSession,
    ) -> IndexResult:
        """Full indexing workflow: download → extract → chunk → embed."""
        index_status.status = "indexing"
        index_status.updated_at = datetime.now(timezone.utc)
        await db.flush()

        tmp_path: Path | None = None
        try:
            tmp_path = await self.download_pdf_for_row(pdf_row, user, db)

            with open(tmp_path, "rb") as f:
                text_with_pages, _total_pages, _pages_analyzed = (
                    extract_text_with_pages(f)
                )

            if not text_with_pages.strip():
                raise TextExtractionError(
                    "PDF has no extractable text (may be image-only)."
                )

            quality = validate_extraction(text_with_pages)
            if not quality.is_usable:
                raise TextExtractionError(
                    f"Extracted text quality too low (score: {quality.score:.1f}). "
                    f"Issues: {'; '.join(quality.warnings)}. "
                    f"This PDF may be image-only or have an unsupported layout."
                )
            if quality.warnings:
                logger.warning(
                    "Extraction quality warnings for PDF %s: %s",
                    pdf_row.id,
                    quality.warnings,
                )

            chunks = chunk_text_with_pages(text_with_pages)
            if not chunks:
                raise ChunkingError("No chunks produced from PDF text.")

            texts = [c.content for c in chunks]
            embeddings = await self._embedding_service.embed_texts(texts, db=db)

            # Delete stale chunks and insert new ones
            await db.execute(
                delete(PdfChunk).where(
                    PdfChunk.pdf_id == pdf_row.id,
                    PdfChunk.user_id == user.id,
                )
            )

            for chunk, embedding in zip(chunks, embeddings):
                db.add(
                    PdfChunk(
                        pdf_id=pdf_row.id,
                        user_id=user.id,
                        chunk_index=chunk.chunk_index,
                        page_number=chunk.page_number,
                        end_page_number=chunk.end_page_number,
                        content=chunk.content.replace("\x00", ""),
                        embedding=embedding,
                        section_title=chunk.section_title,
                        section_level=chunk.section_level,
                    )
                )

            now = datetime.now(timezone.utc)
            index_status.status = "indexed"
            index_status.chunk_count = len(chunks)
            index_status.indexed_at = now
            index_status.updated_at = now
            index_status.error_message = None

            logger.info(
                "Successfully indexed PDF %s (user %s): %d chunks",
                pdf_row.id,
                user.id,
                len(chunks),
            )

            return IndexResult(
                status="indexed",
                chunk_count=len(chunks),
                error_message=None,
                indexed_at=now,
            )

        except (EmbeddingError, OpenRouterQuotaError, TextExtractionError, ChunkingError) as exc:
            index_status.status = "failed"
            index_status.error_message = str(exc)
            index_status.updated_at = datetime.now(timezone.utc)
            logger.error(
                "Indexing failed for PDF %s: %s",
                pdf_row.id,
                exc,
            )
            raise

        except Exception as exc:
            index_status.status = "failed"
            index_status.error_message = f"Unexpected error: {exc}"
            index_status.updated_at = datetime.now(timezone.utc)
            logger.exception(
                "Unexpected error indexing PDF %s",
                pdf_row.id,
            )
            raise IndexingError(str(exc)) from exc

        finally:
            # Clean up temp file
            if tmp_path:
                tmp_path.unlink(missing_ok=True)

    async def download_pdf_for_row(
        self,
        pdf_row: Pdf,
        user: User,
        db: AsyncSession,
    ) -> Path:
        try:
            # Case 1: URL-linked PDF (no stored content)
            if (
                pdf_row.source_url
                and not pdf_row.github_sha
                and not pdf_row.drive_file_id
            ):
                result = await self.download_service.download_to_tempfile(
                    source=PdfSource.EXTERNAL_URL,
                    external_url=pdf_row.source_url,
                )
                return result.file_path

            # Case 2: Stored PDF — delegate to the user's active storage backend
            file_id = pdf_row.drive_file_id or pdf_row.github_sha
            backend = await get_storage_backend(user, db)
            return await backend.download_to_tempfile(file_id, pdf_row.filename)

        except Exception as e:
            raise IndexingError(f"Failed to download PDF: {e}") from e

    async def ensure_indexed(
        self,
        pdf_row: Pdf,
        user: User,
        index_status: PdfIndexStatus,
        db: AsyncSession,
    ) -> PdfIndexStatus:
        """Ensure PDF is indexed, triggering lazy index if needed.

        Main entry point for chat/explain features.
        Handles stale checks, failed retries, and in-progress waits.
        """
        if index_status.status == "indexed":
            return index_status

        await self.reset_if_stale(index_status, db)

        # Handle failed indexing - reset to retry
        if index_status.status == "failed":
            index_status.status = "not_indexed"
            index_status.error_message = None
            await db.flush()

        if index_status.status == "not_indexed":
            await self.index_pdf(pdf_row, user, index_status, db)

        return index_status


# Singleton instance for use in routes
# Note: This needs to be initialized after the app starts to get the download service
# We'll create a factory function for this
_indexing_service_instance: Optional[IndexingService] = None


def get_indexing_service(download_service: PdfDownloadService) -> IndexingService:
    global _indexing_service_instance
    if _indexing_service_instance is None:
        _indexing_service_instance = IndexingService(download_service)
    return _indexing_service_instance
