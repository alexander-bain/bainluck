"""Offline scoreboard; extends eval_registry_contract (ruling 002).

This reports recorded evidence, not a new product or mutation run. A registry
canonical and its extensions form one family. JSON retains every member.
"""

from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
from typing import Any

from scripts.evals.eval_bite_rate_audit import evaluate_sample


REPO = Path(__file__).resolve().parents[3]
EVALS = "backend/scripts/evals/"


def _read(root: Path, path: str) -> Any:
    return json.loads((root / path).read_text())


def _count(root: Path, source: dict[str, Any]) -> int:
    path = root / source["path"]
    if source.get("kind") == "test_functions":
        return sum(
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name.startswith("test_")
            for node in ast.walk(ast.parse(path.read_text()))
        )
    if source.get("kind") == "ast_list":
        tree = ast.parse(path.read_text())
        for node in tree.body:
            targets = node.targets if isinstance(node, ast.Assign) else (
                [node.target] if isinstance(node, ast.AnnAssign) else []
            )
            if any(isinstance(t, ast.Name) and t.id == source["key"] for t in targets):
                if not isinstance(node.value, (ast.List, ast.Tuple, ast.Dict)):
                    raise ValueError(f"{path}: {source['key']} is not a literal case table")
                return len(node.value.keys if isinstance(node.value, ast.Dict) else node.value.elts)
        raise ValueError(f"{path}: case table {source['key']} absent")
    value = _read(root, source["path"])
    for part in source.get("selector", []):
        value = value[part]
    if not isinstance(value, list):
        raise ValueError(f"{path}: case selector is not an array")
    return len(value)


def build_scoreboard(root: Path = REPO) -> dict[str, Any]:
    registry = _read(root, EVALS + "eval_registry.json")
    record = _read(root, EVALS + "scoreboard_record.json")
    known: set[str] = set()
    families = []
    for domain in registry["domains"]:
        members = []
        for name in [domain["canonical"], *(m["name"] for m in domain["members"])]:
            known.add(name)
            evidence = record["artifacts"].get(name, {})
            sources = evidence.get("case_sources", [])
            members.append({
                "name": name,
                "cases": sum(_count(root, s) for s in sources) if sources else None,
                "case_sources": sources,
                "last_result": evidence.get("last_result"),
            })
        families.append({
            "domain": domain["domain"],
            "canonical": domain["canonical"],
            "cases": sum(m["cases"] or 0 for m in members),
            "unknown_case_counts": [m["name"] for m in members if m["cases"] is None],
            "members": members,
        })

    # Pre-ratification artifacts remain visible, distinct from reviewed legacy.
    on_disk = {p.stem for p in (root / EVALS).glob("*.py")}
    grandfathered = set(record["pre_ratification"]) - known
    legacy = {row["name"] for row in registry.get("legacy", [])}
    unregistered = on_disk - known - grandfathered - legacy
    baseline = _read(root, "backend/tests/fixtures/matching_golden_baseline.json")
    bite = evaluate_sample(_read(root, "backend/tests/evals/fixtures/eval_bite_rate_audit.json"))
    return {
        "schema_version": "eval-scoreboard/v1",
        "recorded_at_pt": record["recorded_at_pt"],
        "recorded_source_sha": record["source_sha"],
        "families": families,
        "golden": {
            "passing": sum(value is True for value in baseline["pairs"].values()),
            "total": len(baseline["pairs"]),
            "floor": baseline["passing_count"],
            "declared_total": baseline["pair_count"],
        },
        "bite_rate": {k: bite[k] for k in ("total", "mutation_bites", "real_boundaries")},
        "mutation_residue": record["mutation_residue"],
        "registry": {
            "registered": len(known),
            "unregistered": len(unregistered),
            "legacy": len(legacy),
            "grandfathered": len(grandfathered & on_disk),
            "unregistered_names": sorted(unregistered),
            "legacy_names": sorted(legacy),
        },
    }


def render(board: dict[str, Any]) -> str:
    lines = [
        "BAIN LUCK EVALS — recorded evidence; no production reads",
        f"Results recorded {board['recorded_at_pt']} at {board['recorded_source_sha'][:10]}",
        "DOMAIN / CANONICAL FAMILY                         CASES   LAST RECORDED RESULT",
    ]
    for family in board["families"]:
        results = [m["last_result"] for m in family["members"] if m["last_result"]]
        passed = sum(r["passed"] for r in results)
        failed = sum(r["failed"] for r in results)
        skipped = sum(r["skipped"] for r in results)
        unknown = len(family["members"]) - len(results)
        result = f"tests {passed} pass/{failed} fail/{skipped} skip"
        if unknown:
            result += f"; {unknown} unrecorded"
        cases = str(family["cases"]) + ("+?" if family["unknown_case_counts"] else "")
        label = f"{family['domain']} / {family['canonical'].removesuffix('_contract')}"
        lines.append(f"{label:62} {cases:>5}   {result}")
    g, b, r, counts = (board[k] for k in ("golden", "bite_rate", "mutation_residue", "registry"))
    lines += [
        f"Golden: {g['passing']}/{g['total']} passing; floor {g['floor']}/{g['declared_total']} (recorded, not replayed)",
        f"Bite audit: {b['mutation_bites']}/{b['total']} bite; {b['real_boundaries']}/{b['total']} real boundaries (offline replay)",
        f"Mutation residue: {r['verdict']} (recorded); {r['needles']} needles, {r['targets']} targets; {r['scope']}",
        f"Registry: {counts['registered']} registered / {counts['unregistered']} unregistered / {counts['legacy']} legacy; {counts['grandfathered']} pre-ratification unregistered",
        "Cases include fixture rows, mutants and named generated tests; +? = missing counts.",
        "A recorded test pass grades its contract, not production; --json lists every member and source.",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="include every member and evidence source")
    args = parser.parse_args()
    try:
        board = build_scoreboard()
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.exit(2, f"Scoreboard unavailable: {exc}\n")
    print(json.dumps(board, indent=2, sort_keys=True) if args.json else render(board))
    return 0  # Reporting uncomfortable evidence is never a quality gate.


if __name__ == "__main__":
    raise SystemExit(main())
