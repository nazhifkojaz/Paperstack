"""API-level tests for per-paper summary routes (B1)."""

import asyncio
from datetime import date
from httpx import AsyncClient
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.core.security import create_access_token
from app.db.models import PdfSummary, UserUsageQuota
from app.services.exceptions import QuotaExhaustedError
from app.services.quota_service import quota_service
from sqlalchemy import select
from tests.fixtures import create_test_pdf
from tests.helpers import (
    GatedSummaryResolver,
    make_create_task_stub,
    setup_http_client_mocks,
)


def _make_quota_decrementing_resolve():
    """Fake resolve that actually decrements the summary quota (observable)."""

    async def _resolve(user, db, feature, *, commit=True):
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
        create_task_stub = make_create_task_stub(asyncio.create_task, "run_generation")

        with (
            patch(
                "app.api.routes.summaries.resolve_api_key_with_quota",
                new_callable=AsyncMock,
            ) as mock_resolve,
            patch("app.api.routes.summaries.asyncio.create_task") as mock_create_task,
        ):
            mock_resolve.side_effect = _make_quota_decrementing_resolve()
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

    async def test_409_does_not_resolve_or_consume_quota(
        self, client: AsyncClient, auth_headers, db_session, test_user
    ):
        pdf = await create_test_pdf(
            db_session, user_id=test_user.id, title="Busy", filename="busy.pdf"
        )
        db_session.add_all(
            [
                PdfSummary(
                    pdf_id=pdf.id,
                    user_id=test_user.id,
                    status="generating",
                ),
                UserUsageQuota(
                    user_id=test_user.id,
                    summary_uses_remaining=5,
                    reset_at=date.today(),
                ),
            ]
        )
        await db_session.commit()

        with patch(
            "app.api.routes.summaries.resolve_api_key_with_quota",
            new_callable=AsyncMock,
        ) as mock_resolve:
            response = await client.post(
                f"/v1/pdfs/{pdf.id}/summary", headers=auth_headers
            )

        assert response.status_code == 409
        mock_resolve.assert_not_awaited()
        quota = (
            await db_session.execute(
                select(UserUsageQuota).where(UserUsageQuota.user_id == test_user.id)
            )
        ).scalar_one()
        assert quota.summary_uses_remaining == 5

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
            mock_resolve.side_effect = _make_quota_decrementing_resolve()

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

    @pytest.mark.parametrize("initial_status", [None, "complete"])
    async def test_concurrent_posts_reserve_once(
        self,
        initial_status,
        concurrent_clients,
        concurrent_session_factory,
        concurrent_user,
    ):
        setup_http_client_mocks()
        async with concurrent_session_factory() as session:
            pdf = await create_test_pdf(
                session,
                user_id=concurrent_user.id,
                title=f"Concurrent {initial_status}",
                filename=f"concurrent-{initial_status}.pdf",
            )
            if initial_status:
                session.add(
                    PdfSummary(
                        pdf_id=pdf.id,
                        user_id=concurrent_user.id,
                        status=initial_status,
                    )
                )
            session.add(
                UserUsageQuota(
                    user_id=concurrent_user.id,
                    summary_uses_remaining=5,
                    reset_at=date.today(),
                )
            )
            await session.commit()
            pdf_id = pdf.id

        gated_resolver = GatedSummaryResolver()
        real_create_task = asyncio.create_task
        create_task_stub = make_create_task_stub(real_create_task, "run_generation")
        headers = {"Authorization": f"Bearer {create_access_token(concurrent_user.id)}"}
        url = f"/v1/pdfs/{pdf_id}/summary"
        first_client, second_client = concurrent_clients

        with (
            patch(
                "app.api.routes.summaries.resolve_api_key_with_quota",
                new=gated_resolver,
            ),
            patch(
                "app.api.routes.summaries.asyncio.create_task",
                side_effect=create_task_stub,
            ),
        ):
            first_request = real_create_task(first_client.post(url, headers=headers))
            await asyncio.wait_for(gated_resolver.first_entered.wait(), timeout=2)
            second_request = real_create_task(second_client.post(url, headers=headers))
            try:
                with pytest.raises(asyncio.TimeoutError):
                    await asyncio.wait_for(
                        gated_resolver.second_entered.wait(), timeout=0.1
                    )
            finally:
                gated_resolver.release_first.set()
            responses = await asyncio.wait_for(
                asyncio.gather(first_request, second_request), timeout=5
            )

        assert sorted(response.status_code for response in responses) == [202, 409]
        assert gated_resolver.call_count == 1
        assert len(create_task_stub.background_tasks) == 1
        async with concurrent_session_factory() as session:
            summaries = (
                (
                    await session.execute(
                        select(PdfSummary).where(
                            PdfSummary.pdf_id == pdf_id,
                            PdfSummary.user_id == concurrent_user.id,
                        )
                    )
                )
                .scalars()
                .all()
            )
            quota = (
                await session.execute(
                    select(UserUsageQuota).where(
                        UserUsageQuota.user_id == concurrent_user.id
                    )
                )
            ).scalar_one()
        assert len(summaries) == 1
        assert summaries[0].status == "generating"
        assert quota.summary_uses_remaining == 4


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
