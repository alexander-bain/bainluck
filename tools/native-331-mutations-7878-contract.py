#!/usr/bin/env python3
"""native/331 — mutation battery for the phone's #7878 evidence-contract consumer.

Each mutant severs one rule in the shipped code; the suites must FAIL on every one.
Usage: python3 tools/native-331-mutations-7878-contract.py <simulator-udid> [--dry-run]
Takes the LARGEST `Executed N tests` line (per-suite lines are not the total).
A mutant whose anchor is missing is REFUSED, never counted as a kill.
"""
import re, subprocess, sys, pathlib
ROOT = pathlib.Path(__file__).resolve().parent.parent / "ios" / "Bain Luck"
APP = ROOT / "Bain Luck"
SUITES = ["BainLuckTests/TheServedEvidenceContractDecidesWhereTheLineBreaks7878Tests",
          "BainLuckTests/TheServedEvidenceContractRenderSmokeTests7878"]
C = "Components/OddsChartView.swift"
H = "Models/HistoryModels.swift"
MUTANTS = [
    ("M1 the contract is not put on the point", C,
     "point.servedEvidence = servedEvidence(for: wp, resolution: resolution)", "_ = resolution"),
    ("M2 an unknown contract version is read", H,
     "guard v == Self.knownVersion, let resolutionS,", "guard let resolutionS,"),
    ("M3 a non-positive resolution is read", H,
     "resolutionS.isFinite, resolutionS > 0 else", "resolutionS.isFinite else"),
    ("M4 a backfill/terminal/final/unknown kind's span extends coverage", C,
     "guard let evidence = wp.evidence, evidence.kind == \"observed\" else { return served }",
     "guard let evidence = wp.evidence else { return served }"),
    ("M5 covered_through is ignored", C,
     "served.coveredThrough = through", "_ = through"),
    ("M6 covered_through is never read by the segmenter", C,
     "let coveredUntil = from.servedEvidence?.coveredThrough ?? from.date", "let coveredUntil = from.date"),
    ("M7 pre-match intervals are judged", C,
     "let holeStart = max(coveredUntil, gameStart)", "let holeStart = coveredUntil; _ = gameStart"),
    ("M8 exactly G breaks", C,
     "to.timeIntervalSince(holeStart) > resolution", "to.timeIntervalSince(holeStart) >= resolution"),
    ("M9 a stale live edge is still drawn", C,
     "           !unknown(after: last, until: liveEdge.date) {", "           true {"),
    ("M10 the contract branch falls through to the heuristic", C,
     "return contractSegments(ordered,", "_ = contractSegments(ordered,"),
    ("M11 the blend is classified too", C,
     "points.append(ChartDataPoint(date: date, probability: p.homeProbability, source: \"aggregate\"))",
     "var blend = ChartDataPoint(date: date, probability: p.homeProbability, source: \"aggregate\")\n                if let contractResolution { blend.servedEvidence = ServedEvidence(resolution: contractResolution) }\n                points.append(blend)"),
    ("M12 a live_edge evidence kind is not an anchor", C,
     "point.isLiveEdge = point.isLiveEdge || wp.evidence?.kind == \"live_edge\"", "_ = 0"),
    ("M13 an unreadable evidence object throws (blanks the chart)", H,
     "        let c = try? decoder.container(keyedBy: CodingKeys.self)\n        kind =",
     "        let c: KeyedDecodingContainer<CodingKeys>? = try decoder.container(keyedBy: CodingKeys.self)\n        kind ="),
    ("M14 a backwards covered_through is accepted", C,
     "let at = wp.timestamp.asDate, through > at {", "let _ = wp.timestamp.asDate {"),
    ("M15 an unreadable evidence object is read as a plain reading kind", H,
     "kind = (try? c?.decodeIfPresent(String.self, forKey: .kind)) ?? nil", "kind = (try? c?.decodeIfPresent(String.self, forKey: .kind)) ?? \"observed\""),
]
def run(sim):
    cmd = ["xcodebuild", "test", "-scheme", "Bain Luck", "-destination", f"id={sim}",
           *[f"-only-testing:{s}" for s in SUITES], "-collect-test-diagnostics", "never",
           "OTHER_SWIFT_FLAGS=$(inherited) -Xfrontend -disable-sandbox"]
    out = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True).stdout
    counts = [(int(a), int(b)) for a, b in re.findall(r"Executed (\d+) tests?, with (\d+) failures?", out)]
    return (max(counts) if counts else None), out
def main():
    sim = sys.argv[1]
    dry = "--dry-run" in sys.argv
    for name, rel, old, new in MUTANTS:
        n = (APP / rel).read_text().count(old)
        print(f"{name}: anchor found {n}x", flush=True)
        assert n == 1, f"NEEDLE NOT FOUND / not unique for {name}"
    if dry:
        print("dry-run: every anchor present exactly once; nothing mutated"); return 0
    base, _ = run(sim)
    print(f"BASELINE {base}", flush=True)
    assert base and base[1] == 0, "baseline must be green"
    killed = 0
    only = [a for a in sys.argv[2:] if a.startswith("M")]
    for name, rel, old, new in MUTANTS:
        if only and name.split()[0] not in only: continue
        path = APP / rel
        text = path.read_text()
        path.write_text(text.replace(old, new, 1))
        try:
            res, out = run(sim)
        finally:
            path.write_text(text)
        if res is None:
            verdict = "KILLED (build failed)" if "error:" in out else "NO RESULT"
            if "error:" in out: killed += 1
        elif res[1] > 0:
            verdict = f"KILLED {res}"; killed += 1
        else:
            verdict = f"SURVIVED {res}"
        print(f"{name}: {verdict}", flush=True)
    print(f"TOTAL killed {killed}/{len(MUTANTS)}")
    return 0 if killed == len(MUTANTS) else 1
if __name__ == "__main__":
    sys.exit(main())
