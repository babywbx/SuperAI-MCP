"""FastMCP server with Codex, Gemini, Claude, and broadcast tool registration."""

import asyncio
import json
import os
import shutil

from collections.abc import Awaitable, Callable

from mcp.server.fastmcp import Context, FastMCP
from mcp.types import ToolAnnotations

from superai_mcp.git_utils import get_git_diff, read_files
from superai_mcp.openrouter import check_model, fetch_models
from superai_mcp.models import CLIResult, Sandbox
from superai_mcp.parsers import (
    is_rate_limited,
    parse_claude_output,
    parse_codex_output,
    parse_gemini_output,
)
from superai_mcp.runner import run_cli
from superai_mcp.splitter import run_auto_split
from superai_mcp.validate import (
    validate_cd,
    validate_commit_sha,
    validate_effort,
    validate_files,
    validate_max_budget,
    validate_model,
    validate_reasoning_effort,
    validate_sandbox,
    validate_session_id,
    validate_timeout,
)

mcp = FastMCP("super")

# Max stderr chars to include in error responses
_MAX_STDERR = 500

# Fallback chains for rate-limit cascade degradation
_CLAUDE_FALLBACK_CHAIN = ("sonnet", "haiku")
_CODEX_EFFORT_CHAIN = ("high", "medium", "low")

# Short probe prompt to verify a fallback model/config is reachable
_PROBE_PROMPT = "reply ok"
_PROBE_TIMEOUT = 30.0

# Timeout for status tool CLI probes
_STATUS_TIMEOUT = 15.0

# Prompt size threshold for switching from CLI arg to stdin piping.
# Well under macOS ARG_MAX (~1MB) to leave room for env vars and other args.
_STDIN_THRESHOLD = 200_000  # bytes

# Nesting depth control to prevent recursive fork bombs.
_MAX_DEPTH = 5
_DEPTH_ENV = "SUPERAI_MCP_DEPTH"


def _get_depth(env: dict[str, str] | None = None) -> int:
    """Get current nesting depth from environment."""
    source = env if env is not None else os.environ
    try:
        val = int(source.get(_DEPTH_ENV, "0"))
        return max(0, val)  # clamp negatives to 0
    except (ValueError, TypeError):
        return 0


def _child_env(base: dict[str, str] | None = None) -> dict[str, str]:
    """Build child process env with incremented nesting depth."""
    env = dict(base if base is not None else os.environ)
    env[_DEPTH_ENV] = str(_get_depth(env) + 1)
    return env

# Cumulative usage tracking (in-memory only, resets on process restart)
_usage: dict[str, dict[str, int]] = {}


def _reset_usage() -> None:
    """Reset all usage counters."""
    for cli in ("codex", "gemini", "claude"):
        _usage[cli] = {"calls": 0, "input_tokens": 0, "output_tokens": 0}


# Initialize on module load
_reset_usage()


def _track_usage(cli: str, usage: dict[str, object] | None) -> None:
    """Accumulate usage stats for a CLI tool."""
    if cli not in _usage:
        return
    _usage[cli]["calls"] += 1
    if usage is None:
        return
    for key in ("input_tokens", "output_tokens"):
        val = usage.get(key)
        if isinstance(val, (int, float)):
            _usage[cli][key] += int(val)


def _gemini_prompt_args(prompt: str) -> tuple[list[str], bytes | None]:
    """Build Gemini prompt args; large prompts go via stdin.

    Gemini CLI: ``-p ""`` triggers non-interactive mode; stdin content is
    prepended (docs: "Appended to input on stdin if any").
    """
    encoded = prompt.encode("utf-8")
    if len(encoded) > _STDIN_THRESHOLD:
        return ["-p", ""], encoded
    return ["-p", prompt], None


def _codex_prompt_args(prompt: str) -> tuple[list[str], bytes | None]:
    """Build Codex prompt args; large prompts go via stdin."""
    encoded = prompt.encode("utf-8")
    if len(encoded) > _STDIN_THRESHOLD:
        return ["--", "-"], encoded
    return ["--", prompt], None


def _codex_resume_prompt_args(session_id: str, prompt: str) -> tuple[list[str], bytes | None]:
    """Build Codex resume prompt args; large prompts go via stdin."""
    encoded = prompt.encode("utf-8")
    if len(encoded) > _STDIN_THRESHOLD:
        return ["--", session_id, "-"], encoded
    return ["--", session_id, prompt], None


def _claude_prompt_args(prompt: str) -> tuple[list[str], bytes | None]:
    """Build Claude prompt args; large prompts go via stdin."""
    encoded = prompt.encode("utf-8")
    if len(encoded) > _STDIN_THRESHOLD:
        return ["-p"], encoded
    return ["-p", prompt], None


def _err(msg: str) -> str:
    """Return a JSON error response."""
    return CLIResult(success=False, content=msg).model_dump_json(exclude_none=True)


def _safe_stderr(stderr: str) -> str:
    """Truncate stderr to avoid leaking sensitive info."""
    s = stderr.strip()
    return s[:_MAX_STDERR] if len(s) > _MAX_STDERR else s


_MAX_SNIPPET = 80


def _summarize_line(line: str) -> str:
    """Extract a human-readable snippet from a CLI JSON output line."""
    if not line:
        return ""

    try:
        obj = json.loads(line)
    except (json.JSONDecodeError, ValueError):
        # Non-JSON (e.g. Claude progress text) — return raw truncated
        return line[:_MAX_SNIPPET]

    if not isinstance(obj, dict):
        return line[:_MAX_SNIPPET]

    # Codex JSONL events
    event_type = obj.get("type", "")
    if event_type in ("turn.started", "turn.completed", "turn.failed"):
        msg = event_type
        if event_type == "turn.failed":
            err = obj.get("error", {})
            if isinstance(err, dict) and err.get("message"):
                msg = f"{event_type}: {err['message']}"
        return msg[:_MAX_SNIPPET]

    if event_type == "error":
        err_msg = obj.get("message", "") or obj.get("error", "")
        return f"error: {err_msg}"[:_MAX_SNIPPET]

    if event_type == "thread.started":
        return "thread.started"

    if event_type == "item.completed":
        item = obj.get("item", {})
        if isinstance(item, dict):
            item_type = item.get("type", "")
            if item_type == "error":
                emsg = item.get("message", "")
                return f"error: {emsg}"[:_MAX_SNIPPET] if emsg else "error"
            text = item.get("text", "")
            if item_type == "reasoning" and text:
                return f"reasoning: {text}"[:_MAX_SNIPPET]
            if item_type in ("agent_message", "message") and text:
                return f"message: {text}"[:_MAX_SNIPPET]
        return event_type[:_MAX_SNIPPET]

    # Gemini stream-json events
    if "role" in obj and obj.get("role") == "assistant":
        content = obj.get("content", "")
        if content:
            return f"assistant: {content}"[:_MAX_SNIPPET]

    if event_type == "init":
        model_name = obj.get("model", "")
        return f"init: {model_name}"[:_MAX_SNIPPET] if model_name else "init"

    if event_type == "result":
        status = obj.get("status", "")
        return f"result: {status}"[:_MAX_SNIPPET] if status else "result"

    # Fallback: raw truncated
    return line[:_MAX_SNIPPET]


def _make_progress_cb(
    ctx: Context | None,
    tool_name: str,
    timeout: float,
) -> Callable[[float, str], Awaitable[None]] | None:
    """Build an on_progress callback for run_cli, or None if ctx is unavailable."""
    if ctx is None:
        return None

    async def _cb(elapsed: float, latest_line: str) -> None:
        remaining = timeout - elapsed
        msg = f"{tool_name} [timeout in {remaining:.0f}s]"
        snippet = _summarize_line(latest_line)
        if snippet:
            msg = f"{msg} {snippet}"
        await ctx.report_progress(elapsed, timeout, msg)

    return _cb


async def _build_context(
    prompt: str,
    *,
    cd: str,
    review_uncommitted: bool,
    review_base: str,
    review_commit: str = "",
    files: list[str] | None,
    system_prompt: str = "",
) -> str:
    """Build prompt with optional diff/file context."""
    parts: list[str] = []

    if system_prompt:
        parts.append(f"<system>{system_prompt}</system>")

    if review_uncommitted or review_base or review_commit:
        diff_text = await get_git_diff(
            cd, uncommitted=review_uncommitted, base=review_base, commit=review_commit,
        )
        if diff_text:
            if review_uncommitted:
                label = "uncommitted changes"
            elif review_base:
                label = f"changes vs {review_base}"
            else:
                label = f"commit {review_commit}"
            parts.append(f"Below is the git diff ({label}):\n\n```diff\n{diff_text}\n```")

    if files:
        parts.append(f"Below are the file contents:\n\n{read_files(files, cd)}")

    parts.append(prompt)
    return "\n\n".join(parts)


@mcp.tool(name="codex", annotations=ToolAnnotations(
    readOnlyHint=False, destructiveHint=False, idempotentHint=False,
))
async def codex_tool(
    prompt: str,
    cd: str,
    ctx: Context | None = None,
    session_id: str = "",
    sandbox: str = Sandbox.READ_ONLY,
    model: str = "",
    reasoning_effort: str = "",
    review_uncommitted: bool = False,
    review_base: str = "",
    review_commit: str = "",
    files: list[str] | None = None,
    return_all_messages: bool = False,
    auto_split: bool = False,
    system_prompt: str = "",
    timeout: float = 300.0,
) -> str:
    """Run Codex CLI for coding tasks, code review, or general prompts.

    Modes:
      - Default: forward prompt to Codex
      - Review: set review_uncommitted=True or review_base="main"
      - Files: pass files=["a.py"] to include file contents
      - Resume: pass session_id from a previous call
    """
    try:
        depth = _get_depth()
        if depth >= _MAX_DEPTH:
            return _err(f"nesting depth {depth} reached limit {_MAX_DEPTH}")

        if not shutil.which("codex"):
            return _err("codex CLI not found in PATH")

        # Validate all inputs
        validate_cd(cd)
        validated_sandbox = validate_sandbox(sandbox)
        validate_session_id(session_id)
        validate_model(model)
        validate_reasoning_effort(reasoning_effort)
        validate_commit_sha(review_commit)
        validate_files(files)
        validate_timeout(timeout)

        env = _child_env()

        # Advisory only — don't block, append hint if CLI fails later
        model_warning = await check_model(model, "codex")

        if auto_split and session_id:
            return _err("auto_split and session_id are mutually exclusive")

        if validated_sandbox == Sandbox.DANGER_FULL_ACCESS:
            if not os.environ.get("SUPERAI_ALLOW_DANGEROUS"):
                return _err(
                    "danger-full-access is disabled by default. "
                    "Set SUPERAI_ALLOW_DANGEROUS=1 to enable."
                )

        effective_prompt = await _build_context(
            prompt, cd=cd,
            review_uncommitted=review_uncommitted,
            review_base=review_base,
            review_commit=review_commit,
            files=files,
            system_prompt=system_prompt,
        )

        if auto_split:
            async def _call(p: str, timeout: float) -> CLIResult:
                prompt_args, stdin_data = _codex_prompt_args(p)
                a = [
                    "exec", "--json",
                    "--sandbox", validated_sandbox.value,
                    "--cd", cd,
                    "--skip-git-repo-check",
                ]
                if model:
                    a.extend(["-m", model])
                if reasoning_effort:
                    a.extend(["-c", f"model_reasoning_effort={reasoning_effort}"])
                a.extend(prompt_args)
                r = await run_cli(
                    "codex", a, cwd=cd, env=env, stdin_data=stdin_data,
                    timeout=timeout,
                    on_progress=_make_progress_cb(ctx, "codex", timeout),
                )
                parsed = parse_codex_output(r.stdout_lines)
                if not parsed.model:
                    parsed = parsed.model_copy(update={"model": model or None})
                return parsed

            async def _resume(p: str, sid: str, timeout: float) -> CLIResult:
                prompt_args, stdin_data = _codex_resume_prompt_args(sid, p)
                a = ["exec", "resume", "--json", "--skip-git-repo-check"]
                if model:
                    a.extend(["-m", model])
                if reasoning_effort:
                    a.extend(["-c", f"model_reasoning_effort={reasoning_effort}"])
                a.extend(prompt_args)
                r = await run_cli(
                    "codex", a, cwd=cd, env=env, stdin_data=stdin_data,
                    timeout=timeout,
                    on_progress=_make_progress_cb(ctx, "codex", timeout),
                )
                parsed = parse_codex_output(r.stdout_lines)
                if not parsed.model:
                    parsed = parsed.model_copy(update={"model": model or None})
                return parsed

            parsed = await run_auto_split(
                effective_prompt, call_fn=_call, resume_fn=_resume,
                total_timeout=timeout,
            )
            _track_usage("codex", parsed.usage)
            return parsed.model_dump_json(exclude_none=True)

        # Resume mode: pass session_id and prompt as positional args
        if session_id:
            prompt_args, stdin_data = _codex_resume_prompt_args(
                session_id, effective_prompt,
            )
            args = ["exec", "resume", "--json", "--skip-git-repo-check"]
            if model:
                args.extend(["-m", model])
            if reasoning_effort:
                args.extend(["-c", f"model_reasoning_effort={reasoning_effort}"])
            args.extend(prompt_args)
        else:
            prompt_args, stdin_data = _codex_prompt_args(effective_prompt)
            args = [
                "exec", "--json",
                "--sandbox", validated_sandbox.value,
                "--cd", cd,
                "--skip-git-repo-check",
            ]
            if model:
                args.extend(["-m", model])
            if reasoning_effort:
                args.extend(["-c", f"model_reasoning_effort={reasoning_effort}"])
            args.extend(prompt_args)

        progress_cb = _make_progress_cb(ctx, "codex", timeout)
        result = await run_cli(
            "codex", args, cwd=cd, env=env, stdin_data=stdin_data,
            on_progress=progress_cb, timeout=timeout,
        )
        parsed = parse_codex_output(result.stdout_lines, return_all=return_all_messages)
        if not parsed.model:
            parsed = parsed.model_copy(update={"model": model or None})

        # Cascade fallback on rate limit: degrade reasoning_effort high → medium → low
        if is_rate_limited(parsed) and not session_id:
            effective_effort = reasoning_effort or "high"
            eff_idx = (
                _CODEX_EFFORT_CHAIN.index(effective_effort)
                if effective_effort in _CODEX_EFFORT_CHAIN
                else -1  # unknown effort (e.g. xhigh) → start from high
            )
            for next_effort in _CODEX_EFFORT_CHAIN[eff_idx + 1:]:
                # Probe: short test to verify the effort level is reachable
                probe_args = [
                    "exec", "--json",
                    "--sandbox", validated_sandbox.value,
                    "--cd", cd,
                    "--skip-git-repo-check",
                ]
                if model:
                    probe_args.extend(["-m", model])
                probe_args.extend(["-c", f"model_reasoning_effort={next_effort}"])
                probe_args.extend(["--", _PROBE_PROMPT])
                probe_result = await run_cli(
                    "codex", probe_args, cwd=cd, env=env,
                    timeout=_PROBE_TIMEOUT,
                )
                probe_parsed = parse_codex_output(probe_result.stdout_lines)
                if not probe_parsed.success:
                    if is_rate_limited(probe_parsed):
                        continue  # this level also rate-limited, try next
                    break  # different error, stop
                # Probe OK — send the real prompt
                retry_prompt_args, retry_stdin = _codex_prompt_args(
                    effective_prompt,
                )
                retry_args = [
                    "exec", "--json",
                    "--sandbox", validated_sandbox.value,
                    "--cd", cd,
                    "--skip-git-repo-check",
                ]
                if model:
                    retry_args.extend(["-m", model])
                retry_args.extend(["-c", f"model_reasoning_effort={next_effort}"])
                retry_args.extend(retry_prompt_args)
                retry_result = await run_cli(
                    "codex", retry_args, cwd=cd, env=env,
                    stdin_data=retry_stdin,
                    on_progress=progress_cb, timeout=timeout,
                )
                parsed = parse_codex_output(
                    retry_result.stdout_lines, return_all=return_all_messages,
                )
                if parsed.success:
                    parsed = parsed.model_copy(update={
                        "content": f"[fallback: effort={next_effort}] {parsed.content}",
                    })
                    break
                if not is_rate_limited(parsed):
                    break  # different error, stop
                # still rate-limited — continue to next tier
        elif result.returncode != 0 and not parsed.success:
            msg = f"codex exited with code {result.returncode}: {_safe_stderr(result.stderr)}"
            if model_warning:
                msg = f"{msg} (hint: {model_warning})"
            parsed = parsed.model_copy(update={"content": msg})

        _track_usage("codex", parsed.usage)
        return parsed.model_dump_json(exclude_none=True)

    except asyncio.TimeoutError:
        return _err("codex timed out")
    except ValueError as e:
        return _err(str(e))
    except Exception:
        return _err("codex internal error")


@mcp.tool(name="gemini", annotations=ToolAnnotations(
    readOnlyHint=False, destructiveHint=False, idempotentHint=False,
))
async def gemini_tool(
    prompt: str,
    cd: str,
    ctx: Context | None = None,
    session_id: str = "",
    sandbox: bool = True,
    model: str = "",
    review_uncommitted: bool = False,
    review_base: str = "",
    review_commit: str = "",
    files: list[str] | None = None,
    return_all_messages: bool = False,
    auto_split: bool = False,
    system_prompt: str = "",
    timeout: float = 300.0,
) -> str:
    """Run Gemini CLI for coding tasks, code review, or general prompts.

    Modes:
      - Default: forward prompt to Gemini
      - Review: set review_uncommitted=True or review_base="main"
      - Files: pass files=["a.py"] to include file contents
      - Resume: pass session_id from a previous call
    """
    try:
        depth = _get_depth()
        if depth >= _MAX_DEPTH:
            return _err(f"nesting depth {depth} reached limit {_MAX_DEPTH}")

        if not shutil.which("gemini"):
            return _err("gemini CLI not found in PATH")

        # Validate all inputs
        validate_cd(cd)
        validate_session_id(session_id)
        validate_model(model)
        validate_commit_sha(review_commit)
        validate_files(files)
        validate_timeout(timeout)

        env = _child_env()

        # Advisory only — don't block, append hint if CLI fails later
        model_warning = await check_model(model, "gemini")

        if auto_split and session_id:
            return _err("auto_split and session_id are mutually exclusive")

        effective_prompt = await _build_context(
            prompt, cd=cd,
            review_uncommitted=review_uncommitted,
            review_base=review_base,
            review_commit=review_commit,
            files=files,
            system_prompt=system_prompt,
        )

        if not sandbox and not os.environ.get("SUPERAI_ALLOW_DANGEROUS"):
            return _err(
                "gemini sandbox=False is disabled by default. "
                "Set SUPERAI_ALLOW_DANGEROUS=1 to enable."
            )

        if auto_split:
            async def _call(p: str, timeout: float) -> CLIResult:
                prompt_args, stdin_data = _gemini_prompt_args(p)
                a = prompt_args + ["-o", "stream-json"]
                if sandbox:
                    a.append("--sandbox")
                if model:
                    a.extend(["--model", model])
                r = await run_cli(
                    "gemini", a, cwd=cd, env=env, stdin_data=stdin_data,
                    timeout=timeout,
                    on_progress=_make_progress_cb(ctx, "gemini", timeout),
                )
                parsed = parse_gemini_output(r.stdout_lines)
                if not parsed.model:
                    parsed = parsed.model_copy(update={"model": model or None})
                return parsed

            async def _resume(p: str, sid: str, timeout: float) -> CLIResult:
                prompt_args, stdin_data = _gemini_prompt_args(p)
                a = prompt_args + ["-o", "stream-json", "--resume", sid]
                if sandbox:
                    a.append("--sandbox")
                if model:
                    a.extend(["--model", model])
                r = await run_cli(
                    "gemini", a, cwd=cd, env=env, stdin_data=stdin_data,
                    timeout=timeout,
                    on_progress=_make_progress_cb(ctx, "gemini", timeout),
                )
                parsed = parse_gemini_output(r.stdout_lines)
                if not parsed.model:
                    parsed = parsed.model_copy(update={"model": model or None})
                return parsed

            parsed = await run_auto_split(
                effective_prompt, call_fn=_call, resume_fn=_resume,
                total_timeout=timeout,
            )
            _track_usage("gemini", parsed.usage)
            return parsed.model_dump_json(exclude_none=True)

        prompt_args, stdin_data = _gemini_prompt_args(effective_prompt)
        args = prompt_args + ["-o", "stream-json"]
        if sandbox:
            args.append("--sandbox")
        if model:
            args.extend(["--model", model])
        if session_id:
            args.extend(["--resume", session_id])

        progress_cb = _make_progress_cb(ctx, "gemini", timeout)
        result = await run_cli(
            "gemini", args, cwd=cd, env=env, stdin_data=stdin_data,
            on_progress=progress_cb, timeout=timeout,
        )
        parsed = parse_gemini_output(result.stdout_lines, return_all=return_all_messages)
        if not parsed.model:
            parsed = parsed.model_copy(update={"model": model or None})

        # Quota fallback: retry once with flash model (check before overwriting content)
        if is_rate_limited(parsed) and model != "flash":
            retry_prompt_args, retry_stdin = _gemini_prompt_args(effective_prompt)
            retry_args = retry_prompt_args + ["-o", "stream-json"]
            if sandbox:
                retry_args.append("--sandbox")
            retry_args.extend(["--model", "flash"])
            if session_id:
                retry_args.extend(["--resume", session_id])
            retry_result = await run_cli(
                "gemini", retry_args, cwd=cd, env=env, stdin_data=retry_stdin,
                on_progress=progress_cb, timeout=timeout,
            )
            parsed = parse_gemini_output(retry_result.stdout_lines, return_all=return_all_messages)
            if parsed.success:
                parsed = parsed.model_copy(update={
                    "content": f"[fallback: flash] {parsed.content}",
                    "model": parsed.model or "flash",
                })
        elif result.returncode != 0 and not parsed.success:
            msg = f"gemini exited with code {result.returncode}: {_safe_stderr(result.stderr)}"
            if model_warning:
                msg = f"{msg} (hint: {model_warning})"
            parsed = parsed.model_copy(update={"content": msg})

        _track_usage("gemini", parsed.usage)
        return parsed.model_dump_json(exclude_none=True)

    except asyncio.TimeoutError:
        return _err("gemini timed out")
    except ValueError as e:
        return _err(str(e))
    except Exception:
        return _err("gemini internal error")


def _claude_env() -> dict[str, str]:
    """Build env for Claude subprocess with CLAUDECODE removed."""
    env = dict(os.environ)
    env.pop("CLAUDECODE", None)
    return env


@mcp.tool(name="claude", annotations=ToolAnnotations(
    readOnlyHint=False, destructiveHint=False, idempotentHint=False,
))
async def claude_tool(
    prompt: str,
    cd: str,
    ctx: Context | None = None,
    session_id: str = "",
    sandbox: str = Sandbox.READ_ONLY,
    model: str = "",
    effort: str = "",
    max_budget_usd: float = 0.0,
    review_uncommitted: bool = False,
    review_base: str = "",
    review_commit: str = "",
    files: list[str] | None = None,
    return_all_messages: bool = False,
    auto_split: bool = False,
    system_prompt: str = "",
    timeout: float = 300.0,
) -> str:
    """Run Claude CLI for coding tasks, code review, or general prompts.

    Modes:
      - Default: forward prompt to Claude
      - Review: set review_uncommitted=True or review_base="main"
      - Files: pass files=["a.py"] to include file contents
      - Resume: pass session_id from a previous call
    """
    try:
        depth = _get_depth()
        if depth >= _MAX_DEPTH:
            return _err(f"nesting depth {depth} reached limit {_MAX_DEPTH}")

        if not shutil.which("claude"):
            return _err("claude CLI not found in PATH")

        # Validate all inputs
        validate_cd(cd)
        validated_sandbox = validate_sandbox(sandbox)
        validate_session_id(session_id)
        validate_model(model)
        validate_effort(effort)
        validate_max_budget(max_budget_usd)
        validate_commit_sha(review_commit)
        validate_files(files)
        validate_timeout(timeout)

        # Advisory only — don't block, append hint if CLI fails later
        model_warning = await check_model(model, "claude")

        if auto_split and session_id:
            return _err("auto_split and session_id are mutually exclusive")

        effective_prompt = await _build_context(
            prompt, cd=cd,
            review_uncommitted=review_uncommitted,
            review_base=review_base,
            review_commit=review_commit,
            files=files,
            system_prompt=system_prompt,
        )

        # Sandbox mapping (needed for both auto_split and normal paths)
        sandbox_args: list[str] = []
        if validated_sandbox == Sandbox.WORKSPACE_WRITE:
            sandbox_args.extend(["--permission-mode", "acceptEdits"])
        elif validated_sandbox == Sandbox.DANGER_FULL_ACCESS:
            if not os.environ.get("SUPERAI_ALLOW_DANGEROUS"):
                return _err(
                    "danger-full-access is disabled by default. "
                    "Set SUPERAI_ALLOW_DANGEROUS=1 to enable."
                )
            sandbox_args.append("--dangerously-skip-permissions")

        if auto_split:
            env = _child_env(_claude_env())

            async def _call(p: str, timeout: float) -> CLIResult:
                prompt_args, stdin_data = _claude_prompt_args(p)
                a = prompt_args + ["--output-format", "json"]
                if model:
                    a.extend(["--model", model])
                if effort:
                    a.extend(["--effort", effort])
                a.extend(sandbox_args)
                r = await run_cli(
                    "claude", a, cwd=cd, env=env, stdin_data=stdin_data,
                    timeout=timeout,
                    on_progress=_make_progress_cb(ctx, "claude", timeout),
                )
                parsed = parse_claude_output(r.stdout_lines)
                if not parsed.model:
                    parsed = parsed.model_copy(update={"model": model or None})
                return parsed

            async def _resume(p: str, sid: str, timeout: float) -> CLIResult:
                prompt_args, stdin_data = _claude_prompt_args(p)
                a = prompt_args + ["--output-format", "json", "--resume", sid]
                if model:
                    a.extend(["--model", model])
                if effort:
                    a.extend(["--effort", effort])
                a.extend(sandbox_args)
                r = await run_cli(
                    "claude", a, cwd=cd, env=env, stdin_data=stdin_data,
                    timeout=timeout,
                    on_progress=_make_progress_cb(ctx, "claude", timeout),
                )
                parsed = parse_claude_output(r.stdout_lines)
                if not parsed.model:
                    parsed = parsed.model_copy(update={"model": model or None})
                return parsed

            parsed = await run_auto_split(
                effective_prompt, call_fn=_call, resume_fn=_resume,
                total_timeout=timeout,
            )
            _track_usage("claude", parsed.usage)
            return parsed.model_dump_json(exclude_none=True)

        prompt_args, stdin_data = _claude_prompt_args(effective_prompt)
        args = prompt_args + ["--output-format", "json"]

        if session_id:
            args.extend(["--resume", session_id])
        if model:
            args.extend(["--model", model])
        if effort:
            args.extend(["--effort", effort])
        if max_budget_usd > 0:
            args.extend(["--max-budget-usd", str(max_budget_usd)])
        args.extend(sandbox_args)

        env = _child_env(_claude_env())
        progress_cb = _make_progress_cb(ctx, "claude", timeout)
        result = await run_cli(
            "claude", args, cwd=cd, env=env, stdin_data=stdin_data,
            on_progress=progress_cb, timeout=timeout,
        )
        parsed = parse_claude_output(result.stdout_lines, return_all=return_all_messages)
        if not parsed.model:
            parsed = parsed.model_copy(update={"model": model or None})

        # Cascade fallback on rate limit: current → sonnet → haiku
        if is_rate_limited(parsed):
            # Only try models strictly below the current model in the chain
            start = 0
            for i, m in enumerate(_CLAUDE_FALLBACK_CHAIN):
                if model == m:
                    start = i + 1
                    break
            for fallback_model in _CLAUDE_FALLBACK_CHAIN[start:]:
                # Probe: short test to verify fallback model is reachable
                probe_args = ["-p", _PROBE_PROMPT, "--output-format", "json",
                              "--model", fallback_model]
                probe_args.extend(sandbox_args)
                probe_result = await run_cli(
                    "claude", probe_args, cwd=cd, env=env, timeout=_PROBE_TIMEOUT,
                )
                probe_parsed = parse_claude_output(probe_result.stdout_lines)
                if not probe_parsed.success:
                    if is_rate_limited(probe_parsed):
                        continue  # this level also rate-limited, try next
                    break  # different error, stop
                # Probe OK — send the real prompt
                retry_prompt_args, retry_stdin = _claude_prompt_args(
                    effective_prompt,
                )
                retry_args = retry_prompt_args + [
                    "--output-format", "json", "--model", fallback_model,
                ]
                if effort:
                    retry_args.extend(["--effort", effort])
                if max_budget_usd > 0:
                    retry_args.extend(["--max-budget-usd", str(max_budget_usd)])
                retry_args.extend(sandbox_args)
                retry_result = await run_cli(
                    "claude", retry_args, cwd=cd, env=env, stdin_data=retry_stdin,
                    on_progress=progress_cb, timeout=timeout,
                )
                parsed = parse_claude_output(
                    retry_result.stdout_lines, return_all=return_all_messages,
                )
                if parsed.success:
                    parsed = parsed.model_copy(update={
                        "content": f"[fallback: {fallback_model}] {parsed.content}",
                        "model": parsed.model or fallback_model,
                    })
                    break
                if not is_rate_limited(parsed):
                    break  # different error, stop
                # still rate-limited — continue to next tier
        elif result.returncode != 0 and not parsed.success:
            msg = f"claude exited with code {result.returncode}: {_safe_stderr(result.stderr)}"
            if model_warning:
                msg = f"{msg} (hint: {model_warning})"
            parsed = parsed.model_copy(update={"content": msg})

        _track_usage("claude", parsed.usage)
        return parsed.model_dump_json(exclude_none=True)

    except asyncio.TimeoutError:
        return _err("claude timed out")
    except ValueError as e:
        return _err(str(e))
    except Exception:
        return _err("claude internal error")


_ALL_TARGETS = ("codex", "gemini", "claude")

_TARGET_FNS = {
    "codex": codex_tool,
    "gemini": gemini_tool,
    "claude": claude_tool,
}


@mcp.tool(name="broadcast", annotations=ToolAnnotations(
    readOnlyHint=False, destructiveHint=False, idempotentHint=False,
))
async def broadcast_tool(
    prompt: str,
    cd: str,
    ctx: Context | None = None,
    targets: list[str] | None = None,
    model: str = "",
    models: dict[str, str] | None = None,
    review_uncommitted: bool = False,
    review_base: str = "",
    review_commit: str = "",
    files: list[str] | None = None,
    return_all_messages: bool = False,
    system_prompt: str = "",
    timeout: float = 300.0,
) -> str:
    """Broadcast the same prompt to multiple CLI tools in parallel.

    Sends the prompt concurrently to the specified targets (or all if empty)
    and returns aggregated results. Useful for comparing answers across models.
    """
    effective_targets = list(_ALL_TARGETS) if not targets else targets

    # Deduplicate while preserving order
    seen: set[str] = set()
    deduped: list[str] = []
    for t in effective_targets:
        if t not in seen:
            seen.add(t)
            deduped.append(t)
    effective_targets = deduped

    # Validate targets
    invalid = [t for t in effective_targets if t not in _ALL_TARGETS]
    if invalid:
        return _err(f"invalid target(s): {', '.join(invalid)}. valid: {', '.join(_ALL_TARGETS)}")

    # Pre-build context once to avoid repeated git diff / file reads
    try:
        validate_cd(cd)
        validate_commit_sha(review_commit)
        validate_files(files)
        validate_timeout(timeout)
        effective_prompt = await _build_context(
            prompt, cd=cd,
            review_uncommitted=review_uncommitted,
            review_base=review_base,
            review_commit=review_commit,
            files=files,
            system_prompt=system_prompt,
        )
    except ValueError as e:
        return _err(str(e))

    # Validate per-target model keys
    if models:
        invalid_keys = [k for k in models if k not in _ALL_TARGETS]
        if invalid_keys:
            return _err(f"invalid models key(s): {', '.join(invalid_keys)}. valid: {', '.join(_ALL_TARGETS)}")

    # Forward pre-built prompt; disable review/files so tools don't redo the work
    base_kwargs: dict[str, object] = {
        "prompt": effective_prompt,
        "cd": cd,
        "review_uncommitted": False,
        "review_base": "",
        "review_commit": "",
        "files": None,
        "return_all_messages": return_all_messages,
        "system_prompt": "",
        "timeout": timeout,
    }

    async def _call(target: str) -> tuple[str, object]:
        fn = _TARGET_FNS[target]
        # Per-target model override takes precedence over global model
        target_model = (models or {}).get(target, model)
        kwargs = {**base_kwargs, "model": target_model}
        try:
            raw = await fn(**kwargs)  # type: ignore[arg-type]
            return target, json.loads(raw)
        except Exception as exc:
            return target, {"success": False, "content": f"{target} error: {exc}"}

    tasks = [_call(t) for t in effective_targets]
    pairs = await asyncio.gather(*tasks, return_exceptions=True)

    results: dict[str, object] = {}
    for pair in pairs:
        if isinstance(pair, BaseException):
            results["unknown"] = {"success": False, "content": str(pair)}
        else:
            target, data = pair
            results[target] = data

    return json.dumps({"success": True, "results": results})


# ---------------------------------------------------------------------------
# Multi-model collaboration tools
# ---------------------------------------------------------------------------


@mcp.tool(name="chain", annotations=ToolAnnotations(
    readOnlyHint=False, destructiveHint=False, idempotentHint=False,
))
async def chain_tool(
    steps: list[dict[str, str]],
    cd: str,
    ctx: Context | None = None,
    system_prompt: str = "",
    timeout: float = 300.0,
) -> str:
    """Run a sequential multi-model pipeline. Each step's output is auto-injected into the next.

    steps: list of {target, prompt, model?} objects. target is "codex", "gemini", or "claude".
    Each step receives the previous step's output wrapped in <previous_output> tags.
    Stops on first failure and returns partial results.
    """
    import time

    try:
        validate_cd(cd)
        validate_timeout(timeout)
    except ValueError as e:
        return _err(str(e))

    if not steps:
        return _err("steps must be a non-empty list")

    # Validate all targets upfront
    for i, step in enumerate(steps):
        if not isinstance(step, dict):
            return _err(f"step {i}: must be a dict, got {type(step).__name__}")
        target = step.get("target", "")
        if target not in _TARGET_FNS:
            return _err(f"step {i}: invalid target {target!r}, must be one of {list(_ALL_TARGETS)}")
        if not step.get("prompt"):
            return _err(f"step {i}: prompt is required")

    deadline = time.monotonic() + timeout
    completed: list[dict[str, object]] = []
    prev_output: str | None = None

    for i, step in enumerate(steps):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break

        target = step["target"]
        prompt = step["prompt"]
        step_model = step.get("model", "")

        # Inject previous output
        if prev_output is not None:
            prompt = f"<previous_output>\n{prev_output}\n</previous_output>\n\n{prompt}"

        kwargs: dict[str, object] = {
            "prompt": prompt,
            "cd": cd,
            "ctx": ctx,
            "system_prompt": system_prompt if i == 0 else "",
            "timeout": remaining,
        }
        if step_model:
            kwargs["model"] = step_model

        fn = _TARGET_FNS[target]
        try:
            raw = await fn(**kwargs)  # type: ignore[arg-type]
            result = json.loads(raw)
        except Exception as exc:
            completed.append({"step": i, "target": target, "success": False, "content": str(exc)})
            return json.dumps({"success": False, "steps": completed, "final_content": str(exc)})

        content = result.get("content", "")
        success = result.get("success", False)
        completed.append({"step": i, "target": target, "success": success, "content": content})

        if not success:
            return json.dumps({"success": False, "steps": completed, "final_content": content})

        prev_output = content

    if not completed:
        return json.dumps({"success": False, "steps": [], "final_content": "timeout before any step ran"})
    all_ok = bool(completed) and all(s.get("success") for s in completed)
    final = completed[-1]["content"] if completed else ""
    return json.dumps({"success": all_ok, "steps": completed, "final_content": final})


_JUDGE_TEMPLATE = """\
You are a judge evaluating multiple answers to the same question.

## Original Question
{prompt}

## Candidate Answers
{candidates_text}

## Your Task
Pick the BEST candidate. Reply with:
1. "Winner: Candidate X" (where X is A, B, C, etc.)
2. A brief explanation of why this answer is best.
"""


@mcp.tool(name="vote", annotations=ToolAnnotations(
    readOnlyHint=False, destructiveHint=False, idempotentHint=False,
))
async def vote_tool(
    prompt: str,
    cd: str,
    ctx: Context | None = None,
    candidates: list[str] | None = None,
    judge: str = "claude",
    model: str = "",
    system_prompt: str = "",
    timeout: float = 300.0,
) -> str:
    """Send prompt to multiple models in parallel, then have a judge pick the best answer.

    candidates: list of CLI targets to compete (default: all 3).
    judge: which CLI judges the results (default: claude). Auto-excluded from candidates.
    """
    import time

    try:
        validate_cd(cd)
        validate_timeout(timeout)
    except ValueError as e:
        return _err(str(e))

    if judge not in _TARGET_FNS:
        return _err(f"invalid judge: {judge!r}, must be one of {list(_ALL_TARGETS)}")

    effective_candidates = list(candidates) if candidates else list(_ALL_TARGETS)

    # Validate candidates
    invalid = [c for c in effective_candidates if c not in _TARGET_FNS]
    if invalid:
        return _err(f"invalid candidate(s): {invalid}")

    deadline = time.monotonic() + timeout

    # If only 1 candidate, skip voting (before judge exclusion)
    if len(effective_candidates) == 1:
        target = effective_candidates[0]
        fn = _TARGET_FNS[target]
        try:
            raw = await fn(prompt=prompt, cd=cd, ctx=ctx, system_prompt=system_prompt,
                          timeout=deadline - time.monotonic(), model=model)
            result = json.loads(raw)
            return json.dumps({
                "success": result.get("success", False),
                "final_content": result.get("content", ""),
                "candidates": {target: result.get("content", "")},
                "judge_reasoning": "Single candidate — no voting needed.",
            })
        except Exception as exc:
            return _err(str(exc))

    # Remove judge from candidates to avoid conflict
    effective_candidates = [c for c in effective_candidates if c != judge]
    if not effective_candidates:
        return _err("no candidates remaining after excluding judge")

    # Phase 1: Run candidates in parallel
    candidate_kwargs: dict[str, object] = {
        "prompt": prompt,
        "cd": cd,
        "ctx": ctx,
        "system_prompt": system_prompt,
        "timeout": (deadline - time.monotonic()) * 0.7,  # 70% budget for candidates
        "model": model,
    }

    async def _run_candidate(target: str) -> tuple[str, dict]:
        fn = _TARGET_FNS[target]
        try:
            raw = await fn(**candidate_kwargs)  # type: ignore[arg-type]
            return target, json.loads(raw)
        except Exception as exc:
            return target, {"success": False, "content": str(exc)}

    tasks = [_run_candidate(t) for t in effective_candidates]
    pairs = await asyncio.gather(*tasks)
    candidate_results: dict[str, str] = {}
    for target, data in pairs:
        candidate_results[target] = data.get("content", "")

    # Phase 2: Judge
    labels = list("ABCDEFGHIJ")
    candidates_text_parts: list[str] = []
    label_map: dict[str, str] = {}  # label -> target name
    for i, (target, content) in enumerate(candidate_results.items()):
        label = labels[i] if i < len(labels) else str(i)
        label_map[label] = target
        candidates_text_parts.append(f"### Candidate {label}\n{content}")

    judge_prompt = _JUDGE_TEMPLATE.format(
        prompt=prompt,
        candidates_text="\n\n".join(candidates_text_parts),
    )

    judge_fn = _TARGET_FNS[judge]
    remaining = max(1.0, deadline - time.monotonic())
    try:
        judge_raw = await judge_fn(
            prompt=judge_prompt, cd=cd, ctx=ctx, timeout=remaining, model=model,
        )
        judge_result = json.loads(judge_raw)
        judge_reasoning = judge_result.get("content", "")
    except Exception as exc:
        judge_reasoning = f"Judge failed: {exc}"

    return json.dumps({
        "success": True,
        "candidates": candidate_results,
        "judge_reasoning": judge_reasoning,
        "final_content": judge_reasoning,
    })


@mcp.tool(name="debate", annotations=ToolAnnotations(
    readOnlyHint=False, destructiveHint=False, idempotentHint=False,
))
async def debate_tool(
    prompt: str,
    cd: str,
    ctx: Context | None = None,
    side_a: str = "codex",
    side_b: str = "claude",
    rounds: int = 3,
    model: str = "",
    system_prompt: str = "",
    timeout: float = 300.0,
) -> str:
    """Alternating debate between two models over multiple rounds.

    side_a starts, then side_b critiques and improves, then side_a again, etc.
    Each round sees the opponent's previous response via <opponent_response> tags.
    """
    import time

    try:
        validate_cd(cd)
        validate_timeout(timeout)
    except ValueError as e:
        return _err(str(e))

    if side_a not in _TARGET_FNS:
        return _err(f"invalid side_a: {side_a!r}, must be one of {list(_ALL_TARGETS)}")
    if side_b not in _TARGET_FNS:
        return _err(f"invalid side_b: {side_b!r}, must be one of {list(_ALL_TARGETS)}")
    if side_a == side_b:
        return _err("side_a and side_b must be different")
    if rounds < 1:
        return _err("rounds must be >= 1")

    deadline = time.monotonic() + timeout
    sides = [side_a, side_b]
    round_results: list[dict[str, object]] = []
    prev_content: str | None = None

    for i in range(rounds):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break

        side = sides[i % 2]
        round_prompt = prompt

        if prev_content is not None:
            round_prompt = (
                f"<opponent_response>\n{prev_content}\n</opponent_response>\n\n"
                f"The above is your opponent's response to this topic. "
                f"Critique it and provide your improved answer.\n\n"
                f"Original topic: {prompt}"
            )

        fn = _TARGET_FNS[side]
        try:
            raw = await fn(
                prompt=round_prompt, cd=cd, ctx=ctx,
                system_prompt=system_prompt if i == 0 else "",
                timeout=remaining, model=model,
            )
            result = json.loads(raw)
        except Exception as exc:
            round_results.append({
                "round": i + 1, "side": side, "success": False, "content": str(exc),
            })
            return json.dumps({
                "success": False,
                "rounds": round_results,
                "final_answer": str(exc),
            })

        content = result.get("content", "")
        success = result.get("success", False)
        round_results.append({
            "round": i + 1, "side": side, "success": success, "content": content,
        })

        if not success:
            return json.dumps({
                "success": False,
                "rounds": round_results,
                "final_answer": content,
            })

        prev_content = content

    if not round_results:
        return json.dumps({
            "success": False, "rounds": [], "final_answer": "timeout before any round ran",
        })
    final = round_results[-1]["content"]
    return json.dumps({
        "success": True,
        "rounds": round_results,
        "final_answer": final,
    })


@mcp.tool(name="list-models", annotations=ToolAnnotations(
    readOnlyHint=True, destructiveHint=False, idempotentHint=True,
))
async def list_models_tool(
    provider: str = "",
) -> str:
    """List available models from OpenRouter (covers OpenAI, Google, Anthropic).

    Filter by provider prefix: "openai", "google", "anthropic", or empty for all three.
    """
    try:
        models = await fetch_models(provider)
        return json.dumps({"success": True, "count": len(models), "models": models})
    except Exception as exc:
        return _err(f"Failed to fetch models: {exc}")


@mcp.tool(name="usage", annotations=ToolAnnotations(
    readOnlyHint=False, destructiveHint=False, idempotentHint=False,
))
async def usage_tool(reset: bool = False) -> str:
    """Show cumulative token usage and call counts across all CLI tools.

    Returns per-CLI and total stats. Set reset=True to clear counters after reading.
    """
    total: dict[str, int] = {"calls": 0, "input_tokens": 0, "output_tokens": 0}
    for stats in _usage.values():
        for key in total:
            total[key] += stats[key]

    result: dict[str, object] = {"success": True}
    for cli in ("codex", "gemini", "claude"):
        result[cli] = dict(_usage[cli])
    result["total"] = total

    if reset:
        _reset_usage()

    return json.dumps(result)


async def _check_cli(name: str) -> dict[str, object]:
    """Check a single CLI: available, version, authenticated."""
    if not shutil.which(name):
        return {"available": False, "version": None, "authenticated": False}

    # Get version
    version: str | None = None
    try:
        r = await run_cli(name, ["--version"], timeout=5.0)
        if r.returncode == 0 and r.stdout_lines:
            version = r.stdout_lines[0].strip()
    except Exception:
        pass

    # Auth probe
    authenticated = False
    try:
        if name == "codex":
            args = [
                "exec", "--json", "--sandbox", "read-only",
                "--skip-git-repo-check", "--", _PROBE_PROMPT,
            ]
            env = None
        elif name == "gemini":
            args = ["-p", _PROBE_PROMPT, "-o", "stream-json", "--sandbox"]
            env = None
        else:  # claude
            args = ["-p", _PROBE_PROMPT, "--output-format", "json"]
            env = _claude_env()

        parsers: dict[str, Callable[[list[str]], CLIResult]] = {
            "codex": parse_codex_output,
            "gemini": parse_gemini_output,
            "claude": parse_claude_output,
        }
        r = await run_cli(name, args, timeout=_STATUS_TIMEOUT, env=env)
        parsed = parsers[name](r.stdout_lines)
        authenticated = parsed.success
    except Exception:
        pass

    return {"available": True, "version": version, "authenticated": authenticated}


@mcp.tool(name="status", annotations=ToolAnnotations(
    readOnlyHint=True, destructiveHint=False, idempotentHint=True,
))
async def status_tool() -> str:
    """Check availability, version, and authentication status of all CLI tools."""
    results = await asyncio.gather(
        _check_cli("codex"),
        _check_cli("gemini"),
        _check_cli("claude"),
    )
    return json.dumps({
        "success": True,
        "codex": results[0],
        "gemini": results[1],
        "claude": results[2],
    })


def serve() -> None:
    """Start the MCP server."""
    mcp.run()
