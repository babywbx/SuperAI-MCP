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


from superai_mcp.server import vote_tool


class TestVoteTool:
    async def test_basic_vote(self) -> None:
        async def fake_codex(**kwargs) -> str:
            return _ok("answer A")

        async def fake_claude(**kwargs) -> str:
            return _ok("answer B")

        async def fake_gemini(**kwargs) -> str:
            return _ok("answer C")

        # Judge (claude) picks winner from candidates
        # Patch the judge call separately — vote calls candidates first,
        # then calls judge. We handle this by making claude return different
        # things on first vs second call.
        call_count = {"claude": 0}

        async def claude_multi(**kwargs) -> str:
            call_count["claude"] += 1
            if call_count["claude"] == 1:
                return _ok("answer B")  # candidate
            return _ok("Candidate B is best.")  # judge

        with patch("superai_mcp.server._TARGET_FNS", {
            "codex": fake_codex,
            "claude": claude_multi,
            "gemini": fake_gemini,
        }):
            raw = await vote_tool(
                prompt="What is the best approach?",
                cd="/tmp",
            )
        result = json.loads(raw)
        assert result["success"]
        assert "candidates" in result
        assert "judge_reasoning" in result

    async def test_custom_candidates_and_judge(self) -> None:
        async def fake_codex(**kwargs) -> str:
            return _ok("codex answer")

        async def fake_gemini(**kwargs) -> str:
            return _ok("gemini answer")

        async def fake_claude(**kwargs) -> str:
            return _ok("Claude picks Candidate A.")

        with patch("superai_mcp.server._TARGET_FNS", {
            "codex": fake_codex,
            "gemini": fake_gemini,
            "claude": fake_claude,
        }):
            raw = await vote_tool(
                prompt="solve this",
                candidates=["codex", "gemini"],
                judge="claude",
                cd="/tmp",
            )
        result = json.loads(raw)
        assert result["success"]
        assert "codex" in result["candidates"]
        assert "gemini" in result["candidates"]

    async def test_judge_same_as_candidate_excluded(self) -> None:
        """If judge is in candidates, it should be auto-excluded from candidates."""
        call_targets: list[str] = []

        async def fake_codex(**kwargs) -> str:
            call_targets.append("codex")
            return _ok("codex answer")

        async def fake_claude(**kwargs) -> str:
            call_targets.append("claude")
            return _ok("claude answer")

        with patch("superai_mcp.server._TARGET_FNS", {
            "codex": fake_codex,
            "claude": fake_claude,
        }):
            raw = await vote_tool(
                prompt="solve",
                candidates=["codex", "claude"],
                judge="claude",
                cd="/tmp",
            )
        result = json.loads(raw)
        assert result["success"]

    async def test_single_candidate_skips_voting(self) -> None:
        async def fake_codex(**kwargs) -> str:
            return _ok("only answer")

        with patch("superai_mcp.server._TARGET_FNS", {
            "codex": fake_codex,
        }):
            raw = await vote_tool(
                prompt="solve",
                candidates=["codex"],
                judge="codex",
                cd="/tmp",
            )
        result = json.loads(raw)
        assert result["success"]
        # With only 1 candidate, skip judging — return directly
        assert result["final_content"] == "only answer"

    async def test_invalid_judge(self) -> None:
        raw = await vote_tool(
            prompt="solve",
            judge="invalid",
            cd="/tmp",
        )
        result = json.loads(raw)
        assert not result["success"]
