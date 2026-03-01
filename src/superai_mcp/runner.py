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
    timeout: float = 300.0,
) -> ProcessResult:
    """Run a CLI command asynchronously and capture output.

    Raises asyncio.TimeoutError if the process exceeds `timeout` seconds.
    """
    proc = await asyncio.create_subprocess_exec(
        command,
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=cwd,
    )

    assert proc.stdout is not None
    assert proc.stderr is not None

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
        raise

    stdout_lines, stderr = await asyncio.gather(stdout_task, stderr_task)
    return ProcessResult(
        returncode=proc.returncode or 0,
        stdout_lines=stdout_lines,
        stderr=stderr,
    )
