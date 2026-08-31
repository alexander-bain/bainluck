#!/usr/bin/env python3
"""UX-P230 mutation battery — does the guard actually catch the defect class?

Each mutant is a plausible way to get the futures "All Outcomes" ordering wrong.
For every one we PROVE the edit applied (the source really changed), run the two
guard files, and require a non-zero exit. Sources are restored inside `finally:`
and the restore is verified byte-for-byte by sha256 — UX-P210 stranded a mutant
for want of exactly that.

Run from `frontend/`:  python3 scripts/uxp230_mutation_battery.py
"""

from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

LIB = Path("lib/futuresDetailDisplay.ts")
PAGE = Path("app/futures/[id]/page.tsx")

TEST_PATTERN = "futuresOutcomeSort|futuresDetailOutcomeOrder"

# (id, file, find, replace, what it models)
MUTANTS: list[tuple[str, Path, str, str, str]] = [
    (
        "A",
        LIB,
        "comparison = (a.probability ?? 0) - (b.probability ?? 0);",
        "comparison = (b.probability ?? 0) - (a.probability ?? 0);",
        "the shipped bytes: probability comparator authored in reverse",
    ),
    (
        "B",
        LIB,
        "comparison = aChange - bChange;",
        "comparison = bChange - aChange;",
        "the shipped bytes: change comparator authored in reverse",
    ),
    (
        "C",
        LIB,
        "return direction === \"asc\" ? comparison : -comparison;",
        "return direction === \"asc\" ? -comparison : comparison;",
        "the tempting one-line 'fix' at the inverter: corrects probability and "
        "change, silently reverses name",
    ),
    (
        "D",
        LIB,
        "comparison = a.name.localeCompare(b.name);",
        "comparison = b.name.localeCompare(a.name);",
        "name comparator flipped — A-Z becomes Z-A",
    ),
    (
        "E",
        LIB,
        "comparison = aChange - bChange;",
        "comparison = Math.abs(aChange) - Math.abs(bChange);",
        "change sorted by MAGNITUDE, so the biggest loser reads as the top mover",
    ),
    (
        "F",
        LIB,
        "comparison = (a.probability ?? 0) - (b.probability ?? 0);",
        "comparison = (a.probability ?? 1) - (b.probability ?? 1);",
        "an unpriced outcome treated as certainty and floated to the top",
    ),
    (
        "G",
        LIB,
        "return [...outcomes].sort((a, b) => {",
        "return (outcomes as T[]).sort((a, b) => {",
        "sorting in place — the caller's array is mutated under it",
    ),
    (
        "H",
        LIB,
        "const bChange = b.probability_change_24h ?? 0;",
        "const bChange = b.probability_change_24h ?? -1;",
        "a null change read as a loss rather than as no move",
    ),
    (
        "I",
        PAGE,
        "return sortFuturesOutcomes(market.outcomes, sortField, sortDirection);",
        "return sortFuturesOutcomes(market.outcomes, sortField, \"asc\");",
        "the page ignores its own direction state and always ascends",
    ),
    (
        "J",
        PAGE,
        "return sortFuturesOutcomes(market.outcomes, sortField, sortDirection);",
        "return [...market.outcomes];",
        "the page drops the sort entirely and trusts the payload's arrival order "
        "(passes on production data, which arrives sorted — the vacuity the "
        "shuffled-payload test exists to kill)",
    ),
    (
        "K",
        PAGE,
        "data-outcome-name={outcome.name}",
        "data-outcome-name=\"\"",
        "the render hook goes blank — the guard must not read an empty row list "
        "as agreement",
    ),
    (
        "L",
        PAGE,
        "const [sortDirection, setSortDirection] = useState<SortDirection>(\"desc\");",
        "const [sortDirection, setSortDirection] = useState<SortDirection>(\"asc\");",
        "the page's default direction flipped — same rendered defect, different "
        "cause",
    ),
]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_guards() -> int:
    proc = subprocess.run(
        ["npx", "jest", "--testPathPatterns", TEST_PATTERN],
        capture_output=True,
        text=True,
        env={**__import__("os").environ, "TZ": "UTC"},
    )
    return proc.returncode


def main() -> int:
    originals = {p: p.read_text() for p in (LIB, PAGE)}
    original_shas = {p: sha(p) for p in (LIB, PAGE)}

    baseline = run_guards()
    if baseline != 0:
        print(f"BASELINE IS NOT GREEN (exit {baseline}) — battery is meaningless")
        return 2
    print("baseline: GREEN\n")

    killed, survived = [], []
    try:
        for mid, path, find, repl, why in MUTANTS:
            src = originals[path]
            if src.count(find) != 1:
                print(f"{mid}: ANCHOR NOT UNIQUE ({src.count(find)} hits) — battery invalid")
                return 2
            mutated = src.replace(find, repl)
            assert mutated != src, f"{mid}: mutation is a no-op"
            path.write_text(mutated)
            # Prove it applied: the file on disk differs and contains the mutant text.
            assert sha(path) != original_shas[path], f"{mid}: file unchanged on disk"
            assert repl in path.read_text(), f"{mid}: mutant text absent after write"

            code = run_guards()
            path.write_text(src)
            assert sha(path) == original_shas[path], f"{mid}: restore not byte-identical"

            if code != 0:
                killed.append(mid)
                print(f"{mid}: KILLED (exit {code}) — {why}")
            else:
                survived.append(mid)
                print(f"{mid}: *** SURVIVED *** — {why}")
    finally:
        for path, src in originals.items():
            path.write_text(src)
            assert sha(path) == original_shas[path], f"RESIDUE: {path} not restored"
        print("\nall sources restored, sha256 verified")

    print(f"\n{len(killed)}/{len(MUTANTS)} killed")
    if survived:
        print(f"SURVIVORS: {', '.join(survived)}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
