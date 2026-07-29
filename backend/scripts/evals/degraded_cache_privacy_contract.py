"""Pure C80 contracts for degraded feed publication and Play identity privacy."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
DEGRADED_FIXTURES = ROOT / "degraded_feed_publication_fixtures.json"
KID_FIXTURES = ROOT / "kid_session_privacy_fixtures.json"
OPAQUE_SESSION = re.compile(r"^kid_device:[a-z0-9_-]{8,64}$")


def load_fixture(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def validate_degraded(row: dict[str, Any], corpus: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    degraded = row.get("build_state") in corpus["degraded_build_states"]
    if bool(row.get("degraded_marker")) != degraded:
        errors.append("degraded_marker_mismatch")
    if degraded:
        if row.get("process_last_good_written"):
            errors.append("degraded_process_last_good")
        if row.get("redis_fresh_written"):
            errors.append("degraded_redis_fresh")
        if row.get("redis_stale_written"):
            errors.append("degraded_redis_stale")
        if row.get("next_same_key_action") != "rebuild":
            errors.append("degraded_blocks_recovery")
    elif row.get("build_state") == "complete":
        if not row.get("process_last_good_written"):
            errors.append("complete_missing_last_good")
        if row.get("redis_publish_status") == "success" and not (
            row.get("redis_fresh_written") and row.get("redis_stale_written")
        ):
            errors.append("complete_missing_redis_mirror")
    if row.get("returned_to_current_request") and degraded and not row.get("degraded_marker"):
        errors.append("unmarked_degraded_response")
    return errors


def validate_kid(row: dict[str, Any], corpus: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    session = row.get("session_id")
    if row.get("transmits"):
        if not isinstance(session, str) or not OPAQUE_SESSION.fullmatch(session):
            errors.append("nonopaque_session_id")
    if row.get("display_token") and row.get("display_token") in str(session):
        errors.append("display_name_in_session")
    if row.get("display_token") in row.get("transport_values", []):
        errors.append("display_name_in_transport")
    if row.get("display_token") in row.get("persistence_values", []):
        errors.append("display_name_in_persistence")
    if row.get("display_token") in row.get("telemetry_values", []):
        errors.append("display_name_in_telemetry")
    if row.get("legacy_name_session_written"):
        errors.append("legacy_name_session_continued")
    if row.get("expected_session_id") is not None and session != row.get("expected_session_id"):
        errors.append("session_stability_mismatch")
    if row.get("must_differ_from") is not None and row.get("must_differ_from") == session:
        errors.append("cross_device_collision")
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
    degraded = load_fixture(DEGRADED_FIXTURES)
    kid = load_fixture(KID_FIXTURES)
    print(json.dumps({
        "degraded_feed": evaluate(degraded, validate_degraded),
        "kid_session": evaluate(kid, validate_kid),
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
