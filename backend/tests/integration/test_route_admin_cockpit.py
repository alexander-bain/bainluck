"""Contract tests for the Alex Cockpit admin endpoint (L2-102).

GET /api/admin/cockpit is read-only and reuses warm Redis snapshots plus a few
cheap queries. These tests assert: admin auth is enforced, the payload has the
three tile groups, the "waiting on you" GitHub fallback fires when no token is
set, and the pure banding helpers behave.
"""

from unittest.mock import MagicMock, patch

import pytest

from app.routes.admin_cockpit import (
    _WAITING_FALLBACK,
    _hours_since,
    _status_from_pct,
    _waiting_on_you,
)


@pytest.fixture
def _fake_redis():
    """Patch get_redis_client so the endpoint never touches a real Redis."""
    r = MagicMock()
    r.get.return_value = None  # cold caches → tiles report "unknown"
    r.llen.return_value = 0
    r.set.return_value = True
    with patch("app.tasks.redis_state.get_redis_client", return_value=r):
        yield r


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


class TestHelpers:
    def test_status_bands(self):
        assert _status_from_pct(100, green=99, amber=90) == "green"
        assert _status_from_pct(95, green=99, amber=90) == "amber"
        assert _status_from_pct(50, green=99, amber=90) == "red"
        assert _status_from_pct(None, green=99, amber=90) == "unknown"

    def test_hours_since_none(self):
        assert _hours_since(None) is None

    def test_waiting_fallback_without_token(self, monkeypatch):
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        result = _waiting_on_you()
        assert result["source"] == "fallback"
        assert result["items"] == _WAITING_FALLBACK
        assert len(result["items"]) == 3


# ---------------------------------------------------------------------------
# Endpoint contract
# ---------------------------------------------------------------------------


class TestCockpitEndpoint:
    async def test_rejects_bad_secret(self, client, monkeypatch):
        monkeypatch.setenv("ADMIN_TOKEN", "right-token")
        resp = await client.get("/api/admin/cockpit?secret=wrong")
        assert resp.status_code == 403

    async def test_returns_three_groups(self, client, monkeypatch, _fake_redis):
        monkeypatch.setenv("ADMIN_TOKEN", "right-token")
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        resp = await client.get("/api/admin/cockpit?secret=right-token&bust=1")
        assert resp.status_code == 200
        data = resp.json()

        # Three groups present
        assert isinstance(data["health"], list) and len(data["health"]) >= 3
        assert data["waiting_on_you"]["source"] == "fallback"
        assert "pending_eval_count" in data["eval_queue"]
        assert "new_bug_reports" in data["eval_queue"]
        assert data["eval_queue"]["verdict_endpoint"] == "/api/admin/label-pass/verdict"

        # Health tiles carry the fields the frontend renders
        keys = {t["key"] for t in data["health"]}
        assert {"link_rate", "grid_health", "queue_depth", "creation_freshness"} <= keys
        for tile in data["health"]:
            assert {"key", "label", "value", "status", "href"} <= set(tile)
