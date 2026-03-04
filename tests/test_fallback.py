"""Tests for rate-limit cascade fallback across all CLIs."""

import json
from unittest.mock import AsyncMock, patch

import pytest

from superai_mcp.runner import ProcessResult
from superai_mcp.server import claude_tool, codex_tool, gemini_tool


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _gemini_lines(content: str, *, success: bool = True) -> list[str]:
    """Build gemini stream-json output lines."""
    lines = ['{"type":"init","session_id":"g-001","model":"gemini-3"}']
    if content:
        lines.append(f'{{"type":"message","role":"assistant","content":"{content}","delta":true}}')
    status = "success" if success else "error"
    lines.append(f'{{"type":"result","status":"{status}","stats":{{"input_tokens":10}}}}')
    return lines


def _gemini_quota_lines() -> list[str]:
    return ["RESOURCE_EXHAUSTED: quota exceeded for model gemini-3-pro"]


def _claude_lines(content: str) -> list[str]:
    """Build Claude stream-json output lines."""
    return [
        '{"type":"system","subtype":"init","session_id":"c-001"}',
        json.dumps({"type": "result", "subtype": "success", "result": content,
                     "usage": {"input_tokens": 10}}),
    ]


def _claude_rate_limit_lines() -> list[str]:
    return ["overloaded_error: model is currently overloaded"]


def _codex_lines(content: str) -> list[str]:
    return [
        '{"type":"thread.started","thread_id":"x-001"}',
        json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": content}}),
        '{"type":"turn.completed","usage":{"input_tokens":10,"output_tokens":5}}',
    ]


def _codex_rate_limit_lines() -> list[str]:
    return [
        '{"type":"thread.started","thread_id":"x-001"}',
        '{"type":"error","message":"429 Too Many Requests"}',
        '{"type":"turn.failed","error":{"message":"rate_limit_exceeded"}}',
    ]


@pytest.fixture()
def _mock_run_cli():
    with patch("superai_mcp.server.run_cli", new_callable=AsyncMock) as mock:
        yield mock


@pytest.fixture()
def _mock_which_gemini():
    with patch("superai_mcp.server.shutil.which", return_value="/usr/bin/gemini"):
        yield


@pytest.fixture()
def _mock_which_claude():
    with patch("superai_mcp.server.shutil.which", return_value="/usr/bin/claude"):
        yield


@pytest.fixture()
def _mock_which_codex():
    with patch("superai_mcp.server.shutil.which", return_value="/usr/bin/codex"):
        yield


# ---------------------------------------------------------------------------
# Gemini fallback (unchanged behavior, migrated from test_gemini_fallback.py)
# ---------------------------------------------------------------------------

class TestGeminiFallback:
    @pytest.mark.usefixtures("_mock_which_gemini")
    async def test_fallback_on_quota_exhausted(self, _mock_run_cli: AsyncMock) -> None:
        """First call hits quota, retry with flash succeeds."""
        _mock_run_cli.side_effect = [
            ProcessResult(returncode=1, stdout_lines=_gemini_quota_lines(), stderr=""),
            ProcessResult(returncode=0, stdout_lines=_gemini_lines("flash response"), stderr=""),
        ]

        raw = await gemini_tool(prompt="hello", cd="/tmp")
        result = json.loads(raw)

        assert result["success"] is True
        assert "[fallback: flash]" in result["content"]
        assert "flash response" in result["content"]
        assert result["model"] is not None
        assert _mock_run_cli.call_count == 2

        # Verify retry used --model flash
        retry_args = _mock_run_cli.call_args_list[1][0][1]
        assert "--model" in retry_args
        assert retry_args[retry_args.index("--model") + 1] == "flash"

    @pytest.mark.usefixtures("_mock_which_gemini")
    async def test_no_fallback_when_already_flash(self, _mock_run_cli: AsyncMock) -> None:
        _mock_run_cli.return_value = ProcessResult(
            returncode=1, stdout_lines=_gemini_quota_lines(), stderr="quota err",
        )

        raw = await gemini_tool(prompt="hello", cd="/tmp", model="flash")
        result = json.loads(raw)

        assert result["success"] is False
        assert _mock_run_cli.call_count == 1

    @pytest.mark.usefixtures("_mock_which_gemini")
    async def test_no_fallback_on_other_error(self, _mock_run_cli: AsyncMock) -> None:
        _mock_run_cli.return_value = ProcessResult(
            returncode=1, stdout_lines=["401 Unauthorized"], stderr="auth error",
        )

        raw = await gemini_tool(prompt="hello", cd="/tmp")
        result = json.loads(raw)

        assert result["success"] is False
        assert _mock_run_cli.call_count == 1

    @pytest.mark.usefixtures("_mock_which_gemini")
    async def test_fallback_retry_also_fails(self, _mock_run_cli: AsyncMock) -> None:
        _mock_run_cli.side_effect = [
            ProcessResult(returncode=1, stdout_lines=_gemini_quota_lines(), stderr=""),
            ProcessResult(returncode=1, stdout_lines=_gemini_quota_lines(), stderr=""),
        ]

        raw = await gemini_tool(prompt="hello", cd="/tmp")
        result = json.loads(raw)

        assert result["success"] is False
        assert "[fallback: flash]" not in result["content"]
        assert _mock_run_cli.call_count == 2

    @pytest.mark.usefixtures("_mock_which_gemini")
    async def test_no_fallback_on_success(self, _mock_run_cli: AsyncMock) -> None:
        _mock_run_cli.return_value = ProcessResult(
            returncode=0, stdout_lines=_gemini_lines("great answer"), stderr="",
        )

        raw = await gemini_tool(prompt="hello", cd="/tmp")
        result = json.loads(raw)

        assert result["success"] is True
        assert "[fallback: flash]" not in result["content"]
        assert _mock_run_cli.call_count == 1


# ---------------------------------------------------------------------------
# Claude fallback: (user model) → sonnet → haiku
# ---------------------------------------------------------------------------

class TestClaudeFallback:
    @pytest.mark.usefixtures("_mock_which_claude")
    async def test_fallback_to_sonnet(self, _mock_run_cli: AsyncMock) -> None:
        """Rate limit on default → probe sonnet OK → real call with sonnet succeeds."""
        _mock_run_cli.side_effect = [
            # Original call: rate limited
            ProcessResult(returncode=1, stdout_lines=_claude_rate_limit_lines(), stderr=""),
            # Probe sonnet: OK
            ProcessResult(returncode=0, stdout_lines=_claude_lines("ok"), stderr=""),
            # Real sonnet call: success
            ProcessResult(returncode=0, stdout_lines=_claude_lines("sonnet response"), stderr=""),
        ]

        raw = await claude_tool(prompt="hello", cd="/tmp")
        result = json.loads(raw)

        assert result["success"] is True
        assert "[fallback: sonnet]" in result["content"]
        assert "sonnet response" in result["content"]
        assert result["model"] == "sonnet"
        assert _mock_run_cli.call_count == 3

        # Verify probe used sonnet
        probe_args = _mock_run_cli.call_args_list[1][0][1]
        assert "--model" in probe_args
        assert probe_args[probe_args.index("--model") + 1] == "sonnet"

    @pytest.mark.usefixtures("_mock_which_claude")
    async def test_fallback_skips_to_haiku(self, _mock_run_cli: AsyncMock) -> None:
        """Rate limit on default → probe sonnet also rate-limited → probe haiku OK → real haiku."""
        _mock_run_cli.side_effect = [
            # Original call: rate limited
            ProcessResult(returncode=1, stdout_lines=_claude_rate_limit_lines(), stderr=""),
            # Probe sonnet: also rate limited
            ProcessResult(returncode=1, stdout_lines=_claude_rate_limit_lines(), stderr=""),
            # Probe haiku: OK
            ProcessResult(returncode=0, stdout_lines=_claude_lines("ok"), stderr=""),
            # Real haiku call: success
            ProcessResult(returncode=0, stdout_lines=_claude_lines("haiku response"), stderr=""),
        ]

        raw = await claude_tool(prompt="hello", cd="/tmp")
        result = json.loads(raw)

        assert result["success"] is True
        assert "[fallback: haiku]" in result["content"]
        assert "haiku response" in result["content"]
        assert result["model"] == "haiku"
        assert _mock_run_cli.call_count == 4

    @pytest.mark.usefixtures("_mock_which_claude")
    async def test_no_fallback_when_already_sonnet(self, _mock_run_cli: AsyncMock) -> None:
        """model=sonnet rate limited → skip sonnet, probe haiku → real haiku."""
        _mock_run_cli.side_effect = [
            # Original (sonnet): rate limited
            ProcessResult(returncode=1, stdout_lines=_claude_rate_limit_lines(), stderr=""),
            # Probe haiku: OK
            ProcessResult(returncode=0, stdout_lines=_claude_lines("ok"), stderr=""),
            # Real haiku call: success
            ProcessResult(returncode=0, stdout_lines=_claude_lines("haiku response"), stderr=""),
        ]

        raw = await claude_tool(prompt="hello", cd="/tmp", model="sonnet")
        result = json.loads(raw)

        assert result["success"] is True
        assert "[fallback: haiku]" in result["content"]
        assert result["model"] == "haiku"
        assert _mock_run_cli.call_count == 3

    @pytest.mark.usefixtures("_mock_which_claude")
    async def test_no_fallback_when_already_haiku(self, _mock_run_cli: AsyncMock) -> None:
        """model=haiku rate limited → no further fallback."""
        _mock_run_cli.return_value = ProcessResult(
            returncode=1, stdout_lines=_claude_rate_limit_lines(), stderr="",
        )

        raw = await claude_tool(prompt="hello", cd="/tmp", model="haiku")
        result = json.loads(raw)

        assert result["success"] is False
        assert _mock_run_cli.call_count == 1

    @pytest.mark.usefixtures("_mock_which_claude")
    async def test_no_fallback_on_other_error(self, _mock_run_cli: AsyncMock) -> None:
        """Non-rate-limit errors don't trigger fallback."""
        _mock_run_cli.return_value = ProcessResult(
            returncode=1,
            stdout_lines=["Error: Not authenticated"],
            stderr="auth error",
        )

        raw = await claude_tool(prompt="hello", cd="/tmp")
        result = json.loads(raw)

        assert result["success"] is False
        assert "[fallback:" not in result["content"]
        assert _mock_run_cli.call_count == 1

    @pytest.mark.usefixtures("_mock_which_claude")
    async def test_no_fallback_on_success(self, _mock_run_cli: AsyncMock) -> None:
        _mock_run_cli.return_value = ProcessResult(
            returncode=0, stdout_lines=_claude_lines("great answer"), stderr="",
        )

        raw = await claude_tool(prompt="hello", cd="/tmp")
        result = json.loads(raw)

        assert result["success"] is True
        assert "[fallback:" not in result["content"]
        assert _mock_run_cli.call_count == 1

    @pytest.mark.usefixtures("_mock_which_claude")
    async def test_probe_non_rate_limit_error_stops(self, _mock_run_cli: AsyncMock) -> None:
        """Probe returns a non-rate-limit error → stop trying."""
        _mock_run_cli.side_effect = [
            # Original: rate limited
            ProcessResult(returncode=1, stdout_lines=_claude_rate_limit_lines(), stderr=""),
            # Probe sonnet: auth error (not rate limit)
            ProcessResult(returncode=1, stdout_lines=["Error: Not authenticated"], stderr=""),
        ]

        raw = await claude_tool(prompt="hello", cd="/tmp")
        result = json.loads(raw)

        assert result["success"] is False
        # Should not try haiku after a non-rate-limit probe error
        assert _mock_run_cli.call_count == 2

    @pytest.mark.usefixtures("_mock_which_claude")
    async def test_fallback_real_call_fails(self, _mock_run_cli: AsyncMock) -> None:
        """Probe succeeds but real call fails → return failure without prefix."""
        _mock_run_cli.side_effect = [
            # Original: rate limited
            ProcessResult(returncode=1, stdout_lines=_claude_rate_limit_lines(), stderr=""),
            # Probe sonnet: OK
            ProcessResult(returncode=0, stdout_lines=_claude_lines("ok"), stderr=""),
            # Real sonnet: fails (non-rate-limit)
            ProcessResult(returncode=1, stdout_lines=["Error: internal error"], stderr=""),
        ]

        raw = await claude_tool(prompt="hello", cd="/tmp")
        result = json.loads(raw)

        assert result["success"] is False
        assert "[fallback:" not in result["content"]
        assert _mock_run_cli.call_count == 3

    @pytest.mark.usefixtures("_mock_which_claude")
    async def test_real_retry_rate_limited_continues_to_next(self, _mock_run_cli: AsyncMock) -> None:
        """Probe OK, real retry also rate-limited → continue to haiku."""
        _mock_run_cli.side_effect = [
            # Original: rate limited
            ProcessResult(returncode=1, stdout_lines=_claude_rate_limit_lines(), stderr=""),
            # Probe sonnet: OK
            ProcessResult(returncode=0, stdout_lines=_claude_lines("ok"), stderr=""),
            # Real sonnet: also rate limited
            ProcessResult(returncode=1, stdout_lines=_claude_rate_limit_lines(), stderr=""),
            # Probe haiku: OK
            ProcessResult(returncode=0, stdout_lines=_claude_lines("ok"), stderr=""),
            # Real haiku: success
            ProcessResult(returncode=0, stdout_lines=_claude_lines("haiku works"), stderr=""),
        ]

        raw = await claude_tool(prompt="hello", cd="/tmp")
        result = json.loads(raw)

        assert result["success"] is True
        assert "[fallback: haiku]" in result["content"]
        assert result["model"] == "haiku"
        assert _mock_run_cli.call_count == 5


# ---------------------------------------------------------------------------
# Codex fallback: degrade reasoning_effort high → medium → low
# ---------------------------------------------------------------------------

class TestCodexFallback:
    @pytest.mark.usefixtures("_mock_which_codex")
    async def test_fallback_effort_high_to_medium(self, _mock_run_cli: AsyncMock) -> None:
        """Rate limit with default effort → probe medium OK → real medium succeeds."""
        _mock_run_cli.side_effect = [
            # Original call: rate limited
            ProcessResult(returncode=1, stdout_lines=_codex_rate_limit_lines(), stderr=""),
            # Probe medium: OK
            ProcessResult(returncode=0, stdout_lines=_codex_lines("ok"), stderr=""),
            # Real medium call: success
            ProcessResult(returncode=0, stdout_lines=_codex_lines("medium answer"), stderr=""),
        ]

        raw = await codex_tool(prompt="hello", cd="/tmp")
        result = json.loads(raw)

        assert result["success"] is True
        assert "[fallback: effort=medium]" in result["content"]
        assert "medium answer" in result["content"]
        # model comes from config file fallback or absent
        assert result.get("model") != ""
        assert _mock_run_cli.call_count == 3

        # Verify retry used medium effort
        retry_args = _mock_run_cli.call_args_list[2][0][1]
        assert "model_reasoning_effort=medium" in " ".join(retry_args)

    @pytest.mark.usefixtures("_mock_which_codex")
    async def test_fallback_effort_skips_to_low(self, _mock_run_cli: AsyncMock) -> None:
        """medium also rate-limited → probe low OK → real low."""
        _mock_run_cli.side_effect = [
            # Original (high): rate limited
            ProcessResult(returncode=1, stdout_lines=_codex_rate_limit_lines(), stderr=""),
            # Probe medium: also rate limited
            ProcessResult(returncode=1, stdout_lines=_codex_rate_limit_lines(), stderr=""),
            # Probe low: OK
            ProcessResult(returncode=0, stdout_lines=_codex_lines("ok"), stderr=""),
            # Real low call: success
            ProcessResult(returncode=0, stdout_lines=_codex_lines("low answer"), stderr=""),
        ]

        raw = await codex_tool(prompt="hello", cd="/tmp")
        result = json.loads(raw)

        assert result["success"] is True
        assert "[fallback: effort=low]" in result["content"]
        assert _mock_run_cli.call_count == 4

    @pytest.mark.usefixtures("_mock_which_codex")
    async def test_fallback_from_explicit_high(self, _mock_run_cli: AsyncMock) -> None:
        """Explicit reasoning_effort='high' rate limited → medium → low."""
        _mock_run_cli.side_effect = [
            ProcessResult(returncode=1, stdout_lines=_codex_rate_limit_lines(), stderr=""),
            # Probe medium: OK
            ProcessResult(returncode=0, stdout_lines=_codex_lines("ok"), stderr=""),
            ProcessResult(returncode=0, stdout_lines=_codex_lines("medium answer"), stderr=""),
        ]

        raw = await codex_tool(prompt="hello", cd="/tmp", reasoning_effort="high")
        result = json.loads(raw)

        assert result["success"] is True
        assert "[fallback: effort=medium]" in result["content"]

    @pytest.mark.usefixtures("_mock_which_codex")
    async def test_no_fallback_at_low(self, _mock_run_cli: AsyncMock) -> None:
        """Already at effort=low → no further degradation."""
        _mock_run_cli.return_value = ProcessResult(
            returncode=1, stdout_lines=_codex_rate_limit_lines(), stderr="",
        )

        raw = await codex_tool(prompt="hello", cd="/tmp", reasoning_effort="low")
        result = json.loads(raw)

        assert result["success"] is False
        assert _mock_run_cli.call_count == 1

    @pytest.mark.usefixtures("_mock_which_codex")
    async def test_no_fallback_on_other_error(self, _mock_run_cli: AsyncMock) -> None:
        _mock_run_cli.return_value = ProcessResult(
            returncode=1,
            stdout_lines=['{"type":"error","message":"401 Unauthorized: Missing bearer auth"}'],
            stderr="auth error",
        )

        raw = await codex_tool(prompt="hello", cd="/tmp")
        result = json.loads(raw)

        assert result["success"] is False
        assert "[fallback:" not in result["content"]
        assert _mock_run_cli.call_count == 1

    @pytest.mark.usefixtures("_mock_which_codex")
    async def test_no_fallback_on_success(self, _mock_run_cli: AsyncMock) -> None:
        _mock_run_cli.return_value = ProcessResult(
            returncode=0, stdout_lines=_codex_lines("great answer"), stderr="",
        )

        raw = await codex_tool(prompt="hello", cd="/tmp")
        result = json.loads(raw)

        assert result["success"] is True
        assert "[fallback:" not in result["content"]
        assert _mock_run_cli.call_count == 1

    @pytest.mark.usefixtures("_mock_which_codex")
    async def test_no_fallback_on_session_resume(self, _mock_run_cli: AsyncMock) -> None:
        """Resume mode should not attempt fallback."""
        _mock_run_cli.return_value = ProcessResult(
            returncode=1, stdout_lines=_codex_rate_limit_lines(), stderr="",
        )

        raw = await codex_tool(
            prompt="hello", cd="/tmp",
            session_id="abcd1234-5678-9abc-def0-123456789abc",
        )
        result = json.loads(raw)

        assert result["success"] is False
        assert _mock_run_cli.call_count == 1

    @pytest.mark.usefixtures("_mock_which_codex")
    async def test_fallback_from_medium(self, _mock_run_cli: AsyncMock) -> None:
        """effort=medium rate limited → only try low."""
        _mock_run_cli.side_effect = [
            ProcessResult(returncode=1, stdout_lines=_codex_rate_limit_lines(), stderr=""),
            # Probe low: OK
            ProcessResult(returncode=0, stdout_lines=_codex_lines("ok"), stderr=""),
            ProcessResult(returncode=0, stdout_lines=_codex_lines("low answer"), stderr=""),
        ]

        raw = await codex_tool(prompt="hello", cd="/tmp", reasoning_effort="medium")
        result = json.loads(raw)

        assert result["success"] is True
        assert "[fallback: effort=low]" in result["content"]
        assert _mock_run_cli.call_count == 3

    @pytest.mark.usefixtures("_mock_which_codex")
    async def test_probe_non_rate_limit_error_stops(self, _mock_run_cli: AsyncMock) -> None:
        """Probe returns non-rate-limit error → stop."""
        _mock_run_cli.side_effect = [
            ProcessResult(returncode=1, stdout_lines=_codex_rate_limit_lines(), stderr=""),
            # Probe medium: auth error
            ProcessResult(
                returncode=1,
                stdout_lines=['{"type":"error","message":"401 Unauthorized"}'],
                stderr="",
            ),
        ]

        raw = await codex_tool(prompt="hello", cd="/tmp")
        result = json.loads(raw)

        assert result["success"] is False
        assert _mock_run_cli.call_count == 2

    @pytest.mark.usefixtures("_mock_which_codex")
    async def test_fallback_preserves_model(self, _mock_run_cli: AsyncMock) -> None:
        """Fallback with explicit model should preserve the model in retry args."""
        _mock_run_cli.side_effect = [
            ProcessResult(returncode=1, stdout_lines=_codex_rate_limit_lines(), stderr=""),
            ProcessResult(returncode=0, stdout_lines=_codex_lines("ok"), stderr=""),
            ProcessResult(returncode=0, stdout_lines=_codex_lines("answer"), stderr=""),
        ]

        raw = await codex_tool(prompt="hello", cd="/tmp", model="gpt-5.3-codex")
        result = json.loads(raw)

        assert result["success"] is True
        # Verify model preserved in retry
        retry_args = _mock_run_cli.call_args_list[2][0][1]
        assert "-m" in retry_args
        assert retry_args[retry_args.index("-m") + 1] == "gpt-5.3-codex"

    @pytest.mark.usefixtures("_mock_which_codex")
    async def test_real_retry_rate_limited_continues(self, _mock_run_cli: AsyncMock) -> None:
        """Probe OK, real retry also rate-limited → continue to low."""
        _mock_run_cli.side_effect = [
            # Original (high): rate limited
            ProcessResult(returncode=1, stdout_lines=_codex_rate_limit_lines(), stderr=""),
            # Probe medium: OK
            ProcessResult(returncode=0, stdout_lines=_codex_lines("ok"), stderr=""),
            # Real medium: also rate limited
            ProcessResult(returncode=1, stdout_lines=_codex_rate_limit_lines(), stderr=""),
            # Probe low: OK
            ProcessResult(returncode=0, stdout_lines=_codex_lines("ok"), stderr=""),
            # Real low: success
            ProcessResult(returncode=0, stdout_lines=_codex_lines("low works"), stderr=""),
        ]

        raw = await codex_tool(prompt="hello", cd="/tmp")
        result = json.loads(raw)

        assert result["success"] is True
        assert "[fallback: effort=low]" in result["content"]
        assert _mock_run_cli.call_count == 5

    @pytest.mark.usefixtures("_mock_which_codex")
    async def test_fallback_from_xhigh_starts_at_high(self, _mock_run_cli: AsyncMock) -> None:
        """effort=xhigh (not in chain) → try high first, then medium, low."""
        _mock_run_cli.side_effect = [
            # Original (xhigh): rate limited
            ProcessResult(returncode=1, stdout_lines=_codex_rate_limit_lines(), stderr=""),
            # Probe high: OK
            ProcessResult(returncode=0, stdout_lines=_codex_lines("ok"), stderr=""),
            # Real high: success
            ProcessResult(returncode=0, stdout_lines=_codex_lines("high answer"), stderr=""),
        ]

        raw = await codex_tool(prompt="hello", cd="/tmp", reasoning_effort="xhigh")
        result = json.loads(raw)

        assert result["success"] is True
        assert "[fallback: effort=high]" in result["content"]
        assert _mock_run_cli.call_count == 3
