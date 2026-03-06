"""Lightweight async HTTP helpers using urllib (zero deps)."""

from __future__ import annotations

import asyncio
import json
import urllib.request
from urllib.error import HTTPError, URLError

_TIMEOUT = 15


class QuotaHTTPError(Exception):
    """HTTP request failed."""


def _do_get(url: str, headers: dict[str, str], timeout: int) -> dict:
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
    except HTTPError as e:
        body = e.read()[:200].decode(errors="replace") if e.fp else ""
        raise QuotaHTTPError(f"HTTP {e.code}: {body}") from e
    except URLError as e:
        raise QuotaHTTPError(f"request failed: {e.reason}") from e
    if raw.lstrip()[:15].lower().startswith((b"<!doctype", b"<html")):
        raise QuotaHTTPError("got HTML instead of JSON")
    return json.loads(raw)


def _do_post(url: str, headers: dict[str, str], body: dict, timeout: int) -> dict:
    data = json.dumps(body).encode()
    hdrs = {**headers, "Content-Type": "application/json"}
    req = urllib.request.Request(url, data=data, headers=hdrs, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
    except HTTPError as e:
        err_body = e.read()[:200].decode(errors="replace") if e.fp else ""
        raise QuotaHTTPError(f"HTTP {e.code}: {err_body}") from e
    except URLError as e:
        raise QuotaHTTPError(f"request failed: {e.reason}") from e
    if raw.lstrip()[:15].lower().startswith((b"<!doctype", b"<html")):
        raise QuotaHTTPError("got HTML instead of JSON")
    return json.loads(raw)


async def http_get(url: str, headers: dict[str, str], timeout: int = _TIMEOUT) -> dict:
    """Async GET returning parsed JSON."""
    return await asyncio.to_thread(_do_get, url, headers, timeout)


async def http_post(
    url: str, headers: dict[str, str], body: dict, timeout: int = _TIMEOUT
) -> dict:
    """Async POST returning parsed JSON."""
    return await asyncio.to_thread(_do_post, url, headers, body, timeout)
