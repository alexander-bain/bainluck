#!/usr/bin/env python3
"""CAL-P198 sweep — falsy-zero conflation across the four unswept calibration modules.

A "falsy zero" is a value whose 0 is a MEANINGFUL quantity, tested for truth
(``if x:`` / ``x or default`` / ``not x``), so 0 is silently conflated with
absent/None. Known prior instances: P193-1 (phase_ledger:1299), P194-1
(calibration_main_build:1613/1615), and the three P192 writer collisions.

Runs from any cwd; bootstraps the repo root itself.
"""

from __future__ import annotations

import ast
import pathlib
import re
import sys


def repo_root() -> pathlib.Path:
    here = pathlib.Path(__file__).resolve()
    for p in [here, *here.parents]:
        if (p / "backend" / "app" / "utils" / "calibration_phase_ledger.py").exists():
            return p
    # /tmp copies: fall back to the known worktree
    cand = pathlib.Path("/Users/bain/bainluck-dev/calibration")
    if (cand / "backend" / "app" / "utils" / "calibration_phase_ledger.py").exists():
        return cand
    raise SystemExit("FATAL: could not locate repo root")


ROOT = repo_root()
APP = ROOT / "backend" / "app"

TARGETS = [
    APP / "tasks" / "calibration_beat_gauge_sampler.py",
    APP / "tasks" / "calibration_graded_share.py",
    APP / "tasks" / "calibration_published_twin_worker.py",
    APP / "tasks" / "calibration_sentinel.py",
]
# controls: the two modules already swept, whose known hits must reappear
CONTROLS = [
    (APP / "utils" / "calibration_phase_ledger.py", 1299),
    (APP / "tasks" / "calibration_main_build.py", 1613),
]

NUMERIC_NAME = re.compile(
    r"(?:^|_)(ms|count|counts|n|num|units|unit|total|len|size|idx|index|share|pct|"
    r"percent|score|budget|bound|age|days|secs|seconds|rows|banked|drift|drifted|"
    r"delta|elapsed|remaining|headroom|slack|floor|floors|worst|mean|sum|beats|"
    r"generation|attempts|observations|width|depth|offset|limit|cap|threshold|"
    r"sigma|bucket|buckets|samples|denominator|numerator)s?$",
    re.IGNORECASE,
)

NUMERIC_CALL = {
    "len", "int", "float", "sum", "round", "min", "max", "abs", "count",
}


def expr_label(node: ast.AST) -> str | None:
    """Return a dotted label for a bare value expression, else None."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = expr_label(node.value)
        return f"{base}.{node.attr}" if base else node.attr
    if isinstance(node, ast.Subscript):
        base = expr_label(node.value)
        key = None
        if isinstance(node.slice, ast.Constant):
            key = repr(node.slice.value)
        return f"{base}[{key or '...'}]" if base else None
    if isinstance(node, ast.Call):
        fn = expr_label(node.func)
        if fn and fn.split(".")[-1] in NUMERIC_CALL:
            return f"{fn}()"
        if fn and fn.split(".")[-1].startswith(("get", "count", "len")):
            return f"{fn}()"
        return None
    return None


def numeric_default_get(node: ast.AST) -> bool:
    """``x.get(k, 0)`` / ``x.get(k, 0.0)`` — the numeric default PROVES the
    caller expects a number, so a truth-test on it conflates a real 0 with
    absent. This is the exact shape of P193-1 (phase_ledger:1299)."""
    if not isinstance(node, ast.Call):
        return False
    fn = expr_label(node.func) or ""
    if fn.split(".")[-1] != "get" or len(node.args) < 2:
        return False
    d = node.args[1]
    return (
        isinstance(d, ast.Constant)
        and isinstance(d.value, (int, float))
        and not isinstance(d.value, bool)
    )


def looks_numeric(label: str, numeric_names: set[str]) -> bool:
    tail = label.split(".")[-1].split("[")[0].rstrip("()")
    if tail in numeric_names:
        return True
    if NUMERIC_NAME.search(tail):
        return True
    if label.endswith("()") and label.split(".")[-1].rstrip("()") in NUMERIC_CALL:
        return True
    return False


def collect_numeric_names(tree: ast.AST) -> set[str]:
    """Names assigned anywhere in the module from an unambiguously numeric expr."""
    out: set[str] = set()

    def numeric_value(v: ast.AST) -> bool:
        if isinstance(v, ast.Constant) and isinstance(v.value, (int, float)) and not isinstance(v.value, bool):
            return True
        if isinstance(v, ast.BinOp) and isinstance(v.op, (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow)):
            return True
        if isinstance(v, ast.Call):
            fn = expr_label(v.func) or ""
            if fn.split(".")[-1] in NUMERIC_CALL:
                return True
        return False

    for n in ast.walk(tree):
        targets = []
        if isinstance(n, ast.Assign):
            targets, val = n.targets, n.value
        elif isinstance(n, ast.AnnAssign) and n.value is not None:
            targets, val = [n.target], n.value
        elif isinstance(n, ast.AugAssign):
            targets, val = [n.target], n.value
        else:
            continue
        if not numeric_value(val):
            continue
        for t in targets:
            lbl = expr_label(t)
            if lbl:
                out.add(lbl.split(".")[-1].split("[")[0])
    return out


def truth_sites(tree: ast.AST):
    """Yield (node, context) for every expression whose TRUTH value is taken."""
    for n in ast.walk(tree):
        if isinstance(n, ast.BoolOp):
            for v in n.values[:-1]:
                yield v, ("or" if isinstance(n.op, ast.Or) else "and")
        elif isinstance(n, ast.UnaryOp) and isinstance(n.op, ast.Not):
            yield n.operand, "not"
        elif isinstance(n, (ast.If, ast.While)):
            yield n.test, "if"
        elif isinstance(n, ast.IfExp):
            yield n.test, "ifexp"
        elif isinstance(n, ast.comprehension):
            for c in n.ifs:
                yield c, "comp-if"
        elif isinstance(n, ast.Assert):
            yield n.test, "assert"


def scan(path: pathlib.Path):
    src = path.read_text()
    lines = src.splitlines()
    tree = ast.parse(src)
    numeric_names = collect_numeric_names(tree)
    hits = []
    seen = set()
    for node, ctx in truth_sites(tree):
        lbl = expr_label(node)
        if not lbl:
            continue
        if not (looks_numeric(lbl, numeric_names) or numeric_default_get(node)):
            continue
        key = (node.lineno, node.col_offset, lbl)
        if key in seen:
            continue
        seen.add(key)
        hits.append((node.lineno, ctx, lbl, lines[node.lineno - 1].strip()))
    return sorted(hits)


def main() -> int:
    print("=" * 78)
    print("CAL-P198 — falsy-zero sweep, four unswept calibration modules")
    print("root:", ROOT)
    print("=" * 78)

    print("\n### CONTROL: the two already-swept modules must re-surface their known hits\n")
    control_ok = True
    for path, known_line in CONTROLS:
        hits = scan(path)
        got = [h for h in hits if abs(h[0] - known_line) <= 4]
        mark = "PASS" if got else "FAIL"
        if not got:
            control_ok = False
        print(f"  {mark}  {path.name}: known falsy-zero near line {known_line} -> "
              f"{len(got)} hit(s) in window, {len(hits)} total in file")
        for ln, ctx, lbl, text in got:
            print(f"          L{ln} [{ctx}] {lbl}   {text}")

    total = 0
    for path in TARGETS:
        hits = scan(path)
        total += len(hits)
        print(f"\n### {path.relative_to(ROOT)}  —  {len(hits)} truth-tested numeric site(s)\n")
        for ln, ctx, lbl, text in hits:
            print(f"  L{ln:<5} [{ctx:<7}] {lbl}")
            print(f"          {text}")

    print("\n" + "=" * 78)
    print(f"TOTAL candidate sites across the four unswept modules: {total}")
    print("CONTROL:", "PASS" if control_ok else "FAIL — the detector does not "
          "reproduce a known hit, so a zero-yield sweep would be VACUOUS")
    print("=" * 78)
    return 0 if control_ok else 1


if __name__ == "__main__":
    sys.exit(main())
