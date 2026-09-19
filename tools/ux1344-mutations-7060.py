#!/usr/bin/env python3
"""#7060 mutation battery — does the guard suite actually hold the fix down?

Each mutant edits a tracked file, runs ONLY the #7060 suite, and restores the
file. A mutant that survives is a hole in the suite, not a curiosity.

Mutant A is the pre-fix banner verbatim — the block that told a reader a live
first-innings market had produced "final probabilities". It is the red-first
proof.

Mutants I and J mutate the TEST rather than the product. Both must fail or
error: I breaks the control's phrase list (an absence assertion passes happily
over phrases that never existed), and J points the source reader at a file that
is not there (a reader that returns "" makes every `not.toContain` green).

    cd ~/bainluck-dev/ux && python3 tools/ux1344-mutations-7060.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MODULE = REPO / "frontend" / "lib" / "settlementBanner.ts"
PAGE = REPO / "frontend" / "app" / "futures" / "[id]" / "page.tsx"
SUITE = REPO / "frontend" / "__tests__" / "settlementNeedsEvidenceNotASchedule7060.test.ts"

DECISION = (
    '  return market.status === "resolved" ? "This market has been settled." : null;'
)

NEW_BANNER = """      {settlementBanner && (
        <div className="bg-amber-500/10 border border-amber-500/20 rounded-lg px-4 py-3 text-sm text-amber-400">
          {settlementBanner}
        </div>
      )}"""

PRE_FIX_BANNER = """      {(isResolved || (market.resolution_date && new Date(market.resolution_date) < new Date())) && (
        <div className="bg-amber-500/10 border border-amber-500/20 rounded-lg px-4 py-3 text-sm text-amber-400">
          {isResolved
            ? `This market has been settled.${market.resolution_date ? ` Resolved ${new Date(market.resolution_date).toLocaleDateString()}.` : ""}`
            : `This market resolved on ${new Date(market.resolution_date!).toLocaleDateString()}. Showing final probabilities.`}
        </div>
      )}"""

# A date arm rewritten to dodge every banned PHRASE — only the structural
# assertion (`resolution_date < now` outside the JSX) can catch this one.
QUIET_DATE_ARM = """      {(settlementBanner || (market.resolution_date && new Date(market.resolution_date) < new Date())) && (
        <div className="bg-amber-500/10 border border-amber-500/20 rounded-lg px-4 py-3 text-sm text-amber-400">
          {settlementBanner ?? "Trading has closed. Final numbers below."}
        </div>
      )}"""

# (id, description, target file, old, new)
MUTANTS: list[tuple[str, str, Path, str, str]] = [
    (
        "A",
        "THE PRE-FIX BANNER, verbatim (announces settlement from a passed date)",
        PAGE,
        NEW_BANNER,
        PRE_FIX_BANNER,
    ),
    (
        "B",
        "gate flipped to `!== \"open\"` — a `closed` market gets announced as settled",
        MODULE,
        DECISION,
        '  return market.status !== "open" ? "This market has been settled." : null;',
    ),
    (
        "C",
        "status ignored — every market is settled",
        MODULE,
        DECISION,
        '  return "This market has been settled.";',
    ),
    (
        "D",
        "#7058 REOPENED: the scheduled date appended to the settled sentence",
        MODULE,
        DECISION,
        '  return market.status === "resolved"\n'
        '    ? `This market has been settled. Resolved ${new Date(\n'
        "        (market as { resolution_date?: string }).resolution_date ?? 0,\n"
        "      ).toLocaleDateString()}.`\n"
        "    : null;",
    ),
    (
        "E",
        "banner never renders at all",
        MODULE,
        DECISION,
        "  return null;",
    ),
    (
        "F",
        "case-folded status — a stray `RESOLVED` is believed",
        MODULE,
        DECISION,
        '  return String(market.status).toLowerCase() === "resolved"\n'
        '    ? "This market has been settled."\n'
        "    : null;",
    ),
    (
        "G",
        "the missing-market guard dropped",
        MODULE,
        "  if (!market) return null;\n",
        "",
    ),
    (
        "H",
        "THE QUIET REGRESSION: a date arm back in the JSX, worded to dodge the phrases",
        PAGE,
        NEW_BANNER,
        QUIET_DATE_ARM,
    ),
    (
        "I",
        "page hardcodes the sentence instead of calling the guarded decision",
        PAGE,
        "  const settlementBanner = settlementBannerText(market);",
        '  const settlementBanner = isResolved ? "This market has been settled." : null;',
    ),
    (
        "J",
        "ANTI-VACUITY (mutates the TEST): control's phrase list loses the real phrases",
        SUITE,
        '  "This market resolved on",',
        '  "This market evaporated on",',
    ),
    (
        "K",
        "ANTI-VACUITY (mutates the TEST): the source reader points at a missing file",
        SUITE,
        '"app", "futures", "[id]", "page.tsx"',
        '"app", "futures", "[id]", "page.does-not-exist.tsx"',
    ),
]


def run_suite() -> tuple[int, str]:
    proc = subprocess.run(
        ["npx", "jest", "--testPathPatterns=settlementNeedsEvidenceNotASchedule7060"],
        cwd=REPO / "frontend",
        capture_output=True,
        text=True,
    )
    return proc.returncode, proc.stdout + proc.stderr


def main() -> int:
    baseline_code, baseline_out = run_suite()
    if baseline_code != 0:
        print("BASELINE IS RED — fix the suite before measuring mutants.")
        print(baseline_out[-3000:])
        return 2
    print("baseline: GREEN\n")

    killed, survived = [], []
    for mid, desc, target, old, new in MUTANTS:
        original = target.read_text()
        if old not in original:
            print(f"  {mid}  ?? NOT APPLIED — anchor missing: {desc}")
            survived.append((mid, desc, "anchor missing"))
            continue
        try:
            target.write_text(original.replace(old, new, 1))
            code, out = run_suite()
        finally:
            target.write_text(original)

        if code == 0:
            print(f"  {mid}  SURVIVED  {desc}")
            survived.append((mid, desc, "suite stayed green"))
        else:
            failing = [
                line.strip()
                for line in out.splitlines()
                if line.strip().startswith(("●", "✕"))
            ]
            first = failing[0] if failing else f"exit {code}"
            print(f"  {mid}  killed    {desc}\n           by: {first}")
            killed.append(mid)

    print(f"\n{len(killed)}/{len(MUTANTS)} killed: {', '.join(killed)}")
    if survived:
        print("SURVIVORS (holes in the suite):")
        for mid, desc, why in survived:
            print(f"  {mid}  {desc} — {why}")
        return 1
    print("No survivors.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
