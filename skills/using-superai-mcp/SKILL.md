---
name: using-superai-mcp
description: Use when needing multi-model AI assistance, cross-model code review, model comparison, or any task involving codex/gemini/claude CLI tools via MCP. Triggers include "ask codex", "ask gemini", "compare models", "broadcast to all", "chain pipeline", "vote on best answer", "debate between models", or any multi-model collaboration task.
allowed-tools: [mcp__super__codex, mcp__super__gemini, mcp__super__claude, mcp__super__broadcast, mcp__super__chain, mcp__super__vote, mcp__super__debate, mcp__super__list-models, mcp__super__status, mcp__super__usage, mcp__super__quota]
---

# Using SuperAI MCP

## Core Workflow

Every call requires `prompt` + `cd`. Save `session_id` from response for follow-up. Always check the `success` field.

```
codex(prompt="review this file", cd="/path/to/project")
gemini(prompt="analyze this code", cd="/path/to/project", model="gemini-3.1-pro-preview")
claude(prompt="refactor this", cd="/path/to/project")
```

## Tools Quick Reference

| Tool | Purpose | Key Use Case |
|------|---------|-------------|
| `codex` | OpenAI Codex CLI | Code generation, review |
| `gemini` | Google Gemini CLI | Code review, analysis |
| `claude` | Claude CLI (nested) | Code review, complex tasks |
| `broadcast` | Parallel multi-model | **Code review** — send to all, compare |
| `chain` | Sequential pipeline | Multi-step workflows (each step sees previous output) |
| `vote` | Consensus with judge | Pick best answer from candidates |
| `debate` | Alternating rounds | Explore trade-offs between two models |
| `list-models` | Discover models | Find available model IDs from OpenRouter |
| `status` | CLI health check | Verify availability + auth (+ optional quota) |
| `usage` | Token accounting | Track cumulative usage, cache stats, optional reset/clear |
| `quota` | Account-level quotas | Check rate limits before heavy work |

## Model Selection

```
# Single tool — pass model directly
gemini(prompt="...", cd="...", model="gemini-3.1-pro-preview")

# Broadcast — per-target models via models dict (NOT top-level model)
broadcast(prompt="...", cd="...", targets=["codex","gemini"],
          models={"gemini": "gemini-3.1-pro-preview"})

# Per-target overrides for any parameter
broadcast(prompt="...", cd="...",
          overrides={"codex": {"timeout": 600}, "claude": {"effort": "high"}})
```

**Short aliases** bypass validation: `flash`, `pro`, `sonnet`, `haiku`, `opus`.

## Collaboration Tools

**Chain** — sequential pipeline, each step sees previous output:
```
chain(cd="...", steps=[
  {"target": "gemini", "prompt": "Analyze this code"},
  {"target": "claude", "prompt": "Refactor based on analysis"}
])
```

**Vote** — parallel candidates, judge picks best:
```
vote(prompt="...", cd="...", candidates=["codex","gemini"], judge="claude")
```

**Debate** — alternating rounds between two models:
```
debate(prompt="...", cd="...", side_a="codex", side_b="claude", rounds=3)
```

## Common Mistakes

| Mistake | Fix |
|---------|-----|
| Using `model` on `broadcast` | Use `models` dict for per-target; `model` overrides ALL targets |
| Absolute paths in `files` param | Use relative paths within `cd` directory |
| Not saving `session_id` | Store it from response for multi-turn conversations |
| Calling `gemini` without model | Pass `model="gemini-3.1-pro-preview"` for latest |
| Running multiple reviews separately | Use `broadcast` — builds context once, fans out in parallel |
| Repeating identical prompts | Pass `use_cache=True` to reuse cached responses |
| No visibility during long tasks | Pass `stream=True` to get real-time response chunks |

## References

| Reference | When to Read |
|-----------|-------------|
| [references/parameters.md](references/parameters.md) | Full parameter reference for all 11 tools |
