"""Shared test helpers for mocking quota/API-key resolution results."""

import asyncio
from unittest.mock import MagicMock

from app.services.quota_service import quota_service


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


def make_create_task_stub(real_create_task, *captured_names: str):
    """Capture and close selected background coroutines during route tests."""
    background_tasks = []

    def _create_task(coro):
        coro_name = getattr(getattr(coro, "cr_code", None), "co_name", None)
        if coro_name in captured_names:
            background_tasks.append(coro)
            coro.close()
            return MagicMock()
        return real_create_task(coro)

    _create_task.background_tasks = background_tasks
    return _create_task


class GatedSummaryResolver:
    """Hold the first quota resolution so a second request contends on its lock."""

    def __init__(self) -> None:
        self.first_entered = asyncio.Event()
        self.release_first = asyncio.Event()
        self.second_entered = asyncio.Event()
        self.call_count = 0

    async def __call__(self, user, db, feature, *, commit=True):
        assert feature == "summary"
        assert commit is False
        self.call_count += 1
        if self.call_count == 1:
            self.first_entered.set()
            await self.release_first.wait()
        else:
            self.second_entered.set()

        quota_result = await quota_service.check_and_decrement(user.id, db, "summary")
        resolution = MagicMock(
            provider="openrouter",
            api_key="test-key",
            model=None,
            is_in_house=True,
        )
        return resolution, quota_result


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
