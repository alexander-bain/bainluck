"""Mutation and boundary-fidelity extension of canonical eval_registry_contract."""

from __future__ import annotations

import copy
import importlib
import json
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests/evals/fixtures/eval_bite_rate_audit.json"


def _fixture(name: str) -> dict[str, Any]:
    return json.loads((ROOT / f"tests/evals/fixtures/{name}.json").read_text())


def _find_case(payload: dict[str, Any], case_id: str) -> dict[str, Any]:
    return copy.deepcopy(next(row for row in payload["cases"] if row["id"] == case_id))


def _materialize(contract: str, case_id: str) -> tuple[Callable[[dict[str, Any]], Any], dict[str, Any]]:
    module = importlib.import_module(f"scripts.evals.{contract}")
    payload = _fixture(contract)
    row = _find_case(payload, case_id)
    if contract == "calibration_exit_exam_bundle_contract":
        return module.evaluate_bundle, row["bundle"]
    if contract == "first_content_latency_attribution_contract":
        packet = copy.deepcopy(payload["base"])
        packet.update(row.get("set", {}))
        for key in row.get("delete", []):
            packet.pop(key, None)
        return module.evaluate_packet, packet
    if contract == "first_card_client_contract":
        return module.evaluate_case, row
    if contract == "nonexclusive_bundle_contract":
        expanded = next(row for row in module.load_corpus()["cases"] if row["id"] == case_id)
        return module.classify, copy.deepcopy(expanded)
    return module.evaluate, row.get("input", row)


def _set_path(value: dict[str, Any], path: list[Any], replacement: Any) -> dict[str, Any]:
    result = copy.deepcopy(value)
    cursor: Any = result
    for key in path[:-1]:
        cursor = cursor[key]
    cursor[path[-1]] = replacement
    return result


def evaluate_sample(payload: dict[str, Any]) -> dict[str, Any]:
    rows = []
    for sample in payload["samples"]:
        evaluator, original = _materialize(sample["contract"], sample["case_id"])
        baseline = evaluator(copy.deepcopy(original))
        mutated = evaluator(_set_path(original, sample["mutation"]["path"], sample["mutation"]["value"]))
        bites = baseline != mutated
        real_boundary = sample["boundary"] == "real_production_type"
        rows.append({
            "queue": sample["queue"],
            "contract": sample["contract"],
            "case_id": sample["case_id"],
            "bites": bites,
            "boundary": sample["boundary"],
            "real_boundary": real_boundary,
        })
    total = len(rows)
    bites = sum(row["bites"] for row in rows)
    boundaries = sum(row["real_boundary"] for row in rows)
    return {
        "total": total,
        "mutation_bites": bites,
        "mutation_bite_rate": bites / total if total else None,
        "real_boundaries": boundaries,
        "real_boundary_rate": boundaries / total if total else None,
        "rows": rows,
    }


def validate_retro(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    ids: set[str] = set()
    for row in payload["escaped_defect_retro"]:
        if row["id"] in ids:
            errors.append("RETRO_ID_DUPLICATE")
        ids.add(row["id"])
        if not row.get("production_evidence"):
            errors.append(f"PRODUCTION_EVIDENCE_MISSING:{row['id']}")
        if not row.get("canonical_catcher") or not row.get("case_id"):
            errors.append(f"CANONICAL_CASE_MISSING:{row['id']}")
        else:
            candidates = [
                ROOT / f"tests/evals/fixtures/{row['canonical_catcher']}.json",
                ROOT / f"scripts/evals/{row['canonical_catcher']}.json",
            ]
            fixture = next((path for path in candidates if path.exists()), None)
            if fixture is None:
                errors.append(f"CANONICAL_FIXTURE_ABSENT:{row['id']}")
                continue
            pack = json.loads(fixture.read_text())
            cases = pack.get("cases") or pack.get("scenarios") or []
            if row["case_id"] not in {case.get("id") for case in cases}:
                errors.append(f"CANONICAL_CASE_NOT_MINTED:{row['id']}")
    return sorted(errors)


def main() -> int:
    payload = json.loads(FIXTURE.read_text())
    result = evaluate_sample(payload)
    result["retro_errors"] = validate_retro(payload)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["total"] == 40 and result["mutation_bites"] == 40 and not result["retro_errors"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
