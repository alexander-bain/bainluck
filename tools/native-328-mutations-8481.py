#!/usr/bin/env python3
"""native/328 (#8481 + #1833) — each mutant must turn OneControlOneWindowReadableClock8481Tests red.

Runs on the iOS 27 simulator (the label collision is iOS 27's framework placement).
"""
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
APP = ROOT / "ios/Bain Luck/Bain Luck"
DEST = "id=D57E90D1-35A8-4A09-88D5-C1A5E2C458A2"  # iPhone 18 Pro Max, iOS 27.0 — not reserved

MUTANTS = [
    ("wp-draws-outside-window", "Components/OddsChartView.swift",
     [("filtered = filtered.filter { SharedChartWindow.contains($0.date, in: forcedDomain) }",
       "_ = forcedDomain")]),
    ("score-draws-outside-window", "Components/ScoreDifferentialChartView.swift",
     [("let contained = merged.filter { SharedChartWindow.contains($0.date, in: forcedDomain) }",
       "let contained = merged")]),
    ("window-ignores-the-choice", "Utilities/SharedChartWindow.swift",
     [("start = min(actualStart, max(firstReading, earliestPlausibleStart))",
       "start = actualStart; _ = firstReading")]),
    ("all-has-no-floor", "Utilities/SharedChartWindow.swift",
     [("start = min(actualStart, max(firstReading, earliestPlausibleStart))",
       "start = min(actualStart, firstReading)")]),
    ("picker-not-the-pages", "Views/EventDetailView.swift",
     [("                                     selectedRange: $chartRange,\n", "")]),
    ("score-projection-ignores-choice", "Components/ScoreDifferentialChartView.swift",
     [("guard range == .all, let window else { return gameStart }",
       "guard range == .all, let window, false else { return gameStart }")]),
    ("labels-hang-like-ios27", "Components/OddsChartView.swift",
     [("return tickPositions.map { min(max($0, half), plotWidth - half) }",
       "return tickPositions.enumerated().map { i, x in i == tickPositions.count - 1 ? x - half : x + half }")]),
    ("labels-unclamped", "Components/OddsChartView.swift",
     [("return tickPositions.map { min(max($0, half), plotWidth - half) }",
       "return tickPositions.map { $0 }")]),
    ("ticks-not-on-whole-units", "Components/OddsChartView.swift",
     [("let first = opening.start == domain.lowerBound ? opening.start : opening.end",
       "let first = domain.lowerBound; _ = opening")]),
]

killed = 0
for name, rel, edits in MUTANTS:
    path = APP / rel
    orig = path.read_text()
    try:
        text = orig
        for a, b in edits:
            assert text.count(a) == 1, f"{name}: anchor count {text.count(a)} for {a[:50]!r}"
            text = text.replace(a, b)
        path.write_text(text)
        r = subprocess.run(
            ["xcodebuild", "test", "-project", "Bain Luck.xcodeproj", "-scheme", "Bain Luck",
             "-destination", DEST,
             "OTHER_SWIFT_FLAGS=$(inherited) -Xfrontend -disable-sandbox",
             "-only-testing:BainLuckTests/OneControlOneWindowReadableClock8481Tests"],
            cwd=ROOT / "ios/Bain Luck", capture_output=True, text=True,
            env={**__import__("os").environ, "TEST_RUNNER_TZ": "America/Los_Angeles"})
        out = r.stdout + r.stderr
        failing = sorted({line.split("-[")[1].split("]")[0].split(" ")[1]
                          for line in out.splitlines() if ": error: -[" in line})
        red = r.returncode == 65 and bool(failing)
        killed += red
        print(f"{name}: exit {r.returncode} -> {'KILLED by ' + ', '.join(failing) if red else 'SURVIVED'}",
              flush=True)
        if not red and r.returncode != 0:
            print("\n".join(l for l in out.splitlines() if "error:" in l)[:1500], flush=True)
    finally:
        path.write_text(orig)
print(f"{killed}/{len(MUTANTS)} killed")
sys.exit(0 if killed == len(MUTANTS) else 1)
