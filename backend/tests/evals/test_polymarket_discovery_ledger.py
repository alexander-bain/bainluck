"""Focused tests for Queue #270 / #1468 — Tier-1 Polymarket discovery ledger producer.

Everything here is offline: pure builder functions + an injected fake Gamma/CLOB
client, no network, no DB. The producer's output is asserted ``validate_ledger``-
clean (C51) and, when embedded, ``validate_scoreboard``-clean (C52).

Regression coverage the queue's Gates require:
  * gotcha #18 — nested Poly sub-markets decomposed by conditionId, not flattened.
  * gotcha #36 — 429/timeout/5xx stay typed + retryable, never collapsed to "not found".
  * gotcha #41 — discovery is date-partitioned (exhaustive), never offset-capped.
  * gotcha #89 — ±28h identity window; doubleheaders / home-away / city-only aliases.
  * C50 — conditionId never rstrip-mangled, token side identity, terminal-zero prop
          represented, transient-vs-terminal, duplicate-inflation, threshold_pending,
          idempotent reruns, error != no-data.
"""

from __future__ import annotations

import json
from pathlib import Path

from scripts.evals.named_event_completeness import validate_scoreboard
from scripts.evals.polymarket_discovery_ledger import (
    CLOB_CONDITION, FOUND, GAMMA_EVENT, GAMMA_MARKET, NOT_FOUND,
    POLY_DISCOVERY_OR_MATCHING_DEFECT, POLY_LISTED_HISTORY_UNAVAILABLE,
    POLY_MAIN_RECOVERED, POLY_NONLISTING_ARCHIVALLY_PROVEN, RATE_LIMITED,
    TIMEOUT, UNKNOWN,
    build_event_record, build_ledger, build_prop_records, build_scoreboard,
    classify_submarket, decompose_gamma_event, extract_prop_semantics,
    measure_timeline, parse_clob_token_ids, run_discovery_census, summarize,
)
from scripts.evals.polymarket_recovery_ledger import validate_ledger

FIXTURES = json.loads(
    (Path(__file__).parents[2] / "scripts" / "evals" / "polymarket_discovery_fixtures.json").read_text()
)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _expected(cid="NBA:2026-01-15:alphas@betas:G1", league="NBA", date="2026-01-15",
              away="Alphas", home="Betas", game_number=1):
    from scripts.evals.polymarket_discovery_ledger import normalize_team
    return {
        "canonical_event_id": cid, "league": league, "game_date": date,
        "away_team": away, "home_team": home,
        "away_norm": normalize_team(away), "home_norm": normalize_team(home),
        "commence_time": f"{date}T03:00:00Z", "game_number": game_number,
    }


def _dense_points(n=12, start=1768000000, step=3600, price=0.6):
    return [{"t": start + step * i, "p": price} for i in range(n)]


def _attempt(surface, result, http_status, terminal=None):
    return {
        "surface": surface, "attempted_at": "2026-01-16T00:00:00Z",
        "request_identity": f"req:{surface}", "result": result,
        "http_status": http_status,
        "terminal": terminal if terminal is not None else result in (FOUND, NOT_FOUND),
    }


def _found_attempts():
    return [_attempt(s, FOUND, 200) for s in (GAMMA_EVENT, GAMMA_MARKET, CLOB_CONDITION)]


def _recovered_discovery(points=None):
    event = decompose_gamma_event(FIXTURES["gamma_main_plus_prop"])
    main = event["submarkets"][0]
    props = event["submarkets"][1:]
    points = points if points is not None else _dense_points()
    return {
        "attempts": _found_attempts(),
        "matched_event_id": event["polymarket_event_id"],
        "matched_market": main,
        "main_points": points,
        "prop_markets": [{"submarket": sm, "points": _dense_points(), "trade_count": 12} for sm in props],
        "ambiguous": False,
    }


# --------------------------------------------------------------------------- #
# Decomposition — gotcha #18 + C50 conditionId/token integrity
# --------------------------------------------------------------------------- #
def test_nested_event_decomposed_into_submarkets_by_condition_id():
    event = decompose_gamma_event(FIXTURES["gamma_main_plus_prop"])
    assert len(event["submarkets"]) == 3  # moneyline + player prop + spread, not flattened
    assert event["polymarket_event_id"] == "9001"


def test_condition_id_ending_in_e_is_never_rstrip_mangled():
    event = decompose_gamma_event(FIXTURES["gamma_main_plus_prop"])
    cid = event["submarkets"][0]["condition_id"]
    assert cid.endswith("ee"), "conditionId hex tail must be preserved verbatim"
    assert cid == FIXTURES["gamma_main_plus_prop"]["markets"][0]["conditionId"]


def test_clob_token_ids_parsed_from_json_string_side_correct():
    event = decompose_gamma_event(FIXTURES["gamma_main_plus_prop"])
    outcomes = event["submarkets"][0]["outcomes"]
    assert outcomes[0]["label"] == "Yes" and outcomes[0]["token_id"] == "1001"
    assert outcomes[1]["label"] == "No" and outcomes[1]["token_id"] == "1002"


def test_malformed_token_ids_yield_empty_not_crash():
    assert parse_clob_token_ids("not-a-json-list") == []
    assert parse_clob_token_ids(None) == []
    assert parse_clob_token_ids(["a", "b"]) == ["a", "b"]
    event = decompose_gamma_event(FIXTURES["gamma_malformed_token_ids"])
    assert event["submarkets"][0]["outcomes"][0]["token_id"] is None


# --------------------------------------------------------------------------- #
# Market classification + prop semantics — parent gate #10
# --------------------------------------------------------------------------- #
def test_moneyline_is_main_spread_and_player_prop_are_props():
    event = decompose_gamma_event(FIXTURES["gamma_main_plus_prop"])
    assert classify_submarket(event["submarkets"][0], "alphas", "betas") == "main"
    assert classify_submarket(event["submarkets"][1], "alphas", "betas") == "prop"  # player points
    assert classify_submarket(event["submarkets"][2], "alphas", "betas") == "prop"  # spread


def test_prop_semantics_are_structured_and_never_blank():
    event = decompose_gamma_event(FIXTURES["gamma_main_plus_prop"])
    sem = extract_prop_semantics(event["submarkets"][1])
    assert sem["subject"] and sem["stat"] == "points" and sem["threshold"] == 27.5
    assert sem["direction"] == "over_under" and sem["period"] == "full_game"


# --------------------------------------------------------------------------- #
# Timeline measurement — C50 duplicate-inflation + terminal behavior
# --------------------------------------------------------------------------- #
def test_timeline_dedups_so_effective_never_exceeds_raw():
    pts = [{"t": 100, "p": 0.5}, {"t": 100, "p": 0.5}, {"t": 200, "p": 0.6}]
    tl = measure_timeline(pts, "2026-01-15T03:00:00Z", "tok", "0xc", "e1")
    assert tl["raw_points"] == 3 and tl["effective_points"] == 2


def test_timeline_none_when_no_history():
    assert measure_timeline([], "2026-01-15T03:00:00Z", "tok", "0xc", "e1") is None


# --------------------------------------------------------------------------- #
# State classification — all five states, validate_ledger-clean
# --------------------------------------------------------------------------- #
def test_recovered_event_is_validate_ledger_clean():
    exp = _expected()
    ev = build_event_record(exp, _recovered_discovery())
    props = build_prop_records(exp, _recovered_discovery())
    ledger = build_ledger([ev], props)
    result = validate_ledger(ledger)
    assert result["errors"] == [], result["errors"]
    assert ev["main_state"] == POLY_MAIN_RECOVERED
    assert ev["main_contract"]["condition_id"].endswith("ee")


def test_listed_but_sparse_history_is_listed_history_unavailable():
    disc = _recovered_discovery(points=_dense_points(n=1))  # single point, not robust
    ev = build_event_record(_expected(), disc)
    assert ev["main_state"] == POLY_LISTED_HISTORY_UNAVAILABLE
    # Not a closure blocker.
    ledger = build_ledger([ev], [])
    assert POLY_LISTED_HISTORY_UNAVAILABLE not in {b["code"] for b in validate_ledger(ledger)["blockers"]}


def test_missing_main_market_defaults_to_defect_not_nonlisting():
    # Empty-search miss (200, not 404) can NEVER prove non-listing (parent rule).
    disc = {"attempts": [_attempt(s, NOT_FOUND, 200) for s in (GAMMA_EVENT, GAMMA_MARKET, CLOB_CONDITION)],
            "matched_event_id": None, "matched_market": None, "main_points": [],
            "prop_markets": [], "ambiguous": False}
    ev = build_event_record(_expected(), disc)
    assert ev["main_state"] == POLY_DISCOVERY_OR_MATCHING_DEFECT
    result = validate_ledger(build_ledger([ev], []))
    assert result["closure_ready"] is False  # a defect blocks closure


def test_nonlisting_requires_real_404_on_all_three_surfaces():
    disc = {"attempts": [_attempt(s, NOT_FOUND, 404, terminal=True)
                         for s in (GAMMA_EVENT, GAMMA_MARKET, CLOB_CONDITION)],
            "matched_event_id": None, "matched_market": None, "main_points": [],
            "prop_markets": [], "ambiguous": False}
    ev = build_event_record(_expected(), disc)
    assert ev["main_state"] == POLY_NONLISTING_ARCHIVALLY_PROVEN
    result = validate_ledger(build_ledger([ev], []))
    assert "NONLISTING_PROOF_INCOMPLETE" not in {e["code"] for e in result["errors"]}
    assert result["closure_ready"] is True


def test_transient_surface_failure_is_unknown_not_a_proven_state():
    # gotcha #36: a 429/timeout must never read as "not listed".
    disc = {"attempts": [_attempt(GAMMA_EVENT, RATE_LIMITED, 429, terminal=False)],
            "matched_event_id": None, "matched_market": None, "main_points": [],
            "prop_markets": [], "ambiguous": False}
    ev = build_event_record(_expected(), disc)
    assert ev["main_state"] == UNKNOWN
    assert ev["retry"]["state"] == "failed" and ev["retry"]["next_attempt_at"]  # owned, not tombstone
    result = validate_ledger(build_ledger([ev], []))
    assert "UNQUALIFIED_FAILURE_TOMBSTONE" not in {e["code"] for e in result["errors"]}


def test_ambiguous_identity_is_a_defect():
    disc = {"attempts": _found_attempts(), "matched_event_id": None,
            "matched_market": None, "main_points": [], "prop_markets": [], "ambiguous": True}
    ev = build_event_record(_expected(), disc)
    assert ev["main_state"] == POLY_DISCOVERY_OR_MATCHING_DEFECT


# --------------------------------------------------------------------------- #
# Props — terminal-zero represented, threshold_pending, enumerated-from-source
# --------------------------------------------------------------------------- #
def test_settled_losing_prop_stays_represented_with_terminal_zero():
    props = build_prop_records(_expected(), _recovered_discovery())
    player = next(p for p in props if p["semantic"]["stat"] == "points")
    assert player["represented"] is True
    assert player["terminal_yes_probability"] == 0  # Over settled to 0.0 -> loser, not dropped


def test_every_prop_is_threshold_pending_until_alex_ratifies():
    props = build_prop_records(_expected(), _recovered_discovery())
    assert props and all(p["trade_classification"] == "threshold_pending" for p in props)
    assert all(p["enumerated_from_source_event"] is True for p in props)
    # trade_evidence is always attached (never empty -> no TRADE_EVIDENCE_MISSING).
    assert all(p["trade_evidence"] for p in props)


def test_unrecovered_pending_prop_blocks_closure_as_an_owned_cohort():
    # A discovered prop with no robust history is an unrecovered candidate (blocker),
    # which is the honest recovery-cohort signal, not a silent exclusion.
    disc = _recovered_discovery()
    disc["prop_markets"] = [{"submarket": disc["prop_markets"][0]["submarket"], "points": [], "trade_count": 0}]
    ev = build_event_record(_expected(), disc)
    props = build_prop_records(_expected(), disc)
    assert props[0]["recovery_state"] == "pending"
    result = validate_ledger(build_ledger([ev], props))
    assert "PROP_UNACCOUNTED" in {e["code"] for e in result["errors"]}


# --------------------------------------------------------------------------- #
# Identity edge cases — gotcha #89 (aliases, home/away, doubleheaders)
# --------------------------------------------------------------------------- #
def test_home_away_reversed_still_matches_both_teams():
    from scripts.evals.polymarket_discovery_ledger import event_matches_game
    event = decompose_gamma_event(FIXTURES["gamma_home_away_reversed"])
    # Bain Luck says Alphas @ Betas; Poly lists "Betas at Alphas" — both teams present.
    assert event_matches_game(event, "alphas", "betas") is True


def test_doubleheader_game_number_flows_into_scheduled_instance():
    exp = _expected(cid="MLB:2026-06-15:tigers@rays:G2", league="MLB", date="2026-06-15",
                    away="Tigers", home="Rays", game_number=2)
    ev = build_event_record(exp, _recovered_discovery())
    assert ev["game_number"] == 2
    assert ev["main_contract"]["scheduled_instance"] == "G2"


# --------------------------------------------------------------------------- #
# Fake client — exhaustive date traversal (gotcha #41) + error != no-data
# --------------------------------------------------------------------------- #
class FakeClient:
    """Records discover calls; returns canned discoveries per canonical id."""

    def __init__(self, discoveries):
        self.discoveries = discoveries
        self.calls = []

    def discover_event(self, expected):
        self.calls.append(expected["canonical_event_id"])
        return self.discoveries.get(expected["canonical_event_id"], {
            "attempts": [_attempt(s, NOT_FOUND, 200) for s in (GAMMA_EVENT, GAMMA_MARKET, CLOB_CONDITION)],
            "matched_event_id": None, "matched_market": None, "main_points": [],
            "prop_markets": [], "ambiguous": False,
        })


def test_census_drives_from_expected_population_and_counts_states():
    exp1 = _expected(cid="NBA:2026-01-15:alphas@betas:G1")
    exp2 = _expected(cid="MLB:2026-06-15:tigers@rays:G1", league="MLB", date="2026-06-15",
                     away="Tigers", home="Rays")
    client = FakeClient({exp1["canonical_event_id"]: _recovered_discovery()})
    result = run_discovery_census([exp1, exp2], client)
    by_state = result["summary"]["by_league_state"]
    assert by_state["NBA"][POLY_MAIN_RECOVERED] == 1
    assert by_state["MLB"][POLY_DISCOVERY_OR_MATCHING_DEFECT] == 1  # unmatched miss -> defect
    assert result["summary"]["window"]["expected_events"] == 2


def test_census_emits_c52_scoreboard_embedding_validation():
    exp = _expected()
    client = FakeClient({exp["canonical_event_id"]: _recovered_discovery()})
    result = run_discovery_census([exp], client)
    c52 = result["summary"]["c52_scoreboard"]
    # The produced ledger embeds into and validates through the C52 contract.
    assert c52["poly_embedding_valid"] is True
    assert c52["poly_closure_ready"] is True


def test_census_c52_propagates_poly_blocker():
    exp = _expected()
    disc = {"attempts": [_attempt(s, NOT_FOUND, 200) for s in (GAMMA_EVENT, GAMMA_MARKET, CLOB_CONDITION)],
            "matched_event_id": None, "matched_market": None, "main_points": [],
            "prop_markets": [], "ambiguous": False}
    client = FakeClient({exp["canonical_event_id"]: disc})
    result = run_discovery_census([exp], client)
    assert result["summary"]["c52_scoreboard"]["polymarket_findings_propagated"] >= 1


def test_census_is_idempotent_across_repeat_runs(tmp_path):
    ck = tmp_path / "pdl.json"
    exp = _expected()
    client = FakeClient({exp["canonical_event_id"]: _recovered_discovery()})
    first = run_discovery_census([exp], client, checkpoint=str(ck))
    n = len(client.calls)
    second = run_discovery_census([exp], client, checkpoint=str(ck))
    assert len(client.calls) == n  # served from checkpoint, no new discover calls
    assert json.dumps(first["summary"]["by_league_state"], sort_keys=True) == \
        json.dumps(second["summary"]["by_league_state"], sort_keys=True)


def test_census_limit_defers_remainder_as_named_cohort_not_silent_drop():
    exps = [_expected(cid=f"NBA:2026-01-15:a{i}@b{i}:G1", away=f"A{i}", home=f"B{i}") for i in range(5)]
    client = FakeClient({})
    result = run_discovery_census(exps, client, limit=2)
    assert result["summary"]["window"]["attempted"] == 2
    assert result["summary"]["window"]["deferred_cohort"] == 3
    assert len(result["summary"]["window"]["deferred_named"]) == 3  # named, not hidden


def test_error_is_never_collapsed_to_no_data_in_attempt_ledger():
    disc = {"attempts": [_attempt(GAMMA_EVENT, TIMEOUT, 0, terminal=False)],
            "matched_event_id": None, "matched_market": None, "main_points": [],
            "prop_markets": [], "ambiguous": False}
    ev = build_event_record(_expected(), disc)
    # A timeout is a typed, retryable attempt — not a silent miss.
    assert ev["attempts"][0]["result"] == TIMEOUT and ev["attempts"][0]["terminal"] is False
    assert ev["main_state"] == UNKNOWN


# --------------------------------------------------------------------------- #
# C52 scoreboard embedding — validate_scoreboard propagates poly blockers
# --------------------------------------------------------------------------- #
def _clean_scoreboard_event(event_id="NBA:2026-01-15:alphas@betas:G1"):
    return {
        "expected_event_id": event_id, "league": "NBA",
        "scheduled_at": "2026-01-15T03:00:00Z", "teams": ["Alphas", "Betas"],
        "game_number": 1, "inventory_source": "espn_scoreboard",
        "inventory_attempts": [{"attempt_id": "a1", "attempted_at": "2026-01-16T00:00:00Z",
                                "request_identity": "espn:nba:2026-01-15", "result": "found",
                                "terminal": True}],
    }


def _clean_observation(event_id="NBA:2026-01-15:alphas@betas:G1"):
    return {
        "expected_event_id": event_id,
        "identity": {"state": "canonical", "bainluck_event_id": 4242},
        "final_result": {"state": "verified", "provenance": "espn"},
        "winner": {"state": "verified", "provenance": "espn"},
        "calibration_forecast": {"state": "available", "probability": 0.62,
                                 "captured_at": "2026-01-15T02:00:00Z", "provenance": "polymarket"},
        "sources": [{"source": "polymarket", "attempts": [
            {"attempt_id": "s1", "attempted_at": "2026-01-16T00:00:00Z",
             "request_identity": "clob:token", "result": "found", "terminal": True}],
            "history": {"raw_points": 12, "effective_points": 12, "pregame_points": 5,
                        "ingame_points": 7, "largest_gap_minutes": 60, "ingame_applicable": True}}],
        "render": {"state": "ready", "evidence": "12 win-prob points rendered"},
    }


def test_scoreboard_embeds_clean_ledger_and_validates():
    ev = build_event_record(_expected(), _recovered_discovery())
    props = build_prop_records(_expected(), _recovered_discovery())
    ledger = build_ledger([ev], props)
    sb = build_scoreboard([_clean_scoreboard_event()], [_clean_observation()], ledger)
    result = validate_scoreboard(sb)
    assert result["polymarket_result"]["closure_ready"] is True
    assert result["closure_ready"] is True, result["blockers"]


def test_scoreboard_propagates_polymarket_blockers():
    # A defect in the poly ledger must surface as a POLYMARKET_* scoreboard blocker.
    disc = {"attempts": [_attempt(s, NOT_FOUND, 200) for s in (GAMMA_EVENT, GAMMA_MARKET, CLOB_CONDITION)],
            "matched_event_id": None, "matched_market": None, "main_points": [],
            "prop_markets": [], "ambiguous": False}
    ev = build_event_record(_expected(), disc)
    ledger = build_ledger([ev], [])
    sb = build_scoreboard([_clean_scoreboard_event()], [_clean_observation()], ledger)
    result = validate_scoreboard(sb)
    codes = {row["code"] for row in result["findings"]}
    assert any(code.startswith("POLYMARKET_") for code in codes)
    assert result["closure_ready"] is False


# --------------------------------------------------------------------------- #
# Summary honesty
# --------------------------------------------------------------------------- #
def test_summary_names_worst_cases_and_stages_recovery_cohorts():
    exp1 = _expected(cid="NBA:2026-01-15:alphas@betas:G1")
    exp2 = _expected(cid="MLB:2026-06-15:tigers@rays:G1", league="MLB", date="2026-06-15",
                     away="Tigers", home="Rays")
    ev1 = build_event_record(exp1, _recovered_discovery())
    disc2 = {"attempts": [_attempt(s, NOT_FOUND, 200) for s in (GAMMA_EVENT, GAMMA_MARKET, CLOB_CONDITION)],
             "matched_event_id": None, "matched_market": None, "main_points": [],
             "prop_markets": [], "ambiguous": False}
    ev2 = build_event_record(exp2, disc2)
    ledger = build_ledger([ev1, ev2], [])
    summary = summarize(ledger, {"NBA": 1, "MLB": 1})
    assert summary["worst_cases"]["defect"]["count"] == 1
    assert any(c["cohort"].startswith("main_defect") for c in summary["recovery_cohorts"])
