"""Tests for cost tracking feature."""

from unittest.mock import patch

from superai_mcp.server import (
    _estimate_cost,
    _pricing,
    _reset_usage,
    _track_usage,
    _usage,
)


class TestEstimateCost:
    def setup_method(self) -> None:
        _pricing.clear()
        _pricing["claude-sonnet-4"] = (0.000003, 0.000015)  # $3/$15 per M tokens
        _pricing["gpt-5.3-codex"] = (0.000002, 0.000008)

    def teardown_method(self) -> None:
        _pricing.clear()

    def test_exact_match(self) -> None:
        cost = _estimate_cost("claude-sonnet-4", 1000, 500)
        assert cost > 0
        expected = 1000 * 0.000003 + 500 * 0.000015
        assert abs(cost - expected) < 1e-9

    def test_prefix_match(self) -> None:
        cost = _estimate_cost("sonnet", 1000, 500)
        assert cost > 0

    def test_no_model(self) -> None:
        assert _estimate_cost(None, 1000, 500) == 0.0
        assert _estimate_cost("", 1000, 500) == 0.0

    def test_unknown_model(self) -> None:
        assert _estimate_cost("unknown-model-xyz", 1000, 500) == 0.0

    def test_empty_pricing(self) -> None:
        _pricing.clear()
        assert _estimate_cost("claude-sonnet-4", 1000, 500) == 0.0


class TestTrackUsageCost:
    def setup_method(self) -> None:
        _reset_usage()
        _pricing.clear()
        _pricing["claude-sonnet-4"] = (0.000003, 0.000015)

    def teardown_method(self) -> None:
        _pricing.clear()
        _reset_usage()

    def test_cost_accumulated(self) -> None:
        _track_usage("claude", {"input_tokens": 1000, "output_tokens": 500}, "claude-sonnet-4")
        assert _usage["claude"]["estimated_cost_usd"] > 0

    def test_cost_accumulates_across_calls(self) -> None:
        _track_usage("claude", {"input_tokens": 1000, "output_tokens": 500}, "claude-sonnet-4")
        first = float(_usage["claude"]["estimated_cost_usd"])
        _track_usage("claude", {"input_tokens": 1000, "output_tokens": 500}, "claude-sonnet-4")
        second = float(_usage["claude"]["estimated_cost_usd"])
        assert abs(second - 2 * first) < 1e-9

    def test_no_model_no_cost(self) -> None:
        _track_usage("claude", {"input_tokens": 1000, "output_tokens": 500}, None)
        assert _usage["claude"]["estimated_cost_usd"] == 0.0

    def test_no_usage_no_cost(self) -> None:
        _track_usage("claude", None, "claude-sonnet-4")
        assert _usage["claude"]["estimated_cost_usd"] == 0.0

    def test_reset_clears_cost(self) -> None:
        _track_usage("claude", {"input_tokens": 1000, "output_tokens": 500}, "claude-sonnet-4")
        _reset_usage()
        assert _usage["claude"]["estimated_cost_usd"] == 0.0
