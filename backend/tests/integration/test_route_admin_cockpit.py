"""Contract tests for the Alex Cockpit admin endpoint (L2-102).

GET /api/admin/cockpit is read-only and reuses warm Redis snapshots plus a few
cheap queries. These tests assert: admin auth is enforced, the payload has the
three tile groups, the "waiting on you" GitHub fallback fires when no token is
set, and the pure banding helpers behave.
"""

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.routes.admin_cockpit import (
    _AUTOPILOT_BEATS,
    _WAITING_FALLBACK,
    _autopilot_tile,
    _hours_since,
    _red_sub_context,
    _status_from_pct,
    _waiting_on_you,
)


def _iso_hours_ago(hours: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()


_CAL_BEAT = next(b for b in _AUTOPILOT_BEATS if b["label"] == "calibration_prices")
_COMBAT_BEAT = next(b for b in _AUTOPILOT_BEATS if b["label"] == "backfill_combat_wps")


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

    def test_red_sub_context_tracked_artifact_untracked(self):
        # L2-104: a RED with an open issue is "tracked" and links it.
        tracked = _red_sub_context("grid_health", "nba", "6/100")
        assert tracked["kind"] == "tracked"
        assert tracked["ref"] == "#1059"
        assert tracked["url"] and "1059" in tracked["url"]

        # A known/expected zero is an "artifact" with an explanatory note.
        artifact = _red_sub_context("grid_health", "golf", "0/100")
        assert artifact["kind"] == "artifact"
        assert artifact["note"]

        # Anything else is the true four-alarm "untracked" state.
        untracked = _red_sub_context("grid_health", "mlb", "66/100")
        assert untracked["kind"] == "untracked"
        assert untracked["ref"] is None and untracked["url"] is None


class TestAutopilotTile:
    """L2-105: scheduled-beat visibility tiles (calibration_prices, combat WPS)."""

    def test_fresh_on_cadence_is_green(self):
        # Fired 1h ago with the full 6h cadence's worth of fires → green.
        tile = _autopilot_tile(
            _CAL_BEAT,
            {"last_success_at": _iso_hours_ago(1), "successes_24h": 4, "last_result_summary": {"rescued": 12}},
        )
        assert tile["key"] == "autopilot:calibration_prices"
        assert tile["status"] == "green"
        assert "4/4 fires/24h" in tile["detail"]
        assert "12 rescued" in tile["detail"]

    def test_fresh_but_below_cadence_is_amber(self):
        # r178 signature: last fire recent, but only 1 fire in 24h vs 4 expected —
        # the beat is being triggered manually, not firing on schedule.
        tile = _autopilot_tile(
            _CAL_BEAT,
            {"last_success_at": _iso_hours_ago(1), "successes_24h": 1, "last_result_summary": {"rescued": 3}},
        )
        assert tile["status"] == "amber"
        assert "1/4 fires/24h" in tile["detail"]

    def test_stale_past_cadence_is_red(self):
        # No scheduled fire in >8h → red (the queue's explicit acceptance).
        tile = _autopilot_tile(
            _CAL_BEAT,
            {"last_success_at": _iso_hours_ago(9), "successes_24h": 2},
        )
        assert tile["status"] == "red"

    def test_never_fired_is_red(self):
        tile = _autopilot_tile(_CAL_BEAT, {"status": "no_data"})
        assert tile["status"] == "red"
        assert tile["value"] == "never fired"

    def test_approaching_stale_is_amber(self):
        # 7h since last fire (> 8 * 0.75 = 6) but not yet past 8h → amber warning.
        tile = _autopilot_tile(
            _CAL_BEAT,
            {"last_success_at": _iso_hours_ago(7), "successes_24h": 4},
        )
        assert tile["status"] == "amber"

    def test_daily_beat_single_fire_is_green(self):
        # Combat WPS is daily (expected_24h=1): one fire 3h ago is healthy, not amber.
        tile = _autopilot_tile(
            _COMBAT_BEAT,
            {"last_success_at": _iso_hours_ago(3), "successes_24h": 1, "last_result_summary": {"written": 40}},
        )
        assert tile["status"] == "green"
        assert "40 rescued" in tile["detail"]

    def test_pre_first_fire_is_pending_not_red(self):
        # A beat whose first scheduled fire is in the future is pending, never red.
        beat = dict(_COMBAT_BEAT)
        beat["first_fire"] = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
        tile = _autopilot_tile(beat, {"status": "no_data"})
        assert tile["status"] == "unknown"
        assert "awaiting first fire" in tile["detail"]

    def test_pre_first_fire_ignored_once_fired(self):
        # Once a real fire is recorded, the future-first_fire guard no longer applies.
        beat = dict(_COMBAT_BEAT)
        beat["first_fire"] = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
        tile = _autopilot_tile(
            beat, {"last_success_at": _iso_hours_ago(2), "successes_24h": 1}
        )
        assert tile["status"] == "green"


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
        # L2-105: autopilot beat tiles are part of the health row.
        assert {"autopilot:calibration_prices", "autopilot:backfill_combat_wps"} <= keys
        for tile in data["health"]:
            assert {"key", "label", "value", "status", "href"} <= set(tile)

    async def test_honesty_pass_link_rate_and_grid_context(
        self, client, monkeypatch
    ):
        """L2-104: link-rate headline is the OPEN rate (not all-status), and RED
        grids carry tracked / artifact / untracked context badges."""
        monkeypatch.setenv("ADMIN_TOKEN", "right-token")
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)

        warm = {
            "bainluck:admin:link_rate": json.dumps(
                {
                    "overall": {
                        "link_rate_pct": 99.6,
                        "link_rate_all_pct": 90.3,
                        "open_linked": 143000,
                        "open_total": 143500,
                    }
                }
            ),
            "bainluck:admin:audit_all": json.dumps(
                {
                    "avg_score": 42,
                    "scores": {"nba": 6, "nhl": 94, "mlb": 66, "golf": 0},
                }
            ),
        }
        r = MagicMock()
        r.get.side_effect = lambda key: warm.get(key)
        r.llen.return_value = 0
        r.set.return_value = True
        with patch("app.tasks.redis_state.get_redis_client", return_value=r):
            resp = await client.get("/api/admin/cockpit?secret=right-token&bust=1")
        assert resp.status_code == 200
        tiles = {t["key"]: t for t in resp.json()["health"]}

        # Link-rate HEADLINE is the open-markets rate; all-status demoted to detail.
        link = tiles["link_rate"]
        assert link["value"] == "99.6%"
        assert link["status"] == "green"
        assert "90.3% all-status" in link["detail"]
        assert "gotcha #35" in link["detail"]

        # Grid RED context: mlb untracked (four-alarm, sorted first), nba tracked,
        # golf artifact; nhl (94, amber) is NOT flagged.
        grid = tiles["grid_health"]
        ctx = {c["label"]: c for c in grid["context"]}
        assert set(ctx) == {"nba", "mlb", "golf"}
        assert ctx["nba"]["kind"] == "tracked" and ctx["nba"]["ref"] == "#1059"
        assert ctx["golf"]["kind"] == "artifact"
        assert ctx["mlb"]["kind"] == "untracked"
        assert grid["context"][0]["kind"] == "untracked"
