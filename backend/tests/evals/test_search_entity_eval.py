from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from scripts.evals.probe_registry import filter_probes, load_registry, validate_registry
from scripts.evals.search_gold_eval import (
    SearchGoldMigrationError,
    evaluate_entity_probes,
    load_result_rows,
    parse_gold_markdown,
    require_entity_gold,
)

EVAL_DIR = Path(__file__).parents[2] / "scripts" / "evals"
REGISTRY_PATH = EVAL_DIR / "search_entity_probes.json"
LEGACY_PATH = Path(__file__).parent / "fixtures" / "gold_queries_sample.md"


def _probes() -> list[dict]:
    records = load_registry(REGISTRY_PATH)
    return filter_probes(records, task_type="search_entity", split="test")


def _candidate(probe: dict, *, entity_id: str | None = None, surface: str | None = None, item_type: str | None = None) -> dict:
    answer = probe["oracle"]["answer"]
    expected_surfaces = answer["expected_surfaces"]
    return {
        "entity_id": entity_id or answer["expected_entity_id"],
        "surface": surface or ("concept" if expected_surfaces == ["any"] else expected_surfaces[0]),
        "item_type": item_type or answer["expected_item_type"],
        "display_name": "Synthetic candidate",
    }


def _all_passing_results(probes: list[dict]) -> dict[str, list[dict]]:
    return {probe["identity"]["probe_key"]: [_candidate(probe)] for probe in probes}


def _detail(report: dict, key: str) -> dict:
    return next(row for row in report["details"] if row["probe_key"] == key)


def test_committed_search_registry_is_valid_versioned_and_complete() -> None:
    probes = _probes()
    query_classes = {probe["oracle"]["answer"]["query_class"] for probe in probes}
    assert len(probes) == 9
    assert {
        "canonical_team",
        "ambiguous_tournament",
        "ambiguous_alias",
        "concept_intent",
        "event_intent",
        "stale_alias",
        "full_question",
        "expected_surface_any",
        "market_intent",
    } == query_classes
    for probe in probes:
        lifecycle = probe["lifecycle"]
        if lifecycle["known_failure_status"] == "xfail":
            assert lifecycle["issue_gotcha"]


def test_wrong_entity_on_correct_surface_fails_before_surface() -> None:
    probes = _probes()
    target = next(row for row in probes if row["identity"]["probe_key"] == "search-red-sox-001")
    results = _all_passing_results(probes)
    results["search-red-sox-001"] = [
        _candidate(target, entity_id="synthetic:team:boston-braves", surface="team")
    ]
    report = evaluate_entity_probes(probes, results)
    assert _detail(report, "search-red-sox-001")["code"] == "ENTITY_NOT_TOP"


def test_expected_entity_below_wrong_top_records_rank_and_fails_top_one() -> None:
    probes = _probes()
    target = next(row for row in probes if row["identity"]["probe_key"] == "search-red-sox-001")
    results = _all_passing_results(probes)
    results["search-red-sox-001"] = [
        _candidate(target, entity_id="synthetic:team:boston-braves"),
        _candidate(target),
    ]
    detail = _detail(evaluate_entity_probes(probes, results), "search-red-sox-001")
    assert detail["code"] == "ENTITY_NOT_TOP"
    assert detail["expected_rank"] == 2
    assert detail["reciprocal_rank"] == 0.5


def test_declared_us_open_and_bos_ambiguities_pass_only_inside_set() -> None:
    probes = _probes()
    results = _all_passing_results(probes)
    by_key = {probe["identity"]["probe_key"]: probe for probe in probes}
    results["search-us-open-001"] = [
        _candidate(by_key["search-us-open-001"], entity_id="synthetic:concept:us-open-golf")
    ]
    results["search-bos-001"] = [
        _candidate(by_key["search-bos-001"], entity_id="synthetic:team:boston-bruins")
    ]
    report = evaluate_entity_probes(probes, results)
    assert _detail(report, "search-us-open-001")["code"] == "PASS"
    assert _detail(report, "search-bos-001")["code"] == "PASS"

    results["search-us-open-001"] = [
        _candidate(by_key["search-us-open-001"], entity_id="synthetic:concept:us-open-surfing")
    ]
    assert _detail(evaluate_entity_probes(probes, results), "search-us-open-001")["code"] == "ENTITY_NOT_TOP"


@pytest.mark.parametrize(
    ("overrides", "code"),
    [
        ({"surface": "event"}, "SURFACE_MISMATCH"),
        ({"item_type": "event"}, "TYPE_MISMATCH"),
    ],
)
def test_surface_and_type_failures_are_separately_diagnosable(overrides: dict, code: str) -> None:
    probes = _probes()
    target = next(row for row in probes if row["identity"]["probe_key"] == "search-world-cup-concept-001")
    results = _all_passing_results(probes)
    results[target["identity"]["probe_key"]] = [_candidate(target, **overrides)]
    assert _detail(evaluate_entity_probes(probes, results), target["identity"]["probe_key"])["code"] == code


def test_expected_surface_any_still_fails_with_no_result() -> None:
    probes = _probes()
    results = _all_passing_results(probes)
    results["search-zero-result-001"] = []
    detail = _detail(evaluate_entity_probes(probes, results), "search-zero-result-001")
    assert detail["code"] == "NO_RESULTS"
    assert detail["disposition"] == "xfail"


def test_lifecycle_summary_preserves_pass_xfail_xpass_and_fixed_regression() -> None:
    probes = _probes()
    results = _all_passing_results(probes)
    results["search-zero-result-001"] = []
    fixed = next(row for row in probes if row["identity"]["probe_key"] == "search-stale-alias-001")
    results["search-stale-alias-001"] = [_candidate(fixed, entity_id="synthetic:team:wrong")]
    report = evaluate_entity_probes(probes, results)
    assert report["lifecycle_counts"] == {
        "pass": 6,
        "fail": 0,
        "xfail": 1,
        "xpass": 1,
        "regression": 1,
    }


def test_results_and_details_are_deterministic_regardless_of_probe_order() -> None:
    probes = _probes()
    results = _all_passing_results(probes)
    assert evaluate_entity_probes(probes, results) == evaluate_entity_probes(list(reversed(probes)), results)


def test_legacy_surface_only_gold_requires_migration() -> None:
    rows = parse_gold_markdown(LEGACY_PATH)
    with pytest.raises(SearchGoldMigrationError, match="SEARCH_GOLD_MIGRATION_REQUIRED"):
        require_entity_gold(rows)


def test_result_loader_rejects_duplicate_probe_rows(tmp_path: Path) -> None:
    path = tmp_path / "results.json"
    path.write_text(
        json.dumps({"results": [{"probe_key": "a", "candidates": []}, {"probe_key": "a", "candidates": []}]}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="SEARCH_RESULTS_DUPLICATE"):
        load_result_rows(path)


def test_search_registry_rejects_duplicate_version_and_cross_split_leakage() -> None:
    probe = _probes()[0]
    duplicate = copy.deepcopy(probe)
    assert "DUPLICATE_VERSION" in {error["code"] for error in validate_registry([probe, duplicate])}

    leaked = copy.deepcopy(probe)
    leaked["identity"]["probe_key"] = "leaked-copy"
    leaked["identity"]["probe_version"] = 2
    leaked["isolation"]["split"] = "train"
    codes = {error["code"] for error in validate_registry([probe, leaked])}
    assert {"GROUP_SPLIT_LEAKAGE", "LINEAGE_SPLIT_LEAKAGE"} <= codes


def test_search_registry_rejects_known_answer_exposure() -> None:
    probe = copy.deepcopy(_probes()[0])
    probe["presentation"]["display"] = probe["oracle"]["answer"]["expected_entity_id"]
    assert "KNOWN_ANSWER_EXPOSED" in {error["code"] for error in validate_registry([probe])}


def test_search_registry_rejects_presentation_hash_mismatch() -> None:
    probe = copy.deepcopy(_probes()[0])
    probe["presentation"]["query"] = "mutated query"
    assert "EVIDENCE_HASH_MISMATCH" in {error["code"] for error in validate_registry([probe])}


def test_fixture_and_oracle_mutation_require_version_or_adjudication() -> None:
    old = next(row for row in _probes() if row["identity"]["probe_key"] == "search-red-sox-001")
    changed = copy.deepcopy(old)
    changed["evidence"]["fixture_hash"] = "f" * 64
    changed["oracle"]["answer"]["expected_entity_id"] = "synthetic:team:changed"
    codes = {
        error["code"]
        for error in validate_registry([changed], previous_records=[old])
    }
    assert {"FIXTURE_MUTATED_WITHOUT_VERSION", "ORACLE_MUTATED_WITHOUT_VERSION"} <= codes


def test_non_search_probe_is_rejected_by_adapter() -> None:
    probe = copy.deepcopy(_probes()[0])
    probe["identity"]["task_type"] = "event_link"
    with pytest.raises(ValueError, match="SEARCH_TASK_TYPE_INVALID"):
        evaluate_entity_probes([probe], {})
