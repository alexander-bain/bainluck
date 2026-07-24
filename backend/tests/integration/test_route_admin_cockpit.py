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
    _LINK_TILE_STATE_KEY,
    _WAITING_FALLBACK,
    _apply_link_tile_state_change,
    _autopilot_tile,
    _celery_health_tile,
    _feed_quality_empty_detail,
    _flow_sentinel_group,
    _fmt_duration,
    _grid_sentinel_group,
    _hours_since,
    _link_tile_state_change,
    _red_sub_context,
    _status_from_pct,
    _waiting_on_you,
    _watchdog_stuck_phases,
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


class TestWatchdogStuckPhases:
    """L2-116: the phase-heartbeat watchdog's stuck-fetch signal rides the warm
    `bainluck:watchdog:summary`; the cockpit surfaces it as a tile detail so a
    genuinely wedged fetch stays visible even though idle tasks now read green."""

    def _patch(self, value):
        r = MagicMock()
        r.get.return_value = value
        return patch("app.tasks.redis_state.get_redis_client", return_value=r)

    def test_extracts_stuck_list(self):
        payload = json.dumps(
            {"phase_heartbeat": {"stuck": [{"marker": "poll_kalshi:fetch", "stuck_seconds": 720}]}}
        )
        with self._patch(payload):
            stuck = _watchdog_stuck_phases()
        assert stuck == [{"marker": "poll_kalshi:fetch", "stuck_seconds": 720}]

    def test_empty_when_no_stuck(self):
        with self._patch(json.dumps({"phase_heartbeat": {"stuck": []}})):
            assert _watchdog_stuck_phases() == []

    def test_safe_on_cold_cache(self):
        with self._patch(None):
            assert _watchdog_stuck_phases() == []

    def test_safe_on_malformed(self):
        with self._patch(json.dumps({"phase_heartbeat": "oops"})):
            assert _watchdog_stuck_phases() == []


class TestCeleryHealthTile:
    """L2-117: first-class worker-health tile. Bands must mirror the celery
    dashboard's overall_health, and failing tasks must surface WITH their
    consecutive-failure counts (the tile's honest first render)."""

    def _run(self, tasks, hb_age):
        with patch(
            "app.routes.admin_cockpit._worker_heartbeat_age", return_value=hb_age
        ), patch(
            "app.tasks.redis_state.get_all_task_metrics", return_value=tasks
        ):
            return _celery_health_tile()

    def test_all_healthy_is_green(self):
        tasks = [
            {"task": "poll_kalshi", "health": "healthy"},
            {"task": "match_prediction_markets", "health": "healthy"},
        ]
        tile = self._run(tasks, hb_age=42)
        assert tile["status"] == "green"
        assert tile["value"] == "Healthy"
        assert "2 tasks tracked" in tile["detail"]
        assert tile["href"] == "/admin"
        assert tile["key"] == "celery_health"

    def test_critical_tasks_named_with_consecutive_counts(self):
        # The acceptance criterion: the 3 failing tasks show RED, named, with counts.
        tasks = [
            {"task": "both_winner_guess_flip", "health": "critical", "consecutive_failures": "19"},
            {"task": "compute_fair_fight_comparison", "health": "critical", "consecutive_failures": "12"},
            {"task": "discover_candidate_snapshot", "health": "critical", "consecutive_failures": "6"},
            {"task": "poll_kalshi", "health": "healthy"},
        ]
        tile = self._run(tasks, hb_age=30)
        assert tile["status"] == "red"
        assert tile["value"] == "Critical"
        assert "3 failing" in tile["detail"]
        assert "both_winner_guess_flip ×19" in tile["detail"]
        assert "compute_fair_fight_comparison ×12" in tile["detail"]
        assert "discover_candidate_snapshot ×6" in tile["detail"]

    def test_degraded_is_amber(self):
        tasks = [
            {"task": "poll_polymarket", "health": "degraded", "consecutive_failures": "3"},
            {"task": "poll_kalshi", "health": "healthy"},
        ]
        tile = self._run(tasks, hb_age=30)
        assert tile["status"] == "amber"
        assert tile["value"] == "Degraded"
        assert "poll_polymarket ×3" in tile["detail"]

    def test_worker_down_is_red_regardless_of_task_health(self):
        # Stale heartbeat (>180s) → red even when every task reads healthy: the
        # metrics are untrustworthy because nothing is running to update them.
        tasks = [{"task": "poll_kalshi", "health": "healthy"}]
        tile = self._run(tasks, hb_age=600)
        assert tile["status"] == "red"
        assert tile["value"] == "Worker down"
        assert "no heartbeat for 600s" in tile["detail"]

    def test_idle_and_retired_tasks_do_not_turn_it_red(self):
        # get_task_metrics reports idle→no_data and retired→retired; neither is
        # critical/degraded, so a fleet of idle tasks stays green (the L2-116 fix
        # this tile depends on — an idle window must not read as a four-alarm).
        tasks = [
            {"task": "backfill_combat_wps", "health": "no_data"},
            {"task": "old_retired_task", "health": "retired"},
            {"task": "poll_kalshi", "health": "healthy"},
        ]
        tile = self._run(tasks, hb_age=20)
        assert tile["status"] == "green"

    def test_no_tasks_no_heartbeat_is_unknown(self):
        tile = self._run([], hb_age=None)
        assert tile["status"] == "unknown"
        assert tile["value"] == "—"

    def test_malformed_consecutive_falls_back_to_bare_name(self):
        tasks = [{"task": "weird_task", "health": "critical", "consecutive_failures": "n/a"}]
        tile = self._run(tasks, hb_age=30)
        assert tile["status"] == "red"
        assert "weird_task" in tile["detail"]
        assert "×" not in tile["detail"].split("weird_task")[1][:2]


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

    def test_feed_quality_empty_detail_no_run(self):
        # L2-106: no run row → explain the daily beat + how to seed it, not a
        # bare "no eval run recorded yet".
        detail = _feed_quality_empty_detail(None)
        assert "daily label-eval beat" in detail
        assert "09:55 UTC" in detail
        assert "Discover Quality" in detail

    def test_feed_quality_empty_detail_run_without_labels(self):
        # L2-106: a run exists but scored 0 human labels → say the run ran and
        # how old it is, and that grading is the fix.
        class _Row:
            captured_at = datetime.now(timezone.utc) - timedelta(hours=3)

        detail = _feed_quality_empty_detail(_Row())
        assert "0 human labels" in detail
        assert "3.0h ago" in detail
        assert "Discover Quality" in detail

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


class TestFlowSentinelGroup:
    """L2-108 Item 3: cockpit consumes the persisted Flow Sentinel scorecard."""

    @staticmethod
    def _patch_redis(payload):
        r = MagicMock()
        r.get.return_value = json.dumps(payload) if payload is not None else None
        return patch("app.tasks.redis_state.get_redis_client", return_value=r)

    def test_no_run_cached_is_unknown(self):
        with self._patch_redis(None):
            group = _flow_sentinel_group()
        assert group["status"] == "unknown"
        assert group["per_flow"] == []
        assert "flow-sentinel" in group["detail"].lower() or "Flow Sentinel" in group["detail"]

    def test_scores_per_flow_and_links_filed_issue(self):
        stats = {
            "mode": "live",
            "duration_seconds": 12.3,
            "filed": [
                {"flow": "duplicate_events", "issue": 1085, "action": "filed", "severity": "P2"},
                {"flow": "search_gold_set", "action": "skipped_no_token"},  # no issue → no link
            ],
            "scorecard": {
                "flows_total": 3,
                "flows_passed": 1,
                "flows_failed": 1,
                "per_flow": [
                    {"flow": "search_gold_set", "passed": True, "checked": 26, "failing": 0, "skipped": False},
                    {"flow": "duplicate_events", "passed": False, "checked": 386, "failing": 21, "skipped": False},
                    {"flow": "event_completeness", "passed": True, "checked": 0, "failing": 0, "skipped": True},
                ],
            },
        }
        with self._patch_redis(stats):
            group = _flow_sentinel_group()

        # A real failure dominates → overall RED.
        assert group["status"] == "red"
        assert group["flows_total"] == 3
        assert group["flows_passed"] == 1
        rows = {r["flow"]: r for r in group["per_flow"]}
        assert rows["search_gold_set"]["status"] == "green"
        assert rows["duplicate_events"]["status"] == "red"
        assert rows["duplicate_events"]["issue"] == 1085
        assert rows["duplicate_events"]["issue_url"].endswith("/1085")
        assert rows["event_completeness"]["status"] == "amber"  # skipped
        assert rows["search_gold_set"]["issue_url"] is None

    def test_skip_only_is_amber_not_red(self):
        stats = {
            "scorecard": {
                "flows_total": 2,
                "flows_passed": 1,
                "flows_failed": 0,
                "per_flow": [
                    {"flow": "resolved_state", "passed": True, "checked": 10, "failing": 0, "skipped": False},
                    {"flow": "event_completeness", "passed": True, "checked": 0, "failing": 0, "skipped": True},
                ],
            },
        }
        with self._patch_redis(stats):
            group = _flow_sentinel_group()
        assert group["status"] == "amber"

    def test_generated_at_passed_through_for_age(self):
        # Queue #234 Item 3: the cockpit must surface each sentinel's own run
        # stamp so per-sentinel rows render real ages, not age=None.
        stats = {
            "generated_at": "2026-07-23T07:10:05+00:00",
            "scorecard": {
                "flows_total": 1, "flows_passed": 1, "flows_failed": 0,
                "per_flow": [
                    {"flow": "resolved_state", "passed": True, "checked": 64, "failing": 0, "skipped": False},
                ],
            },
        }
        with self._patch_redis(stats):
            group = _flow_sentinel_group()
        assert group["generated_at"] == "2026-07-23T07:10:05+00:00"

    def test_generated_at_none_when_no_run_cached(self):
        # Shape stays stable pre-first-run: key present, value None (not missing).
        with self._patch_redis(None):
            group = _flow_sentinel_group()
        assert group["status"] == "unknown"
        assert group["generated_at"] is None

    def test_all_pass_is_green(self):
        stats = {
            "scorecard": {
                "flows_total": 1,
                "flows_passed": 1,
                "flows_failed": 0,
                "per_flow": [
                    {"flow": "category_discover", "passed": True, "checked": 5, "failing": 0, "skipped": False},
                ],
            },
        }
        with self._patch_redis(stats):
            group = _flow_sentinel_group()
        assert group["status"] == "green"


class TestGridSentinelGroup:
    """L2-157: the grid tile's VERDICT — watch is blend-hidden ("never RED") and
    must NOT escalate to amber. A clean-but-watch grid stays GREEN + a count."""

    @staticmethod
    def _patch_redis(payload):
        r = MagicMock()
        r.get.return_value = json.dumps(payload) if payload is not None else None
        return patch("app.tasks.redis_state.get_redis_client", return_value=r)

    def test_no_run_cached_returns_none(self):
        # Cold cache → None so the caller falls back to the raw-score tile.
        with self._patch_redis(None):
            assert _grid_sentinel_group() is None

    def test_watch_only_is_green_not_amber(self):
        # The core L2-157 fix: leagues with ONLY watch items stay GREEN.
        stats = {
            "scorecard": {
                "leagues_total": 2,
                "leagues_red": 0,
                "per_league": [
                    {"league": "mlb", "verdict": "green", "phase": "in_season",
                     "real_defects": 0, "explained_artifacts": 0, "watch": 1},
                    {"league": "nba", "verdict": "green", "phase": "in_season",
                     "real_defects": 0, "explained_artifacts": 0, "watch": 2},
                ],
            },
        }
        with self._patch_redis(stats):
            group = _grid_sentinel_group()
        assert group["status"] == "green"
        assert group["watch_total"] == 3
        per = {r["league"]: r for r in group["per_league"]}
        assert per["mlb"]["status"] == "green"
        assert per["nba"]["status"] == "green"

    def test_explained_artifacts_still_amber(self):
        # Explained artifacts (season-window) ARE a legit amber — unchanged.
        stats = {
            "scorecard": {
                "leagues_total": 1, "leagues_red": 0,
                "per_league": [
                    {"league": "nhl", "verdict": "amber", "phase": "offseason",
                     "real_defects": 0, "explained_artifacts": 2, "watch": 0},
                ],
            },
        }
        with self._patch_redis(stats):
            group = _grid_sentinel_group()
        assert group["status"] == "amber"
        assert group["per_league"][0]["status"] == "amber"

    def test_real_defect_is_red(self):
        stats = {
            "scorecard": {
                "leagues_total": 1, "leagues_red": 1,
                "per_league": [
                    {"league": "mlb", "verdict": "red", "phase": "in_season",
                     "real_defects": 1, "explained_artifacts": 0, "watch": 3},
                ],
            },
        }
        with self._patch_redis(stats):
            group = _grid_sentinel_group()
        assert group["status"] == "red"
        assert group["per_league"][0]["status"] == "red"

    def test_mixed_watch_and_artifacts_overall_amber_watch_green(self):
        # The live prod shape (2026-07-22): mlb/nba watch-only, nhl artifacts.
        # Overall AMBER from nhl's real artifacts; mlb/nba per-league GREEN.
        stats = {
            "scorecard": {
                "leagues_total": 3, "leagues_red": 0,
                "per_league": [
                    {"league": "mlb", "verdict": "green", "phase": "in_season",
                     "real_defects": 0, "explained_artifacts": 0, "watch": 1},
                    {"league": "nba", "verdict": "green", "phase": "in_season",
                     "real_defects": 0, "explained_artifacts": 0, "watch": 2},
                    {"league": "nhl", "verdict": "amber", "phase": "offseason",
                     "real_defects": 0, "explained_artifacts": 2, "watch": 0},
                ],
            },
        }
        with self._patch_redis(stats):
            group = _grid_sentinel_group()
        assert group["status"] == "amber"
        assert group["watch_total"] == 3
        per = {r["league"]: r for r in group["per_league"]}
        assert per["mlb"]["status"] == "green"
        assert per["nba"]["status"] == "green"
        assert per["nhl"]["status"] == "amber"


class TestScheduleTextMatchesCrontab:
    """Guard the autopilot tile schedule strings against the REAL Celery crontab.

    L2-108 Item 1: the cal-price tile drifted to ":15 UTC" while the beat had
    moved to minute=10 (#183 de-contention), so the 02:10Z verdict reader was
    misled. These tests cross-check each tile's human schedule string against the
    actual `beat_schedule` crontab so a schedule move can never silently desync
    the tile again.
    """

    @staticmethod
    def _crontab_for(task_name: str):
        from app.tasks import celery_app

        for entry in celery_app.conf.beat_schedule.values():
            if entry["task"] == task_name:
                return entry["schedule"]
        raise AssertionError(f"no beat schedule entry for {task_name}")

    def test_cal_price_schedule_string_matches_beat(self):
        cron = self._crontab_for("app.tasks.compute_calibration_prices")
        # crontab.minute / .hour are sets of ints; the beat fires at :10 in the
        # 2,8,14,20 windows.
        assert cron.minute == {10}
        assert cron.hour == {2, 8, 14, 20}
        text = _CAL_BEAT["schedule"]
        assert ":10 UTC" in text, f"tile schedule text out of sync: {text!r}"
        assert ":15" not in text
        for hr in cron.hour:
            assert f"{hr:02d}" in text, f"missing hour {hr:02d} in {text!r}"

    def test_combat_wps_schedule_string_matches_beat(self):
        cron = self._crontab_for("app.tasks.backfill_combat_wps")
        assert cron.minute == {50}
        assert cron.hour == {9}
        text = _COMBAT_BEAT["schedule"]
        assert "09:50 UTC" in text, f"tile schedule text out of sync: {text!r}"


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
        resp = await client.get("/api/admin/cockpit?bust=1", headers={"Authorization": "Bearer right-token"})
        assert resp.status_code == 200
        data = resp.json()

        # Three groups present
        assert isinstance(data["health"], list) and len(data["health"]) >= 3
        assert data["waiting_on_you"]["source"] == "fallback"
        assert "pending_eval_count" in data["eval_queue"]
        assert "new_bug_reports" in data["eval_queue"]
        assert data["eval_queue"]["verdict_endpoint"] == "/api/admin/label-pass/verdict"
        # L2-108 Item 3: flow-sentinel group present (unknown when Redis cold).
        assert "flow_sentinel" in data
        assert data["flow_sentinel"]["status"] == "unknown"
        assert data["flow_sentinel"]["per_flow"] == []

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
        """L2-145 Item 1: the link tile's HEADLINE is matured-linkage (below-100
        MEANS a real defect); the raw market link-rate is folded into the tile's
        diagnostic subtitle. RED grids carry tracked/artifact/untracked badges."""
        monkeypatch.setenv("ADMIN_TOKEN", "right-token")
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)

        warm = {
            "bainluck:admin:matured_linkage": json.dumps(
                {
                    "status": "ok",
                    "headline_pct": 100,
                    "backed": 12,
                    "checkable_pairs": 12,
                    "phantom": 0,
                }
            ),
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
            resp = await client.get("/api/admin/cockpit?bust=1", headers={"Authorization": "Bearer right-token"})
        assert resp.status_code == 200
        tiles = {t["key"]: t for t in resp.json()["health"]}

        # The link tile HEADLINE is now matured-linkage; the raw link-rate is a
        # subtitle. The standalone "matured_linkage" tile is retired (merged in).
        link = tiles["link_rate"]
        assert link["label"] == "Link rate"
        assert link["value"] == "100%"
        assert link["status"] == "green"
        assert "every matured event fully linked" in link["detail"]
        # Raw link-rate folded into the diagnostic subtitle.
        assert "raw link rate 99.6% open" in link["detail"]
        assert "90.3% all-status" in link["detail"]
        assert "gotcha #35" in link["detail"]
        assert "matured_linkage" not in tiles  # the separate tile is gone

        # Grid RED context: mlb untracked (four-alarm, sorted first), nba tracked,
        # golf artifact; nhl (94, amber) is NOT flagged.
        grid = tiles["grid_health"]
        ctx = {c["label"]: c for c in grid["context"]}
        assert set(ctx) == {"nba", "mlb", "golf"}
        assert ctx["nba"]["kind"] == "tracked" and ctx["nba"]["ref"] == "#1059"
        assert ctx["golf"]["kind"] == "artifact"
        assert ctx["mlb"]["kind"] == "untracked"
        assert grid["context"][0]["kind"] == "untracked"


class TestLinkTileStateChange:
    """L2-146 Item 3: the link tile tracks its own status transitions in Redis so
    a recovery to 100% (when Lane 1's matcher fix lands) is visible on the tile
    without log archaeology. Scoped to admin_cockpit — never touches the matcher."""

    def _stateful_redis(self):
        """A MagicMock redis whose get/set share a dict so `since` persists
        across calls (the whole point of the state-change tracker)."""
        store: dict = {}
        r = MagicMock()
        r.get.side_effect = lambda key: store.get(key)
        r.set.side_effect = lambda key, val, **kw: store.__setitem__(key, val)
        return r, store

    def test_fmt_duration_bands(self):
        assert _fmt_duration(0) == "0s"
        assert _fmt_duration(45) == "45s"
        assert _fmt_duration(59) == "59s"
        assert _fmt_duration(60) == "1m"
        assert _fmt_duration(305) == "5m"
        assert _fmt_duration(3600) == "1h00m"
        assert _fmt_duration(7440) == "2h04m"
        assert _fmt_duration(-10) == "0s"  # clamp

    def test_first_observation_is_bootstrap(self):
        r, store = self._stateful_redis()
        with patch("app.tasks.redis_state.get_redis_client", return_value=r):
            change = _link_tile_state_change("red", 50)
        assert change["bootstrap"] is True
        assert change["prev"] is None
        # It stamped the state so the NEXT observation has a baseline.
        assert _LINK_TILE_STATE_KEY in store
        stamped = json.loads(store[_LINK_TILE_STATE_KEY])
        assert stamped["status"] == "red" and stamped["prev"] is None

    def test_same_status_accrues_age(self):
        r, store = self._stateful_redis()
        # Seed a prior state 2h ago, same status.
        store[_LINK_TILE_STATE_KEY] = json.dumps(
            {"status": "red", "value": 50, "since": _iso_hours_ago(2), "prev": "green"}
        )
        with patch("app.tasks.redis_state.get_redis_client", return_value=r):
            change = _link_tile_state_change("red", 50)
        assert change["bootstrap"] is False
        assert change["prev"] == "green"
        assert 7000 < change["age_s"] < 7400  # ~2h

    def test_status_change_resets_since_and_records_prev(self):
        r, store = self._stateful_redis()
        store[_LINK_TILE_STATE_KEY] = json.dumps(
            {"status": "red", "value": 50, "since": _iso_hours_ago(3), "prev": None}
        )
        with patch("app.tasks.redis_state.get_redis_client", return_value=r):
            change = _link_tile_state_change("green", 100)
        assert change["bootstrap"] is False
        assert change["prev"] == "red"
        assert change["age_s"] == 0.0
        stamped = json.loads(store[_LINK_TILE_STATE_KEY])
        assert stamped["status"] == "green" and stamped["prev"] == "red"

    def test_apply_recovery_message(self):
        r, store = self._stateful_redis()
        store[_LINK_TILE_STATE_KEY] = json.dumps(
            {"status": "red", "value": 50, "since": _iso_hours_ago(1.5), "prev": None}
        )
        bits: list[str] = ["every matured event fully linked"]
        with patch("app.tasks.redis_state.get_redis_client", return_value=r):
            _apply_link_tile_state_change(bits, "green", 100)
        # Just recovered → age 0.
        assert any("recovered" in b and "was red" in b for b in bits)

    def test_apply_stable_message(self):
        r, store = self._stateful_redis()
        store[_LINK_TILE_STATE_KEY] = json.dumps(
            {"status": "green", "value": 100, "since": _iso_hours_ago(5), "prev": "green"}
        )
        bits: list[str] = ["every matured event fully linked"]
        with patch("app.tasks.redis_state.get_redis_client", return_value=r):
            _apply_link_tile_state_change(bits, "green", 100)
        assert any("stable green for 5h" in b for b in bits)

    def test_apply_degraded_message(self):
        r, store = self._stateful_redis()
        store[_LINK_TILE_STATE_KEY] = json.dumps(
            {"status": "green", "value": 100, "since": _iso_hours_ago(0.5), "prev": "green"}
        )
        bits: list[str] = ["11/12 imminent blend sources linked"]
        with patch("app.tasks.redis_state.get_redis_client", return_value=r):
            _apply_link_tile_state_change(bits, "amber", 91)
        assert any("amber for" in b and "was green" in b for b in bits)

    def test_apply_bootstrap_is_noop(self):
        r, _ = self._stateful_redis()
        bits: list[str] = ["every matured event fully linked"]
        with patch("app.tasks.redis_state.get_redis_client", return_value=r):
            _apply_link_tile_state_change(bits, "green", 100)
        assert bits == ["every matured event fully linked"]  # nothing appended

    def test_redis_error_degrades_gracefully(self):
        r = MagicMock()
        r.get.side_effect = RuntimeError("redis down")
        with patch("app.tasks.redis_state.get_redis_client", return_value=r):
            assert _link_tile_state_change("green", 100) is None
        bits: list[str] = ["every matured event fully linked"]
        with patch("app.tasks.redis_state.get_redis_client", return_value=r):
            _apply_link_tile_state_change(bits, "green", 100)
        assert bits == ["every matured event fully linked"]
