"""Integration tests — call real Codex/Gemini CLI.

Run with: uv run pytest tests/test_integration.py -v -s
These tests require codex and gemini CLI installed and configured.
Skip in CI with: pytest -m "not integration"
"""

import json
import shutil

import pytest

from superai_mcp.server import codex_tool, gemini_tool

pytestmark = pytest.mark.integration

SKIP_CODEX = not shutil.which("codex")
SKIP_GEMINI = not shutil.which("gemini")


# -- Codex tests --


@pytest.mark.skipif(SKIP_CODEX, reason="codex CLI not installed")
class TestCodexIntegration:
    async def test_basic_prompt(self) -> None:
        """Codex can answer a simple prompt."""
        raw = await codex_tool(prompt="Reply with exactly: PING", cd="/tmp")
        result = json.loads(raw)
        assert result["success"] is True
        assert result["session_id"]  # non-empty
        assert "PING" in result["content"]

    async def test_session_id_returned(self) -> None:
        """Codex returns a session_id for future resume."""
        raw = await codex_tool(prompt="Say hello", cd="/tmp")
        result = json.loads(raw)
        assert result["success"] is True
        # session_id should be a UUID-like string
        assert result["session_id"]
        assert len(result["session_id"]) > 10

    async def test_return_all_messages(self) -> None:
        """return_all_messages returns the event stream."""
        raw = await codex_tool(prompt="Say OK", cd="/tmp", return_all_messages=True)
        result = json.loads(raw)
        assert result["success"] is True
        assert result["all_messages"] is not None
        assert len(result["all_messages"]) > 0
        # Should contain thread.started event
        types = [e.get("type") for e in result["all_messages"]]
        assert "thread.started" in types

    async def test_usage_stats(self) -> None:
        """Usage stats are captured from turn.completed."""
        raw = await codex_tool(prompt="Say hi", cd="/tmp")
        result = json.loads(raw)
        assert result["success"] is True
        assert result["usage"] is not None
        assert "input_tokens" in result["usage"]


# -- Gemini tests --


@pytest.mark.skipif(SKIP_GEMINI, reason="gemini CLI not installed")
class TestGeminiIntegration:
    async def test_basic_prompt(self) -> None:
        """Gemini can answer a simple prompt."""
        raw = await gemini_tool(prompt="Reply with exactly: PONG", cd="/tmp")
        result = json.loads(raw)
        assert result["success"] is True
        assert result["session_id"]
        assert "PONG" in result["content"]

    async def test_session_resume(self) -> None:
        """Gemini session can be resumed."""
        raw1 = await gemini_tool(prompt="Remember the word CHERRY", cd="/tmp")
        r1 = json.loads(raw1)
        assert r1["success"] is True
        sid = r1["session_id"]
        assert sid

        raw2 = await gemini_tool(prompt="What word did I ask you to remember?", cd="/tmp", session_id=sid)
        r2 = json.loads(raw2)
        assert r2["success"] is True
        assert "CHERRY" in r2["content"].upper()

    async def test_return_all_messages(self) -> None:
        """return_all_messages returns event stream."""
        raw = await gemini_tool(prompt="Say OK", cd="/tmp", return_all_messages=True)
        result = json.loads(raw)
        assert result["success"] is True
        assert result["all_messages"] is not None
        assert len(result["all_messages"]) > 0
        types = [e.get("type") for e in result["all_messages"]]
        assert "init" in types

    async def test_usage_stats(self) -> None:
        """Usage stats captured from result event."""
        raw = await gemini_tool(prompt="Say hi", cd="/tmp")
        result = json.loads(raw)
        assert result["success"] is True
        assert result["usage"] is not None
        assert "input_tokens" in result["usage"]

    async def test_model_selection(self) -> None:
        """Gemini can use a specific model alias."""
        raw = await gemini_tool(prompt="Say OK", cd="/tmp", model="flash")
        result = json.loads(raw)
        assert result["success"] is True


# -- Cross-tool parallel test --


@pytest.mark.skipif(SKIP_CODEX or SKIP_GEMINI, reason="need both CLIs")
class TestParallel:
    async def test_parallel_calls(self) -> None:
        """Both tools can run in parallel."""
        import asyncio

        codex_task = asyncio.create_task(
            codex_tool(prompt="Reply ALPHA", cd="/tmp")
        )
        gemini_task = asyncio.create_task(
            gemini_tool(prompt="Reply BETA", cd="/tmp")
        )

        codex_raw, gemini_raw = await asyncio.gather(codex_task, gemini_task)

        cr = json.loads(codex_raw)
        gr = json.loads(gemini_raw)
        assert cr["success"] is True
        assert gr["success"] is True
        # Both should return non-empty content (exact wording varies)
        assert len(cr["content"]) > 0
        assert len(gr["content"]) > 0
