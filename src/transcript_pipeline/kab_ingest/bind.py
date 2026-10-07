"""Bind-address policy for the K'ab ingest receiver.

Allowed binds, exactly and exhaustively:
- IPv4 loopback 127.0.0.0/8 (tests and same-machine senders)
- IPv4 RFC1918 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16 (the LAN trust zone)
- IPv6 loopback ::1 and IPv6 unique-local fc00::/7

Everything else is rejected: wildcard (0.0.0.0/::), public addresses,
link-local, multicast, and any hostname/DNS name (a name would resolve to
whatever the network says at startup time — the policy is defined on
addresses, not names). There is no container-mode widening here: the
receiver is opt-in per deployment and a wildcard bind has no legitimate
use for a LAN-local ingest.
"""

from __future__ import annotations

import ipaddress

from transcript_pipeline.errors import ConfigurationError

_ALLOWED_V4_NETWORKS = (
    ipaddress.IPv4Network("127.0.0.0/8"),
    ipaddress.IPv4Network("10.0.0.0/8"),
    ipaddress.IPv4Network("172.16.0.0/12"),
    ipaddress.IPv4Network("192.168.0.0/16"),
)
_ALLOWED_V6_NETWORKS = (
    ipaddress.IPv6Network("::1/128"),
    ipaddress.IPv6Network("fc00::/7"),
)


def is_allowed_bind_address(addr: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if isinstance(addr, ipaddress.IPv4Address):
        return any(addr in net for net in _ALLOWED_V4_NETWORKS)
    return any(addr in net for net in _ALLOWED_V6_NETWORKS)


def validate_bind_host(raw: str) -> str:
    """Validates a bind host and returns its normalized textual form."""
    candidate = (raw or "").strip().strip("[]")
    if not candidate:
        raise ConfigurationError("KAB_INGEST_HOST is empty.")
    try:
        addr = ipaddress.ip_address(candidate)
    except ValueError as exc:
        raise ConfigurationError(
            f"KAB_INGEST_HOST must be a literal IP address (loopback, RFC1918 or IPv6 ULA); "
            f"hostnames/DNS names are not accepted: {raw!r}"
        ) from exc
    if not is_allowed_bind_address(addr):
        raise ConfigurationError(
            f"KAB_INGEST_HOST {candidate!r} is not an allowed bind address "
            "(allowed: 127.0.0.0/8, 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16, ::1, fc00::/7)."
        )
    return str(addr)
