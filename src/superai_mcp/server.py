"""FastMCP server with Codex and Gemini tool registration."""

import asyncio
import shutil

from mcp.server.fastmcp import FastMCP

from superai_mcp.git_utils import get_git_diff, read_files
from superai_mcp.models import CLIResult, Sandbox
from superai_mcp.parsers import parse_codex_output, parse_gemini_output
from superai_mcp.runner import run_cli

mcp = FastMCP("super")


def _build_effective_prompt(
    prompt: str,
    *,
    cd: str,
    review_uncommitted: bool,
    review_base: str,
    files: list[str] | None,
    diff_text: str,
) -> str:
    """Build the final prompt with optional context injection."""
    parts: list[str] = []

    if diff_text:
        label = "uncommitted changes" if review_uncommitted else f"changes vs {review_base}"
        parts.append(f"Below is the git diff ({label}):\n\n```diff\n{diff_text}\n```")

    if files:
        file_content = read_files(files, cd)
        parts.append(f"Below are the file contents:\n\n{file_content}")

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
            return CLIResult(success=False, content="codex CLI not found in PATH").model_dump_json()

        # Build diff context if needed
        diff_text = ""
        if review_uncommitted or review_base:
            diff_text = await get_git_diff(cd, uncommitted=review_uncommitted, base=review_base)

        effective_prompt = _build_effective_prompt(
            prompt, cd=cd,
            review_uncommitted=review_uncommitted,
            review_base=review_base,
            files=files,
            diff_text=diff_text,
        )

        # Build command args
        if session_id:
            args = ["exec", "resume", "--json", session_id]
        else:
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
        parsed = parse_codex_output(
            result.stdout_lines,
            return_all=return_all_messages,
        )

        # If process failed but parser found no content, include stderr
        if result.returncode != 0 and not parsed.success:
            parsed = parsed.model_copy(update={
                "content": f"(codex exit {result.returncode}): {result.stderr.strip()}"
            })

        return parsed.model_dump_json()

    except asyncio.TimeoutError:
        return CLIResult(success=False, content="codex timed out (300s)").model_dump_json()
    except Exception as e:
        return CLIResult(success=False, content=f"codex error: {e}").model_dump_json()


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
            return CLIResult(success=False, content="gemini CLI not found in PATH").model_dump_json()

        # Build diff context if needed
        diff_text = ""
        if review_uncommitted or review_base:
            diff_text = await get_git_diff(cd, uncommitted=review_uncommitted, base=review_base)

        effective_prompt = _build_effective_prompt(
            prompt, cd=cd,
            review_uncommitted=review_uncommitted,
            review_base=review_base,
            files=files,
            diff_text=diff_text,
        )

        # Build command args
        args = ["-p", effective_prompt, "-o", "stream-json"]
        if sandbox:
            args.append("--sandbox")
        if model:
            args.extend(["--model", model])
        if session_id:
            args.extend(["--resume", session_id])

        result = await run_cli("gemini", args, cwd=cd)
        parsed = parse_gemini_output(
            result.stdout_lines,
            return_all=return_all_messages,
        )

        if result.returncode != 0 and not parsed.success:
            parsed = parsed.model_copy(update={
                "content": f"(gemini exit {result.returncode}): {result.stderr.strip()}"
            })

        return parsed.model_dump_json()

    except asyncio.TimeoutError:
        return CLIResult(success=False, content="gemini timed out (300s)").model_dump_json()
    except Exception as e:
        return CLIResult(success=False, content=f"gemini error: {e}").model_dump_json()


def serve() -> None:
    """Start the MCP server."""
    mcp.run()
