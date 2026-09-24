#!/usr/bin/env python3
"""native/313 — mutation battery for "Since Start" honouring commence_time_is_kickoff (#7878 D).

Each mutant severs one rule in the shipped code; the suite must FAIL on every one.
Usage: python3 tools/native-313-mutations-kickoff-flag.py <simulator-udid> [--dry-run]
Takes the LARGEST `Executed N tests` line (per-suite lines are not the total).
"""
import re, subprocess, sys, pathlib
ROOT = pathlib.Path(__file__).resolve().parent.parent / "ios" / "Bain Luck"
APP = ROOT / "Bain Luck"
SUITE = "BainLuckTests/SinceStartHonorsTheKickoffFlag7878Tests"
MUTANTS = [
    ("M1 the served false is ignored (cut at the expiration hour)", "Components/OddsChartView.swift",
     "        guard commenceTimeIsKickoff != false else { return nil }",
     "        guard true else { return nil }"),
    ("M2 an absent key vetoes too (older payloads lose the cut)", "Components/OddsChartView.swift",
     "        guard commenceTimeIsKickoff != false else { return nil }",
     "        guard commenceTimeIsKickoff == true else { return nil }"),
    ("M3 Since Start is offered with no cut", "Components/OddsChartView.swift",
     "        isGameStarted && kickoff != nil",
     "        isGameStarted"),
    ("M4 the window cuts whatever the range", "Components/OddsChartView.swift",
     "        guard range == .sinceStart, let startDate = kickoff else { return points }",
     "        guard let startDate = kickoff else { return points }"),
    ("M5 the window never cuts", "Components/OddsChartView.swift",
     "        let filtered = points.filter { $0.date >= startDate }",
     "        let filtered = points.filter { $0.date >= startDate || true }"),
]
def run(sim):
    cmd = ["xcodebuild", "test", "-scheme", "Bain Luck", "-destination", f"id={sim}",
           f"-only-testing:{SUITE}", "-collect-test-diagnostics", "never",
           "-derivedDataPath", "/tmp/n313-dd", "-disableAutomaticPackageResolution",
           "-clonedSourcePackagesDirPath", str(pathlib.Path.home() / "Library/Developer/Xcode/DerivedData/Bain_Luck-cwkxplfeuucvrvbplvqqlcgmpcgx/SourcePackages"),
           "OTHER_SWIFT_FLAGS=$(inherited) -Xfrontend -disable-sandbox"]
    out = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True).stdout
    counts = [(int(a), int(b)) for a, b in re.findall(r"Executed (\d+) tests?, with (\d+) failures?", out)]
    return max(counts) if counts else None, out
def main():
    sim = sys.argv[1]
    dry = "--dry-run" in sys.argv
    for name, rel, old, new in MUTANTS:
        text = (APP / rel).read_text()
        n = text.count(old)
        print(f"{name}: anchor found {n}x", flush=True)
        assert n == 1, f"anchor for {name} not unique/absent"
    if dry:
        print("dry-run: every anchor present exactly once; nothing mutated"); return 0
    base, _ = run(sim)
    print(f"BASELINE {base}", flush=True)
    killed = 0
    for name, rel, old, new in MUTANTS:
        path = APP / rel; orig = path.read_text()
        try:
            path.write_text(orig.replace(old, new))
            res, out = run(sim)
        finally:
            path.write_text(orig)
        verdict = "KILLED" if res and res[1] > 0 else ("BUILD-FAIL" if res is None else "SURVIVED")
        killed += verdict == "KILLED"
        print(f"{name}: {res} {verdict}", flush=True)
    print(f"{killed}/{len(MUTANTS)} killed by assertions")
    return 0 if killed == len(MUTANTS) else 1
sys.exit(main())
