#!/usr/bin/env python3
"""#6999 mutation battery — does the guard suite actually catch the defect?

Each mutant is a plausible WRONG version of the fix. A mutant that survives is
a hole in `__tests__/lib/playoffConferenceHeadingOnce6999.test.tsx`, not a
curiosity: the suite would have merged that version green.

The two mutants that matter most are the two failure SIDES. `pre-fix` prints the
conference twice (the filed defect). `always-empty-title` prints it zero times
in the filtered view, which is the defect the obvious one-line fix creates and
which "the name does not appear twice" cannot see.

    python3 tools/ux1342-mutations-6999.py

Exit 0 = every mutant killed. Exit 1 = at least one survived. Exit 2 = harness.
"""

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"
HELPER = FRONTEND / "lib" / "playoffConferenceSections.ts"
COMPONENT = FRONTEND / "components" / "TournamentProgressionTable.tsx"
PATTERN = "playoffConferenceHeadingOnce6999"

# (name, target file, needle, replacement, what shipping it would look like)
MUTANTS = [
    (
        "pre-fix-both-sides-get-conf",
        HELPER,
        'label: headingCarriesConference ? conf : null,\n    tournamentName: headingCarriesConference ? "" : conf,',
        'label: conf,\n    tournamentName: conf,',
        "the filed defect verbatim: heading and card title both say the conference",
    ),
    (
        "always-empty-title",
        HELPER,
        'tournamentName: headingCarriesConference ? "" : conf,',
        'tournamentName: "",',
        "the tempting one-liner: filtered view names the conference NOWHERE",
    ),
    (
        "always-label",
        HELPER,
        "label: headingCarriesConference ? conf : null,",
        "label: conf,",
        "heading always drawn: filtered view duplicates again",
    ),
    (
        "never-label",
        HELPER,
        "label: headingCarriesConference ? conf : null,",
        "label: null,",
        "heading never drawn: default view loses the conference entirely",
    ),
    (
        "grid-name-substituted",
        HELPER,
        'tournamentName: headingCarriesConference ? "" : conf,',
        'tournamentName: headingCarriesConference ? "NFL Playoffs 2026-27" : conf,',
        "the issue's suggested fix: the page's own h1 restated on every card",
    ),
    (
        "off-by-one-threshold",
        HELPER,
        "const headingCarriesConference = visible.length > 1;",
        "const headingCarriesConference = visible.length > 0;",
        "boundary slip: the single-section case takes the multi-section branch",
    ),
    (
        "threshold-two",
        HELPER,
        "const headingCarriesConference = visible.length > 1;",
        "const headingCarriesConference = visible.length > 2;",
        "boundary slip the other way: two-conference grids lose the heading",
    ),
    (
        "filter-ignored",
        HELPER,
        "const visible = conferences.filter(\n    (conf) => !conferenceFilter || conf === conferenceFilter,\n  );",
        "const visible = [...conferences];",
        "the chip stops narrowing the grid at all",
    ),
    (
        "component-renders-empty-heading",
        COMPONENT,
        "{data.tournament_name && (",
        "{data.tournament_name !== undefined && (",
        "an empty bold line lands where the duplicate was",
    ),
    (
        "component-never-renders-heading",
        COMPONENT,
        "{data.tournament_name && (",
        "{false && (",
        "the filtered view's only conference label is deleted",
    ),
]


def run_suite() -> bool:
    """True when the suite passes."""
    proc = subprocess.run(
        ["npx", "jest", f"--testPathPatterns={PATTERN}"],
        cwd=FRONTEND,
        capture_output=True,
        text=True,
    )
    return proc.returncode == 0


def main() -> int:
    for path in (HELPER, COMPONENT):
        if not path.exists():
            print(f"HARNESS: missing {path}", file=sys.stderr)
            return 2

    if not run_suite():
        print("HARNESS: the suite is RED before any mutation — fix that first.")
        return 2
    print("baseline: suite GREEN on the real tree\n")

    survivors = []
    for name, path, needle, replacement, consequence in MUTANTS:
        original = path.read_text()
        if needle not in original:
            print(f"HARNESS: needle not found for {name} in {path.name}", file=sys.stderr)
            return 2

        backup = path.with_suffix(path.suffix + ".mutbak")
        shutil.copy2(path, backup)
        try:
            path.write_text(original.replace(needle, replacement, 1))
            killed = not run_suite()
        finally:
            shutil.move(backup, path)

        verdict = "KILLED " if killed else "SURVIVED"
        print(f"{verdict}  {name}")
        print(f"          would ship: {consequence}")
        if not killed:
            survivors.append(name)

    print()
    print(f"{len(MUTANTS) - len(survivors)}/{len(MUTANTS)} killed")
    if survivors:
        print("SURVIVORS (holes in the guard): " + ", ".join(survivors))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
