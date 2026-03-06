"""Quota checking for AI provider accounts."""

from __future__ import annotations

import asyncio

from ._models import QuotaResult, SessionQuota, quota_result_to_dict
from ._claude import fetch_claude_quota
from ._codex import fetch_codex_quota
from ._gemini import fetch_gemini_quota

__all__ = [
    "fetch_quota",
    "fetch_all_quotas",
    "QuotaResult",
    "SessionQuota",
    "quota_result_to_dict",
]

_PROVIDERS = {
    "claude": fetch_claude_quota,
    "codex": fetch_codex_quota,
    "gemini": fetch_gemini_quota,
}


async def fetch_quota(provider: str) -> QuotaResult:
    """Fetch quota for a single provider."""
    fn = _PROVIDERS.get(provider)
    if not fn:
        return QuotaResult(provider=provider, error=f"unknown provider: {provider}")
    return await fn()


async def fetch_all_quotas() -> dict[str, QuotaResult]:
    """Fetch quotas for all providers in parallel."""
    results = await asyncio.gather(
        fetch_claude_quota(),
        fetch_codex_quota(),
        fetch_gemini_quota(),
        return_exceptions=True,
    )
    out: dict[str, QuotaResult] = {}
    for name, r in zip(("claude", "codex", "gemini"), results):
        if isinstance(r, Exception):
            out[name] = QuotaResult(provider=name, error=str(r))
        else:
            out[name] = r
    return out
