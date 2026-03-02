"""FastMCP server with Codex, Gemini, Claude, and broadcast tool registration."""

import asyncio
import json
import os
import shutil

from mcp.server.fastmcp import FastMCP

from superai_mcp.git_utils import get_git_diff, read_files
from superai_mcp.models import CLIResult, Sandbox
from superai_mcp.parsers import parse_claude_output, parse_codex_output, parse_gemini_output
from superai_mcp.runner import run_cli
from superai_mcp.splitter import run_auto_split
from superai_mcp.validate import (
    validate_cd,
    validate_effort,
    validate_files,
    validate_max_budget,
    validate_model,
    validate_reasoning_effort,
    validate_sandbox,
    validate_session_id,
)

mcp = FastMCP("super")

# Max stderr chars to include in error responses
_MAX_STDERR = 500


def _err(msg: str) -> str:
    """Return a JSON error response."""
    return CLIResult(success=False, content=msg).model_dump_json()


def _safe_stderr(stderr: str) -> str:
    """Truncate stderr to avoid leaking sensitive info."""
    s = stderr.strip()
    return s[:_MAX_STDERR] if len(s) > _MAX_STDERR else s


async def _build_context(
    prompt: str,
    *,
    cd: str,
    review_uncommitted: bool,
    review_base: str,
    files: list[str] | None,
) -> str:
    """Build prompt with optional diff/file context."""
    parts: list[str] = []

    if review_uncommitted or review_base:
        diff_text = await get_git_diff(cd, uncommitted=review_uncommitted, base=review_base)
        if diff_text:
            label = "uncommitted changes" if review_uncommitted else f"changes vs {review_base}"
            parts.append(f"Below is the git diff ({label}):\n\n```diff\n{diff_text}\n```")

    if files:
        parts.append(f"Below are the file contents:\n\n{read_files(files, cd)}")

    parts.append(prompt)
    return "\n\n".join(parts)


@mcp.tool(name="codex")
async def codex_tool(
    prompt: str,
    cd: str,
    session_id: str = "",
    sandbox: str = Sandbox.READ_ONLY,
    model: str = "",
    reasoning_effort: str = "",
    review_uncommitted: bool = False,
    review_base: str = "",
    files: list[str] | None = None,
    return_all_messages: bool = False,
    auto_split: bool = False,
) -> str:
    """Run Codex CLI for coding tasks, code review, or general prompts.

    Modes:
      - Default: forward prompt to Codex
      - Review: set review_uncommitted=True or review_base="main"
      - Files: pass files=["a.py"] to include file contents
      - Resume: pass session_id from a previous call
    """
    try:
        if not shutil.which("codex"):
            return _err("codex CLI not found in PATH")

        # Validate all inputs
        validate_cd(cd)
        validated_sandbox = validate_sandbox(sandbox)
        validate_session_id(session_id)
        validate_model(model)
        validate_reasoning_effort(reasoning_effort)
        validate_files(files)

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
            files=files,
        )

        if auto_split:
            async def _call(p: str, timeout: float) -> CLIResult:
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
                a.extend(["--", p])
                r = await run_cli("codex", a, cwd=cd, timeout=timeout)
                return parse_codex_output(r.stdout_lines)

            # Codex resume cannot accept new prompt, so no resume_fn
            parsed = await run_auto_split(effective_prompt, call_fn=_call)
            return parsed.model_dump_json()

        # Resume mode: just resume the session, no context injection
        if session_id:
            args = ["exec", "resume", "--json", session_id]
        else:
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
            args.extend(["--", effective_prompt])

        result = await run_cli("codex", args, cwd=cd)
        parsed = parse_codex_output(result.stdout_lines, return_all=return_all_messages)

        if result.returncode != 0 and not parsed.success:
            parsed = parsed.model_copy(update={
                "content": f"codex exited with code {result.returncode}: {_safe_stderr(result.stderr)}"
            })

        return parsed.model_dump_json()

    except asyncio.TimeoutError:
        return _err("codex timed out")
    except ValueError as e:
        return _err(str(e))
    except Exception:
        return _err("codex internal error")


@mcp.tool(name="gemini")
async def gemini_tool(
    prompt: str,
    cd: str,
    session_id: str = "",
    sandbox: bool = True,
    model: str = "",
    review_uncommitted: bool = False,
    review_base: str = "",
    files: list[str] | None = None,
    return_all_messages: bool = False,
    auto_split: bool = False,
) -> str:
    """Run Gemini CLI for coding tasks, code review, or general prompts.

    Modes:
      - Default: forward prompt to Gemini
      - Review: set review_uncommitted=True or review_base="main"
      - Files: pass files=["a.py"] to include file contents
      - Resume: pass session_id from a previous call
    """
    try:
        if not shutil.which("gemini"):
            return _err("gemini CLI not found in PATH")

        # Validate all inputs
        validate_cd(cd)
        validate_session_id(session_id)
        validate_model(model)
        validate_files(files)

        if auto_split and session_id:
            return _err("auto_split and session_id are mutually exclusive")

        effective_prompt = await _build_context(
            prompt, cd=cd,
            review_uncommitted=review_uncommitted,
            review_base=review_base,
            files=files,
        )

        if not sandbox and not os.environ.get("SUPERAI_ALLOW_DANGEROUS"):
            return _err(
                "gemini sandbox=False is disabled by default. "
                "Set SUPERAI_ALLOW_DANGEROUS=1 to enable."
            )

        if auto_split:
            async def _call(p: str, timeout: float) -> CLIResult:
                a = ["-p", p, "-o", "stream-json"]
                if sandbox:
                    a.append("--sandbox")
                if model:
                    a.extend(["--model", model])
                r = await run_cli("gemini", a, cwd=cd, timeout=timeout)
                return parse_gemini_output(r.stdout_lines)

            async def _resume(p: str, sid: str, timeout: float) -> CLIResult:
                a = ["-p", p, "-o", "stream-json", "--resume", sid]
                if sandbox:
                    a.append("--sandbox")
                if model:
                    a.extend(["--model", model])
                r = await run_cli("gemini", a, cwd=cd, timeout=timeout)
                return parse_gemini_output(r.stdout_lines)

            parsed = await run_auto_split(
                effective_prompt, call_fn=_call, resume_fn=_resume,
            )
            return parsed.model_dump_json()

        args = ["-p", effective_prompt, "-o", "stream-json"]
        if sandbox:
            args.append("--sandbox")
        if model:
            args.extend(["--model", model])
        if session_id:
            args.extend(["--resume", session_id])

        result = await run_cli("gemini", args, cwd=cd)
        parsed = parse_gemini_output(result.stdout_lines, return_all=return_all_messages)

        if result.returncode != 0 and not parsed.success:
            parsed = parsed.model_copy(update={
                "content": f"gemini exited with code {result.returncode}: {_safe_stderr(result.stderr)}"
            })

        return parsed.model_dump_json()

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


@mcp.tool(name="claude")
async def claude_tool(
    prompt: str,
    cd: str,
    session_id: str = "",
    sandbox: str = Sandbox.READ_ONLY,
    model: str = "",
    effort: str = "",
    max_budget_usd: float = 0.0,
    review_uncommitted: bool = False,
    review_base: str = "",
    files: list[str] | None = None,
    return_all_messages: bool = False,
    auto_split: bool = False,
) -> str:
    """Run Claude CLI for coding tasks, code review, or general prompts.

    Modes:
      - Default: forward prompt to Claude
      - Review: set review_uncommitted=True or review_base="main"
      - Files: pass files=["a.py"] to include file contents
      - Resume: pass session_id from a previous call
    """
    try:
        if not shutil.which("claude"):
            return _err("claude CLI not found in PATH")

        # Validate all inputs
        validate_cd(cd)
        validated_sandbox = validate_sandbox(sandbox)
        validate_session_id(session_id)
        validate_model(model)
        validate_effort(effort)
        validate_max_budget(max_budget_usd)
        validate_files(files)

        if auto_split and session_id:
            return _err("auto_split and session_id are mutually exclusive")

        effective_prompt = await _build_context(
            prompt, cd=cd,
            review_uncommitted=review_uncommitted,
            review_base=review_base,
            files=files,
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
            env = _claude_env()

            async def _call(p: str, timeout: float) -> CLIResult:
                a = ["-p", p, "--output-format", "json"]
                if model:
                    a.extend(["--model", model])
                if effort:
                    a.extend(["--effort", effort])
                a.extend(sandbox_args)
                r = await run_cli("claude", a, cwd=cd, env=env, timeout=timeout)
                return parse_claude_output(r.stdout_lines)

            async def _resume(p: str, sid: str, timeout: float) -> CLIResult:
                a = ["-p", p, "--output-format", "json", "--resume", sid]
                if model:
                    a.extend(["--model", model])
                if effort:
                    a.extend(["--effort", effort])
                a.extend(sandbox_args)
                r = await run_cli("claude", a, cwd=cd, env=env, timeout=timeout)
                return parse_claude_output(r.stdout_lines)

            parsed = await run_auto_split(
                effective_prompt, call_fn=_call, resume_fn=_resume,
            )
            return parsed.model_dump_json()

        args = ["-p", effective_prompt, "--output-format", "json"]

        if session_id:
            args.extend(["--resume", session_id])
        if model:
            args.extend(["--model", model])
        if effort:
            args.extend(["--effort", effort])
        if max_budget_usd > 0:
            args.extend(["--max-budget-usd", str(max_budget_usd)])
        args.extend(sandbox_args)

        result = await run_cli("claude", args, cwd=cd, env=_claude_env())
        parsed = parse_claude_output(result.stdout_lines, return_all=return_all_messages)

        if result.returncode != 0 and not parsed.success:
            parsed = parsed.model_copy(update={
                "content": f"claude exited with code {result.returncode}: {_safe_stderr(result.stderr)}"
            })

        return parsed.model_dump_json()

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


@mcp.tool(name="broadcast")
async def broadcast_tool(
    prompt: str,
    cd: str,
    targets: list[str] | None = None,
    model: str = "",
    review_uncommitted: bool = False,
    review_base: str = "",
    files: list[str] | None = None,
    return_all_messages: bool = False,
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
        effective_prompt = await _build_context(
            prompt, cd=cd,
            review_uncommitted=review_uncommitted,
            review_base=review_base,
            files=files,
        )
    except ValueError as e:
        return _err(str(e))

    # Forward pre-built prompt; disable review/files so tools don't redo the work
    kwargs: dict[str, object] = {
        "prompt": effective_prompt,
        "cd": cd,
        "model": model,
        "review_uncommitted": False,
        "review_base": "",
        "files": None,
        "return_all_messages": return_all_messages,
    }

    async def _call(target: str) -> tuple[str, object]:
        fn = _TARGET_FNS[target]
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


def serve() -> None:
    """Start the MCP server."""
    mcp.run()
