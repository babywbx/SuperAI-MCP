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


async def test_run_env() -> None:
    """Custom env is passed to subprocess."""
    import os

    env = dict(os.environ)
    env["SUPERAI_TEST_VAR"] = "hello123"
    result = await run_cli("sh", ["-c", "echo $SUPERAI_TEST_VAR"], env=env)
    assert result.returncode == 0
    assert result.stdout_lines == ["hello123"]


async def test_run_env_removes_var() -> None:
    """Env without a var means subprocess doesn't see it."""
    import os

    env = dict(os.environ)
    env.pop("HOME", None)
    result = await run_cli("sh", ["-c", "echo ${HOME:-unset}"], env=env)
    assert result.returncode == 0
    assert result.stdout_lines == ["unset"]


async def test_progress_callback_called() -> None:
    """on_progress is called during long-running commands."""
    from unittest.mock import AsyncMock

    progress_mock = AsyncMock()

    # Use a process that sleeps for longer than the interval
    # We temporarily reduce the interval for testing
    import superai_mcp.runner as runner_mod
    original_interval = runner_mod._PROGRESS_INTERVAL
    runner_mod._PROGRESS_INTERVAL = 0.1  # 100ms for fast test
    try:
        result = await run_cli(
            "sleep", ["0.35"],
            timeout=5.0,
            on_progress=progress_mock,
        )
    finally:
        runner_mod._PROGRESS_INTERVAL = original_interval

    assert result.returncode == 0
    # Should have been called at least twice (at 100ms, 200ms)
    assert progress_mock.call_count >= 2


async def test_progress_callback_none() -> None:
    """on_progress=None (default) works fine."""
    result = await run_cli("echo", ["ok"], on_progress=None)
    assert result.returncode == 0
    assert result.stdout_lines == ["ok"]


async def test_progress_callback_exception_cleans_up() -> None:
    """Subprocess is killed when on_progress raises an exception."""
    import superai_mcp.runner as runner_mod

    original_interval = runner_mod._PROGRESS_INTERVAL
    runner_mod._PROGRESS_INTERVAL = 0.1

    async def _bad_progress(elapsed: float, latest_line: str) -> None:
        raise RuntimeError("callback boom")

    try:
        with pytest.raises(RuntimeError, match="callback boom"):
            await run_cli("sleep", ["10"], timeout=5.0, on_progress=_bad_progress)
    finally:
        runner_mod._PROGRESS_INTERVAL = original_interval


async def test_progress_elapsed_uses_float() -> None:
    """Elapsed time is tracked as float, not truncated to 0 for short intervals."""
    import superai_mcp.runner as runner_mod

    original_interval = runner_mod._PROGRESS_INTERVAL
    runner_mod._PROGRESS_INTERVAL = 0.05  # 50ms

    elapsed_values: list[float] = []

    async def _track(elapsed: float, latest_line: str) -> None:
        elapsed_values.append(elapsed)

    try:
        await run_cli("sleep", ["0.2"], timeout=5.0, on_progress=_track)
    finally:
        runner_mod._PROGRESS_INTERVAL = original_interval

    # With float tracking, at least one callback should report elapsed > 0
    assert any(e > 0 for e in elapsed_values), f"all elapsed were 0: {elapsed_values}"


async def test_run_stdin_data() -> None:
    """stdin_data is written to subprocess stdin."""
    result = await run_cli(
        "cat", [],
        stdin_data=b"hello from stdin",
    )
    assert result.returncode == 0
    assert result.stdout_lines == ["hello from stdin"]


async def test_run_stdin_data_none_uses_devnull() -> None:
    """stdin_data=None (default) keeps stdin as DEVNULL."""
    result = await run_cli("echo", ["ok"], stdin_data=None)
    assert result.returncode == 0
    assert result.stdout_lines == ["ok"]


async def test_run_stdin_data_large() -> None:
    """Large stdin_data doesn't deadlock."""
    # 500KB of text — well above typical pipe buffer (64KB)
    big = ("x" * 999 + "\n") * 500
    result = await run_cli("wc", ["-l"], stdin_data=big.encode())
    assert result.returncode == 0
    assert result.stdout_lines[0].strip() == "500"


async def test_run_stdin_data_early_close() -> None:
    """Child exiting before consuming all stdin doesn't raise BrokenPipeError."""
    big = ("x" * 999 + "\n") * 500
    result = await run_cli("head", ["-n", "1"], stdin_data=big.encode())
    assert result.returncode == 0
    assert len(result.stdout_lines) == 1


def test_process_result_frozen() -> None:
    r = ProcessResult(returncode=0, stdout_lines=["a"], stderr="")
    with pytest.raises(AttributeError):
        r.returncode = 1  # type: ignore[misc]
