"""Tests for sharing routes."""
import uuid
from httpx import AsyncClient
from tests.fixtures import create_test_pdf, create_test_annotation_set, create_test_annotation, create_test_share
from app.db.models import Share


class TestCreateShare:
    """Tests for POST /v1/annotation-sets/{set_id}/share"""

    async def test_create_public_share(self, client: AsyncClient, auth_headers, db_session, test_user) -> None:
        """Test creating a public share link."""
        pdf = await create_test_pdf(db_session, user_id=test_user.id)
        ann_set = await create_test_annotation_set(db_session, pdf_id=pdf.id, user_id=test_user.id)
        await db_session.commit()

        response = await client.post(
            f"/v1/annotation-sets/{ann_set.id}/share",
            json={"permission": "view"},
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert "share_token" in data
        assert data["permission"] == "view"
        assert data["shared_with"] is None

    async def test_create_user_specific_share(self, client: AsyncClient, auth_headers, db_session, test_user, test_user_2) -> None:
        """Test creating a share for a specific user."""
        pdf = await create_test_pdf(db_session, user_id=test_user.id)
        ann_set = await create_test_annotation_set(db_session, pdf_id=pdf.id, user_id=test_user.id)
        await db_session.commit()

        response = await client.post(
            f"/v1/annotation-sets/{ann_set.id}/share",
            json={
                "permission": "comment",
                "shared_with_github_login": test_user_2.github_login,
            },
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["shared_with"] == str(test_user_2.id)

    async def test_create_share_invalid_user_returns_404(self, client: AsyncClient, auth_headers, db_session, test_user) -> None:
        """Test creating share for non-existent user returns 404."""
        pdf = await create_test_pdf(db_session, user_id=test_user.id)
        ann_set = await create_test_annotation_set(db_session, pdf_id=pdf.id, user_id=test_user.id)
        await db_session.commit()

        response = await client.post(
            f"/v1/annotation-sets/{ann_set.id}/share",
            json={
                "permission": "view",
                "shared_with_github_login": "nonexistentuser",
            },
            headers=auth_headers,
        )

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    async def test_create_share_other_users_set_returns_404(self, client: AsyncClient, auth_headers) -> None:
        """Test creating share for another user's set returns 404."""
        fake_set_id = uuid.uuid4()

        response = await client.post(
            f"/v1/annotation-sets/{fake_set_id}/share",
            json={"permission": "view"},
            headers=auth_headers,
        )

        assert response.status_code == 404


class TestSharedWithMe:
    """Tests for GET /v1/shared/with-me"""

    async def test_list_shared_with_me(self, client: AsyncClient, auth_headers_2, db_session, test_user, test_user_2) -> None:
        """Test listing shares received by current user."""
        # Create a share from test_user to test_user_2
        pdf = await create_test_pdf(db_session, user_id=test_user.id)
        ann_set = await create_test_annotation_set(db_session, pdf_id=pdf.id, user_id=test_user.id, name="Shared Set")

        await create_test_share(
            db_session,
            annotation_set_id=ann_set.id,
            shared_by=test_user.id,
            shared_with=test_user_2.id,
            share_token="test_token_123",
            permission="view",
        )
        await db_session.commit()

        # List shares for test_user_2
        response = await client.get(
            "/v1/shared/with-me",
            headers=auth_headers_2,
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["shared_by"] == str(test_user.id)


class TestRevokeShare:
    """Tests for DELETE /v1/shares/{share_id}"""

    async def test_revoke_share(self, client: AsyncClient, auth_headers, db_session, test_user) -> None:
        """Test revoking a share."""
        from sqlalchemy import select

        pdf = await create_test_pdf(db_session, user_id=test_user.id)
        ann_set = await create_test_annotation_set(db_session, pdf_id=pdf.id, user_id=test_user.id, name="Shared Set")

        share = await create_test_share(
            db_session,
            annotation_set_id=ann_set.id,
            shared_by=test_user.id,
            share_token="test_token_revoke",
            permission="view",
        )
        await db_session.commit()

        response = await client.delete(
            f"/v1/shares/{share.id}",
            headers=auth_headers,
        )

        assert response.status_code == 204

        # Verify it's gone
        result = await db_session.execute(select(Share).where(Share.id == share.id))
        assert result.scalar_one_or_none() is None

    async def test_revoke_other_users_share_returns_404(self, client: AsyncClient, auth_headers, db_session, test_user, test_user_2) -> None:
        """Test revoking another user's share returns 404."""
        pdf = await create_test_pdf(db_session, user_id=test_user_2.id)
        ann_set = await create_test_annotation_set(db_session, pdf_id=pdf.id, user_id=test_user_2.id, name="Shared Set")

        share = await create_test_share(
            db_session,
            annotation_set_id=ann_set.id,
            shared_by=test_user_2.id,
            share_token="other_token",
            permission="view",
        )
        await db_session.commit()

        response = await client.delete(
            f"/v1/shares/{share.id}",
            headers=auth_headers,
        )

        assert response.status_code == 404


class TestGetSharedAnnotationsPublic:
    """Tests for GET /v1/shared/annotations/{token}"""

    async def test_get_shared_annotations_public(self, client: AsyncClient, db_session, test_user) -> None:
        """Test public access to shared annotations."""
        pdf = await create_test_pdf(db_session, user_id=test_user.id)
        ann_set = await create_test_annotation_set(
            db_session,
            pdf_id=pdf.id,
            user_id=test_user.id,
            name="Shared Set",
            color="#FFFF00",
        )

        await create_test_annotation(
            db_session,
            set_id=ann_set.id,
            page_number=1,
            type="highlight",
        )

        await create_test_share(
            db_session,
            annotation_set_id=ann_set.id,
            shared_by=test_user.id,
            share_token="public_token_123",
            permission="view",
        )
        await db_session.commit()

        # Public access - no auth headers
        response = await client.get("/v1/shared/annotations/public_token_123")

        assert response.status_code == 200
        data = response.json()
        assert data["shared_by_login"] == (test_user.display_name or test_user.github_login)
        assert data["permission"] == "view"
        assert data["annotation_set"]["name"] == "Shared Set"
        assert len(data["annotation_set"]["annotations"]) == 1

    async def test_get_shared_annotations_invalid_token_returns_404(self, client: AsyncClient) -> None:
        """Test accessing with invalid token returns 404."""
        response = await client.get("/v1/shared/annotations/invalid_token")

        assert response.status_code == 404


class TestGetSharedPdfPublic:
    """Tests for GET /v1/shared/pdf/{token}"""

    async def test_get_shared_pdf_public(self, client: AsyncClient, mock_github_api, db_session, test_user) -> None:
        """Test public access to shared PDF content."""
        pdf = await create_test_pdf(db_session, user_id=test_user.id, github_sha="abc123")
        ann_set = await create_test_annotation_set(db_session, pdf_id=pdf.id, user_id=test_user.id, name="Shared Set")

        await create_test_share(
            db_session,
            annotation_set_id=ann_set.id,
            shared_by=test_user.id,
            share_token="pdf_token_123",
            permission="view",
        )
        await db_session.commit()

        # Public access - no auth headers
        response = await client.get("/v1/shared/pdf/pdf_token_123")

        assert response.status_code == 200
        assert response.headers["content-type"] == "application/pdf"
        assert "etag" in response.headers

    async def test_get_shared_pdf_etag_cache(self, client: AsyncClient, mock_github_api, db_session, test_user) -> None:
        """Test ETag caching for shared PDF."""
        pdf = await create_test_pdf(db_session, user_id=test_user.id, github_sha="etag_sha")
        ann_set = await create_test_annotation_set(db_session, pdf_id=pdf.id, user_id=test_user.id, name="Shared Set")

        await create_test_share(
            db_session,
            annotation_set_id=ann_set.id,
            shared_by=test_user.id,
            share_token="cache_token",
            permission="view",
        )
        await db_session.commit()

        # First request
        response1 = await client.get("/v1/shared/pdf/cache_token")
        etag = response1.headers.get("etag")

        # Second request with If-None-Match
        response2 = await client.get(
            "/v1/shared/pdf/cache_token",
            headers={"if-none-match": etag},
        )

        assert response2.status_code == 304
