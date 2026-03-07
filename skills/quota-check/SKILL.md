---
name: quota-check
description: Use when checking AI provider rate limits, usage quotas, account capacity, or when the user says "check quota", "am I rate limited", "how much quota left", "check usage limits", "check my limits". Reads local OAuth credentials to query real account-level quotas for Claude, Codex, and Gemini.
allowed-tools: [mcp__super__quota, mcp__super__status]
---

# Quota Checking

Check real account-level usage quotas and rate limits for Claude, Codex, and Gemini. Uses local OAuth credentials (macOS Keychain, auth.json, oauth_creds.json) — no API keys or browser cookies needed.

## Quick Start

```
# Check all providers
quota()

# Check single provider
quota(provider="claude")
quota(provider="codex")
quota(provider="gemini")

# Status with quota info merged in
status(include_quota=True)
```

## What It Returns

Each provider reports:
- **plan_type**: Account plan (e.g. "max", "pro", "free")
- **sessions**: Named quota windows with usage percentages and reset times

### Claude sessions
| Session | Meaning |
|---------|---------|
| `current` | 5-hour rolling window |
| `weekly` | 7-day window |
| `weekly_opus` | 7-day Opus-specific window |
| `weekly_sonnet` | 7-day Sonnet-specific window |

### Codex sessions
| Session | Meaning |
|---------|---------|
| `current` | Primary rate limit window |
| `weekly` | Secondary rate limit window |

### Gemini sessions
| Session | Meaning |
|---------|---------|
| `pro` | Pro model quota (lowest remaining across pro models) |
| `flash` | Flash model quota (lowest remaining across flash models) |

## When to Check

- Before heavy batch work (multiple broadcasts, long chains)
- When a tool returns rate-limit errors
- To decide which provider to route work to (pick the one with most quota remaining)
- Periodically during long sessions to avoid hitting limits

## Credential Sources

| Provider | Source | Fallback |
|----------|--------|----------|
| Claude | macOS Keychain (`Claude Code-credentials`) | `~/.claude/.credentials.json` |
| Codex | `~/.codex/auth.json` (or `$CODEX_HOME`) | — |
| Gemini | `~/.gemini/oauth_creds.json` | Auto-refreshes expired tokens |

If credentials are missing or expired, the result shows `success: false` with a descriptive error — other providers still return normally.
