#!/usr/bin/env python3
"""native/334 — mutation battery for the phone's #8565 readout (score_history fold + play attachment).

Each mutant severs one rule in the shipped code; the suites must FAIL on every one.
Usage: python3 tools/native-334-mutations-8565.py <simulator-udid> [--dry-run]
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
SUITES = ["BainLuckTests/ATouchdownOnTheChartShowsTheScoreItMade8565Tests",
          "BainLuckTests/ScrubReadoutDatesCarriedState925Tests"]
C = "Components/OddsChartView.swift"
H = "Models/HistoryModels.swift"
MUTANTS = [
    ("M1 score_history is not folded (ESPN only, the shipped defect)", C,
     "for sh in history.scoreHistory ?? [] {", "for sh in [ScoreHistoryPoint]() {"),
    ("M2 a score sighting wins an exact tie with an ESPN row", C,
     "date: date, rank: 0, homeScore: sh.homeScore", "date: date, rank: 2, homeScore: sh.homeScore"),
    ("M3 the tie rank is not consulted", C,
     "stateRows.sort { ($0.date, $0.rank) < ($1.date, $1.rank) }", "stateRows.sort { $0.date < $1.date }"),
    ("M4 the old symmetric +-60s attachment", C,
     "$0.date < cutoff && pointDate.timeIntervalSince($0.date) < momentMatchWindowSeconds",
     "abs($0.date.timeIntervalSince(pointDate)) < momentMatchWindowSeconds"),
    ("M5 the cutoff clause is dropped (a price before the play carries it)", C,
     "$0.date < cutoff && pointDate.timeIntervalSince($0.date) < momentMatchWindowSeconds",
     "pointDate.timeIntervalSince($0.date) < momentMatchWindowSeconds"),
    ("M6 the window clause is dropped (any older play attaches)", C,
     "$0.date < cutoff && pointDate.timeIntervalSince($0.date) < momentMatchWindowSeconds",
     "$0.date < cutoff"),
    ("M7 the earliest seen play wins, not the latest", C,
     "if let j = playsByTime.lastIndex(where: {", "if let j = playsByTime.firstIndex(where: {"),
    ("M8 the fallback never fires (a last play loses its marker)", C,
     "for (j, entry) in playsByTime.enumerated() where !attachedPlays.contains(j) {",
     "for (j, entry) in playsByTime.enumerated() where j < 0 && !attachedPlays.contains(j) {"),
    ("M9 the fallback fires for every play", C,
     "for (j, entry) in playsByTime.enumerated() where !attachedPlays.contains(j) {",
     "for (j, entry) in playsByTime.enumerated() where j >= 0 {"),
    ("M10 a seen play is never recorded as seen", C,
     "                attachedPlays.insert(j)\n", "                _ = j\n"),
    ("M11 a score sighting is folded a minute late", C,
     "date: date, rank: 0, homeScore: sh.homeScore", "date: date.addingTimeInterval(60), rank: 0, homeScore: sh.homeScore"),
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
