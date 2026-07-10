"""API-level tests for per-paper summary routes (B1)."""

import asyncio
from datetime import date
from httpx import AsyncClient
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import HTTPException

from app.db.models import PdfSummary, UserUsageQuota
from app.services.exceptions import QuotaExhaustedError
from app.services.quota_service import quota_service
from sqlalchemy import select
from tests.fixtures import create_test_pdf
from tests.helpers import setup_http_client_mocks


def _make_create_task_stub(real_create_task):
    """Capture (and close) background coroutines spawned by the route."""
    background_tasks = []

    def _create_task(coro):
        coro_name = getattr(getattr(coro, "cr_code", None), "co_name", None)
        if coro_name in ("run_generation", "run_bulk_generation"):
            background_tasks.append(coro)
            coro.close()
            return MagicMock()
        return real_create_task(coro)

    _create_task.background_tasks = background_tasks
    return _create_task


def _make_quota_decrementing_resolve(db_session):
    """Fake resolve that actually decrements the summary quota (observable)."""

    async def _resolve(user, db, feature):
        try:
            quota_result = await quota_service.check_and_decrement(
                user.id, db, "summary"
            )
        except QuotaExhaustedError as exc:
            raise HTTPException(status_code=402, detail=str(exc))
        resolution = MagicMock(
            provider="openrouter",
            api_key="test-key",
            model=None,
            is_in_house=True,
        )
        return resolution, quota_result

    return _resolve


class TestGenerateSummary:
    async def test_post_creates_generating_row_and_decrements_quota(
        self, client: AsyncClient, auth_headers, db_session, test_user
    ):
        setup_http_client_mocks()
        pdf = await create_test_pdf(
            db_session, user_id=test_user.id, title="Sum", filename="s.pdf"
        )
        await db_session.commit()
        create_task_stub = _make_create_task_stub(asyncio.create_task)

        with (
            patch(
                "app.api.routes.summaries.resolve_api_key_with_quota",
                new_callable=AsyncMock,
            ) as mock_resolve,
            patch("app.api.routes.summaries.asyncio.create_task") as mock_create_task,
        ):
            mock_resolve.side_effect = _make_quota_decrementing_resolve(db_session)
            mock_create_task.side_effect = create_task_stub

            response = await client.post(
                f"/v1/pdfs/{pdf.id}/summary",
                headers=auth_headers,
            )

        assert response.status_code == 202
        data = response.json()
        assert data["status"] == "generating"
        assert data["pdf_id"] == str(pdf.id)
        assert len(create_task_stub.background_tasks) == 1

        quota_result = await db_session.execute(
            select(UserUsageQuota).where(UserUsageQuota.user_id == test_user.id)
        )
        quota_row = quota_result.scalar_one()
        assert quota_row.summary_uses_remaining == 9

    async def test_post_while_generating_returns_409(
        self, client: AsyncClient, auth_headers, db_session, test_user
    ):
        setup_http_client_mocks()
        pdf = await create_test_pdf(
            db_session, user_id=test_user.id, title="Sum", filename="s.pdf"
        )
        db_session.add(
            PdfSummary(
                pdf_id=pdf.id,
                user_id=test_user.id,
                status="generating",
            )
        )
        await db_session.commit()

        response = await client.post(
            f"/v1/pdfs/{pdf.id}/summary",
            headers=auth_headers,
        )

        assert response.status_code == 409

    async def test_post_quota_exhausted_returns_402(
        self, client: AsyncClient, auth_headers, db_session, test_user
    ):
        setup_http_client_mocks()
        pdf = await create_test_pdf(
            db_session, user_id=test_user.id, title="Sum", filename="s.pdf"
        )
        db_session.add(
            UserUsageQuota(
                user_id=test_user.id,
                summary_uses_remaining=0,
                reset_at=date.today(),
            )
        )
        await db_session.commit()

        with patch(
            "app.api.routes.summaries.resolve_api_key_with_quota",
            new_callable=AsyncMock,
        ) as mock_resolve:
            mock_resolve.side_effect = _make_quota_decrementing_resolve(db_session)

            response = await client.post(
                f"/v1/pdfs/{pdf.id}/summary",
                headers=auth_headers,
            )

        assert response.status_code == 402

    async def test_post_other_users_pdf_returns_404(
        self, client: AsyncClient, auth_headers, db_session, test_user_2
    ):
        setup_http_client_mocks()
        pdf = await create_test_pdf(
            db_session, user_id=test_user_2.id, title="Other", filename="o.pdf"
        )
        await db_session.commit()

        response = await client.post(
            f"/v1/pdfs/{pdf.id}/summary",
            headers=auth_headers,
        )
        assert response.status_code == 404


class TestGetSummary:
    async def test_get_no_row_returns_404(
        self, client: AsyncClient, auth_headers, db_session, test_user
    ):
        pdf = await create_test_pdf(
            db_session, user_id=test_user.id, title="Sum", filename="s.pdf"
        )
        await db_session.commit()

        response = await client.get(
            f"/v1/pdfs/{pdf.id}/summary",
            headers=auth_headers,
        )
        assert response.status_code == 404

    async def test_get_with_row_returns_200(
        self, client: AsyncClient, auth_headers, db_session, test_user
    ):
        pdf = await create_test_pdf(
            db_session, user_id=test_user.id, title="Sum", filename="s.pdf"
        )
        db_session.add(
            PdfSummary(
                pdf_id=pdf.id,
                user_id=test_user.id,
                status="complete",
                tldr="A summary.",
                method="some method",
            )
        )
        await db_session.commit()

        response = await client.get(
            f"/v1/pdfs/{pdf.id}/summary",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "complete"
        assert data["tldr"] == "A summary."
        assert data["method"] == "some method"


class TestUpdateSummary:
    async def test_patch_creates_row_when_missing(
        self, client: AsyncClient, auth_headers, db_session, test_user
    ):
        pdf = await create_test_pdf(
            db_session, user_id=test_user.id, title="Sum", filename="s.pdf"
        )
        await db_session.commit()

        response = await client.patch(
            f"/v1/pdfs/{pdf.id}/summary",
            json={"method": "manual method"},
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "not_generated"
        assert data["method"] == "manual method"
        assert data["edited_fields"] == ["method"]

    async def test_patch_while_generating_returns_409(
        self, client: AsyncClient, auth_headers, db_session, test_user
    ):
        pdf = await create_test_pdf(
            db_session, user_id=test_user.id, title="Sum", filename="s.pdf"
        )
        db_session.add(
            PdfSummary(
                pdf_id=pdf.id,
                user_id=test_user.id,
                status="generating",
            )
        )
        await db_session.commit()

        response = await client.patch(
            f"/v1/pdfs/{pdf.id}/summary",
            json={"method": "x"},
            headers=auth_headers,
        )
        assert response.status_code == 409

    async def test_patch_accumulates_edited_fields(
        self, client: AsyncClient, auth_headers, db_session, test_user
    ):
        pdf = await create_test_pdf(
            db_session, user_id=test_user.id, title="Sum", filename="s.pdf"
        )
        await db_session.commit()

        r1 = await client.patch(
            f"/v1/pdfs/{pdf.id}/summary",
            json={"method": "m1"},
            headers=auth_headers,
        )
        assert r1.status_code == 200
        assert set(r1.json()["edited_fields"]) == {"method"}

        r2 = await client.patch(
            f"/v1/pdfs/{pdf.id}/summary",
            json={"result": "r1"},
            headers=auth_headers,
        )
        assert r2.status_code == 200
        assert set(r2.json()["edited_fields"]) == {"method", "result"}

        # Re-editing the same field doesn't duplicate.
        r3 = await client.patch(
            f"/v1/pdfs/{pdf.id}/summary",
            json={"method": "m2"},
            headers=auth_headers,
        )
        assert r3.status_code == 200
        assert set(r3.json()["edited_fields"]) == {"method", "result"}
