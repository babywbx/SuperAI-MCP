"""Tests for cache integration in tool handlers."""

import json
from unittest.mock import AsyncMock, patch

from superai_mcp.cache import cache_clear, cache_get, cache_key, cache_put
from superai_mcp.runner import ProcessResult
from superai_mcp.server import codex_tool, gemini_tool, claude_tool, usage_tool


class TestCacheHit:
    def setup_method(self) -> None:
        cache_clear()

    async def test_codex_cache_hit(self) -> None:
        cached_response = json.dumps({"success": True, "content": "cached answer"})
        prompt = "test prompt"
        model = "test-model"
        from superai_mcp.server import _build_context
        effective = await _build_context(
            prompt, cd="/tmp", review_uncommitted=False,
            review_base="", review_commit="", files=None, system_prompt="",
        )
        cache_put(cache_key("codex", "/tmp", effective, model), cached_response)

        with patch("superai_mcp.server.run_cli") as mock_cli:
            with patch("superai_mcp.server.shutil.which", return_value="/usr/bin/codex"):
                with patch("superai_mcp.server.check_model", return_value=""):
                    result = await codex_tool(
                        prompt=prompt, cd="/tmp", model=model,
                        use_cache=True,
                    )

        assert result == cached_response
        mock_cli.assert_not_called()

    async def test_codex_cache_miss_stores(self) -> None:
        codex_output = [
            '{"type":"item.completed","item":{"type":"agent_message","text":"hello"}}',
            '{"type":"turn.completed","usage":{"input_tokens":10,"output_tokens":5}}',
        ]
        mock_result = ProcessResult(returncode=0, stdout_lines=codex_output, stderr="")

        with patch("superai_mcp.server.run_cli", AsyncMock(return_value=mock_result)):
            with patch("superai_mcp.server.shutil.which", return_value="/usr/bin/codex"):
                with patch("superai_mcp.server.check_model", return_value=""):
                    result = await codex_tool(
                        prompt="test", cd="/tmp", model="m",
                        use_cache=True,
                    )

        parsed = json.loads(result)
        assert parsed["success"] is True
        from superai_mcp.server import _build_context
        effective = await _build_context(
            "test", cd="/tmp", review_uncommitted=False,
            review_base="", review_commit="", files=None, system_prompt="",
        )
        assert cache_get(cache_key("codex", "/tmp", effective, "m")) == result

    async def test_cache_disabled_by_default(self) -> None:
        codex_output = [
            '{"type":"item.completed","item":{"type":"agent_message","text":"hello"}}',
        ]
        mock_result = ProcessResult(returncode=0, stdout_lines=codex_output, stderr="")

        with patch("superai_mcp.server.run_cli", AsyncMock(return_value=mock_result)):
            with patch("superai_mcp.server.shutil.which", return_value="/usr/bin/codex"):
                with patch("superai_mcp.server.check_model", return_value=""):
                    await codex_tool(prompt="test", cd="/tmp")

        from superai_mcp.server import _build_context
        effective = await _build_context(
            "test", cd="/tmp", review_uncommitted=False,
            review_base="", review_commit="", files=None, system_prompt="",
        )
        assert cache_get(cache_key("codex", "/tmp", effective, "")) is None

    async def test_failed_response_not_cached(self) -> None:
        mock_result = ProcessResult(returncode=1, stdout_lines=[], stderr="error")

        with patch("superai_mcp.server.run_cli", AsyncMock(return_value=mock_result)):
            with patch("superai_mcp.server.shutil.which", return_value="/usr/bin/codex"):
                with patch("superai_mcp.server.check_model", return_value=""):
                    await codex_tool(prompt="test", cd="/tmp", use_cache=True)

        from superai_mcp.server import _build_context
        effective = await _build_context(
            "test", cd="/tmp", review_uncommitted=False,
            review_base="", review_commit="", files=None, system_prompt="",
        )
        assert cache_get(cache_key("codex", "/tmp", effective, "")) is None

    async def test_session_id_bypasses_cache(self) -> None:
        cached = json.dumps({"success": True, "content": "cached"})
        cache_put(cache_key("codex", "/tmp", "test", ""), cached)

        mock_result = ProcessResult(
            returncode=0,
            stdout_lines=['{"type":"item.completed","item":{"type":"agent_message","text":"fresh"}}'],
            stderr="",
        )

        with patch("superai_mcp.server.run_cli", AsyncMock(return_value=mock_result)):
            with patch("superai_mcp.server.shutil.which", return_value="/usr/bin/codex"):
                with patch("superai_mcp.server.check_model", return_value=""):
                    result = await codex_tool(
                        prompt="test", cd="/tmp",
                        session_id="01234567-abcd-0000-0000-000000000000",
                        use_cache=True,
                    )

        parsed = json.loads(result)
        assert "fresh" in parsed["content"]


class TestUsageToolCache:
    def setup_method(self) -> None:
        cache_clear()

    async def test_cache_stats_in_usage(self) -> None:
        cache_put("k1", "v1")
        result = json.loads(await usage_tool())
        assert result["cache"]["size"] == 1
        assert result["cache"]["maxsize"] == 128

    async def test_clear_cache_via_usage(self) -> None:
        cache_put("k1", "v1")
        await usage_tool(clear_cache=True)
        assert cache_get("k1") is None
