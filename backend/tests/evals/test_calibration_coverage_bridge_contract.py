from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from app.utils.calibration_coverage_bridge import EXCLUSION_RUNGS, RUNG_KEYS
from scripts.evals.calibration_coverage_bridge_contract import (
    build_from_case,
    evaluate_case,
    evaluate_corpus,
    load_corpus,
)

FIXTURE = (
    Path(__file__).parent / "fixtures" / "calibration_coverage_bridge_contract.json"
)


def _case(case_id: str) -> dict:
    return copy.deepcopy(
        next(row for row in load_corpus(FIXTURE)["cases"] if row["id"] == case_id)
    )


def test_committed_corpus_is_complete_and_matches_oracles() -> None:
    corpus = load_corpus(FIXTURE)
    report = evaluate_corpus(corpus)
    assert report["total"] == 21
    assert report["passed"] == 21, [row for row in report["cases"] if not row["ok"]]
    ids = {row["id"] for row in corpus["cases"]}
    # Every class the ruling names has to be represented, or the corpus is
    # asserting reconciliation over a population it never exercised.
    assert {
        "truth-ineligible-is-its-own-rung",
        "virtual-representative-selection-rung",
        "field-normalization-completeness-rung",
        "sportsbook-treatment-is-a-separate-leg",
        "phantom-liquidity-rung",
        "malformed-and-unknown-truth-rung",
        "checked-zero-is-not-unknown",
    } <= ids


def test_reference_totals_reconcile_in_both_units() -> None:
    """The corpus header's own numbers must obey the contract it pins."""
    totals = load_corpus(FIXTURE)["reference_totals"]
    assert (
        totals["futures_outcomes_plotted"] + totals["sportsbook_curve_legs"]
        == totals["published_curve_observations"]
    )
    census = build_from_case(_case("production-shape-reconciles"))
    rungs = {cell["key"]: cell["outcomes"] for cell in census["coverage_bridge"]["rungs"]}
    assert sum(rungs.values()) == totals["outcomes_with_calibration_coverage"]
    assert (
        rungs["plotted_on_curve"] + sum(rungs[k] for k in EXCLUSION_RUNGS)
        == totals["outcomes_with_calibration_coverage"]
    )


def test_the_two_headline_numbers_never_share_a_unit() -> None:
    census = build_from_case(_case("production-shape-reconciles"))
    units = census["units"]
    assert units["published_curve_observations"]["unit"] == "curve_observation"
    assert units["outcomes_with_calibration_coverage"]["unit"] == "futures_outcome"
    # The coverage number is strictly larger, and saying so is the whole point:
    # a reader must not be able to mistake it for the plotted count.
    assert (
        units["outcomes_with_calibration_coverage"]["value"]
        > units["published_curve_observations"]["value"]
    )


def test_calling_coverage_the_plotted_count_is_refused() -> None:
    assert evaluate_case(_case("coverage-may-not-be-called-plotted")) == [
        "COVERAGE_LABELLED_AS_PLOTTED"
    ]
    assert evaluate_case(_case("headline-unit-must-stay-observations")) == [
        "HEADLINE_UNIT_NOT_OBSERVATIONS"
    ]


def test_an_unmeasured_rung_is_unknown_and_never_zero() -> None:
    row = _case("unknown-rung-never-becomes-zero")
    census = build_from_case(row)
    missing = next(
        c for c in census["coverage_bridge"]["rungs"] if c["key"] == "phantom_liquidity"
    )
    assert missing["outcomes"] is None
    assert missing["checked"] is False
    assert census["status"] == "incomplete"
    assert "RUNG_UNKNOWN" in census["invariants"]["violations"]
    # And the coverage headline refuses to be a number built on a hole.
    assert census["units"]["outcomes_with_calibration_coverage"]["value"] is None


def test_a_measured_empty_rung_is_a_checked_zero() -> None:
    census = build_from_case(_case("checked-zero-is-not-unknown"))
    zeroes = [c for c in census["coverage_bridge"]["rungs"] if c["outcomes"] == 0]
    assert zeroes, "the checked-zero case must contain at least one empty rung"
    assert all(c["checked"] is True for c in zeroes)
    assert census["status"] == "complete"


@pytest.mark.parametrize(
    "case_id,code",
    [
        ("plotted-hinge-must-agree", "PLOTTED_HINGE_DIVERGES"),
        ("plotted-hinge-unchecked-is-refused", "PLOTTED_HINGE_UNCHECKED"),
        ("sportsbook-legs-omitted-breaks-observations", "OBSERVATION_BRIDGE_BROKEN"),
        ("generation-may-not-be-mixed", "MIXED_GENERATION"),
        ("population-version-may-not-be-mixed", "MIXED_POPULATION_VERSION"),
    ],
)
def test_the_bridge_refuses_to_reconcile_by_construction(case_id: str, code: str) -> None:
    assert code in evaluate_case(_case(case_id))


def test_a_tier_with_no_census_says_so_rather_than_omitting_it() -> None:
    assert evaluate_case(_case("degraded-tier-honest-is-accepted")) == []
    census = build_from_case(_case("degraded-tier-honest-is-accepted"))
    assert census["status"] == "unavailable"
    assert all(c["outcomes"] is None for c in census["coverage_bridge"]["rungs"])
    assert census["invariants"]["violations"] == ["CENSUS_UNAVAILABLE"]


def test_publishing_the_census_may_not_touch_the_curve() -> None:
    assert evaluate_case(_case("census-may-not-change-the-curve")) == [
        "PLOTTED_POPULATION_CHANGED"
    ]
    assert evaluate_case(_case("census-may-not-bump-the-version")) == [
        "UNAUTHORIZED_VERSION_BUMP"
    ]


def test_corpus_schema_is_pinned() -> None:
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert raw["schema_version"] == "calibration-coverage-bridge-contract/v1"
    with pytest.raises(ValueError):
        load_corpus(
            _write_tmp({**raw, "schema_version": "calibration-coverage-bridge-contract/v2"})
        )


def test_every_rung_key_is_exercised_by_the_corpus() -> None:
    """A rung nobody counts is a rung nobody notices going wrong."""
    corpus = load_corpus(FIXTURE)
    seen: set[str] = set()
    for row in corpus["cases"]:
        seen |= set((row.get("measured") or {}).get("rungs") or {})
    assert seen == set(RUNG_KEYS)


def _write_tmp(payload: dict) -> Path:
    import tempfile

    path = Path(tempfile.mkdtemp()) / "corpus.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path
