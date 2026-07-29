"""Pure C76 validators for golf session/provenance and native identity/render rails."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
GOLF_FIXTURES = ROOT / "golf_session_provenance_fixtures.json"
NATIVE_FIXTURES = ROOT / "native_principal_render_fixtures.json"


def load_fixture(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def validate_golf(row: dict[str, Any], corpus: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    provenance = row.get("provenance")
    if provenance not in corpus["allowed_provenance"]:
        errors.append("invalid_provenance")
    expected = {
        "l0_fresh": "fresh", "redis_fresh": "fresh", "redis_stale": "last_good",
        "durable_last_good": "last_good", "process_last_good": "last_good",
        "inline": "inline", "inline_error": "unavailable", "cancelled": "unavailable",
        "unavailable": "unavailable",
    }.get(row.get("tier"))
    if expected is not None and provenance != expected and "invalid_provenance" not in errors:
        errors.append("provenance_tier_mismatch")
    if not row.get("observable", False):
        errors.append("provenance_not_observable")
    fields = set(row.get("signal_fields", []))
    if fields - {"provenance"}:
        errors.append("identity_bearing_signal")
    state = row.get("session_state")
    if row.get("later_queries") and state == "statement_cancelled":
        errors.append("dirty_session_reused")
    if row.get("later_queries") and state == "rollback_failed":
        errors.append("rollback_failure_reused")
    if row.get("db_mutated") and row.get("later_queries") and state not in {
        "clean", "rolled_back", "isolated_fill_session"
    } and not any(e in errors for e in ("dirty_session_reused", "rollback_failure_reused")):
        errors.append("unsafe_session_transition")
    return errors


def validate_native(row: dict[str, Any], corpus: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    dispatch = row.get("dispatch_identity")
    current = row.get("current_identity")
    if dispatch not in corpus["opaque_identities"] or current not in corpus["opaque_identities"]:
        errors.append("unknown_identity_fixture")
    same_identity = dispatch == current
    signed_in = dispatch != "anon"
    auth_consistent = bool(row.get("was_authenticated")) == signed_in
    if row.get("publish") and not (same_identity and auth_consistent):
        errors.append("cross_identity_publish" if not same_identity else "principal_auth_mismatch")
    if row.get("store") and not (same_identity and auth_consistent):
        errors.append("cross_identity_store" if not same_identity else "store_auth_mismatch")

    token = row.get("render_token")
    ack = row.get("ack_generation")
    if token is not None:
        required = {"generation", "started_at", "provenance", "item_count"}
        if set(token) != required:
            errors.append("invalid_render_token")
        elif ack != token["generation"]:
            errors.append("render_ack_generation_mismatch")
        if row.get("ack_source") != "generation":
            errors.append("invalid_ack_source")
    elif ack is not None:
        errors.append("ack_without_render_token")
    if row.get("reads_live_count"):
        errors.append("mutable_render_count")
    if row.get("reads_mutable_start"):
        errors.append("mutable_render_start")
    if row.get("requires_onappear_refire"):
        errors.append("onappear_refire_assumption")
    identities = set(corpus["opaque_identities"])
    if set(row.get("telemetry_fields", [])) & identities:
        errors.append("identity_bearing_telemetry")
    return errors


def evaluate(corpus: dict[str, Any], validator: Any) -> dict[str, dict[str, list[str]]]:
    return {
        "accepted": {row["id"]: validator(row, corpus) for row in corpus["scenarios"]},
        "rejected": {
            row["id"]: validator(row, corpus)
            for row in corpus.get("rejected_counterexamples", [])
        },
    }


def main() -> int:
    golf = load_fixture(GOLF_FIXTURES)
    native = load_fixture(NATIVE_FIXTURES)
    print(json.dumps({"golf": evaluate(golf, validate_golf), "native": evaluate(native, validate_native)}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
