"""Offline contract for source-agnostic named-event completeness scoreboards."""

from __future__ import annotations

import copy
from typing import Any

from scripts.evals.polymarket_recovery_ledger import validate_ledger

SCHEMA_VERSION = "named-event-completeness/v1"
LEAGUES = {"NBA", "MLB", "NHL"}
ERROR_RESULTS = {"timeout", "rate_limited", "server_error", "parse_error"}
ATTEMPT_RESULTS = ERROR_RESULTS | {"found", "upstream_absent", "identity_ambiguous"}
IDENTITY_STATES = {"canonical", "missing", "false_merge", "missed_merge", "ambiguous"}


def _finding(
    code: str, event_id: str, path: str, message: str, *, blocking: bool = True
) -> dict[str, Any]:
    return {
        "code": code,
        "event_id": event_id,
        "path": path,
        "message": message,
        "blocking": blocking,
    }


def _attempt_findings(attempts: Any, event_id: str, path: str) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    if not isinstance(attempts, list) or not attempts:
        return [
            _finding(
                "ATTEMPT_STATE_MISSING", event_id, path, "attempt history is required"
            )
        ]

    seen: set[str] = set()
    for index, attempt in enumerate(attempts):
        attempt_path = f"{path}[{index}]"
        attempt_id = attempt.get("attempt_id")
        result = attempt.get("result")
        if (
            not attempt_id
            or not attempt.get("attempted_at")
            or not attempt.get("request_identity")
        ):
            findings.append(
                _finding(
                    "ATTEMPT_EVIDENCE_MISSING",
                    event_id,
                    attempt_path,
                    "attempt id, time, and request identity are required",
                )
            )
        elif attempt_id in seen:
            findings.append(
                _finding(
                    "ATTEMPT_DUPLICATE",
                    event_id,
                    attempt_path,
                    f"duplicate attempt {attempt_id}",
                )
            )
        else:
            seen.add(attempt_id)
        if result == "no_data":
            findings.append(
                _finding(
                    "ERROR_COLLAPSED_TO_NO_DATA",
                    event_id,
                    attempt_path,
                    "no_data is not a typed source result",
                )
            )
        elif result not in ATTEMPT_RESULTS:
            findings.append(
                _finding(
                    "ATTEMPT_RESULT_INVALID",
                    event_id,
                    attempt_path,
                    f"unsupported result {result!r}",
                )
            )
        if result in ERROR_RESULTS and attempt.get("terminal") is True:
            findings.append(
                _finding(
                    "TRANSIENT_MARKED_TERMINAL",
                    event_id,
                    attempt_path,
                    "request and parse errors remain retryable",
                )
            )
        if result == "upstream_absent":
            if attempt.get("terminal") is not True or not attempt.get("evidence"):
                findings.append(
                    _finding(
                        "UPSTREAM_ABSENCE_UNPROVED",
                        event_id,
                        attempt_path,
                        "terminal absence requires evidence",
                    )
                )
            else:
                findings.append(
                    _finding(
                        "UPSTREAM_ABSENCE",
                        event_id,
                        attempt_path,
                        "source has evidenced no coverage",
                        blocking=False,
                    )
                )
    return findings


def _history_findings(
    history: Any,
    event_id: str,
    path: str,
    policy: dict[str, Any],
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    if not isinstance(history, dict):
        return [
            _finding(
                "ZERO_SNAPSHOTS", event_id, path, "history measurements are missing"
            )
        ]
    required = (
        "raw_points",
        "effective_points",
        "pregame_points",
        "ingame_points",
        "largest_gap_minutes",
    )
    if any(history.get(field) is None for field in required):
        return [
            _finding(
                "HISTORY_MEASUREMENT_MISSING",
                event_id,
                path,
                "all history measurements are required",
            )
        ]
    if history["effective_points"] > history["raw_points"]:
        findings.append(
            _finding(
                "NON_IDEMPOTENT_DUPLICATE_HISTORY",
                event_id,
                path,
                "effective points exceed raw points",
            )
        )
    if history["effective_points"] == 0:
        findings.append(
            _finding("ZERO_SNAPSHOTS", event_id, path, "no effective history exists")
        )
    history_policy = policy.get("history") or {}
    if not history_policy.get("version"):
        findings.append(
            _finding(
                "HISTORY_POLICY_MISSING",
                event_id,
                "policy.history",
                "versioned history policy is required",
            )
        )
        return findings
    if history["pregame_points"] < history_policy.get("min_pregame_points", 0):
        findings.append(
            _finding(
                "SPARSE_PREGAME_HISTORY",
                event_id,
                path,
                "pregame history misses supplied policy",
            )
        )
    if history.get("ingame_applicable") is True and history[
        "ingame_points"
    ] < history_policy.get("min_ingame_points", 0):
        findings.append(
            _finding(
                "SPARSE_INGAME_HISTORY",
                event_id,
                path,
                "in-game history misses supplied policy",
            )
        )
    if history["largest_gap_minutes"] > history_policy.get(
        "max_gap_minutes", float("inf")
    ):
        findings.append(
            _finding(
                "SPARSE_HISTORY_GAP",
                event_id,
                path,
                "largest gap exceeds supplied policy",
            )
        )
    return findings


def validate_scoreboard(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate the independent denominator and return named deterministic findings."""

    findings: list[dict[str, Any]] = []
    if payload.get("schema_version") != SCHEMA_VERSION:
        findings.append(
            _finding(
                "SCHEMA_VERSION_INVALID",
                "__scoreboard__",
                "schema_version",
                f"expected {SCHEMA_VERSION}",
            )
        )
    policy = payload.get("policy") or {}
    if not policy.get("version"):
        findings.append(
            _finding(
                "POLICY_VERSION_MISSING",
                "__scoreboard__",
                "policy.version",
                "policy version is required",
            )
        )

    inventory = payload.get("expected_events")
    observations = payload.get("observations")
    if not isinstance(inventory, list) or not inventory:
        findings.append(
            _finding(
                "ABSENT_EXPECTED_INVENTORY",
                "__scoreboard__",
                "expected_events",
                "independent expected-event inventory is required",
            )
        )
        inventory = inventory or []
    if not isinstance(observations, list):
        findings.append(
            _finding(
                "OBSERVATIONS_INVALID",
                "__scoreboard__",
                "observations",
                "observations must be a list",
            )
        )
        observations = observations or []

    expected: dict[str, dict[str, Any]] = {}
    for index, event in enumerate(inventory):
        event_id = event.get("expected_event_id") or f"__inventory_{index}__"
        path = f"expected_events[{index}]"
        if event_id in expected:
            findings.append(
                _finding(
                    "EXPECTED_EVENT_DUPLICATE",
                    event_id,
                    path,
                    "expected event appears twice",
                )
            )
        else:
            expected[event_id] = event
        if (
            event.get("league") not in LEAGUES
            or not event.get("scheduled_at")
            or len(event.get("teams") or []) != 2
        ):
            findings.append(
                _finding(
                    "EXPECTED_IDENTITY_INCOMPLETE",
                    event_id,
                    path,
                    "league, scheduled time, and two teams are required",
                )
            )
        if event.get("game_number") is None or not event.get("inventory_source"):
            findings.append(
                _finding(
                    "EXPECTED_PROVENANCE_INCOMPLETE",
                    event_id,
                    path,
                    "game number and independent inventory source are required",
                )
            )
        findings.extend(
            _attempt_findings(
                event.get("inventory_attempts"), event_id, f"{path}.inventory_attempts"
            )
        )

    observed: dict[str, dict[str, Any]] = {}
    for index, observation in enumerate(observations):
        event_id = observation.get("expected_event_id") or f"__observation_{index}__"
        path = f"observations[{index}]"
        if event_id not in expected:
            findings.append(
                _finding(
                    "OBSERVATION_OUTSIDE_DENOMINATOR",
                    event_id,
                    path,
                    "observation lacks an independent expected event",
                )
            )
        if event_id in observed:
            findings.append(
                _finding(
                    "OBSERVATION_DUPLICATE",
                    event_id,
                    path,
                    "event has multiple scoreboard rows",
                )
            )
        else:
            observed[event_id] = observation

        identity = observation.get("identity") or {}
        identity_state = identity.get("state")
        if identity_state not in IDENTITY_STATES:
            findings.append(
                _finding(
                    "IDENTITY_STATE_INVALID",
                    event_id,
                    f"{path}.identity",
                    "identity state is invalid",
                )
            )
        elif identity_state == "missing":
            findings.append(
                _finding(
                    "MISSING_BAINLUCK_EVENT",
                    event_id,
                    f"{path}.identity",
                    "no Bain Luck event row",
                )
            )
        elif identity_state == "false_merge":
            findings.append(
                _finding(
                    "FALSE_MERGE",
                    event_id,
                    f"{path}.identity",
                    "event is merged to the wrong real game",
                )
            )
        elif identity_state == "missed_merge":
            findings.append(
                _finding(
                    "MISSED_MERGE",
                    event_id,
                    f"{path}.identity",
                    "duplicate rows represent one real game",
                )
            )
        elif identity_state == "ambiguous":
            findings.append(
                _finding(
                    "IDENTITY_AMBIGUITY",
                    event_id,
                    f"{path}.identity",
                    "canonical event identity is unresolved",
                )
            )
        elif not identity.get("bainluck_event_id"):
            findings.append(
                _finding(
                    "MISSING_BAINLUCK_EVENT",
                    event_id,
                    f"{path}.identity",
                    "canonical identity requires a Bain Luck event id",
                )
            )

        for dimension, code in (
            ("final_result", "FINAL_RESULT_MISSING"),
            ("winner", "WINNER_MISSING"),
        ):
            value = observation.get(dimension) or {}
            if value.get("state") != "verified" or not value.get("provenance"):
                findings.append(
                    _finding(
                        code,
                        event_id,
                        f"{path}.{dimension}",
                        f"verified {dimension} with provenance is required",
                    )
                )

        forecast = observation.get("calibration_forecast") or {}
        if (
            forecast.get("state") != "available"
            or forecast.get("probability") is None
            or not forecast.get("captured_at")
            or not forecast.get("provenance")
        ):
            findings.append(
                _finding(
                    "CALIBRATION_FORECAST_MISSING",
                    event_id,
                    f"{path}.calibration_forecast",
                    "forecast probability, capture time, and provenance are required",
                )
            )

        sources = observation.get("sources") or []
        if not sources:
            findings.append(
                _finding(
                    "SOURCE_LINKAGE_MISSING",
                    event_id,
                    f"{path}.sources",
                    "at least one source record is required",
                )
            )
        source_names: set[str] = set()
        robust_source = False
        for source_index, source in enumerate(sources):
            source_path = f"{path}.sources[{source_index}]"
            source_name = source.get("source")
            if not source_name or source_name in source_names:
                findings.append(
                    _finding(
                        "SOURCE_IDENTITY_INVALID",
                        event_id,
                        source_path,
                        "source names must be present and unique",
                    )
                )
            source_names.add(source_name)
            attempts = source.get("attempts") or []
            attempt_findings = _attempt_findings(
                attempts, event_id, f"{source_path}.attempts"
            )
            source_absent = bool(attempts) and all(
                attempt.get("result") == "upstream_absent" for attempt in attempts
            )
            history_findings = (
                []
                if source_absent
                else _history_findings(
                    source.get("history"), event_id, f"{source_path}.history", policy
                )
            )
            findings.extend(attempt_findings)
            findings.extend(history_findings)
            if not any(
                row["blocking"] for row in attempt_findings + history_findings
            ) and any(attempt.get("result") == "found" for attempt in attempts):
                robust_source = True
        if not robust_source:
            findings.append(
                _finding(
                    "NO_ROBUST_SOURCE",
                    event_id,
                    f"{path}.sources",
                    "no source has typed success plus policy-complete history",
                )
            )

        render = observation.get("render") or {}
        if render.get("state") != "ready" or not render.get("evidence"):
            findings.append(
                _finding(
                    "RENDER_NOT_READY",
                    event_id,
                    f"{path}.render",
                    "render readiness needs named evidence",
                )
            )

    for event_id in expected.keys() - observed.keys():
        findings.append(
            _finding(
                "MISSING_BAINLUCK_EVENT",
                event_id,
                "observations",
                "expected event has no scoreboard observation",
            )
        )

    polymarket_result = None
    if "polymarket_ledger" in payload:
        polymarket_result = validate_ledger(payload["polymarket_ledger"])
        for blocker in polymarket_result["blockers"]:
            findings.append(
                _finding(
                    f"POLYMARKET_{blocker['code']}",
                    "__polymarket__",
                    f"polymarket_ledger.{blocker['path']}",
                    blocker["message"],
                )
            )

    findings = sorted(
        findings, key=lambda row: (row["event_id"], row["path"], row["code"])
    )
    blockers = [row for row in findings if row["blocking"]]
    named_blockers = sorted(
        {row["event_id"] for row in blockers if not row["event_id"].startswith("__")}
    )
    complete_events = sorted(set(expected) - set(named_blockers))
    return {
        "valid": not findings,
        "closure_ready": bool(expected) and not blockers,
        "expected_count": len(expected),
        "observed_count": len(observed),
        "complete_count": len(complete_events),
        "complete_events": complete_events,
        "named_blockers": named_blockers,
        "failure_counts": {
            code: sum(1 for row in findings if row["code"] == code)
            for code in sorted({row["code"] for row in findings})
        },
        "blockers": blockers,
        "findings": findings,
        "polymarket_result": polymarket_result,
    }


def merge_scoreboards(
    previous: dict[str, Any], current: dict[str, Any]
) -> dict[str, Any]:
    """Idempotently merge a rerun while preserving typed source attempt history."""

    merged = copy.deepcopy(previous)
    for collection, key in (
        ("expected_events", "expected_event_id"),
        ("observations", "expected_event_id"),
    ):
        rows = {row[key]: copy.deepcopy(row) for row in merged.get(collection, [])}
        for new_row in current.get(collection, []):
            row_id = new_row[key]
            if collection == "expected_events":
                old_attempts = rows.get(row_id, {}).get("inventory_attempts", [])
                candidate = copy.deepcopy(new_row)
                candidate["inventory_attempts"] = _merge_attempts(
                    old_attempts, candidate.get("inventory_attempts", [])
                )
            else:
                candidate = copy.deepcopy(new_row)
                old_sources = {
                    row["source"]: row
                    for row in rows.get(row_id, {}).get("sources", [])
                }
                for source in candidate.get("sources", []):
                    source["attempts"] = _merge_attempts(
                        old_sources.get(source["source"], {}).get("attempts", []),
                        source.get("attempts", []),
                    )
            rows[row_id] = candidate
        merged[collection] = [rows[row_id] for row_id in sorted(rows)]
    if "polymarket_ledger" in current:
        merged["polymarket_ledger"] = copy.deepcopy(current["polymarket_ledger"])
    return merged


def _merge_attempts(
    previous: list[dict[str, Any]], current: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    attempts = {row["attempt_id"]: copy.deepcopy(row) for row in previous}
    for row in current:
        attempts[row["attempt_id"]] = copy.deepcopy(row)
    return [attempts[key] for key in sorted(attempts)]
