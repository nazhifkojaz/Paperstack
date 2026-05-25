"""Tests for the PDF indexing service."""

import tempfile
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.indexing_service import IndexingService, IndexResult
from app.services.exceptions import (
    ChunkingError,
    IndexInProgressError,
    IndexingError,
    TextExtractionError,
)
from app.services.pdf_download_service import PdfDownloadService
from app.db.models import PdfIndexStatus


@pytest.fixture
def mock_download_service():
    svc = MagicMock(spec=PdfDownloadService)
    svc.download_to_tempfile = AsyncMock()
    return svc


@pytest.fixture
def mock_embedding():
    svc = MagicMock()
    svc.embed_query = AsyncMock()
    svc.embed_texts = AsyncMock()
    return svc


@pytest.fixture
def indexing_service(mock_download_service, mock_embedding):
    return IndexingService(
        download_service=mock_download_service,
        embedding_service=mock_embedding,
    )


@pytest.fixture
def mock_db():
    db = MagicMock()
    db.execute = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    return db


@pytest.fixture
def sample_index_status():
    return PdfIndexStatus(
        pdf_id=str(uuid.uuid4()),
        user_id=str(uuid.uuid4()),
        status="not_indexed",
    )


# ---------------------------------------------------------------------------
# get_or_create_status
# ---------------------------------------------------------------------------

class TestGetOrCreateStatus:

    async def test_returns_existing_status(self, indexing_service, mock_db):
        existing = PdfIndexStatus(
            pdf_id="pdf-1", user_id="user-1", status="indexed",
        )
        scalar_result = MagicMock()
        scalar_result.scalar_one_or_none = MagicMock(return_value=existing)
        mock_db.execute = AsyncMock(return_value=scalar_result)

        result = await indexing_service.get_or_create_status("pdf-1", "user-1", mock_db)
        assert result is existing
        assert result.status == "indexed"

    async def test_creates_new_status_when_none(self, indexing_service, mock_db):
        scalar_result = MagicMock()
        scalar_result.scalar_one_or_none = MagicMock(return_value=None)
        mock_db.execute = AsyncMock(return_value=scalar_result)

        result = await indexing_service.get_or_create_status("pdf-1", "user-1", mock_db)
        assert result.status == "not_indexed"
        assert result.pdf_id == "pdf-1"
        assert result.user_id == "user-1"
        mock_db.add.assert_called_once()


# ---------------------------------------------------------------------------
# reset_if_stale
# ---------------------------------------------------------------------------

class TestResetIfStale:

    async def test_not_indexing_status_skips(self, indexing_service, mock_db):
        status = PdfIndexStatus(
            pdf_id="pdf-1", user_id="user-1", status="indexed",
        )
        was_reset = await indexing_service.reset_if_stale(status, mock_db)
        assert was_reset is False

    async def test_active_indexing_raises(self, indexing_service, mock_db):
        status = PdfIndexStatus(
            pdf_id="pdf-1", user_id="user-1", status="indexing",
            updated_at=datetime.now(timezone.utc),
        )
        with pytest.raises(IndexInProgressError):
            await indexing_service.reset_if_stale(status, mock_db)

    async def test_stale_indexing_resets(self, indexing_service, mock_db):
        stale_time = datetime.now(timezone.utc) - timedelta(minutes=15)
        status = PdfIndexStatus(
            pdf_id="pdf-1", user_id="user-1", status="indexing",
            updated_at=stale_time,
        )
        was_reset = await indexing_service.reset_if_stale(status, mock_db)
        assert was_reset is True
        assert status.status == "not_indexed"

    async def test_no_updated_at_resets(self, indexing_service, mock_db):
        status = PdfIndexStatus(
            pdf_id="pdf-1", user_id="user-1", status="indexing",
            updated_at=None,
        )
        was_reset = await indexing_service.reset_if_stale(status, mock_db)
        assert was_reset is True
        assert status.status == "not_indexed"


# ---------------------------------------------------------------------------
# ensure_indexed
# ---------------------------------------------------------------------------

class TestEnsureIndexed:

    async def test_already_indexed_returns(self, indexing_service, mock_db):
        pdf_row = MagicMock()
        pdf_row.id = uuid.uuid4()
        user = MagicMock()
        status = PdfIndexStatus(pdf_id="pdf-1", user_id="user-1", status="indexed")

        result = await indexing_service.ensure_indexed(pdf_row, user, status, mock_db)
        assert result is status

    @staticmethod
    def _setup_tmp_download(svc):
        """Create a real temp file and mock the download to return it."""
        tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
        tmp.write(b"dummy pdf content")
        tmp.close()
        tmp_path = Path(tmp.name)
        result = MagicMock()
        result.file_path = tmp_path
        svc.download_service.download_to_tempfile = AsyncMock(return_value=result)
        return tmp_path

    async def test_not_indexed_triggers_indexing(
        self, indexing_service, mock_db, mock_embedding
    ):
        mock_embedding.embed_texts = AsyncMock(return_value=[[0.1] * 384])

        pdf_row = MagicMock()
        pdf_row.id = uuid.uuid4()
        pdf_row.source_url = "https://example.com/test.pdf"
        pdf_row.github_sha = None
        pdf_row.drive_file_id = None
        pdf_row.filename = "test.pdf"

        user = MagicMock()
        user.id = uuid.uuid4()

        status = PdfIndexStatus(pdf_id="pdf-1", user_id="user-1", status="not_indexed")

        tmp_path = self._setup_tmp_download(indexing_service)

        try:
            with patch(
                "app.services.indexing_service.extract_text_with_pages",
                return_value=(
                    "--- PAGE 1 ---\n\n"
                    + " ".join(
                        f"This is sentence {i} on page one with enough content to create chunks."
                        for i in range(25)
                    ),
                    1,
                    1,
                ),
            ), patch(
                "app.services.indexing_service.validate_extraction",
                return_value=MagicMock(is_usable=True, warnings=[]),
            ):
                result = await indexing_service.ensure_indexed(pdf_row, user, status, mock_db)
        finally:
            tmp_path.unlink(missing_ok=True)

        assert result.status == "indexed"

    async def test_failed_status_resets_to_retry(
        self, indexing_service, mock_db, mock_embedding
    ):
        mock_embedding.embed_texts = AsyncMock(return_value=[[0.1] * 384])

        pdf_row = MagicMock()
        pdf_row.id = uuid.uuid4()
        pdf_row.source_url = "https://example.com/test.pdf"
        pdf_row.github_sha = None
        pdf_row.drive_file_id = None
        pdf_row.filename = "test.pdf"

        user = MagicMock()
        user.id = uuid.uuid4()

        status = PdfIndexStatus(
            pdf_id="pdf-1", user_id="user-1", status="failed",
            error_message="previous error",
        )

        tmp_path = self._setup_tmp_download(indexing_service)

        try:
            with patch(
                "app.services.indexing_service.extract_text_with_pages",
                return_value=(
                    "--- PAGE 1 ---\n\n"
                    + " ".join(
                        f"Sentence {i} with enough content for chunking."
                        for i in range(25)
                    ),
                    1,
                    1,
                ),
            ), patch(
                "app.services.indexing_service.validate_extraction",
                return_value=MagicMock(is_usable=True, warnings=[]),
            ):
                result = await indexing_service.ensure_indexed(pdf_row, user, status, mock_db)
        finally:
            tmp_path.unlink(missing_ok=True)

        assert result.status == "indexed"
        assert result.error_message is None


# ---------------------------------------------------------------------------
# index_pdf — full pipeline
# ---------------------------------------------------------------------------

class TestIndexPdf:

    @staticmethod
    def _setup_tmp_download(svc):
        tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
        tmp.write(b"dummy pdf content")
        tmp.close()
        tmp_path = Path(tmp.name)
        result = MagicMock()
        result.file_path = tmp_path
        svc.download_service.download_to_tempfile = AsyncMock(return_value=result)
        return tmp_path

    async def test_index_pdf_success(self, indexing_service, mock_db, mock_embedding):
        mock_embedding.embed_texts = AsyncMock(
            return_value=[[0.1] * 384, [0.2] * 384]
        )

        pdf_row = MagicMock()
        pdf_row.id = uuid.uuid4()
        pdf_row.source_url = "https://example.com/test.pdf"
        pdf_row.github_sha = None
        pdf_row.drive_file_id = None
        pdf_row.filename = "test.pdf"

        user = MagicMock()
        user.id = uuid.uuid4()

        status = PdfIndexStatus(pdf_id="pdf-1", user_id="user-1", status="not_indexed")

        tmp_path = self._setup_tmp_download(indexing_service)

        try:
            with patch(
                "app.services.indexing_service.extract_text_with_pages",
                return_value=(
                    "--- PAGE 1 ---\n\n"
                    + " ".join(
                        f"This is sentence {i} with enough content for chunking."
                        for i in range(25)
                    ),
                    1,
                    1,
                ),
            ), patch(
                "app.services.indexing_service.validate_extraction",
                return_value=MagicMock(is_usable=True, warnings=[]),
            ), patch(
                "app.services.indexing_service.chunk_text_with_pages",
                return_value=[
                    MagicMock(
                        chunk_index=0, page_number=1, end_page_number=1,
                        content="chunk 1 content", section_title=None, section_level=None,
                    ),
                    MagicMock(
                        chunk_index=1, page_number=1, end_page_number=1,
                        content="chunk 2 content", section_title=None, section_level=None,
                    ),
                ],
            ):
                result = await indexing_service.index_pdf(pdf_row, user, status, mock_db)
        finally:
            tmp_path.unlink(missing_ok=True)

        assert isinstance(result, IndexResult)
        assert result.status == "indexed"
        assert result.chunk_count == 2
        assert result.error_message is None
        assert result.indexed_at is not None

    async def test_index_pdf_chunking_failure(self, indexing_service, mock_db):
        pdf_row = MagicMock()
        pdf_row.id = uuid.uuid4()
        pdf_row.source_url = "https://example.com/test.pdf"
        pdf_row.github_sha = None
        pdf_row.drive_file_id = None
        pdf_row.filename = "test.pdf"

        user = MagicMock()
        status = PdfIndexStatus(pdf_id="pdf-1", user_id="user-1", status="not_indexed")

        tmp_path = self._setup_tmp_download(indexing_service)

        try:
            with patch(
                "app.services.indexing_service.extract_text_with_pages",
                return_value=("some text", 1, 1),
            ), patch(
                "app.services.indexing_service.validate_extraction",
                return_value=MagicMock(is_usable=True, warnings=[]),
            ), patch(
                "app.services.indexing_service.chunk_text_with_pages",
                return_value=[],
            ):
                with pytest.raises(ChunkingError, match="No chunks produced"):
                    await indexing_service.index_pdf(pdf_row, user, status, mock_db)
        finally:
            tmp_path.unlink(missing_ok=True)

        assert status.status == "failed"

    async def test_index_pdf_text_extraction_unusable(
        self, indexing_service, mock_db
    ):
        pdf_row = MagicMock()
        pdf_row.id = uuid.uuid4()
        pdf_row.source_url = "https://example.com/test.pdf"
        pdf_row.github_sha = None
        pdf_row.drive_file_id = None
        pdf_row.filename = "test.pdf"

        user = MagicMock()
        status = PdfIndexStatus(pdf_id="pdf-1", user_id="user-1", status="not_indexed")

        tmp_path = self._setup_tmp_download(indexing_service)

        try:
            with patch(
                "app.services.indexing_service.extract_text_with_pages",
                return_value=("poor quality text", 1, 1),
            ), patch(
                "app.services.indexing_service.validate_extraction",
                return_value=MagicMock(is_usable=False, score=10.0, warnings=["too short"]),
            ):
                with pytest.raises(TextExtractionError, match="quality too low"):
                    await indexing_service.index_pdf(pdf_row, user, status, mock_db)
        finally:
            tmp_path.unlink(missing_ok=True)

        assert status.status == "failed"


# ---------------------------------------------------------------------------
# download_pdf_for_row
# ---------------------------------------------------------------------------


class TestDownloadPdfForRow:

    @staticmethod
    def _make_pdf_row(source_url=None, github_sha=None, drive_file_id=None, filename="test.pdf"):
        row = MagicMock()
        row.source_url = source_url
        row.github_sha = github_sha
        row.drive_file_id = drive_file_id
        row.filename = filename
        return row

    async def test_external_url_download(self, indexing_service, mock_db):
        pdf_row = self._make_pdf_row(source_url="https://example.com/test.pdf")
        user = MagicMock()

        tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
        tmp.write(b"pdf content")
        tmp.close()
        tmp_path = Path(tmp.name)

        try:
            result_mock = MagicMock()
            result_mock.file_path = tmp_path
            indexing_service.download_service.download_to_tempfile = AsyncMock(
                return_value=result_mock
            )

            result = await indexing_service.download_pdf_for_row(pdf_row, user, mock_db)

            assert result == tmp_path
        finally:
            tmp_path.unlink(missing_ok=True)

    async def test_stored_pdf_delegates_to_storage_backend(self, indexing_service, mock_db):
        pdf_row = self._make_pdf_row(github_sha="abc123", filename="stored.pdf")
        user = MagicMock()
        user.id = uuid.uuid4()

        tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
        tmp.write(b"stored content")
        tmp.close()
        tmp_path = Path(tmp.name)

        try:
            with patch(
                "app.services.indexing_service.get_storage_backend",
                new_callable=AsyncMock,
            ) as mock_get_backend:
                mock_backend = MagicMock()
                mock_backend.download_to_tempfile = AsyncMock(return_value=tmp_path)
                mock_get_backend.return_value = mock_backend

                result = await indexing_service.download_pdf_for_row(
                    pdf_row, user, mock_db
                )

                assert result == tmp_path
                mock_get_backend.assert_called_once()
        finally:
            tmp_path.unlink(missing_ok=True)

    async def test_download_failure_wraps_as_indexing_error(self, indexing_service, mock_db):
        pdf_row = self._make_pdf_row(source_url="https://example.com/test.pdf")
        user = MagicMock()

        indexing_service.download_service.download_to_tempfile = AsyncMock(
            side_effect=Exception("Network failure")
        )

        with pytest.raises(IndexingError, match="Failed to download PDF"):
            await indexing_service.download_pdf_for_row(pdf_row, user, mock_db)


# ---------------------------------------------------------------------------
# index_pdf — unexpected exception
# ---------------------------------------------------------------------------


class TestIndexPdfUnexpectedError:

    @staticmethod
    def _setup_tmp_download(svc):
        tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
        tmp.write(b"dummy pdf content")
        tmp.close()
        tmp_path = Path(tmp.name)
        result = MagicMock()
        result.file_path = tmp_path
        svc.download_service.download_to_tempfile = AsyncMock(return_value=result)
        return tmp_path

    async def test_unexpected_exception_sets_failed(self, indexing_service, mock_db):
        pdf_row = MagicMock()
        pdf_row.id = uuid.uuid4()
        pdf_row.source_url = "https://example.com/test.pdf"
        pdf_row.github_sha = None
        pdf_row.drive_file_id = None
        pdf_row.filename = "test.pdf"

        user = MagicMock()
        status = PdfIndexStatus(pdf_id="pdf-1", user_id="user-1", status="not_indexed")

        tmp_path = self._setup_tmp_download(indexing_service)

        try:
            with patch(
                "app.services.indexing_service.extract_text_with_pages",
                side_effect=RuntimeError("Unexpected filesystem error"),
            ):
                with pytest.raises(IndexingError, match="Unexpected filesystem error"):
                    await indexing_service.index_pdf(pdf_row, user, status, mock_db)
        finally:
            tmp_path.unlink(missing_ok=True)

        assert status.status == "failed"
        assert "Unexpected filesystem error" in status.error_message
