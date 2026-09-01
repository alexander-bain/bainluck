#!/usr/bin/env python3
"""UX-P237 mutation battery — "the Discover card obeys the shape field".

This ship is a VETO, and a veto has two ways to be wrong:

  * firing too LITTLE — the wrong kernel comes back (A-C, F-H, J);
  * firing too MUCH  — the 43 cards that were already right get "fixed" into
    something worse, which passes a naive wrong-kernel test while breaking the
    majority of the feed (D, E).

Both directions are attacked. D and E matter most: they are the mutants a guard
written only around the two defective cards would never catch.

I is the clause that looks redundant and is not — the cumulative footer
suppression. Nothing about the ladder's *rungs* changes if it is removed; only a
sentence the ordering cannot support reappears.

For every mutant we PROVE the edit applied (sha256 changes) and require a
non-zero exit. Sources are restored inside `finally:` and verified byte-for-byte.

Run from `frontend/`:  python3 scripts/uxp237_mutation_battery.py
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path

SHAPE = Path("lib/marketShape.ts")
CARD = Path("components/discover/FuturesCard.tsx")
ROUTE = Path("components/DiscoverCard.tsx")

TEST_PATTERN = "discoverShapeDispatchP237"

MUTANTS: list[tuple[str, Path, str, str, str]] = [
    (
        "A",
        SHAPE,
        '  [SHAPE_QUANTITY]: new Set<MarketKernel>(["top-3"]),\n',
        "",
        "🔴 HALF THE SHIPPED DEFECT — a quantity market is rankable again, so the "
        "S&P date ladder goes back to being numbered 'Rank N by probability' and "
        "cropped to 4, losing Sep/Oct/Nov 2026",
    ),
    (
        "B",
        SHAPE,
        '  [SHAPE_FIELD]: new Set<MarketKernel>(["ladder-strip"]),\n',
        "",
        "🔴 THE OTHER HALF — eight independent All-In Podcast claims are drawn as a "
        "4-rung threshold ladder under 'Above 50% through <one of them>'",
    ),
    (
        "C",
        SHAPE,
        "  return SHAPE_FORBIDS_KERNEL[shape]?.has(kernel) ?? false;",
        "  return false;",
        "the table is built and never consulted — a vacuous veto. Kills A and B "
        "together, so it also proves no OTHER code path is silently doing this work",
    ),
    (
        "D",
        SHAPE,
        "  return SHAPE_FORBIDS_KERNEL[shape]?.has(kernel) ?? false;",
        "  return true;",
        "🔴 THE VETO FIRES TOO WIDELY — every shape forbids every kernel, so the 43 "
        "already-correct cards collapse to the generic hero. The survivor rows "
        "(McDonald's ladder, NYC precipitation bins) are what catch this",
    ),
    (
        "E",
        CARD,
        [
            (
                'import { shapeForbidsKernel, storedShape, SHAPE_QUANTITY, SHAPE_FIELD } from "@/lib/marketShape";',
                'import { shapeForbidsKernel, storedShape, resolveShapeFallback, SHAPE_QUANTITY, SHAPE_FIELD } from "@/lib/marketShape";',
            ),
            (
                '  const forbidsLadder = shapeForbidsKernel(data.market_type, "ladder-strip");',
                "  const forbidsLadder = shapeForbidsKernel(\n"
                "    data.market_type ??\n"
                "      resolveShapeFallback({ outcomeNames: data.top_outcomes?.map((o) => o.name) }),\n"
                '    "ladder-strip",\n'
                "  );",
            ),
        ],
        None,
        "🔴 THE HEURISTIC GETS A VOTE — the outcome-name fallback returns `field` "
        "for the All-In Podcast market (measured), so a market carrying NO stored "
        "shape has its ladder vetoed on the strength of the same kind of regex "
        "guess that produced the wrong format hint. ⚠️ RE-ANCHORED: the first "
        "version mutated `storedShape`, which receives no outcome names, so it was "
        "semantically a no-op and SURVIVED — a survivor for the wrong reason is not "
        "a finding, it is a broken mutant",
    ),
    (
        "F",
        CARD,
        "  const ladderFromDistribution = isQuantity && heatmapRows.length < 2;",
        "  const ladderFromDistribution = false;",
        "the quantity veto still fires but nothing feeds the ladder, so the card "
        "drops to the generic hero — a veto that leaves the reader worse off",
    ),
    (
        "G",
        CARD,
        '    (data.discover_card?.suggested_format === "outcome_distribution" || isField) &&',
        '    data.discover_card?.suggested_format === "outcome_distribution" &&',
        "the field veto kills the wrong ladder and nothing replaces it — all eight "
        "entrants vanish behind a single number. This is the exact regression the "
        "first draft shipped and the guard caught",
    ),
    (
        "H",
        ROUTE,
        " && !comparisonForbidden ? (",
        " ? (",
        "🔴 THE FIX ON A PATH THE READER DOES NOT TAKE (the CERT-606 / UX-P236-1 "
        "class) — FuturesCard is fully correct, but a quantity market with 4+ "
        "top_outcomes is handed to ComparisonCard before FuturesCard is ever "
        "reached, so the ladder never renders for it",
    ),
    (
        "I",
        CARD,
        "    const above50 = ladderFromDistribution\n      ? []\n      : shownCells.filter((r) => (r.probability ?? 0) >= 0.5);",
        "    const above50 = shownCells.filter((r) => (r.probability ?? 0) >= 0.5);",
        "🟢 THE CLAUSE THAT LOOKS REDUNDANT AND IS NOT — every rung still renders in "
        "the same order, so a rung-only guard would call this a survivor. What comes "
        "back is 'Above 50% through Before Dec 1, 2026', a cumulative claim about an "
        "ordering these valueless rungs do not have",
    ),
    (
        "J",
        CARD,
        "    ? distributionRows.slice(0, 8).map((row, index) => ({",
        "    ? distributionRows.slice(0, 4).map((row, index) => ({",
        "the ladder renders but re-crops to four rungs, so the three nearest date "
        "buckets are lost again — the kernel is right and the reader still cannot "
        "see the decision-relevant end",
    ),
]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_guards() -> int:
    proc = subprocess.run(
        ["npx", "jest", "--testPathPatterns", TEST_PATTERN],
        capture_output=True,
        text=True,
        env={**os.environ, "TZ": "UTC"},
    )
    return proc.returncode


def main() -> int:
    files = (SHAPE, CARD, ROUTE)
    originals = {p: p.read_text() for p in files}
    original_shas = {p: sha(p) for p in files}

    baseline = run_guards()
    if baseline != 0:
        print(f"BASELINE IS NOT GREEN (exit {baseline}) — battery is meaningless")
        return 2
    print("baseline: GREEN\n")

    killed, survived = [], []
    try:
        for mid, path, find, repl, why in MUTANTS:
            src = originals[path]
            # A mutant is one or more (find, repl) edits to a single file. Some
            # realistic mutations need two — E has to add an import as well as
            # change the call — and applying only half would leave a file that
            # does not compile, which reds for the wrong reason.
            edits = find if isinstance(find, list) else [(find, repl)]
            mutated = src
            for anchor, replacement in edits:
                hits = mutated.count(anchor)
                if hits != 1:
                    print(f"{mid}: ANCHOR NOT UNIQUE ({hits} hits) — battery invalid")
                    return 2
                mutated = mutated.replace(anchor, replacement)
            assert mutated != src, f"{mid}: mutation is a no-op"
            path.write_text(mutated)
            assert sha(path) != original_shas[path], f"{mid}: file unchanged on disk"

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
