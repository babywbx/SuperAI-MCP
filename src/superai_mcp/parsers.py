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


def parse_claude_output(
    lines: list[str],
    *,
    return_all: bool = False,
) -> CLIResult:
    """Parse Claude `--output-format json` output into CLIResult.

    Claude outputs a single JSON object (possibly multi-line) with fields:
      session_id, usage, result
    Non-JSON lines before the JSON block are captured as error text.
    """
    plain_lines: list[str] = []
    json_lines: list[str] = []
    in_json = False

    for line in lines:
        stripped = line.strip()
        if not stripped and not in_json:
            continue
        if not in_json and stripped.startswith("{"):
            in_json = True
        if in_json:
            json_lines.append(line)
        else:
            plain_lines.append(stripped)

    if json_lines:
        blob = "\n".join(json_lines)
        data = _parse_json_object(blob)
        if data is not None:
            content = data.get("result", "")
            if not isinstance(content, str):
                content = ""
            session_id = data.get("session_id")
            if session_id is not None:
                session_id = str(session_id)
            usage = data.get("usage")
            if not isinstance(usage, dict):
                usage = None
            raw_model = data.get("model")
            model = str(raw_model) if isinstance(raw_model, str) and raw_model else None
            return CLIResult(
                success=bool(content),
                session_id=session_id,
                content=content or "(no output)",
                model=model,
                all_messages=[data] if return_all else None,
                usage=usage,
            )

    # No valid JSON — report plain text errors
    error_text = "\n".join(plain_lines) if plain_lines else "(no output)"
    return CLIResult(
        success=False,
        session_id=None,
        content=error_text,
    )


def parse_claude_stream_output(
    lines: list[str],
    *,
    return_all: bool = False,
) -> CLIResult:
    """Parse Claude `--output-format stream-json` NDJSON output into CLIResult.

    Event types handled:
      system (subtype: init) -> session_id, model
      assistant               -> message.content[].text
      tool_use / tool_result  -> clear accumulated chunks (keep final answer only)
      result                  -> final answer, usage, model (highest priority)

    Non-JSON lines are captured as error text.
    """
    session_id: str | None = None
    model: str | None = None
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
            plain_lines.append(stripped)
            continue

        if return_all:
            all_events.append(event)

        etype = event.get("type")

        if etype == "system":
            subtype = event.get("subtype")
            if subtype == "init":
                sid = event.get("session_id")
                session_id = str(sid) if sid else None
                raw_model = event.get("model")
                if isinstance(raw_model, str) and raw_model:
                    model = raw_model

        elif etype == "assistant":
            msg = event.get("message")
            if isinstance(msg, dict):
                content_blocks = msg.get("content", [])
                if isinstance(content_blocks, list):
                    for block in content_blocks:
                        if isinstance(block, dict) and block.get("type") == "text":
                            text = block.get("text", "")
                            if isinstance(text, str) and text:
                                chunks.append(text)

        elif etype in ("tool_use", "tool_result"):
            if not return_all:
                chunks.clear()

        elif etype == "result":
            subtype = event.get("subtype")
            success = subtype == "success"
            # result.result is the authoritative final answer
            result_text = event.get("result")
            if isinstance(result_text, str) and result_text:
                chunks.clear()
                chunks.append(result_text)
            raw_usage = event.get("usage")
            if isinstance(raw_usage, dict):
                usage = raw_usage
            # Model from result event has highest priority
            raw_model = event.get("model")
            if isinstance(raw_model, str) and raw_model:
                model = raw_model

    content = "".join(chunks)
    if content:
        return CLIResult(
            success=success,
            session_id=session_id,
            content=content,
            model=model,
            all_messages=all_events if return_all else None,
            usage=usage,
        )

    # No assistant output — report plain text errors or "(no output)"
    error_text = "\n".join(plain_lines) if plain_lines else "(no output)"
    return CLIResult(
        success=False,
        session_id=session_id,
        content=error_text,
        model=model,
        all_messages=all_events if return_all else None,
        usage=usage,
    )


_RATE_LIMIT_PATTERNS = (
    "RESOURCE_EXHAUSTED",   # Gemini
    "overloaded_error",     # Claude
    "rate_limit",           # Claude / Codex
    "429",                  # HTTP 429 Too Many Requests
    "too many requests",    # generic
    "quota",                # generic
)


def is_rate_limited(result: CLIResult) -> bool:
    """Check if result indicates a rate limit or quota error."""
    if result.success:
        return False
    lower = result.content.lower()
    return any(p.lower() in lower for p in _RATE_LIMIT_PATTERNS)


# Backward-compatible alias
is_quota_exhausted = is_rate_limited


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
    model: str | None = None
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
            raw_model = event.get("model")
            if isinstance(raw_model, str) and raw_model:
                model = raw_model

        elif etype == "message":
            if event.get("role") == "assistant":
                content = event.get("content", "")
                if isinstance(content, str) and content:
                    chunks.append(content)

        elif etype in ("tool_call", "tool_use", "tool_result"):
            # Discard intermediate text before tool use;
            # only keep the final answer after all tool cycles.
            if not return_all:
                chunks.clear()

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
            model=model,
            all_messages=all_events if return_all else None,
            usage=usage,
        )

    # No assistant output — report plain text errors or "(no output)"
    error_text = "\n".join(plain_lines) if plain_lines else "(no output)"
    return CLIResult(
        success=False,
        session_id=session_id,
        content=error_text,
        model=model,
        all_messages=all_events if return_all else None,
        usage=usage,
    )
