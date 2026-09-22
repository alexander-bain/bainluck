#!/usr/bin/env python3
"""native/284 — mutation battery for #7780 (grid relegation colour polarity).

Same two harness rules as `native-284-mutations-7759.py`: gate on the EXIT CODE
(65 xcodebuild / 1 jest), and match `with (\\d+) failures?` — xcodebuild writes
"with 1 failure", SINGULAR, and a plural-only regex reads a sibling class's
"0 failures" and reports a killed mutant as survived.

The mutants worth naming here are the ones that keep the specimen passing while
breaking the other half of the bug — M2 (relegation always bad news, so a
FALLING risk still prints red) is the one a one-directional test would miss.
"""

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LIB = ROOT / "ios/Bain Luck/Bain Luck/Utilities/GridColumnPolarity.swift"
GRID = ROOT / "ios/Bain Luck/Bain Luck/Components/ChampionshipPathView.swift"
SIM = "D2DA47A0-85F6-4BF8-AEFF-33146AE3EB05"

MUTANTS = [
    ("M1 relegation is no longer adverse (the original bug, restored)",
     LIB, 'static let adverseColumnKeys: Set<String> = ["relegation"]',
     'static let adverseColumnKeys: Set<String> = []', "swift"),
    ("M2 relegation is ALWAYS bad news, so a falling risk still prints red",
     LIB, "trend > 0 ? risingIsGood(columnKey) : !risingIsGood(columnKey)",
     "trend > 0 ? risingIsGood(columnKey) : false", "swift"),
    ("M3 the whole grid inverts (specimen passes, everything else flips)",
     LIB, "return !adverseColumnKeys.contains(columnKey)",
     "return adverseColumnKeys.contains(columnKey)", "swift"),
    ("M4 an absent key stops defaulting to rising-is-good",
     LIB, "guard let columnKey, !columnKey.isEmpty else { return true }",
     "guard let columnKey, !columnKey.isEmpty else { return false }", "swift"),
    ("M5 the label is accepted as a key",
     LIB, 'static let adverseColumnKeys: Set<String> = ["relegation"]',
     'static let adverseColumnKeys: Set<String> = ["relegation", "Relegated"]', "jest"),
    ("M6 the view stops asking and paints on the raw trend again",
     GRID,
     "GridColumnPolarity.isGoodNews(trend: trend, columnKey: stage.key) ? .green : .red",
     "trend > 0 ? .green : .red", "jest"),
    ("M7 the view asks about the LABEL instead of the key",
     GRID, "columnKey: stage.key", "columnKey: stage.label", "jest"),
    ("M8 the arrow is flipped to agree with the colour",
     GRID, 'Image(systemName: trend > 0 ? "arrow.up" : "arrow.down")',
     'Image(systemName: GridColumnPolarity.isGoodNews(trend: trend, columnKey: stage.key) ? "arrow.up" : "arrow.down")',
     "jest"),
]


def run_jest():
    p = subprocess.run(
        ["npx", "jest", "--testPathPatterns=gridColumnPolarityParity7780"],
        cwd=ROOT / "frontend", capture_output=True, text=True,
    )
    return p.returncode, p.stdout + p.stderr


def run_swift():
    p = subprocess.run(
        ["xcodebuild", "-project", str(ROOT / "ios/Bain Luck/Bain Luck.xcodeproj"),
         "-scheme", "Bain Luck", "-destination", f"id={SIM}",
         "-disableAutomaticPackageResolution",
         "-only-testing:BainLuckTests/GridRelegationPolarity7780Tests",
         "OTHER_SWIFT_FLAGS=$(inherited) -Xfrontend -disable-sandbox", "test"],
        capture_output=True, text=True,
    )
    return p.returncode, p.stdout + p.stderr


COUNT = re.compile(r"with (\d+) failures?")


def label(out):
    hits = [int(m) for m in COUNT.findall(out)]
    return f"{sum(hits)} failing assertion group(s)" if hits else "no count line"


def main():
    results = []
    for name, path, find, repl, runner in MUTANTS:
        original = path.read_text()
        if original.count(find) != 1:
            results.append((name, "ERROR", f"anchor matches {original.count(find)}x, want 1"))
            print(f"  {results[-1][1]:9} {name}  ({results[-1][2]})", flush=True)
            continue
        path.write_text(original.replace(find, repl, 1))
        try:
            code, out = run_jest() if runner == "jest" else run_swift()
        finally:
            path.write_text(original)
        expected = 1 if runner == "jest" else 65
        if code == expected:
            verdict, detail = "KILLED", f"{runner} exit {code} — {label(out)}"
        elif code == 0:
            verdict, detail = "SURVIVED", f"{runner} exit 0 — NO TEST NOTICED"
        else:
            verdict, detail = "ERROR", f"{runner} exit {code} — harness, not a verdict"
        results.append((name, verdict, detail))
        print(f"  {verdict:9} {name}  ({detail})", flush=True)

    killed = sum(1 for _, v, _ in results if v == "KILLED")
    print(f"\n{killed}/{len(MUTANTS)} killed")
    for n, v, d in results:
        if v != "KILLED":
            print(f"  {v}: {n} — {d}")
    return 0 if killed == len(MUTANTS) else 1


if __name__ == "__main__":
    sys.exit(main())
