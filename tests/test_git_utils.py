"""Tests for git_utils module."""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from superai_mcp.git_utils import _validate_ref, get_git_diff, read_files
from superai_mcp.runner import ProcessResult


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

    def test_reject_sibling_prefix_attack(self, tmp_path: Path) -> None:
        # /tmp/repo vs /tmp/repo2 — startswith would pass, is_relative_to blocks
        sibling = tmp_path.parent / (tmp_path.name + "2")
        sibling.mkdir(exist_ok=True)
        secret = sibling / "secret.txt"
        secret.write_text("leaked")
        rel = f"../{sibling.name}/secret.txt"
        result = read_files([rel], str(tmp_path))
        assert "(rejected: path traversal)" in result


class TestGetGitDiff:
    async def test_no_params_returns_empty(self, tmp_path: Path) -> None:
        result = await get_git_diff(str(tmp_path))
        assert result == ""

    async def test_mutually_exclusive_uncommitted_base(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="mutually exclusive"):
            await get_git_diff(str(tmp_path), uncommitted=True, base="main")

    async def test_mutually_exclusive_uncommitted_commit(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="mutually exclusive"):
            await get_git_diff(str(tmp_path), uncommitted=True, commit="abc1234")

    async def test_mutually_exclusive_base_commit(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="mutually exclusive"):
            await get_git_diff(str(tmp_path), base="main", commit="abc1234")

    async def test_mutually_exclusive_all_three(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="mutually exclusive"):
            await get_git_diff(str(tmp_path), uncommitted=True, base="main", commit="abc1234")


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


class TestGetGitDiffCommit:
    """Tests for review_commit mode using diff-tree --root."""

    async def test_commit_uses_diff_tree_root(self, tmp_path: Path) -> None:
        """commit mode calls 'git diff-tree --root -p <sha>'."""
        fake = ProcessResult(returncode=0, stdout_lines=["diff output"], stderr="")
        with patch("superai_mcp.git_utils.run_cli", new_callable=AsyncMock, return_value=fake) as mock:
            result = await get_git_diff(str(tmp_path), commit="abc1234")

        mock.assert_called_once()
        args = mock.call_args[0]
        assert args[0] == "git"
        assert args[1] == ["diff-tree", "--root", "-p", "abc1234"]
        assert result == "diff output"

    async def test_commit_failure_returns_error(self, tmp_path: Path) -> None:
        """Non-zero returncode returns error message."""
        fake = ProcessResult(returncode=128, stdout_lines=[], stderr="bad object")
        with patch("superai_mcp.git_utils.run_cli", new_callable=AsyncMock, return_value=fake):
            result = await get_git_diff(str(tmp_path), commit="bad1234")

        assert "git diff failed" in result
        assert "bad object" in result
