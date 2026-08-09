"""AST oracle for imports that cannot resolve from the backend working directory."""

from __future__ import annotations

import argparse
import ast
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FIXTURES = ROOT / "tests/evals/fixtures/python_import_guard_contract.json"
CURRENT_RE = re.compile(r"^[ \t]*(?:from|import)[ \t]+backend\.", re.MULTILINE)


def current_regex_flags(source: str) -> bool:
    return bool(CURRENT_RE.search(source))


def forbidden_imports(source: str) -> list[str]:
    """Return normalized forbidden imports; comments/strings are never code."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return ["SYNTAX_ERROR"]
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "backend" or alias.name.startswith("backend."):
                    found.append(f"import:{alias.name}")
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if node.level == 0 and (module == "backend" or module.startswith("backend.")):
                found.append(f"from:{module}")
        elif isinstance(node, ast.Call) and node.args:
            target = node.func
            is_import_module = (
                isinstance(target, ast.Attribute)
                and isinstance(target.value, ast.Name)
                and target.value.id == "importlib"
                and target.attr == "import_module"
            ) or (isinstance(target, ast.Name) and target.id == "import_module")
            literal = node.args[0]
            if is_import_module and isinstance(literal, ast.Constant) and isinstance(literal.value, str):
                name = literal.value
                if name == "backend" or name.startswith("backend."):
                    found.append(f"dynamic:{name}")
    return sorted(set(found))


def evaluate(case: dict) -> dict:
    source = case["source"]
    forbidden = forbidden_imports(source)
    return {
        "verdict": "REFUSE" if forbidden else "ALLOW",
        "forbidden": forbidden,
        "current_regex_flags": current_regex_flags(source),
    }


def evaluate_pack(pack: dict) -> dict:
    results = []
    passed = 0
    for case in pack["cases"]:
        actual = evaluate(case)
        mismatches = [] if actual == case["expected"] else ["EXPECTED_RESULT_MISMATCH"]
        passed += not mismatches
        results.append({"id": case["id"], "actual": actual, "expected_mismatches": mismatches})
    return {"cases": len(results), "passed": passed, "results": results}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixtures", type=Path, default=DEFAULT_FIXTURES)
    args = parser.parse_args()
    result = evaluate_pack(json.loads(args.fixtures.read_text()))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["passed"] == result["cases"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
