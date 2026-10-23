#!/usr/bin/env python3
"""native — mutation battery for #11493 (team page reads the grid's out verdict).

Each mutant is applied to the tree, the #11493 test class is run, and the file is
restored byte-for-byte. A mutant whose needle is not found is REFUSED, never
counted as a kill. The clean tree runs LAST and must pass.
Usage: tools/native-11493-mutations-out-verdict.py <SIM_UDID> [--dry-run] [--only M8[,M2...]]
"""
import subprocess, sys, pathlib
ROOT = pathlib.Path(__file__).resolve().parent.parent
IOS = ROOT / "ios/Bain Luck"
P = "Bain Luck/Utilities/TeamFutureRowPresentation.swift"
R = "Bain Luck/Utilities/TeamDivisionRace.swift"
M = "Bain Luck/Models/FuturesModels.swift"
S = "Bain Luck/Models/SearchModels.swift"
MUTANTS = [
    ("M1 residual price kept under a verdict", P, "if verdict != nil {", "if false {"),
    ("M2 out ignored", P, "let out = verdict == .eliminated", "let out = false"),
    ("M3 rank kept when out", P, "if !settledWon, !out, let rank", "if !settledWon, let rank"),
    ("M4 eliminated step prints nothing", P, "case .eliminated: return .out", "case .eliminated: return .none"),
    ("M5 grid won ignored", P, "let settledWon = graded || verdict == .won", "let settledWon = graded"),
    ("M6 verdict outranks a graded result", P, "let verdict = graded ? nil : item.gridVerdict", "let verdict = item.gridVerdict"),
    ("M7 decided step keeps its rank", R, "guard entry.gridVerdict == nil else { return nil }", ""),
    ("M8 priceless decided step lets the row back", R, "if $0.gridVerdict != nil { return true }", ""),
    ("M9 futures state not decoded", M, "        case state\n", ""),
    ("M10 path state not decoded", S, "var state: String? = nil", "let state: String? = nil"),
]

def run(sim):
    cmd = ["xcodebuild", "test", "-scheme", "Bain Luck", "-destination", f"id={sim}",
           "-derivedDataPath", "/tmp/native-10955-dd",
           "-only-testing:BainLuckTests/TeamPageReadsTheGridOutVerdict11493Tests",
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
