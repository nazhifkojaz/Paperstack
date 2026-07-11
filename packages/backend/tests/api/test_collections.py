"""Tests for collection routes."""

import asyncio
import uuid
from datetime import date
import httpx
from httpx import AsyncClient
from unittest.mock import AsyncMock, MagicMock, patch

from app.db.models import (
    CollectionInsight,
    Pdf,
    PdfCollection,
    PdfSummary,
    UserUsageQuota,
)
from app.services.exceptions import QuotaExhaustedError
from app.services.quota_service import quota_service
from tests.fixtures import (
    create_test_pdf,
    create_test_collection,
    create_test_pdf_collection,
    create_test_citation,
)


def _make_create_task_stub(real_create_task):
    """Capture (and close) background coroutines spawned by a route."""
    background_tasks = []

    def _create_task(coro):
        coro_name = getattr(getattr(coro, "cr_code", None), "co_name", None)
        if coro_name == "run_bulk_generation":
            background_tasks.append(coro)
            coro.close()
            return MagicMock()
        return real_create_task(coro)

    _create_task.background_tasks = background_tasks
    return _create_task


def _make_insight_create_task_stub(real_create_task):
    """Capture (and close) run_insight coroutines spawned by insight routes."""
    background_tasks = []

    def _create_task(coro):
        coro_name = getattr(getattr(coro, "cr_code", None), "co_name", None)
        if coro_name == "run_insight":
            background_tasks.append(coro)
            coro.close()
            return MagicMock()
        return real_create_task(coro)

    _create_task.background_tasks = background_tasks
    return _create_task


def _make_resolve(unlimited: bool = False):
    async def _resolve(user, db, feature):
        resolution = MagicMock(
            provider="openrouter",
            api_key="test-key",
            model=None,
            is_in_house=True,
        )
        if unlimited:
            quota_result = MagicMock(unlimited=True, remaining=-1)
            return resolution, quota_result
        try:
            quota_result = await quota_service.check_and_decrement(
                user.id, db, "summary"
            )
        except QuotaExhaustedError as exc:
            from fastapi import HTTPException

            raise HTTPException(status_code=402, detail=str(exc))
        return resolution, quota_result

    return _resolve


class TestCreateCollection:
    """Tests for POST /v1/collections"""

    async def test_create_collection(self, client: AsyncClient, auth_headers) -> None:
        """Test creating a new collection."""
        response = await client.post(
            "/v1/collections",
            json={"name": "Research Papers", "position": 0},
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Research Papers"
        assert data["position"] == 0
        assert "id" in data

    async def test_create_collection_with_parent(
        self, client: AsyncClient, auth_headers, db_session, test_user
    ) -> None:
        """Test creating a nested collection."""
        parent = await create_test_collection(
            db_session, user_id=test_user.id, name="Parent", position=0
        )
        await db_session.commit()

        response = await client.post(
            "/v1/collections",
            json={
                "name": "Child",
                "parent_id": str(parent.id),
                "position": 0,
            },
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["parent_id"] == str(parent.id)

    async def test_create_collection_invalid_parent_returns_400(
        self, client: AsyncClient, auth_headers
    ) -> None:
        """Test creating collection with invalid parent returns 400."""
        fake_parent_id = uuid.uuid4()

        response = await client.post(
            "/v1/collections",
            json={
                "name": "Orphan",
                "parent_id": str(fake_parent_id),
            },
            headers=auth_headers,
        )

        assert response.status_code == 400


class TestListCollections:
    """Tests for GET /v1/collections"""

    async def test_list_collections_returns_user_collections(
        self, client: AsyncClient, auth_headers, db_session, test_user, test_user_2
    ) -> None:
        """Test listing returns only user's collections."""
        await create_test_collection(
            db_session, user_id=test_user.id, name="My Collection 1", position=0
        )
        await create_test_collection(
            db_session, user_id=test_user.id, name="My Collection 2", position=1
        )
        # Other user's collection
        await create_test_collection(
            db_session, user_id=test_user_2.id, name="Other's Collection", position=0
        )
        await db_session.commit()

        response = await client.get(
            "/v1/collections",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert all(c["user_id"] == str(test_user.id) for c in data)

    async def test_list_collections_ordered_by_position(
        self, client: AsyncClient, auth_headers, db_session, test_user
    ) -> None:
        """Test collections are ordered by position."""
        await create_test_collection(
            db_session, user_id=test_user.id, name="First", position=1
        )
        await create_test_collection(
            db_session, user_id=test_user.id, name="Second", position=0
        )
        await db_session.commit()

        response = await client.get(
            "/v1/collections",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data[0]["name"] == "Second"
        assert data[1]["name"] == "First"


class TestUpdateCollection:
    """Tests for PATCH /v1/collections/{collection_id}"""

    async def test_update_collection(
        self, client: AsyncClient, auth_headers, db_session, test_user
    ) -> None:
        """Test updating collection name."""
        col = await create_test_collection(
            db_session, user_id=test_user.id, name="Original", position=0
        )
        await db_session.commit()

        response = await client.patch(
            f"/v1/collections/{col.id}",
            json={"name": "Updated"},
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated"

    async def test_update_other_users_collection_returns_404(
        self, client: AsyncClient, auth_headers
    ) -> None:
        """Test updating another user's collection returns 404."""
        fake_collection_id = uuid.uuid4()

        response = await client.patch(
            f"/v1/collections/{fake_collection_id}",
            json={"name": "Hacked"},
            headers=auth_headers,
        )

        assert response.status_code == 404


class TestDeleteCollection:
    """Tests for DELETE /v1/collections/{collection_id}"""

    async def test_delete_collection(
        self, client: AsyncClient, auth_headers, db_session, test_user
    ) -> None:
        """Test deleting a collection."""
        from sqlalchemy import select
        from app.db.models import Collection

        col = await create_test_collection(
            db_session, user_id=test_user.id, name="To Delete", position=0
        )
        await db_session.commit()

        response = await client.delete(
            f"/v1/collections/{col.id}",
            headers=auth_headers,
        )

        assert response.status_code == 200

        # Verify it's gone
        result = await db_session.execute(
            select(Collection).where(Collection.id == col.id)
        )
        assert result.scalar_one_or_none() is None

    async def test_delete_collection_cascades_pdf_associations(
        self, client: AsyncClient, auth_headers, db_session, test_user
    ) -> None:
        """Test deleting collection removes PDF associations."""
        from sqlalchemy import select
        from app.db.models import PdfCollection

        pdf = await create_test_pdf(db_session, user_id=test_user.id)
        col = await create_test_collection(
            db_session, user_id=test_user.id, name="To Delete", position=0
        )

        await create_test_pdf_collection(
            db_session, pdf_id=pdf.id, collection_id=col.id
        )
        await db_session.commit()

        await client.delete(
            f"/v1/collections/{col.id}",
            headers=auth_headers,
        )

        # Verify association is gone (cascade)
        result = await db_session.execute(
            select(PdfCollection).where(PdfCollection.collection_id == col.id)
        )
        assert result.scalar_one_or_none() is None


class TestAddPdfToCollection:
    """Tests for POST /v1/collections/{collection_id}/pdfs"""

    async def test_add_pdf_to_collection(
        self, client: AsyncClient, auth_headers, db_session, test_user
    ) -> None:
        """Test adding a PDF to a collection."""
        pdf = await create_test_pdf(db_session, user_id=test_user.id)
        col = await create_test_collection(
            db_session, user_id=test_user.id, name="Research", position=0
        )
        await db_session.commit()

        response = await client.post(
            f"/v1/collections/{col.id}/pdfs",
            params={"pdf_id": str(pdf.id)},
            headers=auth_headers,
        )

        assert response.status_code == 200
        assert "added to collection" in response.json()["message"].lower()

    async def test_add_pdf_other_users_collection_returns_404(
        self, client: AsyncClient, auth_headers, db_session, test_user, test_user_2
    ) -> None:
        """Test adding PDF to another user's collection returns 404."""
        pdf = await create_test_pdf(
            db_session, user_id=test_user.id, title="My PDF", filename="my.pdf"
        )
        col = await create_test_collection(
            db_session, user_id=test_user_2.id, name="Other's", position=0
        )
        await db_session.commit()

        response = await client.post(
            f"/v1/collections/{col.id}/pdfs",
            params={"pdf_id": str(pdf.id)},
            headers=auth_headers,
        )

        assert response.status_code == 404

    async def test_add_other_users_pdf_returns_404(
        self, client: AsyncClient, auth_headers, db_session, test_user, test_user_2
    ) -> None:
        """Test adding another user's PDF returns 404."""
        pdf = await create_test_pdf(
            db_session,
            user_id=test_user_2.id,
            title="Other's PDF",
            filename="other.pdf",
        )
        col = await create_test_collection(
            db_session, user_id=test_user.id, name="Mine", position=0
        )
        await db_session.commit()

        response = await client.post(
            f"/v1/collections/{col.id}/pdfs",
            params={"pdf_id": str(pdf.id)},
            headers=auth_headers,
        )

        assert response.status_code == 404


class TestRemovePdfFromCollection:
    """Tests for DELETE /v1/collections/{collection_id}/pdfs/{pdf_id}"""

    async def test_remove_pdf_from_collection(
        self, client: AsyncClient, auth_headers, db_session, test_user
    ) -> None:
        """Test removing a PDF from a collection."""
        from sqlalchemy import select
        from app.db.models import PdfCollection

        pdf = await create_test_pdf(db_session, user_id=test_user.id)
        col = await create_test_collection(
            db_session, user_id=test_user.id, name="Research", position=0
        )

        await create_test_pdf_collection(
            db_session, pdf_id=pdf.id, collection_id=col.id
        )
        await db_session.commit()

        response = await client.delete(
            f"/v1/collections/{col.id}/pdfs/{pdf.id}",
            headers=auth_headers,
        )

        assert response.status_code == 200

        # Verify association is removed
        result = await db_session.execute(
            select(PdfCollection).where(
                PdfCollection.pdf_id == pdf.id,
                PdfCollection.collection_id == col.id,
            )
        )
        assert result.scalar_one_or_none() is None

    async def test_remove_pdf_not_in_collection_returns_404(
        self, client: AsyncClient, auth_headers, db_session, test_user
    ) -> None:
        """Test removing PDF that's not in collection returns 404."""
        pdf = await create_test_pdf(db_session, user_id=test_user.id)
        col = await create_test_collection(
            db_session, user_id=test_user.id, name="Research", position=0
        )
        await db_session.commit()

        response = await client.delete(
            f"/v1/collections/{col.id}/pdfs/{pdf.id}",
            headers=auth_headers,
        )

        assert response.status_code == 404


class TestUpdateCollectionCycleGuard:
    """Tests for cycle detection in PATCH /v1/collections/{collection_id}"""

    async def test_cannot_set_self_as_parent(
        self, client: AsyncClient, auth_headers, db_session, test_user
    ) -> None:
        """Test that a collection cannot be its own parent."""
        col = await create_test_collection(
            db_session, user_id=test_user.id, name="Self", position=0
        )
        await db_session.commit()

        response = await client.patch(
            f"/v1/collections/{col.id}",
            json={"parent_id": str(col.id)},
            headers=auth_headers,
        )

        assert response.status_code == 400

    async def test_cannot_move_under_descendant(
        self, client: AsyncClient, auth_headers, db_session, test_user
    ) -> None:
        """Test that a collection cannot be moved under its own descendant."""
        grandparent = await create_test_collection(
            db_session, user_id=test_user.id, name="Grandparent", position=0
        )
        parent = await create_test_collection(
            db_session,
            user_id=test_user.id,
            name="Parent",
            parent_id=grandparent.id,
            position=0,
        )
        child = await create_test_collection(
            db_session,
            user_id=test_user.id,
            name="Child",
            parent_id=parent.id,
            position=0,
        )
        await db_session.commit()

        response = await client.patch(
            f"/v1/collections/{grandparent.id}",
            json={"parent_id": str(child.id)},
            headers=auth_headers,
        )

        assert response.status_code == 400


class TestExportCollection:
    """Tests for GET /v1/collections/{collection_id}/export"""

    async def test_export_bibtex(
        self, client: AsyncClient, auth_headers, db_session, test_user
    ) -> None:
        """Test exporting a collection as BibTeX."""
        pdf = await create_test_pdf(db_session, user_id=test_user.id)
        col = await create_test_collection(
            db_session, user_id=test_user.id, name="Export Me", position=0
        )
        await create_test_pdf_collection(
            db_session, pdf_id=pdf.id, collection_id=col.id
        )
        await create_test_citation(
            db_session,
            pdf_id=pdf.id,
            user_id=test_user.id,
            bibtex="@article{test2024,\n  title  = {Test Title},\n}",
        )
        await db_session.commit()

        response = await client.get(
            f"/v1/collections/{col.id}/export",
            params={"format": "bibtex"},
            headers=auth_headers,
        )

        assert response.status_code == 200
        assert "Test Title" in response.text
        assert "attachment" in response.headers["content-disposition"]

    async def test_export_markdown(
        self, client: AsyncClient, auth_headers, db_session, test_user
    ) -> None:
        """Test exporting a collection as Markdown."""
        pdf = await create_test_pdf(db_session, user_id=test_user.id, title="A Paper")
        col = await create_test_collection(
            db_session, user_id=test_user.id, name="Markdown Export", position=0
        )
        await create_test_pdf_collection(
            db_session, pdf_id=pdf.id, collection_id=col.id
        )
        await create_test_citation(
            db_session,
            pdf_id=pdf.id,
            user_id=test_user.id,
            title="A Paper",
            authors="Doe, John",
            year=2024,
            doi="10.1234/test",
        )
        await db_session.commit()

        response = await client.get(
            f"/v1/collections/{col.id}/export",
            params={"format": "markdown"},
            headers=auth_headers,
        )

        assert response.status_code == 200
        assert "A Paper" in response.text
        assert "Doe, John" in response.text
        assert "doi.org/10.1234/test" in response.text

    async def test_export_skips_pdf_without_citation(
        self, client: AsyncClient, auth_headers, db_session, test_user
    ) -> None:
        """Test that papers without citations are counted in the skip note."""
        pdf1 = await create_test_pdf(
            db_session, user_id=test_user.id, title="Has Citation", filename="has.pdf"
        )
        pdf2 = await create_test_pdf(
            db_session, user_id=test_user.id, title="No Citation", filename="no.pdf"
        )
        col = await create_test_collection(
            db_session, user_id=test_user.id, name="Mixed", position=0
        )
        await create_test_pdf_collection(
            db_session, pdf_id=pdf1.id, collection_id=col.id
        )
        await create_test_pdf_collection(
            db_session, pdf_id=pdf2.id, collection_id=col.id
        )
        await create_test_citation(
            db_session,
            pdf_id=pdf1.id,
            user_id=test_user.id,
            bibtex="@article{has2024}",
        )
        await db_session.commit()

        response = await client.get(
            f"/v1/collections/{col.id}/export",
            params={"format": "bibtex"},
            headers=auth_headers,
        )

        assert response.status_code == 200
        assert "1 of 2 papers had no citation" in response.text

    async def test_export_other_users_collection_returns_404(
        self, client: AsyncClient, auth_headers
    ) -> None:
        """Test exporting another user's collection returns 404."""
        fake_collection_id = uuid.uuid4()

        response = await client.get(
            f"/v1/collections/{fake_collection_id}/export",
            params={"format": "bibtex"},
            headers=auth_headers,
        )

        assert response.status_code == 404


class TestCollectionOverview:
    """Tests for GET /v1/collections/{collection_id}/overview"""

    async def test_overview_aggregates(
        self, client: AsyncClient, auth_headers, db_session, test_user
    ) -> None:
        """Test overview returns correct aggregate stats."""
        pdf1 = await create_test_pdf(
            db_session, user_id=test_user.id, title="Paper 2023", filename="p1.pdf"
        )
        pdf2 = await create_test_pdf(
            db_session, user_id=test_user.id, title="Paper 2024", filename="p2.pdf"
        )
        col = await create_test_collection(
            db_session, user_id=test_user.id, name="Stats", position=0
        )
        await create_test_pdf_collection(
            db_session, pdf_id=pdf1.id, collection_id=col.id
        )
        await create_test_pdf_collection(
            db_session, pdf_id=pdf2.id, collection_id=col.id
        )
        await create_test_citation(
            db_session,
            pdf_id=pdf1.id,
            user_id=test_user.id,
            authors="John Doe",
            year=2023,
        )
        await create_test_citation(
            db_session,
            pdf_id=pdf2.id,
            user_id=test_user.id,
            authors="John Doe, Jane Smith",
            year=2024,
        )
        await db_session.commit()

        response = await client.get(
            f"/v1/collections/{col.id}/overview",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["paper_count"] == 2
        assert "2023" in data["year_distribution"]
        assert "2024" in data["year_distribution"]
        assert data["year_distribution"]["2023"] == 1
        assert data["year_distribution"]["2024"] == 1
        assert len(data["top_authors"]) >= 1
        author_names = [a["name"] for a in data["top_authors"]]
        assert "John Doe" in author_names

    async def test_overview_recent_papers(
        self, client: AsyncClient, auth_headers, db_session, test_user
    ) -> None:
        """Test overview returns recent papers."""
        pdf = await create_test_pdf(
            db_session, user_id=test_user.id, title="Recent Paper", filename="r.pdf"
        )
        col = await create_test_collection(
            db_session, user_id=test_user.id, name="Recent", position=0
        )
        await create_test_pdf_collection(
            db_session, pdf_id=pdf.id, collection_id=col.id
        )
        await db_session.commit()

        response = await client.get(
            f"/v1/collections/{col.id}/overview",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["paper_count"] == 1
        assert len(data["recent_papers"]) >= 1
        assert data["recent_papers"][0]["title"] == "Recent Paper"

    async def test_overview_other_users_collection_returns_404(
        self, client: AsyncClient, auth_headers
    ) -> None:
        """Test overview for another user's collection returns 404."""
        fake_collection_id = uuid.uuid4()

        response = await client.get(
            f"/v1/collections/{fake_collection_id}/overview",
            headers=auth_headers,
        )

        assert response.status_code == 404


class TestBulkSummarizeCollection:
    async def test_bulk_skips_complete_members(
        self, client: AsyncClient, auth_headers, db_session, test_user
    ) -> None:
        from tests.helpers import setup_http_client_mocks

        setup_http_client_mocks()

        complete_pdf = await create_test_pdf(
            db_session, user_id=test_user.id, title="Done", filename="d.pdf"
        )
        missing_pdf = await create_test_pdf(
            db_session, user_id=test_user.id, title="Missing", filename="m.pdf"
        )
        col = await create_test_collection(
            db_session, user_id=test_user.id, name="Mixed", position=0
        )
        await create_test_pdf_collection(
            db_session, pdf_id=complete_pdf.id, collection_id=col.id
        )
        await create_test_pdf_collection(
            db_session, pdf_id=missing_pdf.id, collection_id=col.id
        )
        db_session.add(
            PdfSummary(
                pdf_id=complete_pdf.id,
                user_id=test_user.id,
                status="complete",
                tldr="done",
            )
        )
        await db_session.commit()

        create_task_stub = _make_create_task_stub(asyncio.create_task)
        with (
            patch(
                "app.api.routes.collections.resolve_api_key_with_quota",
                new_callable=AsyncMock,
            ) as mock_resolve,
            patch("app.api.routes.collections.asyncio.create_task") as mock_create_task,
        ):
            mock_resolve.side_effect = _make_resolve(unlimited=True)
            mock_create_task.side_effect = create_task_stub

            response = await client.post(
                f"/v1/collections/{col.id}/summaries",
                headers=auth_headers,
            )

        assert response.status_code == 202
        data = response.json()
        assert data["skipped_complete"] == 1
        assert [str(missing_pdf.id)] == [q for q in data["queued"]]
        assert len(create_task_stub.background_tasks) == 1

    async def test_bulk_quota_caps_queued(
        self, client: AsyncClient, auth_headers, db_session, test_user
    ) -> None:
        from tests.helpers import setup_http_client_mocks

        setup_http_client_mocks()

        pdfs = [
            await create_test_pdf(
                db_session,
                user_id=test_user.id,
                title=f"P{i}",
                filename=f"p{i}.pdf",
            )
            for i in range(3)
        ]
        col = await create_test_collection(
            db_session, user_id=test_user.id, name="Three", position=0
        )
        for p in pdfs:
            await create_test_pdf_collection(
                db_session, pdf_id=p.id, collection_id=col.id
            )
        db_session.add(
            UserUsageQuota(
                user_id=test_user.id,
                summary_uses_remaining=1,
                reset_at=date.today(),
            )
        )
        await db_session.commit()

        create_task_stub = _make_create_task_stub(asyncio.create_task)
        with (
            patch(
                "app.api.routes.collections.resolve_api_key_with_quota",
                new_callable=AsyncMock,
            ) as mock_resolve,
            patch("app.api.routes.collections.asyncio.create_task") as mock_create_task,
        ):
            mock_resolve.side_effect = _make_resolve(unlimited=False)
            mock_create_task.side_effect = create_task_stub

            response = await client.post(
                f"/v1/collections/{col.id}/summaries",
                headers=auth_headers,
            )

        assert response.status_code == 202
        data = response.json()
        assert len(data["queued"]) == 1
        assert data["skipped_quota"] == 2
        assert data["total_papers"] == 3


class TestCollectionSummariesList:
    async def test_returns_member_rows_only(
        self, client: AsyncClient, auth_headers, db_session, test_user
    ) -> None:
        member = await create_test_pdf(
            db_session, user_id=test_user.id, title="Member", filename="m.pdf"
        )
        nonmember = await create_test_pdf(
            db_session, user_id=test_user.id, title="Other", filename="o.pdf"
        )
        col = await create_test_collection(
            db_session, user_id=test_user.id, name="C", position=0
        )
        await create_test_pdf_collection(
            db_session, pdf_id=member.id, collection_id=col.id
        )
        db_session.add(
            PdfSummary(
                pdf_id=member.id,
                user_id=test_user.id,
                status="complete",
                tldr="m",
            )
        )
        db_session.add(
            PdfSummary(
                pdf_id=nonmember.id,
                user_id=test_user.id,
                status="complete",
                tldr="o",
            )
        )
        await db_session.commit()

        response = await client.get(
            f"/v1/collections/{col.id}/summaries",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["pdf_id"] == str(member.id)


class TestCollectionComparison:
    async def test_comparison_rows_missing_count_and_order(
        self, client: AsyncClient, auth_headers, db_session, test_user
    ) -> None:
        older = await create_test_pdf(
            db_session, user_id=test_user.id, title="Older Paper", filename="old.pdf"
        )
        newer = await create_test_pdf(
            db_session, user_id=test_user.id, title="Newer Paper", filename="new.pdf"
        )
        unscored = await create_test_pdf(
            db_session, user_id=test_user.id, title="No Year", filename="ny.pdf"
        )
        col = await create_test_collection(
            db_session, user_id=test_user.id, name="Compare", position=0
        )
        for p in (older, newer, unscored):
            await create_test_pdf_collection(
                db_session, pdf_id=p.id, collection_id=col.id
            )
        await create_test_citation(
            db_session,
            pdf_id=older.id,
            user_id=test_user.id,
            title="Older Paper",
            year=2017,
        )
        await create_test_citation(
            db_session,
            pdf_id=newer.id,
            user_id=test_user.id,
            title="Newer Paper",
            year=2020,
        )
        # Only 'older' has a complete summary.
        db_session.add(
            PdfSummary(
                pdf_id=older.id,
                user_id=test_user.id,
                status="complete",
                tldr="old tldr",
            )
        )
        await db_session.commit()

        response = await client.get(
            f"/v1/collections/{col.id}/comparison",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["missing_count"] == 2
        titles = [r["title"] for r in data["rows"]]
        # Year ascending (nulls last): 2017, 2020, then no-year.
        assert titles == ["Older Paper", "Newer Paper", "No Year"]
        # Complete summary attached to the older row; others null.
        by_title = {r["title"]: r for r in data["rows"]}
        assert by_title["Older Paper"]["summary"] is not None
        assert by_title["Newer Paper"]["summary"] is None

    async def test_comparison_other_users_collection_returns_404(
        self, client: AsyncClient, auth_headers
    ) -> None:
        response = await client.get(
            f"/v1/collections/{uuid.uuid4()}/comparison",
            headers=auth_headers,
        )
        assert response.status_code == 404


class TestCollectionInsights:
    """Tests for POST synthesize/gaps and GET insights/{kind}."""

    async def _seed_collection_with_summaries(self, db_session, test_user, n=2):
        col = await create_test_collection(
            db_session, user_id=test_user.id, name="Insights", position=0
        )
        for i in range(n):
            pdf = await create_test_pdf(
                db_session,
                user_id=test_user.id,
                title=f"Paper {i}",
                filename=f"ins{i}.pdf",
            )
            await create_test_pdf_collection(
                db_session, pdf_id=pdf.id, collection_id=col.id
            )
            db_session.add(
                PdfSummary(
                    pdf_id=pdf.id,
                    user_id=test_user.id,
                    status="complete",
                    tldr=f"tldr {i}",
                )
            )
        await db_session.commit()
        return col

    async def test_synthesize_returns_202(
        self, client: AsyncClient, auth_headers, db_session, test_user
    ) -> None:
        from tests.helpers import setup_http_client_mocks

        setup_http_client_mocks()
        col = await self._seed_collection_with_summaries(db_session, test_user, n=2)

        stub = _make_insight_create_task_stub(asyncio.create_task)
        with (
            patch(
                "app.api.routes.collections.resolve_api_key_with_quota",
                new_callable=AsyncMock,
            ) as mock_resolve,
            patch("app.api.routes.collections.asyncio.create_task") as mock_ct,
        ):
            mock_resolve.side_effect = _make_resolve(unlimited=True)
            mock_ct.side_effect = stub
            response = await client.post(
                f"/v1/collections/{col.id}/synthesize",
                headers=auth_headers,
            )

        assert response.status_code == 202
        data = response.json()
        assert data["kind"] == "synthesis"
        assert data["status"] == "generating"
        assert data["is_stale"] is False
        assert len(stub.background_tasks) == 1

    async def test_gaps_returns_202(
        self, client: AsyncClient, auth_headers, db_session, test_user
    ) -> None:
        from tests.helpers import setup_http_client_mocks

        setup_http_client_mocks()
        col = await self._seed_collection_with_summaries(db_session, test_user, n=2)

        stub = _make_insight_create_task_stub(asyncio.create_task)
        with (
            patch(
                "app.api.routes.collections.resolve_api_key_with_quota",
                new_callable=AsyncMock,
            ) as mock_resolve,
            patch("app.api.routes.collections.asyncio.create_task") as mock_ct,
        ):
            mock_resolve.side_effect = _make_resolve(unlimited=True)
            mock_ct.side_effect = stub
            response = await client.post(
                f"/v1/collections/{col.id}/insights/gaps",
                headers=auth_headers,
            )

        assert response.status_code == 202
        data = response.json()
        assert data["kind"] == "gaps"
        assert data["status"] == "generating"

    async def test_synthesize_400_when_fewer_than_2_summaries(
        self, client: AsyncClient, auth_headers, db_session, test_user
    ) -> None:
        col = await self._seed_collection_with_summaries(db_session, test_user, n=1)

        response = await client.post(
            f"/v1/collections/{col.id}/synthesize",
            headers=auth_headers,
        )
        assert response.status_code == 400
        assert "at least 2" in response.json()["detail"].lower()

    async def test_synthesize_409_while_generating(
        self, client: AsyncClient, auth_headers, db_session, test_user
    ) -> None:
        col = await self._seed_collection_with_summaries(db_session, test_user, n=2)
        db_session.add(
            CollectionInsight(
                collection_id=col.id,
                user_id=test_user.id,
                kind="synthesis",
                status="generating",
            )
        )
        await db_session.commit()

        response = await client.post(
            f"/v1/collections/{col.id}/synthesize",
            headers=auth_headers,
        )
        assert response.status_code == 409

    async def test_synthesize_402_quota_exhausted(
        self, client: AsyncClient, auth_headers, db_session, test_user
    ) -> None:
        col = await self._seed_collection_with_summaries(db_session, test_user, n=2)
        db_session.add(
            UserUsageQuota(
                user_id=test_user.id,
                summary_uses_remaining=0,
                reset_at=date.today(),
            )
        )
        await db_session.commit()

        with patch(
            "app.api.routes.collections.resolve_api_key_with_quota",
            new_callable=AsyncMock,
        ) as mock_resolve:
            mock_resolve.side_effect = _make_resolve(unlimited=False)
            response = await client.post(
                f"/v1/collections/{col.id}/synthesize",
                headers=auth_headers,
            )
        assert response.status_code == 402

    async def test_get_insight_404_when_absent(
        self, client: AsyncClient, auth_headers, db_session, test_user
    ) -> None:
        col = await self._seed_collection_with_summaries(db_session, test_user, n=2)
        response = await client.get(
            f"/v1/collections/{col.id}/insights/synthesis",
            headers=auth_headers,
        )
        assert response.status_code == 404

    async def test_get_insight_payload_roundtrip(
        self, client: AsyncClient, auth_headers, db_session, test_user
    ) -> None:
        col = await self._seed_collection_with_summaries(db_session, test_user, n=2)
        db_session.add(
            CollectionInsight(
                collection_id=col.id,
                user_id=test_user.id,
                kind="synthesis",
                status="complete",
                payload={"synthesis": "narrative", "themes": []},
                model="test-model",
            )
        )
        await db_session.commit()

        response = await client.get(
            f"/v1/collections/{col.id}/insights/synthesis",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "complete"
        assert data["payload"]["synthesis"] == "narrative"
        assert data["model"] == "test-model"

    async def test_get_insight_invalid_kind_422(
        self, client: AsyncClient, auth_headers, db_session, test_user
    ) -> None:
        col = await self._seed_collection_with_summaries(db_session, test_user, n=2)
        response = await client.get(
            f"/v1/collections/{col.id}/insights/graph",
            headers=auth_headers,
        )
        assert response.status_code == 422

    async def test_add_pdf_flips_is_stale(
        self, client: AsyncClient, auth_headers, db_session, test_user
    ) -> None:
        from sqlalchemy import select as sa_select

        col = await self._seed_collection_with_summaries(db_session, test_user, n=2)
        insight = CollectionInsight(
            collection_id=col.id,
            user_id=test_user.id,
            kind="synthesis",
            status="complete",
            is_stale=False,
        )
        db_session.add(insight)
        await db_session.commit()

        pdf = await create_test_pdf(
            db_session,
            user_id=test_user.id,
            title="New",
            filename="new.pdf",
        )
        await db_session.commit()

        response = await client.post(
            f"/v1/collections/{col.id}/pdfs",
            params={"pdf_id": str(pdf.id)},
            headers=auth_headers,
        )
        assert response.status_code == 200

        result = await db_session.execute(
            sa_select(CollectionInsight).where(
                CollectionInsight.collection_id == col.id,
            )
        )
        fresh = result.scalar_one()
        assert fresh.is_stale is True

    async def test_remove_pdf_flips_is_stale(
        self, client: AsyncClient, auth_headers, db_session, test_user
    ) -> None:
        from sqlalchemy import select as sa_select

        col = await self._seed_collection_with_summaries(db_session, test_user, n=2)
        insight = CollectionInsight(
            collection_id=col.id,
            user_id=test_user.id,
            kind="gaps",
            status="complete",
            is_stale=False,
        )
        db_session.add(insight)
        await db_session.commit()

        # Remove one of the member PDFs.
        member = await db_session.execute(
            sa_select(Pdf.id)
            .join(PdfCollection, PdfCollection.pdf_id == Pdf.id)
            .where(PdfCollection.collection_id == col.id)
            .limit(1)
        )
        member_id = member.scalar_one()

        response = await client.delete(
            f"/v1/collections/{col.id}/pdfs/{member_id}",
            headers=auth_headers,
        )
        assert response.status_code == 200

        result = await db_session.execute(
            sa_select(CollectionInsight).where(
                CollectionInsight.collection_id == col.id,
            )
        )
        fresh = result.scalar_one()
        assert fresh.is_stale is True


class TestCollectionDuplicates:
    """Tests for GET /collections/{id}/duplicates."""

    async def test_pair_above_threshold(
        self, client: AsyncClient, auth_headers, db_session, test_user
    ) -> None:
        emb = [0.01] * 1024
        pdf_a = await create_test_pdf(
            db_session, user_id=test_user.id, title="A", filename="a.pdf"
        )
        pdf_b = await create_test_pdf(
            db_session, user_id=test_user.id, title="B", filename="b.pdf"
        )
        col = await create_test_collection(
            db_session, user_id=test_user.id, name="Dup", position=0
        )
        await create_test_pdf_collection(
            db_session, pdf_id=pdf_a.id, collection_id=col.id
        )
        await create_test_pdf_collection(
            db_session, pdf_id=pdf_b.id, collection_id=col.id
        )
        for pid in (pdf_a.id, pdf_b.id):
            db_session.add(
                PdfSummary(
                    pdf_id=pid,
                    user_id=test_user.id,
                    status="complete",
                    paper_embedding=emb,
                )
            )
        await db_session.commit()

        response = await client.get(
            f"/v1/collections/{col.id}/duplicates",
            headers=auth_headers,
        )
        assert response.status_code == 200
        pairs = response.json()["pairs"]
        assert len(pairs) == 1
        assert pairs[0]["similarity"] >= 0.95

    async def test_pair_below_threshold_excluded(
        self, client: AsyncClient, auth_headers, db_session, test_user
    ) -> None:
        emb_a = [1.0 if i % 2 == 0 else 0.0 for i in range(1024)]
        emb_b = [0.0 if i % 2 == 0 else 1.0 for i in range(1024)]
        pdf_a = await create_test_pdf(
            db_session, user_id=test_user.id, title="A", filename="a.pdf"
        )
        pdf_b = await create_test_pdf(
            db_session, user_id=test_user.id, title="B", filename="b.pdf"
        )
        col = await create_test_collection(
            db_session, user_id=test_user.id, name="Dup", position=0
        )
        await create_test_pdf_collection(
            db_session, pdf_id=pdf_a.id, collection_id=col.id
        )
        await create_test_pdf_collection(
            db_session, pdf_id=pdf_b.id, collection_id=col.id
        )
        db_session.add(
            PdfSummary(
                pdf_id=pdf_a.id,
                user_id=test_user.id,
                status="complete",
                paper_embedding=emb_a,
            )
        )
        db_session.add(
            PdfSummary(
                pdf_id=pdf_b.id,
                user_id=test_user.id,
                status="complete",
                paper_embedding=emb_b,
            )
        )
        await db_session.commit()

        response = await client.get(
            f"/v1/collections/{col.id}/duplicates",
            headers=auth_headers,
        )
        assert response.status_code == 200
        assert response.json()["pairs"] == []

    async def test_papers_without_embeddings_skipped(
        self, client: AsyncClient, auth_headers, db_session, test_user
    ) -> None:
        emb = [0.01] * 1024
        pdf_a = await create_test_pdf(
            db_session, user_id=test_user.id, title="A", filename="a.pdf"
        )
        pdf_b = await create_test_pdf(
            db_session, user_id=test_user.id, title="B", filename="b.pdf"
        )
        pdf_c = await create_test_pdf(
            db_session, user_id=test_user.id, title="C", filename="c.pdf"
        )
        col = await create_test_collection(
            db_session, user_id=test_user.id, name="Dup", position=0
        )
        for p in (pdf_a, pdf_b, pdf_c):
            await create_test_pdf_collection(
                db_session, pdf_id=p.id, collection_id=col.id
            )
        # A and B have identical embeddings; C has no embedding.
        for pid in (pdf_a.id, pdf_b.id):
            db_session.add(
                PdfSummary(
                    pdf_id=pid,
                    user_id=test_user.id,
                    status="complete",
                    paper_embedding=emb,
                )
            )
        db_session.add(
            PdfSummary(
                pdf_id=pdf_c.id,
                user_id=test_user.id,
                status="complete",
            )
        )
        await db_session.commit()

        response = await client.get(
            f"/v1/collections/{col.id}/duplicates",
            headers=auth_headers,
        )
        assert response.status_code == 200
        pairs = response.json()["pairs"]
        # Only the A-B pair; C is skipped (no embedding).
        assert len(pairs) == 1


class TestOverviewPapersList:
    """Tests for the papers list in the overview response."""

    async def test_overview_includes_papers_with_year_and_author(
        self, client: AsyncClient, auth_headers, db_session, test_user
    ) -> None:
        pdf1 = await create_test_pdf(
            db_session, user_id=test_user.id, title="Paper 1", filename="p1.pdf"
        )
        pdf2 = await create_test_pdf(
            db_session, user_id=test_user.id, title="Paper 2", filename="p2.pdf"
        )
        col = await create_test_collection(
            db_session, user_id=test_user.id, name="O", position=0
        )
        await create_test_pdf_collection(
            db_session, pdf_id=pdf1.id, collection_id=col.id
        )
        await create_test_pdf_collection(
            db_session, pdf_id=pdf2.id, collection_id=col.id
        )
        await create_test_citation(
            db_session,
            pdf_id=pdf1.id,
            user_id=test_user.id,
            authors="Doe, John",
            year=2023,
        )
        await db_session.commit()

        response = await client.get(
            f"/v1/collections/{col.id}/overview",
            headers=auth_headers,
        )
        assert response.status_code == 200
        papers = response.json()["papers"]
        assert len(papers) == 2
        by_title = {p["title"]: p for p in papers}
        assert by_title["Paper 1"]["year"] == 2023
        assert by_title["Paper 1"]["first_author"] == "Doe"
        assert by_title["Paper 2"]["year"] is None
        assert by_title["Paper 2"]["first_author"] is None


class TestCollectionRecommendations:
    """Tests for GET /collections/{id}/recommendations."""

    async def test_frequency_ranking_and_min_citing_filter(
        self, client: AsyncClient, auth_headers, db_session, test_user
    ) -> None:
        # Three members: two cite W1, one cites W2. With min_citing=2, only W1
        # should be suggested with cited_by_count == 2.
        pdf_a = await create_test_pdf(
            db_session, user_id=test_user.id, title="A", filename="a.pdf"
        )
        pdf_b = await create_test_pdf(
            db_session, user_id=test_user.id, title="B", filename="b.pdf"
        )
        pdf_c = await create_test_pdf(
            db_session, user_id=test_user.id, title="C", filename="c.pdf"
        )
        col = await create_test_collection(
            db_session, user_id=test_user.id, name="Recs", position=0
        )
        for p in (pdf_a, pdf_b, pdf_c):
            await create_test_pdf_collection(
                db_session, pdf_id=p.id, collection_id=col.id
            )
            await create_test_citation(
                db_session,
                pdf_id=p.id,
                user_id=test_user.id,
                doi=f"10.1/{p.id.hex[:4]}",
            )
        # Pre-populate summaries with openalex_id + referenced_works so no
        # backfill is needed.
        db_session.add(
            PdfSummary(
                pdf_id=pdf_a.id,
                user_id=test_user.id,
                status="complete",
                openalex_id="MA",
                referenced_openalex_ids=["W1", "W9"],
            )
        )
        db_session.add(
            PdfSummary(
                pdf_id=pdf_b.id,
                user_id=test_user.id,
                status="complete",
                openalex_id="MB",
                referenced_openalex_ids=["W1"],
            )
        )
        db_session.add(
            PdfSummary(
                pdf_id=pdf_c.id,
                user_id=test_user.id,
                status="complete",
                openalex_id="MC",
                referenced_openalex_ids=["W2"],
            )
        )
        await db_session.commit()

        with patch(
            "app.services.openalex_client.fetch_works_batch",
            new_callable=AsyncMock,
            return_value=[
                MagicMock(
                    openalex_id="W1",
                    title="Paper One",
                    authors=["Author A"],
                    year=2020,
                    doi="10.2/w1",
                ),
                MagicMock(
                    openalex_id="W2",
                    title="Paper Two",
                    authors=["Author B"],
                    year=2021,
                    doi="10.2/w2",
                ),
            ],
        ):
            response = await client.get(
                f"/v1/collections/{col.id}/recommendations",
                headers=auth_headers,
            )

        assert response.status_code == 200
        body = response.json()
        # Only W1 meets min_citing=2.
        suggestions = body["suggestions"]
        assert len(suggestions) == 1
        assert suggestions[0]["openalex_id"] == "W1"
        assert suggestions[0]["cited_by_count"] == 2
        assert body["papers_total"] == 3
        assert body["papers_with_refs"] == 3

    async def test_member_openalex_id_excluded(
        self, client: AsyncClient, auth_headers, db_session, test_user
    ) -> None:
        # A referenced work that is itself a member (by openalex_id) must
        # never be suggested, even if cited by many members.
        pdf_a = await create_test_pdf(
            db_session, user_id=test_user.id, title="A", filename="a.pdf"
        )
        pdf_b = await create_test_pdf(
            db_session, user_id=test_user.id, title="B", filename="b.pdf"
        )
        col = await create_test_collection(
            db_session, user_id=test_user.id, name="Recs", position=0
        )
        for p in (pdf_a, pdf_b):
            await create_test_pdf_collection(
                db_session, pdf_id=p.id, collection_id=col.id
            )
            await create_test_citation(
                db_session,
                pdf_id=p.id,
                user_id=test_user.id,
                doi=f"10.1/{p.id.hex[:4]}",
            )
        # Both cite W_MEMBER, which is pdf_b's own openalex_id.
        db_session.add(
            PdfSummary(
                pdf_id=pdf_a.id,
                user_id=test_user.id,
                status="complete",
                openalex_id="MA",
                referenced_openalex_ids=["W_MEMBER"],
            )
        )
        db_session.add(
            PdfSummary(
                pdf_id=pdf_b.id,
                user_id=test_user.id,
                status="complete",
                openalex_id="W_MEMBER",
                referenced_openalex_ids=[],
            )
        )
        await db_session.commit()

        with patch(
            "app.services.openalex_client.fetch_works_batch",
            new_callable=AsyncMock,
            return_value=[],
        ):
            response = await client.get(
                f"/v1/collections/{col.id}/recommendations",
                headers=auth_headers,
            )

        assert response.status_code == 200
        assert response.json()["suggestions"] == []
        # W_MEMBER was filtered by the counter (member openalex_id), so the
        # batch was called with an empty id list (no real resolution needed).

    async def test_backfill_creates_summary_row_and_caches(
        self, client: AsyncClient, auth_headers, db_session, test_user
    ) -> None:
        # Member with a DOI but no PdfSummary row -> row created and refs
        # stored; second call does no DOI fetch.
        pdf = await create_test_pdf(
            db_session, user_id=test_user.id, title="A", filename="a.pdf"
        )
        col = await create_test_collection(
            db_session, user_id=test_user.id, name="Recs", position=0
        )
        await create_test_pdf_collection(
            db_session, pdf_id=pdf.id, collection_id=col.id
        )
        await create_test_citation(
            db_session,
            pdf_id=pdf.id,
            user_id=test_user.id,
            doi="10.1/abc",
        )
        await db_session.commit()

        fetch_by_doi = AsyncMock(
            return_value=MagicMock(
                openalex_id="W_NEW",
                referenced_works=["W_EXT1", "W_EXT2"],
            )
        )
        with patch(
            "app.services.openalex_client.fetch_work_by_doi",
            new=fetch_by_doi,
        ):
            response = await client.get(
                f"/v1/collections/{col.id}/recommendations",
                headers=auth_headers,
            )
            assert response.status_code == 200

        # The summary row was created and cached.
        assert fetch_by_doi.call_count == 1
        # Reload the row from the DB to verify persistence.
        await db_session.commit()  # ensure the route's commit is visible
        from sqlalchemy import select

        row = (
            await db_session.execute(
                select(PdfSummary).where(
                    PdfSummary.pdf_id == pdf.id,
                    PdfSummary.user_id == test_user.id,
                )
            )
        ).scalar_one()
        assert row.openalex_id == "W_NEW"
        assert row.referenced_openalex_ids == ["W_EXT1", "W_EXT2"]

        # Second call: openalex_id is set, so no DOI fetch this time.
        fetch_by_doi2 = AsyncMock(return_value=MagicMock())
        with patch(
            "app.services.openalex_client.fetch_work_by_doi",
            new=fetch_by_doi2,
        ):
            response = await client.get(
                f"/v1/collections/{col.id}/recommendations",
                headers=auth_headers,
            )
            assert response.status_code == 200
        assert fetch_by_doi2.call_count == 0

    async def test_not_found_doi_stores_sentinel(
        self, client: AsyncClient, auth_headers, db_session, test_user
    ) -> None:
        # fetch_work_by_doi returns None -> sentinel stored; next call skips.
        pdf = await create_test_pdf(
            db_session, user_id=test_user.id, title="A", filename="a.pdf"
        )
        col = await create_test_collection(
            db_session, user_id=test_user.id, name="Recs", position=0
        )
        await create_test_pdf_collection(
            db_session, pdf_id=pdf.id, collection_id=col.id
        )
        await create_test_citation(
            db_session,
            pdf_id=pdf.id,
            user_id=test_user.id,
            doi="10.1/missing",
        )
        await db_session.commit()

        fetch_by_doi = AsyncMock(return_value=None)
        with patch(
            "app.services.openalex_client.fetch_work_by_doi",
            new=fetch_by_doi,
        ):
            response = await client.get(
                f"/v1/collections/{col.id}/recommendations",
                headers=auth_headers,
            )
            assert response.status_code == 200
        assert fetch_by_doi.call_count == 1

        # Second call: sentinel is set, so no DOI fetch.
        fetch_by_doi2 = AsyncMock(return_value=None)
        with patch(
            "app.services.openalex_client.fetch_work_by_doi",
            new=fetch_by_doi2,
        ):
            response = await client.get(
                f"/v1/collections/{col.id}/recommendations",
                headers=auth_headers,
            )
            assert response.status_code == 200
        assert fetch_by_doi2.call_count == 0

    async def test_http_error_skips_member_but_keeps_200(
        self, client: AsyncClient, auth_headers, db_session, test_user
    ) -> None:
        # fetch_work_by_doi raises httpx.HTTPError for one member -> response
        # still 200, that member just missing from papers_with_refs.
        pdf_a = await create_test_pdf(
            db_session, user_id=test_user.id, title="A", filename="a.pdf"
        )
        pdf_b = await create_test_pdf(
            db_session, user_id=test_user.id, title="B", filename="b.pdf"
        )
        col = await create_test_collection(
            db_session, user_id=test_user.id, name="Recs", position=0
        )
        for p in (pdf_a, pdf_b):
            await create_test_pdf_collection(
                db_session, pdf_id=p.id, collection_id=col.id
            )
            await create_test_citation(
                db_session,
                pdf_id=p.id,
                user_id=test_user.id,
                doi=f"10.1/{p.id.hex[:4]}",
            )
        await db_session.commit()

        call_count = {"n": 0}

        async def _side_effect(doi):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise httpx.ConnectError("refused")
            return MagicMock(
                openalex_id="W_OK",
                referenced_works=["W_SUG"],
            )

        with (
            patch(
                "app.services.openalex_client.fetch_work_by_doi",
                new=_side_effect,
            ),
            patch(
                "app.services.openalex_client.fetch_works_batch",
                new_callable=AsyncMock,
                return_value=[
                    MagicMock(
                        openalex_id="W_SUG",
                        title="Suggested",
                        authors=["X"],
                        year=2019,
                        doi="10.2/sug",
                    )
                ],
            ),
        ):
            response = await client.get(
                f"/v1/collections/{col.id}/recommendations",
                headers=auth_headers,
            )

        assert response.status_code == 200
        body = response.json()
        # The non-erroring member contributed references; the other did not.
        assert body["papers_with_refs"] == 1
        assert body["papers_total"] == 2

    async def test_pdf_doi_used_when_no_citation_row(
        self, client: AsyncClient, auth_headers, db_session, test_user
    ) -> None:
        # A paper with Pdf.doi but no Citation row (extraction not run) should
        # still contribute references via the Pdf.doi fallback.
        pdf_a = await create_test_pdf(
            db_session,
            user_id=test_user.id,
            title="A",
            filename="a.pdf",
            doi="10.1/from-pdf-a",
        )
        pdf_b = await create_test_pdf(
            db_session,
            user_id=test_user.id,
            title="B",
            filename="b.pdf",
            doi="10.1/from-pdf-b",
        )
        col = await create_test_collection(
            db_session, user_id=test_user.id, name="Recs", position=0
        )
        for p in (pdf_a, pdf_b):
            await create_test_pdf_collection(
                db_session, pdf_id=p.id, collection_id=col.id
            )
        # NOTE: no create_test_citation calls — DOIs live on Pdf only.
        # Pre-populate summaries so no backfill is needed.
        db_session.add(
            PdfSummary(
                pdf_id=pdf_a.id,
                user_id=test_user.id,
                status="complete",
                openalex_id="MA",
                referenced_openalex_ids=["W_SHARED"],
            )
        )
        db_session.add(
            PdfSummary(
                pdf_id=pdf_b.id,
                user_id=test_user.id,
                status="complete",
                openalex_id="MB",
                referenced_openalex_ids=["W_SHARED"],
            )
        )
        await db_session.commit()

        with patch(
            "app.services.openalex_client.fetch_works_batch",
            new_callable=AsyncMock,
            return_value=[
                MagicMock(
                    openalex_id="W_SHARED",
                    title="Shared Ref",
                    authors=["Author"],
                    year=2019,
                    doi="10.2/shared",
                ),
            ],
        ):
            response = await client.get(
                f"/v1/collections/{col.id}/recommendations",
                headers=auth_headers,
            )

        assert response.status_code == 200
        body = response.json()
        # Both papers contributed references despite having no Citation rows.
        assert body["papers_with_refs"] == 2
        assert body["papers_without_doi"] == 0
        suggestions = body["suggestions"]
        assert len(suggestions) == 1
        assert suggestions[0]["openalex_id"] == "W_SHARED"
        assert suggestions[0]["cited_by_count"] == 2
