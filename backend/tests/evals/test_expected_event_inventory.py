"""Focused tests for #1467 expected-event inventory + named-event recovery ledger.

Covers the queue's required classes: missing Event rows, doubleheaders,
postponed/rescheduled games, sparse history, transient source failure, repeat
runs (idempotence), denominator independence, worst-case visibility,
attempt-state preservation, and the rule that ``error`` never becomes ``no data``.
All offline — pure functions + injected fake providers, no network, no DB.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.evals.expected_event_inventory import (
    ATTEMPTED_UNAVAILABLE, EVENT_MISSING, NOT_APPLICABLE, PARSE_FAILURE, PRESENT,
    RECOVERABLE_MISSING, REQUEST_FAILURE, SPARSE_HISTORY, UNKNOWN,
    canonical_event_id, grade_event, match_bl, normalize_team,
    parse_espn_scoreboard, run_census, summarize,
)

FIXTURES = json.loads(
    (Path(__file__).parents[2] / "scripts" / "evals" / "expected_event_inventory_fixtures.json").read_text()
)


# --------------------------------------------------------------------------- #
# Identity + parsing
# --------------------------------------------------------------------------- #
def test_normalize_team_uses_stable_nickname_token():
    assert normalize_team("Tampa Bay Rays") == "rays"
    assert normalize_team("St. Louis Cardinals") == "cardinals"
    assert normalize_team("") == ""


def test_canonical_id_is_independent_of_bl_and_includes_game_number():
    cid = canonical_event_id("MLB", "2026-06-15", "Detroit Tigers", "Tampa Bay Rays", 2)
    assert cid == "MLB:2026-06-15:tigers@rays:G2"


def test_parse_excludes_preseason_and_numbers_doubleheaders():
    games = parse_espn_scoreboard(FIXTURES["espn_mlb_doubleheader"], "MLB", "2026-06-15")
    ids = [g["canonical_event_id"] for g in games]
    # preseason (season.type=1) excluded -> 3 games, not 4
    assert len(games) == 3
    assert "MLB:2026-06-15:tigers@rays:G1" in ids
    assert "MLB:2026-06-15:tigers@rays:G2" in ids  # doubleheader numbered
    # doubleheader ordered by commence time
    g1 = next(g for g in games if g["canonical_event_id"].endswith("tigers@rays:G1"))
    g2 = next(g for g in games if g["canonical_event_id"].endswith("tigers@rays:G2"))
    assert g1["commence_time"] < g2["commence_time"]
    # postponed game is present in the inventory but marked postponed
    post = next(g for g in games if "yankees@sox" in g["canonical_event_id"])
    assert post["status"] == "postponed"


def test_malformed_event_does_not_drop_the_whole_slate():
    payload = {"events": [
        {"id": "1", "season": {"type": 2}},  # no competitions -> skipped, not fatal
        FIXTURES["espn_mlb_doubleheader"]["events"][0],
    ]}
    games = parse_espn_scoreboard(payload, "MLB", "2026-06-15")
    assert len(games) == 1


# --------------------------------------------------------------------------- #
# Grading — missing event, present, sparse, not-applicable
# --------------------------------------------------------------------------- #
def _expected(status="final", completed=True, **kw):
    base = {
        "canonical_event_id": "MLB:2026-06-15:tigers@rays:G1", "league": "MLB",
        "game_date": "2026-06-15", "away_team": "Detroit Tigers", "home_team": "Tampa Bay Rays",
        "espn_event_id": "401800001", "status": status, "completed": completed,
        "away_norm": "tigers", "home_norm": "rays",
    }
    base.update(kw)
    return base


def _full_bl(**kw):
    bl = {
        "event_id": 900, "exists": True, "match_method": "espn_id", "status": "completed",
        "completed": True, "home_score": 4, "away_score": 2, "has_closing_prob": True,
        "linkage_count": 3, "pregame_snaps": 10, "ingame_snaps": 40, "total_snaps": 55,
    }
    bl.update(kw)
    return bl


def test_missing_event_row_is_recoverable_missing_not_unknown():
    row = grade_event(_expected(), None)
    assert row["dimensions"]["event_existence"]["state"] == RECOVERABLE_MISSING
    assert row["dimensions"]["event_existence"]["attempt"] == EVENT_MISSING
    # downstream dims blocked on the missing row -> recoverable-missing, never unknown
    for dim in ("event_linkage", "final_result", "calibration_forecast", "ingame_history"):
        assert row["dimensions"][dim]["state"] == RECOVERABLE_MISSING
        assert row["dimensions"][dim]["attempt"] == EVENT_MISSING
    assert row["overall_state"] == RECOVERABLE_MISSING
    assert UNKNOWN not in {d["state"] for d in row["dimensions"].values()}


def test_fully_recovered_event_is_present_across_all_dimensions():
    row = grade_event(_expected(), _full_bl())
    assert row["overall_state"] == PRESENT
    assert all(d["state"] == PRESENT for d in row["dimensions"].values())


def test_sparse_history_is_flagged_recoverable_with_sparse_attempt():
    row = grade_event(_expected(), _full_bl(pregame_snaps=1, ingame_snaps=2, total_snaps=3))
    assert row["dimensions"]["pregame_history"]["state"] == RECOVERABLE_MISSING
    assert row["dimensions"]["pregame_history"]["attempt"] == SPARSE_HISTORY
    assert row["dimensions"]["ingame_history"]["attempt"] == SPARSE_HISTORY
    assert row["dimensions"]["rendered_chart"]["state"] == RECOVERABLE_MISSING


def test_postponed_game_is_not_applicable_for_play_dimensions():
    row = grade_event(_expected(status="postponed", completed=False), _full_bl(completed=False, home_score=None, away_score=None))
    assert row["dimensions"]["final_result"]["state"] == NOT_APPLICABLE
    assert row["dimensions"]["ingame_history"]["state"] == NOT_APPLICABLE
    # existence still graded (the event row exists)
    assert row["dimensions"]["event_existence"]["state"] == PRESENT


def test_future_scheduled_game_has_na_ingame_but_gradeable_existence():
    row = grade_event(_expected(status="scheduled", completed=False), _full_bl(completed=False, home_score=None, away_score=None, ingame_snaps=0))
    assert row["dimensions"]["ingame_history"]["state"] == NOT_APPLICABLE
    assert row["dimensions"]["final_result"]["state"] == NOT_APPLICABLE


# --------------------------------------------------------------------------- #
# Matching
# --------------------------------------------------------------------------- #
def test_match_prefers_espn_id_then_falls_back_to_date_teams():
    idx = {
        "by_espn": {"401800001": {"event_id": 1, "exists": True}},
        "by_teams": {("2026-06-15", "tigers", "rays"): {"event_id": 2, "exists": True}},
    }
    assert match_bl(_expected(), idx)["match_method"] == "espn_id"
    # no espn hit -> date+teams
    assert match_bl(_expected(espn_event_id="nope"), idx)["match_method"] == "date+teams"
    # neither -> None (event genuinely missing)
    assert match_bl(_expected(espn_event_id="x", away_norm="a", home_norm="b"), idx) is None


# --------------------------------------------------------------------------- #
# Census summary — worst-case visibility + error != no-data
# --------------------------------------------------------------------------- #
def test_summary_names_worst_cases_and_never_hides_missing_events():
    rows = [
        grade_event(_expected(canonical_event_id="MLB:2026-06-15:tigers@rays:G1"), _full_bl()),
        grade_event(_expected(canonical_event_id="MLB:2026-06-16:a@b:G1", game_date="2026-06-16",
                              away_team="A", home_team="B", away_norm="a", home_norm="b"), None),
    ]
    report = summarize(rows, [])
    assert report["totals"]["expected"] == 2
    assert report["totals"]["missing_event"] == 1
    named = report["worst_cases"]["missing_event"]["named"]
    assert any("a@b" in n["canonical_event_id"] for n in named)


def test_slate_fetch_error_is_recorded_not_collapsed_to_zero():
    report = summarize([], [
        {"league": "NBA", "date": "2026-04-01", "result": REQUEST_FAILURE, "detail": "timeout"},
        {"league": "NBA", "date": "2026-04-02", "result": PARSE_FAILURE, "detail": "bad json"},
        {"league": "NBA", "date": "2026-04-03", "result": "ok"},
    ])
    sl = report["slate_ledger"]
    assert sl[REQUEST_FAILURE] == 1
    assert sl[PARSE_FAILURE] == 1
    assert sl["ok"] == 1
    assert len(sl["failed_slates"]) == 2  # named, not silently dropped


def test_june_is_broken_out_separately():
    rows = [
        grade_event(_expected(canonical_event_id="MLB:2026-05-01:a@b:G1", game_date="2026-05-01"), _full_bl()),
        grade_event(_expected(canonical_event_id="MLB:2026-06-01:c@d:G1", game_date="2026-06-01"), _full_bl()),
    ]
    report = summarize(rows, [])
    assert "MLB:2026-06" in report["june_breakout"]
    assert "MLB:2026-05" not in report["june_breakout"]


# --------------------------------------------------------------------------- #
# Fake providers for census orchestration (denominator independence, idempotence)
# --------------------------------------------------------------------------- #
class FakeSchedule:
    """Returns a fixed slate; can be told to fail specific (league, day) fetches."""

    def __init__(self, slates, failures=None):
        self.slates = slates  # {(league, day): [games]}
        self.failures = failures or {}  # {(league, day): result_class}
        self.calls = []

    def fetch(self, league, day):
        self.calls.append((league, day))
        if (league, day) in self.failures:
            return {"result": self.failures[(league, day)], "games": [], "detail": "injected"}
        return {"result": "ok", "games": self.slates.get((league, day), [])}


class FakeBackend:
    def __init__(self, index):
        self.index = index  # {(league, month_start): bl_index}
        self.calls = []

    def fetch_bl_side(self, league, month_start, month_end):
        self.calls.append((league, month_start))
        return self.index.get((league, month_start), {"by_espn": {}, "by_teams": {}})


def _game(cid, date_str, espn_id, status="final"):
    away, home = "Alpha", "Beta"
    return {
        "league": "MLB", "espn_event_id": espn_id, "game_date": date_str,
        "commence_time": f"{date_str}T20:00Z", "away_team": away, "home_team": home,
        "away_norm": "alpha", "home_norm": "beta", "status": status, "completed": status == "final",
        "away_score": 1, "home_score": 2, "season_type": 2, "game_number": 1,
        "canonical_event_id": cid,
    }


def test_denominator_independent_of_bl_rows():
    # ESPN lists a game; Bain Luck has NO matching row -> it must still be counted.
    sched = FakeSchedule({("MLB", "2026-06-01"): [_game("MLB:2026-06-01:alpha@beta:G1", "2026-06-01", "e1")]})
    backend = FakeBackend({})  # empty BL side
    census = run_census("2026-06-01", "2026-06-01", sched, backend)
    assert census["totals"]["expected"] == 1
    assert census["totals"]["missing_event"] == 1
    # census skips NBA/NHL empty days but still fetched them (no crash)
    assert census["window"]["expected_events"] == 1


def test_census_transient_source_failure_named_not_zero():
    sched = FakeSchedule(
        {("MLB", "2026-06-02"): [_game("MLB:2026-06-02:alpha@beta:G1", "2026-06-02", "e2")]},
        failures={("MLB", "2026-06-01"): REQUEST_FAILURE},
    )
    backend = FakeBackend({})
    census = run_census("2026-06-01", "2026-06-02", sched, backend)
    assert census["slate_ledger"][REQUEST_FAILURE] >= 1
    assert any(f["date"] == "2026-06-01" and f["league"] == "MLB"
               for f in census["slate_ledger"]["failed_slates"])


def test_census_is_idempotent_across_repeat_runs(tmp_path):
    ck = tmp_path / "ck.json"
    sched = FakeSchedule({("MLB", "2026-06-01"): [_game("MLB:2026-06-01:alpha@beta:G1", "2026-06-01", "e1")]})
    backend = FakeBackend({})
    first = run_census("2026-06-01", "2026-06-01", sched, backend, checkpoint=str(ck))
    n_calls_first = len(sched.calls)
    # Second run reuses the checkpoint: no new schedule fetches, identical census.
    second = run_census("2026-06-01", "2026-06-01", sched, backend, checkpoint=str(ck))
    assert len(sched.calls) == n_calls_first  # slates served from checkpoint
    assert json.dumps(first["totals"], sort_keys=True) == json.dumps(second["totals"], sort_keys=True)
    assert json.dumps(first["per_league_month"], sort_keys=True, default=str) == \
        json.dumps(second["per_league_month"], sort_keys=True, default=str)


def test_force_rerun_refetches_slates(tmp_path):
    ck = tmp_path / "ck.json"
    sched = FakeSchedule({("MLB", "2026-06-01"): [_game("MLB:2026-06-01:alpha@beta:G1", "2026-06-01", "e1")]})
    backend = FakeBackend({})
    run_census("2026-06-01", "2026-06-01", sched, backend, checkpoint=str(ck))
    n = len(sched.calls)
    run_census("2026-06-01", "2026-06-01", sched, backend, checkpoint=str(ck), force=True)
    assert len(sched.calls) > n  # force ignores the checkpoint
