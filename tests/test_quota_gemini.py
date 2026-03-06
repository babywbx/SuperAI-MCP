"""Unit tests for Gemini quota provider."""

import json
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from superai_mcp.quota._gemini import (
    _extract_oauth_client,
    _gemini_project_id_cache,
    fetch_gemini_quota,
)

_OAUTH_CREDS = {
    "access_token": "ya29.fake-token",
    "refresh_token": "1//fake-refresh",
    "expiry_date": int(time.time() * 1000) + 3600_000,
    "id_token": "fake-id-token",
}

_OAUTH_CREDS_EXPIRED = {
    **_OAUTH_CREDS,
    "expiry_date": int(time.time() * 1000) - 3600_000,
}

_SETTINGS = {"security": {"auth": {"selectedType": "oauth-personal"}}}

_LOAD_CODE_ASSIST_RESP = {
    "cloudaicompanionProject": "gen-lang-client-123",
}

_QUOTA_RESPONSE = {
    "quotaBuckets": [
        {
            "modelId": "gemini-2.5-pro",
            "remainingFraction": 0.75,
            "resetTime": "2026-03-05T18:00:00Z",
        },
        {
            "modelId": "gemini-2.5-pro",
            "remainingFraction": 0.80,
            "resetTime": "2026-03-05T18:00:00Z",
        },
        {
            "modelId": "gemini-2.5-flash",
            "remainingFraction": 0.90,
            "resetTime": "2026-03-06T00:00:00Z",
        },
    ],
}

_REFRESH_RESPONSE = {
    "access_token": "ya29.refreshed-token",
    "expires_in": 3600,
    "token_type": "Bearer",
}


class TestExtractOauthClient:
    def test_extract_from_js(self, tmp_path) -> None:
        js = tmp_path / "oauth2.js"
        js.write_text(
            "const OAUTH_CLIENT_ID = '123.apps.googleusercontent.com';\n"
            "const OAUTH_CLIENT_SECRET = 'GOCSPX-secret';\n"
        )
        cid, csecret = _extract_oauth_client(str(js))
        assert cid == "123.apps.googleusercontent.com"
        assert csecret == "GOCSPX-secret"

    def test_missing_file(self) -> None:
        with pytest.raises(FileNotFoundError):
            _extract_oauth_client("/nonexistent/oauth2.js")


class TestFetchGeminiQuota:
    def setup_method(self) -> None:
        _gemini_project_id_cache.clear()

    async def test_success(self) -> None:
        with patch("superai_mcp.quota._gemini._read_settings", return_value=_SETTINGS):
            with patch(
                "superai_mcp.quota._gemini._read_oauth_creds",
                return_value=dict(_OAUTH_CREDS),
            ):
                with patch(
                    "superai_mcp.quota._gemini.http_post",
                    new_callable=AsyncMock,
                ) as mock_post:
                    mock_post.side_effect = [
                        _LOAD_CODE_ASSIST_RESP,
                        _QUOTA_RESPONSE,
                    ]
                    result = await fetch_gemini_quota()
        assert result.success is True
        assert result.provider == "gemini"
        assert result.sessions["pro"].used_percent == 25.0
        assert result.sessions["pro"].remaining_percent == 75.0
        assert result.sessions["flash"].used_percent == 10.0

    async def test_project_id_cached(self) -> None:
        _gemini_project_id_cache["project_id"] = "cached-proj"
        with patch("superai_mcp.quota._gemini._read_settings", return_value=_SETTINGS):
            with patch(
                "superai_mcp.quota._gemini._read_oauth_creds",
                return_value=dict(_OAUTH_CREDS),
            ):
                with patch(
                    "superai_mcp.quota._gemini.http_post",
                    new_callable=AsyncMock,
                ) as mock_post:
                    mock_post.return_value = _QUOTA_RESPONSE
                    result = await fetch_gemini_quota()
        assert result.success is True
        assert mock_post.call_count == 1

    async def test_token_refresh(self) -> None:
        mock_refresh_resp = MagicMock()
        mock_refresh_resp.read.return_value = json.dumps(_REFRESH_RESPONSE).encode()
        mock_refresh_resp.__enter__ = lambda s: s
        mock_refresh_resp.__exit__ = MagicMock(return_value=False)

        with patch("superai_mcp.quota._gemini._read_settings", return_value=_SETTINGS):
            with patch(
                "superai_mcp.quota._gemini._read_oauth_creds",
                return_value=dict(_OAUTH_CREDS_EXPIRED),
            ):
                with patch(
                    "superai_mcp.quota._gemini._find_oauth2_js",
                    return_value="/fake/oauth2.js",
                ):
                    with patch(
                        "superai_mcp.quota._gemini._extract_oauth_client",
                        return_value=("client-id", "client-secret"),
                    ):
                        with patch(
                            "superai_mcp.quota._gemini.urllib.request.urlopen",
                            return_value=mock_refresh_resp,
                        ):
                            with patch(
                                "superai_mcp.quota._gemini.http_post",
                                new_callable=AsyncMock,
                            ) as mock_post:
                                mock_post.side_effect = [
                                    _LOAD_CODE_ASSIST_RESP,
                                    _QUOTA_RESPONSE,
                                ]
                                with patch(
                                    "superai_mcp.quota._gemini._write_oauth_creds"
                                ):
                                    result = await fetch_gemini_quota()
        assert result.success is True

    async def test_no_settings(self) -> None:
        with patch(
            "superai_mcp.quota._gemini._read_settings",
            side_effect=FileNotFoundError("no file"),
        ):
            result = await fetch_gemini_quota()
        assert result.success is False
        assert "no file" in (result.error or "")

    async def test_api_key_auth_rejected(self) -> None:
        settings = {"security": {"auth": {"selectedType": "api-key"}}}
        with patch("superai_mcp.quota._gemini._read_settings", return_value=settings):
            result = await fetch_gemini_quota()
        assert result.success is False
        assert "oauth" in (result.error or "").lower()
