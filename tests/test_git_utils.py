"""Tests for git_utils module."""

from pathlib import Path

import pytest

from superai_mcp.git_utils import _validate_ref, read_files


class TestReadFiles:
    def test_existing_file(self, tmp_path: Path) -> None:
        f = tmp_path / "hello.txt"
        f.write_text("world")
        result = read_files(["hello.txt"], str(tmp_path))
        assert "--- hello.txt ---" in result
        assert "world" in result

    def test_missing_file(self, tmp_path: Path) -> None:
        result = read_files(["nope.txt"], str(tmp_path))
        assert "(file not found)" in result

    def test_multiple_files(self, tmp_path: Path) -> None:
        (tmp_path / "a.py").write_text("aaa")
        (tmp_path / "b.py").write_text("bbb")
        result = read_files(["a.py", "b.py"], str(tmp_path))
        assert "--- a.py ---" in result
        assert "--- b.py ---" in result
        assert "aaa" in result
        assert "bbb" in result

    def test_empty_list(self, tmp_path: Path) -> None:
        result = read_files([], str(tmp_path))
        assert result == ""

    def test_reject_path_traversal(self, tmp_path: Path) -> None:
        result = read_files(["../../../etc/passwd"], str(tmp_path))
        assert "(rejected: path traversal)" in result

    def test_reject_absolute_path(self, tmp_path: Path) -> None:
        result = read_files(["/etc/passwd"], str(tmp_path))
        assert "(rejected: absolute path)" in result


class TestValidateRef:
    def test_valid_refs(self) -> None:
        assert _validate_ref("main") == "main"
        assert _validate_ref("feature/foo-bar") == "feature/foo-bar"
        assert _validate_ref("v1.0.0") == "v1.0.0"

    def test_reject_leading_dash(self) -> None:
        with pytest.raises(ValueError, match="invalid git ref"):
            _validate_ref("--output=/tmp/x")

    def test_reject_double_dot(self) -> None:
        with pytest.raises(ValueError, match="not allowed"):
            _validate_ref("main..HEAD")
