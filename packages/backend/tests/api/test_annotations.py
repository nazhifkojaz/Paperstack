"""Tests for annotation routes."""
import uuid
from httpx import AsyncClient
from tests.fixtures import create_test_pdf, create_test_annotation_set, create_test_annotation


class TestListAnnotationSets:
    """Tests for GET /v1/annotations/sets"""

    async def test_list_annotation_sets_by_pdf(self, client: AsyncClient, auth_headers, db_session, test_user) -> None:
        """Test listing annotation sets for a specific PDF."""
        pdf = await create_test_pdf(db_session, user_id=test_user.id, title="Test PDF", filename="test.pdf", github_sha="abc")
        await create_test_annotation_set(db_session, pdf_id=pdf.id, user_id=test_user.id, name="Set 1", color="#FFFF00")
        await create_test_annotation_set(db_session, pdf_id=pdf.id, user_id=test_user.id, name="Set 2", color="#FF0000")
        await db_session.commit()

        response = await client.get(
            f"/v1/annotations/sets?pdf_id={pdf.id}",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert any(s["name"] == "Set 1" for s in data)
        assert any(s["name"] == "Set 2" for s in data)

    async def test_list_annotation_sets_other_users_pdf_returns_404(self, client: AsyncClient, auth_headers, db_session, test_user_2) -> None:
        """Test listing sets for another user's PDF returns 404."""
        pdf = await create_test_pdf(db_session, user_id=test_user_2.id, title="Other's PDF", filename="other.pdf", github_sha="abc")
        await create_test_annotation_set(db_session, pdf_id=pdf.id, user_id=test_user_2.id, name="Other's Set")
        await db_session.commit()

        response = await client.get(
            f"/v1/annotations/sets?pdf_id={pdf.id}",
            headers=auth_headers,
        )

        assert response.status_code == 404


class TestCreateAnnotationSet:
    """Tests for POST /v1/annotations/sets"""

    async def test_create_annotation_set(self, client: AsyncClient, auth_headers, db_session, test_user) -> None:
        """Test creating a new annotation set."""
        pdf = await create_test_pdf(db_session, user_id=test_user.id, title="Test PDF", filename="test.pdf", github_sha="abc")
        await db_session.commit()

        response = await client.post(
            "/v1/annotations/sets",
            json={
                "pdf_id": str(pdf.id),
                "name": "My Annotations",
                "color": "#00FF00",
            },
            headers=auth_headers,
        )

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "My Annotations"
        assert data["color"] == "#00FF00"
        assert "id" in data

    async def test_create_annotation_set_other_users_pdf_returns_404(self, client: AsyncClient, auth_headers) -> None:
        """Test creating set for another user's PDF returns 404."""
        fake_pdf_id = uuid.uuid4()

        response = await client.post(
            "/v1/annotations/sets",
            json={
                "pdf_id": str(fake_pdf_id),
                "name": "Should Fail",
            },
            headers=auth_headers,
        )

        assert response.status_code == 404


class TestUpdateAnnotationSet:
    """Tests for PATCH /v1/annotations/sets/{set_id}"""

    async def test_update_annotation_set(self, client: AsyncClient, auth_headers, db_session, test_user) -> None:
        """Test updating an annotation set."""
        pdf = await create_test_pdf(db_session, user_id=test_user.id, title="Test PDF", filename="test.pdf", github_sha="abc")
        ann_set = await create_test_annotation_set(db_session, pdf_id=pdf.id, user_id=test_user.id, name="Original Name", color="#FFFF00")
        await db_session.commit()

        response = await client.patch(
            f"/v1/annotations/sets/{ann_set.id}",
            json={"name": "Updated Name", "color": "#FF0000"},
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Name"
        assert data["color"] == "#FF0000"

    async def test_update_other_users_set_returns_404(self, client: AsyncClient, auth_headers, db_session, test_user_2) -> None:
        """Test updating another user's set returns 404."""
        pdf = await create_test_pdf(db_session, user_id=test_user_2.id, title="Other PDF", filename="other.pdf", github_sha="abc")
        ann_set = await create_test_annotation_set(db_session, pdf_id=pdf.id, user_id=test_user_2.id, name="Other's Set")
        await db_session.commit()

        response = await client.patch(
            f"/v1/annotations/sets/{ann_set.id}",
            json={"name": "Hacked"},
            headers=auth_headers,
        )

        assert response.status_code == 404


class TestDeleteAnnotationSet:
    """Tests for DELETE /v1/annotations/sets/{set_id}"""

    async def test_delete_annotation_set(self, client: AsyncClient, auth_headers, db_session, test_user) -> None:
        """Test deleting an annotation set."""
        from sqlalchemy import select
        from app.db.models import Annotation

        pdf = await create_test_pdf(db_session, user_id=test_user.id, title="Test PDF", filename="test.pdf", github_sha="abc")
        ann_set = await create_test_annotation_set(db_session, pdf_id=pdf.id, user_id=test_user.id, name="To Delete")
        await create_test_annotation(db_session, set_id=ann_set.id, page_number=1)
        await db_session.commit()

        response = await client.delete(
            f"/v1/annotations/sets/{ann_set.id}",
            headers=auth_headers,
        )

        assert response.status_code == 204

        # Verify annotations are cascade deleted
        result = await db_session.execute(select(Annotation).where(Annotation.set_id == ann_set.id))
        assert result.scalar_one_or_none() is None

    async def test_delete_other_users_set_returns_404(self, client: AsyncClient, auth_headers, db_session, test_user_2) -> None:
        """Test deleting another user's set returns 404."""
        pdf = await create_test_pdf(db_session, user_id=test_user_2.id, title="Other PDF", filename="other.pdf", github_sha="abc")
        ann_set = await create_test_annotation_set(db_session, pdf_id=pdf.id, user_id=test_user_2.id, name="Other's Set")
        await db_session.commit()

        response = await client.delete(
            f"/v1/annotations/sets/{ann_set.id}",
            headers=auth_headers,
        )

        assert response.status_code == 404


class TestListAnnotations:
    """Tests for GET /v1/annotations/sets/{set_id}/items"""

    async def test_list_annotations_in_set(self, client: AsyncClient, auth_headers, db_session, test_user) -> None:
        """Test listing annotations in a set."""
        pdf = await create_test_pdf(db_session, user_id=test_user.id, title="Test PDF", filename="test.pdf", github_sha="abc", page_count=2)
        ann_set = await create_test_annotation_set(db_session, pdf_id=pdf.id, user_id=test_user.id, name="Test Set")
        await create_test_annotation(db_session, set_id=ann_set.id, page_number=1, type="highlight")
        await create_test_annotation(db_session, set_id=ann_set.id, page_number=2, type="note", note_content="Test note")
        await db_session.commit()

        response = await client.get(
            f"/v1/annotations/sets/{ann_set.id}/items",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2


class TestCreateAnnotation:
    """Tests for POST /v1/annotations/items"""

    async def test_create_annotation(self, client: AsyncClient, auth_headers, db_session, test_user) -> None:
        """Test creating a new annotation."""
        pdf = await create_test_pdf(db_session, user_id=test_user.id, title="Test PDF", filename="test.pdf", github_sha="abc")
        ann_set = await create_test_annotation_set(db_session, pdf_id=pdf.id, user_id=test_user.id, name="Test Set")
        await db_session.commit()

        response = await client.post(
            "/v1/annotations/items",
            json={
                "set_id": str(ann_set.id),
                "page_number": 1,
                "type": "highlight",
                "rects": [{"x": 0.1, "y": 0.1, "w": 0.2, "h": 0.2}],
                "selected_text": "Selected text",
                "color": "#FFFF00",
            },
            headers=auth_headers,
        )

        assert response.status_code == 201
        data = response.json()
        assert data["type"] == "highlight"
        assert data["page_number"] == 1
        assert data["selected_text"] == "Selected text"

    async def test_create_annotation_other_users_set_returns_404(self, client: AsyncClient, auth_headers) -> None:
        """Test creating annotation in another user's set returns 404."""
        fake_set_id = uuid.uuid4()

        response = await client.post(
            "/v1/annotations/items",
            json={
                "set_id": str(fake_set_id),
                "page_number": 1,
                "type": "highlight",
                "rects": [{"x": 0, "y": 0, "w": 0.1, "h": 0.1}],
            },
            headers=auth_headers,
        )

        assert response.status_code == 404


class TestUpdateAnnotation:
    """Tests for PATCH /v1/annotations/items/{ann_id}"""

    async def test_update_annotation(self, client: AsyncClient, auth_headers, db_session, test_user) -> None:
        """Test updating an annotation."""
        pdf = await create_test_pdf(db_session, user_id=test_user.id, title="Test PDF", filename="test.pdf", github_sha="abc")
        ann_set = await create_test_annotation_set(db_session, pdf_id=pdf.id, user_id=test_user.id, name="Test Set")
        ann = await create_test_annotation(db_session, set_id=ann_set.id, page_number=1, type="highlight")
        await db_session.commit()

        response = await client.patch(
            f"/v1/annotations/items/{ann.id}",
            json={
                "color": "#FF0000",
                "note_content": "Updated note",
            },
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["color"] == "#FF0000"
        assert data["note_content"] == "Updated note"

    async def test_update_other_users_annotation_returns_404(self, client: AsyncClient, auth_headers, db_session, test_user_2) -> None:
        """Test updating another user's annotation returns 404."""
        pdf = await create_test_pdf(db_session, user_id=test_user_2.id, title="Other PDF", filename="other.pdf", github_sha="abc")
        ann_set = await create_test_annotation_set(db_session, pdf_id=pdf.id, user_id=test_user_2.id, name="Other's Set")
        ann = await create_test_annotation(db_session, set_id=ann_set.id, page_number=1, type="highlight")
        await db_session.commit()

        response = await client.patch(
            f"/v1/annotations/items/{ann.id}",
            json={"color": "#FF0000"},
            headers=auth_headers,
        )

        assert response.status_code == 404


class TestDeleteAnnotation:
    """Tests for DELETE /v1/annotations/items/{ann_id}"""

    async def test_delete_annotation(self, client: AsyncClient, auth_headers, db_session, test_user) -> None:
        """Test deleting an annotation."""
        from sqlalchemy import select
        from app.db.models import Annotation

        pdf = await create_test_pdf(db_session, user_id=test_user.id, title="Test PDF", filename="test.pdf", github_sha="abc")
        ann_set = await create_test_annotation_set(db_session, pdf_id=pdf.id, user_id=test_user.id, name="Test Set")
        ann = await create_test_annotation(db_session, set_id=ann_set.id, page_number=1, type="highlight")
        await db_session.commit()

        response = await client.delete(
            f"/v1/annotations/items/{ann.id}",
            headers=auth_headers,
        )

        assert response.status_code == 204

        # Verify it's gone
        result = await db_session.execute(select(Annotation).where(Annotation.id == ann.id))
        assert result.scalar_one_or_none() is None

    async def test_delete_other_users_annotation_returns_404(self, client: AsyncClient, auth_headers, db_session, test_user_2) -> None:
        """Test deleting another user's annotation returns 404."""
        pdf = await create_test_pdf(db_session, user_id=test_user_2.id, title="Other PDF", filename="other.pdf", github_sha="abc")
        ann_set = await create_test_annotation_set(db_session, pdf_id=pdf.id, user_id=test_user_2.id, name="Other's Set")
        ann = await create_test_annotation(db_session, set_id=ann_set.id, page_number=1, type="highlight")
        await db_session.commit()

        response = await client.delete(
            f"/v1/annotations/items/{ann.id}",
            headers=auth_headers,
        )

        assert response.status_code == 404
