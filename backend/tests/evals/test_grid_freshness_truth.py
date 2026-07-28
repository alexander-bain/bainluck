from copy import deepcopy
from pathlib import Path

from scripts.evals.grid_freshness_truth import evaluate_case, evaluate_pack, load_pack

FIXTURES = (
    Path(__file__).parents[2] / "scripts/evals/grid_freshness_truth_fixtures.json"
)


def pack():
    return load_pack(FIXTURES)


def by_id(result, case_id):
    return next(row for row in result["results"] if row["id"] == case_id)


def test_required_adversarial_cases_are_present():
    ids = {case["id"] for case in pack()["cases"]}
    assert {
        "db-timeout",
        "cancelled",
        "db-error",
        "partial-evidence",
        "nba-ncaab-wnba-pollution",
        "nba-cup-prefix",
        "mlb-college-pollution",
        "old-season-touched",
        "grid-http-failure",
        "prior-red-unknown",
    } <= ids


def test_clean_and_stale_truth_states_are_deterministic():
    result = evaluate_pack(pack())
    assert by_id(result, "verified-fresh")["evidence_state"] == "verified"
    assert by_id(result, "stale-active")["verdict"] == "red"
    assert by_id(result, "stale-quiet")["verdict"] == "green"


def test_unknown_never_closes_prior_red():
    row = by_id(evaluate_pack(pack()), "prior-red-unknown")
    assert row["evidence_state"] == "unknown"
    assert row["filing"] == "hold"
    assert "UNKNOWN_DID_NOT_HOLD_PRIOR_RED" not in row["findings"]


def test_cross_league_and_old_season_rows_fail_population_contract():
    result = evaluate_pack(pack())
    for case_id in (
        "nba-ncaab-wnba-pollution",
        "nba-cup-prefix",
        "mlb-college-pollution",
        "old-season-touched",
    ):
        assert "POPULATION_MISMATCH" in by_id(result, case_id)["findings"]


def test_partial_evidence_is_unknown_not_aggregate_green():
    row = by_id(evaluate_pack(pack()), "partial-evidence")
    assert row["evidence_state"] == "unknown"
    assert row["verdict"] == "unknown"


def test_cockpit_must_preserve_evidence_fields():
    case = deepcopy(pack()["cases"][0])
    del case["cockpit"]["population_count"]
    row = evaluate_case(case, pack()["policy"])
    assert "COCKPIT_EVIDENCE_DROPPED:population_count" in row["findings"]


def test_policy_is_injected_not_hidden():
    data = pack()
    case = deepcopy(data["cases"][0])
    case["query"]["scanned_rows"] = 2
    row = evaluate_case(case, {"max_scanned_rows": 1, "max_query_ms": 1000})
    assert "QUERY_SCAN_OVER_POLICY" in row["findings"]


def test_missing_plan_is_named_not_fabricated():
    row = by_id(evaluate_pack(pack()), "db-timeout")
    assert "PLAN_UNMEASURED" in row["findings"]


def test_expected_outcomes_match_all_fixtures():
    result = evaluate_pack(pack())
    assert all(
        "EXPECTED_OUTCOME_MISMATCH" not in row["findings"] for row in result["results"]
    )
