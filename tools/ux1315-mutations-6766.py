#!/usr/bin/env python3
"""Mutation battery for #6766's guard — does each arm die for its OWN reason?

Restores by writing the in-memory original back, NEVER `git checkout --` (ux/1314
lost a whole uncommitted fix to that), and prints an explicit `restored:` line
per mutant so a silent failure cannot pass as a result. Also prints WHICH test
names failed, because four mutants killed by one assertion is one test firing
four times, not a battery.
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FRONTEND = ROOT / "frontend"
LIB = FRONTEND / "lib/twoLegCardPair.ts"
POLITICS = FRONTEND / "app/politics/page.tsx"
ENT = FRONTEND / "app/entertainment/page.tsx"

MUTANTS = [
    (
        "A · the original defect: derive the second number even when a leg is served",
        LIB,
        "      second: served,",
        "      second: { name: served.name, prob: 100 - first.prob },",
    ),
    (
        "B · every pair is declared one question",
        LIB,
        "      oneQuestion: isComplementPair([first.prob / 100, served.prob / 100]),",
        "      oneQuestion: true,",
    ),
    (
        "C · /politics routes on arity alone again",
        POLITICS,
        "  const isBinary = market.outcome_count <= 2 && twoLegCardPair(market).oneQuestion;",
        "  const isBinary = market.outcome_count <= 2;",
    ),
    (
        "D · /entertainment's moment card draws YES/NO on anything with two legs",
        ENT,
        "  const yesNo =\n    market.outcome_count <= 2 && pair.oneQuestion ? pair.second : null;",
        "  const yesNo =\n    market.outcome_count <= 2 ? { name: \"No\", prob: 100 - market.prob } : null;",
    ),
    (
        "E · /entertainment's tech rail does the same",
        ENT,
        "        const yesNo = m.outcome_count <= 2 && pair.oneQuestion ? pair.second : null;",
        "        const yesNo = m.outcome_count <= 2 ? { name: \"No\", prob: 100 - m.prob } : null;",
    ),
    (
        "F · the complement is licensed by arity 2 rather than arity 1",
        LIB,
        "  if (row.outcome_count <= 1) {",
        "  if (row.outcome_count <= 2) {",
    ),
]

JSON_OUT = Path("/tmp/ux1315-mutation-jest.json")


def run_tests() -> tuple[int, set[str]]:
    """Failing test NAMES, read from jest's own JSON.

    Not scraped from the console: this workspace's reporter prints no per-test
    lines even under `--verbose`, so a regex over stdout finds nothing and every
    mutant reports `0 assertions fired` — a battery that cannot tell one kill
    from another.
    """
    proc = subprocess.run(
        [
            "npx", "jest",
            "--testPathPatterns=dashboardCardReadsItsSecondLeg6766",
            "--json", f"--outputFile={JSON_OUT}",
        ],
        cwd=FRONTEND,
        capture_output=True,
        text=True,
        env={**__import__("os").environ, "TZ": "UTC"},
    )
    failed: set[str] = set()
    if JSON_OUT.exists():
        import json

        report = json.loads(JSON_OUT.read_text())
        for suite in report.get("testResults", []):
            for case in suite.get("assertionResults", []):
                if case.get("status") == "failed":
                    failed.add(case.get("fullName", "?"))
    return proc.returncode, failed


code, failed = run_tests()
print(f"BASELINE (the fix as committed): exit {code}, {len(failed)} failing")
if code != 0:
    print("🔴 the baseline is not green — nothing below means anything")
    sys.exit(2)

killed = 0
witnesses: dict[str, frozenset] = {}
for name, path, old, new in MUTANTS:
    orig = path.read_text()
    if old not in orig:
        print(f"🔴 {name}: anchor NOT FOUND in {path.name} — mutant never applied")
        continue
    path.write_text(orig.replace(old, new, 1))
    code, failed = run_tests()
    path.write_text(orig)
    restored = "YES" if path.read_text() == orig else "🔴 NO"
    verdict = "KILLED" if code != 0 else "🔴 SURVIVED"
    if code != 0:
        killed += 1
        witnesses[name] = frozenset(failed)
    print(f"\n{verdict}  {name}")
    print(f"   exit {code} · {len(failed)} assertion(s) fired · restored: {restored}")
    for f in sorted(failed):
        print(f"     ✕ {f}")

print(f"\n{killed}/{len(MUTANTS)} killed")
distinct = {v for v in witnesses.values()}
print(f"{len(distinct)} distinct failure signatures across {len(witnesses)} kills")
sys.exit(0 if killed == len(MUTANTS) else 3)
