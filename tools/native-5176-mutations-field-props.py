#!/usr/bin/env python3
"""native — mutation battery for #5176 (iPhone Player Props "Most …" fields).

Each mutant is applied to the tree, PlayerPropsField5176Tests is run, and the file
is restored byte-for-byte. A mutant whose needle is not found exactly once is
REFUSED, never counted as a kill. The clean tree runs LAST and must pass.
Usage: tools/native-5176-mutations-field-props.py <SIM_UDID> [--dry-run] [--only M1[,M2...]]
"""
import subprocess, sys, pathlib
ROOT = pathlib.Path(__file__).resolve().parent.parent
IOS = ROOT / "ios/Bain Luck"
F = "Bain Luck/Utilities/PlayerPropsField.swift"
C = "Bain Luck/Components/PlayerPropsCardView.swift"
MUTANTS = [
    ("M1 Over/Under admitted", F, "return !answerWords.contains(outcome.lowercased())", "return true"),
    ("M2 threshold rows admitted", F, "guard prop.threshold == nil, fieldTitle", "guard fieldTitle"),
    ("M3 colon outcomes admitted", F, '!outcome.isEmpty, !outcome.contains(":")', "!outcome.isEmpty"),
    ("M4 any phrase is a field", F, 'guard phrase.lowercased().hasPrefix("most "),', "guard !phrase.isEmpty,"),
    ("M5 flat field drawn", F, "|| PlayerPropsPricing.isPricedLadder(field.candidates.map(\\.probability))", "|| true"),
    ("M6 grade ignored in order", F, "if aWon != bWon { return aWon }", ""),
    ("M7 pregame tiebreak dropped", F, "if aMark != bMark { return aMark > bMark }", ""),
    ("M8 duplicate names kept", F, "guard entry.seen.insert(name).inserted else { continue }", "_ = entry.seen.insert(name)"),
    ("M9 no-price leg kept", F, "let probability = prop.overProbability, probability.isFinite", "let probability = Optional(prop.overProbability ?? 0), probability.isFinite"),
    ("M10 caption says hitting", F, 'return "chance of leading"', 'return "chance of hitting"'),
    ("M11 card empty guard reverted", C, "if allPlayerCards.isEmpty && fields.isEmpty { EmptyView() }", "if allPlayerCards.isEmpty { EmptyView() }"),
    ("M12 card draws no field", C, "                            fieldView(field)\n", "                            EmptyView()\n"),
]

def run(sim):
    cmd = ["xcodebuild", "test", "-scheme", "Bain Luck", "-destination", f"id={sim}",
           "-derivedDataPath", "/tmp/n5176-dd",
           "-only-testing:BainLuckTests/PlayerPropsField5176Tests",
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
