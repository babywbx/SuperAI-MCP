"""Unit tests for quota public API."""

from unittest.mock import AsyncMock, patch

from superai_mcp.quota import fetch_quota, fetch_all_quotas
from superai_mcp.quota._models import QuotaResult


_OK = QuotaResult(provider="claude", success=True)
_FAIL = QuotaResult(provider="codex", success=False, error="boom")


class TestFetchQuota:
    async def test_claude(self) -> None:
        with patch("superai_mcp.quota.fetch_claude_quota", new_callable=AsyncMock, return_value=_OK):
            result = await fetch_quota("claude")
        assert result.success is True

    async def test_unknown_provider(self) -> None:
        result = await fetch_quota("unknown")
        assert result.success is False
        assert "unknown provider" in (result.error or "").lower()


class TestFetchAllQuotas:
    async def test_mixed_results(self) -> None:
        with patch("superai_mcp.quota.fetch_claude_quota", new_callable=AsyncMock,
                    return_value=QuotaResult(provider="claude", success=True)):
            with patch("superai_mcp.quota.fetch_codex_quota", new_callable=AsyncMock,
                       return_value=QuotaResult(provider="codex", success=False, error="fail")):
                with patch("superai_mcp.quota.fetch_gemini_quota", new_callable=AsyncMock,
                           return_value=QuotaResult(provider="gemini", success=True)):
                    results = await fetch_all_quotas()
        assert len(results) == 3
        assert results["claude"].success is True
        assert results["codex"].success is False
        assert results["gemini"].success is True
