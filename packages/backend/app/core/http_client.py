"""HTTP client connection pooling for external API calls.

Provides shared httpx.AsyncClient instances with connection pooling
for LLM and embedding services. Reduces TCP handshake overhead
and improves performance under load.
"""
import httpx
from fastapi import FastAPI
from app.core.config import settings


class HTTPClientState:
    """Manages HTTP client lifecycle in app.state.

    Shared clients are initialized at startup and closed at shutdown
    to enable connection pooling across requests.
    """

    # Keys for storing clients in app.state
    LLM_CLIENT_KEY = "llm_http_client"
    EMBEDDING_CLIENT_KEY = "embedding_http_client"

    @staticmethod
    def init_http_clients(app: FastAPI) -> None:
        """Initialize shared HTTP clients and store in app.state.

        Creates clients with connection pooling configured for LLM/embedding APIs.
        Called during application startup via lifespan context manager.
        """
        # Configure connection limits and timeouts
        limits = httpx.Limits(
            max_connections=settings.HTTP_CONNECTION_LIMIT,
            max_keepalive_connections=settings.HTTP_MAX_KEEPALIVE,
        )
        timeout = httpx.Timeout(
            connect=settings.HTTP_TIMEOUT_CONNECT,
            read=settings.HTTP_TIMEOUT_READ,
            write=settings.HTTP_TIMEOUT_CONNECT,
            pool=settings.HTTP_TIMEOUT_CONNECT,
        )

        # LLM client - used for chat, auto-highlight, and explain features
        app.state.llm_http_client = httpx.AsyncClient(
            timeout=timeout,
            limits=limits,
        )

        # Embedding client - used for vector search indexing
        app.state.embedding_http_client = httpx.AsyncClient(
            timeout=timeout,
            limits=limits,
        )

    @staticmethod
    async def close_http_clients(app: FastAPI) -> None:
        """Close all HTTP clients gracefully.

        Called during application shutdown via lifespan context manager.
        """
        if hasattr(app.state, "llm_http_client"):
            await app.state.llm_http_client.aclose()
        if hasattr(app.state, "embedding_http_client"):
            await app.state.embedding_http_client.aclose()

    @staticmethod
    def get_llm_client(app: FastAPI) -> httpx.AsyncClient:
        """Get shared LLM HTTP client from app.state."""
        return getattr(app.state, "llm_http_client")

    @staticmethod
    def get_embedding_client(app: FastAPI) -> httpx.AsyncClient:
        """Get shared embedding HTTP client from app.state."""
        return getattr(app.state, "embedding_http_client")
