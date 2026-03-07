"""Gemini quota provider — OAuth creds + token refresh + quota API."""

from __future__ import annotations

import asyncio
import json
import re
import shutil
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from ._http import http_get, http_post
from ._models import QuotaResult, SessionQuota

_SETTINGS_FILE = Path.home() / ".gemini" / "settings.json"
_OAUTH_CREDS_FILE = Path.home() / ".gemini" / "oauth_creds.json"

_QUOTA_URL = "https://cloudcode-pa.googleapis.com/v1internal:retrieveUserQuota"
_CODE_ASSIST_URL = "https://cloudcode-pa.googleapis.com/v1internal:loadCodeAssist"
_PROJECTS_URL = "https://cloudresourcemanager.googleapis.com/v1/projects"
_TOKEN_URL = "https://oauth2.googleapis.com/token"

_gemini_project_id_cache: dict[str, str] = {}

_PRO_KEYWORDS = ("pro",)
_FLASH_KEYWORDS = ("flash",)


def _read_settings() -> dict:
    if not _SETTINGS_FILE.exists():
        raise FileNotFoundError(f"not found: {_SETTINGS_FILE}")
    return json.loads(_SETTINGS_FILE.read_text())


def _read_oauth_creds() -> dict:
    if not _OAUTH_CREDS_FILE.exists():
        raise FileNotFoundError(f"not found: {_OAUTH_CREDS_FILE}")
    return json.loads(_OAUTH_CREDS_FILE.read_text())


def _write_oauth_creds(creds: dict) -> None:
    _OAUTH_CREDS_FILE.write_text(json.dumps(creds, indent=2))


def _is_expired(creds: dict) -> bool:
    expiry_ms = creds.get("expiry_date", 0)
    return time.time() * 1000 >= expiry_ms - 60_000


def _find_oauth2_js() -> str:
    """Locate oauth2.js in the Gemini CLI installation."""
    gemini_bin = shutil.which("gemini")
    if not gemini_bin:
        raise FileNotFoundError("gemini CLI not in PATH")
    wrapper = Path(gemini_bin).read_text()
    for line in wrapper.splitlines():
        if "node_modules/@google/gemini-cli/dist/index.js" in line:
            match = re.search(r'["\s]([^\s"]+/node_modules/@google/gemini-cli/)', line)
            if match:
                base = match.group(1)
                candidates = [
                    Path(base)
                    / "node_modules/@google/gemini-cli-core/dist/src/code_assist/oauth2.js",
                    Path(base).parent
                    / "@google/gemini-cli-core/dist/src/code_assist/oauth2.js",
                ]
                for c in candidates:
                    if c.exists():
                        return str(c)
    raise FileNotFoundError("oauth2.js not found in Gemini CLI installation")


def _extract_oauth_client(oauth2_js_path: str) -> tuple[str, str]:
    """Extract OAUTH_CLIENT_ID and OAUTH_CLIENT_SECRET from oauth2.js."""
    if not Path(oauth2_js_path).exists():
        raise FileNotFoundError(f"not found: {oauth2_js_path}")
    text = Path(oauth2_js_path).read_text()
    cid_match = re.search(r"OAUTH_CLIENT_ID\s*=\s*['\"]([^'\"]+)['\"]", text)
    csecret_match = re.search(r"OAUTH_CLIENT_SECRET\s*=\s*['\"]([^'\"]+)['\"]", text)
    if not cid_match or not csecret_match:
        raise ValueError("could not extract OAuth client ID/secret from oauth2.js")
    return cid_match.group(1), csecret_match.group(1)


async def _refresh_token(creds: dict) -> dict:
    """Refresh the OAuth token and update creds file."""
    js_path = await asyncio.to_thread(_find_oauth2_js)
    client_id, client_secret = await asyncio.to_thread(_extract_oauth_client, js_path)

    form_data = urllib.parse.urlencode(
        {
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": creds["refresh_token"],
            "grant_type": "refresh_token",
        }
    ).encode()

    def _do_refresh() -> dict:
        req = urllib.request.Request(_TOKEN_URL, data=form_data, method="POST")
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())

    data = await asyncio.to_thread(_do_refresh)
    creds["access_token"] = data["access_token"]
    creds["expiry_date"] = int(time.time() * 1000) + data.get("expires_in", 3600) * 1000
    await asyncio.to_thread(_write_oauth_creds, creds)
    return creds


async def _get_project_id(headers: dict[str, str]) -> str:
    """Get Gemini project ID (cached)."""
    if "project_id" in _gemini_project_id_cache:
        return _gemini_project_id_cache["project_id"]

    try:
        data = await http_post(
            _CODE_ASSIST_URL,
            headers,
            {
                "metadata": {"ideType": "GEMINI_CLI", "pluginType": "GEMINI"},
            },
        )
        pid = data.get("cloudaicompanionProject", "")
        if pid:
            _gemini_project_id_cache["project_id"] = pid
            return pid
    except Exception:
        pass

    data = await http_get(_PROJECTS_URL, headers)
    for proj in data.get("projects", []):
        pid = proj.get("projectId", "")
        if pid.startswith("gen-lang-client"):
            _gemini_project_id_cache["project_id"] = pid
            return pid
        labels = proj.get("labels", {})
        if "generative-language" in labels:
            _gemini_project_id_cache["project_id"] = pid
            return pid

    raise ValueError("no Gemini project found")


def _classify_model(model_id: str) -> str | None:
    lower = model_id.lower()
    if any(k in lower for k in _PRO_KEYWORDS):
        return "pro"
    if any(k in lower for k in _FLASH_KEYWORDS):
        return "flash"
    return None


def _format_resets_in(resets_at: str) -> str | None:
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


async def fetch_gemini_quota() -> QuotaResult:
    """Fetch Gemini account quota via private API."""
    try:
        settings = await asyncio.to_thread(_read_settings)
    except Exception as e:
        return QuotaResult(provider="gemini", error=str(e))

    auth_type = settings.get("security", {}).get("auth", {}).get("selectedType", "")
    if auth_type not in ("oauth-personal", ""):
        return QuotaResult(
            provider="gemini",
            error=f"unsupported auth type: {auth_type}, need oauth-personal",
        )

    try:
        creds = await asyncio.to_thread(_read_oauth_creds)
    except Exception as e:
        return QuotaResult(provider="gemini", error=str(e))

    if _is_expired(creds):
        try:
            creds = await _refresh_token(creds)
        except Exception as e:
            return QuotaResult(provider="gemini", error=f"token refresh failed: {e}")

    headers = {"Authorization": f"Bearer {creds['access_token']}"}

    try:
        project_id = await _get_project_id(headers)
    except Exception as e:
        return QuotaResult(provider="gemini", error=f"project discovery failed: {e}")

    try:
        data = await http_post(_QUOTA_URL, headers, {"project": project_id})
    except Exception as e:
        return QuotaResult(provider="gemini", error=str(e))

    groups: dict[str, list[dict]] = {}
    for bucket in data.get("buckets", data.get("quotaBuckets", [])):
        model_id = bucket.get("modelId", "")
        cls = _classify_model(model_id)
        if cls:
            groups.setdefault(cls, []).append(bucket)

    sessions: dict[str, SessionQuota] = {}
    for cls, buckets in groups.items():
        worst = min(buckets, key=lambda b: b.get("remainingFraction", 1.0))
        remaining = worst.get("remainingFraction", 1.0)
        used = round((1 - remaining) * 100, 2)
        resets_at = worst.get("resetTime")
        sessions[cls] = SessionQuota(
            used_percent=used,
            remaining_percent=round(remaining * 100, 2),
            resets_at=resets_at,
            resets_in=_format_resets_in(resets_at) if resets_at else None,
        )

    return QuotaResult(provider="gemini", success=True, sessions=sessions)
