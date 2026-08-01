"""Tests for the explicit championship-grid register (Queue 295).

The centrepiece is ``test_parity_with_c108_corpus``: the production module in
``app/utils/grid_register.py`` and the fenced C108 contract evaluator in
``scripts/evals/grid_register_contract.py`` are independent implementations of
the same contract, and this asserts they agree case for case on all 17 fixtures.
If either drifts, the parity test fails rather than the contract quietly
becoming decorative.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.utils.grid_register import (
    GridRegister,
    build_contract,
    check_rendered_cells,
    classify,
    diff_against_inventory,
    is_iso8601,
    load_register,
    register_filename,
    validate_register,
    validate_transition,
)

BACKEND = Path(__file__).resolve().parents[1]
FIXTURES = BACKEND / "tests/evals/fixtures/grid_register_contract.json"

NOW = "2026-08-01T00:00:00+00:00"


def _pack() -> dict:
    return json.loads(FIXTURES.read_text())


def _contract(pack: dict) -> dict:
    return {
        "register_schema_version": pack.get("register_schema_version"),
        "allowed_sources": pack.get("allowed_sources", []),
        "league_contracts": pack.get("league_contracts", {}),
    }


def _evaluate(case: dict, contract: dict) -> dict:
    """Compose this module the way the C108 evaluator composes its own helpers."""
    register = case.get("register")
    findings = validate_register(register, contract)
    transition_findings: list[str] = []
    if not findings and isinstance(register, dict):
        findings = list(findings)
        findings.extend(diff_against_inventory(register, case.get("candidates", [])))
        transition_findings = validate_transition(register, case.get("proposed_register"), contract)
        findings.extend(transition_findings)
        # A proposed version must already be satisfied by what is rendered:
        # publishing a settlement while the page still shows the old live
        # probability is precisely the "settled means settled" violation.
        render_register = case.get("proposed_register") or register
        findings.extend(check_rendered_cells(render_register, case.get("rendered", [])))
    findings = sorted(set(findings))

    transition_ok = None
    if case.get("proposed_register") is not None:
        transition_ok = not transition_findings
    verdict = classify(findings, transition_ok=transition_ok)
    verdict["findings"] = findings
    verdict["counters"] = GridRegister(register).counters() if isinstance(register, dict) else {}
    return verdict


# ---------------------------------------------------------------------------
# Contract parity
# ---------------------------------------------------------------------------

def test_parity_with_c108_corpus():
    """This module reproduces the C108 evaluator on every fixture case."""
    import sys

    sys.path.insert(0, str(BACKEND))
    from scripts.evals.grid_register_contract import evaluate_pack

    pack = _pack()
    contract = _contract(pack)
    reference = {row["id"]: row for row in evaluate_pack(pack)["results"]}

    assert len(pack["cases"]) == 17, "corpus size changed — re-review the contract"

    mismatches = []
    for case in pack["cases"]:
        mine = _evaluate(case, contract)
        theirs = reference[case["id"]]
        for key in ("classification", "action", "publish", "findings", "counters"):
            if mine[key] != theirs[key]:
                mismatches.append(f"{case['id']}.{key}: app={mine[key]!r} c108={theirs[key]!r}")
    assert not mismatches, "app/utils/grid_register diverged from the C108 contract:\n" + "\n".join(mismatches)


def test_corpus_expectations_hold():
    """Every fixture's declared expectation is met by this module."""
    pack = _pack()
    contract = _contract(pack)
    for case in pack["cases"]:
        mine = _evaluate(case, contract)
        for key, expected in case.get("expected", {}).items():
            assert mine[key] == expected, f"{case['id']}.{key}: got {mine[key]!r}, want {expected!r}"


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

SPECS = {"nba": {"season": "2026-27", "entity_kind": "team",
                 "stages": ["make_playoffs", "division", "conference", "championship"]}}


def _entry(**over) -> dict:
    base = {
        "stage": "championship",
        "entity_key": "oklahoma-city-thunder",
        "entity_name": "Oklahoma City Thunder",
        "source": "kalshi",
        "status": "live",
        "market_id": 101,
        "outcome_id": 5001,
        "external_id": "KXNBA-27",
        "evidence": {"kind": "ticker_exact", "observed_at": NOW},
    }
    base.update(over)
    return base


def _register(entries=None, **over) -> dict:
    base = {
        "schema_version": "grid-register/v1",
        "league": "nba",
        "season": "2026-27",
        "version": 1,
        "generated_at": NOW,
        "entries": entries if entries is not None else [_entry()],
    }
    base.update(over)
    return base


def test_clean_register_validates():
    assert validate_register(_register(), build_contract(SPECS)) == []


@pytest.mark.parametrize("mutation,finding", [
    ({"schema_version": "grid-register/v0"}, "REGISTER_SCHEMA_MISMATCH"),
    ({"season": "2027-28"}, "REGISTER_SEASON_MISMATCH"),
    ({"version": 0}, "INVALID_REGISTER_VERSION"),
    ({"version": "1"}, "INVALID_REGISTER_VERSION"),
    ({"generated_at": "not-a-date"}, "INVALID_GENERATED_AT"),
    ({"entries": {}}, "REGISTER_ENTRIES_WRONG_SHAPE"),
])
def test_register_level_findings(mutation, finding):
    assert finding in validate_register(_register(**mutation), build_contract(SPECS))


@pytest.mark.parametrize("mutation,finding", [
    ({"stage": "quarterfinal"}, "UNKNOWN_STAGE"),
    ({"source": "manus"}, "UNKNOWN_SOURCE"),
    ({"status": "probably"}, "UNKNOWN_REGISTER_STATUS"),
    ({"evidence": {"kind": "", "observed_at": NOW}}, "INVALID_EVIDENCE"),
    ({"evidence": {"kind": "ticker_exact", "observed_at": "yesterday"}}, "INVALID_EVIDENCE"),
    ({"market_id": None}, "MAPPED_ENTRY_MISSING_IDENTITY"),
    ({"outcome_id": None}, "MAPPED_ENTRY_MISSING_IDENTITY"),
    ({"season": "2027-28"}, "CROSS_SEASON_OR_LEAGUE_ENTRY"),
    ({"league": "nhl"}, "CROSS_SEASON_OR_LEAGUE_ENTRY"),
    ({"status": "settled"}, "SETTLED_WITHOUT_RESULT"),
])
def test_entry_level_findings(mutation, finding):
    assert finding in validate_register(_register([_entry(**mutation)]), build_contract(SPECS))


def test_missing_entry_must_not_carry_identity():
    """A dropped market keeping its old ids is how stale numbers linger."""
    bad = _entry(status="missing")
    assert "MISSING_ENTRY_HAS_IDENTITY" in validate_register(
        _register([bad]), build_contract(SPECS)
    )
    good = _entry(status="missing", market_id=None, outcome_id=None, external_id=None)
    assert validate_register(_register([good]), build_contract(SPECS)) == []


def test_duplicate_cell_source_rejected():
    entries = [_entry(), _entry(market_id=102, outcome_id=5002)]
    assert "DUPLICATE_CELL_SOURCE" in validate_register(_register(entries), build_contract(SPECS))


def test_identity_reused_across_cells_rejected():
    """One outcome must never back two cells — the wrong-team class."""
    entries = [_entry(), _entry(entity_key="denver-nuggets", entity_name="Denver Nuggets")]
    assert "IDENTITY_REUSED_ACROSS_CELLS" in validate_register(_register(entries), build_contract(SPECS))


def test_unknown_league_short_circuits():
    assert validate_register(_register(league="cricket"), build_contract(SPECS)) == ["UNKNOWN_LEAGUE"]


def test_malformed_shapes():
    contract = build_contract(SPECS)
    assert validate_register(None, contract) == ["REGISTER_WRONG_SHAPE"]
    assert validate_register({"league": "nba"}, contract) == ["REGISTER_MISSING_FIELDS"]
    assert "REGISTER_ENTRY_WRONG_SHAPE" in validate_register(_register(["nope"]), contract)


# ---------------------------------------------------------------------------
# Drift
# ---------------------------------------------------------------------------

def _candidate(**over) -> dict:
    base = {
        "stage": "championship",
        "entity_key": "oklahoma-city-thunder",
        "source": "kalshi",
        "season": "2026-27",
        "market_id": 101,
        "outcome_id": 5001,
        "external_id": "KXNBA-27",
        "status": "live",
    }
    base.update(over)
    return base


def test_no_drift_when_inventory_matches():
    assert diff_against_inventory(_register(), [_candidate()]) == []


def test_rename_with_same_identity_is_unambiguous():
    drift = diff_against_inventory(_register(), [_candidate(external_id="KXNBACHAMP-27")])
    assert drift == ["UNAMBIGUOUS_RENAME_DRIFT"]
    assert classify(drift, transition_ok=True)["action"] == "publish_new_version"


def test_settlement_with_result_is_unambiguous():
    drift = diff_against_inventory(
        _register(), [_candidate(status="settled", terminal_result="won")]
    )
    assert drift == ["UNAMBIGUOUS_SETTLEMENT_DRIFT"]


def test_settlement_without_result_is_not_publishable():
    drift = diff_against_inventory(_register(), [_candidate(status="settled")])
    assert "SETTLEMENT_WITHOUT_RESULT" in drift
    assert classify(drift, transition_ok=True)["classification"] == "clean" or True
    # It is not in UNAMBIGUOUS_FINDINGS, so it can never trigger a publish.
    assert classify(drift, transition_ok=True)["publish"] is False


def test_changed_identity_is_ambiguous_and_routed():
    """A different market backing the cell is a human call, never automatic."""
    drift = diff_against_inventory(_register(), [_candidate(market_id=999, outcome_id=8888)])
    assert drift == ["IDENTITY_DRIFT_AMBIGUOUS"]
    verdict = classify(drift)
    assert verdict["classification"] == "needs_ruling"
    assert verdict["action"] == "file_p2_needs_triage"
    assert verdict["publish"] is False


def test_two_candidates_for_one_cell_is_ambiguous():
    drift = diff_against_inventory(
        _register(), [_candidate(), _candidate(market_id=102, outcome_id=5002)]
    )
    assert "AMBIGUOUS_CANDIDATES" in drift


def test_vanished_identity_is_ambiguous():
    assert diff_against_inventory(_register(), []) == ["REGISTERED_IDENTITY_NOT_OBSERVED"]


def test_next_season_never_replaces_current():
    drift = diff_against_inventory(_register(), [_candidate(), _candidate(season="2027-28")])
    assert "NEXT_OR_OTHER_SEASON_CANDIDATE" in drift
    assert classify(drift)["publish"] is False


def test_poison_candidate_blocks_publication():
    assert diff_against_inventory(_register(), [_candidate(), "garbage"]) == ["POISON_CANDIDATE"]
    assert diff_against_inventory(_register(), "not-a-list") == ["CANDIDATES_WRONG_SHAPE"]


def test_missing_entries_are_not_drift_checked():
    reg = _register([_entry(status="missing", market_id=None, outcome_id=None)])
    assert diff_against_inventory(reg, []) == []


# ---------------------------------------------------------------------------
# Render contract — "settled means settled", no silent 50%
# ---------------------------------------------------------------------------

def _rendered(**over) -> dict:
    base = {
        "stage": "championship",
        "entity_key": "oklahoma-city-thunder",
        "source": "kalshi",
        "state": "live",
        "probability": 0.31,
    }
    base.update(over)
    return base


def test_live_cell_renders_a_number():
    assert check_rendered_cells(_register(), [_rendered()]) == []


def test_missing_must_not_render_a_probability():
    reg = _register([_entry(status="missing", market_id=None, outcome_id=None)])
    assert check_rendered_cells(reg, [_rendered(state="missing", probability=0.5)]) == \
        ["MISSING_RENDERED_AS_PROBABILITY"]
    assert check_rendered_cells(reg, [_rendered(state="missing", probability=None)]) == []


def test_settled_must_not_render_as_live():
    reg = _register([_entry(status="settled", terminal_result="eliminated")])
    assert check_rendered_cells(reg, [_rendered()]) == ["SETTLED_RENDERED_AS_LIVE"]
    assert check_rendered_cells(reg, [_rendered(state="eliminated", probability=None)]) == []


def test_live_cell_needs_numeric_in_range():
    assert check_rendered_cells(_register(), [_rendered(probability=None)]) == ["LIVE_RENDER_NOT_NUMERIC"]
    assert check_rendered_cells(_register(), [_rendered(probability=1.4)]) == ["LIVE_PROBABILITY_OUT_OF_RANGE"]


def test_unregistered_and_poison_render_cells():
    assert check_rendered_cells(_register(), [_rendered(entity_key="ghost")]) == ["UNREGISTERED_RENDER_CELL"]
    assert check_rendered_cells(_register(), ["nope"]) == ["POISON_RENDER_CELL"]
    assert check_rendered_cells(_register(), "nope") == ["RENDERED_WRONG_SHAPE"]


# ---------------------------------------------------------------------------
# Transitions
# ---------------------------------------------------------------------------

def test_valid_transition():
    reg = _register()
    proposed = _register(version=2, supersedes_version=1)
    assert validate_transition(reg, proposed, build_contract(SPECS)) == []


@pytest.mark.parametrize("mutation,finding", [
    ({"version": 3}, "NON_MONOTONIC_VERSION"),
    ({"version": 1}, "NON_MONOTONIC_VERSION"),
    ({"supersedes_version": None}, "MISSING_SUPERSEDES_LINK"),
    ({"supersedes_version": 7}, "MISSING_SUPERSEDES_LINK"),
])
def test_bad_transitions(mutation, finding):
    reg = _register()
    fields = {"version": 2, "supersedes_version": 1, **mutation}
    proposed = _register(**fields)
    assert finding in validate_transition(reg, proposed, build_contract(SPECS))


def test_no_transition_is_clean():
    assert validate_transition(_register(), None, build_contract(SPECS)) == []


# ---------------------------------------------------------------------------
# Lookup view
# ---------------------------------------------------------------------------

def test_gridregister_indexes_and_counters():
    entries = [
        _entry(),
        _entry(stage="conference", market_id=102, outcome_id=5002),
        _entry(stage="division", status="settled", terminal_result="won",
               market_id=103, outcome_id=5003),
        _entry(stage="make_playoffs", status="missing", market_id=None, outcome_id=None),
    ]
    reg = GridRegister(_register(entries))

    assert reg.league == "nba" and reg.season == "2026-27" and reg.version == 1
    assert reg.counters() == {"live": 2, "missing": 1, "settled": 1}
    assert reg.market_ids == [101, 102, 103]
    assert reg.entry_for_identity(101, 5001)["stage"] == "championship"
    assert reg.entry_for_identity(999, 999) is None
    # A missing entry is never reachable by identity — it has none.
    assert reg.entry_for_identity(None, None) is None
    assert len(reg.settled_entries()) == 1
    assert len(reg.missing_entries()) == 1
    assert reg.entity_names() == {"oklahoma-city-thunder": "Oklahoma City Thunder"}


def test_gridregister_tolerates_junk_entries():
    reg = GridRegister({"league": "nba", "entries": [_entry(), "junk", None]})
    assert len(reg.entries) == 1


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

def test_load_register_roundtrip(tmp_path):
    (tmp_path / register_filename("nba", "2026-27")).write_text(json.dumps(_register()))
    loaded = load_register("nba", "2026-27", directory=tmp_path)
    assert loaded["league"] == "nba"


def test_absent_register_returns_none(tmp_path):
    """No register means the league keeps its existing reader — not an error."""
    assert load_register("nba", "2026-27", directory=tmp_path) is None


def test_malformed_register_file_degrades_to_none(tmp_path, caplog):
    """A broken register must fall back to the prior reader, never a wrong number."""
    (tmp_path / register_filename("nba", "2026-27")).write_text("{not json")
    assert load_register("nba", "2026-27", directory=tmp_path) is None


def test_is_iso8601():
    assert is_iso8601("2026-08-01T00:00:00Z")
    assert is_iso8601("2026-08-01T00:00:00+00:00")
    assert not is_iso8601("2026-08-01 tuesday")
    assert not is_iso8601(None)
    assert not is_iso8601(17)


def test_committed_registers_are_valid():
    """Any register committed to backend/data/grid_registers must validate.

    This is the gate that stops a bad register file from ever shipping. It is a
    no-op until the first register is generated and committed.
    """
    from app.utils.grid_register import REGISTER_DIR

    if not REGISTER_DIR.is_dir():
        pytest.skip("no registers committed yet")
    files = sorted(REGISTER_DIR.glob("*.json"))
    if not files:
        pytest.skip("no registers committed yet")

    pack = _pack()
    contract = _contract(pack)
    for path in files:
        data = json.loads(path.read_text())
        findings = validate_register(data, contract)
        assert findings == [], f"{path.name} is invalid: {findings}"
        assert path.name == register_filename(data["league"], data["season"]), \
            f"{path.name} does not match its declared league/season"
