# 🚀 SuperAI MCP

[![Python](https://img.shields.io/badge/Python-3.12+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![MCP](https://img.shields.io/badge/MCP-FastMCP-8A2BE2)](https://modelcontextprotocol.io/)
[![Claude Code](https://img.shields.io/badge/Claude_Code-compatible-cc785c?logo=anthropic&logoColor=white)](https://github.com/anthropics/claude-code)
[![Codex CLI](https://img.shields.io/badge/Codex_CLI-compatible-74aa9c?logo=openai&logoColor=white)](https://github.com/openai/codex)
[![Gemini CLI](https://img.shields.io/badge/Gemini_CLI-compatible-4285F4?logo=google&logoColor=white)](https://github.com/google-gemini/gemini-cli)

[中文](README_ZH.md)

Wraps **Gemini CLI**, **Codex CLI**, and **Claude CLI** as MCP tools, enabling Claude Code to invoke other AI CLIs for code review and coding tasks.

## ✨ Features

- 🔧 **11 tools**: `codex` + `gemini` + `claude` + `broadcast` + `chain` + `vote` + `debate` + `list-models` + `status` + `usage` + `quota`
- 📋 **5 modes**: prompt forwarding / git diff review (uncommitted/base/commit) / file list review
- 🔄 **Session resume**: continue context via `session_id`
- 🎯 **Model selection**: specify model and reasoning effort
- ⚡ **Pure async**: built on `asyncio.create_subprocess_exec` (quota/network helpers use `asyncio.to_thread`)
- 🔍 **Model discovery**: `list-models` queries available models in real-time, `model` param auto-validates with correction suggestions
- 🔒 **Secure**: path traversal guard, git ref validation, no shell injection, nesting depth limit (max 5)
- 📡 **Progress notifications**: `report_progress` keepalive every 5s during long tasks
- ⏱️ **Timeout + grace period**: 300s default timeout, auto-extends when CLI is actively producing output (30s for new output / 120s for keyword match)
- 🔄 **Rate-limit fallback**: automatic cascading degradation (Gemini→flash / Claude→sonnet→haiku / Codex effort downgrade)
- 📝 **System prompt**: `system_prompt` param injects system-level instructions
- 📦 **Large prompt support**: >200KB auto-piped via stdin to avoid OS ARG_MAX limits
- 🏷️ **Tool annotations**: every tool includes `ToolAnnotations` metadata
- 🤝 **Multi-model collaboration**: `chain` pipeline / `vote` consensus / `debate` iteration
- 📊 **Quota checking**: real-time account-level usage quotas via local OAuth credentials (Claude/Codex/Gemini)

## 📦 Prerequisites

- Python >= 3.12
- [uv](https://docs.astral.sh/uv/)
- At least one of the following CLIs (invoking an uninstalled CLI returns an error without affecting the others):
  - [Codex CLI](https://github.com/openai/codex) — `npm install -g @openai/codex`
  - [Gemini CLI](https://github.com/google-gemini/gemini-cli) — `npm install -g @google/gemini-cli`
  - [Claude Code](https://github.com/anthropics/claude-code) — `curl -fsSL https://claude.ai/install.sh | bash` or `brew install --cask claude-code`

## 🔌 Installation & Configuration

### Claude Code

```bash
# Install from Git (recommended)
claude mcp add super -s user --transport stdio -- uvx --from git+https://github.com/babywbx/SuperAI-MCP.git superai-mcp

# Or clone and install locally
git clone https://github.com/babywbx/SuperAI-MCP.git
claude mcp add super -s user --transport stdio -- uv run --directory /path/to/SuperAI-MCP superai-mcp
```

<details>
<summary>Edit config manually</summary>

Add to `~/.claude/mcp.json` (global) or `.mcp.json` (project-level):

```json
{
  "mcpServers": {
    "super": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/babywbx/SuperAI-MCP.git", "superai-mcp"]
    }
  }
}
```

</details>

<details>
<summary>Optional: auto-allow tool calls (skip confirmation prompts)</summary>

Add to `~/.claude/settings.json`:

```json
{
  "permissions": {
    "allow": [
      "mcp__super"
    ]
  }
}
```

You can also allow specific tools only: `"mcp__super__codex"`, `"mcp__super__gemini"`, `"mcp__super__claude"`, `"mcp__super__broadcast"`, `"mcp__super__chain"`, `"mcp__super__vote"`, `"mcp__super__debate"`, `"mcp__super__list-models"`, `"mcp__super__status"`, `"mcp__super__usage"`, `"mcp__super__quota"`.

</details>

### Codex CLI

Add to `~/.codex/config.toml`:

```toml
[mcp_servers.super]
command = "uvx"
args = ["--from", "git+https://github.com/babywbx/SuperAI-MCP.git", "superai-mcp"]
```

### Gemini CLI

```bash
gemini mcp add super -- uvx --from git+https://github.com/babywbx/SuperAI-MCP.git superai-mcp
```

<details>
<summary>Edit config manually</summary>

Add to `~/.gemini/settings.json`:

```json
{
  "mcpServers": {
    "super": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/babywbx/SuperAI-MCP.git", "superai-mcp"]
    }
  }
}
```

</details>

Restart the CLI after configuration.

## 🛠️ Tool Parameters

### `codex`

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `prompt` | str | required | Task instruction |
| `cd` | str | required | Working directory |
| `session_id` | str | `""` | Resume session |
| `sandbox` | str | `"read-only"` | Sandbox mode |
| `model` | str | `""` | Model name |
| `reasoning_effort` | str | `""` | Reasoning depth: low/medium/high/xhigh |
| `review_uncommitted` | bool | `False` | Review uncommitted changes |
| `review_base` | str | `""` | Review changes vs a branch |
| `review_commit` | str | `""` | Review specific commit (7-40 hex SHA) |
| `files` | list[str] | `None` | File list mode |
| `return_all_messages` | bool | `False` | Return full event stream |
| `auto_split` | bool | `False` | Auto-split large task into subtasks |
| `system_prompt` | str | `""` | System-level instruction (injected as `<system>` tag) |
| `timeout` | float | `300` | Timeout in seconds |

### `gemini`

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `prompt` | str | required | Task instruction |
| `cd` | str | required | Working directory |
| `session_id` | str | `""` | Resume session |
| `sandbox` | bool | `True` | Enable sandbox |
| `model` | str | `""` | Model name/alias (pro, flash, etc.) |
| `review_uncommitted` | bool | `False` | Review uncommitted changes |
| `review_base` | str | `""` | Review changes vs a branch |
| `review_commit` | str | `""` | Review specific commit (7-40 hex SHA) |
| `files` | list[str] | `None` | File list mode |
| `return_all_messages` | bool | `False` | Return full event stream |
| `auto_split` | bool | `False` | Auto-split large task into subtasks |
| `system_prompt` | str | `""` | System-level instruction (injected as `<system>` tag) |
| `timeout` | float | `300` | Timeout in seconds |

### `claude`

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `prompt` | str | required | Task instruction |
| `cd` | str | required | Working directory |
| `session_id` | str | `""` | Resume session (maps to --resume) |
| `sandbox` | str | `"read-only"` | Sandbox mode (maps to permission mode) |
| `model` | str | `""` | Model name (opus/sonnet/haiku, etc.) |
| `effort` | str | `""` | Effort level: low/medium/high |
| `max_budget_usd` | float | `0.0` | API cost limit (0=unlimited) |
| `review_uncommitted` | bool | `False` | Review uncommitted changes |
| `review_base` | str | `""` | Review changes vs a branch |
| `review_commit` | str | `""` | Review specific commit (7-40 hex SHA) |
| `files` | list[str] | `None` | File list mode |
| `return_all_messages` | bool | `False` | Return full JSON |
| `auto_split` | bool | `False` | Auto-split large task into subtasks |
| `system_prompt` | str | `""` | System-level instruction (injected as `<system>` tag) |
| `timeout` | float | `300` | Timeout in seconds |

### `broadcast`

Broadcast the same prompt to multiple CLIs in parallel, returning aggregated results. Useful for comparing answers across different AI models.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `prompt` | str | required | Task instruction |
| `cd` | str | required | Working directory |
| `targets` | list[str] | `None` | Target CLIs, empty=all (`codex`, `gemini`, `claude`) |
| `model` | str | `""` | Model name passed to all CLIs (global override) |
| `models` | dict[str,str] | `None` | Per-CLI model override, e.g. `{"gemini": "gemini-3.1-pro-preview"}` |
| `overrides` | dict[str,dict] | `None` | Per-CLI parameter overrides (see below) |
| `review_uncommitted` | bool | `False` | Review uncommitted changes |
| `review_base` | str | `""` | Review changes vs a branch |
| `review_commit` | str | `""` | Review specific commit (7-40 hex SHA) |
| `files` | list[str] | `None` | File list mode |
| `return_all_messages` | bool | `False` | Return full event stream |
| `system_prompt` | str | `""` | System-level instruction (injected as `<system>` tag) |
| `timeout` | float | `300` | Timeout in seconds |

**Per-target overrides**: Use `overrides` to set any tool parameter individually per CLI target. Top-level parameters serve as defaults; `overrides` values take precedence. Priority for model: `overrides` > `models` > `model`.

```json
{
  "overrides": {
    "codex": {"timeout": 600, "reasoning_effort": "high"},
    "gemini": {"timeout": 120, "system_prompt": "be concise"},
    "claude": {"timeout": 900, "effort": "high", "max_budget_usd": 5.0}
  }
}
```

> **Note**: Context-building parameters (`review_uncommitted`, `review_base`, `review_commit`, `files`) are pre-built once and cannot be overridden per-target.

### `chain`

Sequential multi-model pipeline. Each step's output is auto-injected into the next (wrapped in `<previous_output>` tags). Stops on first failure and returns partial results.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `steps` | list[dict] | required | Steps list, each `{target, prompt, model?}` |
| `cd` | str | required | Working directory |
| `system_prompt` | str | `""` | System-level instruction |
| `timeout` | float | `300` | Total timeout in seconds (end-to-end budget) |

### `vote`

Send prompt to multiple candidate models in parallel, then have a judge model pick the best answer.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `prompt` | str | required | Task instruction |
| `cd` | str | required | Working directory |
| `candidates` | list[str] | `None` | Candidate CLIs, empty=all |
| `judge` | str | `"claude"` | Judge CLI (auto-excluded from candidates) |
| `model` | str | `""` | Model name |
| `system_prompt` | str | `""` | System-level instruction |
| `timeout` | float | `300` | Total timeout in seconds |

### `debate`

Alternating debate between two models over multiple rounds. Each round sees the opponent's previous response (wrapped in `<opponent_response>` tags).

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `prompt` | str | required | Debate topic / task instruction |
| `cd` | str | required | Working directory |
| `side_a` | str | `"codex"` | Side A CLI |
| `side_b` | str | `"claude"` | Side B CLI |
| `rounds` | int | `3` | Number of debate rounds |
| `model` | str | `""` | Model name |
| `system_prompt` | str | `""` | System-level instruction |
| `timeout` | float | `300` | Total timeout in seconds |

### `list-models`

Query available models from OpenRouter (covers OpenAI, Google, Anthropic). No API key needed, results cached for 5 minutes.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `provider` | str | `""` | Filter by provider: `openai`, `google`, `anthropic`, or empty for all |

The returned `model_id` can be used directly as the `model` parameter for other tools. Automatically filters out CLI-incompatible variants (image, customtools, gemma, :free, etc.).

> **⚠️ Note**: Data comes from OpenRouter — **not all returned models are guaranteed to work with the corresponding CLI**. This is a discovery aid; actual availability depends on each CLI. As of March 2026, verified latest models:
>
> | CLI | Latest Verified Model |
> |-----|----------------------|
> | Gemini | `gemini-3.1-pro-preview` |
> | Codex | `gpt-5.3-codex` |
> | Claude | `claude-opus-4-6` |

### `status`

Check availability, version, and authentication status of all CLI tools.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `include_quota` | bool | `False` | Also fetch account-level usage quotas for each provider |

### `quota`

Check real account-level usage quotas and rate limits. Reads local OAuth credentials (Keychain, auth.json, oauth_creds.json) — no API keys or browser cookies needed.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `provider` | str | `""` | Provider to check: `claude`, `codex`, `gemini`, or empty for all |

### `usage`

Show cumulative token usage and call counts across all CLI tools.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `reset` | bool | `False` | Clear counters after reading |

## 🔍 Model Validation

When a `model` parameter is provided, the tool validates the model name against an OpenRouter cache. This is an advisory feature — passing validation doesn't guarantee CLI support, but **failing validation likely indicates a typo**.

- **Model exists** → proceed normally
- **Model not found** → instant error + similar model suggestions
- **Short aliases** (`flash`, `pro`, `sonnet`, `haiku`, `opus`) → bypass validation, pass directly to CLI
- **OpenRouter unreachable** → silently skip validation, don't block the request

## 🚦 Usage Modes

```
1️⃣ Default — prompt forwarded directly to CLI
2️⃣ Review — auto-fetch git diff and inject into prompt (uncommitted / base / commit)
3️⃣ Files — read file contents and inject into prompt
```

## 🔄 Rate-Limit Fallback

When a CLI returns a rate-limit error (`RESOURCE_EXHAUSTED`, `overloaded_error`, `429`, `rate_limit`, `quota`, etc.), the tool automatically cascades to a fallback. Before fallback, a short probe request verifies the target is reachable.

| CLI | Fallback Strategy | Example |
|-----|-------------------|---------|
| **Gemini** | Switch to `flash` model | `pro` → `flash` |
| **Claude** | Model downgrade | current → `sonnet` → `haiku` |
| **Codex** | Reduce reasoning effort | `high` → `medium` → `low` |

On success, the response is prefixed with `[fallback: ...]` (e.g. `[fallback: sonnet]`, `[fallback: effort=medium]`).
If already at the end of the chain (Gemini already on `flash`, Claude on `haiku`, Codex on `low`), no retry is attempted.

## 📡 Progress Notifications

During CLI execution, an MCP `report_progress` keepalive is sent every 5 seconds, including elapsed time and a current status summary.
This prevents clients from timing out and disconnecting during long-running tasks.

## 🧪 Testing

```bash
uv run pytest -v
```

## 📄 License

Apache-2.0 License © 2026 [Babywbx](https://github.com/babywbx)
