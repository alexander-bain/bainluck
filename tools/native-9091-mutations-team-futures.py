#!/usr/bin/env python3
"""native — mutation battery for #9091 (team page Season Futures row).

Each mutant is applied to the tree, the #8622 test class is run, and the file is
restored byte-for-byte. A mutant whose needle is not found is REFUSED, never
counted as a kill. The clean tree runs LAST and must pass.
Usage: tools/native-9091-mutations-team-futures.py <SIM_UDID> [--dry-run] [--only M8[,M2...]]
`--only` runs the named mutants (plus the clean control) — native/338 used it to
finish M8 after native/337 was reaped mid-battery with M8 applied to the tree.
"""
import subprocess, sys, pathlib
ROOT = pathlib.Path(__file__).resolve().parent.parent
IOS = ROOT / "ios/Bain Luck"
P = "Bain Luck/Utilities/TeamFutureRowPresentation.swift"
M = "Bain Luck/Models/FuturesModels.swift"
MUTANTS = [
    ("M1 title is the market", P, "title: item.outcomeName,", "title: item.marketName,"),
    ("M2 settled ignored", P, "let settledWon = item.isWinner == true", "let settledWon = false"),
    ("M3 absent reads as won", P, "let settledWon = item.isWinner == true", "let settledWon = item.isWinner != false"),
    ("M4 rank kept when settled", P, "if !settledWon, let rank", "if let rank"),
    ("M5 bare round on live", P, ": formatProbability(p)", ": \"\\(Int((p * 100).rounded()))%\""),
    ("M6 settled hedged", P, 'settledWon ? "\\(percentNumber(p * 100))%"', "settledWon ? formatProbability(p)"),
    ("M7 isWinner not decoded", M, "case rank, totalOutcomes, resolutionDate, isWinner, matchedTeam", "case rank, totalOutcomes, resolutionDate, matchedTeam"),
]

def run(sim):
    cmd = ["xcodebuild", "test", "-scheme", "Bain Luck", "-destination", f"id={sim}",
           "-derivedDataPath", "/tmp/n9091-dd",
           "-only-testing:BainLuckTests/TeamFutureRowWebParity9091Tests",
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
