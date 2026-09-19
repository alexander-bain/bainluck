#!/usr/bin/env python3
"""
#7065 mutation battery — does `tournamentLiveSectionAgreement7065` actually kill
the regressions it claims to guard, or is it a decoration?

Every mutant below is a change a careless edit could really make. A SURVIVOR is a
hole in the guard, not a curiosity: it means the suite is green on a tree where
the reader sees the defect again.

Three of the mutants restore the PRE-FIX tree at each layer separately (the
bucketer, My Stuff's copy, the shared decider's arms), because each of those can
regress on its own without the others.

    cd ~/bainluck-dev/ux && python3 tools/ux1346-mutations-7065.py

Exit 0 = every mutant killed. Exit 1 = at least one survivor (named). Exit 2 =
the harness could not run (a mutation did not apply, the baseline was not green)
— that is a story about this script, never a verdict about the guard.
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FRONTEND = ROOT / "frontend"

DECIDER = FRONTEND / "lib/tournamentLive.ts"
SECTIONS = FRONTEND / "lib/feedSections.ts"
MYSTUFF = FRONTEND / "app/my-stuff/page.tsx"
CARD = FRONTEND / "components/TournamentCard.tsx"

PATTERN = "tournamentLiveSectionAgreement7065"

# (name, file, find, replace, why this is a real regression)
MUTANTS = [
    (
        "bucketer-reverts-to-the-dead-string",
        SECTIONS,
        "if (isTournamentLive(td)) {",
        'if (td.schedule_status === "in-progress") {',
        "the pre-fix tree: the exact line that filed a LIVE card under Upcoming",
    ),
    (
        "bucketer-always-upcoming",
        SECTIONS,
        "if (isTournamentLive(td)) {",
        "if (false) {",
        "the `else` unconditional again, by a different route",
    ),
    (
        "bucketer-always-live",
        SECTIONS,
        "if (isTournamentLive(td)) {",
        "if (true) {",
        "the opposite failure — a finished tournament pulsing in Live Now",
    ),
    (
        "bucketer-negated",
        SECTIONS,
        "if (isTournamentLive(td)) {",
        "if (!isTournamentLive(td)) {",
        "both sections wrong at once, which a one-directional guard would miss",
    ),
    (
        "my-stuff-reverts-to-the-dead-string",
        MYSTUFF,
        "if (isTournamentLive(td)) {",
        'if (td.schedule_status === "in-progress") {',
        "the pre-fix tree on the third reader",
    ),
    (
        "my-stuff-always-upcoming",
        MYSTUFF,
        "if (isTournamentLive(td)) {",
        "if (false) {",
        "My Stuff silently keeps the unconditional else",
    ),
    (
        "window-loses-its-final-day",
        DECIDER,
        "const endOfLastDay = new Date(new Date(tournament.end_date).getTime() + 86400000);",
        "const endOfLastDay = new Date(tournament.end_date);",
        "UX-P180's original defect: the card goes dark for the whole final round",
    ),
    (
        "window-start-becomes-exclusive",
        DECIDER,
        "return now >= start && now < endOfLastDay;",
        "return now > start && now < endOfLastDay;",
        "off-by-one at the opening instant",
    ),
    (
        "window-end-becomes-inclusive",
        DECIDER,
        "return now >= start && now < endOfLastDay;",
        "return now >= start && now <= endOfLastDay;",
        "the tournament outlives its own window by an instant",
    ),
    (
        "window-ignores-start",
        DECIDER,
        "return now >= start && now < endOfLastDay;",
        "return now < endOfLastDay;",
        "every future tournament reads LIVE",
    ),
    (
        "window-arm-deleted",
        DECIDER,
        "if (tournament.start_date && tournament.end_date) {",
        "if (false && tournament.start_date && tournament.end_date) {",
        "the window stops being the veto and the price signal decides again",
    ),
    (
        "price-threshold-widened",
        DECIDER,
        "Math.abs(g.movement_24h) >= 0.01",
        "Math.abs(g.movement_24h) >= 0",
        "any movement at all, including none, reads as live",
    ),
    (
        "price-threshold-narrowed",
        DECIDER,
        "Math.abs(g.movement_24h) >= 0.01",
        "Math.abs(g.movement_24h) >= 1",
        "the windowless live tournament stops being live",
    ),
    (
        "price-arm-deleted",
        DECIDER,
        "return (tournament.golfers ?? []).some(",
        "return false || (tournament.golfers ?? []).slice(0, 0).some(",
        "a windowless live tournament (Asia Masters, Nationwide) goes quiet",
    ),
    (
        "price-arm-always-true",
        DECIDER,
        "return (tournament.golfers ?? []).some(",
        "return true || (tournament.golfers ?? []).some(",
        "a season-long futures row is filed as a live tournament",
    ),
    (
        "in-progress-arm-inverted",
        DECIDER,
        'if (tournament.schedule_status === "in-progress") return true;',
        'if (tournament.schedule_status !== "in-progress") return true;',
        "the arm that is dead in production must still be right if the venue revives it",
    ),
    (
        "card-stops-using-the-shared-decider",
        CARD,
        "return isTournamentLive(tournament);",
        "return tournament.schedule_status === \"in-progress\";",
        "the badge and the section drift apart again, from the card's side this time",
    ),
]


def run_suite() -> bool:
    r = subprocess.run(
        ["npx", "jest", f"--testPathPatterns={PATTERN}"],
        cwd=FRONTEND,
        capture_output=True,
        text=True,
    )
    return r.returncode == 0


def main() -> int:
    originals = {p: p.read_text() for p in {DECIDER, SECTIONS, MYSTUFF, CARD}}

    print("baseline: the guard must be GREEN before any mutant means anything")
    if not run_suite():
        print("  ✖ baseline is RED — fix the tree before reading this battery")
        return 2
    print("  ✓ green\n")

    survivors = []
    try:
        for name, path, find, replace, why in MUTANTS:
            src = originals[path]
            if src.count(find) != 1:
                print(f"  ! {name}: anchor found {src.count(find)}x in {path.name} — cannot apply")
                return 2
            path.write_text(src.replace(find, replace))
            killed = not run_suite()
            path.write_text(src)
            mark = "✓ killed " if killed else "✖ SURVIVED"
            print(f"  {mark} {name}  ({why})")
            if not killed:
                survivors.append(name)
    finally:
        for p, s in originals.items():
            p.write_text(s)

    print(f"\n{len(MUTANTS) - len(survivors)}/{len(MUTANTS)} killed")
    if survivors:
        print("SURVIVORS (each one is a hole in the guard):")
        for s in survivors:
            print(f"  - {s}")
        return 1
    print("no survivors")
    return 0


if __name__ == "__main__":
    sys.exit(main())
