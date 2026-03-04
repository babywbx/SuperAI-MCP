"""Tests for multi-model collaboration tools (chain, vote, debate)."""

import json
from unittest.mock import AsyncMock, patch

from superai_mcp.server import chain_tool


def _ok(content: str, usage: dict | None = None) -> str:
    """Build a successful JSON response like the real tools return."""
    d: dict = {"success": True, "content": content}
    if usage:
        d["usage"] = usage
    return json.dumps(d)


def _fail(content: str) -> str:
    return json.dumps({"success": False, "content": content})


class TestChainTool:
    async def test_empty_steps(self) -> None:
        raw = await chain_tool(steps=[], cd="/tmp")
        result = json.loads(raw)
        assert not result["success"]
        assert "steps" in result["content"].lower()

    async def test_single_step(self) -> None:
        with patch("superai_mcp.server._TARGET_FNS", {
            "codex": AsyncMock(return_value=_ok("hello world")),
        }):
            raw = await chain_tool(
                steps=[{"target": "codex", "prompt": "say hello"}],
                cd="/tmp",
            )
        result = json.loads(raw)
        assert result["success"]
        assert result["final_content"] == "hello world"
        assert len(result["steps"]) == 1

    async def test_two_steps_injects_previous(self) -> None:
        calls: list[dict] = []

        async def fake_codex(**kwargs) -> str:
            calls.append(kwargs)
            return _ok("code from codex")

        async def fake_claude(**kwargs) -> str:
            calls.append(kwargs)
            return _ok("review from claude")

        with patch("superai_mcp.server._TARGET_FNS", {
            "codex": fake_codex,
            "claude": fake_claude,
        }):
            raw = await chain_tool(
                steps=[
                    {"target": "codex", "prompt": "write code"},
                    {"target": "claude", "prompt": "review this"},
                ],
                cd="/tmp",
            )
        result = json.loads(raw)
        assert result["success"]
        assert result["final_content"] == "review from claude"
        # Second call should have previous output injected
        assert "<previous_output>" in calls[1]["prompt"]
        assert "code from codex" in calls[1]["prompt"]

    async def test_fail_fast(self) -> None:
        async def fail_codex(**kwargs) -> str:
            return _fail("codex error")

        claude_mock = AsyncMock(return_value=_ok("should not run"))

        with patch("superai_mcp.server._TARGET_FNS", {
            "codex": fail_codex,
            "claude": claude_mock,
        }):
            raw = await chain_tool(
                steps=[
                    {"target": "codex", "prompt": "do something"},
                    {"target": "claude", "prompt": "review"},
                ],
                cd="/tmp",
            )
        result = json.loads(raw)
        assert not result["success"]
        assert len(result["steps"]) == 1
        claude_mock.assert_not_called()

    async def test_invalid_target(self) -> None:
        raw = await chain_tool(
            steps=[{"target": "invalid", "prompt": "hello"}],
            cd="/tmp",
        )
        result = json.loads(raw)
        assert not result["success"]
        assert "invalid" in result["content"]

    async def test_step_model_override(self) -> None:
        calls: list[dict] = []

        async def fake_codex(**kwargs) -> str:
            calls.append(kwargs)
            return _ok("done")

        with patch("superai_mcp.server._TARGET_FNS", {"codex": fake_codex}):
            await chain_tool(
                steps=[{"target": "codex", "prompt": "hi", "model": "gpt-5"}],
                cd="/tmp",
            )
        assert calls[0]["model"] == "gpt-5"

    async def test_timeout_budget(self) -> None:
        calls: list[dict] = []

        async def fake_codex(**kwargs) -> str:
            calls.append(kwargs)
            return _ok("done")

        with patch("superai_mcp.server._TARGET_FNS", {"codex": fake_codex}):
            await chain_tool(
                steps=[
                    {"target": "codex", "prompt": "step1"},
                    {"target": "codex", "prompt": "step2"},
                ],
                cd="/tmp",
                timeout=60.0,
            )
        # Each step should get a fraction of total timeout
        for c in calls:
            assert c["timeout"] <= 60.0

    async def test_system_prompt_first_step_only(self) -> None:
        calls: list[dict] = []

        async def fake_codex(**kwargs) -> str:
            calls.append(kwargs)
            return _ok("done")

        with patch("superai_mcp.server._TARGET_FNS", {"codex": fake_codex}):
            await chain_tool(
                steps=[
                    {"target": "codex", "prompt": "step1"},
                    {"target": "codex", "prompt": "step2"},
                ],
                cd="/tmp",
                system_prompt="be concise",
            )
        # system_prompt passed to first step, empty for subsequent
        assert calls[0]["system_prompt"] == "be concise"
        assert calls[1]["system_prompt"] == ""
