#!/usr/bin/env python3
"""native/309 — mutation battery for the #836/#837/#920 single-source live arm.

Each mutant severs one rule in the shipped code; the suite must FAIL on every one.
Usage: python3 tools/native-309-mutations-920-single-source.py <simulator-udid> [--dry-run]
Takes the LARGEST `Executed N tests` line (per-suite lines are not the total).
"""
import re, subprocess, sys, pathlib
ROOT = pathlib.Path(__file__).resolve().parent.parent / "ios" / "Bain Luck"
APP = ROOT / "Bain Luck"
SUITE = "BainLuckTests/ASingleSourceLiveChartKeepsItsPushSpeed920Tests"
MUTANTS = [
    ("M1 tie/older readings admitted", "Components/OddsChartView.swift",
     "let edge = edges[source], frame.date > edge else { continue }",
     "let edge = edges[source], frame.date >= edge.addingTimeInterval(-86400) else { continue }"),
    ("M2 unserved source minted", "Components/OddsChartView.swift",
     "let edge = edges[source], frame.date > edge else { continue }",
     "case let edge = edges[source] ?? .distantPast, frame.date > edge else { continue }"),
    ("M3 blend p stands in for the venue value", "Components/OddsChartView.swift",
     "extended.append(ChartDataPoint(date: frame.date, probability: value, source: source))",
     "_ = value; extended.append(ChartDataPoint(date: frame.date, probability: frame.homeProbability, source: source))"),
    ("M4 apply drops the venue reading", "ViewModels/EventDetailViewModel.swift",
     "source: frame.source, sourceProbability: frame.sourceValue),",
     "source: nil, sourceProbability: frame.sourceValue),"),
    ("M5 source series extended even where the backend blended", "Components/OddsChartView.swift",
     "        var extended = points\n        for frame in liveFrames where frame.date > publishedEdge {",
     "        var extended = extendingServedSourceSeries(points, with: liveFrames, servedSources: Set((history.winProbHistory ?? [:]).keys))\n        for frame in liveFrames where frame.date > publishedEdge {"),
    ("M6 out-of-range venue value admitted", "Utilities/LiveChartEdge.swift",
     "let value = sourceProbability, value.isFinite, (0...1).contains(value) {",
     "let value = sourceProbability, value.isFinite {"),
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
