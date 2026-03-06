"""Codex quota provider — auth.json + ChatGPT usage API."""

from __future__ import annotations

import asyncio
import base64
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from ._http import http_get
from ._models import QuotaResult, SessionQuota

_API_URL = "https://chatgpt.com/backend-api/wham/usage"


def _auth_path() -> Path:
    """Return path to Codex auth.json."""
    codex_home = os.environ.get("CODEX_HOME")
    if codex_home:
        return Path(codex_home) / "auth.json"
    return Path.home() / ".codex" / "auth.json"


def _read_auth() -> dict:
    """Read Codex auth credentials."""
    path = _auth_path()
    if not path.exists():
        raise FileNotFoundError(f"credentials not found: {path}")
    return json.loads(path.read_text())


def _extract_account_id_from_jwt(token: str) -> str | None:
    """Decode JWT payload to extract chatgpt_account_id."""
    try:
        parts = token.split(".")
        if len(parts) < 2:
            return None
        payload = parts[1]
        padding = 4 - len(payload) % 4
        if padding != 4:
            payload += "=" * padding
        data = json.loads(base64.urlsafe_b64decode(payload))
        return data.get("chatgpt_account_id")
    except Exception:
        return None


def _format_resets_in(reset_at: int) -> str | None:
    """Convert Unix timestamp to human-readable duration."""
    try:
        dt = datetime.fromtimestamp(reset_at, tz=timezone.utc)
        delta = dt - datetime.now(timezone.utc)
        total = int(delta.total_seconds())
        if total <= 0:
            return "now"
        hours, remainder = divmod(total, 3600)
        minutes = remainder // 60
        if hours > 24:
            days = hours // 24
            return f"{days}d {hours % 24}h"
        if hours > 0:
            return f"{hours}h {minutes}m"
        return f"{minutes}m"
    except Exception:
        return None


def _parse_window(data: dict | None) -> SessionQuota | None:
    """Parse a rate limit window."""
    if not data:
        return None
    used = data.get("used_percent")
    if used is None:
        return None
    reset_at = data.get("reset_at", 0)
    resets_at_iso = (
        datetime.fromtimestamp(reset_at, tz=timezone.utc).isoformat()
        if reset_at
        else None
    )
    return SessionQuota(
        used_percent=used,
        remaining_percent=round(100 - used, 2),
        resets_at=resets_at_iso,
        resets_in=_format_resets_in(reset_at) if reset_at else None,
    )


async def fetch_codex_quota() -> QuotaResult:
    """Fetch Codex account quota via ChatGPT API."""
    try:
        auth = await asyncio.to_thread(_read_auth)
    except Exception as e:
        return QuotaResult(provider="codex", error=str(e))

    tokens = auth.get("tokens", auth)
    access_token = tokens.get("access_token", "")
    account_id = tokens.get("account_id", "")

    if not account_id:
        account_id = _extract_account_id_from_jwt(access_token) or ""
    if not access_token:
        return QuotaResult(provider="codex", error="no access_token in auth.json")
    if not account_id:
        return QuotaResult(provider="codex", error="no account_id in auth.json or JWT")

    try:
        data = await http_get(
            _API_URL,
            {
                "Authorization": f"Bearer {access_token}",
                "ChatGPT-Account-Id": account_id,
            },
        )
    except Exception as e:
        return QuotaResult(provider="codex", error=str(e))

    rate_limit = data.get("rate_limit", {})
    sessions: dict[str, SessionQuota] = {}
    if sq := _parse_window(rate_limit.get("primary_window")):
        sessions["current"] = sq
    if sq := _parse_window(rate_limit.get("secondary_window")):
        sessions["weekly"] = sq

    return QuotaResult(
        provider="codex",
        success=True,
        plan_type=data.get("plan_type"),
        sessions=sessions,
    )
