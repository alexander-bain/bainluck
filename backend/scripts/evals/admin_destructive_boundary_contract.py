"""Q315 direct-destruction census and second-token oracle."""

from __future__ import annotations

import ast
from copy import deepcopy
from functools import lru_cache
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
    # Read current contents on every call: mutation controls may edit a file
    # without changing its path, size or mtime. Cache parsing, never a PASS.
    root = ROUTES.resolve()
    sources = tuple(
        (path.name, path.read_text()) for path in sorted(root.glob("admin_*.py"))
    )
    parsed = _parse_handlers(
        str(root), sources, tuple(sorted(MUTATING_METHODS)), tuple(DESTRUCTIVE_SIGNALS)
    )
    # Callers historically received fresh nested dictionaries and signal lists.
    return deepcopy(parsed)


@lru_cache(maxsize=1)
def _parse_handlers(
    root: str,
    sources: tuple[tuple[str, str], ...],
    mutating_methods: tuple[str, ...],
    destructive_signals: tuple[str, ...],
) -> dict[str, dict]:
    """Reuse only the latest identical root/content/classification snapshot."""
    found: dict[str, dict] = {}
    for name, source in sources:
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            body = ast.get_source_segment(source, node) or ""
            signals = [
                signal for signal in destructive_signals if signal in body.lower()
            ]
            if not signals:
                continue
            for decorator in node.decorator_list:
                if not (
                    isinstance(decorator, ast.Call)
                    and isinstance(decorator.func, ast.Attribute)
                    and decorator.func.attr in mutating_methods
                    and decorator.args
                    and isinstance(decorator.args[0], ast.Constant)
                ):
                    continue
                route = str(decorator.args[0].value)
                key = f"{name}:{decorator.func.attr}:{route}"
                found[key] = {
                    "module": name,
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
        passed = bool(
            observed
            and observed["strong_gate_calls"] == 1
            and observed["weak_gate_calls"] == 0
        )
        rows.append({"id": case["id"], "actual": observed, "passed": passed})
    return {
        "total": len(rows),
        "passed": sum(row["passed"] for row in rows),
        "rows": rows,
    }
