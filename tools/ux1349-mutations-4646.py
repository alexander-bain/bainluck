#!/usr/bin/env python3
"""#4646 mutation battery — does the suite hold the rung, and do the two suites
whose FIXTURES this diff moved still catch their own defects?

Half of this battery is not about #4646 at all. `relatedFuturesOneGamePropsHeading3417`,
`relatedFuturesEmptyBigPicture3775` and `aDrawIsNotAPerson6372` all used the event's own
moneyline as their generic game_prop, and #4646 deletes that market from the rail — so all
three fixtures had to move to a market that survives. A fixture edit that quietly defangs
another issue's guard is the failure mode to be afraid of here, so M5, M6 and M8 re-break
each of those three defects and require the edited suite to go red.

Each mutant edits ONE source file in place, runs the whole RelatedFutures family, and
restores. A mutant that leaves the suite GREEN is a survivor and is printed as such.

Run from the repo root of the ux worktree:
    python3 tools/ux1349-mutations-4646.py
"""

from __future__ import annotations

import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1] / "frontend"
RAIL = ROOT / "components/RelatedFutures.tsx"

# Every suite that renders this component, not just the ones named for it: #6372 lives in
# `aDrawIsNotAPerson6372.test.tsx` and would have been missed by a name-shaped pattern —
# it was the THIRD suite whose fixture this diff moved, and the full-suite run is what
# found it.
PATTERN = "([Rr]elatedFutures|aDrawIsNotAPerson6372)"

RUNG = "  if (isEventOwnMoneylineMarket(f.market_name, homeTeam, awayTeam)) return false;\n"
EARLY = '  if (f.display_category !== "game_prop") return true;\n'

GATE = """  const effectiveStatProps = hasGameMarkets
    ? 0
    : visibleHomeStatProps.length + visibleAwayStatProps.length;
"""

EYEBROW = "                  {gamePropsHeading({ isFinished, isLive, hasBoxScore: !!boxScore })}\n"

MUTANTS: list[tuple[str, pathlib.Path, str, str]] = [
    (
        "M1 delete the rung — the rail answers the hero's question again",
        RAIL,
        RUNG,
        "",
    ),
    (
        "M2 invert the rung — the rail keeps ONLY the event's own question",
        RAIL,
        RUNG,
        "  if (!isEventOwnMoneylineMarket(f.market_name, homeTeam, awayTeam)) return false;\n",
    ),
    (
        "M3 hoist the rung above the game_prop early return — it reaches every category",
        RAIL,
        EARLY + RUNG,
        RUNG + EARLY,
    ),
    (
        "M4 key the rung on the market's CLEAN LABEL instead of its name",
        RAIL,
        "isEventOwnMoneylineMarket(f.market_name, homeTeam, awayTeam)",
        "isEventOwnMoneylineMarket(f.clean_label, homeTeam, awayTeam)",
    ),
    (
        "M5 #3775's gate counts PAYLOAD rows again — a header over an empty section",
        RAIL,
        GATE,
        "  const effectiveStatProps = hasGameMarkets\n"
        "    ? 0\n"
        "    : homeCats.statProps.length + awayCats.statProps.length;\n",
    ),
    (
        "M6 #3417's eyebrow is deleted — Bigger Picture opens on an unlabelled grid",
        RAIL,
        EYEBROW,
        "",
    ),
    (
        "M8 #6372's fallback calls every unparsed outcome a person again",
        RAIL,
        "    playerName: outcomeNamesASubject(outcomeName) ? outcomeName : null,\n",
        "    playerName: outcomeName,\n",
    ),
    (
        "M7 EQUIVALENT BY DESIGN — the two sides are swapped at the call site",
        RAIL,
        "isEventOwnMoneylineMarket(f.market_name, homeTeam, awayTeam)",
        "isEventOwnMoneylineMarket(f.market_name, awayTeam, homeTeam)",
    ),
]

# M7: `isEventOwnMoneylineMarket` tests BOTH orientations of the pair internally
# (`first names away && second names home` OR the reverse), so naming the sides in the
# other order cannot change an answer. Declared rather than "fixed" with a test that
# would be asserting a property of the callee, not of this call site.
#
# M4 IS NOT EQUIVALENT, AND IS STILL DECLARED — read this before "fixing" it.
# `clean_label` is the ELLIPSISED display string: measured on the shipped capture, the
# backend cuts at 55 characters and appends "…" ('Singapore Open, Qualification: Nika
# Radisic vs Viktoria Morvayova' → '…vs Viktoria…'). A truncated second side names no
# club, so keying the rung on `clean_label` would silently stop firing on exactly the
# LONGEST fixture names. It survives because no specimen can currently distinguish the
# two: 63 own-moneyline rows sampled across ATP/WTA/NHL/EPL/MLB/MMA on 2026-09-19 were
# all Kalshi short forms ("Dallas vs St. Louis", "Brighton vs Arsenal"), none within 20
# characters of the cut. Killing it would mean inventing a payload row no venue serves
# today — a fixture asserting the answer rather than measuring it. The reason `market_name`
# is the right input is written into the rung's comment instead, where a future reader
# meets it.
EXPECTED_SURVIVORS = {
    "M4": "DECLARED, not equivalent — no specimen can distinguish it (see above)",
    "M7": "EQUIVALENT — the predicate tests both orientations internally",
}


def run_suite() -> bool:
    """True when the suite is GREEN."""
    proc = subprocess.run(
        ["npx", "jest", f"--testPathPatterns={PATTERN}"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    return proc.returncode == 0


def main() -> int:
    if not run_suite():
        print("REFUSING: the suite is not green before mutating anything.")
        return 2

    unexpected: list[str] = []
    for name, path, old, new in MUTANTS:
        original = path.read_text()
        if old not in original:
            print(f"  SKIPPED-UNAPPLIED {name}  <- pattern not found in {path.name}")
            unexpected.append(name)
            continue
        if original.count(old) != 1:
            print(f"  SKIPPED-AMBIGUOUS {name}  <- {original.count(old)} matches")
            unexpected.append(name)
            continue
        try:
            path.write_text(original.replace(old, new, 1))
            green = run_suite()
        finally:
            path.write_text(original)

        tag = name.split(" ", 1)[0]
        if green:
            if tag in EXPECTED_SURVIVORS:
                print(f"  survivor ({EXPECTED_SURVIVORS[tag]})\n             {name}")
            else:
                print(f"  🔴 SURVIVOR {name}")
                unexpected.append(name)
        else:
            print(f"  killed   {name}")

    if not run_suite():
        print("🔴 the tree did not restore green — inspect before committing.")
        return 2
    print(
        f"\n{len(MUTANTS) - len(unexpected)}/{len(MUTANTS)} accounted for "
        f"({len(EXPECTED_SURVIVORS)} declared survivors)."
    )
    return 1 if unexpected else 0


if __name__ == "__main__":
    sys.exit(main())
