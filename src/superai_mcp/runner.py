"""Async subprocess runner for CLI tools."""

import asyncio
from dataclasses import dataclass, field
from pathlib import Path


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
    timeout: float = 300.0,
) -> ProcessResult:
    """Run a CLI command asynchronously and capture output.

    Raises asyncio.TimeoutError if the process exceeds `timeout` seconds.
    """
    proc = await asyncio.create_subprocess_exec(
        command,
        *args,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=cwd,
        env=env,
    )

    if proc.stdout is None or proc.stderr is None:
        raise RuntimeError("Failed to capture subprocess pipes")

    async def drain_lines(stream: asyncio.StreamReader) -> list[str]:
        lines: list[str] = []
        while True:
            raw = await stream.readline()
            if not raw:
                break
            lines.append(raw.decode("utf-8", errors="replace").rstrip("\r\n"))
        return lines

    async def drain_all(stream: asyncio.StreamReader) -> str:
        data = await stream.read()
        return data.decode("utf-8", errors="replace")

    stdout_task = asyncio.create_task(drain_lines(proc.stdout))
    stderr_task = asyncio.create_task(drain_all(proc.stderr))

    try:
        await asyncio.wait_for(proc.wait(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        stdout_task.cancel()
        stderr_task.cancel()
        await asyncio.gather(stdout_task, stderr_task, return_exceptions=True)
        raise

    stdout_lines, stderr = await asyncio.gather(stdout_task, stderr_task)
    return ProcessResult(
        returncode=proc.returncode if proc.returncode is not None else -1,
        stdout_lines=stdout_lines,
        stderr=stderr,
    )
