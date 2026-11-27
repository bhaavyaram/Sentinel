"""Health probes. Return True (healthy), False (failed) or None (no probe possible)."""

import socket
from urllib.parse import urlparse

import httpx


def to_ipv4_loopback(address: str) -> str:
    """Published ports listen on 127.0.0.1 only. On Windows, 'localhost' tries IPv6 (::1) first
    and the refused attempt costs about a second, so we go straight to IPv4."""
    return address.replace("//localhost:", "//127.0.0.1:", 1).replace("//localhost/", "//127.0.0.1/", 1)


def probe(address: str | None, timeout: float = 1.0) -> bool | None:
    if not address:
        return None
    if address.startswith("tcp://"):
        return _probe_tcp(to_ipv4_loopback(address), timeout)
    if address.startswith(("http://", "https://")):
        return _probe_http(to_ipv4_loopback(address), timeout)
    return None  # a bare "/path" has no host to call, so nothing can be probed


def _probe_tcp(address: str, timeout: float) -> bool:
    try:
        parsed = urlparse(address)
        host, port = parsed.hostname, parsed.port
    except ValueError:
        return False
    if not host or not port:
        return False
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _probe_http(address: str, timeout: float) -> bool:
    try:
        response = httpx.get(address, timeout=timeout, headers={"User-Agent": "sentinel"})
    except httpx.HTTPError:
        return False
    return response.status_code < 400