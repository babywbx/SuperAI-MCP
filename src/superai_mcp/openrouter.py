"""Fetch model listings from OpenRouter (no API key required)."""

import asyncio
import json
import time
import urllib.request

OPENROUTER_URL = "https://openrouter.ai/api/v1/models"
PROVIDERS = ("anthropic", "google", "openai")
_TIMEOUT = 15
_CACHE_TTL = 300.0  # 5 minutes

# CLI name → OpenRouter provider prefix
CLI_PROVIDERS = {"codex": "openai", "gemini": "google", "claude": "anthropic"}

# Short aliases each CLI accepts natively (bypass validation)
CLI_ALIASES: dict[str, frozenset[str]] = {
    "codex": frozenset(),
    "gemini": frozenset({"flash", "pro"}),
    "claude": frozenset({"sonnet", "haiku", "opus"}),
}

# In-memory cache: provider → (expires_at, model_id set)
_cache: dict[str, tuple[float, set[str]]] = {}

# Model ID keywords that indicate non-CLI-compatible variants
_EXCLUDE_KEYWORDS = ("image", "customtools")
# Model families under google/ that aren't available via Gemini CLI
_EXCLUDE_PREFIXES = ("google/gemma",)


def _is_cli_compatible(model_id: str) -> bool:
    """Return False for models that won't work with CLI tools."""
    lower = model_id.lower()
    if any(lower.startswith(p) for p in _EXCLUDE_PREFIXES):
        return False
    if any(kw in lower for kw in _EXCLUDE_KEYWORDS):
        return False
    # OpenRouter free-tier routing suffix (e.g. "gemma-3n-e2b-it:free")
    if ":free" in lower:
        return False
    return True


async def fetch_models(provider: str = "") -> list[dict]:
    """Fetch model list from OpenRouter, optionally filtered by provider."""
    cache_key = provider.strip("/").lower() or "_all"
    now = time.monotonic()

    if cache_key in _cache:
        expires, cached = _cache[cache_key]
        if now < expires:
            return cached

    def _fetch() -> dict:
        req = urllib.request.Request(
            OPENROUTER_URL, headers={"User-Agent": "superai-mcp"},
        )
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            return json.loads(resp.read())

    raw = await asyncio.to_thread(_fetch)
    models: list[dict] = raw.get("data", [])

    if provider:
        prefix = provider.rstrip("/") + "/"
        models = [m for m in models if m.get("id", "").startswith(prefix)]
    else:
        # Default: only the 3 main providers
        models = [
            m for m in models
            if any(m.get("id", "").startswith(p + "/") for p in PROVIDERS)
        ]

    models = [m for m in models if _is_cli_compatible(m.get("id", ""))]
    result = [_simplify(m) for m in models]
    _cache[cache_key] = (now + _CACHE_TTL, result)
    return result


def _simplify(m: dict) -> dict:
    """Extract key fields from an OpenRouter model entry."""
    full_id = m.get("id") or ""
    # Strip provider prefix: "anthropic/claude-sonnet-4" → "claude-sonnet-4"
    model_id = full_id.split("/", 1)[1] if "/" in full_id else full_id
    pricing = m.get("pricing", {})
    return {
        "id": full_id,
        "model_id": model_id,
        "name": m.get("name"),
        "context_length": m.get("context_length"),
        "prompt_price": pricing.get("prompt"),
        "completion_price": pricing.get("completion"),
    }


async def check_model(model: str, cli: str) -> str | None:
    """Validate model name against OpenRouter. Returns error message or None.

    Best-effort: if OpenRouter is unreachable, silently passes.
    Known short aliases (e.g. "sonnet", "flash") bypass the check.
    """
    if not model:
        return None
    if model.lower() in CLI_ALIASES.get(cli, frozenset()):
        return None
    provider = CLI_PROVIDERS.get(cli)
    if not provider:
        return None

    try:
        models = await fetch_models(provider)
    except Exception:
        return None  # OpenRouter unreachable, skip validation

    known = {m["model_id"] for m in models}
    if model in known:
        return None

    # Suggest similar model names
    lower = model.lower()
    similar = sorted(m for m in known if lower in m.lower())[:5]
    hint = f"similar: {', '.join(similar)}" if similar else f'use list-models(provider="{provider}")'
    return f"model '{model}' not found for {cli}. {hint}"
