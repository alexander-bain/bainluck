#!/usr/bin/env python3
"""Mutation battery for #4568's second half — the date-ladder tie-break.

TWO files under mutation: the RULE (`lib/futuresLadder.ts`) and the WIRING
(`app/futures/[id]/page.tsx`). The wiring mutant is not decoration — this page
has two outcome renderers chosen by market shape, and a rule that is perfect
inside a function the quantity branch never reaches is what ux/1317 shipped by
mistake and caught only by re-rendering the issue's own specimen.

Two mutants exist purely because a live specimen does NOT exercise the seam
(G, the anchor; F, the day). Their guards are constructed, and the mutants are
how we know the constructed guard is load-bearing rather than decorative.

In-memory restore, an `applied:`/`restored:` line per mutant (a no-op perl reads
identical to a survivor — ux/1315), and failing test names out of jest's JSON,
because this workspace's reporter prints no per-test lines.

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
RULE = FRONTEND / "lib/futuresLadder.ts"
PAGE = FRONTEND / "app/futures/[id]/page.tsx"
BAND = "dateLadderTiesBreakChronologically4568|futuresDetailDateLadderOrder4568|futuresLadderShapeQ478"
JSON_OUT = Path("/tmp/ux1318-mutation-4568-sort.json")

MUTANTS = [
    (
        "A · the tie-break is deleted — master's behaviour restored, which IS the "
        "filed defect: eleven tied rungs in scrambled serve order",
        RULE,
        "      if (ap !== bp) return ap - bp;\n      if (!chrono) return 0;\n      return (chrono.get(a) ?? 0) - (chrono.get(b) ?? 0);",
        "      return ap === bp ? 0 : ap - bp;",
    ),
    (
        "B · ties break on outcome ID — the rule Q478 forbids by name, and on "
        "108559 ids are not chronological either",
        RULE,
        "      return (chrono.get(a) ?? 0) - (chrono.get(b) ?? 0);",
        "      return a.id - b.id;",
    ),
    (
        "C · the calendar runs backwards — a reordering that is not a no-op, so a "
        "guard asserting only 'the order changed' would pass it",
        RULE,
        "      return (chrono.get(a) ?? 0) - (chrono.get(b) ?? 0);",
        "      return (chrono.get(b) ?? 0) - (chrono.get(a) ?? 0);",
    ),
    (
        "D · the all-or-nothing rule is dropped — an unparseable label is skipped "
        "and the rungs that DID parse are placed around it, the partial timeline "
        "the backend parser's docstring refuses",
        RULE,
        "    const got = parseLadderDate(row.name);\n    if (!got) return null;\n    parsed.push([row, got]);",
        "    const got = parseLadderDate(row.name);\n    if (!got) continue;\n    parsed.push([row, got]);",
    ),
    (
        "E · the forward-looking refusal is deleted — an 'or later' ladder gets "
        "sorted ascending, which on that ladder is upside down",
        RULE,
        "    if (pointsForward(row.name ?? \"\")) return null;",
        "    if (false) return null;",
    ),
    (
        "F · the day is dropped from the sort key — invisible on today's "
        "population, which is why its guard is constructed",
        RULE,
        "    ranks.set(row, (year * 100 + d.month) * 100 + d.day);",
        "    ranks.set(row, (year * 100 + d.month) * 100);",
    ),
    (
        "G · the anchor loses its -1 — a bare month then claims to fall AFTER the "
        "dated rung it precedes",
        RULE,
        "    anchor = Math.min(...years) - 1;",
        "    anchor = Math.min(...years);",
    ),
    (
        "H · a bare month no longer needs its before/by framing — 'October' as a "
        "plain label becomes a date and invents a timeline out of a field",
        RULE,
        "    return g.lead ? { year: null, month, day: 1 } : null;",
        "    return { year: null, month, day: 1 };",
    ),
    (
        "I · the day bound is dropped — 'Before Jun 32, 2027' parses",
        RULE,
        "    return day >= 1 && day <= 31 ? day : null;",
        "    return day;",
    ),
    (
        "J · the WIRING is reverted: the page stops asking for cumulative order, "
        "so the rule is correct and unreachable on the specimen it was built for",
        PAGE,
        "      ladderOrderFor(market?.mutually_exclusive),",
        '      "served",',
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
