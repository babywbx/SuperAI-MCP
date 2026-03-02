"""Shared data models for CLI tool wrappers."""

from enum import StrEnum

from pydantic import BaseModel


class Sandbox(StrEnum):
    """Codex sandbox modes."""

    READ_ONLY = "read-only"
    WORKSPACE_WRITE = "workspace-write"
    DANGER_FULL_ACCESS = "danger-full-access"


class CLIResult(BaseModel):
    """Unified result from any CLI invocation."""

    success: bool
    session_id: str | None = None
    content: str
    model: str | None = None
    all_messages: list[dict[str, object]] | None = None
    usage: dict[str, object] | None = None
