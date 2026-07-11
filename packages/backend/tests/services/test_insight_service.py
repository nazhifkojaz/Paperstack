"""Service-level tests for collection insight generation (Phase 3)."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import select

from app.db.models import Collection, CollectionInsight, Pdf, PdfCollection, PdfSummary
from app.services import insight_service


class _FakeSessionCtx:
    """Async context manager yielding the shared test session (never closes)."""

    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, *_):
        return False


@pytest.mark.asyncio
class TestRunInsight:
    async def _seed_collection(self, db_session, test_user, n=2):
        collection = Collection(
            user_id=test_user.id,
            name="Test Collection",
        )
        db_session.add(collection)
        await db_session.flush()

        pdfs = []
        for i in range(n):
            pdf = Pdf(
                user_id=test_user.id,
                title=f"Paper {i}",
                filename=f"p{i}.pdf",
            )
            db_session.add(pdf)
            await db_session.flush()
            db_session.add(PdfCollection(pdf_id=pdf.id, collection_id=collection.id))
            db_session.add(
                PdfSummary(
                    pdf_id=pdf.id,
                    user_id=test_user.id,
                    status="complete",
                    tldr=f"tldr {i}",
                    method=f"method {i}",
                    result=f"result {i}",
                    key_claims=[f"claim {i}"],
                )
            )
            pdfs.append(pdf)
        await db_session.flush()
        return collection, pdfs

    def _patch_session(self, monkeypatch, db_session):
        monkeypatch.setattr(
            insight_service, "SessionLocal", lambda: _FakeSessionCtx(db_session)
        )
        monkeypatch.setattr(db_session, "commit", db_session.flush)

    async def test_synthesis_complete_resolves_chips(
        self, db_session, test_user, monkeypatch
    ):
        collection, pdfs = await self._seed_collection(db_session, test_user, n=2)
        row = CollectionInsight(
            collection_id=collection.id,
            user_id=test_user.id,
            kind="synthesis",
            status="generating",
        )
        db_session.add(row)
        await db_session.flush()
        self._patch_session(monkeypatch, db_session)

        paper_refs = [
            (pdfs[0].id, "Paper 0", 2020),
            (pdfs[1].id, "Paper 1", 2021),
        ]

        monkeypatch.setattr(
            insight_service.LLMService,
            "generate_collection_synthesis",
            AsyncMock(
                return_value={
                    "synthesis": "These papers relate.",
                    "themes": [
                        {
                            "name": "Theme A",
                            "description": "desc",
                            "paper_indexes": [1, 2],
                        }
                    ],
                }
            ),
        )

        await insight_service.run_insight(
            collection_id=collection.id,
            user_id=test_user.id,
            collection_name="Test Collection",
            kind="synthesis",
            paper_refs=paper_refs,
            total_members=2,
            provider="openrouter",
            api_key="key",
            model=None,
            llm_client=MagicMock(),
        )

        result = await db_session.execute(
            select(CollectionInsight).where(
                CollectionInsight.collection_id == collection.id,
                CollectionInsight.kind == "synthesis",
            )
        )
        fresh = result.scalar_one()
        assert fresh.status == "complete"
        assert fresh.progress_pct == 100
        assert fresh.payload is not None
        assert fresh.payload["synthesis"] == "These papers relate."
        theme = fresh.payload["themes"][0]
        assert theme["name"] == "Theme A"
        assert len(theme["papers"]) == 2
        assert theme["papers"][0]["pdf_id"] == str(pdfs[0].id)

    async def test_gaps_complete_resolves_chips(
        self, db_session, test_user, monkeypatch
    ):
        collection, pdfs = await self._seed_collection(db_session, test_user, n=2)
        row = CollectionInsight(
            collection_id=collection.id,
            user_id=test_user.id,
            kind="gaps",
            status="generating",
        )
        db_session.add(row)
        await db_session.flush()
        self._patch_session(monkeypatch, db_session)

        paper_refs = [
            (pdfs[0].id, "Paper 0", 2020),
            (pdfs[1].id, "Paper 1", 2021),
        ]

        monkeypatch.setattr(
            insight_service.LLMService,
            "generate_collection_gaps",
            AsyncMock(
                return_value={
                    "contradictions": [
                        {
                            "title": "Disagree",
                            "description": "desc",
                            "paper_indexes": [1, 2],
                        }
                    ],
                    "gaps": [],
                    "lineages": [],
                }
            ),
        )

        await insight_service.run_insight(
            collection_id=collection.id,
            user_id=test_user.id,
            collection_name="Test Collection",
            kind="gaps",
            paper_refs=paper_refs,
            total_members=2,
            provider="openrouter",
            api_key="key",
            model=None,
            llm_client=MagicMock(),
        )

        result = await db_session.execute(
            select(CollectionInsight).where(
                CollectionInsight.collection_id == collection.id,
                CollectionInsight.kind == "gaps",
            )
        )
        fresh = result.scalar_one()
        assert fresh.status == "complete"
        assert len(fresh.payload["contradictions"]) == 1
        assert len(fresh.payload["contradictions"][0]["papers"]) == 2

    async def test_parse_failure_marks_failed(self, db_session, test_user, monkeypatch):
        collection, pdfs = await self._seed_collection(db_session, test_user, n=2)
        row = CollectionInsight(
            collection_id=collection.id,
            user_id=test_user.id,
            kind="synthesis",
            status="generating",
        )
        db_session.add(row)
        await db_session.flush()
        self._patch_session(monkeypatch, db_session)

        monkeypatch.setattr(
            insight_service.LLMService,
            "generate_collection_synthesis",
            AsyncMock(side_effect=ValueError("bad json")),
        )

        await insight_service.run_insight(
            collection_id=collection.id,
            user_id=test_user.id,
            collection_name="Test Collection",
            kind="synthesis",
            paper_refs=[(pdfs[0].id, "Paper 0", 2020)],
            total_members=2,
            provider="openrouter",
            api_key="key",
            model=None,
            llm_client=MagicMock(),
        )

        result = await db_session.execute(
            select(CollectionInsight).where(
                CollectionInsight.collection_id == collection.id,
            )
        )
        fresh = result.scalar_one()
        assert fresh.status == "failed"
        assert fresh.error_message is not None
        assert "parsing" in fresh.error_message.lower()
