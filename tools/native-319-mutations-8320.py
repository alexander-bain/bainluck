#!/usr/bin/env python3
"""native/319 (#8320 slice 2) — mutation battery for the live-hero declutter guards.

Each mutant re-introduces one shape of the defect; the named test class must go
red. Run from the worktree root. Restores every file whatever happens.
Usage: tools/native-319-mutations-8320.py [--dry-run]
"""
import subprocess, sys, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
APP = ROOT / "ios/Bain Luck/Bain Luck"
PAGE = APP / "Views/EventDetailView.swift"
SIM = "D2DA47A0-85F6-4BF8-AEFF-33146AE3EB05"

MUTANTS = [
    ("live hero keeps its context", PAGE,
     "        status != \"live\"\n",
     "        true\n"),
    ("bar repeats the score over the visible hero", PAGE,
     "        return heroBottom <= viewportTop\n",
     "        return true\n"),
    ("unmeasured hero drops the score", PAGE,
     "        guard let heroBottom else { return true }\n",
     "        guard let heroBottom else { return false }\n"),
    ("hero sparkline back", PAGE,
     "                        // #8320 — #3313's live sparkline was drawn here",
     "                        if isLive, let history = vm.history { LiveSparklineChart(points: OddsChartView.chartPoints(from: history)) }\n                        // #8320 — #3313's live sparkline was drawn here"),
    ("away record ungated on the live hero", PAGE,
     "if carriesContext, let record = event.awayTeamData?.record {",
     "if let record = event.awayTeamData?.record {"),
    ("Game Info hides when only handed-over facts exist", PAGE,
     "event.commenceTime != nil || !handedOver.isEmpty",
     "event.commenceTime != nil"),
    ("fallback bar title carries the score", PAGE,
     "            Text(scorelessTitle).font(.headline).lineLimit(1)",
     "            Text(dynamicTitle).font(.headline).lineLimit(1)"),
    ("inning table back in front of the chart", PAGE,
     "                    VStack(spacing: 0) {\n                        OddsChartView(",
     "                    if let history = vm.history { GameSegmentsView(history: history, homeTeam: event.homeTeam, awayTeam: event.awayTeam, homeTeamColor: .red, awayTeamColor: .blue) }\n                    VStack(spacing: 0) {\n                        OddsChartView("),
]

def run_tests():
    cmd = ["xcodebuild", "-project", str(ROOT / "ios/Bain Luck/Bain Luck.xcodeproj"),
           "-scheme", "Bain Luck", "-destination", f"platform=iOS Simulator,id={SIM}",
           "-disableAutomaticPackageResolution",
           "OTHER_SWIFT_FLAGS=$(inherited) -Xfrontend -disable-sandbox",
           "-only-testing:BainLuckTests/ALiveHeroCarriesTheStoryNotTheContext8320Tests", "test"]
    p = subprocess.run(cmd, capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr

def main():
    dry = "--dry-run" in sys.argv
    for name, path, old, new in MUTANTS:
        src = path.read_text()
        if src.count(old) != 1:
            print(f"UNAPPLIABLE {name}: anchor count {src.count(old)}"); sys.exit(3)
    if dry:
        print(f"dry-run: {len(MUTANTS)} mutants, every anchor found exactly once"); return
    killed = 0
    for name, path, old, new in MUTANTS:
        src = path.read_text()
        try:
            path.write_text(src.replace(old, new))
            rc, out = run_tests()
        finally:
            path.write_text(src)
        verdict = "KILLED" if rc != 0 and "** TEST FAILED **" in out else ("BUILD-BROKE" if "BUILD FAILED" in out else "SURVIVED")
        killed += verdict == "KILLED"
        fails = [l.strip() for l in out.splitlines() if "error: -[" in l or ": error: " in l and "Tests" in l][:2]
        print(f"{verdict:9} {name}  {fails[:1]}")
    print(f"{killed}/{len(MUTANTS)} killed")
    sys.exit(0 if killed == len(MUTANTS) else 1)

main()
