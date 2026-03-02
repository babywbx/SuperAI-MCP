"""Tests for input validation module."""

from pathlib import Path

import pytest

from superai_mcp.validate import (
    validate_cd,
    validate_files,
    validate_model,
    validate_reasoning_effort,
    validate_sandbox,
    validate_session_id,
)


class TestValidateCd:
    def test_valid_dir(self, tmp_path: Path) -> None:
        result = validate_cd(str(tmp_path))
        assert result == tmp_path.resolve()

    def test_nonexistent(self) -> None:
        with pytest.raises(ValueError, match="not a valid directory"):
            validate_cd("/nonexistent/path/xyz")

    def test_file_not_dir(self, tmp_path: Path) -> None:
        f = tmp_path / "file.txt"
        f.write_text("x")
        with pytest.raises(ValueError, match="not a valid directory"):
            validate_cd(str(f))


class TestValidateSandbox:
    def test_valid_values(self) -> None:
        from superai_mcp.models import Sandbox

        assert validate_sandbox("read-only") == Sandbox.READ_ONLY
        assert validate_sandbox("workspace-write") == Sandbox.WORKSPACE_WRITE
        assert validate_sandbox("danger-full-access") == Sandbox.DANGER_FULL_ACCESS

    def test_invalid(self) -> None:
        with pytest.raises(ValueError, match="invalid sandbox"):
            validate_sandbox("yolo-mode")

    def test_empty_string(self) -> None:
        with pytest.raises(ValueError, match="invalid sandbox"):
            validate_sandbox("")


class TestValidateSessionId:
    def test_valid_uuid(self) -> None:
        assert validate_session_id("019cabc6-2dda-7831-ba07-794ff7ba9858")

    def test_empty_ok(self) -> None:
        assert validate_session_id("") == ""

    def test_flag_injection(self) -> None:
        with pytest.raises(ValueError, match="invalid session_id"):
            validate_session_id("--evil-flag")

    def test_path_injection(self) -> None:
        with pytest.raises(ValueError, match="invalid session_id"):
            validate_session_id("../../../etc/passwd")


class TestValidateModel:
    def test_valid_models(self) -> None:
        assert validate_model("gpt-5.3-codex") == "gpt-5.3-codex"
        assert validate_model("gemini-3.1-pro") == "gemini-3.1-pro"
        assert validate_model("flash") == "flash"
        assert validate_model("pro") == "pro"

    def test_empty_ok(self) -> None:
        assert validate_model("") == ""

    def test_flag_injection(self) -> None:
        with pytest.raises(ValueError, match="invalid model"):
            validate_model("--config=/evil")

    def test_special_chars(self) -> None:
        with pytest.raises(ValueError, match="invalid model"):
            validate_model("model; rm -rf /")


class TestValidateReasoningEffort:
    def test_valid_values(self) -> None:
        for v in ("low", "medium", "high", "xhigh"):
            assert validate_reasoning_effort(v) == v

    def test_empty_ok(self) -> None:
        assert validate_reasoning_effort("") == ""

    def test_invalid(self) -> None:
        with pytest.raises(ValueError, match="invalid reasoning_effort"):
            validate_reasoning_effort("ultra")

    def test_injection(self) -> None:
        with pytest.raises(ValueError, match="invalid reasoning_effort"):
            validate_reasoning_effort("high other_setting=evil")


class TestValidateFiles:
    def test_normal_list(self) -> None:
        assert validate_files(["a.py", "b.py"]) == ["a.py", "b.py"]

    def test_none_ok(self) -> None:
        assert validate_files(None) is None

    def test_too_many(self) -> None:
        with pytest.raises(ValueError, match="too many files"):
            validate_files([f"file{i}.py" for i in range(100)])
