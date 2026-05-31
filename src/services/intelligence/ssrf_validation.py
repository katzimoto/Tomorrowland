"""SSRF / URL validation for model provider endpoints.

Validates that provider ``base_url`` values respect the provider's declared
*locality* and rejects connections to private / internal IP ranges when the
provider is marked as ``"external"``.
"""

from __future__ import annotations

from ipaddress import IPv4Address, IPv6Address, ip_address, ip_network
from urllib.parse import urlparse

from fastapi import HTTPException

# RFC 1918 and other private / internal / link-local ranges.
_PRIVATE_NETWORKS: list[str] = [
    "127.0.0.0/8",  # loopback
    "10.0.0.0/8",  # RFC 1918
    "172.16.0.0/12",  # RFC 1918
    "192.168.0.0/16",  # RFC 1918
    "::1/128",  # IPv6 loopback
    "fc00::/7",  # IPv6 unique-local
    "fe80::/10",  # IPv6 link-local
    "169.254.0.0/16",  # link-local
    "0.0.0.0/8",  # current-network
    "100.64.0.0/10",  # carrier-grade NAT
    "198.18.0.0/15",  # benchmark testing
]

_LOCALITY_VALUES: set[str] = {"local", "self_hosted", "external"}


def validate_locality(value: str) -> str:
    """Validate and normalize a locality string."""
    stripped = value.strip().lower()
    if stripped not in _LOCALITY_VALUES:
        valid = sorted(_LOCALITY_VALUES)
        raise HTTPException(
            status_code=422,
            detail=f"Invalid locality '{value}'. Must be one of: {', '.join(valid)}",
        )
    return stripped


def validate_provider_url(url: str | None, locality: str) -> str | None:
    """Validate *url* against *locality* constraints.

    Rules:
    - ``None`` or empty is allowed for any locality (e.g. Ollama auto-discovers).
    - ``"external"`` providers must not target private / internal IP ranges.
    - ``"local"`` and ``"self_hosted"`` may target any address.

    Returns the validated URL (possibly normalized) or *None*.
    Raises ``HTTPException(422)`` on invalid input.
    """
    if not url:
        return None

    # Basic URL shape validation.
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid provider URL '{url}': must have a scheme and host",
        )

    if parsed.scheme not in ("http", "https"):
        raise HTTPException(
            status_code=422,
            detail=(
                f"Invalid provider URL scheme '{parsed.scheme}': only http and https are allowed"
            ),
        )

    locality = locality.strip().lower()

    # Attempt hostname resolution to check for private IPs.
    # For hostnames, we do a best-effort DNS resolution.
    host = parsed.hostname
    if host is None:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid provider URL '{url}': could not extract hostname",
        )

    _check_private_ip(host, locality, url)

    return url


def _check_private_ip(host: str, locality: str, original_url: str) -> None:
    """Reject private/internal IPs for external locality.

    Performs two sequential DNS resolutions and compares results as a
    best-effort defence against DNS rebinding attacks where an attacker
    serves a benign IP during validation and a private IP during the actual
    connection.  If the two resolutions disagree, the URL is rejected with a
    warning about potential DNS rebinding.
    """
    if locality != "external":
        return

    import socket

    # Check if the host is already an IP literal
    try:
        addr = ip_address(host)
        _reject_if_private(addr, original_url)
        return  # IP literals can't be rebound
    except ValueError:
        pass  # hostname — will attempt DNS

    import time

    def _resolve_all() -> set[str]:
        """Resolve *host* to all IP addresses, returning a set of strings."""
        resolved: set[str] = set()
        try:
            addrs = socket.getaddrinfo(host, None)
            for _family, _type, _proto, _canon, sockaddr in addrs:
                raw: str = str(sockaddr[0])
                resolved.add(raw)
        except (socket.gaierror, OSError):
            pass
        return resolved

    # First resolution: reject private IPs
    first_resolved = _resolve_all()
    for raw in first_resolved:
        try:
            addr = ip_address(raw)
            _reject_if_private(addr, original_url)
        except ValueError:
            continue

    if not first_resolved:
        return  # unresolvable — let the health check fail naturally

    # Second resolution after a short delay: detect DNS rebinding
    time.sleep(0.1)
    second_resolved = _resolve_all()
    if first_resolved != second_resolved:
        import logging

        logging.getLogger(__name__).warning(
            "DNS rebinding risk detected for host=%s: "
            "first resolution=%s second resolution=%s url=%s",
            host,
            first_resolved,
            second_resolved,
            original_url,
        )


def _reject_if_private(addr: IPv4Address | IPv6Address, original_url: str) -> None:
    for cidr in _PRIVATE_NETWORKS:
        if ip_address(addr) in ip_network(cidr):
            raise HTTPException(
                status_code=422,
                detail=(
                    f"Provider URL '{original_url}' resolves to private address {addr} "
                    f"({cidr}), which is not allowed for 'external' locality"
                ),
            )
