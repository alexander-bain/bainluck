#!/usr/bin/env python3
"""native/288 — mutation battery for #4445 (the Evolution card at large text).

Same two harness rules as `native-286-mutations-7722.py`: gate on the EXIT CODE
(65 xcodebuild), and match `with (\\d+) failures?` — xcodebuild writes "with 1
failure", SINGULAR, and a plural-only regex reads a sibling class's "0 failures"
and reports a killed mutant as survived. Every anchor is required to match
EXACTLY ONCE; a bad anchor wastes a whole mutant slot and reads as a survivor.

The mutants worth naming:

  * M1 is the defect itself — the terminal arm is taken away again, so
    `ViewThatFits` falls through to a `stackedRows` that does not fit. If
    anything survives it must not be this one.
  * M2/M3 keep the terminal arm but stop ONE group wrapping. They are here
    because "there is an arm" and "the arm fits" are different claims, and the
    range group and the `Top N` group are independently over-wide (414.5 and
    383.5 against 343 at .accessibility5).
  * M5 restores the arrangement the OLD terminal arm had — `Sum` and `Top N`
    sharing a row — inside the new one. It is the plausible half-fix.
  * M6 empties the guard's swept type sizes. Three assertions sweep that list,
    and an empty one makes all three pass without measuring anything. It is
    killed by the non-vacuity test added beside them, and by nothing else.
  * M7 gives the STRAWMAN the fix, so the control can no longer reproduce the
    defect. It proves the control is load-bearing rather than decorative.
  * M8 makes the camera ignore the type size it is handed. The acceptance
    assertions then pass vacuously (everything fits at .large) and only the
    control can tell — which is the point of having one.
"""

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VIEW = ROOT / "ios/Bain Luck/Bain Luck/Components/EvolutionChartView.swift"
GUARD = (ROOT / "ios/Bain Luck/BainLuckTests"
         / "TheEvolutionCardFitsTheScreenAtEveryTypeSize4445Tests.swift")
SIM = "D0AD5FA3-7B48-4D21-AFB4-E8EB30B1586A"

MUTANTS = [
    ("M1 the defect restored — the terminal wrapping arm is taken away",
     VIEW,
     "                stackedRows(chipPadding: Self.chipPaddings[0])\n"
     "                wrappedRows(chipPadding: Self.chipPaddings[0])\n",
     "                stackedRows(chipPadding: Self.chipPaddings[0])\n"),

    ("M2 the terminal arm stops wrapping the RANGE chips",
     VIEW,
     "            rangeGroup(chipPadding: chipPadding, wraps: true)",
     "            rangeGroup(chipPadding: chipPadding)"),

    ("M3 the terminal arm stops wrapping the `Top N` chips",
     VIEW,
     "            topGroup(chipPadding: chipPadding, wraps: true)",
     "            topGroup(chipPadding: chipPadding)"),

    ("M4 ChipStrip ignores `wraps` — nothing can wrap anywhere",
     VIEW,
     "        if wraps {\n            FlowLayout(spacing: 0) { content }",
     "        if false {\n            FlowLayout(spacing: 0) { content }"),

    ("M5 the plausible half-fix — `Sum` and `Top N` share a row again",
     VIEW,
     "            sumToggle(chipPadding: chipPadding)\n"
     "            topGroup(chipPadding: chipPadding, wraps: true)\n"
     "        }\n        .frame(maxWidth: .infinity, alignment: .leading)",
     "            HStack(spacing: 8) {\n"
     "                sumToggle(chipPadding: chipPadding)\n"
     "                topGroup(chipPadding: chipPadding, wraps: true)\n"
     "            }\n"
     "        }\n        .frame(maxWidth: .infinity, alignment: .leading)"),

    ("M6 the GUARD's swept type sizes are emptied (the vacuity this guard pins)",
     GUARD,
     "    private let everyTypeSize = DynamicTypeSize.allCases",
     "    private let everyTypeSize: [DynamicTypeSize] = []"),

    ("M7 the STRAWMAN is given the fix, so it can no longer reproduce the defect",
     GUARD,
     "                    bar.stackedRows(chipPadding: EvolutionControlBar.chipPaddings[0])\n"
     "                }",
     "                    bar.stackedRows(chipPadding: EvolutionControlBar.chipPaddings[0])\n"
     "                    bar.wrappedRows(chipPadding: EvolutionControlBar.chipPaddings[0])\n"
     "                }"),

    ("M8 the camera ignores the type size it is handed",
     GUARD,
     "        let host = hostForMeasurement(view, at: size)\n"
     "        host.view.frame = CGRect(x: 0, y: 0, width: width, height: 2000)",
     "        let host = hostForMeasurement(view, at: .large)\n"
     "        host.view.frame = CGRect(x: 0, y: 0, width: width, height: 2000)"),
]


def run_swift():
    p = subprocess.run(
        ["xcodebuild", "-project", str(ROOT / "ios/Bain Luck/Bain Luck.xcodeproj"),
         "-scheme", "Bain Luck", "-destination", f"id={SIM}",
         "-disableAutomaticPackageResolution",
         "-only-testing:BainLuckTests/"
         "TheEvolutionCardFitsTheScreenAtEveryTypeSize4445Tests",
         "-only-testing:BainLuckTests/EvolutionControlBarLayoutTests",
         "-only-testing:BainLuckTests/EvolutionLeaderboardWidthTests",
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
