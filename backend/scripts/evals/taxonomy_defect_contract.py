"""Dependency-free oracle for product-visible taxonomy health."""

from __future__ import annotations

import json
from pathlib import Path


FIXTURE = Path(__file__).parents[2] / "tests/evals/fixtures/taxonomy_defect_contract.json"
IDENTITY_NAMESPACES = ("sport", "league", "category")


def load_corpus() -> dict:
    return json.loads(FIXTURE.read_text())


def _namespace(tags: list[str], name: str) -> set[str]:
    prefix = f"{name}:"
    return {tag[len(prefix):] for tag in tags if isinstance(tag, str) and tag.startswith(prefix)}


def record_reasons(row: dict) -> list[str]:
    if not row.get("eligible", False):
        return []
    inline = row.get("inline_tags", [])
    stored = row.get("stored_tags", [])
    reasons = set()
    if not _namespace(inline, "sport"):
        reasons.add("missing")
    if any(not row.get("stored_tag_validity", {}).get(tag, True) for tag in stored):
        reasons.add("invalid")
    for namespace in IDENTITY_NAMESPACES:
        expected = _namespace(inline, namespace)
        persisted = _namespace(stored, namespace)
        if expected and persisted and expected.isdisjoint(persisted):
            reasons.add("authority_disagree")
    return sorted(reasons)


def census_decision(case: dict) -> dict:
    if case["census_state"] == "failed":
        return {"verdict": "unknown", "reason_codes": [], "actionable_count": 0}
    reasons = [reason for row in case.get("rows", []) for reason in record_reasons(row)]
    if reasons:
        verdict = "red"
    elif case["census_state"] != "complete":
        verdict = "yellow"
    else:
        verdict = "green"
    return {
        "verdict": verdict,
        "reason_codes": sorted(set(reasons)),
        "actionable_count": sum(bool(record_reasons(row)) for row in case.get("rows", [])),
    }


def evaluate_corpus(corpus: dict) -> dict:
    results = []
    for case in corpus["cases"]:
        actual = census_decision(case)
        passed = actual == case["expected"]
        results.append({"id": case["id"], "passed": passed, "actual": actual})
    return {"total": len(results), "passed": sum(row["passed"] for row in results), "cases": results}


if __name__ == "__main__":
    print(json.dumps(evaluate_corpus(load_corpus()), indent=2, sort_keys=True))
