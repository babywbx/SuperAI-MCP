"""Tests for prompt template feature."""

import json
from unittest.mock import AsyncMock, patch

import pytest

from superai_mcp.runner import ProcessResult
from superai_mcp.server import _apply_template, _TEMPLATES, codex_tool


class TestApplyTemplate:
    def test_empty_template_passthrough(self) -> None:
        assert _apply_template("hello", "") == "hello"

    def test_known_template(self) -> None:
        result = _apply_template("my code", "review")
        assert "my code" in result
        assert "bugs" in result.lower() or "review" in result.lower()

    def test_unknown_template_raises(self) -> None:
        with pytest.raises(ValueError, match="unknown template"):
            _apply_template("hello", "nonexistent")

    def test_unknown_template_lists_available(self) -> None:
        with pytest.raises(ValueError, match="review"):
            _apply_template("hello", "bad")

    def test_all_templates_have_prompt_placeholder(self) -> None:
        for name, tpl in _TEMPLATES.items():
            assert "{prompt}" in tpl, f"template {name!r} missing {{prompt}}"

    def test_all_templates_format_correctly(self) -> None:
        for name in _TEMPLATES:
            result = _apply_template("test input", name)
            assert "test input" in result
            assert "{prompt}" not in result


class TestTemplateIntegration:
    @pytest.fixture()
    def _mock_run_cli(self):
        with patch("superai_mcp.server.run_cli", new_callable=AsyncMock) as mock:
            yield mock

    @pytest.fixture()
    def _mock_which(self):
        with patch("superai_mcp.server.shutil.which", return_value="/usr/bin/codex"):
            yield

    @pytest.mark.usefixtures("_mock_which")
    async def test_template_wraps_prompt(self, _mock_run_cli: AsyncMock) -> None:
        """Template should wrap the prompt before sending to CLI."""
        codex_lines = [
            '{"type":"thread.started","thread_id":"x-001"}',
            '{"type":"item.completed","item":{"type":"agent_message","text":"done"}}',
            '{"type":"turn.completed","usage":{"input_tokens":10,"output_tokens":5}}',
        ]
        _mock_run_cli.return_value = ProcessResult(
            returncode=0, stdout_lines=codex_lines, stderr="",
        )

        raw = await codex_tool(prompt="check this function", cd="/tmp", template="review")
        result = json.loads(raw)

        assert result["success"] is True
        # The prompt sent to CLI should contain template text
        call_args = _mock_run_cli.call_args
        stdin_data = call_args.kwargs.get("stdin_data")
        if stdin_data:
            sent_prompt = stdin_data.decode()
        else:
            cli_args = call_args[0][1]
            sent_prompt = cli_args[-1]
        assert "check this function" in sent_prompt
        assert "review" in sent_prompt.lower() or "bug" in sent_prompt.lower()

    @pytest.mark.usefixtures("_mock_which")
    async def test_invalid_template_returns_error(self, _mock_run_cli: AsyncMock) -> None:
        """Invalid template should return error without calling CLI."""
        raw = await codex_tool(prompt="hello", cd="/tmp", template="nonexistent")
        result = json.loads(raw)

        assert result["success"] is False
        assert "unknown template" in result["content"]
        _mock_run_cli.assert_not_called()
