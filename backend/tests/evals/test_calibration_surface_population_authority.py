import json

from scripts.evals.calibration_surface_population_authority import DEFAULT_FIXTURES, decide, evaluate_pack


def test_every_surface_state_matches_population_authority() -> None:
    result = evaluate_pack(json.loads(DEFAULT_FIXTURES.read_text()))
    assert result["passed"] == result["cases"] == 12


def test_complete_coverage_requires_exact_unit_label_and_version() -> None:
    pack = json.loads(DEFAULT_FIXTURES.read_text())
    rows = {row["id"]: decide(row) for row in pack["cases"]}
    assert rows["web-current-complete"]["verdict"] == "allow"
    assert rows["current-web-implementation-hides-coverage"]["verdict"] == "refuse"
    assert rows["version-mismatched-census-hidden"]["coverage_authoritative"] is False


def test_every_numeric_surface_discloses_stale_evidence() -> None:
    pack = json.loads(DEFAULT_FIXTURES.read_text())
    rows = {row["id"]: decide(row) for row in pack["cases"]}
    assert rows["stale-web-dated"]["verdict"] == "allow"
    assert rows["stale-native-dated"]["verdict"] == "allow"
    assert "STALE_NUMBERS_PRESENTED_CURRENT" in rows["about-stale-proof-undisclosed"]["errors"]


def test_empty_curve_and_available_census_are_independent_states() -> None:
    pack = json.loads(DEFAULT_FIXTURES.read_text())
    rows = {row["id"]: decide(row) for row in pack["cases"]}
    assert rows["empty-curve-keeps-complete-census"]["verdict"] == "allow"
    assert "EMPTY_CURVE_ERASES_CENSUS" in rows["empty-curve-current-native-erases-census"]["errors"]
