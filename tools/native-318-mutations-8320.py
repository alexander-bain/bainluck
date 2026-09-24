#!/usr/bin/env python3
"""native/318 (#8320) — mutation battery for the one-freshness-status guards.

Each mutant re-introduces one shape of the defect; the named test class must go
red. Run from the worktree root. Restores every file whatever happens.
Usage: tools/native-318-mutations-8320.py [--dry-run]
"""
import subprocess, sys, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
APP = ROOT / "ios/Bain Luck/Bain Luck"
PAGE = APP / "Views/EventDetailView.swift"
CHART = APP / "Components/OddsChartView.swift"
SIM = "D2DA47A0-85F6-4BF8-AEFF-33146AE3EB05"

MUTANTS = [
    ("chart Live chip back", CHART,
     "        if EventState.isFinished(status) {\n            HStack(spacing: 4) {\n                Circle().fill(.secondary)",
     "        if status == \"live\" { Text(\"Live\") } else if EventState.isFinished(status) {\n            HStack(spacing: 4) {\n                Circle().fill(.secondary)"),
    ("polled arm painted as push dot", PAGE,
     "        case .polling:\n            Image(systemName: \"arrow.clockwise\")",
     "        case .polling:\n            LivePushDot(diameter: 22)\n            Image(systemName: \"arrow.clockwise\")"),
    ("indicator ignores the stream", PAGE,
     "return streamDelivering ? .streaming : .polling",
     "return .streaming"),
    ("fullscreen dot ungated", CHART,
     "if status == \"live\" && refreshStreaming {",
     "if status == \"live\" {"),
    ("toolbar loses its status", PAGE,
     "                            refreshStatus\n",
     "                            EmptyView()\n"),
]

def run_tests():
    cmd = ["xcodebuild", "-project", str(ROOT / "ios/Bain Luck/Bain Luck.xcodeproj"),
           "-scheme", "Bain Luck", "-destination", f"platform=iOS Simulator,id={SIM}",
           "-disableAutomaticPackageResolution",
           "OTHER_SWIFT_FLAGS=$(inherited) -Xfrontend -disable-sandbox",
           "-only-testing:BainLuckTests/ALiveEventPageSaysItsFreshnessOnce8320Tests",
           "-only-testing:BainLuckTests/EventRefreshTruthTests", "test"]
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
