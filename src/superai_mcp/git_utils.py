"""Git diff and file reading helpers."""

from pathlib import Path

from superai_mcp.runner import run_cli


async def get_git_diff(
    cd: str,
    *,
    uncommitted: bool = False,
    base: str = "",
) -> str:
    """Get git diff output.

    - uncommitted: diff of unstaged + staged changes
    - base: diff relative to a branch (e.g. "main")
    """
    args: list[str] = ["diff"]
    if uncommitted:
        args.append("HEAD")
    elif base:
        args.extend([f"{base}...HEAD"])
    else:
        return ""

    result = await run_cli("git", args, cwd=cd, timeout=30.0)
    if result.returncode != 0:
        return f"(git diff failed: {result.stderr.strip()})"
    return "\n".join(result.stdout_lines)


def read_files(paths: list[str], cd: str) -> str:
    """Read file contents and format for prompt injection."""
    root = Path(cd)
    parts: list[str] = []
    for rel in paths:
        fp = root / rel
        if not fp.is_file():
            parts.append(f"--- {rel} ---\n(file not found)")
            continue
        try:
            content = fp.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            parts.append(f"--- {rel} ---\n(read error: {e})")
            continue
        parts.append(f"--- {rel} ---\n{content}")
    return "\n\n".join(parts)
