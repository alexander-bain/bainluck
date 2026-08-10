"""Rendered cross-surface extension of canonical calibration_population_integrity."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


FIXTURE = Path(__file__).parents[2] / "tests/evals/fixtures/calibration_rendered_parity_contract.json"
FIELDS = {
    "population_version", "generated_at", "contract_state", "cache_status",
    "cohort_n", "full_n", "moved_n", "unchanged_n", "not_applicable_n",
    "partition_reconciles", "ece_pp", "brier",
}


def evaluate(case: dict[str, Any]) -> dict[str, Any]:
    reasons: list[str] = []
    web = case.get("web") or {}
    native = case.get("native") or {}
    payload_sha = case.get("payload_sha256")
    if not payload_sha or web.get("payload_sha256") != payload_sha or native.get("payload_sha256") != payload_sha:
        reasons.append("NOT_ONE_PAYLOAD")
    if web.get("producer") != "web_rendered_dom":
        reasons.append("WEB_NOT_RENDERED_BOUNDARY")
    if native.get("producer") != "native_rendered_accessibility":
        reasons.append("NATIVE_NOT_RENDERED_BOUNDARY")
    for surface, artifact in (("WEB", web), ("NATIVE", native)):
        figures = artifact.get("figures") or {}
        if FIELDS - set(figures):
            reasons.append(f"{surface}_FIGURES_INCOMPLETE")
    if not reasons:
        for field in sorted(FIELDS):
            if web["figures"][field] != native["figures"][field]:
                reasons.append(f"FIGURE_MISMATCH:{field}")
    return {"verdict": "GREEN" if not reasons else "REFUSE", "reasons": sorted(reasons)}


def main() -> int:
    payload = json.loads(FIXTURE.read_text())
    rows = []
    for case in payload["cases"]:
        actual = evaluate(case["input"])
        rows.append({"id": case["id"], "actual": actual, "ok": actual == case["expected"]})
    print(json.dumps(rows, indent=2, sort_keys=True))
    return 0 if all(row["ok"] for row in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
