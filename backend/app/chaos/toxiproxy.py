"""Toxiproxy HTTP client. Toxiproxy rejects browser-like User-Agents, so we always send our own."""

import httpx

from app.config import settings
from app.errors import AppError

HEADERS = {"User-Agent": "sentinel"}


def _request(method: str, path: str, what: str, json: dict | None = None, ok_404: bool = False) -> None:
    try:
        with httpx.Client(base_url=settings.toxiproxy_url, headers=HEADERS, timeout=5.0) as client:
            resp = client.request(method, path, json=json)
    except httpx.HTTPError as exc:
        raise AppError(502, "chaos_failed", f"Cannot reach Toxiproxy at {settings.toxiproxy_url}: {exc}")
    if resp.status_code == 404 and ok_404:
        return
    if resp.status_code >= 400:
        raise AppError(
            502, "chaos_failed", f"Toxiproxy could not {what}: HTTP {resp.status_code} {resp.text.strip()}"
        )


def add_toxic(proxy: str, name: str, toxic_type: str, attributes: dict) -> None:
    _request(
        "POST",
        f"/proxies/{proxy}/toxics",
        f"add {toxic_type} toxic to proxy '{proxy}'",
        json={"name": name, "type": toxic_type, "stream": "downstream", "toxicity": 1.0, "attributes": attributes},
    )


def remove_toxic(proxy: str, name: str) -> None:
    _request("DELETE", f"/proxies/{proxy}/toxics/{name}", f"remove toxic from proxy '{proxy}'", ok_404=True)


def set_enabled(proxy: str, enabled: bool) -> None:
    state = "enable" if enabled else "disable"
    _request("POST", f"/proxies/{proxy}", f"{state} proxy '{proxy}'", json={"enabled": enabled})