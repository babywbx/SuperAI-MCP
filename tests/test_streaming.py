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


from unittest.mock import AsyncMock, patch

from superai_mcp.runner import ProcessResult
from superai_mcp.server import codex_tool


class TestStreamIntegration:
    async def test_codex_stream_calls_ctx_info(self) -> None:
        """stream=True pushes content chunks via ctx.info()."""
        codex_output = [
            '{"type":"turn.started"}',
            '{"type":"item.completed","item":{"type":"agent_message","text":"chunk1"}}',
            '{"type":"item.completed","item":{"type":"agent_message","text":"chunk2"}}',
            '{"type":"turn.completed","usage":{}}',
        ]
        mock_result = ProcessResult(returncode=0, stdout_lines=codex_output, stderr="")
        mock_ctx = AsyncMock()

        captured_cb = None

        async def fake_run_cli(*args, **kwargs):
            nonlocal captured_cb
            captured_cb = kwargs.get("on_output")
            if captured_cb:
                for line in codex_output:
                    await captured_cb(line)
            return mock_result

        with patch("superai_mcp.server.run_cli", side_effect=fake_run_cli):
            with patch("superai_mcp.server.shutil.which", return_value="/usr/bin/codex"):
                with patch("superai_mcp.server.check_model", return_value=""):
                    await codex_tool(
                        prompt="test", cd="/tmp",
                        ctx=mock_ctx, stream=True,
                    )

        info_calls = [c for c in mock_ctx.info.call_args_list]
        texts = [c.args[0] for c in info_calls]
        assert "chunk1" in texts
        assert "chunk2" in texts

    async def test_codex_no_stream_no_ctx_info(self) -> None:
        """stream=False (default) does not call ctx.info()."""
        codex_output = [
            '{"type":"item.completed","item":{"type":"agent_message","text":"msg"}}',
        ]
        mock_result = ProcessResult(returncode=0, stdout_lines=codex_output, stderr="")
        mock_ctx = AsyncMock()

        with patch("superai_mcp.server.run_cli", AsyncMock(return_value=mock_result)):
            with patch("superai_mcp.server.shutil.which", return_value="/usr/bin/codex"):
                with patch("superai_mcp.server.check_model", return_value=""):
                    await codex_tool(
                        prompt="test", cd="/tmp",
                        ctx=mock_ctx, stream=False,
                    )

        mock_ctx.info.assert_not_called()
