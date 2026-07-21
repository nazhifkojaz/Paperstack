"""Direct unit tests for ``app.api.deps.resolve_api_key_with_quota``.

This function is the spine of the per-feature quota system: it resolves the API
key, then either decrements daily quota (in-house OpenRouter key) or returns an
unlimited result (user's own BYOK key).
"""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.api.deps import resolve_api_key_with_quota
from app.services.api_key_service import ApiKeyResolution
from app.services.exceptions import ApiKeyNotFoundError, QuotaExhaustedError


def _make_user():
    return SimpleNamespace(id=uuid.uuid4())


def _make_db(prefs=None):
    """Minimal AsyncSession double. Only ``execute``/``commit`` are touched."""
    db = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = prefs
    db.execute.return_value = result
    return db


def _make_prefs(model="org/model", mode="app"):
    return SimpleNamespace(
        conversation_model=model,
        analysis_model=model,
        openrouter_key_mode=mode,
    )


def _patch_services(monkeypatch, resolver_return=None, resolver_raises=None):
    """Patch the lazily-imported service singletons inside the function."""
    api_key_service = MagicMock()
    quota_service = MagicMock()
    usage_service = MagicMock()

    resolver = AsyncMock()
    if resolver_raises is not None:
        resolver.side_effect = resolver_raises
    elif resolver_return is not None:
        resolver.return_value = resolver_return
    api_key_service.resolve_for_chat = resolver
    api_key_service.resolve_for_explain = resolver
    api_key_service.resolve_for_auto_highlight = resolver

    quota_service.unlimited.return_value = SimpleNamespace(
        remaining=-1, unlimited=True, name="unlimited"
    )
    check_result = MagicMock()
    check_result.with_global_warning.return_value = SimpleNamespace(
        name="decremented", global_warning="global-warn"
    )
    quota_service.check_and_decrement = AsyncMock(return_value=check_result)

    usage_service.record_and_check = AsyncMock(
        return_value=SimpleNamespace(warning_message="global-warn")
    )

    monkeypatch.setattr("app.services.api_key_service.api_key_service", api_key_service)
    monkeypatch.setattr("app.services.quota_service.quota_service", quota_service)
    monkeypatch.setattr(
        "app.services.openrouter_usage_service.openrouter_usage_service",
        usage_service,
    )
    return api_key_service, quota_service, usage_service, check_result


class TestResolveApiKeyWithQuota:
    async def test_missing_api_key_returns_402(self, monkeypatch):
        # Contract: a missing key is surfaced as 402 so the frontend can show
        # the upgrade/add-key prompt. This mirrors the route-level assertions
        # in test_chat / test_auto_highlight / test_summaries.
        _patch_services(monkeypatch, resolver_raises=ApiKeyNotFoundError("chat"))
        with pytest.raises(HTTPException) as exc:
            await resolve_api_key_with_quota(_make_user(), _make_db(), "chat")
        assert exc.value.status_code == 402

    async def test_quota_exhausted_at_resolve_returns_402(self, monkeypatch):
        _patch_services(
            monkeypatch, resolver_raises=QuotaExhaustedError("chat", remaining=0)
        )
        with pytest.raises(HTTPException) as exc:
            await resolve_api_key_with_quota(_make_user(), _make_db(), "chat")
        assert exc.value.status_code == 402

    async def test_byok_key_skips_quota_decrement(self, monkeypatch):
        # A user's own key (is_in_house=False) must not consume daily quota and
        # must not record global usage.
        resolution = ApiKeyResolution(
            provider="openrouter", api_key="sk-or-user", is_in_house=False
        )
        services = _patch_services(monkeypatch, resolver_return=resolution)
        _, quota_service, usage_service, _ = services

        returned_resolution, quota_result = await resolve_api_key_with_quota(
            _make_user(), _make_db(prefs=_make_prefs()), "chat"
        )

        assert returned_resolution is resolution
        assert quota_result is quota_service.unlimited.return_value
        quota_service.check_and_decrement.assert_not_called()
        usage_service.record_and_check.assert_not_called()

    async def test_in_house_openrouter_decrements_and_commits(self, monkeypatch):
        resolution = ApiKeyResolution(
            provider="openrouter", api_key="sk-or-app", is_in_house=True
        )
        services = _patch_services(monkeypatch, resolver_return=resolution)
        _, quota_service, usage_service, check_result = services
        db = _make_db(prefs=_make_prefs())

        _, quota_result = await resolve_api_key_with_quota(_make_user(), db, "chat")

        quota_service.check_and_decrement.assert_awaited_once()
        usage_service.record_and_check.assert_awaited_once_with(db)
        db.commit.assert_awaited_once()
        check_result.with_global_warning.assert_called_once_with("global-warn")
        assert quota_result is check_result.with_global_warning.return_value

    async def test_caller_owned_transaction_does_not_commit(self, monkeypatch):
        resolution = ApiKeyResolution(
            provider="openrouter", api_key="sk-or-app", is_in_house=True
        )
        services = _patch_services(monkeypatch, resolver_return=resolution)
        _, quota_service, usage_service, check_result = services
        db = _make_db(prefs=_make_prefs())

        _, quota_result = await resolve_api_key_with_quota(
            _make_user(), db, "summary", commit=False
        )

        quota_service.check_and_decrement.assert_awaited_once()
        usage_service.record_and_check.assert_awaited_once_with(db)
        db.commit.assert_not_awaited()
        check_result.with_global_warning.assert_called_once_with("global-warn")
        assert quota_result is check_result.with_global_warning.return_value

    async def test_in_house_quota_exhausted_returns_402_no_commit(self, monkeypatch):
        resolution = ApiKeyResolution(
            provider="openrouter", api_key="sk-or-app", is_in_house=True
        )
        services = _patch_services(monkeypatch, resolver_return=resolution)
        _, quota_service, _, _ = services
        quota_service.check_and_decrement = AsyncMock(
            side_effect=QuotaExhaustedError("chat", remaining=0)
        )
        db = _make_db(prefs=_make_prefs())

        with pytest.raises(HTTPException) as exc:
            await resolve_api_key_with_quota(_make_user(), db, "chat")

        assert exc.value.status_code == 402
        db.commit.assert_not_awaited()

    async def test_non_openrouter_in_house_is_unlimited(self, monkeypatch):
        # The quota branch requires BOTH in-house AND provider == "openrouter".
        # A future non-openrouter in-house provider must not be charged against
        # the OpenRouter daily quota.
        resolution = ApiKeyResolution(
            provider="anthropic", api_key="sk-ant", is_in_house=True
        )
        services = _patch_services(monkeypatch, resolver_return=resolution)
        _, quota_service, usage_service, _ = services

        _, quota_result = await resolve_api_key_with_quota(
            _make_user(), _make_db(prefs=_make_prefs()), "chat"
        )

        assert quota_result is quota_service.unlimited.return_value
        quota_service.check_and_decrement.assert_not_called()
        usage_service.record_and_check.assert_not_called()

    async def test_uses_preferred_model_and_mode_from_prefs(self, monkeypatch):
        # feature="chat" reads conversation_model + openrouter_key_mode from prefs
        # and forwards them to the resolver.
        resolution = ApiKeyResolution(
            provider="openrouter", api_key="k", is_in_house=True
        )
        services = _patch_services(monkeypatch, resolver_return=resolution)
        api_key_service, _, _, _ = services
        user = _make_user()
        db = _make_db(prefs=_make_prefs(model="org/selected", mode="user"))

        await resolve_api_key_with_quota(user, db, "chat")

        api_key_service.resolve_for_chat.assert_awaited_once()
        _, kwargs = api_key_service.resolve_for_chat.call_args
        assert kwargs["preferred_model"] == "org/selected"
        assert kwargs["openrouter_key_mode"] == "user"

    async def test_missing_prefs_defaults_to_app_mode(self, monkeypatch):
        # No UserLLMPreferences row -> preferred_model=None, mode="app".
        resolution = ApiKeyResolution(
            provider="openrouter", api_key="k", is_in_house=False
        )
        services = _patch_services(monkeypatch, resolver_return=resolution)
        api_key_service, _, _, _ = services

        await resolve_api_key_with_quota(_make_user(), _make_db(prefs=None), "chat")

        _, kwargs = api_key_service.resolve_for_chat.call_args
        assert kwargs["preferred_model"] is None
        assert kwargs["openrouter_key_mode"] == "app"
