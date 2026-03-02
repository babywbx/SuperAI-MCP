"""Auto-split orchestration: decompose a large task into subtasks and execute sequentially."""

import json
import re
from collections.abc import Awaitable, Callable

from pydantic import BaseModel

from superai_mcp.models import CLIResult

# Internal constants
_MAX_SUBTASKS = 5
_PHASE1_TIMEOUT = 120.0
_AUTO_SPLIT_TIMEOUT = 900.0

_DECOMPOSE_TEMPLATE = """\
Break down the following task into {max_subtasks} or fewer independent subtasks.
Output ONLY a JSON array inside a ```json fenced code block. Each element must have:
- "id": integer starting from 1
- "title": short title
- "prompt": the full prompt to execute this subtask

```json
[{{"id": 1, "title": "...", "prompt": "..."}}]
```

Task:
{prompt}"""

# Type aliases for CLI call functions
type SingleCallFn = Callable[[str, float], Awaitable[CLIResult]]
type ResumeCallFn = Callable[[str, str, float], Awaitable[CLIResult]]


class Subtask(BaseModel):
    """A single decomposed subtask."""

    id: int
    title: str
    prompt: str


class SubtaskResult(BaseModel):
    """Result from executing one subtask."""

    subtask_id: int
    title: str
    success: bool
    content: str
    usage: dict[str, object] | None = None


def extract_subtasks(content: str) -> list[Subtask]:
    """Extract subtask list from Phase 1 output.

    Tries fenced ```json block first, then falls back to raw JSON detection.
    Raises ValueError if parsing fails or result is empty.
    """
    raw_json: str | None = None

    # Try ```json ... ``` fenced block
    m = re.search(r"```json\s*\n(.*?)```", content, re.DOTALL)
    if m:
        raw_json = m.group(1).strip()

    # Fallback: find outermost [ ... ]
    if raw_json is None:
        start = content.find("[")
        end = content.rfind("]")
        if start != -1 and end > start:
            raw_json = content[start : end + 1]

    if raw_json is None:
        raise ValueError("No JSON array found in decomposition output")

    data: object = json.loads(raw_json)
    if not isinstance(data, list) or len(data) == 0:
        raise ValueError("Decomposition output is not a non-empty JSON array")

    subtasks = [Subtask.model_validate(item) for item in data[: _MAX_SUBTASKS]]
    return subtasks


def merge_usage(usages: list[dict[str, object] | None]) -> dict[str, object] | None:
    """Merge multiple usage dicts by summing numeric fields."""
    merged: dict[str, object] = {}
    has_any = False

    for u in usages:
        if u is None:
            continue
        has_any = True
        for k, v in u.items():
            existing = merged.get(k)
            if isinstance(v, (int, float)) and isinstance(existing, (int, float)):
                merged[k] = existing + v
            elif isinstance(v, (int, float)) and existing is None:
                merged[k] = v
            else:
                # Non-numeric: last-write-wins
                merged[k] = v

    return merged if has_any else None


def format_aggregated_content(results: list[SubtaskResult]) -> str:
    """Format aggregated content from multiple subtask results."""
    parts: list[str] = []
    for r in results:
        tag = "OK" if r.success else "FAILED"
        parts.append(f"## Subtask {r.subtask_id}: {r.title} [{tag}]\n\n{r.content}")
    return "\n\n---\n\n".join(parts)


async def run_auto_split(
    prompt: str,
    *,
    call_fn: SingleCallFn,
    resume_fn: ResumeCallFn | None = None,
    total_timeout: float = _AUTO_SPLIT_TIMEOUT,
) -> CLIResult:
    """Orchestrate auto-split: decompose then execute subtasks sequentially.

    Args:
        prompt: The original task prompt.
        call_fn: Async function(prompt, timeout) -> CLIResult for new calls.
        resume_fn: Optional async function(prompt, session_id, timeout) -> CLIResult
                   for resuming sessions. If None, each subtask uses call_fn independently.
        total_timeout: Total time budget in seconds.

    Returns:
        CLIResult with aggregated content from all subtasks.
    """
    import time

    deadline = time.monotonic() + total_timeout

    def remaining() -> float:
        return max(0.0, deadline - time.monotonic())

    # Phase 1: Decompose
    decompose_prompt = _DECOMPOSE_TEMPLATE.format(
        max_subtasks=_MAX_SUBTASKS,
        prompt=prompt,
    )
    phase1_timeout = min(_PHASE1_TIMEOUT, remaining())

    try:
        phase1_result = await call_fn(decompose_prompt, phase1_timeout)
        subtasks = extract_subtasks(phase1_result.content)
    except Exception:
        # Fallback: execute original prompt directly
        fallback_result = await call_fn(prompt, remaining())
        return fallback_result

    # Phase 2: Execute subtasks sequentially
    session_id: str | None = phase1_result.session_id
    results: list[SubtaskResult] = []
    usages: list[dict[str, object] | None] = [phase1_result.usage]

    for subtask in subtasks:
        time_left = remaining()
        if time_left <= 0:
            results.append(SubtaskResult(
                subtask_id=subtask.id,
                title=subtask.title,
                success=False,
                content="Skipped: no time remaining",
            ))
            continue

        try:
            if resume_fn is not None and session_id:
                result = await resume_fn(subtask.prompt, session_id, time_left)
            else:
                result = await call_fn(subtask.prompt, time_left)

            # Update session_id for next resume
            if result.session_id:
                session_id = result.session_id

            results.append(SubtaskResult(
                subtask_id=subtask.id,
                title=subtask.title,
                success=result.success,
                content=result.content,
                usage=result.usage,
            ))
            usages.append(result.usage)

        except Exception as exc:
            results.append(SubtaskResult(
                subtask_id=subtask.id,
                title=subtask.title,
                success=False,
                content=f"Error: {exc}",
            ))

    all_success = all(r.success for r in results)
    return CLIResult(
        success=all_success,
        session_id=session_id,
        content=format_aggregated_content(results),
        model=phase1_result.model,
        usage=merge_usage(usages),
    )
