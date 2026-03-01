"""FastMCP server with Codex and Gemini tool registration."""

import asyncio
import shutil

from mcp.server.fastmcp import FastMCP

from superai_mcp.git_utils import get_git_diff, read_files
from superai_mcp.models import CLIResult, Sandbox
from superai_mcp.parsers import parse_codex_output, parse_gemini_output
from superai_mcp.runner import run_cli

mcp = FastMCP("super")


def _err(msg: str) -> str:
    """Return a JSON error response."""
    return CLIResult(success=False, content=msg).model_dump_json()


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

        # Resume mode: just resume the session, no context injection
        if session_id:
            args = ["exec", "resume", "--json", session_id]
        else:
            effective_prompt = await _build_context(
                prompt, cd=cd,
                review_uncommitted=review_uncommitted,
                review_base=review_base,
                files=files,
            )
            args = [
                "exec", "--json",
                "--sandbox", sandbox,
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
                "content": f"(codex exit {result.returncode}): {result.stderr.strip()}"
            })

        return parsed.model_dump_json()

    except asyncio.TimeoutError:
        return _err("codex timed out")
    except ValueError as e:
        return _err(f"validation error: {e}")
    except Exception as e:
        return _err(f"codex error: {e}")


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

        # Resume mode uses --resume flag but still accepts a new prompt
        effective_prompt = await _build_context(
            prompt, cd=cd,
            review_uncommitted=review_uncommitted,
            review_base=review_base,
            files=files,
        )

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
                "content": f"(gemini exit {result.returncode}): {result.stderr.strip()}"
            })

        return parsed.model_dump_json()

    except asyncio.TimeoutError:
        return _err("gemini timed out")
    except ValueError as e:
        return _err(f"validation error: {e}")
    except Exception as e:
        return _err(f"gemini error: {e}")


def serve() -> None:
    """Start the MCP server."""
    mcp.run()
