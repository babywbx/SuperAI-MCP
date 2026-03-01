"""Parsers for Codex JSONL and Gemini stream-json output."""

import json
from typing import TypeAlias

from superai_mcp.models import CLIResult

JsonObject: TypeAlias = dict[str, object]


def _parse_json_object(line: str) -> JsonObject | None:
    """Parse a JSON line, returning dict or None for non-object/invalid."""
    try:
        data: object = json.loads(line)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    return data


def parse_codex_output(
    lines: list[str],
    *,
    return_all: bool = False,
) -> CLIResult:
    """Parse Codex `--json` JSONL output into CLIResult.

    Event types:
      thread.started  -> session_id
      item.completed  -> agent_message text (reasoning items are skipped)
      turn.completed  -> usage stats
    """
    session_id: str | None = None
    texts: list[str] = []
    usage: dict[str, object] | None = None
    all_events: list[dict[str, object]] = []

    for line in lines:
        if not line.strip():
            continue
        event = _parse_json_object(line)
        if event is None:
            continue

        if return_all:
            all_events.append(event)

        etype = event.get("type")

        if etype == "thread.started":
            tid = event.get("thread_id")
            session_id = str(tid) if tid else None

        elif etype == "item.completed":
            item = event.get("item")
            if isinstance(item, dict) and item.get("type") == "agent_message":
                text = item.get("text", "")
                if isinstance(text, str) and text:
                    texts.append(text)

        elif etype == "turn.completed":
            raw_usage = event.get("usage")
            if isinstance(raw_usage, dict):
                usage = raw_usage

    content = "\n\n".join(texts)
    return CLIResult(
        success=bool(content),
        session_id=session_id,
        content=content or "(no output)",
        all_messages=all_events if return_all else None,
        usage=usage,
    )


def parse_gemini_output(
    lines: list[str],
    *,
    return_all: bool = False,
) -> CLIResult:
    """Parse Gemini `-o stream-json` output into CLIResult.

    Event types:
      init     -> session_id, model
      message  -> assistant content (delta)
      result   -> stats, status
    """
    session_id: str | None = None
    chunks: list[str] = []
    usage: dict[str, object] | None = None
    success = False
    all_events: list[dict[str, object]] = []

    for line in lines:
        if not line.strip():
            continue
        event = _parse_json_object(line)
        if event is None:
            continue

        if return_all:
            all_events.append(event)

        etype = event.get("type")

        if etype == "init":
            sid = event.get("session_id")
            session_id = str(sid) if sid else None

        elif etype == "message":
            if event.get("role") == "assistant":
                content = event.get("content", "")
                if isinstance(content, str) and content:
                    chunks.append(content)

        elif etype == "result":
            success = event.get("status") == "success"
            stats = event.get("stats")
            if isinstance(stats, dict):
                usage = stats

    content = "".join(chunks)
    return CLIResult(
        success=success,
        session_id=session_id,
        content=content or "(no output)",
        all_messages=all_events if return_all else None,
        usage=usage,
    )
