# AGENTS.md

Instructions for AI coding agents working with this codebase.

## Package Manager

This project uses **uv** (not pip, poetry, or conda). Always use `uv run` for scripts, `uv add` for dependencies.

## Code Style

- Python 3.12+, pure async (`asyncio.create_subprocess_exec`)
- Code comments in English, short, `//`-style preferred
- No emojis in code or comments
- Zero external dependencies for HTTP — use `urllib.request` + `asyncio.to_thread()`

## Architecture

```
src/superai_mcp/
  server.py       — MCP tool registration, context building, rate-limit fallback
  runner.py       — async subprocess runner (300s timeout + kill)
  parsers.py      — Codex JSONL / Gemini stream-json / Claude stream-json parsers
  splitter.py     — auto_split: decompose large tasks into subtasks
  validate.py     — input validation (cd, sandbox, session_id, model, etc.)
  git_utils.py    — get_git_diff(), read_files() with path traversal guard
  models.py       — CLIResult pydantic model, Sandbox enum
  openrouter.py   — fetch/check models from OpenRouter API (stdlib only)
  quota/          — account-level quota checking (per-provider modules)
```

## Testing

```bash
# All unit tests (371 tests)
uv run pytest -v -m "not integration"

# Integration tests (requires real CLIs + auth)
uv run pytest -v -m integration

# Lint (ruff is not a project dep, use --with)
uv run --with ruff ruff check src/ tests/
```

Test files mirror source structure under `tests/`. Use `unittest.mock` for mocking, `pytest` with `asyncio_mode=auto`.

## Key Conventions

- All errors in quota module converge to `QuotaResult(success=False, error="...")` — never raise
- `_build_context()` in server.py pre-builds review/file context once for broadcast
- Parsers clear accumulated chunks on `tool_use`/`tool_result` events (only keep final answer)
- `_summarize_line()` dispatches by event type for progress display
- `_MAX_STDERR = 500` truncation for error responses
- Large prompts (>200KB) auto-piped via stdin (`_STDIN_THRESHOLD`)

## Documentation

When adding or changing user-facing features (new tools, parameters, behaviors), update **all** of the following:

1. `README.md` — English documentation, tool count, parameter tables
2. `README_ZH.md` — Chinese documentation (mirror of README.md)
3. `skills/using-superai-mcp/SKILL.md` — so AI agents know about the feature
4. `skills/using-superai-mcp/references/parameters.md` — full parameter reference
5. Inline docstrings in `server.py` tool functions

## Commit Messages

`<emoji> <type>(<scope>): <subject>` — single line, English, lowercase subject.

Type-emoji mapping: `feat`->✨, `fix`->🐛, `docs`->📝, `refactor`->♻️, `test`->✅, `chore`->🔧, `revert`->⏪
