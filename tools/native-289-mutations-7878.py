#!/usr/bin/env python3
"""native/289 — mutation battery for #7878 (a capture hole drawn as a line).

Same harness rules as `native-288-mutations-4445.py`: gate on the EXIT CODE, and
match `with (\\d+) failures?` — xcodebuild writes "with 1 failure", SINGULAR, and
a plural-only regex reads a sibling class's "0 failures" and reports a killed
mutant as survived. Every anchor must match EXACTLY ONCE; a bad anchor wastes a
slot and reads as a survivor.

The subject is a rule with TWO thresholds and a domain guard, and the whole risk
of the change is over-breaking — a false gap invents a hole in a line that never
had one, which is worse than the flat line being fixed. So the battery is
weighted towards the mutants that would make the rule fire too often:

  * M1/M2 remove one threshold each. They are the reason both exist: each is
    held by exactly one control test, and if either survives, that threshold is
    decorative and the other is doing all the work.
  * M3 removes the in-game domain guard. This is the dangerous mutant — it is
    the version of this fix that shatters every pre-match line on the site into
    confetti, and only the overnight control can see it.
  * M4 never breaks at all: the defect itself, restored.
  * M5 drops runs of one point, which is the plausible "tidy-up" that silently
    deletes the observation on the far side of the hole.
  * M6 takes the median off the sorted intervals' top end instead of the middle,
    so no interval can ever be 15x it — a break rule that cannot fire.
  * M7 stops sorting, so arrival order decides where the hole is.
"""

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VIEW = ROOT / "ios/Bain Luck/Bain Luck/Components/OddsChartView.swift"
GUARD = (ROOT / "ios/Bain Luck/BainLuckTests"
         / "AStalledCaptureDrawsAGapNotALine7878Tests.swift")
SIM = "D2DA47A0-85F6-4BF8-AEFF-33146AE3EB05"

BREAK_IF = "            if inGame, interval > floor, interval > cadenceMultiple * median {"

MUTANTS = [
    ("M1 the absolute floor is dropped — only the cadence ratio decides",
     VIEW,
     BREAK_IF,
     "            if inGame, interval > cadenceMultiple * median {"),

    ("M2 the cadence ratio is dropped — only the absolute floor decides",
     VIEW,
     BREAK_IF,
     "            if inGame, interval > floor {"),

    ("M3 the in-game domain guard is dropped — pre-match holes break too",
     VIEW,
     BREAK_IF,
     "            if interval > floor, interval > cadenceMultiple * median {"),

    ("M4 the defect restored — the series is never broken",
     VIEW,
     "                segments.append(run)\n"
     "                run = [current]",
     "                run.append(current)"),

    ("M5 runs of a single observation are dropped instead of drawn",
     VIEW,
     "        segments.append(run)\n"
     "        return segments",
     "        segments.append(run)\n"
     "        return segments.filter { $0.count > 1 }"),

    ("M6 the cadence is taken from the longest interval, not the median",
     VIEW,
     "        let median = sortedIntervals[sortedIntervals.count / 2]",
     "        let median = sortedIntervals[sortedIntervals.count - 1]"),

    ("M7 arrival order is trusted — the points are never sorted",
     VIEW,
     "        let ordered = points.sorted { $0.date < $1.date }",
     "        let ordered = points"),

    # The overnight control asserts `count == 1`, and a test asserting "one
    # segment" passes for the boring reason too — the helper returning one
    # segment for EVERYTHING would satisfy it. This moves that control's points
    # in-game and spaces them so a working rule MUST break them, proving the
    # assertion can fail at all. A survivor here means the control is decorative.
    ("M8 the STRAWMAN: the overnight control is given in-game points around a "
     "real hole, so its `count == 1` has to be able to fail",
     GUARD,
     "        let observed = points(offsetsFromCommence: [-172_800, -86_400, -43_200, -3_600, -600])",
     "        let observed = points(offsetsFromCommence: [0, 120, 240, 360, 36_000])"),
]


# Named rather than wrapped across two lines inside the argv list: two adjacent
# string literals there are indistinguishable from a missing comma, which is a
# whole test class silently not running.
GUARD_TEST = (
    "-only-testing:BainLuckTests/"
    + "AStalledCaptureDrawsAGapNotALine7878Tests"
)


def run_swift():
    p = subprocess.run(
        ["xcodebuild", "-project", str(ROOT / "ios/Bain Luck/Bain Luck.xcodeproj"),
         "-scheme", "Bain Luck", "-destination", f"id={SIM}",
         "-disableAutomaticPackageResolution",
         GUARD_TEST,
         "OTHER_SWIFT_FLAGS=$(inherited) -Xfrontend -disable-sandbox", "test"],
        capture_output=True, text=True,
    )
    return p.returncode, p.stdout + p.stderr


COUNT = re.compile(r"with (\d+) failures?")


def label(out):
    hits = [int(m) for m in COUNT.findall(out)]
    return f"{sum(hits)} failing assertion group(s)" if hits else "no count line"


def main():
    # A dry pass first: a bad anchor costs a whole slot and reads as a survivor.
    bad = False
    for name, path, find, _ in MUTANTS:
        n = path.read_text().count(find)
        if n != 1:
            print(f"  ANCHOR    {name}  (matches {n}x, want 1)")
            bad = True
    if bad:
        print("\nrefusing to run: fix the anchors first")
        return 2

    # The baseline must be green on THIS simulator before a single mutant runs,
    # or every KILLED is free and the one SURVIVED is noise.
    code, out = run_swift()
    if code != 0:
        print(f"  BASELINE  RED (exit {code}, {label(out)}) — refusing to run")
        return 2
    print(f"  BASELINE  green (exit 0, {label(out)})", flush=True)

    results = []
    for name, path, find, repl in MUTANTS:
        original = path.read_text()
        path.write_text(original.replace(find, repl, 1))
        try:
            code, out = run_swift()
        finally:
            path.write_text(original)
        verdict = "KILLED" if code != 0 else "SURVIVED"
        results.append((name, verdict, f"exit {code}, {label(out)}"))
        print(f"  {verdict:9} {name}  ({results[-1][2]})", flush=True)

    killed = sum(1 for _, v, _ in results if v == "KILLED")
    print(f"\n{killed}/{len(results)} killed")
    return 0 if killed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
