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


def _extract_error_message(event: JsonObject) -> str:
    """Extract error message from an error event."""
    # Direct message field (type: "error")
    msg = event.get("message", "")
    if isinstance(msg, str) and msg:
        return msg
    # Nested error object (type: "turn.failed")
    err = event.get("error")
    if isinstance(err, dict):
        inner = err.get("message", "")
        if isinstance(inner, str) and inner:
            return inner
    return ""


def parse_codex_output(
    lines: list[str],
    *,
    return_all: bool = False,
) -> CLIResult:
    """Parse Codex `--json` JSONL output into CLIResult.

    Event types handled:
      thread.started  -> session_id
      item.completed  -> agent_message text (reasoning items are skipped)
      turn.completed  -> usage stats
      error           -> CLI errors (auth, network, reconnect)
      turn.failed     -> terminal failure with error details
    """
    session_id: str | None = None
    texts: list[str] = []
    errors: list[str] = []
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
            if isinstance(item, dict):
                itype = item.get("type")
                if itype == "agent_message":
                    text = item.get("text", "")
                    if isinstance(text, str) and text:
                        texts.append(text)
                elif itype == "error":
                    emsg = item.get("message", "")
                    if isinstance(emsg, str) and emsg:
                        errors.append(emsg)

        elif etype == "turn.completed":
            raw_usage = event.get("usage")
            if isinstance(raw_usage, dict):
                usage = raw_usage

        elif etype == "error":
            msg = _extract_error_message(event)
            # Skip reconnect attempts, only keep final errors
            if msg and "Reconnecting..." not in msg:
                errors.append(msg)

        elif etype == "turn.failed":
            msg = _extract_error_message(event)
            if msg:
                errors.append(msg)

    content = "\n\n".join(texts)
    if content:
        return CLIResult(
            success=True,
            session_id=session_id,
            content=content,
            all_messages=all_events if return_all else None,
            usage=usage,
        )

    # No agent output — report errors if any
    error_text = "\n".join(errors) if errors else "(no output)"
    return CLIResult(
        success=False,
        session_id=session_id,
        content=error_text,
        all_messages=all_events if return_all else None,
        usage=usage,
    )


def parse_gemini_output(
    lines: list[str],
    *,
    return_all: bool = False,
) -> CLIResult:
    """Parse Gemini `-o stream-json` output into CLIResult.

    Event types handled:
      init     -> session_id, model
      message  -> assistant content (delta)
      result   -> stats, status

    Also captures non-JSON lines as plain text errors
    (e.g. "Please set an Auth method" when gemini is not configured).
    """
    session_id: str | None = None
    chunks: list[str] = []
    plain_lines: list[str] = []
    usage: dict[str, object] | None = None
    success = False
    all_events: list[dict[str, object]] = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        event = _parse_json_object(stripped)
        if event is None:
            # Non-JSON output — likely a CLI error message
            plain_lines.append(stripped)
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
    if content:
        return CLIResult(
            success=success,
            session_id=session_id,
            content=content,
            all_messages=all_events if return_all else None,
            usage=usage,
        )

    # No assistant output — report plain text errors or "(no output)"
    error_text = "\n".join(plain_lines) if plain_lines else "(no output)"
    return CLIResult(
        success=False,
        session_id=session_id,
        content=error_text,
        all_messages=all_events if return_all else None,
        usage=usage,
    )
