"""SSRF protection for server-side fetches of user-supplied URLs.

Users can link PDFs by arbitrary URL (``Pdf.source_url``); the backend then
fetches those URLs for citation extraction, indexing, and sharing. Without
validation that is a server-side request forgery (SSRF) vector — an attacker
can point the backend at internal services (cloud metadata endpoint, loopback
services, private network hosts).

This module provides:

- :func:`validate_external_url` — scheme + DNS-resolved-IP allowlist.
- :func:`ssrf_request_hook` — an httpx ``request`` event hook that validates
  the URL of *every* outbound request, including each redirect hop.

Residual risk (accepted): there is a TOCTOU window between validation and the
actual connect because httpx re-resolves the host. Pinning the validated IP
into the connection would close it but requires a custom transport and is out
of scope for this guard; the hook still blocks the common direct-internal-URL
and redirect-to-internal cases.
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

import httpx

_ALLOWED_SCHEMES = frozenset({"http", "https"})

# Cloud metadata endpoints that resolve to a non-public address but are
# worth naming explicitly for clarity / defense-in-depth.
_BLOCKED_HOSTNAMES = frozenset({"metadata.google.internal", "metadata"})


class UrlSafetyError(ValueError):
    """Raised when a URL is not safe to fetch server-side."""


def _is_blocked_address(addr: str) -> bool:
    ip = ipaddress.ip_address(addr)
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def validate_external_url(url: str | httpx.URL) -> None:
    """Validate that ``url`` is safe for the backend to fetch.

    Allowed: ``http``/``https`` schemes whose host resolves only to public,
    non-reserved IP addresses. Rejects loopback, private, link-local,
    multicast, reserved, and unspecified addresses, as well as cloud metadata
    hostnames. Raises :class:`UrlSafetyError` otherwise.
    """
    url_str = str(url)
    parsed = urlparse(url_str)
    if parsed.scheme not in _ALLOWED_SCHEMES:
        raise UrlSafetyError(f"Refusing non-http(s) URL: {url_str!r}")

    host = parsed.hostname
    if not host:
        raise UrlSafetyError(f"URL has no host: {url_str!r}")
    if host.lower() in _BLOCKED_HOSTNAMES:
        raise UrlSafetyError(f"Refusing metadata host: {host!r}")

    # If the host is already a literal IP, validate it directly without DNS.
    try:
        ipaddress.ip_address(host)
        infos = [(0, 0, 0, 0, (host, 0))]
    except ValueError:
        try:
            infos = socket.getaddrinfo(host, None)
        except socket.gaierror as exc:
            raise UrlSafetyError(f"Could not resolve host {host!r}: {exc}") from exc

    # Block if *any* resolved address is internal. A split-horizon hostname that
    # resolves to both public and private must be treated as unsafe.
    for info in infos:
        addr = info[4][0]
        try:
            blocked = _is_blocked_address(addr)
        except ValueError as exc:  # malformed address — refuse defensively
            raise UrlSafetyError(
                f"Unusable address {addr!r} for host {host!r}"
            ) from exc
        if blocked:
            raise UrlSafetyError(
                f"Refusing private/loopback/reserved address {addr} for {host!r}"
            )


async def ssrf_request_hook(request: httpx.Request) -> None:
    """httpx request event hook that SSRF-checks each outbound URL.

    Attach with ``httpx.AsyncClient(event_hooks={"request": [ssrf_request_hook]})``.
    Fires on the initial request and on every redirect hop, so redirect-based
    SSRF is also blocked.
    """
    validate_external_url(request.url)
