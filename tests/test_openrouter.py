"""Unit tests for openrouter module."""

import json
from unittest.mock import MagicMock, patch
from urllib.error import URLError

import pytest

from superai_mcp.openrouter import (
    PROVIDERS,
    _cache,
    _is_cli_compatible,
    _simplify,
    check_model,
    fetch_models,
)

# Realistic sample data from OpenRouter API
_SAMPLE_DATA = {
    "data": [
        {
            "id": "anthropic/claude-sonnet-4",
            "name": "Claude Sonnet 4",
            "context_length": 200000,
            "pricing": {"prompt": "0.000003", "completion": "0.000015"},
        },
        {
            "id": "google/gemini-2.5-pro",
            "name": "Gemini 2.5 Pro",
            "context_length": 1048576,
            "pricing": {"prompt": "0.00000125", "completion": "0.00001"},
        },
        {
            "id": "openai/gpt-4.1",
            "name": "GPT-4.1",
            "context_length": 1047576,
            "pricing": {"prompt": "0.000002", "completion": "0.000008"},
        },
        {
            "id": "meta-llama/llama-4-maverick",
            "name": "Llama 4 Maverick",
            "context_length": 131072,
            "pricing": {"prompt": "0.0000002", "completion": "0.0000008"},
        },
        {
            "id": "google/gemini-3.1-flash-image-preview",
            "name": "Gemini 3.1 Flash (Image)",
            "context_length": 65536,
            "pricing": {"prompt": "0.000001", "completion": "0.000004"},
        },
        {
            "id": "google/gemini-3.1-pro-preview-customtools",
            "name": "Gemini 3.1 Pro (Custom Tools)",
            "context_length": 1048576,
            "pricing": {"prompt": "0.000002", "completion": "0.00001"},
        },
        {
            "id": "google/gemma-3-27b-it:free",
            "name": "Gemma 3 27B (Free)",
            "context_length": 131072,
            "pricing": {"prompt": "0", "completion": "0"},
        },
        {
            "id": "google/gemma-3-27b-it",
            "name": "Gemma 3 27B",
            "context_length": 128000,
            "pricing": {"prompt": "0.0000001", "completion": "0.0000002"},
        },
    ]
}


@pytest.fixture(autouse=True)
def _clear_cache():
    """Clear the module-level cache before each test."""
    _cache.clear()
    yield
    _cache.clear()


def _mock_urlopen(data: dict = _SAMPLE_DATA):
    """Create a mock for urllib.request.urlopen returning given data."""
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(data).encode()
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    return mock_resp


class TestFetchModelsDefaultFilter:
    """Default (no provider) returns only the 3 main providers."""

    async def test_filters_to_three_providers(self) -> None:
        with patch("superai_mcp.openrouter.urllib.request.urlopen", return_value=_mock_urlopen()):
            models = await fetch_models()

        ids = [m["id"] for m in models]
        assert "anthropic/claude-sonnet-4" in ids
        assert "google/gemini-2.5-pro" in ids
        assert "openai/gpt-4.1" in ids
        # meta-llama should be excluded
        assert "meta-llama/llama-4-maverick" not in ids

    async def test_count_matches(self) -> None:
        with patch("superai_mcp.openrouter.urllib.request.urlopen", return_value=_mock_urlopen()):
            models = await fetch_models()

        assert len(models) == 3


class TestFetchModelsProviderFilter:
    """Provider-specific filtering."""

    async def test_filter_anthropic(self) -> None:
        with patch("superai_mcp.openrouter.urllib.request.urlopen", return_value=_mock_urlopen()):
            models = await fetch_models("anthropic")

        assert len(models) == 1
        assert models[0]["id"] == "anthropic/claude-sonnet-4"

    async def test_filter_google(self) -> None:
        with patch("superai_mcp.openrouter.urllib.request.urlopen", return_value=_mock_urlopen()):
            models = await fetch_models("google")

        assert len(models) == 1
        assert models[0]["id"] == "google/gemini-2.5-pro"

    async def test_filter_openai(self) -> None:
        with patch("superai_mcp.openrouter.urllib.request.urlopen", return_value=_mock_urlopen()):
            models = await fetch_models("openai")

        assert len(models) == 1
        assert models[0]["id"] == "openai/gpt-4.1"

    async def test_filter_nonexistent_provider(self) -> None:
        with patch("superai_mcp.openrouter.urllib.request.urlopen", return_value=_mock_urlopen()):
            models = await fetch_models("nonexistent")

        assert models == []

    async def test_trailing_slash_stripped(self) -> None:
        with patch("superai_mcp.openrouter.urllib.request.urlopen", return_value=_mock_urlopen()):
            models = await fetch_models("anthropic/")

        assert len(models) == 1
        assert models[0]["id"] == "anthropic/claude-sonnet-4"


class TestSimplify:
    """_simplify extracts the right fields."""

    def test_extracts_all_fields(self) -> None:
        m = {
            "id": "openai/gpt-4.1",
            "name": "GPT-4.1",
            "context_length": 1047576,
            "pricing": {"prompt": "0.000002", "completion": "0.000008"},
            "extra_field": "ignored",
        }
        result = _simplify(m)
        assert result == {
            "id": "openai/gpt-4.1",
            "model_id": "gpt-4.1",
            "name": "GPT-4.1",
            "context_length": 1047576,
            "prompt_price": "0.000002",
            "completion_price": "0.000008",
        }

    def test_model_id_strips_provider(self) -> None:
        assert _simplify({"id": "anthropic/claude-sonnet-4"})["model_id"] == "claude-sonnet-4"
        assert _simplify({"id": "google/gemini-2.5-pro"})["model_id"] == "gemini-2.5-pro"
        assert _simplify({"id": "openai/gpt-4.1"})["model_id"] == "gpt-4.1"

    def test_model_id_no_slash(self) -> None:
        assert _simplify({"id": "bare-model"})["model_id"] == "bare-model"

    def test_missing_pricing(self) -> None:
        m = {"id": "test/model", "name": "Test", "context_length": 1024}
        result = _simplify(m)
        assert result["prompt_price"] is None
        assert result["completion_price"] is None

    def test_empty_dict(self) -> None:
        result = _simplify({})
        assert result["id"] == ""
        assert result["model_id"] == ""
        assert result["name"] is None
        assert result["context_length"] is None


class TestFetchModelsErrorHandling:
    """Network and data errors."""

    async def test_network_error_propagates(self) -> None:
        with patch(
            "superai_mcp.openrouter.urllib.request.urlopen",
            side_effect=URLError("connection refused"),
        ):
            with pytest.raises(URLError):
                await fetch_models()

    async def test_empty_data_array(self) -> None:
        with patch(
            "superai_mcp.openrouter.urllib.request.urlopen",
            return_value=_mock_urlopen({"data": []}),
        ):
            models = await fetch_models()

        assert models == []

    async def test_missing_data_key(self) -> None:
        with patch(
            "superai_mcp.openrouter.urllib.request.urlopen",
            return_value=_mock_urlopen({}),
        ):
            models = await fetch_models()

        assert models == []


class TestListModelsTool:
    """Test the MCP tool wrapper in server.py."""

    async def test_tool_success(self) -> None:
        from superai_mcp.server import list_models_tool

        with patch("superai_mcp.openrouter.urllib.request.urlopen", return_value=_mock_urlopen()):
            raw = await list_models_tool()

        result = json.loads(raw)
        assert result["success"] is True
        assert result["count"] == 3
        assert len(result["models"]) == 3

    async def test_tool_with_provider(self) -> None:
        from superai_mcp.server import list_models_tool

        with patch("superai_mcp.openrouter.urllib.request.urlopen", return_value=_mock_urlopen()):
            raw = await list_models_tool(provider="anthropic")

        result = json.loads(raw)
        assert result["success"] is True
        assert result["count"] == 1

    async def test_tool_error_returns_json(self) -> None:
        from superai_mcp.server import list_models_tool

        with patch(
            "superai_mcp.openrouter.urllib.request.urlopen",
            side_effect=URLError("timeout"),
        ):
            raw = await list_models_tool()

        result = json.loads(raw)
        assert result["success"] is False
        assert "Failed to fetch models" in result["content"]


class TestIsCliCompatible:
    """_is_cli_compatible filters non-CLI model variants."""

    def test_normal_models_pass(self) -> None:
        assert _is_cli_compatible("google/gemini-2.5-pro") is True
        assert _is_cli_compatible("anthropic/claude-sonnet-4") is True
        assert _is_cli_compatible("openai/gpt-4.1") is True
        assert _is_cli_compatible("google/gemini-3-flash-preview") is True

    def test_image_variants_excluded(self) -> None:
        assert _is_cli_compatible("google/gemini-3.1-flash-image-preview") is False
        assert _is_cli_compatible("google/gemini-2.5-flash-image") is False

    def test_customtools_excluded(self) -> None:
        assert _is_cli_compatible("google/gemini-3.1-pro-preview-customtools") is False

    def test_gemma_excluded(self) -> None:
        assert _is_cli_compatible("google/gemma-3-27b-it") is False
        assert _is_cli_compatible("google/gemma-3n-e4b-it") is False

    def test_free_tier_excluded(self) -> None:
        assert _is_cli_compatible("google/gemma-3-27b-it:free") is False

    def test_case_insensitive(self) -> None:
        assert _is_cli_compatible("google/Gemini-Image-Model") is False


class TestFetchModelsExcludesIncompatible:
    """fetch_models filters out non-CLI-compatible variants."""

    async def test_google_excludes_variants(self) -> None:
        with patch("superai_mcp.openrouter.urllib.request.urlopen", return_value=_mock_urlopen()):
            models = await fetch_models("google")

        ids = [m["id"] for m in models]
        # Only gemini-2.5-pro should survive
        assert "google/gemini-2.5-pro" in ids
        assert "google/gemini-3.1-flash-image-preview" not in ids
        assert "google/gemini-3.1-pro-preview-customtools" not in ids
        assert "google/gemma-3-27b-it:free" not in ids
        assert "google/gemma-3-27b-it" not in ids

    async def test_default_excludes_variants(self) -> None:
        with patch("superai_mcp.openrouter.urllib.request.urlopen", return_value=_mock_urlopen()):
            models = await fetch_models()

        ids = [m["id"] for m in models]
        assert "google/gemini-3.1-flash-image-preview" not in ids
        assert "google/gemma-3-27b-it" not in ids


class TestCheckModel:
    """check_model validates model names against OpenRouter data."""

    async def test_valid_model_passes(self) -> None:
        with patch("superai_mcp.openrouter.urllib.request.urlopen", return_value=_mock_urlopen()):
            result = await check_model("gemini-2.5-pro", "gemini")
        assert result is None

    async def test_invalid_model_returns_error(self) -> None:
        with patch("superai_mcp.openrouter.urllib.request.urlopen", return_value=_mock_urlopen()):
            result = await check_model("gemini-9999", "gemini")
        assert result is not None
        assert "not found" in result

    async def test_invalid_model_suggests_similar(self) -> None:
        with patch("superai_mcp.openrouter.urllib.request.urlopen", return_value=_mock_urlopen()):
            result = await check_model("gemini-2.5", "gemini")
        assert result is not None
        assert "gemini-2.5-pro" in result

    async def test_alias_bypasses_check(self) -> None:
        # "flash" is a known Gemini alias — should pass without hitting OpenRouter
        with patch("superai_mcp.openrouter.urllib.request.urlopen") as mock:
            result = await check_model("flash", "gemini")
        assert result is None
        mock.assert_not_called()

    async def test_claude_alias_bypasses(self) -> None:
        with patch("superai_mcp.openrouter.urllib.request.urlopen") as mock:
            result = await check_model("sonnet", "claude")
        assert result is None
        mock.assert_not_called()

    async def test_empty_model_passes(self) -> None:
        result = await check_model("", "gemini")
        assert result is None

    async def test_openrouter_down_passes(self) -> None:
        with patch(
            "superai_mcp.openrouter.urllib.request.urlopen",
            side_effect=URLError("timeout"),
        ):
            result = await check_model("unknown-model", "gemini")
        assert result is None  # best-effort, don't block

    async def test_unknown_cli_passes(self) -> None:
        result = await check_model("some-model", "unknown-cli")
        assert result is None


class TestCache:
    """fetch_models caches results with TTL."""

    async def test_second_call_uses_cache(self) -> None:
        mock = _mock_urlopen()
        with patch("superai_mcp.openrouter.urllib.request.urlopen", return_value=mock):
            await fetch_models("google")
            await fetch_models("google")
        # urlopen should be called only once
        mock.read.assert_called_once()

    async def test_different_providers_cached_separately(self) -> None:
        with patch("superai_mcp.openrouter.urllib.request.urlopen", return_value=_mock_urlopen()) as mock:
            await fetch_models("google")
            await fetch_models("anthropic")
        assert mock.call_count == 2

    async def test_cache_expires(self) -> None:
        with patch("superai_mcp.openrouter.urllib.request.urlopen", return_value=_mock_urlopen()) as mock:
            await fetch_models("google")
            # Expire the cache
            for key in _cache:
                _cache[key] = (0.0, _cache[key][1])
            await fetch_models("google")
        assert mock.call_count == 2


class TestProviderCaseNormalization:
    """Provider input is case-insensitive and won't poison cache."""

    async def test_uppercase_provider_matches(self) -> None:
        with patch("superai_mcp.openrouter.urllib.request.urlopen", return_value=_mock_urlopen()):
            models = await fetch_models("Anthropic")
        assert len(models) == 1
        assert models[0]["id"] == "anthropic/claude-sonnet-4"

    async def test_mixed_case_shares_cache(self) -> None:
        """'Google' and 'google' should share the same cache entry."""
        mock = _mock_urlopen()
        with patch("superai_mcp.openrouter.urllib.request.urlopen", return_value=mock):
            await fetch_models("Google")
            await fetch_models("google")
        mock.read.assert_called_once()


class TestCacheDefensiveCopy:
    """Cached results are not affected by caller mutation."""

    async def test_mutation_does_not_affect_cache(self) -> None:
        with patch("superai_mcp.openrouter.urllib.request.urlopen", return_value=_mock_urlopen()):
            models1 = await fetch_models("anthropic")
            models1[0]["id"] = "MUTATED"
            models2 = await fetch_models("anthropic")
        assert models2[0]["id"] == "anthropic/claude-sonnet-4"


class TestProviderConstants:
    """Verify the PROVIDERS constant covers the expected set."""

    def test_providers_tuple(self) -> None:
        assert set(PROVIDERS) == {"anthropic", "google", "openai"}
