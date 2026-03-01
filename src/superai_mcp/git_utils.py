"""Git diff and file reading helpers."""

import re
from pathlib import Path

from superai_mcp.runner import run_cli

# Only allow safe git refnames (no leading dash, no .., no special chars)
_SAFE_REF = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_./-]*$")


def _validate_ref(ref: str) -> str:
    """Validate a git ref to prevent option injection."""
    if not _SAFE_REF.match(ref):
        raise ValueError(f"invalid git ref: {ref!r}")
    if ".." in ref:
        raise ValueError(f"'..' not allowed in git ref: {ref!r}")
    return ref


async def get_git_diff(
    cd: str,
    *,
    uncommitted: bool = False,
    base: str = "",
) -> str:
    """Get git diff output.

    - uncommitted: diff of unstaged + staged changes
    - base: diff relative to a branch (e.g. "main")

    Raises ValueError if both uncommitted and base are set.
    """
    if uncommitted and base:
        raise ValueError("review_uncommitted and review_base are mutually exclusive")

    args: list[str] = ["diff"]
    if uncommitted:
        args.append("HEAD")
    elif base:
        _validate_ref(base)
        args.append(f"{base}...HEAD")
    else:
        return ""

    result = await run_cli("git", args, cwd=cd, timeout=30.0)
    if result.returncode != 0:
        return f"(git diff failed: {result.stderr.strip()})"
    return "\n".join(result.stdout_lines)


def read_files(paths: list[str], cd: str) -> str:
    """Read file contents, enforcing path containment within cd."""
    root = Path(cd).resolve()
    parts: list[str] = []
    for rel in paths:
        # Reject absolute paths
        if Path(rel).is_absolute():
            parts.append(f"--- {rel} ---\n(rejected: absolute path)")
            continue

        target = (root / rel).resolve()

        # Enforce containment (is_relative_to is prefix-safe unlike startswith)
        if not target.is_relative_to(root):
            parts.append(f"--- {rel} ---\n(rejected: path traversal)")
            continue

        if not target.is_file():
            parts.append(f"--- {rel} ---\n(file not found)")
            continue
        try:
            content = target.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            parts.append(f"--- {rel} ---\n(read error: {e})")
            continue
        parts.append(f"--- {rel} ---\n{content}")
    return "\n\n".join(parts)
