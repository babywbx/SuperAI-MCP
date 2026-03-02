"""Unit tests for the broadcast tool (mocked CLI calls)."""

import json
from unittest.mock import AsyncMock, patch

import pytest

from superai_mcp.models import CLIResult
from superai_mcp.server import broadcast_tool
from superai_mcp.validate import MAX_FILES


def _fake_result(name: str) -> str:
    """Return a JSON string mimicking a successful CLIResult."""
    return CLIResult(
        success=True, content=f"{name} response", session_id=f"{name}-sid-123",
    ).model_dump_json()


def _fake_error(name: str) -> str:
    """Return a JSON string mimicking a failed CLIResult."""
    return CLIResult(success=False, content=f"{name} CLI not found in PATH").model_dump_json()


@pytest.fixture()
def _mock_tools():
    """Patch all three tool functions with async mocks."""
    with (
        patch("superai_mcp.server.codex_tool", new_callable=AsyncMock) as codex,
        patch("superai_mcp.server.gemini_tool", new_callable=AsyncMock) as gemini,
        patch("superai_mcp.server.claude_tool", new_callable=AsyncMock) as claude,
    ):
        codex.return_value = _fake_result("codex")
        gemini.return_value = _fake_result("gemini")
        claude.return_value = _fake_result("claude")
        # Also patch _TARGET_FNS so broadcast picks up the mocks
        with patch.dict(
            "superai_mcp.server._TARGET_FNS",
            {"codex": codex, "gemini": gemini, "claude": claude},
        ):
            yield {"codex": codex, "gemini": gemini, "claude": claude}


class TestDefaultTargets:
    @pytest.mark.usefixtures("_mock_tools")
    async def test_all_targets_called(self, _mock_tools: dict) -> None:
        """No targets -> all three CLIs called."""
        raw = await broadcast_tool(prompt="hello", cd="/tmp")
        result = json.loads(raw)
        assert result["success"] is True
        assert set(result["results"].keys()) == {"codex", "gemini", "claude"}
        for name in ("codex", "gemini", "claude"):
            assert result["results"][name]["success"] is True

    @pytest.mark.usefixtures("_mock_tools")
    async def test_empty_list_means_all(self, _mock_tools: dict) -> None:
        """Empty list [] also means all targets."""
        raw = await broadcast_tool(prompt="hello", cd="/tmp", targets=[])
        result = json.loads(raw)
        assert result["success"] is True
        assert set(result["results"].keys()) == {"codex", "gemini", "claude"}


class TestSpecificTargets:
    @pytest.mark.usefixtures("_mock_tools")
    async def test_single_target(self, _mock_tools: dict) -> None:
        """Only the specified target is called."""
        raw = await broadcast_tool(prompt="hello", cd="/tmp", targets=["gemini"])
        result = json.loads(raw)
        assert result["success"] is True
        assert set(result["results"].keys()) == {"gemini"}
        assert result["results"]["gemini"]["success"] is True
        _mock_tools["codex"].assert_not_called()
        _mock_tools["claude"].assert_not_called()

    @pytest.mark.usefixtures("_mock_tools")
    async def test_two_targets(self, _mock_tools: dict) -> None:
        """Two targets -> only those two called."""
        raw = await broadcast_tool(prompt="hello", cd="/tmp", targets=["codex", "claude"])
        result = json.loads(raw)
        assert set(result["results"].keys()) == {"codex", "claude"}
        _mock_tools["gemini"].assert_not_called()


class TestInvalidTargets:
    async def test_invalid_target_error(self) -> None:
        """Non-existent target returns error."""
        raw = await broadcast_tool(prompt="hello", cd="/tmp", targets=["gpt5"])
        result = json.loads(raw)
        assert result["success"] is False
        assert "invalid target" in result["content"]

    async def test_mixed_valid_invalid(self) -> None:
        """Mix of valid and invalid targets returns error."""
        raw = await broadcast_tool(prompt="hello", cd="/tmp", targets=["codex", "bad"])
        result = json.loads(raw)
        assert result["success"] is False
        assert "bad" in result["content"]


class TestDuplicateTargets:
    @pytest.mark.usefixtures("_mock_tools")
    async def test_duplicates_deduplicated(self, _mock_tools: dict) -> None:
        """Duplicate targets are deduplicated, each CLI called once."""
        raw = await broadcast_tool(prompt="hello", cd="/tmp", targets=["codex", "codex"])
        result = json.loads(raw)
        assert result["success"] is True
        assert set(result["results"].keys()) == {"codex"}
        _mock_tools["codex"].assert_called_once()

    @pytest.mark.usefixtures("_mock_tools")
    async def test_duplicates_preserve_order(self, _mock_tools: dict) -> None:
        """Deduplication preserves first-seen order."""
        raw = await broadcast_tool(
            prompt="hello", cd="/tmp",
            targets=["claude", "codex", "claude", "gemini", "codex"],
        )
        result = json.loads(raw)
        assert set(result["results"].keys()) == {"claude", "codex", "gemini"}


class TestPartialFailure:
    @pytest.mark.usefixtures("_mock_tools")
    async def test_one_cli_fails(self, _mock_tools: dict) -> None:
        """One CLI failure doesn't affect others."""
        _mock_tools["codex"].return_value = _fake_error("codex")
        raw = await broadcast_tool(prompt="hello", cd="/tmp")
        result = json.loads(raw)
        assert result["success"] is True
        assert result["results"]["codex"]["success"] is False
        assert result["results"]["gemini"]["success"] is True
        assert result["results"]["claude"]["success"] is True

    @pytest.mark.usefixtures("_mock_tools")
    async def test_one_cli_raises(self, _mock_tools: dict) -> None:
        """One CLI raising exception doesn't affect others."""
        _mock_tools["gemini"].side_effect = RuntimeError("boom")
        raw = await broadcast_tool(prompt="hello", cd="/tmp")
        result = json.loads(raw)
        assert result["success"] is True
        assert result["results"]["gemini"]["success"] is False
        assert "boom" in result["results"]["gemini"]["content"]
        assert result["results"]["codex"]["success"] is True
        assert result["results"]["claude"]["success"] is True

    @pytest.mark.usefixtures("_mock_tools")
    async def test_malformed_json_from_tool(self, _mock_tools: dict) -> None:
        """Tool returning non-JSON string is handled gracefully."""
        _mock_tools["codex"].return_value = "not json at all"
        raw = await broadcast_tool(prompt="hello", cd="/tmp")
        result = json.loads(raw)
        assert result["success"] is True
        # codex should have an error entry since json.loads will fail
        assert result["results"]["codex"]["success"] is False
        assert "error" in result["results"]["codex"]["content"]
        # Others unaffected
        assert result["results"]["gemini"]["success"] is True


class TestResultsStructure:
    @pytest.mark.usefixtures("_mock_tools")
    async def test_json_structure(self, _mock_tools: dict) -> None:
        """Verify the top-level JSON structure."""
        raw = await broadcast_tool(prompt="hello", cd="/tmp")
        result = json.loads(raw)
        assert isinstance(result, dict)
        assert result["success"] is True
        assert "results" in result
        assert isinstance(result["results"], dict)
        for data in result["results"].values():
            assert "success" in data
            assert "content" in data

    @pytest.mark.usefixtures("_mock_tools")
    async def test_context_prebuilt(self, _mock_tools: dict) -> None:
        """Review/files kwargs are disabled for per-target calls (context pre-built)."""
        await broadcast_tool(
            prompt="test", cd="/tmp", targets=["codex"],
            review_uncommitted=True, files=["a.py"],
        )
        call_kwargs = _mock_tools["codex"].call_args.kwargs
        # Context was pre-built, so review/files should be disabled
        assert call_kwargs["review_uncommitted"] is False
        assert call_kwargs["review_base"] == ""
        assert call_kwargs["files"] is None

    @pytest.mark.usefixtures("_mock_tools")
    async def test_kwargs_forwarded(self, _mock_tools: dict) -> None:
        """Common kwargs are forwarded to tool functions."""
        await broadcast_tool(
            prompt="test", cd="/tmp", targets=["codex"],
            model="gpt-4",
        )
        _mock_tools["codex"].assert_called_once()
        call_kwargs = _mock_tools["codex"].call_args.kwargs
        assert "test" in call_kwargs["prompt"]
        assert call_kwargs["cd"] == "/tmp"
        assert call_kwargs["model"] == "gpt-4"


class TestBroadcastValidatesFiles:
    async def test_too_many_files_rejected(self) -> None:
        """broadcast_tool enforces MAX_FILES limit."""
        big_list = [f"file{i}.py" for i in range(MAX_FILES + 1)]
        raw = await broadcast_tool(prompt="hello", cd="/tmp", files=big_list)
        result = json.loads(raw)
        assert result["success"] is False
        assert "too many files" in result["content"]
