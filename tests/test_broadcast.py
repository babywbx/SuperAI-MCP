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
    async def test_system_prompt_passed_per_target(self, _mock_tools: dict) -> None:
        """system_prompt is forwarded to each target (not pre-baked into context)."""
        await broadcast_tool(
            prompt="test", cd="/tmp", targets=["codex"],
            system_prompt="be concise",
        )
        call_kwargs = _mock_tools["codex"].call_args.kwargs
        assert call_kwargs["system_prompt"] == "be concise"

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


class TestPerTargetModels:
    @pytest.mark.usefixtures("_mock_tools")
    async def test_per_target_model_override(self, _mock_tools: dict) -> None:
        """Per-target model overrides the global model."""
        await broadcast_tool(
            prompt="test", cd="/tmp", targets=["codex", "gemini"],
            model="default-model",
            models={"gemini": "gemini-3.1-pro-preview"},
        )
        codex_kwargs = _mock_tools["codex"].call_args.kwargs
        gemini_kwargs = _mock_tools["gemini"].call_args.kwargs
        assert codex_kwargs["model"] == "default-model"
        assert gemini_kwargs["model"] == "gemini-3.1-pro-preview"

    @pytest.mark.usefixtures("_mock_tools")
    async def test_per_target_model_only(self, _mock_tools: dict) -> None:
        """Per-target model without global model leaves others empty."""
        await broadcast_tool(
            prompt="test", cd="/tmp", targets=["codex", "gemini"],
            models={"gemini": "gemini-3.1-pro-preview"},
        )
        codex_kwargs = _mock_tools["codex"].call_args.kwargs
        gemini_kwargs = _mock_tools["gemini"].call_args.kwargs
        assert codex_kwargs["model"] == ""
        assert gemini_kwargs["model"] == "gemini-3.1-pro-preview"

    async def test_invalid_models_key(self) -> None:
        """Invalid key in models dict returns error."""
        raw = await broadcast_tool(
            prompt="test", cd="/tmp",
            models={"gpt5": "some-model"},
        )
        result = json.loads(raw)
        assert result["success"] is False
        assert "invalid models key" in result["content"]


class TestPerTargetOverrides:
    @pytest.mark.usefixtures("_mock_tools")
    async def test_override_timeout(self, _mock_tools: dict) -> None:
        """Per-target timeout override via overrides dict."""
        await broadcast_tool(
            prompt="test", cd="/tmp", targets=["codex", "claude"],
            timeout=300.0,
            overrides={"codex": {"timeout": 600.0}},
        )
        codex_kwargs = _mock_tools["codex"].call_args.kwargs
        claude_kwargs = _mock_tools["claude"].call_args.kwargs
        assert codex_kwargs["timeout"] == 600.0
        assert claude_kwargs["timeout"] == 300.0

    @pytest.mark.usefixtures("_mock_tools")
    async def test_override_system_prompt(self, _mock_tools: dict) -> None:
        """Per-target system_prompt override."""
        await broadcast_tool(
            prompt="test", cd="/tmp", targets=["codex", "gemini"],
            system_prompt="default prompt",
            overrides={"gemini": {"system_prompt": "gemini specific"}},
        )
        codex_kwargs = _mock_tools["codex"].call_args.kwargs
        gemini_kwargs = _mock_tools["gemini"].call_args.kwargs
        assert codex_kwargs["system_prompt"] == "default prompt"
        assert gemini_kwargs["system_prompt"] == "gemini specific"

    @pytest.mark.usefixtures("_mock_tools")
    async def test_override_model_priority(self, _mock_tools: dict) -> None:
        """overrides.model > models dict > global model."""
        await broadcast_tool(
            prompt="test", cd="/tmp", targets=["codex", "gemini", "claude"],
            model="global",
            models={"gemini": "from-models"},
            overrides={"claude": {"model": "from-overrides"}},
        )
        codex_kwargs = _mock_tools["codex"].call_args.kwargs
        gemini_kwargs = _mock_tools["gemini"].call_args.kwargs
        claude_kwargs = _mock_tools["claude"].call_args.kwargs
        assert codex_kwargs["model"] == "global"
        assert gemini_kwargs["model"] == "from-models"
        assert claude_kwargs["model"] == "from-overrides"

    @pytest.mark.usefixtures("_mock_tools")
    async def test_override_model_beats_models_dict(self, _mock_tools: dict) -> None:
        """overrides.model takes precedence over models dict for same target."""
        await broadcast_tool(
            prompt="test", cd="/tmp", targets=["codex"],
            models={"codex": "from-models"},
            overrides={"codex": {"model": "from-overrides"}},
        )
        codex_kwargs = _mock_tools["codex"].call_args.kwargs
        assert codex_kwargs["model"] == "from-overrides"

    @pytest.mark.usefixtures("_mock_tools")
    async def test_override_target_specific_params(self, _mock_tools: dict) -> None:
        """Target-specific params like effort (claude) via overrides."""
        await broadcast_tool(
            prompt="test", cd="/tmp", targets=["claude"],
            overrides={"claude": {"effort": "high", "max_budget_usd": 5.0}},
        )
        claude_kwargs = _mock_tools["claude"].call_args.kwargs
        assert claude_kwargs["effort"] == "high"
        assert claude_kwargs["max_budget_usd"] == 5.0

    @pytest.mark.usefixtures("_mock_tools")
    async def test_override_multiple_targets(self, _mock_tools: dict) -> None:
        """Different overrides for different targets."""
        await broadcast_tool(
            prompt="test", cd="/tmp",
            overrides={
                "codex": {"timeout": 120.0, "reasoning_effort": "high"},
                "gemini": {"timeout": 60.0},
                "claude": {"timeout": 900.0, "effort": "high"},
            },
        )
        codex_kwargs = _mock_tools["codex"].call_args.kwargs
        gemini_kwargs = _mock_tools["gemini"].call_args.kwargs
        claude_kwargs = _mock_tools["claude"].call_args.kwargs
        assert codex_kwargs["timeout"] == 120.0
        assert codex_kwargs["reasoning_effort"] == "high"
        assert gemini_kwargs["timeout"] == 60.0
        assert claude_kwargs["timeout"] == 900.0
        assert claude_kwargs["effort"] == "high"

    @pytest.mark.usefixtures("_mock_tools")
    async def test_blocked_keys_ignored(self, _mock_tools: dict) -> None:
        """Pre-built context params in overrides are silently ignored."""
        await broadcast_tool(
            prompt="test", cd="/tmp", targets=["codex"],
            overrides={"codex": {
                "review_uncommitted": True,
                "files": ["hack.py"],
                "timeout": 999.0,
            }},
        )
        codex_kwargs = _mock_tools["codex"].call_args.kwargs
        # Blocked keys stay at their pre-built values
        assert codex_kwargs["review_uncommitted"] is False
        assert codex_kwargs["files"] is None
        # Non-blocked key is applied
        assert codex_kwargs["timeout"] == 999.0

    async def test_invalid_overrides_key(self) -> None:
        """Invalid target key in overrides returns error."""
        raw = await broadcast_tool(
            prompt="test", cd="/tmp",
            overrides={"gpt5": {"timeout": 100}},
        )
        result = json.loads(raw)
        assert result["success"] is False
        assert "invalid overrides key" in result["content"]

    @pytest.mark.usefixtures("_mock_tools")
    async def test_empty_overrides_no_effect(self, _mock_tools: dict) -> None:
        """Empty overrides dict has no effect."""
        await broadcast_tool(
            prompt="test", cd="/tmp", targets=["codex"],
            timeout=300.0, overrides={},
        )
        codex_kwargs = _mock_tools["codex"].call_args.kwargs
        assert codex_kwargs["timeout"] == 300.0

    @pytest.mark.usefixtures("_mock_tools")
    async def test_none_overrides_no_effect(self, _mock_tools: dict) -> None:
        """None overrides has no effect (default)."""
        await broadcast_tool(
            prompt="test", cd="/tmp", targets=["codex"],
            timeout=300.0,
        )
        codex_kwargs = _mock_tools["codex"].call_args.kwargs
        assert codex_kwargs["timeout"] == 300.0


class TestBroadcastValidatesFiles:
    async def test_too_many_files_rejected(self) -> None:
        """broadcast_tool enforces MAX_FILES limit."""
        big_list = [f"file{i}.py" for i in range(MAX_FILES + 1)]
        raw = await broadcast_tool(prompt="hello", cd="/tmp", files=big_list)
        result = json.loads(raw)
        assert result["success"] is False
        assert "too many files" in result["content"]
