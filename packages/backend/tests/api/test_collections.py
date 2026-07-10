"""Tests for collection routes."""

import asyncio
import uuid
from datetime import date
from httpx import AsyncClient
from unittest.mock import AsyncMock, MagicMock, patch

from app.db.models import PdfSummary, UserUsageQuota
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
