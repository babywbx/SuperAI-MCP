"""Async subprocess runner for CLI tools."""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path

# Interval in seconds between progress callbacks
_PROGRESS_INTERVAL = 5.0
# Grace period when CLI has new output (still active)
_GRACE_OUTPUT = 30.0
# Grace period when output contains keywords signaling active generation
_GRACE_KEYWORD = 120.0
# Maximum cumulative grace time to prevent unbounded runs
_MAX_GRACE_TOTAL = 300.0
# Keywords that signal CLI is in its final output phase (strict).
# Only matched against the LAST stdout line (lowercased).
# Codex:  "agent_message" appears in item.completed when outputting the final answer.
# Gemini: after tool cycles, assistant delta messages are the final answer.
# Claude: stream-json emits "type":"assistant" events during final answer output.
_GRACE_KEYWORDS = frozenset((
    "agent_message",         # Codex: final answer item
    '"role":"assistant"',    # Gemini: assistant is speaking (final answer after tool cycles)
    '"type":"assistant"',    # Claude: stream-json assistant event
))


@dataclass(frozen=True)
class ProcessResult:
    """Captured output from a subprocess."""

    returncode: int
    stdout_lines: list[str] = field(default_factory=list)
    stderr: str = ""


async def run_cli(
    command: str,
    args: list[str],
    *,
    cwd: str | Path | None = None,
    env: dict[str, str] | None = None,
    stdin_data: bytes | None = None,
    timeout: float = 900.0,
    on_progress: Callable[[float, str], Awaitable[None]] | None = None,
    on_output: Callable[[str], Awaitable[None]] | None = None,
) -> ProcessResult:
    """Run a CLI command asynchronously and capture output.

    Raises asyncio.TimeoutError if the process exceeds `timeout` seconds.
    Calls on_progress(elapsed_seconds, latest_stdout_line) every ~25s while waiting.
    """
    proc = await asyncio.create_subprocess_exec(
        command,
        *args,
        stdin=asyncio.subprocess.PIPE if stdin_data is not None else asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=cwd,
        env=env,
    )

    if proc.stdout is None or proc.stderr is None:
        raise RuntimeError("Failed to capture subprocess pipes")

    # Write stdin data concurrently to avoid deadlock with stdout/stderr draining.
    # BrokenPipeError is suppressed when the child exits before consuming all input
    # (e.g. head -n1), matching subprocess.communicate() semantics.
    async def write_stdin(data: bytes) -> None:
        assert proc.stdin is not None
        try:
            proc.stdin.write(data)
            await proc.stdin.drain()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            proc.stdin.close()
            try:
                await proc.stdin.wait_closed()
            except OSError:
                pass

    stdin_task: asyncio.Task[None] | None = None
    if stdin_data is not None:
        stdin_task = asyncio.create_task(write_stdin(stdin_data))

    # Shared buffer so the progress loop can peek at the latest line
    stdout_lines: list[str] = []

    # Fire-and-forget tasks for on_output to avoid blocking pipe reads
    _output_tasks: list[asyncio.Task[None]] = []

    async def drain_lines(stream: asyncio.StreamReader) -> list[str]:
        while True:
            raw = await stream.readline()
            if not raw:
                break
            line = raw.decode("utf-8", errors="replace").rstrip("\r\n")
            stdout_lines.append(line)
            if on_output is not None:
                _output_tasks.append(asyncio.create_task(on_output(line)))
        return stdout_lines

    async def drain_all(stream: asyncio.StreamReader) -> str:
        data = await stream.read()
        return data.decode("utf-8", errors="replace")

    stdout_task = asyncio.create_task(drain_lines(proc.stdout))
    stderr_task = asyncio.create_task(drain_all(proc.stderr))

    try:
        wait_task = asyncio.create_task(proc.wait())
        elapsed = 0.0
        remaining = timeout
        last_line_count = 0
        in_grace = False
        grace_used = 0.0

        while True:
            interval = min(_PROGRESS_INTERVAL, remaining)
            done, _ = await asyncio.wait({wait_task}, timeout=interval)
            if done:
                break
            elapsed += interval
            remaining -= interval
            if remaining <= 0:
                # Grace period: extend if CLI is still producing output
                if grace_used >= _MAX_GRACE_TOTAL:
                    raise asyncio.TimeoutError()
                current_count = len(stdout_lines)
                has_new_output = current_count > last_line_count
                has_keywords = False
                if stdout_lines:
                    recent = stdout_lines[-1].lower()
                    has_keywords = any(kw in recent for kw in _GRACE_KEYWORDS)
                grace_budget = _MAX_GRACE_TOTAL - grace_used
                if has_keywords:
                    extension = min(_GRACE_KEYWORD, grace_budget)
                    remaining = extension
                    grace_used += extension
                    last_line_count = current_count
                    in_grace = True
                elif has_new_output:
                    extension = min(_GRACE_OUTPUT, grace_budget)
                    remaining = extension
                    grace_used += extension
                    last_line_count = current_count
                    in_grace = True
                else:
                    raise asyncio.TimeoutError()
            if on_progress is not None:
                latest = stdout_lines[-1] if stdout_lines else ""
                suffix = " (grace period)" if in_grace else ""
                await on_progress(elapsed, latest + suffix)
    except BaseException:
        proc.kill()
        await proc.wait()
        wait_task.cancel()
        stdout_task.cancel()
        stderr_task.cancel()
        cleanup: list[asyncio.Task[object]] = [wait_task, stdout_task, stderr_task]
        if stdin_task is not None:
            stdin_task.cancel()
            cleanup.append(stdin_task)
        for t in _output_tasks:
            t.cancel()
            cleanup.append(t)
        await asyncio.gather(*cleanup, return_exceptions=True)
        raise

    if stdin_task is not None:
        await stdin_task
    stdout_lines, stderr = await asyncio.gather(stdout_task, stderr_task)
    # Wait for fire-and-forget output callbacks to finish (best-effort)
    if _output_tasks:
        await asyncio.gather(*_output_tasks, return_exceptions=True)
    return ProcessResult(
        returncode=proc.returncode if proc.returncode is not None else -1,
        stdout_lines=stdout_lines,
        stderr=stderr,
    )
