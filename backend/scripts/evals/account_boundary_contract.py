"""Pure C78 validators for native and Google account-boundary fixtures."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
NATIVE_FIXTURES = ROOT / "native_account_isolation_fixtures.json"
GOOGLE_FIXTURES = ROOT / "google_access_token_audience_fixtures.json"


def load_fixture(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def validate_native(row: dict[str, Any], corpus: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    identities = set(corpus["opaque_identities"])
    dispatch = row.get("dispatch_identity")
    current = row.get("current_identity")
    if dispatch not in identities or current not in identities:
        errors.append("unknown_identity")

    if row["kind"] == "pagination":
        stale = row.get("captured_generation") != row.get("current_generation")
        forbidden = {
            "items": row.get("items_mutated"),
            "offset": row.get("offset_mutated"),
            "has_more": row.get("has_more_mutated"),
            "error": row.get("error_mutated"),
            "analytics": row.get("analytics_emitted"),
        }
        if stale:
            for field, changed in forbidden.items():
                if changed:
                    errors.append(f"stale_generation_{field}_mutation")
        if not row.get("guard_after_every_await"):
            errors.append("missing_post_await_generation_guard")
    elif row["kind"] == "cache":
        crossed = dispatch != current
        if crossed and row.get("cache_hit"):
            errors.append("cross_identity_cache_hit")
        if row.get("cache_hit") and not (
            row.get("identity_partitioned") or row.get("identity_change_evicted")
        ):
            errors.append("unbound_cache_hit")
        if crossed and not (
            row.get("identity_partitioned") or row.get("identity_change_evicted")
        ):
            errors.append("identity_change_not_isolated")
    else:
        errors.append("unknown_native_kind")

    if set(row.get("telemetry_values", [])) & identities:
        errors.append("identity_bearing_telemetry")
    return errors


def validate_google(row: dict[str, Any], corpus: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    authority = set(corpus["configuration_authority"]["symbolic_allowed_client_ids"])
    audience = row.get("introspected_audience")
    accepted_audience = audience in authority
    authorized_party = row.get("authorized_party")
    party_consistent = authorized_party in (None, audience)
    verified = (
        row.get("tokeninfo_status") == "ok"
        and accepted_audience
        and party_consistent
        and row.get("userinfo_status") == "ok"
        and row.get("email_present")
        and row.get("email_verified")
    )
    if row.get("accepted") != bool(verified):
        errors.append("acceptance_mismatch")
    if row.get("accepted") and not party_consistent:
        errors.append("authorized_party_mismatch")
    if not row.get("accepted"):
        for effect in corpus["forbidden_rejection_side_effects"]:
            if row.get(effect):
                errors.append(f"rejection_side_effect:{effect}")
    if audience is None and row.get("accepted"):
        errors.append("missing_audience_accepted")
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
    native = load_fixture(NATIVE_FIXTURES)
    google = load_fixture(GOOGLE_FIXTURES)
    print(json.dumps({
        "native": evaluate(native, validate_native),
        "google": evaluate(google, validate_google),
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
