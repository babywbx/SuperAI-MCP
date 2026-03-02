# 🚀 SuperAI MCP

Wraps **Gemini CLI**, **Codex CLI**, and **Claude CLI** as MCP tools, enabling Claude Code to invoke other AI CLIs for code review and coding tasks.

## ✨ Features

- 🔧 **Four tools**: `mcp__super__codex` + `mcp__super__gemini` + `mcp__super__claude` + `mcp__super__broadcast`
- 📋 **Three modes**: prompt forwarding / git diff review / file list review
- 🔄 **Session resume**: continue context via `session_id`
- 🎯 **Model selection**: specify model and reasoning effort
- ⚡ **Pure async**: built on `asyncio.create_subprocess_exec`, no threads
- 🔒 **Secure**: path traversal guard, git ref validation, no shell injection

## 📦 Prerequisites

- Python >= 3.12
- [uv](https://docs.astral.sh/uv/)
- At least one of the following CLIs (uninstalled ones return an error on invocation without affecting others):
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

You can also allow specific tools only: `"mcp__super__codex"`, `"mcp__super__gemini"`, `"mcp__super__claude"`, `"mcp__super__broadcast"`.

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
| `files` | list[str] | `None` | File list mode |
| `return_all_messages` | bool | `False` | Return full event stream |
| `auto_split` | bool | `False` | Auto-split large task into subtasks |

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
| `files` | list[str] | `None` | File list mode |
| `return_all_messages` | bool | `False` | Return full event stream |
| `auto_split` | bool | `False` | Auto-split large task into subtasks |

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
| `files` | list[str] | `None` | File list mode |
| `return_all_messages` | bool | `False` | Return full JSON |
| `auto_split` | bool | `False` | Auto-split large task into subtasks |

### `broadcast`

Broadcast the same prompt to multiple CLIs in parallel, returning aggregated results. Useful for comparing answers across different AI models.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `prompt` | str | required | Task instruction |
| `cd` | str | required | Working directory |
| `targets` | list[str] | `None` | Target CLIs, empty=all (`codex`, `gemini`, `claude`) |
| `model` | str | `""` | Model name passed to each CLI |
| `review_uncommitted` | bool | `False` | Review uncommitted changes |
| `review_base` | str | `""` | Review changes vs a branch |
| `files` | list[str] | `None` | File list mode |
| `return_all_messages` | bool | `False` | Return full event stream |

## 🚦 Usage Modes

```
1️⃣ Default — prompt forwarded directly to CLI
2️⃣ Review — auto-fetch git diff and inject into prompt
3️⃣ Files — read file contents and inject into prompt
```

## 🧪 Testing

```bash
uv run pytest -v
```

## 📄 License

MIT License © 2026 [Babywbx](https://github.com/babywbx)
