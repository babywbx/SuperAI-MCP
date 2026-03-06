"""Unit tests for Claude quota provider."""

import json
from unittest.mock import AsyncMock, patch

from superai_mcp.quota._claude import fetch_claude_quota

_KEYCHAIN_JSON = json.dumps(
    {
        "claudeAiOauth": {
            "accessToken": "sk-ant-oat01-fake-token",
            "refreshToken": "sk-ant-ort01-fake",
            "expiresAt": 9999999999999,
            "scopes": ["user:inference", "user:profile"],
            "subscriptionType": "max",
            "rateLimitTier": "default_claude_max_20x",
        }
    }
)

_USAGE_RESPONSE = {
    "five_hour": {"utilization": 25.0, "resets_at": "2026-03-05T18:00:00Z"},
    "seven_day": {"utilization": 10.0, "resets_at": "2026-03-10T00:00:00Z"},
    "seven_day_opus": {"utilization": 5.0, "resets_at": "2026-03-10T00:00:00Z"},
    "seven_day_sonnet": {"utilization": 8.0, "resets_at": "2026-03-10T00:00:00Z"},
}


class TestFetchClaudeQuota:
    async def test_success(self) -> None:
        with patch(
            "superai_mcp.quota._claude._read_credentials",
            return_value=json.loads(_KEYCHAIN_JSON),
        ):
            with patch(
                "superai_mcp.quota._claude.http_get",
                new_callable=AsyncMock,
                return_value=_USAGE_RESPONSE,
            ):
                result = await fetch_claude_quota()
        assert result.success is True
        assert result.provider == "claude"
        assert result.plan_type == "max"
        assert result.sessions["current"].used_percent == 25.0
        assert result.sessions["current"].remaining_percent == 75.0
        assert result.sessions["weekly"].used_percent == 10.0
        assert result.sessions["weekly_opus"].used_percent == 5.0
        assert result.sessions["weekly_sonnet"].used_percent == 8.0

    async def test_no_credentials(self) -> None:
        with patch(
            "superai_mcp.quota._claude._read_credentials",
            side_effect=FileNotFoundError("no creds"),
        ):
            result = await fetch_claude_quota()
        assert result.success is False
        assert "no creds" in (result.error or "")

    async def test_api_error(self) -> None:
        with patch(
            "superai_mcp.quota._claude._read_credentials",
            return_value=json.loads(_KEYCHAIN_JSON),
        ):
            with patch(
                "superai_mcp.quota._claude.http_get",
                new_callable=AsyncMock,
                side_effect=Exception("HTTP 401"),
            ):
                result = await fetch_claude_quota()
        assert result.success is False
        assert "401" in (result.error or "")

    async def test_missing_user_profile_scope(self) -> None:
        creds = json.loads(_KEYCHAIN_JSON)
        creds["claudeAiOauth"]["scopes"] = ["user:inference"]
        with patch("superai_mcp.quota._claude._read_credentials", return_value=creds):
            result = await fetch_claude_quota()
        assert result.success is False
        assert "user:profile" in (result.error or "")
