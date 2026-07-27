"""Offline entity-correct Search evaluator using C47's probe registry.

The legacy markdown parser remains available only to identify rows needing
migration. Scoring requires versioned Search probes with stable entity IDs.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

try:
    from .probe_registry import filter_probes, load_registry
except ImportError:  # Direct ``python scripts/evals/search_gold_eval.py`` use.
    from probe_registry import filter_probes, load_registry

BACKEND = Path(__file__).resolve().parents[2]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

REAL_CLASSES = {
    "Golf": "category_as_query", "MLB": "category_as_query", "tush push": "concept_rule",
    "Taylor Swift Madison": "qualified_entity", "Where will Taylor Swift and Travis Kelce's Wedding occur?": "full_question",
    "us open": "ambiguity", "fable": "self_reference",
}


def parse_gold_markdown(path: str | Path) -> list[dict[str, str]]:
    text = Path(path).read_text(encoding="utf-8").replace("\xa0", " ")
    rows: list[dict[str, str]] = []
    before_real, _, real = text.partition("## THE REAL HALF")
    family = "coverage"
    for line in before_real.splitlines():
        match = re.match(r"^([^:#]+):\s*(.+)$", line)
        if not match or line.startswith(("Source", "STATUS")):
            continue
        heading, body = match.groups()
        surface_match = re.search(r"\(([^)]+)\)\s*$", body)
        expected = surface_match.group(1).split("/")[0] if surface_match else "any"
        body = re.sub(r"\s*\([^)]+\)\s*$", "", body)
        family = heading.strip().lower().replace(" ", "_")
        rows.extend({"query": q.strip(" \"") , "class": family, "expected_surface": expected} for q in body.split(" · ") if q.strip())
    for heading in ("Native Recents", "Desktop Recents"):
        match = re.search(rf"^{heading}:\s*(.+)$", real, re.MULTILINE)
        if match:
            for query in match.group(1).split(" · "):
                query = query.strip(" \"")
                rows.append({"query": query, "class": REAL_CLASSES.get(query, "real_history"), "expected_surface": "any"})
    return rows


class SearchGoldMigrationError(ValueError):
    """Raised when legacy gold lacks stable entity identity."""


def load_result_rows(path: str | Path) -> dict[str, list[dict[str, Any]]]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    rows = payload.get("results", payload) if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        raise ValueError("SEARCH_RESULTS_INVALID: expected a result-row list")
    result: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        key = row.get("probe_key") if isinstance(row, dict) else None
        candidates = row.get("candidates") if isinstance(row, dict) else None
        if not isinstance(key, str) or not isinstance(candidates, list):
            raise ValueError("SEARCH_RESULTS_INVALID: probe_key and candidates are required")
        if key in result:
            raise ValueError(f"SEARCH_RESULTS_DUPLICATE: {key}")
        result[key] = candidates
    return result


def require_entity_gold(rows: list[dict[str, Any]]) -> None:
    """Reject legacy surface-only rows instead of recreating the old false green."""

    missing = [row.get("query", "<unknown>") for row in rows if not row.get("expected_entity_id")]
    if missing:
        raise SearchGoldMigrationError(
            "SEARCH_GOLD_MIGRATION_REQUIRED: stable expected_entity_id missing for "
            + ", ".join(sorted(missing))
        )


def _score_probe(probe: dict[str, Any], candidates: list[dict[str, Any]]) -> dict[str, Any]:
    identity = probe["identity"]
    oracle = probe["oracle"]["answer"]
    lifecycle = probe["lifecycle"]
    key = identity["probe_key"]
    expected_ids = {oracle["expected_entity_id"], *oracle.get("allowed_entity_ids", [])}
    expected_surfaces = set(oracle["expected_surfaces"])
    expected_type = oracle["expected_item_type"]

    top = candidates[0] if candidates else None
    expected_rank = next(
        (index for index, candidate in enumerate(candidates, 1) if candidate.get("entity_id") in expected_ids),
        None,
    )
    if top is None:
        code = "NO_RESULTS"
    elif top.get("entity_id") not in expected_ids:
        code = "ENTITY_NOT_TOP"
    elif "any" not in expected_surfaces and top.get("surface") not in expected_surfaces:
        code = "SURFACE_MISMATCH"
    elif top.get("item_type") != expected_type:
        code = "TYPE_MISMATCH"
    else:
        code = "PASS"

    passed = code == "PASS"
    known = lifecycle["known_failure_status"]
    if known == "xfail":
        disposition = "xpass" if passed else "xfail"
    elif known == "fixed" and not passed:
        disposition = "regression"
    else:
        disposition = "pass" if passed else "fail"
    return {
        "probe_key": key,
        "probe_version": identity["probe_version"],
        "query_class": oracle["query_class"],
        "code": code,
        "disposition": disposition,
        "expected_rank": expected_rank,
        "reciprocal_rank": 1 / expected_rank if expected_rank else 0.0,
        "actual_top": None if top is None else {
            "entity_id": top.get("entity_id"),
            "surface": top.get("surface"),
            "item_type": top.get("item_type"),
        },
    }


def evaluate_entity_probes(
    probes: list[dict[str, Any]],
    results: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    """Score supplied ranked results against validated Search probes."""

    details = []
    seen_keys = set()
    for probe in sorted(probes, key=lambda row: (row["identity"]["probe_key"], row["identity"]["probe_version"])):
        if probe["identity"]["task_type"] != "search_entity":
            raise ValueError("SEARCH_TASK_TYPE_INVALID")
        key = probe["identity"]["probe_key"]
        if key in seen_keys:
            raise ValueError(f"SEARCH_PROBE_DUPLICATE: {key}")
        seen_keys.add(key)
        details.append(_score_probe(probe, results.get(key, [])))

    counts = {name: sum(row["disposition"] == name for row in details) for name in ("pass", "fail", "xfail", "xpass", "regression")}
    strict_passes = sum(row["code"] == "PASS" for row in details)
    by_class: dict[str, dict[str, int]] = {}
    for row in details:
        bucket = by_class.setdefault(row["query_class"], {"total": 0, "passed": 0})
        bucket["total"] += 1
        bucket["passed"] += row["code"] == "PASS"
    return {
        "total": len(details),
        "entity_top_1_rate": strict_passes / len(details) if details else 0.0,
        "mean_reciprocal_rank": sum(row["reciprocal_rank"] for row in details) / len(details) if details else 0.0,
        "lifecycle_counts": counts,
        "per_query_class": {key: by_class[key] for key in sorted(by_class)},
        "details": details,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry")
    parser.add_argument("--split", choices=("train", "tune", "test", "canary"))
    parser.add_argument("--results")
    parser.add_argument("--legacy-gold")
    args = parser.parse_args()
    if args.legacy_gold:
        require_entity_gold(parse_gold_markdown(args.legacy_gold))
        raise AssertionError("legacy parser unexpectedly produced entity gold")
    if not (args.registry and args.split and args.results):
        parser.error("--registry, --split, and --results are required")
    records = load_registry(args.registry)
    probes = filter_probes(records, task_type="search_entity", split=args.split)
    report = evaluate_entity_probes(probes, load_result_rows(args.results))
    print(json.dumps(report, indent=2))
    counts = report["lifecycle_counts"]
    return 1 if counts["fail"] or counts["regression"] or counts["xpass"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
