#!/usr/bin/env python3
"""native/9067 — mutation battery for #9067 (Game Segments reads the stored line score).

Each mutant is applied to the tree, the #8622 test class is run, and the file is
restored byte-for-byte. A mutant whose needle is not found is REFUSED, never
counted as a kill. The clean tree runs LAST and must pass.
Usage: tools/native-9067-mutations-line-score.py <SIM_UDID> [--dry-run] [--only M8[,M2...]]
"""
import subprocess, sys, pathlib
ROOT = pathlib.Path(__file__).resolve().parent.parent
IOS = ROOT / "ios/Bain Luck"
S = "Bain Luck/Utilities/StoredLineScore.swift"
P = "Bain Luck/Utilities/PeriodLabel.swift"
MUTANTS = [
    ("M1 stale running period keeps its number", S, "            cells[lastPlayed] = .unknown\n", ""),
    ("M2 arrays past the scoreboard accepted", S, "        if known > total { return false }\n", ""),
    ("M3 no baseball X", S, "                               ? homePeriods.count : nil),", "                               ? nil : nil),"),
    ("M4 hockey fifth entry named", S, "maxPeriods = entry.regulation + 1", "maxPeriods = entry.regulation + 9"),
    ("M5 soccer extra time named", S, "maxPeriods = entry.regulation\n", "maxPeriods = entry.regulation + 9\n"),
    ("M6 null read as zero", S, "                guard let points = periods[index] else {\n                    cells.append(.unknown)", "                guard let points = periods[index] else {\n                    cells.append(.score(0))"),
    ("M7 second extra period called OT", P, 'return extra == 1 ? "OT" : "\\(extra)OT"', 'return "OT"'),
    ("M8 decode throws on a bad box score", S, "        guard let container = try? decoder.container(keyedBy: CodingKeys.self) else {", "        guard let container = Optional(try decoder.container(keyedBy: CodingKeys.self)) else {"),
    ("M9 future period printed as a gap", S, "cells.append(isFinished ? .unknown : .notPlayed)", "cells.append(.unknown)"),
]

def run(sim):
    cmd = ["xcodebuild", "test", "-scheme", "Bain Luck", "-destination", f"id={sim}",
           "-derivedDataPath", "/tmp/n9067-dd",
           "-only-testing:BainLuckTests/GameSegmentsReadsTheStoredLineScore9067Tests",
           "OTHER_SWIFT_FLAGS=$(inherited) -Xfrontend -disable-sandbox"]
    r = subprocess.run(cmd, cwd=IOS, capture_output=True, text=True)
    return r.returncode, ("Testing cancelled because the build failed" in r.stdout)

def main():
    sim = sys.argv[1]; dry = "--dry-run" in sys.argv
    only = sys.argv[sys.argv.index("--only") + 1].split(",") if "--only" in sys.argv else None
    chosen = [m for m in MUTANTS if only is None or m[0].split()[0] in only]
    results = []
    for name, rel, needle, repl in chosen:
        p = IOS / rel; orig = p.read_bytes(); text = orig.decode()
        if text.count(needle) != 1:
            results.append((name, f"REFUSED (needle count {text.count(needle)})")); continue
        if dry: results.append((name, "applies")); continue
        p.write_text(text.replace(needle, repl))
        try:
            rc, build_failed = run(sim)
        finally:
            p.write_bytes(orig)
        assert p.read_bytes() == orig
        results.append((name, "KILLED (build)" if build_failed else ("KILLED" if rc != 0 else "SURVIVED")))
        print(name, results[-1][1], flush=True)
    if not dry:
        rc, _ = run(sim)
        results.append(("clean control", "PASS" if rc == 0 else f"FAIL rc={rc}"))
    for n, v in results: print(f"{n}: {v}")
    killed = sum(1 for _, v in results if v.startswith("KILLED"))
    print(f"{killed}/{len(chosen)} killed")
    bad = any(v.startswith(("SURVIVED", "REFUSED", "FAIL")) for _, v in results)
    sys.exit(1 if bad else 0)

main()
