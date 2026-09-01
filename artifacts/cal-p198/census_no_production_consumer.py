#!/usr/bin/env python3
"""CAL-P198 census — public members with no PRODUCTION consumer, on the three
calibration modules P197 did not reach.

Two widenings over P197's proof_1 §E, both deliberate:

  1. P197 scanned CLASS METHODS only (``ClassDef`` bodies). These three modules
     expose mostly MODULE-LEVEL functions, so a method-only scan would report a
     vacuous zero. This scans both.
  2. P197 scanned ``backend/app`` only, so "no consumer" meant "not referenced
     in production". That collapses two very different states. This separates
     them:
         ORPHAN        — no reference in app OR tests. Dead.
         TEST-ONLY     — referenced by tests, never by production code.
                         This is the P197-1 shape exactly: built, documented,
                         TESTED, and never wired to anything that runs.

CONTROL ARM: re-runs the widened census against the ledger module, where the
answer is known (exactly one orphan, ``failed_phase``). If the control does not
reproduce it, a zero-yield census on the three targets is vacuous.

Runs from any cwd; bootstraps the repo root itself. Exit 0 = control held.
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
    cand = pathlib.Path("/Users/bain/bainluck-dev/calibration")
    if (cand / "backend" / "app" / "utils" / "calibration_phase_ledger.py").exists():
        return cand
    raise SystemExit("FATAL: could not locate repo root")


ROOT = repo_root()
APP = ROOT / "backend" / "app"
TESTS = ROOT / "backend" / "tests"

LEDGER = APP / "utils" / "calibration_phase_ledger.py"
TARGETS = [
    APP / "utils" / "calibration_staged_futures.py",
    APP / "tasks" / "calibration_main_build.py",
    APP / "utils" / "calibration_staged_disclosure.py",
]

APP_FILES = sorted(APP.rglob("*.py"))
TEST_FILES = sorted(TESTS.rglob("*.py")) if TESTS.exists() else []


def public_members(tree: ast.AST) -> list[tuple[str, str, int, int]]:
    """(owner, name, start, end) for every public def — module level AND methods."""
    out: list[tuple[str, str, int, int]] = []
    for n in tree.body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and not n.name.startswith("_"):
            out.append(("<module>", n.name, n.lineno, n.end_lineno))
        elif isinstance(n, ast.ClassDef):
            for m in n.body:
                if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef)) and not m.name.startswith("_"):
                    out.append((n.name, m.name, m.lineno, m.end_lineno))
    return out


def refs(path: pathlib.Path, token: str, skip: tuple[int, int] | None = None) -> list[str]:
    pat = re.compile(r"\b" + re.escape(token) + r"\b")
    out = []
    try:
        lines = path.read_text(errors="ignore").splitlines()
    except OSError:
        return []
    for i, line in enumerate(lines, 1):
        if skip and skip[0] <= i <= skip[1]:
            continue
        if pat.search(line):
            out.append("%s:%d: %s" % (path.relative_to(ROOT), i, line.strip()[:110]))
    return out


def census(module: pathlib.Path):
    tree = ast.parse(module.read_text())
    members = public_members(tree)
    orphans, test_only = [], []
    for owner, name, s, e in members:
        cross = []
        for f in APP_FILES:
            if f == module:
                continue
            cross += refs(f, name)
        inmod = refs(module, name, skip=(s, e))
        if cross or inmod:
            continue
        tref = []
        for f in TEST_FILES:
            tref += refs(f, name)
        entry = (owner, name, s, tref)
        (test_only if tref else orphans).append(entry)
    return members, orphans, test_only


def report(module: pathlib.Path) -> tuple[int, int]:
    members, orphans, test_only = census(module)
    print("\n### %s" % module.relative_to(ROOT))
    print("    public members scanned (module-level defs + class methods): %d" % len(members))

    print("    ORPHAN (no reference in app OR tests): %d" % len(orphans))
    for owner, name, s, _ in orphans:
        print("        %s.%s   line %d" % (owner, name, s))

    print("    TEST-ONLY (tested, never referenced by production code): %d" % len(test_only))
    for owner, name, s, tref in test_only:
        print("        %s.%s   line %d   — %d test reference(s)" % (owner, name, s, len(tref)))
        for r in tref[:4]:
            print("            %s" % r)
    return len(orphans), len(test_only)


def main() -> int:
    print("=" * 78)
    print("CAL-P198 — no-production-consumer census, three modules P197 did not reach")
    print("root:", ROOT)
    print("app files scanned: %d   test files scanned: %d" % (len(APP_FILES), len(TEST_FILES)))
    print("=" * 78)

    print("\n" + "-" * 78)
    print("CONTROL — the widened census must still find P197's known orphan")
    print("-" * 78)
    _, c_orph, c_test = census(LEDGER)
    orph_names = [n for _, n, _, _ in c_orph]
    test_names = [n for _, n, _, _ in c_test]
    # P197 reported failed_phase as an "orphan" while scanning backend/app ONLY.
    # Under the finer split it is TEST-ONLY: its guard
    # (TestTheFailureLogNamesTheRightPhase) does reference it. Both buckets mean
    # "no production consumer", so the control is that it surfaces in EITHER --
    # landing in TEST-ONLY is the taxonomy working, not a regression.
    control_ok = "failed_phase" in orph_names or "failed_phase" in test_names
    print("  %s  P197's known finding still surfaces" % ("PASS" if control_ok else "FAIL"))
    print("        orphans   : %s" % (orph_names or "none"))
    print("        test-only : %s" % (test_names or "none"))
    if "failed_phase" in test_names:
        print("        NOTE: P197 called it an orphan (it scanned backend/app only).")
        print("              The finer split puts it in TEST-ONLY — tested, never wired.")
    if not control_ok:
        print("        FAIL => a zero-yield census on the targets would be VACUOUS")

    print("\n" + "-" * 78)
    print("TARGETS")
    print("-" * 78)
    to = so = 0
    for m in TARGETS:
        a, b = report(m)
        to += a
        so += b

    print("\n" + "=" * 78)
    print("TOTAL across the three targets — orphans: %d   test-only: %d" % (to, so))
    print("CONTROL:", "PASS" if control_ok else "FAIL")
    print("=" * 78)
    return 0 if control_ok else 1


if __name__ == "__main__":
    sys.exit(main())
