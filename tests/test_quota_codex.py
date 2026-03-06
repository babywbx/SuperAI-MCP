"""Unit tests for Codex quota provider."""

import json
from unittest.mock import AsyncMock, patch

from superai_mcp.quota._codex import fetch_codex_quota

_AUTH_JSON = {
    "auth_mode": "oauth",
    "tokens": {
        "access_token": "fake-access-token",
        "account_id": "acct-123",
    },
}

_USAGE_RESPONSE = {
    "plan_type": "plus",
    "rate_limit": {
        "primary_window": {
            "used_percent": 30.0,
            "reset_at": 1741200000,
        },
        "secondary_window": {
            "used_percent": 12.0,
            "reset_at": 1741800000,
        },
    },
}


class TestFetchCodexQuota:
    async def test_success(self) -> None:
        with patch("superai_mcp.quota._codex._read_auth", return_value=_AUTH_JSON):
            with patch(
                "superai_mcp.quota._codex.http_get",
                new_callable=AsyncMock,
                return_value=_USAGE_RESPONSE,
            ):
                result = await fetch_codex_quota()
        assert result.success is True
        assert result.provider == "codex"
        assert result.plan_type == "plus"
        assert result.sessions["current"].used_percent == 30.0
        assert result.sessions["current"].remaining_percent == 70.0
        assert result.sessions["weekly"].used_percent == 12.0

    async def test_no_auth_file(self) -> None:
        with patch(
            "superai_mcp.quota._codex._read_auth",
            side_effect=FileNotFoundError("not found"),
        ):
            result = await fetch_codex_quota()
        assert result.success is False
        assert "not found" in (result.error or "")

    async def test_jwt_fallback_for_account_id(self) -> None:
        import base64

        payload = (
            base64.urlsafe_b64encode(
                json.dumps({"chatgpt_account_id": "acct-from-jwt"}).encode()
            )
            .rstrip(b"=")
            .decode()
        )
        auth = {"tokens": {"access_token": f"header.{payload}.sig"}}
        with patch("superai_mcp.quota._codex._read_auth", return_value=auth):
            with patch(
                "superai_mcp.quota._codex.http_get",
                new_callable=AsyncMock,
                return_value=_USAGE_RESPONSE,
            ) as mock_get:
                result = await fetch_codex_quota()
        assert result.success is True
        call_headers = mock_get.call_args[0][1]
        assert call_headers["ChatGPT-Account-Id"] == "acct-from-jwt"

    async def test_no_rate_limit(self) -> None:
        resp = {"plan_type": "free"}
        with patch("superai_mcp.quota._codex._read_auth", return_value=_AUTH_JSON):
            with patch(
                "superai_mcp.quota._codex.http_get",
                new_callable=AsyncMock,
                return_value=resp,
            ):
                result = await fetch_codex_quota()
        assert result.success is True
        assert result.sessions == {}
