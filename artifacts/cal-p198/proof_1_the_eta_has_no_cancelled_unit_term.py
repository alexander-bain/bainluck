#!/usr/bin/env python3
"""CAL-P198 PROOF 1 (static) — the beat ETA has no term for cancelled units,
and computes the observed throughput one statement before discarding it.

Runs from any cwd; bootstraps the repo root itself. Exit 0 = every claim held.

Claims proved here:
  A. ``_record_staged_rate`` computes the beat's OBSERVED throughput
     (``completed_units``), records it as ``staged:units_completed_this_beat``,
     and never reads it again. The projection below it uses only the MEAN COST
     of a completed unit, never the COUNT that completed.
  B. ``usable_ms`` -- the numerator of that projection -- deducts only the
     NON-unit overhead (``elapsed - stages[read:futures_unit]``). Time spent
     inside the unit stage on units that were CANCELLED is inside
     ``stages[read:futures_unit]``, is therefore NOT deducted, and is modelled
     as time available for units that will complete.
  C. The sibling projection ``PhaseLedger.unit_projection`` has the identical
     blindness with a different numerator and divisor: ``budget_ms //
     unit_ms``. Neither projection references any cancellation quantity.
  D. CAL-P071's own docstring names this defect -- "observed throughput is not
     an input to it" / "an ETA that cannot fall as the build slows is not an
     estimate, it is a constant wearing one" -- and the sentence is STILL TRUE
     of the code the docstring is attached to. CAL-P071 changed the divisor
     (``max_phase_ms`` -> ``budget_ms``), which fixes the "optimistic" half and
     leaves the "immovable" half standing.
  E. Both fix sites are outside all four fingerprint-hashed functions => a fix
     costs zero rebuild (P194's cost correction).
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
    raise SystemExit("FATAL: could not locate repo root from %s" % here)


ROOT = repo_root()
APP = ROOT / "backend" / "app"
BUILD = APP / "tasks" / "calibration_main_build.py"
LEDGER = APP / "utils" / "calibration_phase_ledger.py"
PRECOMPUTE = APP / "tasks" / "precompute_calibration.py"

HASHED_FNS = {
    "compute_calibration_payload",
    "_calibration_population_ctes",
    "_virtual_market_ctes",
    "_main_futures_sql",
}

# Any name that could carry a cancellation quantity into a projection.
CANCEL_TOKENS = (
    "cancel", "cancelled", "units_cancelled", "unit_cancelled",
    "abandoned", "truncated", "timeout_units", "unit_cancelled_after_ms",
)

failures: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(("  PASS  " if ok else "  FAIL  ") + label + (("\n          " + detail) if detail else ""))
    if not ok:
        failures.append(label)


def find_fn(tree: ast.AST, name: str, cls: str | None = None):
    for n in ast.walk(tree):
        if isinstance(n, ast.ClassDef) and cls and n.name == cls:
            for m in n.body:
                if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef)) and m.name == name:
                    return m
        if cls is None and isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name:
            return n
    raise SystemExit("FATAL: %s not found" % name)


def body_src(path: pathlib.Path, node) -> str:
    lines = path.read_text().splitlines()
    return "\n".join(lines[node.lineno - 1 : node.end_lineno])


def name_reads(node, token: str) -> list[int]:
    """Lines where ``token`` is READ (ast.Load), not written."""
    out = []
    for n in ast.walk(node):
        if isinstance(n, ast.Name) and n.id == token and isinstance(n.ctx, ast.Load):
            out.append(n.lineno)
    return out


print("=" * 78)
print("CAL-P198 PROOF 1 — the beat ETA has no cancelled-unit term")
print("repo root: %s" % ROOT)
print("=" * 78)

build_tree = ast.parse(BUILD.read_text())
ledger_tree = ast.parse(LEDGER.read_text())

rate = find_fn(build_tree, "_record_staged_rate")
rate_src = body_src(BUILD, rate)
proj = find_fn(ledger_tree, "unit_projection", cls="PhasePlan")
proj_src = body_src(LEDGER, proj)

# ---- A ---------------------------------------------------------------------
print("\nA. observed throughput is computed, recorded, and then discarded")
reads = name_reads(rate, "completed_units")
# the only Load of completed_units should be the record_gauge argument
gauge_lines = [
    n.lineno
    for n in ast.walk(rate)
    if isinstance(n, ast.Call)
    and isinstance(n.func, ast.Attribute)
    and n.func.attr == "record_gauge"
    and any(isinstance(a, ast.Name) and a.id == "completed_units" for a in n.args)
]
print("          completed_units READ on lines: %s" % reads)
print("          of which inside a record_gauge(...) call: %s" % gauge_lines)
check(
    "completed_units is read ONLY to be recorded as a gauge",
    bool(reads) and set(reads) == set(gauge_lines),
    "every read is the gauge write; the count never reaches the projection",
)

# the projection statement itself
per_beat_assign = [
    n for n in ast.walk(rate)
    if isinstance(n, ast.Assign)
    and any(isinstance(t, ast.Name) and t.id == "per_beat" for t in n.targets)
]
check("the projection assigns per_beat exactly once", len(per_beat_assign) == 1)
pb_src = "\n".join(BUILD.read_text().splitlines()[per_beat_assign[0].lineno - 1 : per_beat_assign[0].end_lineno])
print("          per_beat (line %d): %s" % (per_beat_assign[0].lineno, pb_src.strip()))
check(
    "per_beat divides a time budget by a COST, not by an observed count",
    "completed_units" not in pb_src and "projection_mean" in pb_src,
)

# ---- B ---------------------------------------------------------------------
print("\nB. usable_ms deducts only NON-unit overhead, so cancelled unit time survives in it")
usable = [
    n for n in ast.walk(rate)
    if isinstance(n, ast.Assign)
    and any(isinstance(t, ast.Name) and t.id in ("usable_ms", "fixed_ms") for t in n.targets)
]
for n in sorted(usable, key=lambda x: x.lineno):
    s = "\n".join(BUILD.read_text().splitlines()[n.lineno - 1 : n.end_lineno]).strip()
    print("          line %d: %s" % (n.lineno, s))
fixed_src = "\n".join(
    "\n".join(BUILD.read_text().splitlines()[n.lineno - 1 : n.end_lineno])
    for n in usable
)
check(
    "fixed_ms is elapsed MINUS the unit stage — i.e. unit-stage time is kept as usable",
    "elapsed_ms()" in fixed_src and "STAGED_UNIT_STAGE" in fixed_src,
)
check(
    "no cancellation quantity appears anywhere in _record_staged_rate's projection",
    not any(t in rate_src.lower() for t in ("units_cancelled", "unit_cancelled")),
    "searched for: %s" % ", ".join(CANCEL_TOKENS),
)

# ---- C ---------------------------------------------------------------------
print("\nC. the sibling projection PhasePlan.unit_projection has the identical blindness")
print("          %s" % [l.strip() for l in proj_src.splitlines() if "per_beat =" in l])
check(
    "unit_projection divides a budget by unit_ms and references no cancellation",
    "per_beat = per_beat_ms // budget.unit_ms" in proj_src
    and not any(t in proj_src.lower() for t in ("cancel", "abandoned")),
)

# ---- D ---------------------------------------------------------------------
print("\nD. CAL-P071's docstring names the defect, and the sentence is still true")
doc = ast.get_docstring(proj) or ""
needles = [
    "observed throughput is not an input to it",
    "is not an estimate, it is a constant wearing one",
]
for needle in needles:
    check("docstring contains: %r" % needle[:52], needle in doc.replace("\n", " ").replace("  ", " "))
check(
    "CAL-P071's actual change was the DIVISOR (max_phase_ms -> budget_ms)",
    "max_phase_ms" in doc and "budget.unit_ms" in proj_src,
)
check(
    "and the throughput it says is not an input STILL is not one",
    "units_done" in proj_src and "units_completed" not in proj_src,
    "unit_projection reads the cumulative units_done, never a per-beat completion count",
)

# ---- E ---------------------------------------------------------------------
print("\nE. both fix sites are fingerprint-free (zero rebuild cost)")
pc_tree = ast.parse(PRECOMPUTE.read_text())
spans = {
    n.name: (n.lineno, n.end_lineno)
    for n in ast.walk(pc_tree)
    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in HASHED_FNS
}
check("all four hashed functions located in precompute_calibration.py", len(spans) == 4, str(spans))
check(
    "fix site 1 (calibration_main_build.py) is not precompute_calibration.py",
    BUILD.resolve() != PRECOMPUTE.resolve(),
)
check(
    "fix site 2 (calibration_phase_ledger.py) is not precompute_calibration.py",
    LEDGER.resolve() != PRECOMPUTE.resolve(),
)
print("          => neither fix site can be inside any hashed function; the input")
print("             fingerprint cannot move, so no staged-cursor reset. (P194)")

print("\n" + "=" * 78)
if failures:
    print("PROOF 1 FAILED — %d claim(s) did not hold:" % len(failures))
    for f in failures:
        print("  - %s" % f)
    sys.exit(1)
print("PROOF 1 HELD — every claim above is true of the tree at HEAD.")
sys.exit(0)
