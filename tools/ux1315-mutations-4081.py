#!/usr/bin/env python3
"""Mutation battery for #4081's guard — and for what it refuses to claim.

Same discipline as `ux1315-mutations-6766.py`: in-memory restore (never
`git checkout --`, which deletes an uncommitted fix), an explicit `restored:`
line per mutant, and failing test NAMES read from jest's own JSON because this
workspace's reporter prints no per-test lines.
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FRONTEND = ROOT / "frontend"
LIB = FRONTEND / "lib/gameTimeLabel.ts"
JSON_OUT = Path("/tmp/ux1315-mutation-4081.json")

MUTANTS = [
    (
        "A · the original defect: only a BARE date counts as a declared day",
        "  return DATE_ONLY.test(value) || UTC_MIDNIGHT.test(value);",
        "  return DATE_ONLY.test(value);",
    ),
    (
        "B · everything is a declared day (render the world in UTC)",
        "  return DATE_ONLY.test(value) || UTC_MIDNIGHT.test(value);",
        "  return true;",
    ),
    (
        "C · any offset counts, not only a zero one",
        "const UTC_MIDNIGHT = /^\\d{4}-\\d{2}-\\d{2}T00:00:00(?:\\.0+)?(?:Z|\\+00:00)$/i;",
        "const UTC_MIDNIGHT = /^\\d{4}-\\d{2}-\\d{2}T00:00:00(?:\\.0+)?(?:Z|[+-]\\d{2}:\\d{2})$/i;",
    ),
    (
        "D · any fraction counts, not only an all-zero one",
        "const UTC_MIDNIGHT = /^\\d{4}-\\d{2}-\\d{2}T00:00:00(?:\\.0+)?(?:Z|\\+00:00)$/i;",
        "const UTC_MIDNIGHT = /^\\d{4}-\\d{2}-\\d{2}T00:00:00(?:\\.\\d+)?(?:Z|\\+00:00)$/i;",
    ),
    (
        "E · the zone choice is inverted at the label",
        "  const zone = isDeclaredCalendarDay(resolutionDate)\n    ? { timeZone: \"UTC\" as const }\n    : {};",
        "  const zone = isDeclaredCalendarDay(resolutionDate)\n    ? {}\n    : { timeZone: \"UTC\" as const };",
    ),
    (
        "F · the label stops asking for the year (#1717)",
        "    month: \"short\",\n    day: \"numeric\",\n    year: \"numeric\",\n    ...zone,",
        "    month: \"short\",\n    day: \"numeric\",\n    ...zone,",
    ),
]


def run_tests() -> tuple[int, set[str]]:
    import json
    import os

    proc = subprocess.run(
        [
            "npx", "jest",
            "--testPathPatterns=declaredDeadlineKeepsItsDay4081|gameTimeLabel|resolvesLabel",
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
    print("🔴 the baseline is not green — nothing below means anything")
    for f in sorted(failed):
        print(f"   ✕ {f}")
    sys.exit(2)

killed = 0
signatures = []
for name, old, new in MUTANTS:
    orig = LIB.read_text()
    if old not in orig:
        print(f"🔴 {name}: anchor NOT FOUND — mutant never applied")
        continue
    LIB.write_text(orig.replace(old, new, 1))
    code, failed = run_tests()
    LIB.write_text(orig)
    restored = "YES" if LIB.read_text() == orig else "🔴 NO"
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
