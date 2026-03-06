"""Unit tests for quota HTTP helper."""

import json
from unittest.mock import MagicMock, patch

import pytest

from superai_mcp.quota._http import http_get, http_post, QuotaHTTPError


class TestHttpGet:
    async def test_success(self) -> None:
        body = json.dumps({"ok": True}).encode()
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = body
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch(
            "superai_mcp.quota._http.urllib.request.urlopen", return_value=mock_resp
        ):
            result = await http_get("https://example.com/api", {})
        assert result == {"ok": True}

    async def test_non_200_raises(self) -> None:
        from urllib.error import HTTPError
        import io

        err = HTTPError("https://x", 401, "Unauthorized", {}, io.BytesIO(b"bad"))
        with patch("superai_mcp.quota._http.urllib.request.urlopen", side_effect=err):
            with pytest.raises(QuotaHTTPError, match="401"):
                await http_get("https://x", {})

    async def test_html_response_raises(self) -> None:
        body = b"<!DOCTYPE html><html><body>Login</body></html>"
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = body
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch(
            "superai_mcp.quota._http.urllib.request.urlopen", return_value=mock_resp
        ):
            with pytest.raises(QuotaHTTPError, match="HTML"):
                await http_get("https://x", {})


class TestHttpPost:
    async def test_success(self) -> None:
        body = json.dumps({"result": "ok"}).encode()
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = body
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch(
            "superai_mcp.quota._http.urllib.request.urlopen", return_value=mock_resp
        ) as mock_open:
            result = await http_post("https://example.com/api", {}, {"key": "val"})
            assert result == {"result": "ok"}
            req = mock_open.call_args[0][0]
            assert req.data == json.dumps({"key": "val"}).encode()
