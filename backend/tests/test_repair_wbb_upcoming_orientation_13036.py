"""Tests for #13036 (Ruling 269: A) upcoming WBB ``(W)`` orientation repair script."""

from __future__ import annotations

import argparse
import asyncio
import json
import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text

import scripts.repair_wbb_upcoming_orientation_13036 as mod


def _dt(hour: int = 18, day: int = 15) -> datetime:
    return datetime(2025, 2, day, hour, 0, tzinfo=timezone.utc)


def _cand(
    event_id: int,
    home: str,
    away: str,
    *,
    sport_key: str = "basketball_other",
    commence_time: datetime | None = None,
    wps: dict[str, Any] | None = None,
    home_norm: str | None = None,
    away_norm: str | None = None,
    **overrides: Any,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "id": event_id,
        "sport_id": 99 if sport_key == "basketball_other" else 42,
        "sport_key": sport_key,
        "home_team_name": home,
        "away_team_name": away,
        "home_team_normalized": home_norm,
        "away_team_normalized": away_norm,
        "home_team_alt_names": None,
        "away_team_alt_names": None,
        "home_team_id": None,
        "away_team_id": None,
        "commence_time": commence_time or _dt(),
        "status": "scheduled",
        "espn_id": None,
        "external_id": None,
        "home_score": None,
        "away_score": None,
        "completed_at": None,
        "opening_home_probability": None,
        "opening_away_probability": None,
        "opening_home_spread": None,
        "opening_favorite": None,
        "closing_home_probability": None,
        "closing_away_probability": None,
        "closing_home_spread": None,
        "espn_win_prob_home": None,
        "win_probability_sources": wps,
        "event_tags": [],
    }
    row.update(overrides)
    return row


def _twin(
    event_id: int,
    home: str,
    away: str,
    *,
    commence_time: datetime | None = None,
    espn_id: str | None = "401911746",
    external_id: str | None = "odds_1",
    event_tags: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "id": event_id,
        "home_team_name": home,
        "away_team_name": away,
        "commence_time": commence_time or _dt(),
        "status": "scheduled",
        "espn_id": espn_id,
        "external_id": external_id,
        "event_tags": event_tags or [],
    }


class TestWriteGates:
    def _args(self, **kw: Any) -> argparse.Namespace:
        defaults = {
            "apply": False,
            "backup": False,
            "expect_plan_sha256": None,
            "rollback": None,
            "settle_rounds": 2,
        }
        defaults.update(kw)
        return argparse.Namespace(**defaults)

    def test_dry_run_allowed_without_heroku_app(self, monkeypatch):
        monkeypatch.delenv("HEROKU_APP_NAME", raising=False)
        assert mod.check_write_gates(self._args()) is None

    def test_apply_requires_backup_hash_and_producer_app(self, monkeypatch):
        monkeypatch.setenv("HEROKU_APP_NAME", "bainluck")
        assert "requires --backup" in (
            mod.check_write_gates(self._args(apply=True)) or ""
        )
        assert "expect-plan-sha256" in (
            mod.check_write_gates(self._args(apply=True, backup=True)) or ""
        )
        assert "settle-rounds" in (
            mod.check_write_gates(
                self._args(
                    apply=True, backup=True, expect_plan_sha256="abc", settle_rounds=1
                )
            )
            or ""
        )
        assert (
            mod.check_write_gates(
                self._args(apply=True, backup=True, expect_plan_sha256="abc")
            )
            is None
        )

    def test_apply_and_rollback_refuse_wrong_or_unset_app(self, monkeypatch):
        monkeypatch.delenv("HEROKU_APP_NAME", raising=False)
        assert "REFUSING to write" in (
            mod.check_write_gates(
                self._args(apply=True, backup=True, expect_plan_sha256="abc")
            )
            or ""
        )
        assert "REFUSING to write" in (
            mod.check_write_gates(self._args(rollback="run123")) or ""
        )
        monkeypatch.setenv("HEROKU_APP_NAME", "bainluck-staging")
        assert "REFUSING to write" in (
            mod.check_write_gates(self._args(rollback="run123")) or ""
        )
        monkeypatch.setenv("HEROKU_APP_NAME", "bainluck")
        assert mod.check_write_gates(self._args(rollback="run123")) is None

    def test_apply_and_rollback_mutually_exclusive(self, monkeypatch):
        monkeypatch.setenv("HEROKU_APP_NAME", "bainluck")
        assert "mutually exclusive" in (
            mod.check_write_gates(
                self._args(
                    apply=True,
                    backup=True,
                    expect_plan_sha256="abc",
                    rollback="run123",
                )
            )
            or ""
        )


class TestProbabilityFlipping:
    def test_flips_both_dict_and_bare_float_shapes_and_is_self_inverse(self):
        wps = {
            "polymarket": {"value": 0.725, "updated_at": "2025-02-15T18:00:00Z"},
            "kalshi": 0.71,
            "meta": {"note": "kept", "flag": True},
        }
        flipped = mod.flip_win_probability_sources(wps)
        assert flipped == {
            "polymarket": {"value": 0.275, "updated_at": "2025-02-15T18:00:00Z"},
            "kalshi": 0.29,
            "meta": {"note": "kept", "flag": True},
        }
        assert mod.flip_win_probability_sources(flipped) == wps
        # Original dict was not mutated
        assert wps["polymarket"]["value"] == 0.725

    def test_handles_none_empty_and_boundaries(self):
        assert mod.flip_win_probability_sources(None) is None
        assert mod.flip_win_probability_sources({}) == {}
        assert mod.flip_probability(0.0) == 1.0
        assert mod.flip_probability(1.0) == 0.0
        assert mod.flip_opening_favorite("home") == "away"
        assert mod.flip_opening_favorite("away") == "home"
        assert mod.flip_opening_favorite("even") == "even"
        assert mod.flip_opening_favorite(None) is None


class TestTwinDetectionAndPlanBuilding:
    def test_splits_twin_moves_and_standalone_repairs_cleanly(self):
        c_twin = _cand(
            101,
            "Fordham Rams (W)",
            "Duke Blue Devils (W)",
            wps={"polymarket": {"value": 0.08}},
        )
        c_solo = _cand(
            102,
            "Notre Dame Fighting Irish (W)",
            "USC Trojans (W)",
            home_norm="Notre Dame Fighting Irish (W)",
            away_norm="USC Trojans (W)",
            wps={"polymarket": {"value": 0.62, "updated_at": "2025-02-15T17:00:00Z"}},
        )
        clean = [_twin(901, "Duke Blue Devils", "Fordham Rams")]
        espn_fixtures = [
            {
                "espn_id": "401999001",
                "kickoff": _dt(),
                "home": "USC Trojans",
                "away": "Notre Dame Fighting Irish",
                "neutral": False,
            }
        ]
        plan = mod.build_plan(
            candidates=[c_twin, c_solo],
            clean_twins=clean,
            markets_by_event={101: [{"market_id": 5001, "outcome_count": 2}]},
            anchors_by_event={101: [{"anchor_id": 7001}]},
            child_counts_by_event={
                101: {"win_prob_snapshots": 3},
                102: {"win_prob_snapshots": 5},
            },
            espn_fixtures=espn_fixtures,
        )

        assert plan.refusals == []
        assert plan.internal_w_duplicate_pairs == []
        assert len(plan.twin_moves) == 1
        tm = plan.twin_moves[0]
        assert tm.event_id == 101
        assert tm.twin_id == 901
        assert tm.twin_orientation == "swapped"
        assert tm.market_ids == (5001,)
        assert tm.anchor_ids == (7001,)

        assert len(plan.standalone_repairs) == 1
        sr = plan.standalone_repairs[0]
        assert sr.event_id == 102
        assert sr.new_home == "USC Trojans"
        assert sr.new_away == "Notre Dame Fighting Irish"
        assert sr.new_home_norm == "USC Trojans"
        assert sr.new_away_norm == "Notre Dame Fighting Irish"
        assert sr.new_wps["polymarket"]["value"] == 0.38
        assert sr.espn_check == "confirmed_reversed"
        assert sr.espn_id == "401999001"

    def test_twin_matching_blocks_shared_token_rivals_and_respects_window(self):
        cand = _cand(201, "Ohio Bobcats (W)", "Akron Zips (W)")
        rival = _twin(902, "Akron Zips", "Ohio State Buckeyes")
        far = _twin(903, "Akron Zips", "Ohio Bobcats", commence_time=_dt() + timedelta(hours=50))
        twin, orient, err = mod.find_clean_twin(cand, [rival, far])
        assert (twin, orient, err) == (None, None, None)

    def test_prefers_single_espn_twin_and_refuses_ambiguous_tie(self):
        cand = _cand(202, "Fordham Rams (W)", "Duke Blue Devils (W)")
        t_espn = _twin(910, "Duke Blue Devils", "Fordham Rams", espn_id="401911746")
        t_bare = _twin(911, "Duke Blue Devils", "Fordham Rams", espn_id=None, external_id=None)
        twin, orient, err = mod.find_clean_twin(cand, [t_espn, t_bare])
        assert twin["id"] == 910
        assert orient == "swapped"
        assert err is None

        t_espn_2 = _twin(912, "Duke Blue Devils", "Fordham Rams", espn_id="401911999")
        twin2, orient2, err2 = mod.find_clean_twin(cand, [t_espn, t_espn_2])
        assert twin2 is None
        assert "AMBIGUOUS_TWIN" in (err2 or "")

    def test_refuses_espn_already_aligned_and_unhandled_fields(self):
        c_aligned = _cand(301, "Duke Blue Devils (W)", "Fordham Rams (W)")
        c_scored = _cand(302, "UCLA Bruins (W)", "Stanford Cardinal (W)", home_score=44)
        c_odds = _cand(303, "Texas Longhorns (W)", "Baylor Bears (W)")
        fixtures = [
            {
                "espn_id": "401911746",
                "kickoff": _dt(),
                "home": "Duke Blue Devils",
                "away": "Fordham Rams",
                "neutral": False,
            }
        ]
        plan = mod.build_plan(
            candidates=[c_aligned, c_scored, c_odds],
            clean_twins=[],
            markets_by_event={},
            anchors_by_event={},
            child_counts_by_event={303: {"odds_snapshots": 2}},
            espn_fixtures=fixtures,
        )
        assert plan.standalone_repairs == []
        reasons = {r["event_id"]: r["reason"] for r in plan.refusals}
        assert "espn_already_aligned" in reasons[301]
        assert "has_espn_or_score_or_completed" in reasons[302]
        assert "2 odds_snapshots" in reasons[303]

    def test_detects_internal_w_duplicate_pairs(self):
        c1 = _cand(401, "Fordham Rams (W)", "Duke Blue Devils (W)", sport_key="basketball_other")
        c2 = _cand(402, "Fordham Rams (W)", "Duke Blue Devils (W)", sport_key="basketball_wncaab")
        plan = mod.build_plan([c1, c2], [], {}, {}, {})
        assert plan.internal_w_duplicate_pairs == [(401, 402)]


class TestPlanHashAndDryRunReport:
    def test_plan_hash_stable_across_live_quote_ticks_and_sensitive_to_drift(self):
        c1 = _cand(501, "Notre Dame (W)", "USC (W)", wps={"polymarket": {"value": 0.61}})
        c2 = _cand(501, "Notre Dame (W)", "USC (W)", wps={"polymarket": {"value": 0.64}})
        p1 = mod.build_plan([c1], [], {}, {}, {})
        p2 = mod.build_plan([c2], [], {}, {}, {})
        assert mod.compute_plan_sha256(p1) == mod.compute_plan_sha256(p2)

        c3 = _cand(502, "Notre Dame (W)", "USC (W)", wps={"polymarket": {"value": 0.61}})
        p3 = mod.build_plan([c1, c3], [], {}, {}, {})
        assert mod.compute_plan_sha256(p1) != mod.compute_plan_sha256(p3)

    def test_dry_run_report_includes_buckets_examples_backup_and_rollback(self):
        c_twin = _cand(101, "Fordham Rams (W)", "Duke Blue Devils (W)")
        c_solo = _cand(
            102,
            "Notre Dame Fighting Irish (W)",
            "USC Trojans (W)",
            wps={"polymarket": {"value": 0.60}},
        )
        plan = mod.build_plan(
            candidates=[c_twin, c_solo],
            clean_twins=[_twin(901, "Duke Blue Devils", "Fordham Rams")],
            markets_by_event={101: [{"market_id": 5001, "outcome_count": 2}]},
            anchors_by_event={101: [{"anchor_id": 7001}]},
            child_counts_by_event={},
        )
        sha = mod.compute_plan_sha256(plan)
        report = mod.format_dry_run_report(plan, sha, examples=10)
        assert f"plan_sha256: {sha}" in report
        assert "bak_13036_wbb_events" in report
        assert "--rollback <run_id>" in report
        assert f"--expect-plan-sha256 {sha}" in report
        assert "event 101" in report
        assert "event 102" in report
        assert "polymarket=0.6000" in report
        assert "polymarket=0.4000" in report


class TestSettlementAndSqlHygiene:
    def test_classify_settlement_all_verdicts(self):
        assert mod.classify_settlement(None, None) == "UNPRICED"
        assert mod.classify_settlement(None, 0.4) == "NOT-YET-WRITTEN"
        assert mod.classify_settlement(0.4, None) == "SOURCE-WOULD-RETIRE"
        assert mod.classify_settlement(0.4001, 0.4000) == "SETTLED"
        assert mod.classify_settlement(0.6000, 0.4000) == "REVERTED"
        assert mod.classify_settlement(0.5100, 0.4000) == "UNEXPECTED"

    def test_sql_has_no_broken_bind_casts(self):
        src = Path(mod.__file__).read_text(encoding="utf-8")
        # Any `:param::type` breaks SQLAlchemy bind parsing on Postgres
        bad = re.findall(r":[a-zA-Z_][a-zA-Z0-9_]*::[a-zA-Z_]+", src)
        assert bad == [], f"found unsafe SQLAlchemy bind casts: {bad}"

        for sql_text, expected_binds in (
            (mod.CANDIDATE_SQL, {"sport_keys"}),
            (mod.CLEAN_TWINS_SQL, {"target_sport_key", "window_start", "window_end"}),
            (mod.MARKETS_FOR_EVENTS_SQL, {"ids"}),
            (mod.ANCHORS_FOR_EVENTS_SQL, {"ids"}),
            (mod.CHILD_COUNTS_SQL, {"ids"}),
            (mod.REMAINING_UPCOMING_W_SQL, {"sport_keys"}),
            (mod.RESTAMP_POLY_SQL, {"event_id", "value"}),
            (mod.RESTAMP_SNAPSHOTS_SQL, {"event_id", "since", "expected", "eps"}),
        ):
            compiled = text(sql_text)
            assert set(compiled._bindparams.keys()) == expected_binds


class _FakeResult:
    def __init__(
        self,
        *,
        rowcount: int = 1,
        scalar: Any = None,
        mapping_row: dict[str, Any] | None = None,
    ):
        self.rowcount = rowcount
        self._scalar = scalar
        self._mapping_row = mapping_row

    def scalar_one(self):
        return self._scalar

    def scalar_one_or_none(self):
        return self._scalar

    def mappings(self):
        return self

    def one_or_none(self):
        return self._mapping_row


class _FakeSession:
    def __init__(self, events: dict[int, dict[str, Any]], outcome_counts: dict[int, int]):
        self.events = events
        self.outcome_counts = outcome_counts
        self.executed: list[tuple[str, dict[str, Any]]] = []

    async def execute(self, stmt, params: dict[str, Any] | None = None):
        sql = str(stmt)
        params = dict(params or {})
        self.executed.append((sql, params))
        if "FROM events" in sql and "FOR UPDATE" in sql:
            return _FakeResult(mapping_row=self.events.get(params["eid"]))
        if "SELECT id FROM events WHERE id = :tid" in sql:
            return _FakeResult(scalar=params["tid"])
        if "FROM futures_outcomes WHERE market_id" in sql:
            return _FakeResult(scalar=self.outcome_counts[params["mid"]])
        if f"SELECT count(*) FROM {mod.BACKUP_EVENTS_TABLE}" in sql:
            return _FakeResult(scalar=len(self.events))
        return _FakeResult(rowcount=1)


class TestAtomicApplyAndRollbackFlow:
    def test_apply_and_rollback_execute_all_backup_and_restore_steps(self):
        c_twin = _cand(101, "Fordham Rams (W)", "Duke Blue Devils (W)")
        c_solo = _cand(
            102,
            "Notre Dame (W)",
            "USC (W)",
            opening_home_spread=Decimal("-4.5"),
            opening_favorite="home",
            win_probability_sources={"polymarket": {"value": 0.65}},
        )
        plan = mod.build_plan(
            candidates=[c_twin, c_solo],
            clean_twins=[_twin(901, "Duke Blue Devils", "Fordham Rams")],
            markets_by_event={101: [{"market_id": 5001, "outcome_count": 2}]},
            anchors_by_event={101: [{"anchor_id": 7001}]},
            child_counts_by_event={102: {"win_prob_snapshots": 1}},
        )
        session = _FakeSession(
            events={101: c_twin, 102: c_solo},
            outcome_counts={5001: 2},
        )
        stats = asyncio.run(mod.apply_plan_atomic(session, plan, 42, "run-test-1"))
        assert stats == {
            "events_backed_up": 2,
            "markets_moved": 1,
            "anchors_moved": 1,
            "twins_retired": 1,
            "standalone_repaired": 1,
            "snapshots_swapped": 1,
        }
        # Verify the standalone UPDATE flipped wps, spread, favorite, names, and sport
        standalone_updates = [
            p for sql, p in session.executed if "SET sport_id = :wncaab_sport_id" in sql
        ]
        assert len(standalone_updates) == 1
        upd = standalone_updates[0]
        assert upd["wncaab_sport_id"] == 42
        assert upd["new_home"] == "USC"
        assert upd["new_away"] == "Notre Dame"
        assert upd["new_opening_spread"] == Decimal("4.5")
        assert upd["new_opening_fav"] == "away"
        assert json.loads(upd["wps_json"]) == {"polymarket": {"value": 0.35}}

        rb_stats = asyncio.run(mod.rollback_run_atomic(session, "run-test-1"))
        assert rb_stats == {
            "events_restored": 1,
            "markets_restored": 1,
            "anchors_restored": 1,
            "snapshots_restored": 1,
        }

    def test_apply_aborts_if_event_status_drifted(self):
        c_solo = _cand(102, "Notre Dame (W)", "USC (W)")
        plan = mod.build_plan([c_solo], [], {}, {}, {})
        drifted = dict(c_solo, status="live")
        session = _FakeSession(events={102: drifted}, outcome_counts={})
        with pytest.raises(RuntimeError, match="compare-and-set failed"):
            asyncio.run(mod.apply_plan_atomic(session, plan, 42, "run-drift"))
