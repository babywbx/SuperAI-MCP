---
description: Check account-level usage quotas for Claude, Codex, and Gemini
allowed-tools: [mcp__super__quota]
---

Call the `quota` tool to check account-level usage quotas.

If the user specified a provider (e.g., `/quota claude`), pass it as the `provider` parameter: $ARGUMENTS

If no argument was given, call with empty provider to check all providers.

Present the results in a clear, readable format showing usage percentages and reset times.
