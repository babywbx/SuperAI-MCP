"""Data models for quota results."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SessionQuota:
    """A single usage window (e.g. 5-hour session, weekly)."""

    used_percent: float | None = None
    remaining_percent: float | None = None
    resets_at: str | None = None  # ISO 8601
    resets_in: str | None = None  # "2h 30m"


@dataclass
class QuotaResult:
    """Unified quota result from a provider."""

    provider: str
    success: bool = False
    error: str | None = None
    plan_type: str | None = None
    sessions: dict[str, SessionQuota] = field(default_factory=dict)


def quota_result_to_dict(qr: QuotaResult) -> dict[str, object]:
    """Convert QuotaResult to a JSON-serializable dict."""
    sessions: dict[str, dict[str, object]] = {}
    for key, sq in qr.sessions.items():
        sessions[key] = {
            "used_percent": sq.used_percent,
            "remaining_percent": sq.remaining_percent,
            "resets_at": sq.resets_at,
            "resets_in": sq.resets_in,
        }
    return {
        "provider": qr.provider,
        "success": qr.success,
        "error": qr.error,
        "plan_type": qr.plan_type,
        "sessions": sessions,
    }
