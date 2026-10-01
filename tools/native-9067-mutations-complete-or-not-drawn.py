#!/usr/bin/env python3
"""native — mutation battery for #9067 rage #165 (Game Segments is complete or not drawn).

Each mutant is applied to the tree, the guard test class is run, and the file is
restored byte-for-byte. A mutant whose needle is not found is REFUSED, never
counted as a kill. The clean tree runs LAST and must pass.
Usage: tools/native-9067-mutations-complete-or-not-drawn.py <SIM_UDID> [--dry-run] [--only M1[,M2...]]
"""
import subprocess, sys, pathlib
ROOT = pathlib.Path(__file__).resolve().parent.parent
IOS = ROOT / "ios/Bain Luck"
S = "Bain Luck/Utilities/StoredLineScore.swift"
V = "Bain Luck/Views/EventDetailView.swift"
MUTANTS = [
    ("M1 stored path draws a gap", V,
     "        ), StoredLineScore.isDrawable(home: columns.map(\\.home), away: columns.map(\\.away)) {\n",
     "        ) {\n"),
    ("M2 half-inning path draws a gap", V,
     "                ), StoredLineScore.isDrawable(home: squared.home, away: squared.away)\n                else { return nil }",
     "                ) else { return nil }"),
    ("M3 generic path draws a gap", V,
     "        guard StoredLineScore.isDrawable(home: squared.home, away: squared.away),\n",
     "        guard true,\n"),
    ("M4 innings to come stay gaps", V, "        if !isFinished {\n            for index in segments.indices where index > lastObservedIndex {",
     "        if false {\n            for index in segments.indices where index > lastObservedIndex {"),
    ("M5 rule reads one row", S, "        !home.contains(.unknown) && !away.contains(.unknown)\n", "        !home.contains(.unknown)\n"),
    ("M6 caption explains the gap again", V, '                    Text("Score by period")\n',
     '                    Text("Score by period · · = not recorded")\n'),
]

def run(sim):
    cmd = ["xcodebuild", "test", "-scheme", "Bain Luck", "-destination", f"id={sim}",
           "-derivedDataPath", "/tmp/n9067b-dd",
           "-only-testing:BainLuckTests/GameSegmentsIsCompleteOrNotDrawn9067Tests",
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
