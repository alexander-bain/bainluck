#!/usr/bin/env python3
"""native/310 — mutation battery for the synthetic live edge (#7547/#7878 D).

Each mutant severs one rule in the shipped code; the suite must FAIL on every one.
Usage: python3 tools/native-310-mutations-live-edge.py <simulator-udid> [--dry-run]
Takes the LARGEST `Executed N tests` line (per-suite lines are not the total).
"""
import re, subprocess, sys, pathlib
ROOT = pathlib.Path(__file__).resolve().parent.parent / "ios" / "Bain Luck"
APP = ROOT / "Bain Luck"
SUITE = "BainLuckTests/ASyntheticLiveEdgeIsNotAReading7878Tests"
MUTANTS = [
    ("M1 the served flag is not decoded onto the point", "Components/OddsChartView.swift",
     "point.isLiveEdge = wp.liveEdge == true",
     "point.isLiveEdge = false"),
    ("M2 the edge counts as a reading (cadence + interior)", "Components/OddsChartView.swift",
     "let ordered = points.filter { !$0.isLiveEdge }.sorted { $0.date < $1.date }",
     "let ordered = points.sorted { $0.date < $1.date }"),
    ("M3 an unsupported trailing interval is still drawn", "Components/OddsChartView.swift",
     "            if !unsupported {\n                segments[segments.count - 1].append(liveEdge)",
     "            if unsupported || !unsupported {\n                segments[segments.count - 1].append(liveEdge)"),
    ("M4 a supported trailing interval no longer reaches now", "Components/OddsChartView.swift",
     "                segments[segments.count - 1].append(liveEdge)",
     "                _ = liveEdge"),
    ("M5 a lone edge is returned as a run of one", "Components/OddsChartView.swift",
     "        guard !ordered.isEmpty else { return [] }",
     "        guard !ordered.isEmpty else { return points.isEmpty ? [] : [points] }"),
    ("M6 Score Differential takes the edge's score", "Components/ScoreDifferentialChartView.swift",
     "for pt in points where pt.liveEdge != true {",
     "for pt in points {"),
]
def run(sim):
    cmd = ["xcodebuild", "test", "-scheme", "Bain Luck", "-destination", f"id={sim}",
           f"-only-testing:{SUITE}", "-collect-test-diagnostics", "never",
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
