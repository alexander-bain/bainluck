#!/usr/bin/env python3
"""UX-P232 mutation battery — CERT-598's block: the settled table's winner-first rule.

Each mutant is a plausible way to get the SETTLED ordering wrong, including the
blocked bytes themselves (mutant A) and the two over-corrections that would trade
this bug for a different one (D, E). For every mutant we PROVE the edit applied
(the file on disk really changed and contains the mutant text), run the guards, and
require a non-zero exit. Sources are restored inside `finally:` and the restore is
verified byte-for-byte by sha256.

Run from `frontend/`:  python3 scripts/uxp232_mutation_battery.py
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path

LIB = Path("lib/futuresDetailDisplay.ts")
PAGE = Path("app/futures/[id]/page.tsx")

# The settled guards PLUS UX-P230's open-market pair: a repair that fixed the
# settled order by breaking the live one must not read as a pass.
TEST_PATTERN = "futuresSettledOutcome|futuresOutcomeSort|futuresDetailOutcomeOrder"

WINNER_KEY = (
    "      comparison =\n"
    "        (a.is_winner === true ? 1 : 0) - (b.is_winner === true ? 1 : 0);"
)

PAGE_CALL = (
    "    return sortFuturesOutcomes(\n"
    "      market.outcomes,\n"
    "      sortField,\n"
    "      sortDirection,\n"
    '      market.status === "resolved",\n'
    "    );"
)

# (id, file, find, replace, what it models)
MUTANTS: list[tuple[str, Path, str, str, str]] = [
    (
        "A",
        LIB,
        'const winnerLeads = resolved && field === "probability" && direction === "desc";',
        "const winnerLeads = false;",
        "THE BLOCKED BYTES — the comparator cannot see is_winner at all, so a "
        "settled page leads with the frozen price leader (CERT-598's finding)",
    ),
    (
        "B",
        PAGE,
        PAGE_CALL,
        "    return sortFuturesOutcomes(market.outcomes, sortField, sortDirection);",
        "the page stops passing the settled flag — the rule is correct and the "
        "page never invokes it, which is exactly how CERT-598's defect existed "
        "beside a correct pickHeroOutcome",
    ),
    (
        "C",
        LIB,
        WINNER_KEY,
        "      comparison =\n"
        "        (b.is_winner === true ? 1 : 0) - (a.is_winner === true ? 1 : 0);",
        "the winner key authored in reverse — the winner sinks to the BOTTOM of "
        "the results table (UX-P230's original defect, one key over)",
    ),
    (
        "D",
        LIB,
        'const winnerLeads = resolved && field === "probability" && direction === "desc";',
        "const winnerLeads = resolved;",
        "OVER-CORRECTION: the winner is forced above every ordering, so an "
        "explicit name or change sort silently stops being what it says",
    ),
    (
        "E",
        LIB,
        'const winnerLeads = resolved && field === "probability" && direction === "desc";',
        'const winnerLeads = resolved && field === "probability";',
        "OVER-CORRECTION: probability ASCENDING puts a 21% winner above a 2% "
        "longshot, making the pill's up-arrow a lie",
    ),
    (
        "F",
        LIB,
        WINNER_KEY,
        "      comparison =\n"
        "        (a.is_winner !== false ? 1 : 0) - (b.is_winner !== false ? 1 : 0);",
        "an UNGRADED row (is_winner null) promoted as though it had won — "
        "absence read as a result",
    ),
    (
        "G",
        LIB,
        WINNER_KEY,
        "      return (b.is_winner === true ? 1 : 0) - (a.is_winner === true ? 1 : 0);",
        "an early return that skips the direction flip: the winner leads but the "
        "losers below him fall back to arrival order — passes on production data, "
        "which arrives sorted, and is caught only by the shuffled-payload test",
    ),
    (
        "H",
        LIB,
        "    if (comparison === 0) {",
        "    if (comparison === 0 && !winnerLeads) {",
        "the winner key stops falling through, so the whole settled table loses "
        "its probability sub-order",
    ),
    (
        "I",
        LIB,
        "  resolved = false,",
        "  resolved = true,",
        "the default flips, so every OPEN market starts honouring a stray "
        "is_winner flag and claims a result it does not have",
    ),
    (
        "J",
        PAGE,
        '      market.status === "resolved",',
        "      market.outcomes.some((o) => o.is_winner === true),",
        "the gate keys off the GRADING rather than the STATUS — a live market "
        "with one flagged outcome renders as though it had settled",
    ),
    (
        "K",
        PAGE,
        '      market.status === "resolved",',
        '      market.status === "settled",',
        "the status literal is wrong, so the rule is wired to a value the payload "
        "never carries and does nothing",
    ),
    (
        "L",
        PAGE,
        "data-outcome-name={outcome.name}",
        'data-outcome-name=""',
        "the render hook goes blank — the guard must not read an empty row list "
        "as agreement between hero and table",
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
