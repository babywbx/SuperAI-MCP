"""Input validation for all tool parameters."""

import re
from pathlib import Path

from superai_mcp.models import Sandbox

# session_id: UUID-like hex with dashes
_SESSION_RE = re.compile(r"^[0-9a-f]{8}(-[0-9a-f]{4,}){1,5}$", re.I)

# model: alphanumeric with dots, dashes, slashes (e.g. "gpt-5.3-codex", "gemini-3.1-pro")
_MODEL_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._/-]{0,127}$")

_VALID_EFFORT = frozenset({"low", "medium", "high", "xhigh"})
_VALID_CLAUDE_EFFORT = frozenset({"low", "medium", "high"})

_COMMIT_RE = re.compile(r"^[0-9a-fA-F]{7,40}$")

MAX_FILES = 50
MAX_FILE_BYTES = 2 * 1024 * 1024  # 2 MB per file


def validate_cd(cd: str) -> Path:
    """Validate cd is an existing directory."""
    p = Path(cd).resolve()
    if not p.is_dir():
        raise ValueError("cd is not a valid directory")
    return p


def validate_sandbox(sandbox: str) -> Sandbox:
    """Enforce sandbox must be a valid Sandbox enum value."""
    try:
        return Sandbox(sandbox)
    except ValueError:
        valid = [s.value for s in Sandbox]
        raise ValueError(f"invalid sandbox: {sandbox!r}, must be one of {valid}")


def validate_session_id(session_id: str) -> str:
    """Validate session_id looks like a UUID."""
    if session_id and not _SESSION_RE.match(session_id):
        raise ValueError("invalid session_id format")
    return session_id


def validate_model(model: str) -> str:
    """Validate model name characters."""
    if model and not _MODEL_RE.match(model):
        raise ValueError(f"invalid model name: {model!r}")
    return model


def validate_reasoning_effort(effort: str) -> str:
    """Validate reasoning_effort is one of the allowed values."""
    if effort and effort not in _VALID_EFFORT:
        raise ValueError(f"invalid reasoning_effort: {effort!r}, must be one of {sorted(_VALID_EFFORT)}")
    return effort


def validate_effort(effort: str) -> str:
    """Validate effort level for Claude CLI."""
    if effort and effort not in _VALID_CLAUDE_EFFORT:
        raise ValueError(f"invalid effort: {effort!r}, must be one of {sorted(_VALID_CLAUDE_EFFORT)}")
    return effort


def validate_max_budget(budget: float) -> float:
    """Validate max_budget_usd is non-negative."""
    if budget < 0:
        raise ValueError(f"invalid max_budget_usd: {budget}, must be >= 0")
    return budget


def validate_commit_sha(sha: str) -> str:
    """Validate commit SHA format (7-40 hex characters)."""
    if sha and not _COMMIT_RE.match(sha):
        raise ValueError(f"invalid commit SHA: {sha!r}")
    return sha


def validate_files(files: list[str] | None) -> list[str] | None:
    """Validate file list size."""
    if files and len(files) > MAX_FILES:
        raise ValueError(f"too many files: {len(files)} > {MAX_FILES}")
    return files
