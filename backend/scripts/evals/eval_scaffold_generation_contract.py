"""Canonical renderer and validator for portable eval test scaffolds."""

from __future__ import annotations

import ast
import re
from typing import Any


MODULE_RE = re.compile(r"^[a-z][a-z0-9_]*$")
SYMBOL_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def render(spec: dict[str, Any]) -> str:
    module = str(spec.get("module") or "")
    symbols = list(spec.get("symbols") or [])
    if not MODULE_RE.fullmatch(module):
        raise ValueError("MODULE_NAME_INVALID")
    if not symbols or any(not SYMBOL_RE.fullmatch(str(symbol)) for symbol in symbols):
        raise ValueError("SYMBOLS_INVALID")
    lines = []
    if spec.get("fixture"):
        lines.extend(["import json", "from pathlib import Path", ""])
    if len(symbols) == 1:
        lines.append(f"from scripts.evals.{module} import {symbols[0]}")
    else:
        lines.append(f"from scripts.evals.{module} import (")
        lines.extend(f"    {symbol}," for symbol in symbols)
        lines.append(")")
    if spec.get("fixture"):
        lines.extend(["", f'FIXTURE = Path(__file__).parent / "fixtures" / "{spec["fixture"]}"'])
    return "\n".join(lines) + "\n"


def validate(case: dict[str, Any]) -> dict[str, Any]:
    reasons: set[str] = set()
    source = str(case.get("source") or "")
    path = str(case.get("path") or "")
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return {"verdict": "REFUSE", "reasons": ["GENERATED_SYNTAX_ERROR"]}
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            imports.append(("." * node.level) + (node.module or ""))
        elif isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
    eval_imports = [name for name in imports if "scripts.evals" in name]
    if not eval_imports:
        reasons.add("EVAL_IMPORT_MISSING")
    if any(name.startswith("backend.scripts.evals") for name in eval_imports):
        reasons.add("BACKEND_PREFIX_GENERATED")
    if any(name.startswith(".") for name in eval_imports):
        reasons.add("RELATIVE_IMPORT_GENERATED")
    if any(not name.startswith("scripts.evals.") for name in eval_imports):
        reasons.add("NONCANONICAL_EVAL_IMPORT")
    expected_module = case.get("module")
    if expected_module and f"scripts.evals.{expected_module}" not in eval_imports:
        reasons.add("MODULE_IDENTITY_DRIFT")
    if not re.fullmatch(r"backend/tests/evals/test_[a-z0-9_]+\.py", path):
        reasons.add("GENERATED_TEST_PATH_INVALID")
    contexts = set(case.get("verified_contexts") or [])
    if not {"repo_root_pytest", "backend_pytest"} <= contexts:
        reasons.add("PYTEST_CONTEXTS_UNVERIFIED")
    if case.get("direct_execution") and "direct_script" not in contexts:
        reasons.add("DIRECT_CONTEXT_UNVERIFIED")
    fixture = case.get("fixture")
    if fixture:
        expected = f'Path(__file__).parent / "fixtures" / "{fixture}"'
        if expected not in source:
            reasons.add("FIXTURE_PATH_NOT_LOCAL")
    if case.get("same_file_loaded_twice"):
        reasons.add("DUPLICATE_MODULE_IDENTITY")
    return {"verdict": "ALLOW" if not reasons else "REFUSE", "reasons": sorted(reasons)}
