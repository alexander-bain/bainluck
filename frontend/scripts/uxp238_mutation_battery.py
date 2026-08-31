#!/usr/bin/env python3
"""UX-P238 mutation battery — does the guard catch the defect class, or one card?

The ship: a futures card's hero must print the probability of the question its
title asks, not of whichever side is winning. Each mutant below is a plausible
way to get that wrong — including the four "fixed the lib, missed a call site"
shapes, which are the ones a lib-only test cannot see.

For every mutant we PROVE the edit applied (sha changed AND the mutant text is
on disk), run the guards, and require a non-zero exit. Sources are restored
inside `finally:` and the restore is verified byte-for-byte by sha256 —
UX-P210 stranded a mutant for want of exactly that.

This harness lives beside `uxp230_mutation_battery.py` and
`uxp237_mutation_battery.py` and carries its own residue check, because
`backend/scripts/evals/scan_mutation_residue.py` globs `*_mutations.py` under
`backend/scripts/evals/` and does not reach the frontend batteries.

Run from `frontend/`:  python3 scripts/uxp238_mutation_battery.py
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path

HERO = Path("lib/discover/heroOutcome.ts")
FUTURES_CARD = Path("components/discover/FuturesCard.tsx")
FEED_CARD = Path("components/FeedCard.tsx")
UTILS = Path("components/discover/utils.ts")

TARGETS = (HERO, FUTURES_CARD, FEED_CARD, UTILS)

TEST_PATTERN = (
    "heroAnswersQuestionP238|feedCardSumCapture|discoverHeroAgreementCapture"
)

# (id, file, find, replace, what it models)
MUTANTS: list[tuple[str, Path, str, str, str]] = [
    (
        "A",
        HERO,
        "  if (other.probability == null || !Number.isFinite(other.probability)) return served;\n  return other;",
        "  if (other.probability == null || !Number.isFinite(other.probability)) return served;\n  return served;",
        "the decision is computed and thrown away — the whole ship as a no-op",
    ),
    (
        "B",
        HERO,
        "if (!served || !outcomes || outcomes.length !== 2) return served;",
        "if (!served || !outcomes || outcomes.length < 2) return served;",
        "the arity guard loosened: a 3-way market led by the Fed's real "
        "'No change' row becomes re-headlinable",
    ),
    (
        "C",
        HERO,
        "  if (restatement.length < MIN_RESTATEMENT_CHARS) return false;\n  return restatement.startsWith(aff) || aff.startsWith(restatement);",
        "  if (restatement.length < MIN_RESTATEMENT_CHARS) return false;\n  return true;",
        "the pair test dropped for a bare prefix regex — the 'No change' "
        "false positive this file exists to prevent",
    ),
    (
        "D",
        HERO,
        "  if (other.probability == null || !Number.isFinite(other.probability)) return served;\n",
        "",
        "the unpriced-affirmative guard removed: a wrong hero traded for no "
        "hero at all",
    ),
    (
        "E",
        HERO,
        "const MIN_RESTATEMENT_CHARS = 4;",
        "const MIN_RESTATEMENT_CHARS = 40;",
        "the restatement bar set too high — real negations stop being read as "
        "negations",
    ),
    (
        "F",
        HERO,
        'return (name ?? "").replace(/\\s*(?:\\.{3}|…)\\s*$/, "").trim().toLowerCase();',
        'return (name ?? "").trim().toLowerCase();',
        "the ellipsis is not stripped, so a pair truncated at two different "
        "lengths stops matching — the Onslaught card silently reverts",
    ),
    (
        "G",
        HERO,
        "if (!other || !negates(served, other)) return served;",
        "if (!other || !negates(other, served)) return served;",
        "the negation asked in the wrong direction",
    ),
    (
        "H",
        FUTURES_CARD,
        "  const leader = heroOutcome(data.top_outcomes);\n  const prob = leader?.probability ?? null;",
        "  const leader = data.top_outcomes?.[0];\n  const prob = leader?.probability ?? null;",
        "the Discover card call site missed — the lib is right and the surface "
        "a reader looks at is not",
    ),
    (
        "I",
        FUTURES_CARD,
        "  const leader = heroOutcome(data.top_outcomes);\n  // UX-P162",
        "  const leader = data.top_outcomes?.[0];\n  // UX-P162",
        "the compact group/bundle row missed — the same market, one component "
        "sideways, with no outcome label to recover from",
    ),
    (
        "J",
        FEED_CARD,
        "  const leader = heroOutcome(data.top_outcomes);\n  const leaderProb = leader?.probability;",
        "  const leader = data.top_outcomes?.[0];\n  const leaderProb = leader?.probability;",
        "/categories, /sports and /my-stuff missed — the CERT-606 lesson, a "
        "second surface draws the same payload",
    ),
    (
        "K",
        UTILS,
        "const leaderProb = heroOutcome(data.top_outcomes)?.probability ?? null;",
        "const leaderProb = data.top_outcomes?.[0]?.probability ?? null;",
        "the sub-1% suppression left reading the served leader, so it waves "
        "through the bare '<1%' hero it was written to catch",
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
    originals = {p: p.read_text() for p in TARGETS}
    original_shas = {p: sha(p) for p in TARGETS}

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
                print(
                    f"{mid}: ANCHOR NOT UNIQUE in {path} "
                    f"({src.count(find)} hits) — battery invalid"
                )
                return 2
            mutated = src.replace(find, repl)
            assert mutated != src, f"{mid}: mutation is a no-op"
            path.write_text(mutated)
            # Prove it applied: the file on disk differs, and it differs the way
            # the mutant says. A no-op mutant that "survives" is a broken mutant,
            # not a finding about the guard.
            assert sha(path) != original_shas[path], f"{mid}: file unchanged on disk"
            assert find not in path.read_text(), f"{mid}: original text still present"

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
