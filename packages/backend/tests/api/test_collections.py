"""Tests for collection routes."""
import uuid
from httpx import AsyncClient
from tests.fixtures import create_test_pdf, create_test_collection, create_test_pdf_collection


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

    async def test_create_collection_with_parent(self, client: AsyncClient, auth_headers, db_session, test_user) -> None:
        """Test creating a nested collection."""
        parent = await create_test_collection(db_session, user_id=test_user.id, name="Parent", position=0)
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

    async def test_create_collection_invalid_parent_returns_400(self, client: AsyncClient, auth_headers) -> None:
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

    async def test_list_collections_returns_user_collections(self, client: AsyncClient, auth_headers, db_session, test_user, test_user_2) -> None:
        """Test listing returns only user's collections."""
        await create_test_collection(db_session, user_id=test_user.id, name="My Collection 1", position=0)
        await create_test_collection(db_session, user_id=test_user.id, name="My Collection 2", position=1)
        # Other user's collection
        await create_test_collection(db_session, user_id=test_user_2.id, name="Other's Collection", position=0)
        await db_session.commit()

        response = await client.get(
            "/v1/collections",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert all(c["user_id"] == str(test_user.id) for c in data)

    async def test_list_collections_ordered_by_position(self, client: AsyncClient, auth_headers, db_session, test_user) -> None:
        """Test collections are ordered by position."""
        await create_test_collection(db_session, user_id=test_user.id, name="First", position=1)
        await create_test_collection(db_session, user_id=test_user.id, name="Second", position=0)
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

    async def test_update_collection(self, client: AsyncClient, auth_headers, db_session, test_user) -> None:
        """Test updating collection name."""
        col = await create_test_collection(db_session, user_id=test_user.id, name="Original", position=0)
        await db_session.commit()

        response = await client.patch(
            f"/v1/collections/{col.id}",
            json={"name": "Updated"},
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated"

    async def test_update_other_users_collection_returns_404(self, client: AsyncClient, auth_headers) -> None:
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

    async def test_delete_collection(self, client: AsyncClient, auth_headers, db_session, test_user) -> None:
        """Test deleting a collection."""
        from sqlalchemy import select
        from app.db.models import Collection

        col = await create_test_collection(db_session, user_id=test_user.id, name="To Delete", position=0)
        await db_session.commit()

        response = await client.delete(
            f"/v1/collections/{col.id}",
            headers=auth_headers,
        )

        assert response.status_code == 200

        # Verify it's gone
        result = await db_session.execute(select(Collection).where(Collection.id == col.id))
        assert result.scalar_one_or_none() is None

    async def test_delete_collection_cascades_pdf_associations(self, client: AsyncClient, auth_headers, db_session, test_user) -> None:
        """Test deleting collection removes PDF associations."""
        from sqlalchemy import select
        from app.db.models import PdfCollection

        pdf = await create_test_pdf(db_session, user_id=test_user.id)
        col = await create_test_collection(db_session, user_id=test_user.id, name="To Delete", position=0)

        await create_test_pdf_collection(db_session, pdf_id=pdf.id, collection_id=col.id)
        await db_session.commit()

        await client.delete(
            f"/v1/collections/{col.id}",
            headers=auth_headers,
        )

        # Verify association is gone (cascade)
        result = await db_session.execute(select(PdfCollection).where(PdfCollection.collection_id == col.id))
        assert result.scalar_one_or_none() is None


class TestAddPdfToCollection:
    """Tests for POST /v1/collections/{collection_id}/pdfs"""

    async def test_add_pdf_to_collection(self, client: AsyncClient, auth_headers, db_session, test_user) -> None:
        """Test adding a PDF to a collection."""
        pdf = await create_test_pdf(db_session, user_id=test_user.id)
        col = await create_test_collection(db_session, user_id=test_user.id, name="Research", position=0)
        await db_session.commit()

        response = await client.post(
            f"/v1/collections/{col.id}/pdfs",
            params={"pdf_id": str(pdf.id)},
            headers=auth_headers,
        )

        assert response.status_code == 200
        assert "added to collection" in response.json()["message"].lower()

    async def test_add_pdf_other_users_collection_returns_404(self, client: AsyncClient, auth_headers, db_session, test_user, test_user_2) -> None:
        """Test adding PDF to another user's collection returns 404."""
        pdf = await create_test_pdf(db_session, user_id=test_user.id, title="My PDF", filename="my.pdf")
        col = await create_test_collection(db_session, user_id=test_user_2.id, name="Other's", position=0)
        await db_session.commit()

        response = await client.post(
            f"/v1/collections/{col.id}/pdfs",
            params={"pdf_id": str(pdf.id)},
            headers=auth_headers,
        )

        assert response.status_code == 404

    async def test_add_other_users_pdf_returns_404(self, client: AsyncClient, auth_headers, db_session, test_user, test_user_2) -> None:
        """Test adding another user's PDF returns 404."""
        pdf = await create_test_pdf(db_session, user_id=test_user_2.id, title="Other's PDF", filename="other.pdf")
        col = await create_test_collection(db_session, user_id=test_user.id, name="Mine", position=0)
        await db_session.commit()

        response = await client.post(
            f"/v1/collections/{col.id}/pdfs",
            params={"pdf_id": str(pdf.id)},
            headers=auth_headers,
        )

        assert response.status_code == 404


class TestRemovePdfFromCollection:
    """Tests for DELETE /v1/collections/{collection_id}/pdfs/{pdf_id}"""

    async def test_remove_pdf_from_collection(self, client: AsyncClient, auth_headers, db_session, test_user) -> None:
        """Test removing a PDF from a collection."""
        from sqlalchemy import select
        from app.db.models import PdfCollection

        pdf = await create_test_pdf(db_session, user_id=test_user.id)
        col = await create_test_collection(db_session, user_id=test_user.id, name="Research", position=0)

        await create_test_pdf_collection(db_session, pdf_id=pdf.id, collection_id=col.id)
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

    async def test_remove_pdf_not_in_collection_returns_404(self, client: AsyncClient, auth_headers, db_session, test_user) -> None:
        """Test removing PDF that's not in collection returns 404."""
        pdf = await create_test_pdf(db_session, user_id=test_user.id)
        col = await create_test_collection(db_session, user_id=test_user.id, name="Research", position=0)
        await db_session.commit()

        response = await client.delete(
            f"/v1/collections/{col.id}/pdfs/{pdf.id}",
            headers=auth_headers,
        )

        assert response.status_code == 404
