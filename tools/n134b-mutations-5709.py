#!/usr/bin/env python3
"""#5709 mutation sweep — does the guard actually catch a fifth implementation?

This ship's whole value is the GUARD: the two fixed lines matter less than the
assertion that stops the sixth copy of the rule appearing. So the mutants attack
the guard, not only the fix.

Each mutant is an EXACT string replacement asserted to match exactly once, so a
typo'd pattern aborts instead of quietly reading as SURVIVED.

Run from the native worktree root:  python3 tools/n134b-mutations-5709.py [Mn]
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CLIENT = ROOT / "ios/Bain Luck/BainLuckWidget/WidgetAPIClient.swift"
PBX = ROOT / "ios/Bain Luck/Bain Luck.xcodeproj/project.pbxproj"
WATCH = ROOT / "ios/Bain Luck/BainLuckWatch Watch App/WatchFeedModels.swift"

CALL = """            let abbrevs = TeamShortName.abbreviationPair(
                away: event.awayTeam,
                home: event.homeTeam,
                awayServed: event.awayTeamData?.abbreviation,
                homeServed: event.homeTeamData?.abbreviation
            )
            let homeAbbrev = abbrevs.home
            let awayAbbrev = abbrevs.away"""

REGRESSED = """            let homeAbbrev = event.homeTeamData?.abbreviation
                ?? String(event.homeTeam.split(separator: " ").last ?? "")
            let awayAbbrev = event.awayTeamData?.abbreviation
                ?? String(event.awayTeam.split(separator: " ").last ?? "")"""

MUTANTS = [
    # The defect itself, put back exactly as it was. This is the mutation that
    # matters: the guard exists to make this un-shippable.
    ("M1 the original defect is restored verbatim",
     CLIENT, CALL, REGRESSED,
     "testNoTargetShortensATeamNameByHand"),
    # A NEW file could reintroduce it; simulate by regressing a different target.
    # COMPILING, deliberately: renaming the call to a symbol that does not exist
    # dies at the compiler, which kills the mutant without proving the scan ran.
    ("M2 the pair rule is swapped for the single-name rule (loses #3430)",
     CLIENT, CALL,
     """            let homeAbbrev = event.homeTeamData?.abbreviation
                ?? TeamShortName.abbreviation(event.homeTeam)
            let awayAbbrev = event.awayTeamData?.abbreviation
                ?? TeamShortName.abbreviation(event.awayTeam)""",
     "testTheWidgetAsksTheSharedRule"),
    ("M3 the served abbreviation stops being passed through",
     CLIENT, "                awayServed: event.awayTeamData?.abbreviation,\n"
             "                homeServed: event.homeTeamData?.abbreviation\n", "",
     "testTheWidgetAsksTheSharedRule"),
    # Dropping membership ALONE cannot compile (the widget then cannot see the
    # type), so the honest mutant is the whole ship reverted: call regressed AND
    # membership removed. That compiles, and proves the membership assertion is
    # live rather than shadowed by the compiler.
    ("M4 the whole ship is reverted — call regressed and membership dropped",
     PBX, "\t\t\t\tUtilities/TeamShortName.swift,\n", "",
     "testTeamShortNameIsAMemberOfTheWidgetTarget", CLIENT, CALL, REGRESSED),
    # The allowlist must expire rather than rot: if the watch is fixed and the
    # entry is left behind, the guard silently stops protecting that file.
    #
    # BOTH accessors, not one. Mutating a single line left the file still
    # carrying the defect on the other, so the allowlist entry was still
    # justified and the mutant SURVIVED — correctly. That survivor was an
    # EQUIVALENT mutant, not a hole, and the distinction is the whole reason to
    # look at a survivor before "fixing" the test it failed to kill.
    ("M5 an allowlisted watch file is FULLY fixed but left on the allowlist",
     WATCH, """    func homeAbbrev() -> String {
        homeTeamData?.abbreviation ?? String(homeTeam?.split(separator: " ").last ?? "")
    }

    func awayAbbrev() -> String {
        awayTeamData?.abbreviation ?? String(awayTeam?.split(separator: " ").last ?? "")
    }""",
     """    func homeAbbrev() -> String {
        homeTeamData?.abbreviation ?? (homeTeam ?? "")
    }

    func awayAbbrev() -> String {
        awayTeamData?.abbreviation ?? (awayTeam ?? "")
    }""",
     "testTheAllowlistDoesNotRot"),
]

SIM = "platform=iOS Simulator,name=iPhone 17 Pro"
PROJ = ROOT / "ios/Bain Luck/Bain Luck.xcodeproj"


def run_suite():
    cmd = [
        "xcodebuild", "test",
        "-project", str(PROJ),
        "-scheme", "Bain Luck",
        "-destination", SIM,
        "-only-testing:BainLuckTests/TeamLabelSingleSourceAcrossTargetsTests",
        "OTHER_SWIFT_FLAGS=$(inherited) -Xfrontend -disable-sandbox",
    ]
    p = subprocess.run(cmd, capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr


def main():
    only = sys.argv[1] if len(sys.argv) > 1 else None
    print("=== baseline (unmutated) ===", flush=True)
    code, out = run_suite()
    if code != 0:
        print("BASELINE IS RED — fix that before trusting any mutant below.")
        print("\n".join(l for l in out.splitlines() if "error:" in l)[:3000])
        return 1
    print("baseline GREEN\n", flush=True)

    killed, survived = [], []
    for name, path, find, repl, expect, *rest in MUTANTS:
        if only and not name.startswith(only):
            continue
        original = path.read_text()
        n = original.count(find)
        if n != 1:
            print(f"ABORT {name}: pattern matched {n} times, expected exactly 1")
            return 2
        extra = None
        if len(rest) == 3:
            xpath, xfind, xrepl = rest
            xorig = xpath.read_text()
            if xorig.count(xfind) != 1:
                print(f"ABORT {name}: secondary pattern matched {xorig.count(xfind)} times")
                return 2
            extra = (xpath, xorig, xfind, xrepl)
        try:
            path.write_text(original.replace(find, repl))
            if extra:
                extra[0].write_text(extra[1].replace(extra[2], extra[3]))
            code, out = run_suite()
            if code == 0:
                survived.append(name)
                print(f"SURVIVED  {name}", flush=True)
            else:
                compiled = "Executed" in out or "Test Case" in out
                hit = f"{expect}]' failed" in out
                if compiled and hit:
                    print(f"KILLED    {name}  (by {expect})", flush=True)
                elif compiled:
                    print(f"KILLED*   {name}  -- but NOT by {expect}", flush=True)
                else:
                    print(f"KILLED(compile)  {name}  -- weaker: no test ran", flush=True)
                killed.append(name)
        finally:
            path.write_text(original)
            if extra:
                extra[0].write_text(extra[1])

    print(f"\n=== {len(killed)} killed / {len(MUTANTS)} mutants; survivors: {survived or 'none'}")
    return 0 if not survived else 3


if __name__ == "__main__":
    sys.exit(main())
