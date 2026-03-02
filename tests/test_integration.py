"""Integration tests — call real Codex/Gemini CLI.

Run with: uv run pytest tests/test_integration.py -v -s
These tests require codex and gemini CLI installed and configured.
Skip in CI with: pytest -m "not integration"
"""

import json
import shutil

import pytest

from superai_mcp.server import broadcast_tool, claude_tool, codex_tool, gemini_tool

pytestmark = pytest.mark.integration

SKIP_CODEX = not shutil.which("codex")
SKIP_GEMINI = not shutil.which("gemini")
SKIP_CLAUDE = not shutil.which("claude")


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


    async def test_auto_split_session_id_exclusive(self) -> None:
        """auto_split and session_id are mutually exclusive."""
        raw = await codex_tool(
            prompt="test", cd="/tmp", auto_split=True, session_id="abc12345-1234-1234-1234-123456789abc",
        )
        result = json.loads(raw)
        assert result["success"] is False
        assert "mutually exclusive" in result["content"]


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


    async def test_auto_split_session_id_exclusive(self) -> None:
        """auto_split and session_id are mutually exclusive."""
        raw = await gemini_tool(
            prompt="test", cd="/tmp", auto_split=True, session_id="abc12345-1234-1234-1234-123456789abc",
        )
        result = json.loads(raw)
        assert result["success"] is False
        assert "mutually exclusive" in result["content"]


# -- Claude tests --


@pytest.mark.skipif(SKIP_CLAUDE, reason="claude CLI not installed")
class TestClaudeIntegration:
    async def test_basic_prompt(self) -> None:
        """Claude can answer a simple prompt."""
        raw = await claude_tool(prompt="Reply with exactly: ECHO", cd="/tmp")
        result = json.loads(raw)
        assert result["success"] is True
        assert result["session_id"]
        assert "ECHO" in result["content"]

    async def test_session_id_returned(self) -> None:
        """Claude returns a session_id for future resume."""
        raw = await claude_tool(prompt="Say hello", cd="/tmp")
        result = json.loads(raw)
        assert result["success"] is True
        assert result["session_id"]
        assert len(result["session_id"]) > 10

    async def test_return_all_messages(self) -> None:
        """return_all_messages returns the JSON object."""
        raw = await claude_tool(prompt="Say OK", cd="/tmp", return_all_messages=True)
        result = json.loads(raw)
        assert result["success"] is True
        assert result["all_messages"] is not None
        assert len(result["all_messages"]) > 0

    async def test_usage_stats(self) -> None:
        """Usage stats are captured from JSON output."""
        raw = await claude_tool(prompt="Say hi", cd="/tmp")
        result = json.loads(raw)
        assert result["success"] is True
        assert result["usage"] is not None
        assert "input_tokens" in result["usage"]

    async def test_model_selection(self) -> None:
        """Claude can use a specific model."""
        raw = await claude_tool(prompt="Say OK", cd="/tmp", model="sonnet")
        result = json.loads(raw)
        assert result["success"] is True


    async def test_auto_split_session_id_exclusive(self) -> None:
        """auto_split and session_id are mutually exclusive."""
        raw = await claude_tool(
            prompt="test", cd="/tmp", auto_split=True, session_id="abc12345-1234-1234-1234-123456789abc",
        )
        result = json.loads(raw)
        assert result["success"] is False
        assert "mutually exclusive" in result["content"]


# -- Broadcast tests --


class TestBroadcastIntegration:
    async def test_broadcast_all(self) -> None:
        """Broadcast to all targets returns three results."""
        raw = await broadcast_tool(prompt="Reply with exactly: HELLO", cd="/tmp")
        result = json.loads(raw)
        assert result["success"] is True
        assert "results" in result
        # Each installed CLI should have a result (success or not)
        for target in ("codex", "gemini", "claude"):
            if target in result["results"]:
                assert "success" in result["results"][target]

    async def test_broadcast_subset(self) -> None:
        """Broadcast to a single target returns only that result."""
        # Pick whichever CLI is available
        target = None
        for name, skip in [("codex", SKIP_CODEX), ("gemini", SKIP_GEMINI), ("claude", SKIP_CLAUDE)]:
            if not skip:
                target = name
                break
        if target is None:
            pytest.skip("no CLI installed")

        raw = await broadcast_tool(prompt="Say OK", cd="/tmp", targets=[target])
        result = json.loads(raw)
        assert result["success"] is True
        assert set(result["results"].keys()) == {target}
        assert result["results"][target]["success"] is True

    async def test_broadcast_invalid_target(self) -> None:
        """Invalid target returns error without calling any CLI."""
        raw = await broadcast_tool(prompt="hello", cd="/tmp", targets=["nonexistent"])
        result = json.loads(raw)
        assert result["success"] is False
        assert "invalid target" in result["content"]


# -- Cross-tool parallel test --


@pytest.mark.skipif(SKIP_CODEX or SKIP_GEMINI or SKIP_CLAUDE, reason="need all CLIs")
class TestParallel:
    async def test_parallel_calls(self) -> None:
        """All three tools can run in parallel."""
        import asyncio

        codex_task = asyncio.create_task(
            codex_tool(prompt="Reply ALPHA", cd="/tmp")
        )
        gemini_task = asyncio.create_task(
            gemini_tool(prompt="Reply BETA", cd="/tmp")
        )
        claude_task = asyncio.create_task(
            claude_tool(prompt="Reply GAMMA", cd="/tmp")
        )

        codex_raw, gemini_raw, claude_raw = await asyncio.gather(
            codex_task, gemini_task, claude_task,
        )

        cr = json.loads(codex_raw)
        gr = json.loads(gemini_raw)
        clr = json.loads(claude_raw)
        assert cr["success"] is True
        assert gr["success"] is True
        assert clr["success"] is True
        assert len(cr["content"]) > 0
        assert len(gr["content"]) > 0
        assert len(clr["content"]) > 0
