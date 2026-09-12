#!/usr/bin/env python3
"""#5656 mutation sweep — is the MARGIN MAPS / TOTAL MAPS guard vacuous?

A source-scan guard's failure mode is passing because it read nothing, so M6
mutates the TEST's own scan path: if the anti-vacuity assertion is doing its
job, a guard pointed at a missing file must go RED, not green.

Each mutant is an EXACT string replacement and the script asserts the pattern
matched exactly once before writing (rig note 14).

Run from the worktree root:  python3 tools/n132-mutations-5656.py
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VIEW = ROOT / "ios/Bain Luck/Bain Luck/Components/MarketMapView.swift"
TEST = ROOT / "ios/Bain Luck/BainLuckTests/MarketMapColumnHeaders5656Tests.swift"

WIDE_MARGIN = "VStack(alignment: .leading, spacing: 6) { marginCards }"
WIDE_TOTAL = "VStack(alignment: .leading, spacing: 6) { totalCards }"
HEADER = ('Text("%s")\n'
          '                                .font(.system(size: 11, weight: .heavy))\n'
          '                                .foregroundStyle(.secondary)\n'
          '                                .tracking(1)\n'
          '                            ')

MUTANTS = [
    ("M1  MARGIN MAPS header restored on the iPad",
     VIEW, WIDE_MARGIN,
     "VStack(alignment: .leading, spacing: 6) { " + (HEADER % "MARGIN MAPS") + "marginCards }"),
    ("M2  TOTAL MAPS header restored on the iPad",
     VIEW, WIDE_TOTAL,
     "VStack(alignment: .leading, spacing: 6) { " + (HEADER % "TOTAL MAPS") + "totalCards }"),
    ("M3  a DIFFERENTLY worded esports header ('GOAL MAPS')",
     VIEW, WIDE_TOTAL,
     "VStack(alignment: .leading, spacing: 6) { " + (HEADER % "GOAL MAPS") + "totalCards }"),
    ("M4  sharing broken — wide branch inlines the cards again",
     VIEW, WIDE_MARGIN,
     "VStack(alignment: .leading, spacing: 6) { fullMarginMap; halfMarginMaps }"),
    ("M5  a card dropped, not just its header",
     VIEW, "    private var totalCards: some View {\n        fullTotalMap\n        halfTotalMaps\n    }",
           "    private var totalCards: some View {\n        fullTotalMap\n    }"),
    ("M6  the scan itself pointed at a file that does not exist",
     TEST, '.appendingPathComponent("MarketMapView.swift")',
           '.appendingPathComponent("MarketMapViewTypo.swift")'),
]

TEST_CMD = [
    "xcodebuild", "test",
    "-project", "ios/Bain Luck/Bain Luck.xcodeproj",
    "-scheme", "Bain Luck",
    "-destination", "platform=iOS Simulator,name=iPhone 17",
    "-disableAutomaticPackageResolution",
    "-only-testing:BainLuckTests/MarketMapColumnHeaders5656Tests",
    "OTHER_SWIFT_FLAGS=$(inherited) -Xfrontend -disable-sandbox",
]


def run_tests():
    p = subprocess.run(TEST_CMD, cwd=ROOT, capture_output=True, text=True, timeout=900)
    return p.returncode == 0


def main():
    killed, survived = [], []
    for name, path, old, new in MUTANTS:
        original = path.read_text()
        hits = original.count(old)
        assert hits == 1, f"{name}: pattern matched {hits} times, expected exactly 1 — refusing to write"
        try:
            path.write_text(original.replace(old, new))
            ok = run_tests()
            (survived if ok else killed).append(name)
            print(f"  {'SURVIVED' if ok else 'KILLED  '}  {name}", flush=True)
        finally:
            path.write_text(original)

    print(f"\n{len(killed)}/{len(MUTANTS)} killed")
    if survived:
        print("SURVIVORS:")
        for s in survived:
            print(f"  - {s}")
    return 1 if survived else 0


if __name__ == "__main__":
    sys.exit(main())
