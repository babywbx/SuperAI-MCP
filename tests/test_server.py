"""Tests for server helper functions."""

import json

from superai_mcp.server import (
    _MAX_SNIPPET,
    _STDIN_THRESHOLD,
    _build_context,
    _codex_prompt_args,
    _codex_resume_prompt_args,
    _claude_prompt_args,
    _gemini_prompt_args,
    _summarize_line,
    _usage,
    _track_usage,
    _reset_usage,
    usage_tool,
)


class TestSummarizeLine:
    def test_empty_string(self) -> None:
        assert _summarize_line("") == ""

    # -- Codex events --

    def test_codex_turn_started(self) -> None:
        line = json.dumps({"type": "turn.started"})
        assert _summarize_line(line) == "turn.started"

    def test_codex_turn_completed(self) -> None:
        line = json.dumps({"type": "turn.completed"})
        assert _summarize_line(line) == "turn.completed"

    def test_codex_turn_failed_with_message(self) -> None:
        line = json.dumps({
            "type": "turn.failed",
            "error": {"message": "rate limit exceeded"},
        })
        assert _summarize_line(line) == "turn.failed: rate limit exceeded"

    def test_codex_turn_failed_no_message(self) -> None:
        line = json.dumps({"type": "turn.failed"})
        assert _summarize_line(line) == "turn.failed"

    def test_codex_error(self) -> None:
        line = json.dumps({"type": "error", "message": "something broke"})
        assert _summarize_line(line) == "error: something broke"

    def test_codex_item_completed_reasoning(self) -> None:
        line = json.dumps({
            "type": "item.completed",
            "item": {"type": "reasoning", "text": "Let me analyze the code structure"},
        })
        assert _summarize_line(line) == "reasoning: Let me analyze the code structure"

    def test_codex_item_completed_agent_message(self) -> None:
        line = json.dumps({
            "type": "item.completed",
            "item": {"type": "agent_message", "text": "Here's the fix"},
        })
        assert _summarize_line(line) == "message: Here's the fix"

    def test_codex_item_completed_message(self) -> None:
        line = json.dumps({
            "type": "item.completed",
            "item": {"type": "message", "text": "Done"},
        })
        assert _summarize_line(line) == "message: Done"

    def test_codex_item_completed_error(self) -> None:
        line = json.dumps({
            "type": "item.completed",
            "item": {"type": "error", "message": "something went wrong"},
        })
        assert _summarize_line(line) == "error: something went wrong"

    def test_codex_item_completed_error_no_message(self) -> None:
        line = json.dumps({
            "type": "item.completed",
            "item": {"type": "error"},
        })
        assert _summarize_line(line) == "error"

    def test_codex_thread_started(self) -> None:
        line = json.dumps({"type": "thread.started", "thread_id": "abc-123"})
        assert _summarize_line(line) == "thread.started"

    def test_codex_item_completed_no_text(self) -> None:
        line = json.dumps({
            "type": "item.completed",
            "item": {"type": "reasoning"},
        })
        assert _summarize_line(line) == "item.completed"

    # -- Gemini events --

    def test_gemini_assistant_message(self) -> None:
        line = json.dumps({"role": "assistant", "content": "The function should..."})
        assert _summarize_line(line) == "assistant: The function should..."

    def test_gemini_init(self) -> None:
        line = json.dumps({"type": "init", "model": "gemini-3.1-pro"})
        assert _summarize_line(line) == "init: gemini-3.1-pro"

    def test_gemini_init_no_model(self) -> None:
        line = json.dumps({"type": "init"})
        assert _summarize_line(line) == "init"

    def test_gemini_result(self) -> None:
        line = json.dumps({"type": "result", "status": "success"})
        assert _summarize_line(line) == "result: success"

    def test_gemini_result_no_status(self) -> None:
        line = json.dumps({"type": "result"})
        assert _summarize_line(line) == "result"

    # -- Non-JSON / fallback --

    def test_non_json_line(self) -> None:
        assert _summarize_line("some plain text") == "some plain text"

    def test_non_dict_json(self) -> None:
        line = json.dumps([1, 2, 3])
        assert _summarize_line(line) == line[:_MAX_SNIPPET]

    # -- Truncation --

    def test_truncation_at_max_snippet(self) -> None:
        long_text = "x" * 200
        result = _summarize_line(long_text)
        assert len(result) == _MAX_SNIPPET

    def test_truncation_codex_reasoning(self) -> None:
        long_reason = "a" * 200
        line = json.dumps({
            "type": "item.completed",
            "item": {"type": "reasoning", "text": long_reason},
        })
        result = _summarize_line(line)
        assert len(result) == _MAX_SNIPPET
        assert result.startswith("reasoning: ")

    def test_truncation_gemini_assistant(self) -> None:
        long_content = "b" * 200
        line = json.dumps({"role": "assistant", "content": long_content})
        result = _summarize_line(line)
        assert len(result) == _MAX_SNIPPET
        assert result.startswith("assistant: ")


class TestPromptArgHelpers:
    def test_gemini_small_prompt(self) -> None:
        args, data = _gemini_prompt_args("hello")
        assert args == ["-p", "hello"]
        assert data is None

    def test_gemini_large_prompt(self) -> None:
        big = "x" * (_STDIN_THRESHOLD + 1)
        args, data = _gemini_prompt_args(big)
        assert args == ["-p", ""]
        assert data == big.encode("utf-8")

    def test_codex_small_prompt(self) -> None:
        args, data = _codex_prompt_args("hello")
        assert args == ["--", "hello"]
        assert data is None

    def test_codex_large_prompt(self) -> None:
        big = "x" * (_STDIN_THRESHOLD + 1)
        args, data = _codex_prompt_args(big)
        assert args == ["--", "-"]
        assert data == big.encode("utf-8")

    def test_codex_resume_small_prompt(self) -> None:
        args, data = _codex_resume_prompt_args("sid-123", "hello")
        assert args == ["--", "sid-123", "hello"]
        assert data is None

    def test_codex_resume_large_prompt(self) -> None:
        big = "x" * (_STDIN_THRESHOLD + 1)
        args, data = _codex_resume_prompt_args("sid-123", big)
        assert args == ["--", "sid-123", "-"]
        assert data == big.encode("utf-8")

    def test_claude_small_prompt(self) -> None:
        args, data = _claude_prompt_args("hello")
        assert args == ["-p", "hello"]
        assert data is None

    def test_claude_large_prompt(self) -> None:
        big = "x" * (_STDIN_THRESHOLD + 1)
        args, data = _claude_prompt_args(big)
        assert args == ["-p"]
        assert data == big.encode("utf-8")

    def test_threshold_boundary_exact(self) -> None:
        """Exactly at threshold stays as arg."""
        prompt = "x" * _STDIN_THRESHOLD
        _, data = _gemini_prompt_args(prompt)
        assert data is None

    def test_threshold_boundary_one_over(self) -> None:
        """One byte over threshold triggers stdin."""
        prompt = "x" * (_STDIN_THRESHOLD + 1)
        _, data = _gemini_prompt_args(prompt)
        assert data is not None


class TestBuildContextSystemPrompt:
    async def test_system_prompt_prepended(self) -> None:
        result = await _build_context(
            "do stuff", cd="/tmp",
            review_uncommitted=False, review_base="", files=None,
            system_prompt="You are a code reviewer",
        )
        assert result.startswith("<system>You are a code reviewer</system>")
        assert result.endswith("do stuff")

    async def test_empty_system_prompt(self) -> None:
        result = await _build_context(
            "do stuff", cd="/tmp",
            review_uncommitted=False, review_base="", files=None,
            system_prompt="",
        )
        assert result == "do stuff"
        assert "<system>" not in result


class TestUsageTracking:
    def setup_method(self) -> None:
        _reset_usage()

    def test_track_usage_basic(self) -> None:
        _track_usage("codex", {"input_tokens": 100, "output_tokens": 50})
        assert _usage["codex"]["calls"] == 1
        assert _usage["codex"]["input_tokens"] == 100
        assert _usage["codex"]["output_tokens"] == 50

    def test_track_usage_accumulates(self) -> None:
        _track_usage("codex", {"input_tokens": 100, "output_tokens": 50})
        _track_usage("codex", {"input_tokens": 200, "output_tokens": 100})
        assert _usage["codex"]["calls"] == 2
        assert _usage["codex"]["input_tokens"] == 300
        assert _usage["codex"]["output_tokens"] == 150

    def test_track_usage_none(self) -> None:
        _track_usage("codex", None)
        assert _usage["codex"]["calls"] == 1
        assert _usage["codex"]["input_tokens"] == 0

    def test_track_usage_missing_keys(self) -> None:
        _track_usage("gemini", {"some_other_stat": 42})
        assert _usage["gemini"]["calls"] == 1
        assert _usage["gemini"]["input_tokens"] == 0

    def test_reset_usage(self) -> None:
        _track_usage("codex", {"input_tokens": 100, "output_tokens": 50})
        _reset_usage()
        assert _usage["codex"]["calls"] == 0
        assert _usage["codex"]["input_tokens"] == 0

    def test_track_unknown_cli(self) -> None:
        _track_usage("unknown_cli", {"input_tokens": 100})
        # Should not crash, just silently ignore
        assert "unknown_cli" not in _usage


class TestUsageTool:
    def setup_method(self) -> None:
        _reset_usage()

    async def test_empty_usage(self) -> None:
        raw = await usage_tool()
        result = json.loads(raw)
        assert result["success"] is True
        assert result["codex"]["calls"] == 0
        assert result["total"]["calls"] == 0

    async def test_usage_after_tracking(self) -> None:
        _track_usage("codex", {"input_tokens": 100, "output_tokens": 50})
        _track_usage("gemini", {"input_tokens": 200, "output_tokens": 80})
        raw = await usage_tool()
        result = json.loads(raw)
        assert result["codex"]["calls"] == 1
        assert result["codex"]["input_tokens"] == 100
        assert result["gemini"]["calls"] == 1
        assert result["total"]["calls"] == 2
        assert result["total"]["input_tokens"] == 300
        assert result["total"]["output_tokens"] == 130

    async def test_usage_reset(self) -> None:
        _track_usage("codex", {"input_tokens": 100, "output_tokens": 50})
        raw = await usage_tool(reset=True)
        result = json.loads(raw)
        assert result["codex"]["calls"] == 1
        assert _usage["codex"]["calls"] == 0
