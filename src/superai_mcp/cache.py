"""In-memory LRU+TTL response cache."""

import hashlib
import os

from cachetools import TTLCache

def _safe_int(val: str, default: int) -> int:
    """Parse int from string, falling back to default on error."""
    try:
        return int(val)
    except (ValueError, TypeError):
        return default


_DEFAULT_TTL = _safe_int(os.environ.get("SUPERAI_MCP_CACHE_TTL", "300"), 300)
_DEFAULT_MAXSIZE = _safe_int(os.environ.get("SUPERAI_MCP_CACHE_MAXSIZE", "128"), 128)

_cache: TTLCache[str, str] = TTLCache(maxsize=_DEFAULT_MAXSIZE, ttl=_DEFAULT_TTL)


def _replace_cache(*, maxsize: int, ttl: float) -> None:
    """Replace the global cache instance (for testing)."""
    global _cache
    _cache = TTLCache(maxsize=maxsize, ttl=ttl)


def cache_key(cli: str, cd: str, prompt: str, model: str) -> str:
    """Build a deterministic cache key from CLI name, directory, prompt, and model."""
    raw = f"{cli}|{cd}|{prompt}|{model}"
    return hashlib.sha256(raw.encode()).hexdigest()


def cache_get(key: str) -> str | None:
    """Get a cached response by key. Returns None on miss."""
    return _cache.get(key)


def cache_put(key: str, value: str) -> None:
    """Store a response in the cache."""
    _cache[key] = value


def cache_clear() -> None:
    """Clear all cached entries."""
    _cache.clear()


def cache_stats() -> dict[str, int]:
    """Return current cache size and max size."""
    return {"size": len(_cache), "maxsize": _cache.maxsize}
