# SuperAI MCP Parameter Reference

## Common Parameters (codex, gemini, claude)

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `prompt` | str | required | Task instruction |
| `cd` | str | required | Working directory |
| `session_id` | str | `""` | Resume previous session |
| `model` | str | `""` | Model name or alias |
| `review_uncommitted` | bool | `False` | Review uncommitted git changes |
| `review_base` | str | `""` | Review diff vs a branch (e.g. `"main"`) |
| `review_commit` | str | `""` | Review specific commit (7-40 hex SHA) |
| `files` | list[str] | `None` | Read file contents into context (relative paths only) |
| `return_all_messages` | bool | `False` | Return full event stream |
| `auto_split` | bool | `False` | Auto-split large task into subtasks |
| `system_prompt` | str | `""` | System-level instruction |
| `use_cache` | bool | `False` | Return cached response for identical prompt+model |
| `stream` | bool | `False` | Push response chunks in real-time via `ctx.info()` |
| `timeout` | float | `300` | Timeout in seconds |

## CLI-Specific Parameters

### codex only

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `sandbox` | str | `"read-only"` | Sandbox mode |
| `reasoning_effort` | str | `""` | `low`/`medium`/`high`/`xhigh` |

### gemini only

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `sandbox` | bool | `True` | Enable sandbox |

### claude only

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `sandbox` | str | `"read-only"` | Sandbox / permission mode |
| `effort` | str | `""` | `low`/`medium`/`high` |
| `max_budget_usd` | float | `0.0` | API cost limit (0=unlimited) |

## broadcast

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `prompt` | str | required | Task instruction |
| `cd` | str | required | Working directory |
| `targets` | list[str] | `None` | Target CLIs, empty=all |
| `model` | str | `""` | Global model override (applies to ALL targets) |
| `models` | dict[str,str] | `None` | Per-target model, e.g. `{"gemini": "..."}` |
| `overrides` | dict[str,dict] | `None` | Per-target parameter overrides |

Model priority: `overrides` > `models` > `model` > default.

Context parameters (`review_*`, `files`) are pre-built once and cannot be overridden per-target.

## chain

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `steps` | list[dict] | required | `[{target, prompt, model?}, ...]` |
| `cd` | str | required | Working directory |
| `system_prompt` | str | `""` | System-level instruction |
| `timeout` | float | `300` | End-to-end timeout budget |

## vote

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `prompt` | str | required | Task instruction |
| `cd` | str | required | Working directory |
| `candidates` | list[str] | `None` | Candidate CLIs, empty=all |
| `judge` | str | `"claude"` | Judge CLI (auto-excluded from candidates) |

## debate

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `prompt` | str | required | Debate topic |
| `cd` | str | required | Working directory |
| `side_a` | str | `"codex"` | Side A CLI |
| `side_b` | str | `"claude"` | Side B CLI |
| `rounds` | int | `3` | Number of rounds |

## list-models

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `provider` | str | `""` | Filter: `openai`/`google`/`anthropic`/empty=all |

## status

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `include_quota` | bool | `False` | Also fetch account-level quotas |

## quota

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `provider` | str | `""` | `claude`/`codex`/`gemini`/empty=all |

## usage

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `reset` | bool | `False` | Clear counters after reading |
| `clear_cache` | bool | `False` | Clear the response cache |
