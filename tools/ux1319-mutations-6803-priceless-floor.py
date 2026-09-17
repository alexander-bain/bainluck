#!/usr/bin/env python3
"""#6803 mutation battery — does the guard suite actually hold the rule?

A green bar on a fixed tree proves nothing. Each mutant below breaks the rule in
one specific way and must be CAUGHT by a named clause. A SURVIVOR is a hole.

COMMIT BEFORE RUNNING. Restores by writing the original bytes back, never by
`git checkout --` (which would take the whole worktree with it).

    python3 tools/ux1319-mutations-6803-priceless-floor.py
"""
from __future__ import annotations

import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
FE = ROOT / "frontend"
LIB = FE / "lib" / "futuresCardPriceAge.ts"
TEST = FE / "__tests__" / "futuresCardPricelessRowFloor6803.test.ts"
FIXTURE = FE / "__tests__" / "fixtures" / "futures114175PricelessTail6803.json"

# (name, file, find, replace, why it must be caught)
MUTANTS = [
    (
        "rule-removed: the pre-#6803 walk, priceless rows vote again",
        LIB,
        "    if (!showsAPrice(row)) continue;\n",
        "",
        "the original defect — specimen must date to May 12 again",
    ),
    (
        "rule-inverted: only PRICELESS rows vote",
        LIB,
        "    if (!showsAPrice(row)) continue;",
        "    if (showsAPrice(row)) continue;",
        "specimen would wear the tail's date and nothing else",
    ),
    (
        "predicate-truthy: `!!probability` drops every 0% rung",
        LIB,
        "  return row?.probability != null;",
        "  return !!row?.probability;",
        "the seam — `0` is a price; only the 0%-keeps-its-vote clause sees this",
    ),
    (
        "predicate-strict-null: `!== null` misses an ABSENT key",
        LIB,
        "  return row?.probability != null;",
        "  return row?.probability !== null;",
        "only the absent-probability-key clause sees this",
    ),
    (
        "predicate-always-true: every row votes",
        LIB,
        "  return row?.probability != null;",
        "  return true;",
        "same reader-visible effect as rule-removed",
    ),
    (
        "predicate-always-false: no row votes, card always withholds",
        LIB,
        "  return row?.probability != null;",
        "  return false;",
        "specimen must not collapse to null — a card with prices has an age",
    ),
    (
        "floor-to-ceiling: newest instead of oldest",
        LIB,
        "    if (oldest === null || ms < oldest) oldest = ms;",
        "    if (oldest === null || ms > oldest) oldest = ms;",
        "#6018's flattering half — the 0%-keeps-its-vote clause is the one that holds it",
    ),
    (
        "served-shortcut-dropped: client re-derives what the server scoped",
        LIB,
        "  if (served !== null) return market.prices_updated_at as string;",
        "  if (false) return market.prices_updated_at as string;",
        "the prefers-the-server clause",
    ),
    (
        "fixture-doctored: a priceless rung made NEWER than the priced ones",
        FIXTURE,
        '"last_updated": "2026-05-12T16:16:06.970740+00:00"',
        '"last_updated": "2026-09-18T00:00:00.000000+00:00"',
        "the non-vacuity clause must refuse a fixture that cannot show the defect",
    ),
]

# Deliberate controls: these MUST survive. A control that dies means the suite is
# resting on a line that only reads like an assertion.
CONTROLS = [
    (
        "control: `not.toBe(PRICELESS_TAIL)` neutered on the ship clause",
        TEST,
        '    expect(asOf).not.toBe(PRICELESS_TAIL);',
        '    expect(asOf).not.toBe("nonsense");',
        "that line states the ship for a reader; `toBe(PRICED_FLOOR)` above it is "
        "what holds the rule, and this proves the rule does not depend on the prose",
    ),
]


def run_suite() -> tuple[bool, str]:
    p = subprocess.run(
        ["npx", "jest", "--testPathPatterns=futuresCardPrice"],
        cwd=FE, capture_output=True, text=True,
    )
    return p.returncode == 0, (p.stdout + p.stderr)


def caught_clauses(output: str) -> list[str]:
    """Jest names each failure on a `● <describe> › <clause>` line."""
    names = []
    for line in output.splitlines():
        s = line.strip()
        if s.startswith("●") and "›" in s:
            clause = s.split("›")[-1].strip()
            if clause and clause not in names:
                names.append(clause)
    return names


def main() -> int:
    ok, out = run_suite()
    if not ok:
        print("BASELINE IS RED — fix the tree before mutating.")
        print(out[-3000:])
        return 2
    print("baseline: GREEN\n")

    survivors = []
    signatures = set()
    bad_controls = []
    for name, path, find, repl, why in MUTANTS + CONTROLS:
        is_control = (name, path, find, repl, why) in CONTROLS
        original = path.read_text()
        if find not in original:
            print(f"🔴 ANCHOR NOT FOUND — {name}\n     looked for: {find!r}")
            survivors.append(name + " (anchor missing)")
            continue
        path.write_text(original.replace(find, repl, 1))
        print(f"applied   {name}")
        try:
            passed, output = run_suite()
        finally:
            path.write_text(original)
            print(f"restored  {name}")
        clauses = caught_clauses(output)
        if is_control:
            if passed:
                print(f"   ✅ survived as designed — {why}\n")
            else:
                print(f"   🔴 CONTROL DIED — caught by: {'; '.join(clauses)}\n")
                bad_controls.append(name)
            continue
        if passed:
            print(f"   🔴 SURVIVED — {why}\n")
            survivors.append(name)
        else:
            signatures.add(tuple(sorted(clauses)))
            shown = "; ".join(clauses) or "(suite red, clause unparsed)"
            print(f"   ✅ caught by: {shown}\n")

    print("=" * 72)
    print(f"{len(MUTANTS) - len(survivors)}/{len(MUTANTS)} mutants caught, "
          f"{len(signatures)} distinct failure signatures; "
          f"{len(CONTROLS) - len(bad_controls)}/{len(CONTROLS)} controls survived as designed")
    if survivors or bad_controls:
        for s in survivors:
            print("  SURVIVOR (a hole in the guard):", s)
        for s in bad_controls:
            print("  CONTROL DIED (the suite rests on prose):", s)
        return 1
    ok, _ = run_suite()
    print("tree restored and GREEN" if ok else "🔴 TREE NOT RESTORED")
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
