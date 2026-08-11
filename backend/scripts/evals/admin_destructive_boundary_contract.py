"""Q315 direct-destruction census and second-token oracle."""
from __future__ import annotations

import ast
import json
import os
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
ROUTES = Path(os.environ.get("C271_ROUTES_DIR", REPO / "backend/app/routes"))
FIXTURE = REPO / "backend/tests/evals/fixtures/admin_destructive_boundary_contract.json"
MUTATING_METHODS = {"post", "put", "patch", "delete"}
DESTRUCTIVE_SIGNALS = (
    "delete from",
    "drop index",
    "vacuum",
    "db.delete(",
    "db.execute(delete(",
    "os.unlink(",
    "shutil.rmtree(",
)


def load_pack(path: Path = FIXTURE) -> dict:
    return json.loads(path.read_text())


def handlers() -> dict[str, dict]:
    found: dict[str, dict] = {}
    for path in sorted(ROUTES.glob("admin_*.py")):
        source = path.read_text()
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            body = ast.get_source_segment(source, node) or ""
            signals = [signal for signal in DESTRUCTIVE_SIGNALS if signal in body.lower()]
            if not signals:
                continue
            for decorator in node.decorator_list:
                if not (
                    isinstance(decorator, ast.Call)
                    and isinstance(decorator.func, ast.Attribute)
                    and decorator.func.attr in MUTATING_METHODS
                    and decorator.args
                    and isinstance(decorator.args[0], ast.Constant)
                ):
                    continue
                route = str(decorator.args[0].value)
                key = f"{path.name}:{decorator.func.attr}:{route}"
                found[key] = {
                    "module": path.name,
                    "method": decorator.func.attr,
                    "route": route,
                    "function": node.name,
                    "signals": signals,
                    "strong_gate_calls": body.count("_check_admin_destructive("),
                    "weak_gate_calls": body.count("_check_admin_secret("),
                }
    return found


def evaluate_pack(pack: dict) -> dict:
    actual = handlers()
    rows = []
    for case in pack["cases"]:
        key = f"{case['module']}:{case['method']}:{case['route']}"
        observed = actual.get(key)
        passed = bool(observed and observed["strong_gate_calls"] == 1 and observed["weak_gate_calls"] == 0)
        rows.append({"id": case["id"], "actual": observed, "passed": passed})
    return {"total": len(rows), "passed": sum(row["passed"] for row in rows), "rows": rows}
