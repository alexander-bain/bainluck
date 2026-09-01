#!/usr/bin/env python3
"""CAL-P197 PROOF 1 (static) — CAL-P109's fix was never wired to the line it fixed.

Runs from any cwd; bootstraps the repo root itself. Exit 0 = every claim held.

Claims proved here:
  A. ``PhaseLedger.failed_phase`` has ZERO references anywhere in ``backend/app``
     other than its own def-to-end span. Not in another module, not in its own
     module, not in a payload.
  B. The one log line CAL-P109 was written to fix still prints
     ``completed_required`` under the label "in phase group".
  C. That log line is NOT inside any of the four functions the input
     fingerprint hashes -> a fix costs zero rebuild (P194's cost correction).
  D. The guard class ``TestTheFailureLogNamesTheRightPhase`` asserts on the
     ledger accessor only; it never references the logging call site.
  E. Of every public member of the ledger module, ``failed_phase`` is the ONLY
     one with no consumer at all -- the other five with no cross-module reader
     are consumed in-module (as_payload or a sibling predicate).
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
TESTS = ROOT / "backend" / "tests"
LEDGER = APP / "utils" / "calibration_phase_ledger.py"
BUILD = APP / "tasks" / "precompute_calibration.py"
GUARD = TESTS / "test_calibration_elastic_budget_p109.py"

HASHED_FNS = {
    "compute_calibration_payload",
    "_calibration_population_ctes",
    "_virtual_market_ctes",
    "_main_futures_sql",
}

failures: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(("  PASS  " if ok else "  FAIL  ") + label + (("\n          " + detail) if detail else ""))
    if not ok:
        failures.append(label)


def member_span(tree: ast.AST, name: str) -> tuple[int, int]:
    for cls in [n for n in tree.body if isinstance(n, ast.ClassDef)]:
        for n in cls.body:
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name:
                return n.lineno, n.end_lineno
    raise SystemExit("FATAL: %s not found" % name)


def refs(path: pathlib.Path, token: str, skip: tuple[int, int] | None = None) -> list[str]:
    pat = re.compile(r"\b" + re.escape(token) + r"\b")
    out = []
    for i, line in enumerate(path.read_text(errors="ignore").splitlines(), 1):
        if skip and skip[0] <= i <= skip[1]:
            continue
        if pat.search(line):
            out.append("%s:%d: %s" % (path.relative_to(ROOT), i, line.strip()[:100]))
    return out


print("CAL-P197 PROOF 1 — failed_phase is defined, documented, tested, and never read")
print("repo root: %s\n" % ROOT)

ledger_tree = ast.parse(LEDGER.read_text())
span = member_span(ledger_tree, "failed_phase")

# ---- A ---------------------------------------------------------------------
print("A. zero references in backend/app outside its own body")
app_refs: list[str] = []
for f in sorted(APP.rglob("*.py")):
    app_refs += refs(f, "failed_phase", skip=span if f == LEDGER else None)
check(
    "failed_phase has no reader anywhere in backend/app (def span %d-%d excluded)" % span,
    not app_refs,
    "unexpected refs:\n          " + "\n          ".join(app_refs) if app_refs else "",
)

# ---- B ---------------------------------------------------------------------
print("\nB. the CAL-P109 log line still prints completed_required")
build_src = BUILD.read_text()
build_lines = build_src.splitlines()
log_idx = [i for i, l in enumerate(build_lines, 1) if "in phase group" in l]
check("exactly one 'in phase group' log line exists", len(log_idx) == 1, "found at %s" % log_idx)
if len(log_idx) == 1:
    ln = log_idx[0]
    window = "\n".join(build_lines[ln - 1 : ln + 2])
    print("          %s:%d\n          %s" % (BUILD.relative_to(ROOT), ln, window.replace("\n", "\n          ")))
    check("its argument is completed_required", "completed_required" in window)
    check("its argument is NOT failed_phase", "failed_phase" not in window)

# ---- C ---------------------------------------------------------------------
print("\nC. the fix site is outside every hashed function (zero rebuild cost)")
build_tree = ast.parse(build_src)
target = log_idx[0]
enclosing = None
for n in ast.walk(build_tree):
    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.lineno <= target <= n.end_lineno:
        if enclosing is None or n.lineno > enclosing.lineno:
            enclosing = n
check("log line is inside a function", enclosing is not None)
if enclosing:
    print("          enclosing function: %s (%d-%d)" % (enclosing.name, enclosing.lineno, enclosing.end_lineno))
    check("enclosing function is not one of the 4 hashed functions", enclosing.name not in HASHED_FNS)
for h in sorted(HASHED_FNS):
    hits = [n for n in ast.walk(build_tree)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == h]
    check("hashed %s does not contain the log line" % h,
          all(not (n.lineno <= target <= n.end_lineno) for n in hits))

# ---- D ---------------------------------------------------------------------
print("\nD. the guard named for the log line never touches the log line")
guard_src = GUARD.read_text()
check("guard class TestTheFailureLogNamesTheRightPhase exists",
      "class TestTheFailureLogNamesTheRightPhase" in guard_src)
check("guard asserts on ledger.failed_phase", "ledger.failed_phase" in guard_src)
check("guard never references the logger call site ('in phase group')",
      "in phase group" not in guard_src.split("class TestTheFailureLogNamesTheRightPhase")[1])
check("guard never imports or patches the build module's logger",
      "caplog" not in guard_src and "precompute_calibration" not in guard_src)

# ---- E ---------------------------------------------------------------------
print("\nE. failed_phase is the ONLY member of the module with no consumer at all")
public: list[tuple[str, str, int, int]] = []
for cls in [n for n in ledger_tree.body if isinstance(n, ast.ClassDef)]:
    for n in cls.body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and not n.name.startswith("_"):
            public.append((cls.name, n.name, n.lineno, n.end_lineno))

orphans = []
for cls_name, name, s, e in public:
    cross = []
    for f in sorted(APP.rglob("*.py")):
        if f == LEDGER:
            continue
        cross += refs(f, name)
    inmod = refs(LEDGER, name, skip=(s, e))
    if not cross and not inmod:
        orphans.append("%s.%s (line %d)" % (cls_name, name, s))

print("          members scanned: %d" % len(public))
print("          members with no consumer anywhere: %s" % (orphans or "none"))
check("exactly one member has no consumer anywhere", len(orphans) == 1, "got: %s" % orphans)
check("that member is PhaseLedger.failed_phase",
      len(orphans) == 1 and orphans[0].startswith("PhaseLedger.failed_phase"))

# ---- verdict ---------------------------------------------------------------
print("\n" + "=" * 78)
if failures:
    print("PROOF 1 FAILED — %d claim(s) did not hold:" % len(failures))
    for f in failures:
        print("  - %s" % f)
    sys.exit(1)
print("PROOF 1 HELD — every claim above is true of the tree at HEAD.")
sys.exit(0)
