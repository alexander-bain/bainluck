"""Offline contract and validator for versioned evaluation probes.

C48 Search and C49 semantic-matching adapters should call ``load_registry`` and
``filter_probes``. They must select an explicit task type and split, retain the
registry's oracle metadata outside presentation payloads, and use
``real_world_group_key`` as the indivisible split unit.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Iterable

SCHEMA_VERSION = "probe-registry/v1"
SPLITS = {"train", "tune", "test", "canary"}
ORACLE_KINDS = {"objective", "known_answer", "adjudicated", "judgment"}
KNOWN_FAILURE_STATES = {"pass", "xfail", "fixed"}
LIFECYCLE_STATES = {"active", "retired"}
TASK_LABEL_SCHEMAS = {
    "cross_source_contract": {"contract_equivalence/v1"},
    "event_link": {"event_link/v1"},
    "market_shape": {"market_shape/v1"},
    "resolution_lifecycle": {"resolution_state/v1"},
    "discover_tapworthiness": {"tapworthiness_judgment/v1"},
    "kid_curiosity": {"kid_curiosity_judgment/v1"},
    "kid_safety": {"guardian_safety/v1"},
    "enrichment_entity_match": {"entity_match/v1"},
    "search_entity": {"search_entity/v1"},
    "semantic_matching": {"contract_equivalence/v1"},
}
REGISTRY_METADATA = {
    "schema_version": SCHEMA_VERSION,
    "split_unit": "isolation.real_world_group_key",
    "c48_search": {
        "task_type": "search_entity",
        "required_expected_field": "oracle.answer.expected_entity_id",
    },
    "c49_semantic_matching": {
        "task_type": "semantic_matching",
        "label_schema": "contract_equivalence/v1",
    },
}

_HASH_RE = re.compile(r"^[0-9a-f]{64}$")
_PII_KEY_RE = re.compile(r"(^|_)(child_)?(name|email|phone|address|birth|dob|user_id)($|_)")


def _error(code: str, path: str, message: str) -> dict[str, str]:
    return {"code": code, "path": path, "message": message}


def _get(record: dict[str, Any], dotted: str, default: Any = None) -> Any:
    value: Any = record
    for part in dotted.split("."):
        if not isinstance(value, dict) or part not in value:
            return default
        value = value[part]
    return value


def _strings(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for child in value.values():
            yield from _strings(child)
    elif isinstance(value, list):
        for child in value:
            yield from _strings(child)


def _answers(oracle: dict[str, Any]) -> list[str]:
    values = oracle.get("allowed_alternatives") or []
    answer = oracle.get("answer")
    if answer not in (None, ""):
        values = [answer, *values]
    return [str(value).strip().casefold() for value in _strings(values) if str(value).strip()]


def _has_child_pii(value: Any) -> bool:
    if isinstance(value, dict):
        for key, child in value.items():
            if _PII_KEY_RE.search(str(key).casefold()) and child not in (None, "", "redacted"):
                return True
            if _has_child_pii(child):
                return True
    elif isinstance(value, list):
        return any(_has_child_pii(child) for child in value)
    return False


def _stable_identity(record: dict[str, Any]) -> bool:
    identity = record.get("identity", {})
    return any(
        identity.get(key)
        for key in ("subject_id", "question_id", "entity_ids")
    )


def validate_registry(
    records: list[dict[str, Any]],
    *,
    previous_records: list[dict[str, Any]] | None = None,
    allow_retired: bool = False,
) -> list[dict[str, str]]:
    """Return deterministic structured validation errors for ``records``."""

    errors: list[dict[str, str]] = []
    seen: dict[tuple[str, int], dict[str, Any]] = {}
    latest_version: dict[str, int] = {}
    previous = {
        (_get(row, "identity.probe_key"), _get(row, "identity.probe_version")): row
        for row in previous_records or []
    }

    for index, record in enumerate(records):
        base = f"records[{index}]"
        identity = record.get("identity", {})
        evidence = record.get("evidence", {})
        oracle = record.get("oracle", {})
        lifecycle = record.get("lifecycle", {})
        audience = record.get("audience_safety", {})
        isolation = record.get("isolation", {})
        key = identity.get("probe_key")
        version = identity.get("probe_version")

        if not isinstance(key, str) or not key.strip():
            errors.append(_error("IDENTITY_MISSING", f"{base}.identity.probe_key", "probe_key is required"))
        if not isinstance(version, int) or isinstance(version, bool) or version <= 0:
            errors.append(_error("VERSION_INVALID", f"{base}.identity.probe_version", "probe_version must be a positive integer"))
        if identity.get("schema_version") != SCHEMA_VERSION:
            errors.append(_error("SCHEMA_VERSION_INVALID", f"{base}.identity.schema_version", f"expected {SCHEMA_VERSION}"))
        if not all(identity.get(field) for field in ("surface", "task_type", "item_type")):
            errors.append(_error("IDENTITY_MISSING", f"{base}.identity", "surface, task_type, and item_type are required"))
        if not _stable_identity(record):
            errors.append(_error("STABLE_ID_MISSING", f"{base}.identity", "a stable subject, question, or entity ID is required"))

        if isinstance(key, str) and isinstance(version, int):
            pair = (key, version)
            if pair in seen:
                errors.append(_error("DUPLICATE_VERSION", base, f"duplicate probe identity {key}@{version}"))
            seen[pair] = record
            prior_version = latest_version.get(key)
            if prior_version is not None and version < prior_version:
                errors.append(_error("VERSION_REGRESSION", f"{base}.identity.probe_version", f"{version} follows {prior_version}"))
            latest_version[key] = max(version, prior_version or version)

        fixture_hash = evidence.get("fixture_hash")
        if not isinstance(fixture_hash, str) or not _HASH_RE.fullmatch(fixture_hash):
            errors.append(_error("EVIDENCE_HASH_INVALID", f"{base}.evidence.fixture_hash", "fixture_hash must be lowercase sha256 hex"))
        if not all(evidence.get(field) not in (None, "") for field in ("source", "provenance", "license_usage_note")):
            errors.append(_error("EVIDENCE_MISSING", f"{base}.evidence", "source, provenance, and license_usage_note are required"))
        if evidence.get("pii_redacted") is not True:
            errors.append(_error("PII_REDACTION_MISSING", f"{base}.evidence.pii_redacted", "pii_redacted must be true"))

        task_type = identity.get("task_type")
        label_schema = oracle.get("label_schema")
        if task_type not in TASK_LABEL_SCHEMAS:
            errors.append(_error("TASK_TYPE_UNKNOWN", f"{base}.identity.task_type", f"unknown task type {task_type!r}"))
        elif label_schema not in TASK_LABEL_SCHEMAS[task_type]:
            errors.append(_error("LABEL_SCHEMA_UNKNOWN", f"{base}.oracle.label_schema", f"unsupported schema for {task_type}"))
        if not oracle.get("label_schema_version"):
            errors.append(_error("LABEL_SCHEMA_VERSION_MISSING", f"{base}.oracle.label_schema_version", "label schema version is required"))
        kind = oracle.get("oracle_kind")
        if kind not in ORACLE_KINDS:
            errors.append(_error("ORACLE_KIND_INVALID", f"{base}.oracle.oracle_kind", "invalid oracle kind"))
        if not oracle.get("authority"):
            errors.append(_error("ORACLE_AUTHORITY_MISSING", f"{base}.oracle.authority", "oracle authority is required"))
        if kind in {"objective", "known_answer"} and (oracle.get("answer") in (None, "") or not oracle.get("evidence")):
            errors.append(_error("OBJECTIVE_ORACLE_INCOMPLETE", f"{base}.oracle", "objective/known-answer oracle requires answer and evidence"))
        if kind == "judgment" and oracle.get("known_truth") is True:
            errors.append(_error("JUDGMENT_AS_TRUTH", f"{base}.oracle.known_truth", "judgment cannot be marked as known truth"))
        votes = oracle.get("votes")
        if isinstance(votes, dict) and len(votes) == 2 and len(set(votes.values())) == 2 and oracle.get("answer") not in (None, ""):
            errors.append(_error("TIE_RECORDED_AS_TRUTH", f"{base}.oracle.answer", "a 1-1 tie must remain unresolved"))
        if task_type == "search_entity" and kind in {"objective", "known_answer"}:
            answer = oracle.get("answer")
            if not isinstance(answer, dict) or not answer.get("expected_entity_id"):
                errors.append(_error("SEARCH_EXPECTED_ENTITY_MISSING", f"{base}.oracle.answer", "objective Search gold requires expected_entity_id"))

        presentation = record.get("presentation", {})
        normalized_presentation = "\n".join(_strings(presentation)).casefold()
        if kind in {"objective", "known_answer", "adjudicated"} and any(
            len(answer) >= 3 and answer in normalized_presentation for answer in _answers(oracle)
        ):
            errors.append(_error("KNOWN_ANSWER_EXPOSED", f"{base}.presentation", "presentation contains an oracle answer"))

        state = lifecycle.get("state")
        if state not in LIFECYCLE_STATES:
            errors.append(_error("LIFECYCLE_INVALID", f"{base}.lifecycle.state", "invalid lifecycle state"))
        elif state == "retired" and not allow_retired:
            errors.append(_error("RETIRED_NOT_ALLOWED", f"{base}.lifecycle.state", "retired probe requires explicit override"))
        if not lifecycle.get("owner") or lifecycle.get("known_failure_status") not in KNOWN_FAILURE_STATES:
            errors.append(_error("LIFECYCLE_INCOMPLETE", f"{base}.lifecycle", "owner and valid known-failure status are required"))

        split = isolation.get("split")
        if split not in SPLITS:
            errors.append(_error("SPLIT_INVALID", f"{base}.isolation.split", "invalid immutable split"))
        if not isolation.get("real_world_group_key"):
            errors.append(_error("GROUP_KEY_MISSING", f"{base}.isolation.real_world_group_key", "real-world group key is required"))
        lineage = isolation.get("contamination_lineage")
        if not isinstance(lineage, list) or not all(isinstance(item, str) and item for item in lineage):
            errors.append(_error("LINEAGE_INVALID", f"{base}.isolation.contamination_lineage", "contamination lineage must be a string list"))

        if audience.get("kid_facing") is True:
            if _has_child_pii(record) or audience.get("privacy_sensitivity") == "child_pii":
                errors.append(_error("CHILD_PII_PRESENT", base, "kid-facing probes may not contain child PII"))
            if task_type == "kid_safety" and not audience.get("guardian_safety_authority"):
                errors.append(_error("GUARDIAN_AUTHORITY_MISSING", f"{base}.audience_safety", "kid safety requires adult/guardian authority"))
            if task_type == "kid_safety" and oracle.get("authority_role") == "kid_taste_reviewer":
                errors.append(_error("KID_TASTE_AS_SAFETY", f"{base}.oracle.authority_role", "kid taste cannot supply the safety oracle"))

        old = previous.get((key, version))
        if old is not None:
            if _get(old, "evidence.fixture_hash") != fixture_hash:
                errors.append(_error("FIXTURE_MUTATED_WITHOUT_VERSION", f"{base}.evidence.fixture_hash", "fixture hash changed without version bump"))
            if old.get("oracle") != oracle:
                history = oracle.get("adjudication_history")
                if not isinstance(history, list) or not history:
                    errors.append(_error("ORACLE_MUTATED_WITHOUT_VERSION", f"{base}.oracle", "oracle changed without version bump/adjudication record"))

    memberships: dict[tuple[str, str], set[str]] = {}
    for record in records:
        split = _get(record, "isolation.split")
        group = _get(record, "isolation.real_world_group_key")
        if split in SPLITS and group:
            memberships.setdefault(("group", group), set()).add(split)
        for lineage in _get(record, "isolation.contamination_lineage", []) or []:
            memberships.setdefault(("lineage", lineage), set()).add(split)
    for (kind, value), member_splits in sorted(memberships.items()):
        if len(member_splits) > 1:
            code = "GROUP_SPLIT_LEAKAGE" if kind == "group" else "LINEAGE_SPLIT_LEAKAGE"
            errors.append(_error(code, f"isolation.{kind}:{value}", f"cross-split leakage: {','.join(sorted(member_splits))}"))

    return sorted(errors, key=lambda item: (item["path"], item["code"], item["message"]))


def load_registry(path: str | Path, *, allow_retired: bool = False) -> list[dict[str, Any]]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    records = payload.get("probes") if isinstance(payload, dict) else payload
    if not isinstance(records, list):
        raise ValueError("registry must be a list or contain a probes list")
    errors = validate_registry(records, allow_retired=allow_retired)
    if errors:
        raise ValueError(json.dumps(errors, sort_keys=True))
    return records


def filter_probes(
    records: Iterable[dict[str, Any]],
    *,
    task_type: str,
    split: str,
    known_failure_status: str | None = None,
) -> list[dict[str, Any]]:
    if task_type not in TASK_LABEL_SCHEMAS or split not in SPLITS:
        raise ValueError("task_type and split must be registered")
    selected = [
        row
        for row in records
        if _get(row, "identity.task_type") == task_type
        and _get(row, "isolation.split") == split
        and _get(row, "lifecycle.state") == "active"
        and (known_failure_status is None or _get(row, "lifecycle.known_failure_status") == known_failure_status)
    ]
    return sorted(selected, key=lambda row: (_get(row, "identity.probe_key"), _get(row, "identity.probe_version")))


def fixture_sha256(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()
