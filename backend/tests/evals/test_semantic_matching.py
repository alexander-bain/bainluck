from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from scripts.evals.probe_registry import validate_registry
from scripts.evals.semantic_relationship_eval import (
    evaluate_semantic_probes,
    load_semantic_probes,
)

EVAL_DIR = Path(__file__).parents[2] / "scripts" / "evals"
LEGACY_PATH = EVAL_DIR / "semantic_merge_fixtures.json"
MANIFEST_PATH = EVAL_DIR / "semantic_relationship_manifest.json"


@pytest.fixture(scope="module")
def probes() -> list[dict]:
    return load_semantic_probes(LEGACY_PATH, MANIFEST_PATH)


def _by_key(probes: list[dict]) -> dict[str, dict]:
    return {probe["identity"]["probe_key"]: probe for probe in probes}


def _details(report: dict) -> dict[str, dict]:
    return {row["probe_key"]: row for row in report["details"]}


def test_every_legacy_c31_case_is_accounted_for_exactly_once(probes: list[dict]) -> None:
    legacy = json.loads(LEGACY_PATH.read_text(encoding="utf-8"))["cases"]
    legacy_ids = [row["id"] for row in legacy]
    mapped = [probe["legacy_case_id"] for probe in probes if probe["legacy_case_id"]]
    assert len(legacy_ids) == 17
    assert sorted(mapped) == sorted(legacy_ids)
    assert len(mapped) == len(set(mapped))


def test_corpus_is_c47_valid_and_covers_required_relationships(probes: list[dict]) -> None:
    assert validate_registry(probes) == []
    assert len(probes) == 32
    tasks = {probe["identity"]["item_type"] for probe in probes}
    assert {
        "contract_identity",
        "canonical_market_identity",
        "event_identity",
        "event_market_identity",
        "group_relation",
        "shape_relation",
        "conditional_relation",
        "outcome_relation",
        "lifecycle_relation",
        "provenance_relation",
    } <= tasks
    failures = {probe["lifecycle"]["failure_family"] for probe in probes}
    assert {
        "numeric_identity",
        "direction_guard",
        "binary_complement_identity",
        "date_identity",
        "line_identity",
        "period_identity",
        "league_identity",
        "doubleheader_identity",
        "field_binary_conflation",
        "topn_field_conflation",
        "ladder_range_conflation",
        "bundle_field_conflation",
        "parent_condition",
        "model_market_conflation",
        "input_order_tie",
    } <= failures


def test_all_xfails_have_issue_or_handoff_and_nonexec_rows_are_owned(probes: list[dict]) -> None:
    for probe in probes:
        if probe["lifecycle"]["known_failure_status"] == "xfail":
            assert probe["lifecycle"]["issue_gotcha"]
        execution = probe["semantic_execution"]
        if execution["status"] == "non_executable":
            assert execution["reason_code"]
            assert execution["production_seam"].startswith("backend/") or execution["production_seam"] in {
                "prediction market grouping/matching metadata",
                "prediction market event linker",
                "calibration virtual-market classifier",
                "market shape/backfill classifier",
                "calibration source population classifier",
            }
            assert execution["lane1_handoff"]


def test_evaluator_reports_honest_executable_and_nonexec_census(probes: list[dict]) -> None:
    report = evaluate_semantic_probes(probes)
    assert report["total"] == 32
    assert report["executable"] == 10
    assert report["executable_rate"] == 10 / 32
    assert report["lifecycle_counts"] == {
        "pass": 6,
        "fail": 0,
        "xfail": 4,
        "xpass": 0,
        "regression": 0,
        "non_executable": 22,
    }
    assert report["by_adapter"] == {
        "production_conservative_near": 8,
        "production_normalize_exact": 2,
    }


@pytest.mark.parametrize(
    ("key", "expected", "observed"),
    [
        ("false-exact-hyphen-digit-collapse", "distinct_contract", "same_contract"),
        ("false-exact-decimal-collapse", "distinct_contract", "same_contract"),
        ("miss-short-paraphrase", "same_contract", "distinct_contract"),
        ("miss-country-alias", "same_contract", "distinct_contract"),
    ],
)
def test_known_production_defects_are_xfail_not_green(
    probes: list[dict], key: str, expected: str, observed: str
) -> None:
    detail = _details(evaluate_semantic_probes(probes))[key]
    assert detail == {
        "probe_key": key,
        "status": "executable",
        "adapter": detail["adapter"],
        "expected": expected,
        "observed": observed,
        "disposition": "xfail",
        "reason_code": None,
    }


@pytest.mark.parametrize(
    "key",
    [
        "numeric-same-decimal",
        "numeric-distinct-threshold",
        "numeric-distinct-year",
        "numeric-distinct-line",
        "direction-over-under",
        "direction-above-below",
    ],
)
def test_numeric_and_direction_guards_execute_expected_contract(probes: list[dict], key: str) -> None:
    detail = _details(evaluate_semantic_probes(probes))[key]
    assert detail["disposition"] == "pass"
    assert detail["observed"] == detail["expected"]


@pytest.mark.parametrize(
    ("key", "reason"),
    [
        ("false-equal-time-doubleheader", "ASYNC_DB_REGISTRY_BOUNDARY"),
        ("event-same-teams-different-period", "NO_PERIOD_IDENTITY_HELPER"),
        ("event-same-teams-different-league", "ASYNC_DB_REGISTRY_BOUNDARY"),
        ("contract-yes-no-complement", "NO_OUTCOME_RELATION_HELPER"),
        ("group-two-exactly-one-vs-independent", "NO_GROUP_RELATION_HELPER"),
        ("conditional-parent-mismatch", "NO_CONDITIONAL_CONTRACT_HELPER"),
        ("shape-ladder-vs-range", "NO_SHAPE_V2_HELPER"),
        ("shape-bundle-vs-field", "NO_SHAPE_V2_HELPER"),
        ("provenance-model-vs-market", "NO_PROVENANCE_HELPER"),
        ("unstable-equal-time-tie", "ASYNC_DB_ORDER_BOUNDARY"),
    ],
)
def test_missing_pure_boundaries_fail_closed_as_owned_nonexec(
    probes: list[dict], key: str, reason: str
) -> None:
    detail = _details(evaluate_semantic_probes(probes))[key]
    assert detail["status"] == "non_executable"
    assert detail["reason_code"] == reason
    assert detail["lane1_handoff"]


def test_output_is_deterministic_regardless_of_probe_order(probes: list[dict]) -> None:
    assert evaluate_semantic_probes(probes) == evaluate_semantic_probes(list(reversed(probes)))


def test_presentation_mutation_breaks_canonical_hash(probes: list[dict]) -> None:
    changed = copy.deepcopy(probes[0])
    changed["presentation"]["left"]["question"] = "mutated"
    codes = {error["code"] for error in validate_registry([changed])}
    assert "EVIDENCE_HASH_MISMATCH" in codes


def test_unknown_adapter_is_rejected_before_execution(tmp_path: Path) -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    manifest["probes"][0]["execution"]["adapter"] = "fabricated_adapter"
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="SEMANTIC_ADAPTER_UNKNOWN"):
        load_semantic_probes(LEGACY_PATH, path)


def test_unowned_nonexecutable_case_is_rejected(tmp_path: Path) -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    row = next(item for item in manifest["probes"] if item["execution"]["status"] == "non_executable")
    row["execution"].pop("lane1_handoff")
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="SEMANTIC_NONEXECUTABLE_INCOMPLETE"):
        load_semantic_probes(LEGACY_PATH, path)


def test_unmapped_legacy_case_is_rejected(tmp_path: Path) -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    manifest["probes"] = [
        row for row in manifest["probes"] if row.get("legacy_case_id") != "false_source_id_collision"
    ]
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="SEMANTIC_LEGACY_UNACCOUNTED"):
        load_semantic_probes(LEGACY_PATH, path)
