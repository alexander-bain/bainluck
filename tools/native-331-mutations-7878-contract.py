#!/usr/bin/env python3
"""native/331 — mutation battery for the phone's #7878 evidence-contract consumer.

Each mutant severs one rule in the shipped code; the suites must FAIL on every one.
Usage: python3 tools/native-331-mutations-7878-contract.py <simulator-udid> [--dry-run]
Takes the LARGEST `Executed N tests` line (per-suite lines are not the total).
A mutant whose anchor is missing is REFUSED, never counted as a kill.

A KILL is only a COMPLETED run of the full expected suite (the baseline's test
count) with at least one assertion failure. A build failure, a missing test
summary, or a short run is INVALID — never a kill — and makes the battery exit
nonzero (Codex 024850Z review: the first M11 was a compile error counted as a
kill). xcodebuild's return code is kept and printed with every verdict.

Refuses the reserved simulators (tools/reserved-sim-guard.sh): a raw
`-destination id=` never passes through `bl_refuse_reserved_sim`, which is how
native/331's first battery ran on Alex's signed-in 76D961F0.
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
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    out = proc.stdout + proc.stderr
    counts = [(int(a), int(b)) for a, b in re.findall(r"Executed (\d+) tests?, with (\d+) failures?", out)]
    return (max(counts) if counts else None), out, proc.returncode
def refuse_reserved(sim):
    guard = pathlib.Path(__file__).resolve().parent / "reserved-sim-guard.sh"
    r = subprocess.run(["bash", "-c", '. "$1"; bl_is_reserved_sim "$2"', "_", str(guard), sim])
    if r.returncode == 0:
        print(f"REFUSED: {sim} is a reserved simulator (tools/reserved-sim-guard.sh)")
        sys.exit(7)
def main():
    sim = sys.argv[1]
    dry = "--dry-run" in sys.argv
    only = [a for a in sys.argv[2:] if a.startswith("M")]
    for name, rel, old, new in MUTANTS:
        n = (APP / rel).read_text().count(old)
        print(f"{name}: anchor found {n}x", flush=True)
        assert n == 1, f"NEEDLE NOT FOUND / not unique for {name}"
    if dry:
        print("dry-run: every anchor present exactly once; nothing mutated"); return 0
    refuse_reserved(sim)
    base, _, rc = run(sim)
    print(f"BASELINE {base} rc={rc}", flush=True)
    if not base or base[1] != 0 or base[0] == 0 or rc != 0:
        print("BASELINE INVALID — must be a completed green run"); return 2
    expected = base[0]
    killed, invalid, survived, ran = 0, 0, 0, 0
    for name, rel, old, new in MUTANTS:
        if only and name.split()[0] not in only: continue
        ran += 1
        path = APP / rel
        text = path.read_text()
        path.write_text(text.replace(old, new, 1))
        try:
            res, out, rc = run(sim)
        finally:
            path.write_text(text)
        if res is None or res[0] != expected:
            why = "build failed" if " error:" in out else "no/short test summary"
            verdict = f"INVALID ({why}; summary={res}, rc={rc}) — NOT a kill"; invalid += 1
        elif res[1] > 0:
            verdict = f"KILLED {res} rc={rc}"; killed += 1
        else:
            verdict = f"SURVIVED {res} rc={rc}"; survived += 1
        print(f"{name}: {verdict}", flush=True)
    print(f"TOTAL killed {killed}/{ran} · survived {survived} · invalid {invalid}")
    return 0 if killed == ran else 1
if __name__ == "__main__":
    sys.exit(main())
