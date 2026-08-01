from copy import deepcopy
from pathlib import Path

from scripts.evals.grid_register_contract import evaluate_case, evaluate_pack, load_pack


FIXTURES = Path(__file__).parent / "fixtures/grid_register_contract.json"


def pack():
    return load_pack(FIXTURES)


def by_id(result, case_id):
    return next(row for row in result["results"] if row["id"] == case_id)


def test_all_five_leagues_and_required_adversaries_are_present():
    data = pack()
    assert set(data["league_contracts"]) == {"nba", "nhl", "mlb", "nfl", "golf"}
    ids = {case["id"] for case in data["cases"]}
    assert {
        "nba-exact-live", "nhl-alias-preserves-identity", "mlb-unambiguous-rename",
        "nfl-authoritative-settlement", "golf-exact-competitor",
        "missing-is-honest-empty", "reject-silent-fifty-fallback",
        "reject-stale-live-settled", "source-split-is-ambiguous",
        "wrong-team-identity-drift", "next-season-does-not-replace-current",
        "reject-cross-season-entry", "reject-duplicate-cell-source",
        "reject-identity-reused-across-cells", "reject-malformed-register",
        "poison-candidate-blocks-publication-not-sibling-read",
        "reject-nonmonotonic-version-transition",
    } <= ids


def test_expected_outcomes_match_entire_corpus():
    result = evaluate_pack(pack())
    assert all("EXPECTED_OUTCOME_MISMATCH" not in row["findings"] for row in result["results"])


def test_clean_exact_alias_missing_and_golf_cases_pass():
    result = evaluate_pack(pack())
    for case_id in (
        "nba-exact-live", "nhl-alias-preserves-identity",
        "golf-exact-competitor", "missing-is-honest-empty",
    ):
        row = by_id(result, case_id)
        assert row["classification"] == "clean"
        assert row["findings"] == []


def test_only_validated_version_plus_one_can_publish():
    result = evaluate_pack(pack())
    good = by_id(result, "mlb-unambiguous-rename")
    bad = by_id(result, "reject-nonmonotonic-version-transition")
    assert good["publish"] is True
    assert good["action"] == "publish_new_version"
    assert bad["publish"] is False
    assert "NON_MONOTONIC_VERSION" in bad["findings"]


def test_ambiguous_drift_never_auto_repairs():
    result = evaluate_pack(pack())
    for case_id in (
        "source-split-is-ambiguous", "wrong-team-identity-drift",
        "next-season-does-not-replace-current",
        "poison-candidate-blocks-publication-not-sibling-read",
    ):
        row = by_id(result, case_id)
        assert row["classification"] == "needs_ruling"
        assert row["action"] == "file_p2_needs_triage"
        assert row["publish"] is False


def test_invalid_registers_fail_before_drift_or_render_evaluation():
    result = evaluate_pack(pack())
    expected = {
        "reject-cross-season-entry": "CROSS_SEASON_OR_LEAGUE_ENTRY",
        "reject-duplicate-cell-source": "DUPLICATE_CELL_SOURCE",
        "reject-identity-reused-across-cells": "IDENTITY_REUSED_ACROSS_CELLS",
        "reject-malformed-register": "REGISTER_MISSING_FIELDS",
    }
    for case_id, finding in expected.items():
        row = by_id(result, case_id)
        assert row["classification"] == "invalid"
        assert finding in row["findings"]
        assert row["publish"] is False


def test_missing_and_settled_never_render_as_live_probability():
    result = evaluate_pack(pack())
    silent = by_id(result, "reject-silent-fifty-fallback")
    stale = by_id(result, "reject-stale-live-settled")
    assert "MISSING_RENDERED_AS_PROBABILITY" in silent["findings"]
    assert "SETTLED_RENDERED_AS_LIVE" in stale["findings"]
    assert silent["action"] == stale["action"] == "block_release"


def test_mutations_fail_loudly_for_wrong_stage_and_out_of_range_probability():
    data = pack()
    contract = {
        "register_schema_version": data["register_schema_version"],
        "allowed_sources": data["allowed_sources"],
        "league_contracts": data["league_contracts"],
    }
    case = deepcopy(data["cases"][0])
    case["register"]["entries"][0]["stage"] = "invented_round"
    row = evaluate_case(case, contract)
    assert row["classification"] == "invalid"
    assert "UNKNOWN_STAGE" in row["findings"]

    case = deepcopy(data["cases"][0])
    case["rendered"][0]["probability"] = 1.5
    row = evaluate_case(case, contract)
    assert row["classification"] == "render_contract_failure"
    assert "LIVE_PROBABILITY_OUT_OF_RANGE" in row["findings"]


def test_contract_forbids_probability_policy_and_partial_publication():
    contract = pack()["application_repair_contract"]
    assert contract["identity_only"] is True
    assert "probability_or_blend_change" in contract["forbidden"]
    assert "partial_mixed_version_publish" in contract["forbidden"]
    assert "atomically replace" in contract["publication"]
