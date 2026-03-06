"""Claude quota provider — Keychain OAuth + Anthropic usage API."""

from __future__ import annotations

import asyncio
import json
import platform
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from ._http import http_get
from ._models import QuotaResult, SessionQuota

_API_URL = "https://api.anthropic.com/api/oauth/usage"
_BETA_HEADER = "oauth-2025-04-20"
_KEYCHAIN_SERVICE = "Claude Code-credentials"
_CREDS_FILE = Path.home() / ".claude" / ".credentials.json"


def _read_credentials() -> dict:
    """Read Claude OAuth credentials from Keychain (macOS) or file fallback."""
    if platform.system() == "Darwin":
        try:
            r = subprocess.run(
                ["security", "find-generic-password", "-s", _KEYCHAIN_SERVICE, "-w"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if r.returncode == 0 and r.stdout.strip():
                return json.loads(r.stdout.strip())
        except Exception:
            pass
    if _CREDS_FILE.exists():
        return json.loads(_CREDS_FILE.read_text())
    raise FileNotFoundError(
        f"credentials not found: Keychain '{_KEYCHAIN_SERVICE}' or {_CREDS_FILE}"
    )


def _format_resets_in(resets_at: str) -> str | None:
    """Convert ISO 8601 timestamp to human-readable duration."""
    try:
        dt = datetime.fromisoformat(resets_at.replace("Z", "+00:00"))
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


def _parse_session(data: dict) -> SessionQuota | None:
    """Parse a session block from the usage API response."""
    if not data:
        return None
    utilization = data.get("utilization")
    if utilization is None:
        return None
    resets_at = data.get("resets_at")
    return SessionQuota(
        used_percent=utilization,
        remaining_percent=round(100 - utilization, 2)
        if utilization is not None
        else None,
        resets_at=resets_at,
        resets_in=_format_resets_in(resets_at) if resets_at else None,
    )


async def fetch_claude_quota() -> QuotaResult:
    """Fetch Claude account quota via OAuth API."""
    try:
        creds = await asyncio.to_thread(_read_credentials)
    except Exception as e:
        return QuotaResult(provider="claude", error=str(e))

    oauth = creds.get("claudeAiOauth", {})
    token = oauth.get("accessToken", "")
    scopes = oauth.get("scopes", [])
    plan_type = oauth.get("subscriptionType")

    if "user:profile" not in scopes:
        return QuotaResult(
            provider="claude",
            error="token missing user:profile scope (has: " + ", ".join(scopes) + ")",
        )

    try:
        data = await http_get(
            _API_URL,
            {
                "Authorization": f"Bearer {token}",
                "anthropic-beta": _BETA_HEADER,
            },
        )
    except Exception as e:
        return QuotaResult(provider="claude", error=str(e))

    sessions: dict[str, SessionQuota] = {}
    mapping = {
        "five_hour": "current",
        "seven_day": "weekly",
        "seven_day_opus": "weekly_opus",
        "seven_day_sonnet": "weekly_sonnet",
    }
    for api_key, session_key in mapping.items():
        if sq := _parse_session(data.get(api_key, {})):
            sessions[session_key] = sq

    return QuotaResult(
        provider="claude", success=True, plan_type=plan_type, sessions=sessions
    )
