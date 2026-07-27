"""Executable semantic-relationship probes derived from the C31 audit corpus."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

try:
    from .probe_registry import SCHEMA_VERSION, fixture_sha256, validate_registry
except ImportError:  # Direct script execution.
    from probe_registry import SCHEMA_VERSION, fixture_sha256, validate_registry


def _production_normalize_exact(left: dict[str, Any], right: dict[str, Any]) -> str:
    from app.utils.cross_source_matching import normalize_question

    return "same_contract" if normalize_question(left["question"]) == normalize_question(right["question"]) else "distinct_contract"


def _production_conservative_near(left: dict[str, Any], right: dict[str, Any]) -> str:
    from app.utils.cross_source_matching import _is_conservative_near_match

    return "same_contract" if _is_conservative_near_match(left["question"], right["question"]) else "distinct_contract"


ADAPTERS: dict[str, Callable[[dict[str, Any], dict[str, Any]], str]] = {
    "production_normalize_exact": _production_normalize_exact,
    "production_conservative_near": _production_conservative_near,
}


def _load_json(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("SEMANTIC_FILE_INVALID")
    return value


def load_semantic_probes(
    legacy_path: str | Path,
    manifest_path: str | Path,
) -> list[dict[str, Any]]:
    """Build and validate C47-compatible probes from legacy cases plus manifest."""

    legacy = _load_json(legacy_path).get("cases", [])
    manifest = _load_json(manifest_path).get("probes", [])
    legacy_by_id = {row["id"]: row for row in legacy}
    if len(legacy_by_id) != len(legacy):
        raise ValueError("SEMANTIC_LEGACY_DUPLICATE")

    seen_legacy: set[str] = set()
    records: list[dict[str, Any]] = []
    for entry in manifest:
        key = entry.get("probe_key")
        legacy_id = entry.get("legacy_case_id")
        source = legacy_by_id.get(legacy_id) if legacy_id else None
        if legacy_id and source is None:
            raise ValueError(f"SEMANTIC_LEGACY_UNKNOWN: {legacy_id}")
        if legacy_id:
            if legacy_id in seen_legacy:
                raise ValueError(f"SEMANTIC_LEGACY_DUPLICATE_MAPPING: {legacy_id}")
            seen_legacy.add(legacy_id)
        left = entry.get("left", source.get("left") if source else None)
        right = entry.get("right", source.get("right") if source else None)
        if not isinstance(left, dict) or not isinstance(right, dict):
            raise ValueError(f"SEMANTIC_INPUT_MISSING: {key}")
        execution = entry.get("execution", {})
        adapter = execution.get("adapter")
        executable = execution.get("status") == "executable"
        if executable and adapter not in ADAPTERS:
            raise ValueError(f"SEMANTIC_ADAPTER_UNKNOWN: {key}:{adapter}")
        if not executable and not all(execution.get(field) for field in ("reason_code", "production_seam", "lane1_handoff")):
            raise ValueError(f"SEMANTIC_NONEXECUTABLE_INCOMPLETE: {key}")
        lifecycle_status = entry["known_failure_status"]
        issue = entry.get("issue_handoff")
        if lifecycle_status == "xfail" and not issue:
            raise ValueError(f"SEMANTIC_XFAIL_ISSUE_MISSING: {key}")

        presentation = {"left": left, "right": right}
        records.append(
            {
                "identity": {
                    "probe_key": key,
                    "probe_version": entry.get("probe_version", 1),
                    "schema_version": SCHEMA_VERSION,
                    "surface": "semantic_eval",
                    "task_type": "semantic_matching",
                    "item_type": entry["semantic_task"],
                    "question_id": f"semantic:{key}",
                    "entity_ids": entry.get("entity_ids", []),
                },
                "evidence": {
                    "fixture_hash": fixture_sha256(presentation),
                    "hash_scope": "presentation/v1",
                    "source": "synthetic" if not legacy_id else "committed_c31_audit",
                    "provenance": entry.get("provenance", source.get("evidence") if source else "C49 synthetic counterclass"),
                    "license_usage_note": "synthetic/redacted repository fixture",
                    "pii_redacted": True,
                },
                "oracle": {
                    "oracle_kind": "objective",
                    "label_schema": "contract_equivalence/v1",
                    "label_schema_version": 1,
                    "answer": entry["expected_relationship"],
                    "allowed_alternatives": [],
                    "abstain_allowed": False,
                    "authority": entry.get("authority", "explicit contract/event/structure identity"),
                    "evidence": entry["oracle_evidence"],
                    "adjudication_history": [],
                },
                "lifecycle": {
                    "state": "active",
                    "owner": "semantic-evals",
                    "difficulty": entry.get("difficulty", "adversarial"),
                    "failure_family": entry["failure_class"],
                    "issue_gotcha": issue,
                    "known_failure_status": lifecycle_status,
                },
                "audience_safety": {
                    "reviewer_audience": "engineer",
                    "kid_facing": False,
                    "guardian_safety_authority": None,
                    "privacy_sensitivity": "none",
                },
                "isolation": {
                    "split": entry.get("split", "test"),
                    "real_world_group_key": entry.get("real_world_group_key", f"semantic-group:{key}"),
                    "contamination_lineage": entry.get("contamination_lineage", [f"semantic-lineage:{key}"]),
                    "prompt_version": None,
                    "model_version": None,
                    "scorer_version": "semantic-relationship/v1",
                },
                "presentation": presentation,
                "semantic_execution": execution,
                "legacy_case_id": legacy_id,
            }
        )

    missing = sorted(set(legacy_by_id) - seen_legacy)
    if missing:
        raise ValueError("SEMANTIC_LEGACY_UNACCOUNTED: " + ",".join(missing))
    errors = validate_registry(records)
    if errors:
        raise ValueError(json.dumps(errors, sort_keys=True))
    return records


def evaluate_semantic_probes(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Execute supported production adapters and report honest lifecycle state."""

    details: list[dict[str, Any]] = []
    for record in sorted(records, key=lambda row: row["identity"]["probe_key"]):
        key = record["identity"]["probe_key"]
        execution = record["semantic_execution"]
        expected = record["oracle"]["answer"]
        known = record["lifecycle"]["known_failure_status"]
        if execution["status"] == "non_executable":
            details.append(
                {
                    "probe_key": key,
                    "status": "non_executable",
                    "adapter": None,
                    "expected": expected,
                    "observed": None,
                    "disposition": "non_executable",
                    "reason_code": execution["reason_code"],
                    "production_seam": execution["production_seam"],
                    "lane1_handoff": execution["lane1_handoff"],
                }
            )
            continue
        adapter_name = execution["adapter"]
        if adapter_name not in ADAPTERS:
            raise ValueError(f"SEMANTIC_ADAPTER_UNKNOWN: {key}:{adapter_name}")
        observed = ADAPTERS[adapter_name](record["presentation"]["left"], record["presentation"]["right"])
        passed = observed == expected
        if known == "xfail":
            disposition = "xpass" if passed else "xfail"
        elif known == "fixed" and not passed:
            disposition = "regression"
        else:
            disposition = "pass" if passed else "fail"
        details.append(
            {
                "probe_key": key,
                "status": "executable",
                "adapter": adapter_name,
                "expected": expected,
                "observed": observed,
                "disposition": disposition,
                "reason_code": None,
            }
        )

    executable = [row for row in details if row["status"] == "executable"]
    counts = {
        name: sum(row["disposition"] == name for row in details)
        for name in ("pass", "fail", "xfail", "xpass", "regression", "non_executable")
    }
    by_adapter: dict[str, int] = {}
    for row in executable:
        by_adapter[row["adapter"]] = by_adapter.get(row["adapter"], 0) + 1
    return {
        "total": len(details),
        "executable": len(executable),
        "executable_rate": len(executable) / len(details) if details else 0.0,
        "lifecycle_counts": counts,
        "by_adapter": {key: by_adapter[key] for key in sorted(by_adapter)},
        "details": details,
    }
