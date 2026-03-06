"""Unit tests for quota data models."""

from superai_mcp.quota._models import QuotaResult, SessionQuota, quota_result_to_dict


class TestSessionQuota:
    def test_defaults(self) -> None:
        sq = SessionQuota()
        assert sq.used_percent is None
        assert sq.remaining_percent is None
        assert sq.resets_at is None
        assert sq.resets_in is None

    def test_with_values(self) -> None:
        sq = SessionQuota(
            used_percent=42.5,
            remaining_percent=57.5,
            resets_at="2026-03-05T12:00:00Z",
            resets_in="2h 30m",
        )
        assert sq.used_percent == 42.5
        assert sq.resets_in == "2h 30m"


class TestQuotaResult:
    def test_default_failure(self) -> None:
        qr = QuotaResult(provider="claude")
        assert qr.success is False
        assert qr.sessions == {}

    def test_success_with_sessions(self) -> None:
        qr = QuotaResult(
            provider="claude",
            success=True,
            plan_type="max",
            sessions={
                "current": SessionQuota(used_percent=10.0, remaining_percent=90.0)
            },
        )
        assert qr.success is True
        assert qr.sessions["current"].used_percent == 10.0


class TestQuotaResultToDict:
    def test_minimal(self) -> None:
        qr = QuotaResult(provider="codex", success=False, error="no creds")
        d = quota_result_to_dict(qr)
        assert d == {
            "provider": "codex",
            "success": False,
            "error": "no creds",
            "plan_type": None,
            "sessions": {},
        }

    def test_with_sessions(self) -> None:
        qr = QuotaResult(
            provider="claude",
            success=True,
            plan_type="max",
            sessions={
                "current": SessionQuota(
                    used_percent=42.5,
                    remaining_percent=57.5,
                    resets_at="2026-03-05T12:00:00Z",
                    resets_in="2h 30m",
                )
            },
        )
        d = quota_result_to_dict(qr)
        assert d["sessions"]["current"]["used_percent"] == 42.5
        assert d["sessions"]["current"]["resets_in"] == "2h 30m"
