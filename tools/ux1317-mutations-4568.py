#!/usr/bin/env python3
"""Mutation battery for #4568 — the ALL OUTCOMES fold.

TWO files under mutation and FOUR seams inside them, deliberately: the RULE
(`lib/futuresDetailDisplay.ts`), the LIST wiring, the FOLD wiring and the
COUNTERS (all in `app/futures/[id]/page.tsx`). ux/1315's mutant C and ux/1316's
mutants A/B are the reason — a battery that only mutates the rule cannot see a
presentation decision, and this ship's risk is spread across four independent
edits that a partial revert would leave silently half-applied.

The counters get their own mutants because they are the defect's quiet second
half: folding five rows out of a 19-row ladder while "Show all 19" still stands
makes the button promise rows the fold is holding, and no positional assertion
about the fold would notice.

In-memory restore, an `applied:`/`restored:` line per mutant (a no-op perl reads
identical to a survivor — ux/1315), and failing names from jest's JSON, because
this workspace's reporter prints no per-test lines and a `✕` scrape reads
"0 assertions fired" on every kill.

NEVER `git checkout --` to restore: it reads the INDEX and would delete an
uncommitted fix. Commit first; this restores from an in-memory copy.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FRONTEND = ROOT / "frontend"
RULE = FRONTEND / "lib/futuresDetailDisplay.ts"
PAGE = FRONTEND / "app/futures/[id]/page.tsx"
BAND = "numberlessOutcomesFoldBehindADisclosure4568"
JSON_OUT = Path("/tmp/ux1317-mutation-4568.json")

MUTANTS = [
    (
        "A · the LIST wiring is reverted to master's expression — the original "
        "defect: every numberless row back in the open ladder",
        PAGE,
        "  const displayedOutcomes = showAllOutcomes\n    ? pricedOutcomes\n    : pricedOutcomes.slice(0, 25);",
        "  const displayedOutcomes = showAllOutcomes\n    ? sortedOutcomes\n    : sortedOutcomes.slice(0, 25);",
    ),
    (
        "B · the disclosure is deleted rather than collapsed — the rows vanish "
        "entirely, which is the outcome D102 explicitly forbids (gotcha #43)",
        PAGE,
        "        {unpricedOutcomes.length > 0 && (",
        "        {false && (",
    ),
    (
        "C · the rule's predicate is inverted — the PRICED rows get folded and the "
        "numberless ones headline the ladder",
        RULE,
        "    if (outcome.probability == null) folded.push(outcome);",
        "    if (outcome.probability != null) folded.push(outcome);",
    ),
    (
        "D · the rule uses a FALSY check instead of a null check — a genuine 0% "
        "row is a claim and must stay listed; this folds it with the absences",
        RULE,
        "    if (outcome.probability == null) folded.push(outcome);",
        "    if (!outcome.probability) folded.push(outcome);",
    ),
    (
        "E · the show-all control counts the whole ladder again — 'Show all 19' "
        "over a list that can only reveal fourteen",
        PAGE,
        "                : `Show all ${pricedOutcomes.length}`}",
        "                : `Show all ${sortedOutcomes.length}`}",
    ),
    (
        "F · the show-more button counts the whole ladder again",
        PAGE,
        "            Show {pricedOutcomes.length - 25} more outcomes",
        "            Show {sortedOutcomes.length - 25} more outcomes",
    ),
    (
        "G · the fold renumbers its own contents — prints 1-5 and tells the reader "
        "these are the top five of something",
        PAGE,
        "                  rank={outcome.rank ?? pricedOutcomes.length + index + 1}",
        "                  rank={index + 1}",
    ),
    (
        "H · the label reverts to the wording D111 overruled",
        PAGE,
        "              More outcomes ({unpricedOutcomes.length})",
        "              Untraded outcomes ({unpricedOutcomes.length})",
    ),
]


def run_tests():
    if JSON_OUT.exists():
        JSON_OUT.unlink()
    proc = subprocess.run(
        ["npx", "jest", f"--testPathPatterns={BAND}", "--json", f"--outputFile={JSON_OUT}"],
        cwd=FRONTEND,
        capture_output=True,
        text=True,
        env={**os.environ, "TZ": "UTC"},
    )
    failed: set[str] = set()
    if JSON_OUT.exists():
        report = json.loads(JSON_OUT.read_text())
        for suite in report.get("testResults", []):
            for case in suite.get("assertionResults", []):
                if case.get("status") == "failed":
                    failed.add(case.get("fullName", "?"))
    return proc.returncode, failed


code, failed = run_tests()
print(f"BASELINE (the fix as committed): exit {code}, {len(failed)} failing")
if code != 0:
    for f in sorted(failed):
        print(f"   x {f}")
    print("RED BASELINE — nothing below means anything")
    sys.exit(2)

killed = 0
signatures = []
for name, path, old, new in MUTANTS:
    orig = path.read_text()
    if old not in orig:
        print(f"\nANCHOR NOT FOUND  {name}\n   in {path.name} — mutant never applied")
        continue
    mutated = orig.replace(old, new, 1)
    if mutated == orig:
        print(f"\nNO-OP  {name}\n   replacement changed nothing in {path.name}")
        continue
    path.write_text(mutated)
    applied = path.read_text() != orig
    code, failed = run_tests()
    path.write_text(orig)
    restored = "YES" if path.read_text() == orig else "NO"
    verdict = "KILLED" if code != 0 else "SURVIVED"
    if code != 0:
        killed += 1
        signatures.append(frozenset(failed))
    print(f"\n{verdict}  {name}")
    print(f"   applied: {applied} · exit {code} · {len(failed)} assertion(s) fired · restored: {restored}")
    for f in sorted(failed):
        print(f"     x {f}")

print(f"\n{killed}/{len(MUTANTS)} killed · {len(set(signatures))} distinct failure signatures")
sys.exit(0 if killed == len(MUTANTS) else 3)
