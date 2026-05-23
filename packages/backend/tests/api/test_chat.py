"""Tests for chat routes."""

import uuid
from fastapi import HTTPException
from httpx import AsyncClient
from unittest.mock import AsyncMock, patch, MagicMock
from tests.fixtures import (
    create_test_pdf,
    create_test_collection,
    create_test_annotation_set,
    create_test_annotation,
)

TEST_EMBEDDING = [0.01] * 1024


def _init_http_clients():
    """Initialize HTTP clients on app state for tests that need streaming."""
    from app.main import app
    from app.core.http_client import HTTPClientState

    if not hasattr(app.state, "llm_http_client"):
        HTTPClientState.init_http_clients(app)


async def _override_get_llm_http_client():
    """Override LLM HTTP client dependency for tests."""
    _init_http_clients()
    from app.main import app
    from app.core.http_client import HTTPClientState

    yield HTTPClientState.get_llm_client(app)


async def _override_get_embedding_http_client():
    """Override embedding HTTP client dependency for tests."""
    _init_http_clients()
    from app.main import app
    from app.core.http_client import HTTPClientState

    yield HTTPClientState.get_embedding_client(app)


def _setup_stream_mocks():
    """Set up common mocks for streaming tests (HTTP client overrides)."""
    _init_http_clients()
    from app.api import deps

    deps.get_llm_http_client = _override_get_llm_http_client
    deps.get_embedding_http_client = _override_get_embedding_http_client


def _make_stream_mocks(*, stream_reply=None, embed_side_effect=None):
    """Factory for common streaming test mocks.

    Returns a dict with pre-configured indexing, embedding, LLM, and chat mocks.
    """
    mock_indexing = MagicMock()
    mock_indexing.get_or_create_status = AsyncMock(
        return_value=MagicMock(status="indexed")
    )
    mock_indexing.ensure_indexed = AsyncMock(return_value=MagicMock(status="indexed"))
    mock_indexing.reset_if_stale = AsyncMock(return_value=False)

    mock_embed = MagicMock()
    if embed_side_effect:
        mock_embed.embed_query = AsyncMock(side_effect=embed_side_effect)
    else:
        mock_embed.embed_query = AsyncMock(return_value=TEST_EMBEDDING)

    mock_llm = MagicMock()

    mock_chat = MagicMock()
    mock_chat.build_messages = MagicMock(
        return_value=("system prompt", [{"role": "user", "content": "test"}])
    )
    if stream_reply:
        mock_chat.stream_reply = stream_reply

    return {
        "indexing": mock_indexing,
        "embedding": mock_embed,
        "llm": mock_llm,
        "chat": mock_chat,
    }


def _stream_patches(mocks, *, with_chat=True, with_llm=True):
    """Return a list of patch context managers for common stream dependencies."""
    patches = [
        patch("app.api.routes.chat.EmbeddingService", return_value=mocks["embedding"]),
        patch("app.services.indexing_service.IndexingService", return_value=mocks["indexing"]),
    ]
    if with_llm:
        patches.append(patch("app.api.routes.chat.LLMService", return_value=mocks["llm"]))
    if with_chat and mocks.get("chat"):
        patches.append(patch("app.services.chat_orchestrator.ChatService", return_value=mocks["chat"]))
    return patches


class TestCreateConversation:
    """Tests for POST /v1/chat/conversations"""

    async def test_create_conversation_with_pdf_id(
        self, client: AsyncClient, auth_headers, db_session, test_user
    ) -> None:
        """Test creating a conversation scoped to a PDF."""
        pdf = await create_test_pdf(db_session, user_id=test_user.id)
        await db_session.commit()

        response = await client.post(
            "/v1/chat/conversations",
            json={"pdf_id": str(pdf.id)},
            headers=auth_headers,
        )

        assert response.status_code == 201
        data = response.json()
        assert data["pdf_id"] == str(pdf.id)
        assert data["collection_id"] is None
        assert "id" in data
        assert "title" in data
        assert "created_at" in data

    async def test_create_conversation_with_collection_id(
        self, client: AsyncClient, auth_headers, db_session, test_user
    ) -> None:
        """Test creating a conversation scoped to a collection."""
        col = await create_test_collection(
            db_session, user_id=test_user.id, name="Research"
        )
        await db_session.commit()

        response = await client.post(
            "/v1/chat/conversations",
            json={"collection_id": str(col.id)},
            headers=auth_headers,
        )

        assert response.status_code == 201
        data = response.json()
        assert data["collection_id"] == str(col.id)
        assert data["pdf_id"] is None

    async def test_create_conversation_neither_pdf_nor_collection_returns_422(
        self, client: AsyncClient, auth_headers
    ) -> None:
        """Test creating a conversation without pdf_id or collection_id returns 422."""
        response = await client.post(
            "/v1/chat/conversations",
            json={},
            headers=auth_headers,
        )

        assert response.status_code == 422

    async def test_create_conversation_requires_auth(self, client: AsyncClient) -> None:
        """Test that creating a conversation requires authentication."""
        response = await client.post(
            "/v1/chat/conversations",
            json={"pdf_id": str(uuid.uuid4())},
        )

        assert response.status_code == 401


class TestListConversations:
    """Tests for GET /v1/chat/conversations"""

    async def test_list_conversations_returns_user_conversations(
        self, client: AsyncClient, auth_headers, db_session, test_user, test_user_2
    ) -> None:
        """Test listing returns only current user's conversations."""
        pdf = await create_test_pdf(db_session, user_id=test_user.id)
        pdf2 = await create_test_pdf(
            db_session,
            user_id=test_user_2.id,
            title="User2 PDF",
            filename="user2.pdf",
            github_sha="sha_user2",
        )
        await db_session.commit()

        await client.post(
            "/v1/chat/conversations", json={"pdf_id": str(pdf.id)}, headers=auth_headers
        )

        from app.core.security import create_access_token

        token_2_val = create_access_token(test_user_2.id)
        headers_2 = {"Authorization": f"Bearer {token_2_val}"}
        await client.post(
            "/v1/chat/conversations", json={"pdf_id": str(pdf2.id)}, headers=headers_2
        )

        response = await client.get(
            "/v1/chat/conversations",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["pdf_id"] == str(pdf.id)

    async def test_list_conversations_filtered_by_pdf_id(
        self, client: AsyncClient, auth_headers, db_session, test_user
    ) -> None:
        """Test filtering conversations by pdf_id."""
        pdf1 = await create_test_pdf(
            db_session,
            user_id=test_user.id,
            title="PDF One",
            filename="pdf_one.pdf",
            github_sha="sha_filter_1",
        )
        pdf2 = await create_test_pdf(
            db_session,
            user_id=test_user.id,
            title="PDF Two",
            filename="pdf_two.pdf",
            github_sha="sha_filter_2",
        )
        await db_session.commit()

        await client.post(
            "/v1/chat/conversations",
            json={"pdf_id": str(pdf1.id)},
            headers=auth_headers,
        )
        await client.post(
            "/v1/chat/conversations",
            json={"pdf_id": str(pdf2.id)},
            headers=auth_headers,
        )

        response = await client.get(
            f"/v1/chat/conversations?pdf_id={pdf1.id}",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["pdf_id"] == str(pdf1.id)

    async def test_list_conversations_empty(
        self, client: AsyncClient, auth_headers
    ) -> None:
        """Test listing conversations when none exist."""
        response = await client.get(
            "/v1/chat/conversations",
            headers=auth_headers,
        )

        assert response.status_code == 200
        assert response.json() == []

    async def test_list_conversations_requires_auth(self, client: AsyncClient) -> None:
        """Test that listing conversations requires authentication."""
        response = await client.get("/v1/chat/conversations")

        assert response.status_code == 401


class TestGetMessages:
    """Tests for GET /v1/chat/conversations/{conversation_id}/messages"""

    async def test_get_messages_empty(
        self, client: AsyncClient, auth_headers, db_session, test_user
    ) -> None:
        """Test getting messages for a new conversation returns empty list."""
        pdf = await create_test_pdf(db_session, user_id=test_user.id)
        await db_session.commit()

        conv_resp = await client.post(
            "/v1/chat/conversations",
            json={"pdf_id": str(pdf.id)},
            headers=auth_headers,
        )
        conv_id = conv_resp.json()["id"]

        response = await client.get(
            f"/v1/chat/conversations/{conv_id}/messages",
            headers=auth_headers,
        )

        assert response.status_code == 200
        assert response.json() == []

    async def test_get_messages_not_found_returns_404(
        self, client: AsyncClient, auth_headers
    ) -> None:
        """Test getting messages for non-existent conversation returns 404."""
        fake_id = uuid.uuid4()

        response = await client.get(
            f"/v1/chat/conversations/{fake_id}/messages",
            headers=auth_headers,
        )

        assert response.status_code == 404

    async def test_get_messages_other_users_conversation_returns_404(
        self, client: AsyncClient, auth_headers, db_session, test_user, test_user_2
    ) -> None:
        """Test getting messages for another user's conversation returns 404."""
        pdf = await create_test_pdf(
            db_session,
            user_id=test_user_2.id,
            title="Other PDF",
            filename="other.pdf",
            github_sha="sha_other",
        )
        await db_session.commit()

        from app.core.security import create_access_token

        token_2_val = create_access_token(test_user_2.id)
        headers_2 = {"Authorization": f"Bearer {token_2_val}"}

        conv_resp = await client.post(
            "/v1/chat/conversations",
            json={"pdf_id": str(pdf.id)},
            headers=headers_2,
        )
        conv_id = conv_resp.json()["id"]

        response = await client.get(
            f"/v1/chat/conversations/{conv_id}/messages",
            headers=auth_headers,
        )

        assert response.status_code == 404

    async def test_get_messages_requires_auth(self, client: AsyncClient) -> None:
        """Test that getting messages requires authentication."""
        response = await client.get(f"/v1/chat/conversations/{uuid.uuid4()}/messages")

        assert response.status_code == 401


class TestDeleteConversation:
    """Tests for DELETE /v1/chat/conversations/{conversation_id}"""

    async def test_delete_conversation(
        self, client: AsyncClient, auth_headers, db_session, test_user
    ) -> None:
        """Test deleting a conversation."""
        from sqlalchemy import select
        from app.db.models import ChatConversation

        pdf = await create_test_pdf(db_session, user_id=test_user.id)
        await db_session.commit()

        conv_resp = await client.post(
            "/v1/chat/conversations",
            json={"pdf_id": str(pdf.id)},
            headers=auth_headers,
        )
        conv_id = conv_resp.json()["id"]

        response = await client.delete(
            f"/v1/chat/conversations/{conv_id}",
            headers=auth_headers,
        )

        assert response.status_code == 204

        result = await db_session.execute(
            select(ChatConversation).where(ChatConversation.id == conv_id)
        )
        assert result.scalar_one_or_none() is None

    async def test_delete_conversation_not_found_returns_404(
        self, client: AsyncClient, auth_headers
    ) -> None:
        """Test deleting non-existent conversation returns 404."""
        fake_id = uuid.uuid4()

        response = await client.delete(
            f"/v1/chat/conversations/{fake_id}",
            headers=auth_headers,
        )

        assert response.status_code == 404

    async def test_delete_other_users_conversation_returns_404(
        self, client: AsyncClient, auth_headers, db_session, test_user, test_user_2
    ) -> None:
        """Test deleting another user's conversation returns 404."""
        pdf = await create_test_pdf(
            db_session,
            user_id=test_user_2.id,
            title="Other PDF",
            filename="other.pdf",
            github_sha="sha_other_del",
        )
        await db_session.commit()

        from app.core.security import create_access_token

        token_2_val = create_access_token(test_user_2.id)
        headers_2 = {"Authorization": f"Bearer {token_2_val}"}

        conv_resp = await client.post(
            "/v1/chat/conversations",
            json={"pdf_id": str(pdf.id)},
            headers=headers_2,
        )
        conv_id = conv_resp.json()["id"]

        response = await client.delete(
            f"/v1/chat/conversations/{conv_id}",
            headers=auth_headers,
        )

        assert response.status_code == 404

    async def test_delete_conversation_requires_auth(self, client: AsyncClient) -> None:
        """Test that deleting a conversation requires authentication."""
        response = await client.delete(f"/v1/chat/conversations/{uuid.uuid4()}")

        assert response.status_code == 401


class TestStreamMessage:
    """Tests for POST /v1/chat/conversations/{conversation_id}/stream"""

    async def test_stream_message_no_api_key_no_quota_returns_402(
        self, client: AsyncClient, auth_headers, db_session, test_user
    ) -> None:
        """Test streaming without API key or quota returns 402."""
        _setup_stream_mocks()

        pdf = await create_test_pdf(db_session, user_id=test_user.id)
        await db_session.commit()

        conv_resp = await client.post(
            "/v1/chat/conversations",
            json={"pdf_id": str(pdf.id)},
            headers=auth_headers,
        )
        conv_id = conv_resp.json()["id"]

        mocks = _make_stream_mocks()

        with patch(
            "app.api.routes.chat.resolve_api_key_with_quota",
            new_callable=AsyncMock,
        ) as mock_resolve:
            mock_resolve.side_effect = HTTPException(status_code=402, detail="No API keys available")
            with patch("app.services.indexing_service.IndexingService", return_value=mocks["indexing"]):
                response = await client.post(
                    f"/v1/chat/conversations/{conv_id}/stream",
                    json={"content": "What is this paper about?"},
                    headers=auth_headers,
                )
                assert response.status_code == 402

    async def test_stream_message_conversation_not_found_returns_404(
        self, client: AsyncClient, auth_headers
    ) -> None:
        """Test streaming to non-existent conversation returns 404."""
        _setup_stream_mocks()

        response = await client.post(
            f"/v1/chat/conversations/{uuid.uuid4()}/stream",
            json={"content": "Hello"},
            headers=auth_headers,
        )
        assert response.status_code == 404

    async def test_stream_message_requires_auth(self, client: AsyncClient) -> None:
        """Test that streaming requires authentication."""
        response = await client.post(
            f"/v1/chat/conversations/{uuid.uuid4()}/stream",
            json={"content": "Hello"},
        )
        assert response.status_code == 401

    async def test_stream_message_returns_sse_content_type(
        self, client: AsyncClient, auth_headers, db_session, test_user
    ) -> None:
        """Test that streaming endpoint returns SSE content type when it succeeds."""
        _setup_stream_mocks()

        pdf = await create_test_pdf(db_session, user_id=test_user.id)
        await db_session.commit()

        conv_resp = await client.post(
            "/v1/chat/conversations",
            json={"pdf_id": str(pdf.id)},
            headers=auth_headers,
        )
        conv_id = conv_resp.json()["id"]

        async def mock_stream_reply(*args, **kwargs):
            yield "Test "
            yield "response."

        mocks = _make_stream_mocks(stream_reply=mock_stream_reply)

        with patch(
            "app.api.routes.chat.resolve_api_key_with_quota", new_callable=AsyncMock,
        ) as mock_resolve:
            mock_resolve.return_value = MagicMock(
                provider="gemini", api_key="fake-key", is_in_house=True, quota_remaining=10,
            )
            from contextlib import ExitStack
            with ExitStack() as stack:
                for pm in _stream_patches(mocks):
                    stack.enter_context(pm)
                response = await client.post(
                    f"/v1/chat/conversations/{conv_id}/stream",
                    json={"content": "What is this paper about?"},
                    headers=auth_headers,
                )
                assert response.status_code == 200
                assert "text/event-stream" in response.headers.get("content-type", "")

    # --- OpenRouter 429 handling -------------------------------------------------

    async def test_stream_openrouter_429_returns_rate_limited(
        self, client: AsyncClient, auth_headers, db_session, test_user
    ) -> None:
        """When OpenRouter 429s, stream should return a rate_limited SSE error."""
        _setup_stream_mocks()
        from app.services.exceptions import LLMRateLimitError

        pdf = await create_test_pdf(db_session, user_id=test_user.id)
        await db_session.commit()

        conv_resp = await client.post(
            "/v1/chat/conversations",
            json={"pdf_id": str(pdf.id)},
            headers=auth_headers,
        )
        conv_id = conv_resp.json()["id"]

        async def mock_stream(*args, **kwargs):
            raise LLMRateLimitError("openrouter")
            yield

        mocks = _make_stream_mocks(stream_reply=mock_stream)

        with patch(
            "app.api.routes.chat.resolve_api_key_with_quota", new_callable=AsyncMock,
        ) as mock_resolve:
            mock_resolve.return_value = MagicMock(
                provider="openrouter", api_key="openrouter-key", is_in_house=True, quota_remaining=10,
            )
            from contextlib import ExitStack
            with ExitStack() as stack:
                for pm in _stream_patches(mocks):
                    stack.enter_context(pm)
                response = await client.post(
                    f"/v1/chat/conversations/{conv_id}/stream",
                    json={"content": "What is this paper about?"},
                    headers=auth_headers,
                )
                assert response.status_code == 200
                assert "rate_limited" in response.text

    async def test_stream_user_own_key_skips_openrouter(
        self, client: AsyncClient, auth_headers, db_session, test_user
    ) -> None:
        """When user has their own key, OpenRouter should never be tried."""
        _setup_stream_mocks()

        pdf = await create_test_pdf(db_session, user_id=test_user.id)
        await db_session.commit()

        conv_resp = await client.post(
            "/v1/chat/conversations",
            json={"pdf_id": str(pdf.id)},
            headers=auth_headers,
        )
        conv_id = conv_resp.json()["id"]

        async def mock_stream_reply(*args, **kwargs):
            yield "User key response."

        mocks = _make_stream_mocks(stream_reply=mock_stream_reply)

        with patch(
            "app.api.routes.chat.resolve_api_key_with_quota", new_callable=AsyncMock,
        ) as mock_resolve:
            mock_resolve.return_value = MagicMock(
                provider="openai", api_key="user-own-key", is_in_house=False, quota_remaining=None,
            )
            from contextlib import ExitStack
            with ExitStack() as stack:
                for pm in _stream_patches(mocks):
                    stack.enter_context(pm)
                response = await client.post(
                    f"/v1/chat/conversations/{conv_id}/stream",
                    json={"content": "What is this paper about?"},
                    headers=auth_headers,
                )
                assert response.status_code == 200
                assert "User key response." in response.text


class TestStreamMessageOpenRouterQuotaGating:
    """Tests for OpenRouter free-tier quota gating → 503 in streaming."""

    async def _setup_conv(self, client, auth_headers, db_session, test_user):
        """Create a conversation for streaming tests."""
        pdf = await create_test_pdf(db_session, user_id=test_user.id)
        await db_session.commit()
        conv_resp = await client.post(
            "/v1/chat/conversations",
            json={"pdf_id": str(pdf.id)},
            headers=auth_headers,
        )
        return conv_resp.json()["id"]

    async def test_stream_message_quota_exceeded_returns_503(
        self, client: AsyncClient, auth_headers, db_session, test_user
    ):
        """When OpenRouter quota is exceeded, stream_message returns 503."""
        _setup_stream_mocks()
        from app.services.exceptions import OpenRouterQuotaError

        conv_id = await self._setup_conv(client, auth_headers, db_session, test_user)

        mocks = _make_stream_mocks(
            embed_side_effect=OpenRouterQuotaError(limit=1000, count_today=900)
        )

        with patch(
            "app.api.routes.chat.resolve_api_key_with_quota", new_callable=AsyncMock,
        ) as mock_resolve:
            mock_resolve.return_value = MagicMock(
                provider="openrouter", api_key="openrouter-key", is_in_house=True, quota_remaining=10,
            )
            with patch("app.services.indexing_service.IndexingService", return_value=mocks["indexing"]), \
                 patch("app.api.routes.chat.EmbeddingService", return_value=mocks["embedding"]):
                response = await client.post(
                    f"/v1/chat/conversations/{conv_id}/stream",
                    json={"content": "What is this paper about?"},
                    headers=auth_headers,
                )
                assert response.status_code == 503
                assert "OpenRouter free-tier usage" in response.json()["detail"]

    async def test_stream_message_llm_gate_returns_503(
        self, client: AsyncClient, auth_headers, db_session, test_user
    ):
        """When LLM gate triggers for server OpenRouter key, returns 503."""
        _setup_stream_mocks()

        conv_id = await self._setup_conv(client, auth_headers, db_session, test_user)

        mocks = _make_stream_mocks()

        with patch(
            "app.api.routes.chat.resolve_api_key_with_quota", new_callable=AsyncMock,
        ) as mock_resolve:
            mock_resolve.side_effect = HTTPException(
                status_code=503,
                detail="OpenRouter free-tier usage limit reached (900/1000).",
            )
            with patch("app.services.indexing_service.IndexingService", return_value=mocks["indexing"]), \
                 patch("app.api.routes.chat.EmbeddingService", return_value=mocks["embedding"]):
                response = await client.post(
                    f"/v1/chat/conversations/{conv_id}/stream",
                    json={"content": "What is this paper about?"},
                    headers=auth_headers,
                )
                assert response.status_code == 503

    async def test_byok_skips_llm_gate(
        self, client: AsyncClient, auth_headers, db_session, test_user
    ):
        """BYOK keys skip the LLM usage gate entirely."""
        _setup_stream_mocks()

        conv_id = await self._setup_conv(client, auth_headers, db_session, test_user)

        async def mock_stream_reply(*args, **kwargs):
            yield "User key response."

        mocks = _make_stream_mocks(stream_reply=mock_stream_reply)

        with patch(
            "app.api.routes.chat.resolve_api_key_with_quota", new_callable=AsyncMock,
        ) as mock_resolve:
            mock_resolve.return_value = MagicMock(
                provider="openai", api_key="user-own-key", is_in_house=False, quota_remaining=None,
            )
            from contextlib import ExitStack
            with ExitStack() as stack:
                for pm in _stream_patches(mocks):
                    stack.enter_context(pm)
                response = await client.post(
                    f"/v1/chat/conversations/{conv_id}/stream",
                    json={"content": "What is this paper about?"},
                    headers=auth_headers,
                )
                assert response.status_code == 200
