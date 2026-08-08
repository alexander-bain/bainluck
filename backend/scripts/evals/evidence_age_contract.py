"""Dependency-free oracle for timestamped health evidence authority."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

FIXTURE = Path(__file__).parents[2] / "tests/evals/fixtures/evidence_age_contract.json"


def load_corpus(path: str | Path = FIXTURE) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("schema_version") != "evidence-age-contract/v1":
        raise ValueError("SCHEMA_VERSION_INVALID")
    cases = payload.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("CASES_REQUIRED")
    ids = [r.get("id") for r in cases if isinstance(r, dict)]
    if len(ids) != len(cases) or any(not isinstance(v, str) or not v for v in ids):
        raise ValueError("CASE_ID_REQUIRED")
    if len(ids) != len(set(ids)):
        raise ValueError("CASE_ID_DUPLICATE")
    return payload


def evaluate_case(row: dict[str, Any]) -> dict[str, Any]:
    e = row["evidence"]
    age = e.get("age_s")
    max_age = e.get("max_age_s")
    timestamp = e.get("timestamp", "valid")
    last_good = e.get("last_good", False)
    evicted = e.get("evicted", False)
    producer_alive = e.get("producer_alive", True)
    component_ages = e.get("component_ages_s", [])
    reasons: list[str] = []

    if evicted:
        authority, headline, banner, cache = "NO_EVIDENCE", "unknown", "unavailable", "miss"
        reasons.append("CACHE_EVICTED")
    elif timestamp in {"missing", "malformed"} or age is None or max_age is None:
        authority, headline, banner, cache = "NO_TIMESTAMP", "unknown", "age_unknown", "preserve"
        reasons.append("TIMESTAMP_MISSING" if timestamp == "missing" else "TIMESTAMP_INVALID")
    elif timestamp == "future" or age < 0:
        authority, headline, banner, cache = "NO_TIMESTAMP", "unknown", "clock_invalid", "preserve"
        reasons.append("TIMESTAMP_IN_FUTURE")
    elif age > max_age or any(a > max_age for a in component_ages):
        authority, headline, banner, cache = "DATED_STALE", "stale", "dated_stale", "serve_stale" if last_good else "preserve"
        reasons.append("EVIDENCE_EXPIRED")
        if component_ages and any(a > max_age for a in component_ages):
            reasons.append("COMPONENT_EXPIRED")
    else:
        authority, headline, banner, cache = "FRESH_BOUNDED", e.get("fresh_headline", "green"), "none", "serve"

    if not producer_alive and authority == "FRESH_BOUNDED":
        reasons.append("PRODUCER_DEAD_WITHIN_GRACE")
    display_date = timestamp == "valid"
    return {
        "authority": authority,
        "headline": headline,
        "display_date": display_date,
        "banner": banner,
        "cache_action": cache,
        "reason_codes": sorted(reasons),
    }


def evaluate_corpus(payload: dict[str, Any]) -> dict[str, Any]:
    details = []
    for row in sorted(payload["cases"], key=lambda x: x["id"]):
        actual = evaluate_case(row)
        details.append({"id": row["id"], "actual": actual, "expected": row["expected"], "passed": actual == row["expected"]})
    return {"schema_version": payload["schema_version"], "total": len(details), "passed": sum(x["passed"] for x in details), "details": details}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", default=str(FIXTURE))
    args = parser.parse_args()
    report = evaluate_corpus(load_corpus(args.fixture))
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["passed"] == report["total"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
