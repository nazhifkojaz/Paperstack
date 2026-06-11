"""Shared test helpers for mocking quota/API-key resolution results."""

from unittest.mock import MagicMock


TEST_EMBEDDING = [0.01] * 1024


def init_http_clients() -> None:
    """Initialize HTTP clients on app state if not already present."""
    from app.main import app
    from app.core.http_client import HTTPClientState

    if not hasattr(app.state, "llm_http_client"):
        HTTPClientState.init_http_clients(app)


async def override_get_llm_http_client():
    """Override LLM HTTP client dependency for tests."""
    init_http_clients()
    from app.main import app
    from app.core.http_client import HTTPClientState

    yield HTTPClientState.get_llm_client(app)


async def override_get_embedding_http_client():
    """Override embedding HTTP client dependency for tests."""
    init_http_clients()
    from app.main import app
    from app.core.http_client import HTTPClientState

    yield HTTPClientState.get_embedding_client(app)


def setup_http_client_mocks() -> None:
    """Wire the shared HTTP-client overrides into app deps."""
    init_http_clients()
    from app.api import deps

    deps.get_llm_http_client = override_get_llm_http_client
    deps.get_embedding_http_client = override_get_embedding_http_client


def make_quota_result(
    remaining: int = 5,
    global_warning: str | None = None,
    unlimited: bool = False,
) -> MagicMock:
    return MagicMock(
        remaining=remaining,
        global_warning=global_warning,
        unlimited=unlimited,
    )


def make_resolve_result(
    provider: str = "openrouter",
    api_key: str = "test-key",
    model: str | None = None,
    is_in_house: bool = True,
    remaining: int = 5,
    global_warning: str | None = None,
    unlimited: bool = False,
) -> tuple[MagicMock, MagicMock]:
    resolution = MagicMock(
        provider=provider,
        api_key=api_key,
        model=model,
        is_in_house=is_in_house,
    )
    return resolution, make_quota_result(
        remaining=remaining,
        global_warning=global_warning,
        unlimited=unlimited,
    )
