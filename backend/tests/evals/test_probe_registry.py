from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from scripts.evals.probe_registry import (
    SCHEMA_VERSION,
    filter_probes,
    load_registry,
    validate_registry,
)

REGISTRY_PATH = Path(__file__).parents[2] / "scripts" / "evals" / "probe_registry.json"


def _probe(key: str = "probe-a", *, split: str = "test", group: str = "group-a") -> dict:
    return {
        "identity": {
            "probe_key": key,
            "probe_version": 1,
            "schema_version": SCHEMA_VERSION,
            "surface": "semantic_eval",
            "task_type": "cross_source_contract",
            "item_type": "market_pair",
            "question_id": f"question:{key}",
            "entity_ids": ["entity:one"],
        },
        "evidence": {
            "fixture_hash": "a" * 64,
            "source": "synthetic",
            "provenance": "test fixture",
            "captured_at": "2026-07-27T00:00:00Z",
            "valid_at": "2026-07-27T00:00:00Z",
            "license_usage_note": "synthetic",
            "pii_redacted": True,
        },
        "oracle": {
            "oracle_kind": "objective",
            "label_schema": "contract_equivalence/v1",
            "label_schema_version": 1,
            "answer": "same_contract",
            "allowed_alternatives": [],
            "abstain_allowed": False,
            "authority": "contract terms",
            "evidence": "identical terms",
            "adjudication_history": [],
        },
        "lifecycle": {
            "state": "active",
            "owner": "evals",
            "difficulty": "baseline",
            "failure_family": "matching",
            "issue_gotcha": None,
            "known_failure_status": "pass",
        },
        "audience_safety": {
            "reviewer_audience": "engineer",
            "kid_facing": False,
            "guardian_safety_authority": None,
            "privacy_sensitivity": "none",
        },
        "isolation": {
            "split": split,
            "real_world_group_key": group,
            "contamination_lineage": [f"lineage:{group}"],
            "prompt_version": None,
            "model_version": None,
            "scorer_version": "semantic/v1",
        },
        "presentation": {"prompt": "Are these contracts equivalent?"},
    }


def _codes(records: list[dict], **kwargs) -> set[str]:
    return {error["code"] for error in validate_registry(records, **kwargs)}


def test_committed_registry_is_clean_and_covers_required_classes() -> None:
    records = load_registry(REGISTRY_PATH)
    task_types = {row["identity"]["task_type"] for row in records}
    statuses = {row["lifecycle"]["known_failure_status"] for row in records}
    assert {
        "cross_source_contract",
        "event_link",
        "market_shape",
        "resolution_lifecycle",
        "discover_tapworthiness",
        "kid_curiosity",
        "kid_safety",
        "enrichment_entity_match",
    } <= task_types
    assert {"xfail", "fixed"} <= statuses


@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        (lambda row: row["identity"].update(probe_version=0), "VERSION_INVALID"),
        (
            lambda row: (row["identity"].pop("question_id"), row["identity"].update(entity_ids=[])),
            "STABLE_ID_MISSING",
        ),
        (lambda row: row["evidence"].update(fixture_hash="bad"), "EVIDENCE_HASH_INVALID"),
        (lambda row: row["evidence"].update(pii_redacted=False), "PII_REDACTION_MISSING"),
        (lambda row: row["oracle"].update(authority=""), "ORACLE_AUTHORITY_MISSING"),
        (lambda row: row["oracle"].update(answer=None), "OBJECTIVE_ORACLE_INCOMPLETE"),
        (lambda row: row["identity"].update(task_type="unknown"), "TASK_TYPE_UNKNOWN"),
        (lambda row: row["oracle"].update(label_schema="binary_like/v0"), "LABEL_SCHEMA_UNKNOWN"),
        (lambda row: row["lifecycle"].update(state="paused"), "LIFECYCLE_INVALID"),
        (lambda row: row["lifecycle"].update(known_failure_status="maybe"), "LIFECYCLE_INCOMPLETE"),
        (lambda row: row["isolation"].update(split="dev"), "SPLIT_INVALID"),
        (lambda row: row["isolation"].update(real_world_group_key=""), "GROUP_KEY_MISSING"),
        (lambda row: row["isolation"].update(contamination_lineage="lineage"), "LINEAGE_INVALID"),
    ],
)
def test_field_rejections(mutation, code: str) -> None:
    row = _probe()
    mutation(row)
    assert code in _codes([row])


def test_duplicate_and_version_regression_are_rejected() -> None:
    first = _probe()
    duplicate = copy.deepcopy(first)
    assert "DUPLICATE_VERSION" in _codes([first, duplicate])

    newer = _probe()
    newer["identity"]["probe_version"] = 2
    older = _probe()
    assert "VERSION_REGRESSION" in _codes([newer, older])


def test_same_question_under_different_ids_cannot_cross_train_test() -> None:
    train = _probe("row-one", split="train", group="real-question-7")
    test = _probe("row-two", split="test", group="real-question-7")
    test["isolation"]["contamination_lineage"] = ["different-row-id"]
    assert "GROUP_SPLIT_LEAKAGE" in _codes([train, test])


def test_same_story_lineage_cannot_cross_tune_canary() -> None:
    tune = _probe("story-one", split="tune", group="group-one")
    canary = _probe("story-two", split="canary", group="group-two")
    tune["isolation"]["contamination_lineage"] = ["story:shared"]
    canary["isolation"]["contamination_lineage"] = ["story:shared"]
    assert "LINEAGE_SPLIT_LEAKAGE" in _codes([tune, canary])


def test_judgment_cannot_masquerade_as_known_truth() -> None:
    row = _probe()
    row["identity"]["task_type"] = "discover_tapworthiness"
    row["oracle"].update(
        oracle_kind="judgment",
        label_schema="tapworthiness_judgment/v1",
        answer=None,
        known_truth=True,
    )
    assert "JUDGMENT_AS_TRUTH" in _codes([row])


def test_one_to_one_tie_remains_unresolved() -> None:
    row = _probe()
    row["identity"]["task_type"] = "discover_tapworthiness"
    row["oracle"].update(
        oracle_kind="judgment",
        label_schema="tapworthiness_judgment/v1",
        answer="tap",
        known_truth=False,
        votes={"reviewer-a": "tap", "reviewer-b": "skip"},
    )
    assert "TIE_RECORDED_AS_TRUTH" in _codes([row])


def test_objective_search_any_requires_expected_entity() -> None:
    row = _probe()
    row["identity"]["task_type"] = "search_entity"
    row["oracle"].update(
        label_schema="search_entity/v1",
        answer={"expected_surface": "any"},
        evidence="query fixture",
    )
    assert "SEARCH_EXPECTED_ENTITY_MISSING" in _codes([row])


def test_known_answer_cannot_appear_in_prompt_or_display() -> None:
    row = _probe()
    row["presentation"]["prompt"] = "The expected answer is same_contract"
    assert "KNOWN_ANSWER_EXPOSED" in _codes([row])


def _kid_safety_probe() -> dict:
    row = _probe()
    row["identity"].update(task_type="kid_safety", surface="play")
    row["oracle"].update(
        oracle_kind="adjudicated",
        label_schema="guardian_safety/v1",
        answer="approved",
        authority="adult guardian panel",
        authority_role="guardian_safety_reviewer",
        adjudication_history=[{"decision": "approved"}],
    )
    row["audience_safety"].update(
        kid_facing=True,
        reviewer_audience="adult_guardian",
        guardian_safety_authority="guardian-panel",
    )
    return row


def test_kid_taste_cannot_supply_safety_authority() -> None:
    row = _kid_safety_probe()
    row["oracle"]["authority_role"] = "kid_taste_reviewer"
    row["audience_safety"]["guardian_safety_authority"] = None
    codes = _codes([row])
    assert {"KID_TASTE_AS_SAFETY", "GUARDIAN_AUTHORITY_MISSING"} <= codes


def test_child_pii_is_rejected_even_in_nested_presentation() -> None:
    row = _kid_safety_probe()
    row["presentation"]["child_name"] = "Not Redacted"
    assert "CHILD_PII_PRESENT" in _codes([row])


def test_retired_probe_requires_explicit_override() -> None:
    row = _probe()
    row["lifecycle"]["state"] = "retired"
    assert "RETIRED_NOT_ALLOWED" in _codes([row])
    assert validate_registry([row], allow_retired=True) == []


def test_fixture_hash_and_oracle_cannot_change_in_place() -> None:
    old = _probe()
    changed = copy.deepcopy(old)
    changed["evidence"]["fixture_hash"] = "b" * 64
    changed["oracle"]["answer"] = "distinct_contract"
    codes = _codes([changed], previous_records=[old])
    assert "FIXTURE_MUTATED_WITHOUT_VERSION" in codes
    assert "ORACLE_MUTATED_WITHOUT_VERSION" in codes


def test_oracle_adjudication_change_is_recorded_but_fixture_still_versions() -> None:
    old = _probe()
    changed = copy.deepcopy(old)
    changed["oracle"]["answer"] = "distinct_contract"
    changed["oracle"]["adjudication_history"] = [{"decision": "corrected", "at": "2026-07-28"}]
    assert "ORACLE_MUTATED_WITHOUT_VERSION" not in _codes([changed], previous_records=[old])


def test_loader_filter_is_deterministic_and_excludes_retired(tmp_path: Path) -> None:
    active_b = _probe("b", split="test")
    active_a = _probe("a", split="test", group="group-b")
    active_a["isolation"]["contamination_lineage"] = ["lineage:group-b"]
    other = _probe("other", split="train", group="group-c")
    other["isolation"]["contamination_lineage"] = ["lineage:group-c"]
    path = tmp_path / "registry.json"
    path.write_text(json.dumps({"probes": [active_b, active_a, other]}), encoding="utf-8")
    records = load_registry(path)
    selected = filter_probes(records, task_type="cross_source_contract", split="test")
    assert [row["identity"]["probe_key"] for row in selected] == ["a", "b"]


def test_error_output_is_deterministic() -> None:
    row = _probe()
    row["evidence"]["fixture_hash"] = "invalid"
    assert validate_registry([row]) == validate_registry(copy.deepcopy([row]))
