"""Shared test helpers for mocking quota/API-key resolution results."""

from unittest.mock import MagicMock


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
