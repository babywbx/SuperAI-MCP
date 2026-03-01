"""Tests for the async subprocess runner."""

import asyncio

import pytest

from superai_mcp.runner import ProcessResult, run_cli


async def test_run_echo() -> None:
    result = await run_cli("echo", ["hello world"])
    assert result.returncode == 0
    assert result.stdout_lines == ["hello world"]
    assert result.stderr == ""


async def test_run_multiline() -> None:
    result = await run_cli("printf", ["line1\nline2\nline3"])
    assert result.returncode == 0
    assert result.stdout_lines == ["line1", "line2", "line3"]


async def test_run_stderr() -> None:
    result = await run_cli("sh", ["-c", "echo err >&2; exit 1"])
    assert result.returncode == 1
    assert "err" in result.stderr


async def test_run_timeout() -> None:
    with pytest.raises(asyncio.TimeoutError):
        await run_cli("sleep", ["10"], timeout=0.1)


async def test_run_cwd(tmp_path: object) -> None:
    result = await run_cli("pwd", [], cwd=str(tmp_path))
    assert result.returncode == 0
    assert str(tmp_path) in result.stdout_lines[0]


def test_process_result_frozen() -> None:
    r = ProcessResult(returncode=0, stdout_lines=["a"], stderr="")
    with pytest.raises(AttributeError):
        r.returncode = 1  # type: ignore[misc]
