"""Offline validator for exhaustive Tier-1 Polymarket recovery ledgers."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "polymarket-recovery/v1"
LEAGUES = {"NBA", "MLB", "NHL"}
MAIN_STATES = {
    "poly_main_recovered",
    "poly_listed_history_unavailable",
    "poly_discovery_or_matching_defect",
    "poly_nonlisting_archivally_proven",
    "unknown",
}
RETRYABLE_RESULTS = {"timeout", "rate_limited", "server_error"}
REQUIRED_SURFACES = {"gamma_event", "gamma_market", "clob_condition"}


def _err(code: str, path: str, message: str) -> dict[str, str]:
    return {"code": code, "path": path, "message": message}


def _timeline_errors(timeline: Any, path: str, policy: dict[str, Any]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    if not isinstance(timeline, dict):
        return [_err("TIMELINE_MISSING", path, "timeline measurements are required")]
    required = (
        "raw_points", "effective_points", "first_at", "last_at", "largest_gap_minutes",
        "pregame_span_minutes", "ingame_span_minutes", "terminal_behavior", "token_id",
        "dedup_key", "rendered_usable",
    )
    if any(timeline.get(field) is None for field in required):
        errors.append(_err("TIMELINE_MEASUREMENT_MISSING", path, "all timeline measurements are required"))
        return errors
    if timeline["effective_points"] > timeline["raw_points"]:
        errors.append(_err("DUPLICATE_INFLATED_POINTS", path, "effective points cannot exceed raw points"))
    if timeline["effective_points"] <= 2:
        errors.append(_err("OPENING_TERMINAL_ONLY", path, "opening and terminal alone are not robust"))
    if timeline.get("side_token_verified") is not True:
        errors.append(_err("TOKEN_SIDE_UNVERIFIED", path, "timeline token side must be verified"))
    robust = policy.get("robustness")
    if not isinstance(robust, dict) or not robust.get("version"):
        errors.append(_err("ROBUSTNESS_POLICY_MISSING", "policy.robustness", "explicit robustness policy is required"))
        return errors
    if timeline["effective_points"] < robust.get("min_effective_points", 0):
        errors.append(_err("TIMELINE_TOO_SPARSE", path, "effective point minimum not met"))
    if timeline["largest_gap_minutes"] > robust.get("max_gap_minutes", float("inf")):
        errors.append(_err("TIMELINE_GAP_TOO_LARGE", path, "largest gap exceeds supplied policy"))
    if timeline.get("upstream_ingame_points") and timeline["ingame_span_minutes"] <= 0:
        errors.append(_err("INGAME_COVERAGE_MISSING", path, "available upstream in-game history was not recovered"))
    if timeline["rendered_usable"] is not True:
        errors.append(_err("RENDERED_USABILITY_UNPROVED", path, "rendered usability must be recorded true"))
    return errors


def validate_ledger(payload: dict[str, Any]) -> dict[str, Any]:
    """Return deterministic errors, state counts, blockers, and closure verdict."""

    errors: list[dict[str, str]] = []
    if payload.get("schema_version") != SCHEMA_VERSION:
        errors.append(_err("SCHEMA_VERSION_INVALID", "schema_version", f"expected {SCHEMA_VERSION}"))
    policy = payload.get("policy") or {}
    if not policy.get("version"):
        errors.append(_err("POLICY_VERSION_MISSING", "policy.version", "policy version is required"))
    events = payload.get("events")
    props = payload.get("props")
    if not isinstance(events, list) or not isinstance(props, list):
        errors.append(_err("LEDGER_SHAPE_INVALID", "ledger", "events and props must be lists"))
        events, props = events or [], props or []

    event_keys: set[str] = set()
    state_counts = {state: 0 for state in sorted(MAIN_STATES)}
    for index, event in enumerate(events):
        path = f"events[{index}]"
        key = event.get("canonical_event_id")
        if not isinstance(event.get("record_version"), int) or event.get("record_version", 0) <= 0:
            errors.append(_err("RECORD_VERSION_INVALID", path, "positive record version is required"))
        if not key:
            errors.append(_err("EVENT_ID_MISSING", path, "canonical event ID is required"))
        elif key in event_keys:
            errors.append(_err("EVENT_DUPLICATE", path, f"duplicate canonical event {key}"))
        else:
            event_keys.add(key)
        if event.get("league") not in LEAGUES or not event.get("game_date") or not event.get("teams"):
            errors.append(_err("EVENT_IDENTITY_INCOMPLETE", path, "league, date, and teams are required"))
        if event.get("game_number") is None:
            errors.append(_err("GAME_NUMBER_MISSING", path, "game number is required, including 1 for ordinary games"))

        attempts = event.get("attempts") or []
        surfaces = {attempt.get("surface") for attempt in attempts}
        if not REQUIRED_SURFACES <= surfaces:
            errors.append(_err("ARCHIVAL_SURFACES_INCOMPLETE", f"{path}.attempts", "all archival surfaces must be attempted"))
        for a_index, attempt in enumerate(attempts):
            apath = f"{path}.attempts[{a_index}]"
            if not attempt.get("attempted_at") or not attempt.get("request_identity"):
                errors.append(_err("ATTEMPT_EVIDENCE_MISSING", apath, "attempt timestamp and request identity are required"))
            if attempt.get("result") in RETRYABLE_RESULTS and attempt.get("terminal") is True:
                errors.append(_err("TRANSIENT_MARKED_TERMINAL", apath, "transient failures remain retryable"))

        state = event.get("main_state")
        if state not in MAIN_STATES:
            errors.append(_err("MAIN_STATE_INVALID", f"{path}.main_state", "invalid main recovery state"))
        else:
            state_counts[state] += 1
        if state in {"unknown", "poly_discovery_or_matching_defect"}:
            errors.append(_err("EVENT_BLOCKS_CLOSURE", f"{path}.main_state", state))
        if state == "poly_nonlisting_archivally_proven":
            if surfaces != REQUIRED_SURFACES or any(a.get("result") != "not_found" or a.get("http_status") != 404 for a in attempts):
                errors.append(_err("NONLISTING_PROOF_INCOMPLETE", path, "all archival surfaces require named 404 evidence"))
        if state == "poly_main_recovered":
            match = event.get("main_contract") or {}
            if not all(match.get(field) not in (None, "") for field in ("polymarket_event_id", "condition_id", "period", "scheduled_instance")):
                errors.append(_err("MAIN_CONTRACT_INCOMPLETE", f"{path}.main_contract", "main contract identity is incomplete"))
            outcomes = match.get("outcomes") or []
            tokens = [row.get("token_id") for row in outcomes]
            if len(outcomes) < 2 or None in tokens or len(tokens) != len(set(tokens)):
                errors.append(_err("OUTCOME_TOKEN_MAPPING_INVALID", f"{path}.main_contract.outcomes", "each outcome side requires its own token"))
            job = event.get("history_job") or {}
            if not job.get("durable_id") or job.get("state") not in {"complete", "retryable", "running", "pending"}:
                errors.append(_err("DURABLE_HISTORY_JOB_MISSING", f"{path}.history_job", "durable history job is required"))
            if job.get("state") != "complete":
                errors.append(_err("HISTORY_JOB_INCOMPLETE", f"{path}.history_job", "recovered event requires complete history job"))
            errors.extend(_timeline_errors(event.get("timeline"), f"{path}.timeline", policy))
        retry = event.get("retry") or {}
        if retry.get("state") == "failed" and (not retry.get("reason") or not retry.get("input_fingerprint") or not retry.get("next_attempt_at")):
            errors.append(_err("UNQUALIFIED_FAILURE_TOMBSTONE", f"{path}.retry", "failed match requires reason, fingerprint, and next attempt"))

    prop_keys: set[tuple[str, str]] = set()
    for index, prop in enumerate(props):
        path = f"props[{index}]"
        if not isinstance(prop.get("record_version"), int) or prop.get("record_version", 0) <= 0:
            errors.append(_err("RECORD_VERSION_INVALID", path, "positive record version is required"))
        event_id = prop.get("canonical_event_id")
        condition_id = prop.get("condition_id")
        if event_id not in event_keys:
            errors.append(_err("PROP_EVENT_UNKNOWN", path, "prop must reference a ledger event"))
        key = (str(event_id), str(condition_id))
        if key in prop_keys:
            errors.append(_err("PROP_DUPLICATE", path, "duplicate event/condition prop"))
        prop_keys.add(key)
        if prop.get("enumerated_from_source_event") is not True:
            errors.append(_err("PROP_LOCAL_ONLY", path, "prop enumeration must come from source event"))
        semantic = prop.get("semantic") or {}
        if any(semantic.get(field) in (None, "") for field in ("subject", "stat", "direction", "period")):
            errors.append(_err("PROP_SEMANTICS_INCOMPLETE", f"{path}.semantic", "structured prop semantics are required"))
        outcomes = prop.get("outcomes") or []
        tokens = [row.get("token_id") for row in outcomes]
        if len(outcomes) < 2 or None in tokens or len(tokens) != len(set(tokens)):
            errors.append(_err("PROP_TOKEN_MAPPING_INVALID", f"{path}.outcomes", "each prop side requires its own token"))
        if prop.get("terminal_yes_probability") == 0 and prop.get("represented") is not True:
            errors.append(_err("TERMINAL_ZERO_PROP_DROPPED", path, "settled losing prop must remain represented"))
        trade_policy = policy.get("meaningful_trade")
        trade_state = prop.get("trade_classification")
        if not trade_policy or not trade_policy.get("version") or trade_policy.get("threshold") is None:
            if trade_state != "threshold_pending":
                errors.append(_err("TRADE_THRESHOLD_UNRATIFIED", path, "without supplied threshold prop must remain pending"))
        if trade_state in {"meaningful", "threshold_pending"}:
            if not prop.get("trade_evidence"):
                errors.append(_err("TRADE_EVIDENCE_MISSING", path, "trade evidence is required"))
            if prop.get("recovery_state") != "recovered":
                errors.append(_err("PROP_UNACCOUNTED", path, "meaningful or pending prop must be recovered"))
            errors.extend(_timeline_errors(prop.get("timeline"), f"{path}.timeline", policy))

    errors = sorted(errors, key=lambda row: (row["path"], row["code"], row["message"]))
    blockers = [row for row in errors if row["code"] not in {"RENDERED_USABILITY_UNPROVED"}]
    return {
        "valid": not errors,
        "closure_ready": not blockers and bool(events),
        "event_state_counts": state_counts,
        "event_count": len(events),
        "prop_count": len(props),
        "blockers": blockers,
        "errors": errors,
    }


def load_ledger(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("ledger must be an object")
    return value


def apply_case(base: dict[str, Any], case: dict[str, Any]) -> dict[str, Any]:
    """Apply a fixture mutation expressed as dotted dict/list path."""
    value = copy.deepcopy(base)
    target: Any = value
    parts = case["path"].split(".")
    for part in parts[:-1]:
        target = target[int(part)] if isinstance(target, list) else target[part]
    leaf = parts[-1]
    if case.get("delete"):
        if isinstance(target, list):
            del target[int(leaf)]
        else:
            target.pop(leaf, None)
    elif isinstance(target, list):
        target[int(leaf)] = case.get("value")
    else:
        target[leaf] = case.get("value")
    return value
