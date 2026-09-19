#!/usr/bin/env python3
"""#7112 mutation battery — does the suite actually hold the new rung?

Each mutant edits ONE source file in place, runs the two #7112 suites plus the
two arms the notice says must not move (CERT-786, #3211), and restores. A
mutant that leaves the suite GREEN is a survivor and is printed as such.

Run from the repo root of the ux worktree:
    python3 tools/ux1348-mutations-7112.py
"""

from __future__ import annotations

import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1] / "frontend"
STATE = ROOT / "lib/eventState.ts"
SECTIONS = ROOT / "lib/sports/leagueSections.ts"
HORIZON = ROOT / "lib/sports/leagueHorizon.ts"

PATTERN = (
    "(venueSettledIsFinished7112|leaguePageSettledIsNotLive7112"
    "|suspendedIsFirstClassCert786|startedWithoutResultIsNotUpcoming3211)"
)

ARM = """  if (
    settlement &&
    hasNoReportedResult(status, commenceTime, now) &&
    venueSettledSummary(
      settlement.venue_settled,
      settlement.venue_settled_result,
    ) !== null
  ) {
    return "finished";
  }
"""

LADDER = '  if (status === "live" || isSuspendedStatus(status)) return "live";\n'

PASS_EVENT = """    const section = eventSectionKey(
      event.status,
      event.commence_time,
      now,
      event,
    );
"""

MUTANTS: list[tuple[str, pathlib.Path, str, str]] = [
    (
        "M1 drop the hasNoReportedResult conjunct — any flagged row is finished",
        STATE,
        "    hasNoReportedResult(status, commenceTime, now) &&\n",
        "",
    ),
    (
        "M2 drop the settlement read — every suspended row is finished",
        STATE,
        ARM,
        '  if (settlement) {\n    return "finished";\n  }\n',
    ),
    (
        "M3 invert the settlement test — graded rows stay live, ungraded move",
        STATE,
        "    ) !== null\n",
        "    ) === null\n",
    ),
    (
        "M4 the rung returns live instead of finished",
        STATE,
        '  ) {\n    return "finished";\n  }\n',
        '  ) {\n    return "live";\n  }\n',
    ),
    (
        "M5 the rung sits BELOW the status ladder — unreachable for suspended",
        STATE,
        ARM + LADDER,
        LADDER + ARM,
    ),
    (
        "M6 delete the rung entirely",
        STATE,
        ARM,
        "",
    ),
    (
        "M7 leagueSections stops passing the event — the bucket goes back",
        SECTIONS,
        PASS_EVENT,
        "    const section = eventSectionKey(event.status, event.commence_time, now);\n",
    ),
    (
        "M8 leagueHorizon stops passing the event — the two readers disagree",
        HORIZON,
        PASS_EVENT,
        "    const section = eventSectionKey(event.status, event.commence_time, now);\n",
    ),
    (
        "M9 EQUIVALENT BY DESIGN — the summary call collapsed to the raw flag",
        STATE,
        "    venueSettledSummary(\n      settlement.venue_settled,\n      settlement.venue_settled_result,\n    ) !== null\n",
        "    settlement.venue_settled === true\n",
    ),
]

EXPECTED_SURVIVORS = {"M9"}


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
                print(f"  survivor (EXPECTED, equivalent) {name}")
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
        f"({len(EXPECTED_SURVIVORS)} equivalent by design)."
    )
    return 1 if unexpected else 0


if __name__ == "__main__":
    sys.exit(main())
