"""Tests for SSRF protection in ``app.core.url_safety``."""

import httpx
import pytest

from app.core.url_safety import (
    UrlSafetyError,
    ssrf_request_hook,
    validate_external_url,
)


def _resolve_to(addr: str):
    """Build a getaddrinfo-style mock that always resolves to ``addr``."""

    def fake_getaddrinfo(host, *args, **kwargs):
        return [(0, 0, 0, 0, (addr, 0))]

    return fake_getaddrinfo


class TestValidateExternalUrl:
    @pytest.mark.parametrize(
        "addr",
        [
            "127.0.0.1",
            "10.0.0.5",
            "192.168.1.1",
            "172.16.0.1",
            "169.254.169.254",  # cloud metadata IP
            "0.0.0.0",
            "::1",  # IPv6 loopback
            "fe80::1",  # IPv6 link-local
        ],
    )
    def test_blocks_private_and_loopback_addresses(self, monkeypatch, addr):
        monkeypatch.setattr("app.core.url_safety.socket.getaddrinfo", _resolve_to(addr))
        with pytest.raises(UrlSafetyError, match="Refusing private"):
            validate_external_url("https://example.com/x.pdf")

    @pytest.mark.parametrize("scheme", ["file", "ftp", "gopher", "dict", ""])
    def test_rejects_non_http_schemes(self, scheme):
        with pytest.raises(UrlSafetyError, match="non-http"):
            validate_external_url(f"{scheme}:///etc/passwd")

    def test_rejects_metadata_hostname(self, monkeypatch):
        # Even if it resolved to a public IP, the metadata name is blocked.
        monkeypatch.setattr(
            "app.core.url_safety.socket.getaddrinfo",
            lambda host, *a, **k: [(0, 0, 0, 0, ("8.8.8.8", 0))],
        )
        with pytest.raises(UrlSafetyError, match="metadata host"):
            validate_external_url("http://metadata.google.internal/computeMetadata/v1/")

    def test_blocks_literal_internal_ip_without_dns(self):
        # A literal-IP URL must be blocked directly (no DNS needed).
        with pytest.raises(UrlSafetyError, match="Refusing private"):
            validate_external_url("http://169.254.169.254/latest/meta-data/")

    def test_blocks_if_any_resolved_address_is_private(self, monkeypatch):
        # Split-horizon: one public + one private -> must block.
        def mixed(host, *args, **kwargs):
            return [
                (0, 0, 0, 0, ("8.8.8.8", 0)),
                (0, 0, 0, 0, ("10.1.2.3", 0)),
            ]

        monkeypatch.setattr("app.core.url_safety.socket.getaddrinfo", mixed)
        with pytest.raises(UrlSafetyError):
            validate_external_url("https://example.com/x.pdf")

    def test_allows_public_hostname(self, monkeypatch):
        monkeypatch.setattr(
            "app.core.url_safety.socket.getaddrinfo", _resolve_to("8.8.8.8")
        )
        # Should not raise.
        validate_external_url("https://example.com/paper.pdf")

    def test_allows_literal_public_ip(self):
        # No exception expected for a public literal IP.
        validate_external_url("https://8.8.8.8/paper.pdf")

    def test_unresolvable_host_is_rejected(self, monkeypatch):
        import socket

        def raises(host, *args, **kwargs):
            raise socket.gaierror("no such host")

        monkeypatch.setattr("app.core.url_safety.socket.getaddrinfo", raises)
        with pytest.raises(UrlSafetyError, match="Could not resolve"):
            validate_external_url("https://nonexistent.invalid/x.pdf")

    def test_accepts_httpx_url_object(self, monkeypatch):
        monkeypatch.setattr(
            "app.core.url_safety.socket.getaddrinfo", _resolve_to("8.8.8.8")
        )
        validate_external_url(httpx.URL("https://example.com/x.pdf"))


class TestSsrfRequestHook:
    async def test_hook_blocks_internal_request(self, monkeypatch):
        # Literal internal IP — no DNS involved.
        request = httpx.Request("GET", "http://10.0.0.1/secret")
        with pytest.raises(UrlSafetyError):
            await ssrf_request_hook(request)

    async def test_hook_allows_public_request(self, monkeypatch):
        monkeypatch.setattr(
            "app.core.url_safety.socket.getaddrinfo",
            _resolve_to("8.8.8.8"),
        )
        request = httpx.Request("GET", "https://example.com/x.pdf")
        await ssrf_request_hook(request)  # should not raise

    async def test_hook_fires_on_redirect_target(self, monkeypatch):
        """The request hook validates each redirect hop, so a public->internal
        redirect is blocked at the second request."""
        public = "https://example.com"
        internal = "https://169.254.169.254"

        def fake_getaddrinfo(host, *args, **kwargs):
            # The redirect target resolves to a public IP (its hostname is a
            # literal internal IP, so it is validated directly without DNS).
            return [(0, 0, 0, 0, ("8.8.8.8", 0))]

        monkeypatch.setattr("app.core.url_safety.socket.getaddrinfo", fake_getaddrinfo)

        first = httpx.Request("GET", public)
        await ssrf_request_hook(first)  # initial public request OK

        redirected = httpx.Request("GET", internal)  # 302 Location -> internal
        with pytest.raises(UrlSafetyError):
            await ssrf_request_hook(redirected)
