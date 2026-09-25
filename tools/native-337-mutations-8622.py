#!/usr/bin/env python3
"""native/337 — mutation battery for #8622 (finished card + settled hero read prematch_odds).

Each mutant is applied to the tree, the #8622 test class is run, and the file is
restored byte-for-byte. A mutant whose needle is not found is REFUSED, never
counted as a kill. The clean tree runs LAST and must pass.
Usage: tools/native-337-mutations-8622.py <SIM_UDID> [--dry-run] [--only M8[,M2...]]
`--only` runs the named mutants (plus the clean control) — native/338 used it to
finish M8 after native/337 was reaped mid-battery with M8 applied to the tree.
"""
import subprocess, sys, pathlib
ROOT = pathlib.Path(__file__).resolve().parent.parent
IOS = ROOT / "ios/Bain Luck"
A = "Bain Luck/Utilities/PrematchReading.swift"
C = "Bain Luck/Components/EventCardView.swift"
D = "Bain Luck/Views/EventDetailView.swift"
MUTANTS = [
    ("M1 served reading ignored", A, "if let served = prematch, let home", "if false, let served = prematch, let home"),
    ("M2 endpoints accepted", A, "value > 0, value < 1", "value >= 0, value <= 1"),
    ("M3 word ignores the rung", A, 'isServed ? "Pre-match" : "Opened"', '"Opened"'),
    ("M4 card row reads the median", C, "? reading?.homeProbability\n            : (awayIsWithheld ? nil : reading?.awayProbability)",
        "? event.openingOdds?.homeProbability\n            : (awayIsWithheld ? nil : event.openingOdds?.awayProbability)"),
    ("M5 card row rounds the median", C, "renderedPercent: reading?.percents[side == .home ? 1 : 0]",
        "renderedPercent: side == .home ? openingPercents[1] : openingPercents[0]"),
    ("M6 settled bar draws the median", C, "if let reading = prematch {\n                ProbabilityBar(\n                    awayProb: reading.awayProbability,\n                    homeProb: reading.homeProbability,",
        "if let reading = prematch, let opening = event.openingOdds, let a = opening.awayProbability, let h = opening.homeProbability {\n                ProbabilityBar(\n                    awayProb: a,\n                    homeProb: h,"),
    ("M7 hero reads the median", D, "away: pregame.awayProbability,\n                            home: pregame.homeProbability,",
        "away: event.openingOdds?.awayProbability,\n                            home: event.openingOdds?.homeProbability,"),
    ("M8 hero word hard-coded", D, 'let pregameWord = pregame?.captionWord ?? "Opened"', 'let pregameWord = "Opened"'),
]

def run(sim):
    cmd = ["xcodebuild", "test", "-scheme", "Bain Luck", "-destination", f"id={sim}",
           "-derivedDataPath", "/tmp/n337-dd",
           "-only-testing:BainLuckTests/AFinishedCardPrintsTheNumberItsLineQuotes8622Tests",
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
