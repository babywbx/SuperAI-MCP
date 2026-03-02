# 🚀 SuperAI MCP

Wraps **Gemini CLI**, **Codex CLI**, and **Claude CLI** as MCP tools, enabling Claude Code to invoke other AI CLIs for code review and coding tasks.

## ✨ Features

- 🔧 **Triple tools**: `mcp__super__codex` + `mcp__super__gemini` + `mcp__super__claude`
- 📋 **Three modes**: prompt forwarding / git diff review / file list review
- 🔄 **Session resume**: continue context via `session_id`
- 🎯 **Model selection**: specify model and reasoning effort
- ⚡ **Pure async**: built on `asyncio.create_subprocess_exec`, no threads
- 🔒 **Secure**: path traversal guard, git ref validation, no shell injection

## 📦 Installation

```bash
# Requires Python >= 3.12 and uv
uv sync
```

## 🔌 Claude Code Configuration

Add to `.mcp.json`:

```json
{
  "mcpServers": {
    "super": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/SuperAI-MCP", "superai-mcp"]
    }
  }
}
```

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

MIT
