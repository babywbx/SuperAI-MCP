"""Tests for the in-memory LRU+TTL response cache."""

import time

from superai_mcp.cache import (
    cache_clear,
    cache_get,
    cache_key,
    cache_put,
    cache_stats,
)


class TestCacheKey:
    def test_deterministic(self) -> None:
        k1 = cache_key("codex", "/tmp", "hello", "gpt-4")
        k2 = cache_key("codex", "/tmp", "hello", "gpt-4")
        assert k1 == k2

    def test_different_prompt(self) -> None:
        k1 = cache_key("codex", "/tmp", "hello", "gpt-4")
        k2 = cache_key("codex", "/tmp", "world", "gpt-4")
        assert k1 != k2

    def test_different_model(self) -> None:
        k1 = cache_key("codex", "/tmp", "hello", "gpt-4")
        k2 = cache_key("codex", "/tmp", "hello", "claude")
        assert k1 != k2

    def test_different_cli(self) -> None:
        k1 = cache_key("codex", "/tmp", "hello", "")
        k2 = cache_key("claude", "/tmp", "hello", "")
        assert k1 != k2

    def test_different_cd(self) -> None:
        k1 = cache_key("codex", "/project_a", "hello", "")
        k2 = cache_key("codex", "/project_b", "hello", "")
        assert k1 != k2

    def test_empty_model(self) -> None:
        k1 = cache_key("codex", "/tmp", "hello", "")
        k2 = cache_key("codex", "/tmp", "hello", "")
        assert k1 == k2

    def test_returns_hex_string(self) -> None:
        k = cache_key("codex", "/tmp", "test", "model")
        assert isinstance(k, str)
        assert len(k) == 64  # sha256 hex digest


class TestCacheGetPut:
    def setup_method(self) -> None:
        cache_clear()

    def test_miss_returns_none(self) -> None:
        assert cache_get("nonexistent") is None

    def test_put_then_get(self) -> None:
        cache_put("k1", '{"success": true}')
        assert cache_get("k1") == '{"success": true}'

    def test_overwrite(self) -> None:
        cache_put("k1", "old")
        cache_put("k1", "new")
        assert cache_get("k1") == "new"

    def test_clear(self) -> None:
        cache_put("k1", "v1")
        cache_put("k2", "v2")
        cache_clear()
        assert cache_get("k1") is None
        assert cache_get("k2") is None


class TestCacheStats:
    def setup_method(self) -> None:
        cache_clear()

    def test_empty(self) -> None:
        stats = cache_stats()
        assert stats["size"] == 0
        assert stats["maxsize"] == 128

    def test_after_put(self) -> None:
        cache_put("k1", "v1")
        cache_put("k2", "v2")
        assert cache_stats()["size"] == 2


class TestCacheTTL:
    def setup_method(self) -> None:
        cache_clear()

    def test_expired_entry_returns_none(self) -> None:
        from superai_mcp.cache import _replace_cache
        _replace_cache(maxsize=128, ttl=0.1)
        try:
            cache_put("k1", "v1")
            assert cache_get("k1") == "v1"
            time.sleep(0.15)
            assert cache_get("k1") is None
        finally:
            _replace_cache(maxsize=128, ttl=300)


class TestCacheLRU:
    def setup_method(self) -> None:
        cache_clear()

    def test_evicts_lru_when_full(self) -> None:
        from superai_mcp.cache import _replace_cache
        _replace_cache(maxsize=3, ttl=300)
        try:
            cache_put("k1", "v1")
            cache_put("k2", "v2")
            cache_put("k3", "v3")
            cache_get("k1")  # access k1 to make k2 the LRU
            cache_put("k4", "v4")  # should evict k2
            assert cache_get("k1") == "v1"
            assert cache_get("k2") is None  # evicted
            assert cache_get("k3") == "v3"
            assert cache_get("k4") == "v4"
        finally:
            _replace_cache(maxsize=128, ttl=300)
