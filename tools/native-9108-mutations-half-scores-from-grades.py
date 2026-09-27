#!/usr/bin/env python3
"""native — mutation battery for #9108 (settled half cards from graded rows).

Each mutant is applied to the tree, the #9108 test class is run, and the file is
restored byte-for-byte. A mutant whose needle is not found is REFUSED, never
counted as a kill. The clean tree runs LAST and must pass.
Usage: tools/native-9108-mutations-half-scores-from-grades.py <SIM_UDID> [--dry-run] [--only M2[,M5...]]
"""
import subprocess, sys, pathlib
ROOT = pathlib.Path(__file__).resolve().parent.parent
IOS = ROOT / "ios/Bain Luck"
H = "Bain Luck/Utilities/HalfScoresFromGrades.swift"
V = "Bain Luck/Views/EventDetailView.swift"
MUTANTS = [
    ("M1 spread rows never vote", H, 'if row.marketType == "half_spread" {', 'if false, row.marketType == "half_spread" {'),
    ("M2 spread line from served threshold", H, "guard let line = winsByMoreThan(outcome), onALine(line),", "guard winsByMoreThan(outcome) != nil, let line = row.threshold, onALine(line),"),
    ("M3 integer total lines vote", H, "let line = row.threshold, onALine(line),\n                      let verdict", "let line = row.threshold,\n                      let verdict"),
    ("M4 tie rows never vote", H, r'#"^\s*(tie|draw)\b"#', r'#"^\s*(xtie|xdraw)\b"#'),
    ("M5 first survivor wins", H, "if found != nil { return .none }", "if found != nil { continue }"),
    ("M6 fallback without isFinished", V, "guard fromHistory.first == nil, isFinished else", "guard fromHistory.first == nil else"),
    ("M7 grades read as open market", H, "marketResolved: true)", "marketResolved: false)"),
    ("M8 signed handicap legs vote", H, "guard let re = try? NSRegularExpression(pattern: #\"\\bwins\\b.*\\bby more than (\\d+(?:\\.\\d+)?)\"#",
     "guard let re = try? NSRegularExpression(pattern: #\"([+-]?\\d+\\.\\d+)\"#"),
]

def run(sim):
    cmd = ["xcodebuild", "test", "-project", "Bain Luck.xcodeproj", "-scheme", "Bain Luck",
           "-destination", f"platform=iOS Simulator,id={sim}", "-disableAutomaticPackageResolution",
           "-only-testing:BainLuckTests/ASettledHalfCardReadsItsResultFromGrades9108Tests", "-collect-test-diagnostics", "never",
           "OTHER_SWIFT_FLAGS=$(inherited) -Xfrontend -disable-sandbox"]
    r = subprocess.run(cmd, cwd=IOS, capture_output=True, text=True)
    return r.returncode, ("Testing cancelled because the build failed" in r.stdout or "** BUILD FAILED **" in r.stdout)

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
