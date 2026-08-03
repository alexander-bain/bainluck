from __future__ import annotations

import copy

from scripts.evals.calibration_coverage_unit_authority import (
    RULING,
    UNITS,
    evaluate_case,
    evaluate_corpus,
    load_corpus,
)


def _case(case_id: str) -> dict:
    return copy.deepcopy(next(row for row in load_corpus()["cases"] if row["id"] == case_id))


def test_committed_corpus_matches_every_oracle() -> None:
    report = evaluate_corpus(load_corpus())
    assert report["total"] == 18
    assert report["passed"] == report["total"], report["cases"]


def test_three_units_have_exact_predicates_and_consumers() -> None:
    corpus = load_corpus()
    matrix = {row["key"]: row for row in corpus["lineage_matrix"]}
    assert set(matrix) == set(UNITS)
    for key, authority in UNITS.items():
        assert matrix[key]["unit"] == authority["unit"]
        assert matrix[key]["predicate"] == authority["predicate"]
    assert corpus["measured_counts"] == {
        "outcomes_with_terminal_calibration_price": 1284551,
        "outcomes_with_usable_curve_price": 1466736,
        "published_curve_observations": 652407,
    }


def test_alex_ruling_selects_terminal_supporting_census() -> None:
    assert load_corpus()["ruling"] == RULING
    assert evaluate_case(_case("ruled-terminal-census-web")) == []
    assert evaluate_case(_case("ruled-terminal-census-native-parity")) == []
    assert evaluate_case(_case("unselected-option-usable")) == ["OPTION_NOT_SELECTED_BY_ALEX"]


def test_missing_is_unavailable_and_never_zero() -> None:
    assert evaluate_case(_case("old-payload-unavailable-not-zero")) == []
    assert evaluate_case(_case("missing-masquerades-as-zero")) == [
        "MISSING_MUST_RENDER_UNAVAILABLE"
    ]


def test_poison_is_caught_at_every_position() -> None:
    for suffix in ("first", "middle", "last"):
        assert evaluate_case(_case(f"poison-{suffix}")) == ["UNKNOWN_MACHINE_UNIT"]
