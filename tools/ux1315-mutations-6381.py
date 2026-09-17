#!/usr/bin/env python3
"""Mutation battery for #6381's second half.

Two files under mutation, deliberately: the RULE (`lib/eventKeyStats.ts`) and the
WIRING (`app/events/[id]/page.tsx`). The defect was never in the rule — the rule
was correct for the arguments it was given — so a battery that only mutated the
rule would say nothing about the half that was actually broken.

In-memory restore, a `restored:` line per mutant, failing names from jest's JSON.
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FRONTEND = ROOT / "frontend"
LIB = FRONTEND / "lib/eventKeyStats.ts"
PAGE = FRONTEND / "app/events/[id]/page.tsx"
JSON_OUT = Path("/tmp/ux1315-mutation-6381.json")

MUTANTS = [
    (
        "A · the rule loses its arm (the original defect)",
        LIB,
        "  if (args.venueSettled) return false;",
        "  if (false) return false;",
    ),
    (
        "B · the rule fires for every row, graded or not",
        LIB,
        "  if (args.venueSettled) return false;",
        "  return false;",
    ),
    (
        "C · the WIRING is dropped — the rule is right and never asked",
        PAGE,
        "    venueSettled: Boolean(venueSettledSentence),",
        "",
    ),
    (
        "D · the wiring is inverted",
        PAGE,
        "    venueSettled: Boolean(venueSettledSentence),",
        "    venueSettled: !venueSettledSentence,",
    ),
    (
        "E · the grade is folded into onVisiblePoll too — #5459's mistake, which "
        "deletes the age stamp along with the promise",
        PAGE,
        "  const onVisiblePoll = shouldShowRefreshCountdown({\n    isFinished,\n    streamConnected,\n    isLive,\n    isSuspended,\n    commenceTime: event?.commence_time,\n  });",
        "  const onVisiblePoll = shouldShowRefreshCountdown({\n    isFinished,\n    streamConnected,\n    isLive,\n    isSuspended,\n    commenceTime: event?.commence_time,\n    venueSettled: Boolean(venueSettledSentence),\n  });",
    ),
    (
        "F · the arm moves INTO the isSuspended branch — a clock rule where a "
        "state rule belongs, so a LIVE-flagged graded row keeps its ring",
        LIB,
        "  if (args.venueSettled) return false;",
        "",
    ),
]


def run_tests() -> tuple[int, set[str]]:
    import json
    import os

    proc = subprocess.run(
        [
            "npx", "jest",
            "--testPathPatterns=aGradedMatchStopsPromisingAnUpdate6381|deadFixtureStopsPromisingAnUpdate6381|livePageStopsPromisingAnUpdate5459|pregameHeaderStopsPromisingAnUpdate3802",
            "--json", f"--outputFile={JSON_OUT}",
        ],
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
        print(f"   ✕ {f}")
    print("🔴 the baseline is not green — nothing below means anything")
    sys.exit(2)

killed = 0
signatures = []
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
        signatures.append(frozenset(failed))
    print(f"\n{verdict}  {name}")
    print(f"   exit {code} · {len(failed)} assertion(s) fired · restored: {restored}")
    for f in sorted(failed):
        print(f"     ✕ {f}")

print(f"\n{killed}/{len(MUTANTS)} killed · {len(set(signatures))} distinct failure signatures")
sys.exit(0 if killed == len(MUTANTS) else 3)
