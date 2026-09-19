#!/usr/bin/env python3
"""#7070 mutation battery — does the guard suite actually hold the fix down?

Each mutant edits a tracked file, runs ONLY the #7070 suite, and restores the
file. A mutant that survives is a hole in the suite, not a curiosity.

Mutants A, F and I are the PRE-FIX TREE, one layer each: the card without the
venue arm, the mapper that never carries the keys, and the heading hardcoded to
the denial. Each must die on its own, because each could regress on its own.

Mutant O mutates the TEST, not the product: it breaks the frozen pre-fix control
so the source probe's own anchor no longer contains the banned literal. It must
go RED — that is the anti-vacuity proof for arm 4, whose two real assertions are
an ABSENCE and a string match.

    cd ~/bainluck-dev/ux && python3 tools/ux1345-mutations-7070.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CARD = REPO / "frontend" / "components" / "EventCard.tsx"
MAPPER = REPO / "frontend" / "lib" / "leagueCards.ts"
PAGE = REPO / "frontend" / "app" / "sport" / "[sport]" / "[league]" / "page.tsx"
SUITE = REPO / "frontend" / "__tests__" / "leagueRailNamesTheWinner7070.test.tsx"

CARD_SENTENCE = """                  {venueSettledSentence ??
                    suspendedSummary(event.away_score, event.home_score, "home-away")}"""
CARD_DERIVE = """  const venueSettledSentence = isSuspended
    ? venueSettledSummary(event.venue_settled, event.venue_settled_result)
    : null;"""
CARD_DATE = "                  {finishedDateStr && <> · {finishedDateStr}</>}\n"

MAPPER_CARRY = """  if ("venue_settled" in game) {
    event.venue_settled = game.venue_settled;
    event.venue_settled_result = game.venue_settled_result ?? null;
  }"""
MAPPER_RESULT = "    event.venue_settled_result = game.venue_settled_result ?? null;\n"

TITLE_BODY = """  const namesAResult = games.some(
    (g) => venueSettledSummary(g.venue_settled, g.venue_settled_result) !== null,
  );
  return namesAResult ? MIXED_UNREPORTED_RAIL_TITLE : SUSPENDED_LABEL;"""

PAGE_TITLE = "title={unreportedRailTitle(unreportedGames)}"

# (id, description, target file, old, new)
MUTANTS: list[tuple[str, str, Path, str, str]] = [
    (
        "A",
        "THE PRE-FIX CARD: the venue arm removed, denial unconditional",
        CARD,
        CARD_SENTENCE,
        '                  {suspendedSummary(event.away_score, event.home_score, "home-away")}',
    ),
    (
        "B",
        "precedence swapped — `suspendedSummary` never returns null, so the venue never speaks",
        CARD,
        CARD_SENTENCE,
        """                  {suspendedSummary(event.away_score, event.home_score, "home-away") ??
                    venueSettledSentence}""",
    ),
    (
        "C",
        "the flag ignored: every suspended row treated as graded",
        CARD,
        CARD_DERIVE,
        """  const venueSettledSentence = isSuspended
    ? venueSettledSummary(true, event.venue_settled_result)
    : null;""",
    ),
    (
        "D",
        "the date tail dropped from the suspended line (#6361 regression)",
        CARD,
        CARD_DATE,
        "",
    ),
    (
        "E",
        "mapper keys on truthiness — `false` arrives as absent",
        MAPPER,
        '  if ("venue_settled" in game) {',
        "  if (game.venue_settled) {",
    ),
    (
        "F",
        "THE PRE-FIX MAPPER: the keys never reach the card at all",
        MAPPER,
        MAPPER_CARRY,
        "",
    ),
    (
        "G",
        "the flag travels, the sentence does not",
        MAPPER,
        MAPPER_RESULT,
        "",
    ),
    (
        "H",
        "heading needs EVERY row graded, so one honest row restores the lie",
        MAPPER,
        "  const namesAResult = games.some(",
        "  const namesAResult = games.length > 0 && games.every(",
    ),
    (
        "I",
        "THE PRE-FIX HEADING: always the denial",
        MAPPER,
        TITLE_BODY,
        "  return SUSPENDED_LABEL;",
    ),
    (
        "J",
        "heading always the mixed word — the informative case lost",
        MAPPER,
        TITLE_BODY,
        "  return MIXED_UNREPORTED_RAIL_TITLE;",
    ),
    (
        "K",
        "heading keyed on the RESULT STRING, so a bare `Settled` card keeps the denial above it",
        MAPPER,
        "    (g) => venueSettledSummary(g.venue_settled, g.venue_settled_result) !== null,",
        "    (g) => g.venue_settled_result != null,",
    ),
    (
        "L",
        "the mixed heading makes a claim again (`No score reported` over `Draw 0-0`)",
        MAPPER,
        'export const MIXED_UNREPORTED_RAIL_TITLE = "Other games";',
        'export const MIXED_UNREPORTED_RAIL_TITLE = "No score reported";',
    ),
    (
        "M",
        "the literal typed back into the page's JSX beside the function",
        PAGE,
        PAGE_TITLE,
        'title="No result reported"',
    ),
    (
        "N",
        "the heading computed on the WRONG rail's games",
        PAGE,
        PAGE_TITLE,
        "title={unreportedRailTitle(upcomingGames)}",
    ),
    (
        "O",
        "ANTI-VACUITY (mutates the TEST): the frozen pre-fix control loses the literal",
        SUITE,
        "const PRE_FIX_LINE = '        <LeagueGameRail\\n          title=\"No result reported\"\\n';",
        "const PRE_FIX_LINE = '        <LeagueGameRail\\n          title={railTitle}\\n';",
    ),
]


def run_suite() -> tuple[int, str]:
    proc = subprocess.run(
        ["npx", "jest", "--testPathPatterns=leagueRailNamesTheWinner7070"],
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
    print(f"baseline: GREEN ({baseline_out.strip().splitlines()[-4].strip()})\n")

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
