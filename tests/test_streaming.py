"""Tests for streaming output helpers."""

import json

from superai_mcp.server import _extract_content_chunk


class TestExtractContentChunk:
    # -- Non-content lines --

    def test_empty_line(self) -> None:
        assert _extract_content_chunk("", "codex") == ""

    def test_invalid_json(self) -> None:
        assert _extract_content_chunk("not json", "codex") == ""

    def test_non_dict_json(self) -> None:
        assert _extract_content_chunk("[1, 2]", "codex") == ""

    # -- Codex --

    def test_codex_agent_message(self) -> None:
        line = json.dumps({
            "type": "item.completed",
            "item": {"type": "agent_message", "text": "Here is the fix"},
        })
        assert _extract_content_chunk(line, "codex") == "Here is the fix"

    def test_codex_reasoning_ignored(self) -> None:
        line = json.dumps({
            "type": "item.completed",
            "item": {"type": "reasoning", "text": "Let me think..."},
        })
        assert _extract_content_chunk(line, "codex") == ""

    def test_codex_turn_started_ignored(self) -> None:
        line = json.dumps({"type": "turn.started"})
        assert _extract_content_chunk(line, "codex") == ""

    # -- Gemini --

    def test_gemini_assistant_message(self) -> None:
        line = json.dumps({
            "type": "message", "role": "assistant", "content": "Hello world",
        })
        assert _extract_content_chunk(line, "gemini") == "Hello world"

    def test_gemini_user_message_ignored(self) -> None:
        line = json.dumps({
            "type": "message", "role": "user", "content": "prompt",
        })
        assert _extract_content_chunk(line, "gemini") == ""

    def test_gemini_init_ignored(self) -> None:
        line = json.dumps({"type": "init", "model": "gemini-pro"})
        assert _extract_content_chunk(line, "gemini") == ""

    # -- Claude --

    def test_claude_assistant_text(self) -> None:
        line = json.dumps({
            "type": "assistant",
            "message": {"content": [{"type": "text", "text": "response chunk"}]},
        })
        assert _extract_content_chunk(line, "claude") == "response chunk"

    def test_claude_assistant_multiple_blocks(self) -> None:
        line = json.dumps({
            "type": "assistant",
            "message": {"content": [
                {"type": "text", "text": "part1"},
                {"type": "text", "text": "part2"},
            ]},
        })
        assert _extract_content_chunk(line, "claude") == "part1part2"

    def test_claude_result_event(self) -> None:
        line = json.dumps({
            "type": "result", "subtype": "success", "result": "final answer",
        })
        assert _extract_content_chunk(line, "claude") == "final answer"

    def test_claude_system_init_ignored(self) -> None:
        line = json.dumps({"type": "system", "subtype": "init"})
        assert _extract_content_chunk(line, "claude") == ""

    def test_claude_tool_use_ignored(self) -> None:
        line = json.dumps({"type": "tool_use", "name": "read_file"})
        assert _extract_content_chunk(line, "claude") == ""

    # -- Unknown CLI --

    def test_unknown_cli(self) -> None:
        line = json.dumps({"type": "message", "role": "assistant", "content": "hi"})
        assert _extract_content_chunk(line, "unknown") == ""
