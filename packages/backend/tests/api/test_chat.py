"""Tests for chat routes."""

import uuid
from httpx import AsyncClient
from unittest.mock import AsyncMock, patch, MagicMock
from tests.fixtures import (
    create_test_pdf,
    create_test_collection,
    create_test_annotation_set,
    create_test_annotation,
)


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
    """Set up common mocks for streaming tests."""
    _init_http_clients()
    from app.api import deps

    deps.get_llm_http_client = _override_get_llm_http_client
    deps.get_embedding_http_client = _override_get_embedding_http_client


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

        mock_indexing = MagicMock()
        mock_indexing.get_or_create_status = AsyncMock(
            return_value=MagicMock(status="indexed")
        )
        mock_indexing.reset_if_stale = AsyncMock(return_value=False)

        with patch(
            "app.api.routes.chat.api_key_service.resolve_for_chat",
            new_callable=AsyncMock,
        ) as mock_resolve:
            from app.services.exceptions import ApiKeyNotFoundError

            mock_resolve.side_effect = ApiKeyNotFoundError("No API keys available")

            with patch(
                "app.api.routes.chat.IndexingService",
                return_value=mock_indexing,
            ):
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

        fake_id = uuid.uuid4()

        response = await client.post(
            f"/v1/chat/conversations/{fake_id}/stream",
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

        mock_indexing = MagicMock()
        mock_indexing.get_or_create_status = AsyncMock(
            return_value=MagicMock(status="indexed")
        )
        mock_indexing.reset_if_stale = AsyncMock(return_value=False)

        mock_embed_instance = MagicMock()
        mock_embed_instance.embed_query = AsyncMock(return_value=[0.1, 0.2, 0.3])

        mock_llm_instance = MagicMock()

        mock_chat_instance = MagicMock()
        mock_chat_instance.stream_reply = mock_stream_reply
        mock_chat_instance.build_messages = MagicMock(
            return_value=("system prompt", [{"role": "user", "content": "test"}])
        )

        with patch(
            "app.api.routes.chat.api_key_service.resolve_for_chat",
            new_callable=AsyncMock,
        ) as mock_resolve:
            mock_resolve.return_value = MagicMock(
                provider="gemini",
                api_key="fake-key",
                is_in_house=True,
                quota_remaining=10,
            )
            with patch(
                "app.api.routes.chat.EmbeddingService",
                return_value=mock_embed_instance,
            ):
                with patch(
                    "app.api.routes.chat.LLMService",
                    return_value=mock_llm_instance,
                ):
                    with patch(
                        "app.api.routes.chat.ChatService",
                        return_value=mock_chat_instance,
                    ):
                        with patch(
                            "app.api.routes.chat.IndexingService",
                            return_value=mock_indexing,
                        ):
                            response = await client.post(
                                f"/v1/chat/conversations/{conv_id}/stream",
                                json={"content": "What is this paper about?"},
                                headers=auth_headers,
                            )

                            assert response.status_code == 200
                            assert "text/event-stream" in response.headers.get(
                                "content-type", ""
                            )


class TestStreamMessageOpenRouterFallback:
    """Tests for OpenRouter 429 → paid fallback in chat streaming."""

    async def test_stream_openrouter_429_falls_back_to_paid(
        self, client: AsyncClient, auth_headers, db_session, test_user
    ) -> None:
        """When OpenRouter 429s, stream should fall back to paid provider."""
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

        async def mock_stream_reply_openrouter(*args, **kwargs):
            raise LLMRateLimitError("openrouter")
            yield  # noqa: unreachable — makes this an async generator

        async def mock_stream_reply_paid(*args, **kwargs):
            yield "Paid "
            yield "response."

        mock_indexing = MagicMock()
        mock_indexing.get_or_create_status = AsyncMock(
            return_value=MagicMock(status="indexed")
        )
        mock_indexing.reset_if_stale = AsyncMock(return_value=False)

        mock_embed_instance = MagicMock()
        mock_embed_instance.embed_query = AsyncMock(return_value=[0.1, 0.2, 0.3])

        mock_llm_instance = MagicMock()

        mock_chat_instance = MagicMock()
        mock_chat_instance.build_messages = MagicMock(
            return_value=("system prompt", [{"role": "user", "content": "test"}])
        )
        # Must use MagicMock (not AsyncMock) so calls return async generators
        # directly — the route does `async for token in stream_reply(...)`.
        # Call the functions to create async generator objects.
        mock_chat_instance.stream_reply = MagicMock(
            side_effect=[mock_stream_reply_openrouter(), mock_stream_reply_paid()]
        )

        with patch(
            "app.api.routes.chat.api_key_service.resolve_for_chat",
            new_callable=AsyncMock,
        ) as mock_resolve, patch(
            "app.api.routes.chat.api_key_service.resolve_paid_fallback",
            new_callable=AsyncMock,
        ) as mock_paid_resolve, patch(
            "app.api.routes.chat.api_key_service.decrement_quota",
            new_callable=AsyncMock,
            return_value=9,
        ) as mock_decrement:
            mock_resolve.return_value = MagicMock(
                provider="openrouter",
                api_key="openrouter-key",
                is_in_house=True,
                quota_remaining=10,
            )
            mock_paid_resolve.return_value = MagicMock(
                provider="gemini",
                api_key="gemini-key",
                is_in_house=True,
                quota_remaining=10,
            )

            with patch(
                "app.api.routes.chat.EmbeddingService",
                return_value=mock_embed_instance,
            ), patch(
                "app.api.routes.chat.LLMService",
                return_value=mock_llm_instance,
            ), patch(
                "app.api.routes.chat.ChatService",
                return_value=mock_chat_instance,
            ), patch(
                "app.api.routes.chat.IndexingService",
                return_value=mock_indexing,
            ):
                response = await client.post(
                    f"/v1/chat/conversations/{conv_id}/stream",
                    json={"content": "What is this paper about?"},
                    headers=auth_headers,
                )

                assert response.status_code == 200
                assert "text/event-stream" in response.headers.get(
                    "content-type", ""
                )

                # Parse SSE events
                body = response.text
                assert "Free tier rate limited, using backup model." in body
                assert '"provider_fallback": true' in body

                # Verify paid fallback was resolved and quota decremented
                mock_paid_resolve.assert_called_once()
                mock_decrement.assert_called_once()

    async def test_stream_openrouter_429_no_paid_fallback(
        self, client: AsyncClient, auth_headers, db_session, test_user
    ) -> None:
        """When OpenRouter 429s and no paid fallback available, return SSE error."""
        _setup_stream_mocks()

        from app.services.exceptions import LLMRateLimitError, QuotaExhaustedError

        pdf = await create_test_pdf(db_session, user_id=test_user.id)
        await db_session.commit()

        conv_resp = await client.post(
            "/v1/chat/conversations",
            json={"pdf_id": str(pdf.id)},
            headers=auth_headers,
        )
        conv_id = conv_resp.json()["id"]

        async def mock_stream_reply_openrouter(*args, **kwargs):
            raise LLMRateLimitError("openrouter")
            yield  # noqa: unreachable — makes this an async generator

        mock_indexing = MagicMock()
        mock_indexing.get_or_create_status = AsyncMock(
            return_value=MagicMock(status="indexed")
        )
        mock_indexing.reset_if_stale = AsyncMock(return_value=False)

        mock_embed_instance = MagicMock()
        mock_embed_instance.embed_query = AsyncMock(return_value=[0.1, 0.2, 0.3])

        mock_llm_instance = MagicMock()

        mock_chat_instance = MagicMock()
        mock_chat_instance.build_messages = MagicMock(
            return_value=("system prompt", [{"role": "user", "content": "test"}])
        )
        mock_chat_instance.stream_reply = MagicMock(
            side_effect=[mock_stream_reply_openrouter()]
        )

        with patch(
            "app.api.routes.chat.api_key_service.resolve_for_chat",
            new_callable=AsyncMock,
        ) as mock_resolve, patch(
            "app.api.routes.chat.api_key_service.resolve_paid_fallback",
            new_callable=AsyncMock,
        ) as mock_paid_resolve:
            mock_resolve.return_value = MagicMock(
                provider="openrouter",
                api_key="openrouter-key",
                is_in_house=True,
                quota_remaining=10,
            )
            mock_paid_resolve.side_effect = QuotaExhaustedError(
                "chat_uses_remaining", remaining=0
            )

            with patch(
                "app.api.routes.chat.EmbeddingService",
                return_value=mock_embed_instance,
            ), patch(
                "app.api.routes.chat.LLMService",
                return_value=mock_llm_instance,
            ), patch(
                "app.api.routes.chat.ChatService",
                return_value=mock_chat_instance,
            ), patch(
                "app.api.routes.chat.IndexingService",
                return_value=mock_indexing,
            ):
                response = await client.post(
                    f"/v1/chat/conversations/{conv_id}/stream",
                    json={"content": "What is this paper about?"},
                    headers=auth_headers,
                )

                assert response.status_code == 200
                body = response.text
                assert "rate_limited" in body

    async def test_stream_openrouter_no_quota_decrement(
        self, client: AsyncClient, auth_headers, db_session, test_user
    ) -> None:
        """When OpenRouter succeeds, quota should NOT be decremented."""
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
            yield "OpenRouter "
            yield "response."

        mock_indexing = MagicMock()
        mock_indexing.get_or_create_status = AsyncMock(
            return_value=MagicMock(status="indexed")
        )
        mock_indexing.reset_if_stale = AsyncMock(return_value=False)

        mock_embed_instance = MagicMock()
        mock_embed_instance.embed_query = AsyncMock(return_value=[0.1, 0.2, 0.3])

        mock_llm_instance = MagicMock()

        mock_chat_instance = MagicMock()
        mock_chat_instance.stream_reply = mock_stream_reply
        mock_chat_instance.build_messages = MagicMock(
            return_value=("system prompt", [{"role": "user", "content": "test"}])
        )

        with patch(
            "app.api.routes.chat.api_key_service.resolve_for_chat",
            new_callable=AsyncMock,
        ) as mock_resolve, patch(
            "app.api.routes.chat.api_key_service.decrement_quota",
            new_callable=AsyncMock,
            return_value=9,
        ) as mock_decrement:
            mock_resolve.return_value = MagicMock(
                provider="openrouter",
                api_key="openrouter-key",
                is_in_house=True,
                quota_remaining=10,
            )

            with patch(
                "app.api.routes.chat.EmbeddingService",
                return_value=mock_embed_instance,
            ), patch(
                "app.api.routes.chat.LLMService",
                return_value=mock_llm_instance,
            ), patch(
                "app.api.routes.chat.ChatService",
                return_value=mock_chat_instance,
            ), patch(
                "app.api.routes.chat.IndexingService",
                return_value=mock_indexing,
            ):
                response = await client.post(
                    f"/v1/chat/conversations/{conv_id}/stream",
                    json={"content": "What is this paper about?"},
                    headers=auth_headers,
                )

                assert response.status_code == 200
                # Quota should NOT be decremented for free OpenRouter
                mock_decrement.assert_not_called()

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

        mock_indexing = MagicMock()
        mock_indexing.get_or_create_status = AsyncMock(
            return_value=MagicMock(status="indexed")
        )
        mock_indexing.reset_if_stale = AsyncMock(return_value=False)

        mock_embed_instance = MagicMock()
        mock_embed_instance.embed_query = AsyncMock(return_value=[0.1, 0.2, 0.3])

        mock_llm_instance = MagicMock()

        mock_chat_instance = MagicMock()
        mock_chat_instance.stream_reply = mock_stream_reply
        mock_chat_instance.build_messages = MagicMock(
            return_value=("system prompt", [{"role": "user", "content": "test"}])
        )

        with patch(
            "app.api.routes.chat.api_key_service.resolve_for_chat",
            new_callable=AsyncMock,
        ) as mock_resolve, patch(
            "app.api.routes.chat.api_key_service.decrement_quota",
            new_callable=AsyncMock,
            return_value=9,
        ) as mock_decrement:
            # User has their own OpenAI key (not in-house)
            mock_resolve.return_value = MagicMock(
                provider="openai",
                api_key="user-own-key",
                is_in_house=False,
                quota_remaining=None,
            )

            with patch(
                "app.api.routes.chat.EmbeddingService",
                return_value=mock_embed_instance,
            ), patch(
                "app.api.routes.chat.LLMService",
                return_value=mock_llm_instance,
            ), patch(
                "app.api.routes.chat.ChatService",
                return_value=mock_chat_instance,
            ), patch(
                "app.api.routes.chat.IndexingService",
                return_value=mock_indexing,
            ):
                response = await client.post(
                    f"/v1/chat/conversations/{conv_id}/stream",
                    json={"content": "What is this paper about?"},
                    headers=auth_headers,
                )

                assert response.status_code == 200
                body = response.text
                assert "User key response." in body
                assert '"provider_fallback": false' in body
                # Own key — no quota decrement
                mock_decrement.assert_not_called()


class TestSemanticSearch:
    """Tests for POST /v1/chat/semantic-search"""

    async def test_semantic_search_requires_auth(self, client: AsyncClient) -> None:
        """Test that semantic search requires authentication."""
        response = await client.post(
            "/v1/chat/semantic-search",
            json={"query": "test"},
        )

        assert response.status_code == 401

    async def test_semantic_search_embedding_failure_returns_502(
        self, client: AsyncClient, auth_headers
    ) -> None:
        """Test that embedding failure returns 502."""
        _setup_stream_mocks()

        from app.services.embedding_service import EmbeddingError

        with patch("app.api.routes.chat.EmbeddingService") as mock_embed_cls:
            mock_embed = AsyncMock()
            mock_embed.embed_query = AsyncMock(side_effect=EmbeddingError("Failed"))
            mock_embed_cls.return_value = mock_embed

            response = await client.post(
                "/v1/chat/semantic-search",
                json={"query": "machine learning"},
                headers=auth_headers,
            )

            assert response.status_code == 502

    async def test_semantic_search_returns_results(
        self, client: AsyncClient, auth_headers
    ) -> None:
        """Test successful semantic search returns results."""
        _setup_stream_mocks()

        with patch("app.api.routes.chat.EmbeddingService") as mock_embed_cls:
            mock_embed = AsyncMock()
            mock_embed.embed_query = AsyncMock(return_value=[0.1, 0.2, 0.3])
            mock_embed_cls.return_value = mock_embed

            with patch("app.api.routes.chat.vector_search_service") as mock_search:
                mock_result = MagicMock()
                mock_result.pdf_id = str(uuid.uuid4())
                mock_result.pdf_title = "Test Paper"
                mock_result.page_number = 1
                mock_result.content = "Some relevant content"
                mock_result.score = 0.95
                mock_search.search_all = AsyncMock(return_value=[mock_result])

                response = await client.post(
                    "/v1/chat/semantic-search",
                    json={"query": "machine learning", "limit": 5},
                    headers=auth_headers,
                )

                assert response.status_code == 200
                data = response.json()
                assert len(data) == 1
                assert data[0]["pdf_title"] == "Test Paper"
                assert data[0]["page_number"] == 1
                assert data[0]["score"] == 0.95


class TestExplainAnnotation:
    """Tests for POST /v1/chat/explain"""

    async def test_explain_requires_auth(self, client: AsyncClient) -> None:
        """Test that explain requires authentication."""
        response = await client.post(
            "/v1/chat/explain",
            json={
                "pdf_id": str(uuid.uuid4()),
                "annotation_id": str(uuid.uuid4()),
                "selected_text": "test",
                "page_number": 1,
            },
        )

        assert response.status_code == 401

    async def test_explain_annotation_not_found_returns_404(
        self, client: AsyncClient, auth_headers
    ) -> None:
        """Test explaining non-existent annotation returns 404."""
        _setup_stream_mocks()

        fake_pdf_id = uuid.uuid4()
        fake_ann_id = uuid.uuid4()

        response = await client.post(
            "/v1/chat/explain",
            json={
                "pdf_id": str(fake_pdf_id),
                "annotation_id": str(fake_ann_id),
                "selected_text": "test text",
                "page_number": 1,
            },
            headers=auth_headers,
        )

        assert response.status_code == 404

    async def test_explain_pdf_not_found_returns_404(
        self, client: AsyncClient, auth_headers, db_session, test_user
    ) -> None:
        """Test explaining with non-existent PDF returns 404."""
        _setup_stream_mocks()

        pdf = await create_test_pdf(
            db_session,
            user_id=test_user.id,
            title="Explain PDF",
            filename="explain.pdf",
            github_sha="sha_explain",
        )
        ann_set = await create_test_annotation_set(
            db_session, pdf_id=pdf.id, user_id=test_user.id, name="Test Set"
        )
        await create_test_annotation(
            db_session,
            set_id=ann_set.id,
            page_number=1,
            type="highlight",
            selected_text="test",
        )
        await db_session.commit()

        fake_pdf_id = uuid.uuid4()

        response = await client.post(
            "/v1/chat/explain",
            json={
                "pdf_id": str(fake_pdf_id),
                "annotation_id": str(ann_set.id),
                "selected_text": "test text",
                "page_number": 1,
            },
            headers=auth_headers,
        )

        assert response.status_code == 404


class TestExplainOpenRouterFallback:
    """Tests for OpenRouter 429 → paid fallback in explain endpoint."""

    async def test_explain_openrouter_429_falls_back_to_paid(
        self, client: AsyncClient, auth_headers, db_session, test_user
    ) -> None:
        """When OpenRouter 429s on explain, fall back to paid provider."""
        _setup_stream_mocks()

        from app.services.exceptions import LLMRateLimitError

        pdf = await create_test_pdf(
            db_session,
            user_id=test_user.id,
            title="Explain Fallback PDF",
            filename="explain_fb.pdf",
            github_sha="sha_explain_fb",
        )
        ann_set = await create_test_annotation_set(
            db_session, pdf_id=pdf.id, user_id=test_user.id, name="Explain Set"
        )
        ann = await create_test_annotation(
            db_session,
            set_id=ann_set.id,
            page_number=1,
            type="highlight",
            selected_text="test passage",
        )
        await db_session.commit()

        mock_explain_result = MagicMock()
        mock_explain_result.explanation = "This means X."
        mock_explain_result.note_content = "## Explanation\nThis means X."

        with patch(
            "app.api.routes.chat.api_key_service.resolve_for_explain",
            new_callable=AsyncMock,
        ) as mock_resolve, patch(
            "app.api.routes.chat.api_key_service.resolve_paid_fallback",
            new_callable=AsyncMock,
        ) as mock_paid_resolve, patch(
            "app.api.routes.chat.api_key_service.decrement_quota",
            new_callable=AsyncMock,
            return_value=19,
        ) as mock_decrement, patch(
            "app.api.routes.chat.ExplainService"
        ) as mock_explain_cls:
            mock_resolve.return_value = MagicMock(
                provider="openrouter",
                api_key="openrouter-key",
                is_in_house=True,
                quota_remaining=20,
            )
            mock_paid_resolve.return_value = MagicMock(
                provider="gemini",
                api_key="gemini-key",
                is_in_house=True,
                quota_remaining=20,
            )

            mock_explain_svc = AsyncMock()
            mock_explain_svc.explain_with_provider = AsyncMock(
                side_effect=[
                    LLMRateLimitError("openrouter"),
                    mock_explain_result,
                ]
            )
            mock_explain_cls.return_value = mock_explain_svc

            response = await client.post(
                "/v1/chat/explain",
                json={
                    "pdf_id": str(pdf.id),
                    "annotation_id": str(ann.id),
                    "selected_text": "test passage",
                    "page_number": 1,
                },
                headers=auth_headers,
            )

            assert response.status_code == 200
            data = response.json()
            assert data["explanation"] == "This means X."
            assert data["provider_fallback"] is True
            assert data["explain_uses_remaining"] == 19

            mock_paid_resolve.assert_called_once()
            mock_decrement.assert_called_once()

    async def test_explain_openrouter_429_no_paid_fallback_returns_402(
        self, client: AsyncClient, auth_headers, db_session, test_user
    ) -> None:
        """When OpenRouter 429s and no paid fallback, return 402."""
        _setup_stream_mocks()

        from app.services.exceptions import LLMRateLimitError, QuotaExhaustedError

        pdf = await create_test_pdf(
            db_session,
            user_id=test_user.id,
            title="Explain No Fallback PDF",
            filename="explain_nofb.pdf",
            github_sha="sha_explain_nofb",
        )
        ann_set = await create_test_annotation_set(
            db_session, pdf_id=pdf.id, user_id=test_user.id, name="Explain Set 2"
        )
        ann = await create_test_annotation(
            db_session,
            set_id=ann_set.id,
            page_number=1,
            type="highlight",
            selected_text="test passage",
        )
        await db_session.commit()

        with patch(
            "app.api.routes.chat.api_key_service.resolve_for_explain",
            new_callable=AsyncMock,
        ) as mock_resolve, patch(
            "app.api.routes.chat.api_key_service.resolve_paid_fallback",
            new_callable=AsyncMock,
        ) as mock_paid_resolve, patch(
            "app.api.routes.chat.ExplainService"
        ) as mock_explain_cls:
            mock_resolve.return_value = MagicMock(
                provider="openrouter",
                api_key="openrouter-key",
                is_in_house=True,
                quota_remaining=20,
            )
            mock_paid_resolve.side_effect = QuotaExhaustedError(
                "explain_uses_remaining", remaining=0
            )

            mock_explain_svc = AsyncMock()
            mock_explain_svc.explain_with_provider = AsyncMock(
                side_effect=LLMRateLimitError("openrouter")
            )
            mock_explain_cls.return_value = mock_explain_svc

            response = await client.post(
                "/v1/chat/explain",
                json={
                    "pdf_id": str(pdf.id),
                    "annotation_id": str(ann.id),
                    "selected_text": "test passage",
                    "page_number": 1,
                },
                headers=auth_headers,
            )

            assert response.status_code == 402

    async def test_explain_openrouter_no_quota_decrement(
        self, client: AsyncClient, auth_headers, db_session, test_user
    ) -> None:
        """When OpenRouter succeeds on explain, quota should NOT be decremented."""
        _setup_stream_mocks()

        pdf = await create_test_pdf(
            db_session,
            user_id=test_user.id,
            title="Explain OpenRouter OK",
            filename="explain_or_ok.pdf",
            github_sha="sha_explain_or_ok",
        )
        ann_set = await create_test_annotation_set(
            db_session, pdf_id=pdf.id, user_id=test_user.id, name="Explain Set 3"
        )
        ann = await create_test_annotation(
            db_session,
            set_id=ann_set.id,
            page_number=1,
            type="highlight",
            selected_text="test passage",
        )
        await db_session.commit()

        mock_explain_result = MagicMock()
        mock_explain_result.explanation = "Explained."
        mock_explain_result.note_content = "## Note\nExplained."

        with patch(
            "app.api.routes.chat.api_key_service.resolve_for_explain",
            new_callable=AsyncMock,
        ) as mock_resolve, patch(
            "app.api.routes.chat.api_key_service.decrement_quota",
            new_callable=AsyncMock,
            return_value=19,
        ) as mock_decrement, patch(
            "app.api.routes.chat.ExplainService"
        ) as mock_explain_cls:
            mock_resolve.return_value = MagicMock(
                provider="openrouter",
                api_key="openrouter-key",
                is_in_house=True,
                quota_remaining=20,
            )

            mock_explain_svc = AsyncMock()
            mock_explain_svc.explain_with_provider = AsyncMock(
                return_value=mock_explain_result
            )
            mock_explain_cls.return_value = mock_explain_svc

            response = await client.post(
                "/v1/chat/explain",
                json={
                    "pdf_id": str(pdf.id),
                    "annotation_id": str(ann.id),
                    "selected_text": "test passage",
                    "page_number": 1,
                },
                headers=auth_headers,
            )

            assert response.status_code == 200
            data = response.json()
            assert data["provider_fallback"] is False
            # Quota should NOT be decremented for free OpenRouter
            mock_decrement.assert_not_called()

    async def test_explain_user_own_key_skips_openrouter(
        self, client: AsyncClient, auth_headers, db_session, test_user
    ) -> None:
        """When user has their own key for explain, OpenRouter is never tried."""
        _setup_stream_mocks()

        pdf = await create_test_pdf(
            db_session,
            user_id=test_user.id,
            title="Explain User Key PDF",
            filename="explain_userkey.pdf",
            github_sha="sha_explain_userkey",
        )
        ann_set = await create_test_annotation_set(
            db_session, pdf_id=pdf.id, user_id=test_user.id, name="User Key Set"
        )
        ann = await create_test_annotation(
            db_session,
            set_id=ann_set.id,
            page_number=1,
            type="highlight",
            selected_text="test passage",
        )
        await db_session.commit()

        mock_explain_result = MagicMock()
        mock_explain_result.explanation = "Explained via user key."
        mock_explain_result.note_content = "## Note\nExplained via user key."

        with patch(
            "app.api.routes.chat.api_key_service.resolve_for_explain",
            new_callable=AsyncMock,
        ) as mock_resolve, patch(
            "app.api.routes.chat.api_key_service.decrement_quota",
            new_callable=AsyncMock,
            return_value=19,
        ) as mock_decrement, patch(
            "app.api.routes.chat.ExplainService"
        ) as mock_explain_cls:
            # User has own key — not in-house
            mock_resolve.return_value = MagicMock(
                provider="anthropic",
                api_key="user-own-anthropic-key",
                is_in_house=False,
                quota_remaining=None,
            )

            mock_explain_svc = AsyncMock()
            mock_explain_svc.explain_with_provider = AsyncMock(
                return_value=mock_explain_result
            )
            mock_explain_cls.return_value = mock_explain_svc

            response = await client.post(
                "/v1/chat/explain",
                json={
                    "pdf_id": str(pdf.id),
                    "annotation_id": str(ann.id),
                    "selected_text": "test passage",
                    "page_number": 1,
                },
                headers=auth_headers,
            )

            assert response.status_code == 200
            data = response.json()
            assert data["explanation"] == "Explained via user key."
            assert data["provider_fallback"] is False
            assert data["explain_uses_remaining"] == -1  # unlimited for own key
            # Own key — no quota decrement
            mock_decrement.assert_not_called()
