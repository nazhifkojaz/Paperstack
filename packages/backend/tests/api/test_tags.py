"""Tests for tag routes."""
import uuid
import datetime
import pytest
from httpx import AsyncClient
from tests.fixtures import create_test_pdf, create_test_tag


class TestCreateTag:
    """Tests for POST /v1/tags"""

    async def test_create_tag(self, client: AsyncClient, auth_headers) -> None:
        """Test creating a new tag."""
        response = await client.post(
            "/v1/tags",
            json={"name": "Important", "color": "#FF0000"},
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Important"
        assert data["color"] == "#FF0000"

    async def test_create_duplicate_tag_returns_400(self, client: AsyncClient, auth_headers, db_session, test_user) -> None:
        """Test creating duplicate tag name returns 400."""
        await create_test_tag(db_session, user_id=test_user.id, name="Important", color="#FF0000")
        await db_session.commit()

        response = await client.post(
            "/v1/tags",
            json={"name": "Important", "color": "#00FF00"},
            headers=auth_headers,
        )

        assert response.status_code == 400
        assert "already exists" in response.json()["detail"]


class TestListTags:
    """Tests for GET /v1/tags"""

    async def test_list_tags_returns_user_tags(self, client: AsyncClient, auth_headers, db_session, test_user, test_user_2) -> None:
        """Test listing returns only user's tags."""
        await create_test_tag(db_session, user_id=test_user.id, name="Tag 1", color="#FF0000")
        await create_test_tag(db_session, user_id=test_user.id, name="Tag 2", color="#00FF00")
        # Other user's tag
        await create_test_tag(db_session, user_id=test_user_2.id, name="Other's Tag", color="#0000FF")
        await db_session.commit()

        response = await client.get(
            "/v1/tags",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert all(t["user_id"] == str(test_user.id) for t in data)

    async def test_list_tags_ordered_by_name(self, client: AsyncClient, auth_headers, db_session, test_user) -> None:
        """Test tags are ordered by name."""
        await create_test_tag(db_session, user_id=test_user.id, name="Zebra", color="#FF0000")
        await create_test_tag(db_session, user_id=test_user.id, name="Apple", color="#00FF00")
        await db_session.commit()

        response = await client.get(
            "/v1/tags",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data[0]["name"] == "Apple"
        assert data[1]["name"] == "Zebra"


class TestUpdateTag:
    """Tests for PATCH /v1/tags/{tag_id}"""

    async def test_update_tag(self, client: AsyncClient, auth_headers, db_session, test_user) -> None:
        """Test updating tag."""
        tag = await create_test_tag(db_session, user_id=test_user.id, name="Original", color="#FF0000")
        await db_session.commit()

        response = await client.patch(
            f"/v1/tags/{tag.id}",
            json={"name": "Updated", "color": "#00FF00"},
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated"
        assert data["color"] == "#00FF00"

    async def test_update_other_users_tag_returns_404(self, client: AsyncClient, auth_headers, db_session, test_user, test_user_2) -> None:
        """Test updating another user's tag returns 404."""
        tag = await create_test_tag(db_session, user_id=test_user_2.id, name="Other's", color="#FF0000")
        await db_session.commit()

        response = await client.patch(
            f"/v1/tags/{tag.id}",
            json={"name": "Hacked"},
            headers=auth_headers,
        )

        assert response.status_code == 404

    async def test_update_tag_duplicate_name_returns_400(self, client: AsyncClient, auth_headers, db_session, test_user) -> None:
        """Test updating to duplicate name returns 400."""
        tag1 = await create_test_tag(db_session, user_id=test_user.id, name="Tag 1", color="#FF0000")
        tag2 = await create_test_tag(db_session, user_id=test_user.id, name="Tag 2", color="#00FF00")
        await db_session.commit()

        response = await client.patch(
            f"/v1/tags/{tag1.id}",
            json={"name": "Tag 2"},
            headers=auth_headers,
        )

        assert response.status_code == 400


class TestDeleteTag:
    """Tests for DELETE /v1/tags/{tag_id}"""

    async def test_delete_tag(self, client: AsyncClient, auth_headers, db_session, test_user) -> None:
        """Test deleting a tag."""
        from app.db.models import Tag
        from sqlalchemy import select

        tag = await create_test_tag(db_session, user_id=test_user.id, name="To Delete", color="#FF0000")
        await db_session.commit()

        response = await client.delete(
            f"/v1/tags/{tag.id}",
            headers=auth_headers,
        )

        assert response.status_code == 200

        # Verify it's gone
        result = await db_session.execute(select(Tag).where(Tag.id == tag.id))
        assert result.scalar_one_or_none() is None

    async def test_delete_other_users_tag_returns_404(self, client: AsyncClient, auth_headers, db_session, test_user, test_user_2) -> None:
        """Test deleting another user's tag returns 404."""
        tag = await create_test_tag(db_session, user_id=test_user_2.id, name="Other's", color="#FF0000")
        await db_session.commit()

        response = await client.delete(
            f"/v1/tags/{tag.id}",
            headers=auth_headers,
        )

        assert response.status_code == 404


class TestAddTagToPdf:
    """Tests for POST /v1/tags/pdfs/{pdf_id}/tags/{tag_id}"""

    async def test_add_tag_to_pdf(self, client: AsyncClient, auth_headers, db_session, test_user) -> None:
        """Test adding a tag to a PDF."""
        pdf = await create_test_pdf(db_session, user_id=test_user.id)
        tag = await create_test_tag(db_session, user_id=test_user.id, name="Important", color="#FF0000")
        await db_session.commit()

        response = await client.post(
            f"/v1/tags/pdfs/{pdf.id}/tags/{tag.id}",
            headers=auth_headers,
        )

        assert response.status_code == 200
        assert "added to pdf" in response.json()["message"].lower()

    async def test_add_tag_already_assigned_returns_400(self, client: AsyncClient, auth_headers, db_session, test_user) -> None:
        """Test adding already assigned tag returns 400."""
        from app.db.models import PdfTag

        pdf = await create_test_pdf(db_session, user_id=test_user.id)
        tag = await create_test_tag(db_session, user_id=test_user.id, name="Important", color="#FF0000")
        await db_session.flush()

        pt = PdfTag(pdf_id=pdf.id, tag_id=tag.id)
        db_session.add(pt)
        await db_session.commit()

        response = await client.post(
            f"/v1/tags/pdfs/{pdf.id}/tags/{tag.id}",
            headers=auth_headers,
        )

        assert response.status_code == 400

    async def test_add_other_users_tag_returns_404(self, client: AsyncClient, auth_headers, db_session, test_user, test_user_2) -> None:
        """Test adding another user's tag returns 404."""
        pdf = await create_test_pdf(db_session, user_id=test_user.id, title="My PDF", filename="my.pdf")
        tag = await create_test_tag(db_session, user_id=test_user_2.id, name="Other's", color="#FF0000")
        await db_session.commit()

        response = await client.post(
            f"/v1/tags/pdfs/{pdf.id}/tags/{tag.id}",
            headers=auth_headers,
        )

        assert response.status_code == 404


class TestRemoveTagFromPdf:
    """Tests for DELETE /v1/tags/pdfs/{pdf_id}/tags/{tag_id}"""

    async def test_remove_tag_from_pdf(self, client: AsyncClient, auth_headers, db_session, test_user) -> None:
        """Test removing a tag from a PDF."""
        from app.db.models import PdfTag
        from sqlalchemy import select

        pdf = await create_test_pdf(db_session, user_id=test_user.id)
        tag = await create_test_tag(db_session, user_id=test_user.id, name="Important", color="#FF0000")
        await db_session.flush()

        pt = PdfTag(pdf_id=pdf.id, tag_id=tag.id)
        db_session.add(pt)
        await db_session.commit()

        response = await client.delete(
            f"/v1/tags/pdfs/{pdf.id}/tags/{tag.id}",
            headers=auth_headers,
        )

        assert response.status_code == 200

        # Verify association is removed
        result = await db_session.execute(
            select(PdfTag).where(
                PdfTag.pdf_id == pdf.id,
                PdfTag.tag_id == tag.id,
            )
        )
        assert result.scalar_one_or_none() is None

    async def test_remove_tag_not_assigned_returns_404(self, client: AsyncClient, auth_headers, db_session, test_user) -> None:
        """Test removing unassigned tag returns 404."""
        pdf = await create_test_pdf(db_session, user_id=test_user.id)
        tag = await create_test_tag(db_session, user_id=test_user.id, name="Important", color="#FF0000")
        await db_session.commit()

        response = await client.delete(
            f"/v1/tags/pdfs/{pdf.id}/tags/{tag.id}",
            headers=auth_headers,
        )

        assert response.status_code == 404
