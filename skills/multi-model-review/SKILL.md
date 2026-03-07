---
name: multi-model-review
description: Use when performing code review with multiple AI models, comparing diff reviews, reviewing uncommitted changes, reviewing pull requests, or when the user says "review my code", "code review", "review this PR", "review uncommitted", "compare reviews". Produces aggregated multi-model feedback in a single call.
allowed-tools: [mcp__super__broadcast, mcp__super__codex, mcp__super__gemini, mcp__super__claude]
---

# Multi-Model Code Review

Review code changes by broadcasting to multiple AI models in parallel. One call builds context once and fans out — faster and more consistent than sequential reviews.

## Quick Start

```
# Review uncommitted changes with all CLIs
broadcast(
  prompt="Review this diff for bugs, security issues, and improvements",
  cd="/path/to/project",
  review_uncommitted=True
)

# Review against a branch (e.g. PR review)
broadcast(
  prompt="Review these changes for correctness and style",
  cd="/path/to/project",
  review_base="main"
)

# Review a specific commit
broadcast(
  prompt="Review this commit",
  cd="/path/to/project",
  review_commit="abc1234"
)
```

## Choosing Targets

```
# All three CLIs (default)
broadcast(prompt="...", cd="...", review_uncommitted=True)

# Specific targets
broadcast(prompt="...", cd="...", targets=["codex", "gemini"], review_uncommitted=True)
```

**Recommendation:** Use `targets=["codex", "gemini"]` for code review. Two perspectives are usually sufficient and faster than three.

## Review Modes

| Mode | Parameter | Use Case |
|------|-----------|----------|
| Uncommitted | `review_uncommitted=True` | Review working tree changes before commit |
| Branch diff | `review_base="main"` | Review all changes on a feature branch |
| Commit | `review_commit="abc1234"` | Review a specific commit (7-40 hex SHA) |
| File list | `files=["src/foo.py"]` | Review specific files (relative paths only) |

Modes are mutually exclusive. `files` can combine with review modes to add extra context.

## Per-Target Configuration

```
broadcast(
  prompt="Review this diff",
  cd="/path/to/project",
  review_uncommitted=True,
  models={"gemini": "gemini-3.1-pro-preview"},
  overrides={
    "codex": {"reasoning_effort": "high"},
    "claude": {"effort": "high"}
  }
)
```

## Interpreting Results

The response contains one result per target. Compare them:
- **Agreement** on an issue = high confidence finding
- **Unique findings** = worth investigating
- **Contradictions** = use your judgment, or ask a follow-up

## Best Practices

- Always use `broadcast` instead of calling `codex` + `gemini` + `claude` separately — it builds context once
- For large diffs, add `system_prompt="Focus on critical bugs and security issues only"` to keep output focused
- Save `session_id` from each target's result if you want follow-up questions per model
- Check `success` field for each target — one target failing doesn't block others
