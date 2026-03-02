"""Unit tests for the auto-split orchestration module."""

import asyncio

import pytest

from superai_mcp.models import CLIResult
from superai_mcp.splitter import (
    extract_subtasks,
    format_aggregated_content,
    merge_usage,
    run_auto_split,
    SubtaskResult,
)


# -- extract_subtasks --


class TestExtractSubtasks:
    def test_fenced_json(self) -> None:
        content = 'Here are subtasks:\n```json\n[{"id":1,"title":"A","prompt":"do A"}]\n```'
        result = extract_subtasks(content)
        assert len(result) == 1
        assert result[0].id == 1
        assert result[0].title == "A"
        assert result[0].prompt == "do A"

    def test_fenced_json_multiple(self) -> None:
        content = '```json\n[{"id":1,"title":"A","prompt":"a"},{"id":2,"title":"B","prompt":"b"}]\n```'
        result = extract_subtasks(content)
        assert len(result) == 2
        assert result[1].id == 2

    def test_raw_json_fallback(self) -> None:
        content = 'Some text [{"id":1,"title":"X","prompt":"x"}] more text'
        result = extract_subtasks(content)
        assert len(result) == 1
        assert result[0].title == "X"

    def test_no_json_raises(self) -> None:
        with pytest.raises(ValueError, match="No JSON array found"):
            extract_subtasks("no json here")

    def test_empty_array_raises(self) -> None:
        with pytest.raises(ValueError, match="not a non-empty JSON array"):
            extract_subtasks("```json\n[]\n```")

    def test_truncate_to_max(self) -> None:
        items = [{"id": i, "title": f"T{i}", "prompt": f"p{i}"} for i in range(1, 10)]
        import json
        content = f"```json\n{json.dumps(items)}\n```"
        result = extract_subtasks(content)
        assert len(result) == 5  # _MAX_SUBTASKS

    def test_invalid_json_raises(self) -> None:
        with pytest.raises((ValueError, Exception)):
            extract_subtasks("```json\n{not valid}\n```")

    def test_non_array_json_raises(self) -> None:
        with pytest.raises(ValueError, match="not a non-empty JSON array"):
            extract_subtasks('```json\n{"id":1}\n```')


# -- merge_usage --


class TestMergeUsage:
    def test_sum_numeric_fields(self) -> None:
        usages: list[dict[str, object] | None] = [
            {"input_tokens": 10, "output_tokens": 5},
            {"input_tokens": 20, "output_tokens": 15},
        ]
        result = merge_usage(usages)
        assert result is not None
        assert result["input_tokens"] == 30
        assert result["output_tokens"] == 20

    def test_all_none(self) -> None:
        assert merge_usage([None, None]) is None

    def test_mixed_none(self) -> None:
        usages: list[dict[str, object] | None] = [
            None,
            {"input_tokens": 10},
        ]
        result = merge_usage(usages)
        assert result is not None
        assert result["input_tokens"] == 10

    def test_non_numeric_last_write_wins(self) -> None:
        usages: list[dict[str, object] | None] = [
            {"model": "a"},
            {"model": "b"},
        ]
        result = merge_usage(usages)
        assert result is not None
        assert result["model"] == "b"


# -- format_aggregated_content --


class TestFormatAggregatedContent:
    def test_ok_and_failed_tags(self) -> None:
        results = [
            SubtaskResult(subtask_id=1, title="First", success=True, content="done"),
            SubtaskResult(subtask_id=2, title="Second", success=False, content="oops"),
        ]
        text = format_aggregated_content(results)
        assert "[OK]" in text
        assert "[FAILED]" in text
        assert "Subtask 1" in text
        assert "Subtask 2" in text
        assert "---" in text

    def test_single_result(self) -> None:
        results = [
            SubtaskResult(subtask_id=1, title="Only", success=True, content="result"),
        ]
        text = format_aggregated_content(results)
        assert "---" not in text
        assert "result" in text


# -- run_auto_split --


class TestRunAutoSplit:
    async def test_full_flow(self) -> None:
        """Phase 1 decomposes, Phase 2 executes each subtask."""
        call_count = 0

        async def mock_call(p: str, timeout: float) -> CLIResult:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # Phase 1: return subtask list
                return CLIResult(
                    success=True,
                    session_id="sid-1",
                    content='```json\n[{"id":1,"title":"A","prompt":"do A"},{"id":2,"title":"B","prompt":"do B"}]\n```',
                )
            # Phase 2: subtask execution
            return CLIResult(
                success=True,
                session_id=f"sid-{call_count}",
                content=f"Result {call_count - 1}",
                usage={"input_tokens": 10},
            )

        result = await run_auto_split("big task", call_fn=mock_call)
        assert result.success is True
        assert "Subtask 1" in result.content
        assert "Subtask 2" in result.content
        assert "[OK]" in result.content
        assert call_count == 3  # 1 decompose + 2 subtasks

    async def test_phase1_failure_fallback(self) -> None:
        """Phase 1 CLI failure falls back to original prompt."""
        call_count = 0

        async def mock_call(p: str, timeout: float) -> CLIResult:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("CLI crashed")
            return CLIResult(success=True, content="fallback result")

        result = await run_auto_split("original", call_fn=mock_call)
        assert result.success is True
        assert result.content == "fallback result"
        assert call_count == 2

    async def test_json_parse_failure_fallback(self) -> None:
        """Unparseable Phase 1 output falls back to original prompt."""
        call_count = 0

        async def mock_call(p: str, timeout: float) -> CLIResult:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return CLIResult(success=True, content="no json here")
            return CLIResult(success=True, content="fallback")

        result = await run_auto_split("original", call_fn=mock_call)
        assert result.success is True
        assert result.content == "fallback"

    async def test_partial_subtask_failure(self) -> None:
        """Some subtasks fail but execution continues."""
        call_count = 0

        async def mock_call(p: str, timeout: float) -> CLIResult:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return CLIResult(
                    success=True,
                    session_id="s1",
                    content='```json\n[{"id":1,"title":"OK","prompt":"a"},{"id":2,"title":"Fail","prompt":"b"}]\n```',
                )
            if call_count == 2:
                return CLIResult(success=True, content="good")
            return CLIResult(success=False, content="bad")

        result = await run_auto_split("task", call_fn=mock_call)
        assert result.success is False  # not all succeeded
        assert "[OK]" in result.content
        assert "[FAILED]" in result.content

    async def test_resume_fn_used_when_provided(self) -> None:
        """When resume_fn is provided, it's used for Phase 2 subtasks."""
        resume_calls: list[str] = []

        async def mock_call(p: str, timeout: float) -> CLIResult:
            return CLIResult(
                success=True,
                session_id="initial-sid",
                content='```json\n[{"id":1,"title":"T","prompt":"sub"}]\n```',
            )

        async def mock_resume(p: str, sid: str, timeout: float) -> CLIResult:
            resume_calls.append(sid)
            return CLIResult(success=True, session_id="resumed-sid", content="done")

        result = await run_auto_split(
            "task", call_fn=mock_call, resume_fn=mock_resume,
        )
        assert result.success is True
        assert len(resume_calls) == 1
        assert resume_calls[0] == "initial-sid"

    async def test_subtask_timeout(self) -> None:
        """Subtask timeout is caught and marked as failed."""
        call_count = 0

        async def mock_call(p: str, timeout: float) -> CLIResult:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return CLIResult(
                    success=True,
                    content='```json\n[{"id":1,"title":"Slow","prompt":"x"}]\n```',
                )
            raise asyncio.TimeoutError()

        result = await run_auto_split("task", call_fn=mock_call)
        assert result.success is False
        assert "[FAILED]" in result.content

    async def test_usage_merged(self) -> None:
        """Usage from Phase 1 and Phase 2 are merged."""
        call_count = 0

        async def mock_call(p: str, timeout: float) -> CLIResult:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return CLIResult(
                    success=True,
                    content='```json\n[{"id":1,"title":"T","prompt":"x"}]\n```',
                    usage={"input_tokens": 100},
                )
            return CLIResult(
                success=True,
                content="done",
                usage={"input_tokens": 50},
            )

        result = await run_auto_split("task", call_fn=mock_call)
        assert result.usage is not None
        assert result.usage["input_tokens"] == 150
