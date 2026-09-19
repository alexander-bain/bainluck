#!/usr/bin/env python3
"""ux/1357 — mutation battery for #7211 (carry the score forward).

A survivor is a claim about the test. An unverified restore is a claim about the
whole tree, and nobody reads that one — ux/1356's battery silently deleted an
argument from unrelated code 26 lines from its target because it did
`replace(old, new, 1)` on a pattern it never proved unique, then reported two
false SURVIVORS and froze the damage into its own backup.

So this one:
  * refuses any pattern that does not appear EXACTLY once (exit 8, never guess);
  * snapshots every target file at startup and verifies byte-for-byte on exit,
    failing loudly if the tree it hands back is not the tree it was given.
"""
from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FE = ROOT / "frontend"
CHART = FE / "components" / "ScoreDifferentialChart.tsx"
TIMELINE = FE / "lib" / "chartTimeline.ts"
PATTERN = "7211"

# (name, file, find, replace, the test that must go red)
MUTANTS = [
    (
        "carry-removed — the shipped defect, put back",
        CHART,
        '    carryForward(points, "actualDiff");',
        "    // carryForward(points, \"actualDiff\");",
        'Expected: "true"',
    ),
    (
        "carry-runs-backward — fills the pre-game domain",
        TIMELINE,
        "  for (const point of points) {",
        "  for (const point of [...points].reverse()) {",
        "never back-filled",
    ),
    (
        "truthy-test — a 0-0 draw read as an absence",
        TIMELINE,
        '    if (typeof value === "number" && Number.isFinite(value)) {',
        "    if (value) {",
        "0 is a score",
    ),
    (
        "finite-check-dropped — NaN carried as a reading",
        TIMELINE,
        '    if (typeof value === "number" && Number.isFinite(value)) {',
        '    if (typeof value === "number") {',
        "NaN is not a reading",
    ),
    (
        "assign-before-test — every reading flattened to the first",
        TIMELINE,
        '    const value = point[key];',
        '    const value = last === null ? point[key] : last;',
        "never overwritten",
    ),
    (
        "tail-hardcoded-0 — the measurement stops measuring",
        CHART,
        "      lastReading < 0 ? 0 : points.length - 1 - lastReading;",
        "      0;",
        "carried past the goal",
    ),
    (
        "tail-counts-total — the constant that fooled the first battery",
        CHART,
        "      lastReading < 0 ? 0 : points.length - 1 - lastReading;",
        "      lastReading < 0 ? 0 : points.length - 2;",
        "carried past the goal",
    ),
    # KNOWN EQUIVALENT — kept in the list on purpose, not removed to make the
    # tally look better. Once the carry ships, the last point ALWAYS carries a
    # number, so `true` and the real test agree in every reachable state and no
    # assertion can separate them. It is an equivalent mutant, not a hole in the
    # guard: the thing this attribute exists to catch is the carry being DELETED
    # (mutant 1), and that one dies on it. A survivor can mean unreachable.
    (
        "reaches-edge-hardcoded — EQUIVALENT, see note",
        CHART,
        "        : typeof points[points.length - 1]?.actualDiff === \"number\";",
        "        : true;",
        "n/a",
    ),
    (
        "step-to-linear — a goal smoothed into a 50-minute drift",
        CHART,
        '                type="stepAfter"\n                dataKey="actualDiff"',
        '                type="linear"\n                dataKey="actualDiff"',
        "still a step",
    ),
]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_band() -> tuple[bool, str]:
    proc = subprocess.run(
        ["npx", "jest", f"--testPathPatterns={PATTERN}"],
        cwd=FE, capture_output=True, text=True,
    )
    return proc.returncode == 0, proc.stdout + proc.stderr


def main() -> int:
    targets = {CHART, TIMELINE}
    original = {p: p.read_text() for p in targets}
    start = {p: digest(p) for p in targets}

    ok, out = run_band()
    if not ok:
        print("BASELINE IS RED — fix that before reading any verdict below.")
        print(out[-2500:])
        return 2
    print("baseline GREEN\n")

    killed, survived = 0, []
    try:
        for name, path, find, repl, expect in MUTANTS:
            src = original[path]
            hits = src.count(find)
            if hits != 1:
                print(f"REFUSED  {name}: pattern appears {hits}x, must be exactly 1")
                return 8
            path.write_text(src.replace(find, repl, 1))
            # Every OTHER target must be byte-identical while this one is mutated.
            for other in targets - {path}:
                if digest(other) != start[other]:
                    print(f"ABORT: {other.name} changed while mutating {path.name}")
                    return 9
            ok, out = run_band()
            path.write_text(src)
            if ok:
                survived.append(name)
                print(f"SURVIVED {name}")
            else:
                killed += 1
                hit = expect.lower() in out.lower()
                print(f"killed   {name}" + ("" if hit else f"  [!] not via '{expect}'"))
    finally:
        for p, text in original.items():
            p.write_text(text)
        bad = [p.name for p in targets if digest(p) != start[p]]
        if bad:
            print(f"\n*** RESTORE FAILED for {bad} — the tree is NOT as you left it ***")
            return 9
        print("\nrestore verified byte-for-byte")

    print(f"\n{killed}/{len(MUTANTS)} killed")
    if survived:
        print("SURVIVORS (read the diff, not the tally):")
        for s in survived:
            print("  -", s)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
