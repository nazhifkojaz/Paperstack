"""Service-level tests for summary generation (B1)."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import select

from app.db.models import Pdf, PdfChunk, PdfIndexStatus, PdfSummary
from app.services import summary_service
from app.services.llm_service import _parse_summary_json


def _make_summary_dict() -> dict:
    return {
        "tldr": "A compact summary.",
        "problem": "The problem addressed.",
        "method": "The approach.",
        "dataset": "WMT-14",
        "result": "28.4 BLEU.",
        "contribution": "Attention-only architecture.",
        "key_claims": ["claim one", "claim two"],
    }


class _FakeSessionCtx:
    """Async context manager yielding the shared test session (never closes)."""

    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, *_):
        return False


class _FakeIndexingService:
    """Stand-in for IndexingService that skips real PDF indexing."""

    def __init__(self, download_service=None, embedding_service=None):
        pass

    async def get_or_create_status(self, pdf_id, user_id, db):
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

    async def ensure_indexed(self, pdf, user, idx_status, db):
        return None


@pytest.mark.asyncio
class TestComputePaperEmbedding:
    async def test_averages_chunk_embeddings(self, db_session, test_user):
        pdf = Pdf(
            user_id=test_user.id,
            title="Emb Test",
            filename="emb.pdf",
        )
        db_session.add(pdf)
        await db_session.flush()

        for value in (0.0, 2.0):
            db_session.add(
                PdfChunk(
                    pdf_id=pdf.id,
                    user_id=test_user.id,
                    chunk_index=int(value),
                    page_number=1,
                    end_page_number=1,
                    content=f"chunk {value}",
                    embedding=[value] * 1024,
                )
            )
        await db_session.flush()

        emb = await summary_service.compute_paper_embedding(
            pdf.id, test_user.id, db_session
        )

        assert emb is not None
        assert len(emb) == 1024
        # Mean of all-0.0 and all-2.0 vectors is all-1.0.
        assert all(abs(v - 1.0) < 1e-2 for v in emb)

    async def test_returns_none_without_embedded_chunks(self, db_session, test_user):
        pdf = Pdf(
            user_id=test_user.id,
            title="No Emb",
            filename="no.pdf",
        )
        db_session.add(pdf)
        await db_session.flush()
        db_session.add(
            PdfChunk(
                pdf_id=pdf.id,
                user_id=test_user.id,
                chunk_index=0,
                page_number=1,
                end_page_number=1,
                content="no embedding here",
                embedding=None,
            )
        )
        await db_session.flush()

        emb = await summary_service.compute_paper_embedding(
            pdf.id, test_user.id, db_session
        )
        assert emb is None


class TestParseSummaryJson:
    def test_valid_json(self):
        raw = '{"tldr": "x", "problem": "y", "key_claims": ["a", "b"]}'
        data = _parse_summary_json(raw)
        assert data["tldr"] == "x"
        assert data["problem"] == "y"
        assert data["method"] is None
        assert data["key_claims"] == ["a", "b"]

    def test_fenced_json(self):
        raw = '```json\n{"tldr": "fenced"}\n```'
        data = _parse_summary_json(raw)
        assert data["tldr"] == "fenced"

    def test_missing_tldr_raises(self):
        with pytest.raises(ValueError):
            _parse_summary_json('{"problem": "no tldr"}')

    def test_filters_non_string_claims(self):
        raw = '{"tldr": "x", "key_claims": ["ok", 5, "", "good"]}'
        data = _parse_summary_json(raw)
        assert data["key_claims"] == ["ok", "good"]

    def test_caps_claims_at_five(self):
        raw = '{"tldr": "x", "key_claims": ["a", "b", "c", "d", "e", "f", "g"]}'
        data = _parse_summary_json(raw)
        assert data["key_claims"] == ["a", "b", "c", "d", "e"]


@pytest.mark.asyncio
class TestRunGeneration:
    async def _seed(
        self,
        db_session,
        test_user,
        edited_fields=None,
        method_value="user text",
    ):
        pdf = Pdf(
            user_id=test_user.id,
            title="Gen Test",
            filename="gen.pdf",
        )
        db_session.add(pdf)
        await db_session.flush()
        db_session.add(
            PdfChunk(
                pdf_id=pdf.id,
                user_id=test_user.id,
                chunk_index=0,
                page_number=1,
                end_page_number=1,
                content="x" * 200,
            )
        )
        row = PdfSummary(
            pdf_id=pdf.id,
            user_id=test_user.id,
            status="generating",
            edited_fields=list(edited_fields or []),
            method=method_value,
        )
        db_session.add(row)
        await db_session.flush()
        return pdf, row

    def _patch_session(self, monkeypatch, db_session):
        # Route all background SessionLocal() usage to the shared test session
        # so the seeded row is visible. Commits become flushes to avoid
        # releasing the test's savepoint.
        monkeypatch.setattr(
            summary_service, "SessionLocal", lambda: _FakeSessionCtx(db_session)
        )
        monkeypatch.setattr(db_session, "commit", db_session.flush)
        monkeypatch.setattr(summary_service, "IndexingService", _FakeIndexingService)

    async def test_respects_edited_fields(self, db_session, test_user, monkeypatch):
        pdf, row = await self._seed(db_session, test_user, edited_fields=["method"])
        self._patch_session(monkeypatch, db_session)
        monkeypatch.setattr(
            summary_service,
            "extract_summary_source_text",
            AsyncMock(return_value="x" * 200),
        )
        llm_dict = _make_summary_dict()
        monkeypatch.setattr(
            summary_service.LLMService,
            "generate_paper_summary",
            AsyncMock(return_value=llm_dict),
        )

        await summary_service.run_generation(
            pdf_id=pdf.id,
            user_id=test_user.id,
            provider="openrouter",
            api_key="key",
            model=None,
            llm_client=MagicMock(),
        )

        result = await db_session.execute(
            select(PdfSummary).where(
                PdfSummary.pdf_id == pdf.id,
                PdfSummary.user_id == test_user.id,
            )
        )
        fresh = result.scalar_one()
        assert fresh.status == "complete"
        # Edited field preserved.
        assert fresh.method == "user text"
        # Non-edited generated fields written.
        assert fresh.tldr == llm_dict["tldr"]
        assert fresh.dataset == llm_dict["dataset"]
        assert fresh.key_claims == llm_dict["key_claims"]
        assert fresh.edited_fields == ["method"]

    async def test_llm_value_error_marks_failed(
        self, db_session, test_user, monkeypatch
    ):
        pdf, row = await self._seed(db_session, test_user, edited_fields=[])
        self._patch_session(monkeypatch, db_session)
        monkeypatch.setattr(
            summary_service,
            "extract_summary_source_text",
            AsyncMock(return_value="x" * 200),
        )
        monkeypatch.setattr(
            summary_service.LLMService,
            "generate_paper_summary",
            AsyncMock(side_effect=ValueError("bad json")),
        )

        await summary_service.run_generation(
            pdf_id=pdf.id,
            user_id=test_user.id,
            provider="openrouter",
            api_key="key",
            model=None,
            llm_client=MagicMock(),
        )

        result = await db_session.execute(
            select(PdfSummary).where(
                PdfSummary.pdf_id == pdf.id,
                PdfSummary.user_id == test_user.id,
            )
        )
        fresh = result.scalar_one()
        assert fresh.status == "failed"
        assert fresh.error_message is not None
        assert "parsing" in fresh.error_message.lower()
