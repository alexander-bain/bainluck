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
    ATTEMPTED_UNAVAILABLE, CHART_DATA_MISSING, CHART_DATA_READY, CHART_DATA_SPARSE,
    DIMENSIONS, EVENT_MISSING, NOT_APPLICABLE, PARSE_FAILURE, PRESENT,
    RECOVERABLE_MISSING, RENDER_UNVERIFIED, REQUEST_FAILURE, SCHEMA_VERSION,
    SPARSE_HISTORY, UNKNOWN, _overall_state,
    canonical_event_id, grade_event, main, match_bl, normalize_team,
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
    for dim in ("event_linkage", "final_result", "calibration_forecast", "ingame_history", "rendered_chart"):
        assert row["dimensions"][dim]["state"] == RECOVERABLE_MISSING
        assert row["dimensions"][dim]["attempt"] == EVENT_MISSING
    assert row["overall_state"] == RECOVERABLE_MISSING
    assert UNKNOWN not in {d["state"] for d in row["dimensions"].values()}
    assert row["chart_data_readiness"]["state"] == EVENT_MISSING


def test_fully_recovered_data_is_present_on_non_render_dimensions_but_render_stays_unknown():
    # Formerly blessed overall=present from snapshot counts alone (#1467 root counterexample).
    row = grade_event(_expected(), _full_bl())
    non_render = [d for name, d in row["dimensions"].items() if name != "rendered_chart"]
    assert all(d["state"] == PRESENT for d in non_render)
    assert row["non_render_state"] == PRESENT
    assert row["chart_data_readiness"]["state"] == CHART_DATA_READY
    assert row["dimensions"]["rendered_chart"]["state"] == UNKNOWN
    assert row["dimensions"]["rendered_chart"]["attempt"] == RENDER_UNVERIFIED
    assert row["overall_state"] == UNKNOWN


def test_sparse_history_is_flagged_recoverable_with_sparse_attempt():
    row = grade_event(_expected(), _full_bl(pregame_snaps=1, ingame_snaps=2, total_snaps=3))
    assert row["dimensions"]["pregame_history"]["state"] == RECOVERABLE_MISSING
    assert row["dimensions"]["pregame_history"]["attempt"] == SPARSE_HISTORY
    assert row["dimensions"]["ingame_history"]["attempt"] == SPARSE_HISTORY
    # Sparse data is a data-readiness diagnostic; it is not a render observation either.
    assert row["chart_data_readiness"]["state"] == CHART_DATA_SPARSE
    assert row["dimensions"]["rendered_chart"]["state"] == UNKNOWN
    # A known recoverable gap outranks an unverified render in the overall state.
    assert row["overall_state"] == RECOVERABLE_MISSING


def test_postponed_game_is_not_applicable_for_play_dimensions():
    row = grade_event(_expected(status="postponed", completed=False), _full_bl(completed=False, home_score=None, away_score=None))
    assert row["dimensions"]["final_result"]["state"] == NOT_APPLICABLE
    assert row["dimensions"]["ingame_history"]["state"] == NOT_APPLICABLE
    assert row["dimensions"]["rendered_chart"]["state"] == NOT_APPLICABLE
    assert row["chart_data_readiness"]["state"] == NOT_APPLICABLE
    # existence still graded (the event row exists)
    assert row["dimensions"]["event_existence"]["state"] == PRESENT


def test_future_scheduled_game_has_na_ingame_but_gradeable_existence():
    row = grade_event(_expected(status="scheduled", completed=False), _full_bl(completed=False, home_score=None, away_score=None, ingame_snaps=0))
    assert row["dimensions"]["ingame_history"]["state"] == NOT_APPLICABLE
    assert row["dimensions"]["final_result"]["state"] == NOT_APPLICABLE
    assert row["dimensions"]["rendered_chart"]["state"] == NOT_APPLICABLE


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


# --------------------------------------------------------------------------- #
# #1467 render honesty — snapshot density / history JSON are not render proof
# --------------------------------------------------------------------------- #
def _root_counterexample_bl():
    # artifacts/calibration-1467-render-proof-20261019/ROOT-COUNTEREXAMPLE.json
    return {"event_id": 901, "exists": True, "match_method": "espn_id", "status": "completed",
            "completed": True, "home_score": 100, "away_score": 90, "linkage_count": 2,
            "has_closing_prob": True, "pregame_snaps": 100, "ingame_snaps": 100, "total_snaps": 200}


def test_dense_aggregate_without_render_observation_is_not_rendered_present():
    row = grade_event(_expected(), _root_counterexample_bl())
    rc = row["dimensions"]["rendered_chart"]
    assert rc["state"] == UNKNOWN
    assert rc["attempt"] == RENDER_UNVERIFIED
    assert rc["state"] != PRESENT and rc["attempt"] != "complete"
    assert "not observed" in rc["evidence"]
    assert row["overall_state"] == UNKNOWN
    # The density survives as a separate, honestly-labelled data diagnostic.
    cdr = row["chart_data_readiness"]
    assert cdr["state"] == CHART_DATA_READY
    assert (cdr["total_snaps"], cdr["pregame_snaps"], cdr["ingame_snaps"]) == (200, 100, 100)
    assert "not a render observation" in cdr["evidence"]
    assert row["non_render_state"] == PRESENT
    # All eight original dimensions are still graded.
    assert tuple(row["dimensions"]) == DIMENSIONS and len(DIMENSIONS) == 8


def test_no_snapshot_data_is_a_missing_data_diagnostic_not_a_render_verdict():
    row = grade_event(_expected(), _full_bl(pregame_snaps=0, ingame_snaps=0, total_snaps=0))
    assert row["chart_data_readiness"]["state"] == CHART_DATA_MISSING
    assert row["dimensions"]["rendered_chart"]["state"] == UNKNOWN
    assert row["overall_state"] == RECOVERABLE_MISSING


def test_overall_state_known_gap_outranks_unverified():
    assert _overall_state([PRESENT, UNKNOWN]) == UNKNOWN
    assert _overall_state([PRESENT, RECOVERABLE_MISSING, UNKNOWN]) == RECOVERABLE_MISSING
    assert _overall_state([PRESENT, ATTEMPTED_UNAVAILABLE, UNKNOWN]) == ATTEMPTED_UNAVAILABLE
    assert _overall_state([PRESENT, NOT_APPLICABLE]) == PRESENT
    assert _overall_state([NOT_APPLICABLE]) == NOT_APPLICABLE


def test_summary_accounts_dense_rows_as_render_unverified_not_present():
    dense = grade_event(_expected(canonical_event_id="MLB:2026-06-15:tigers@rays:G1"), _root_counterexample_bl())
    sparse = grade_event(_expected(canonical_event_id="MLB:2026-06-16:a@b:G1", game_date="2026-06-16"),
                         _full_bl(pregame_snaps=1, ingame_snaps=2, total_snaps=3))
    missing = grade_event(_expected(canonical_event_id="MLB:2026-06-17:c@d:G1", game_date="2026-06-17"), None)
    postponed = grade_event(_expected(canonical_event_id="MLB:2026-06-18:e@f:G1", game_date="2026-06-18",
                                      status="postponed", completed=False),
                            _full_bl(completed=False, home_score=None, away_score=None))
    report = summarize([dense, sparse, missing, postponed], [])
    t = report["totals"]
    assert t["expected"] == 4
    assert t["present"] == 1             # only the postponed row: no render dimension applies
    assert t["unknown"] == 1             # the dense row — data ready, render unverified
    assert t["recoverable"] == 2         # sparse + missing event
    assert t["missing_event"] == 1
    assert t["non_render_present"] == 2  # dense + postponed
    assert t["render_unverified"] == 2   # dense + sparse (played, row exists, no render observed)
    assert report["dimension_totals"]["rendered_chart"][PRESENT] == 0
    assert report["chart_data_readiness_totals"] == {
        CHART_DATA_READY: 1, CHART_DATA_SPARSE: 1, CHART_DATA_MISSING: 0,
        EVENT_MISSING: 1, NOT_APPLICABLE: 1,
    }
    lm = report["per_league_month"]["MLB:2026-06"]
    assert lm["chart_data_readiness"][CHART_DATA_READY] == 1
    assert lm["non_render_present"] == 2
    # Worst cases name data gaps by data readiness, never by a render claim.
    worst = report["worst_cases"]
    assert "not_chart_ready" not in worst
    named = {n["canonical_event_id"] for n in worst["chart_data_not_ready"]["named"]}
    assert named == {"MLB:2026-06-16:a@b:G1", "MLB:2026-06-17:c@d:G1"}
    assert worst["chart_data_not_ready"]["count"] == 2
    assert report["schema_version"] == SCHEMA_VERSION
    assert "render" in report["render_evidence_note"].lower()


class FakeHistoryBackend(FakeBackend):
    """A backend whose /history JSON read always succeeds with many points."""

    def __init__(self, index):
        super().__init__(index)
        self.history_calls = []

    def fetch_history_points(self, event_id):
        self.history_calls.append(event_id)
        return {"result": "ok", "win_prob_points": 500, "per_source": {"espn": 500}, "odds_points": 80}


class LegacyChartBackend(FakeBackend):
    """Pre-#1467 backend shape: only the old ``fetch_chart_points`` name."""

    def __init__(self, index):
        super().__init__(index)
        self.history_calls = []

    def fetch_chart_points(self, event_id):
        self.history_calls.append(event_id)
        return {"result": "ok", "win_prob_points": 500, "per_source": {"espn": 500}, "odds_points": 80}


def _two_game_census_inputs():
    dense_g = _game("MLB:2026-06-01:alpha@beta:G1", "2026-06-01", "e1")
    sparse_g = {**_game("MLB:2026-06-01:gamma@delta:G1", "2026-06-01", "e2"),
                "away_team": "Gamma", "home_team": "Delta", "away_norm": "gamma", "home_norm": "delta"}
    sched = FakeSchedule({("MLB", "2026-06-01"): [dense_g, sparse_g]})
    index = {("MLB", "2026-06-01"): {
        "by_espn": {"e1": {**_root_counterexample_bl(), "event_id": 11},
                    "e2": {**_full_bl(pregame_snaps=1, ingame_snaps=2, total_snaps=3), "event_id": 12}},
        "by_teams": {},
    }}
    return sched, index


def test_history_json_success_without_render_never_upgrades_rendered_chart():
    sched, index = _two_game_census_inputs()
    backend = FakeHistoryBackend(index)
    census = run_census("2026-06-01", "2026-06-01", sched, backend, check_history_api=5)
    assert sorted(backend.history_calls) == [11, 12]
    assert "rendered_chart_proofs" not in census
    checks = census["history_api_checks"]
    assert len(checks) == 2
    assert all(c["render_observed"] is False for c in checks)
    assert all(c["result"] == "ok" and c["win_prob_points"] == 500 for c in checks)
    assert census["totals"]["present"] == 0
    assert census["dimension_totals"]["rendered_chart"][PRESENT] == 0
    assert "not a render observation" in census["history_api_check_note"]


def test_history_check_sample_still_selects_dense_representative_and_worst_case():
    # Dense rows went overall=unknown; they must not vanish from the representative sample.
    sched, index = _two_game_census_inputs()
    backend = FakeHistoryBackend(index)
    census = run_census("2026-06-01", "2026-06-01", sched, backend, check_history_api=1)
    by_role = {c["sample_role"]: c["bl_event_id"] for c in census["history_api_checks"]}
    assert by_role == {"representative": 11, "worst-case": 12}
    rep = next(c for c in census["history_api_checks"] if c["sample_role"] == "representative")
    assert rep["chart_data_readiness"] == CHART_DATA_READY
    assert rep["overall_state"] == UNKNOWN


def test_legacy_backend_and_verify_charts_kwarg_still_run_the_api_check():
    sched, index = _two_game_census_inputs()
    backend = LegacyChartBackend(index)
    census = run_census("2026-06-01", "2026-06-01", sched, backend, verify_charts=1)
    assert sorted(backend.history_calls) == [11, 12]
    assert all(c["render_observed"] is False for c in census["history_api_checks"])


def test_resumed_legacy_checkpoint_row_claiming_render_present_is_regraded(tmp_path):
    sched, index = _two_game_census_inputs()
    ck = tmp_path / "ck.json"
    run_census("2026-06-01", "2026-06-01", sched, FakeBackend(index), checkpoint=str(ck))
    legacy = json.loads(ck.read_text())
    legacy.pop("schema_version", None)
    row = legacy["rows"]["MLB:2026-06-01:alpha@beta:G1"]
    row["dimensions"]["rendered_chart"] = {"state": PRESENT, "attempt": "complete", "value": 200,
                                           "evidence": "200 total snapshot(s) (aggregate-density proxy)"}
    row["overall_state"] = PRESENT
    for k in ("chart_data_readiness", "non_render_state"):
        row.pop(k, None)
    ck.write_text(json.dumps(legacy))
    n_calls = len(sched.calls)

    census = run_census("2026-06-01", "2026-06-01", sched, FakeBackend(index), checkpoint=str(ck))
    assert len(sched.calls) == n_calls  # slates resumed from the checkpoint
    assert census["totals"]["present"] == 0
    resumed = json.loads(ck.read_text())
    assert resumed["schema_version"] == SCHEMA_VERSION
    regraded = resumed["rows"]["MLB:2026-06-01:alpha@beta:G1"]
    assert regraded["dimensions"]["rendered_chart"]["state"] == UNKNOWN
    assert regraded["overall_state"] == UNKNOWN
    assert regraded["chart_data_readiness"]["state"] == CHART_DATA_READY


def test_cli_help_does_not_advertise_history_json_as_rendered_proof(capsys):
    with pytest.raises(SystemExit):
        main(["census", "--help"])
    out = " ".join(capsys.readouterr().out.split())
    assert "--check-history-api" in out
    assert "--verify-charts" in out  # deprecated alias kept for compatibility
    assert "does not observe a rendered chart" in out
    assert "confirms rendered" not in out
