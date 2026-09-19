#!/usr/bin/env python3
"""native/250 — mutation run for #7174 (the accuracy page's second column is a mean).

The ship is a RENAME plus the coupling that makes the rename hold, so the battery
is split along what a Swift test can and cannot see:

  * ARITHMETIC mutants (1-2). `CalibrationMath.mce` is a pure function over a pure
    value. Turn it into the maximum it used to be named after, or into the
    n-weighted mean beside it, and an ordinary assertion reaches it.

  * COUPLING mutants (3-5). 🔴 THE ONES THAT MATTER. The header is the widest ink
    in this column, and the width model and the view used to spell it separately.
    A column sized for `MCE` and filled with `Bucket` clips at the LEADING edge —
    it prints `ucket`, a plausible word, on every phone. These mutants re-open
    exactly that gap.

  * LABEL mutants (6-7). The word itself, and the Category table's literal box.

🪤 WHAT IS DELIBERATELY NOT MUTATED: the reader-visible SENTENCES (the hero's
secondary line, the section subhead, the benchmark caption). A pure suite cannot
read drawn text, and a guard that banned the word "maximum" would red-light the
honest fix — calibration/2611 wrote that guard first and it did exactly that,
because the honest way to withhold a claim in English is to negate it in front of
the reader (#4113's trap). Those three strings are carried by the 390pt and 375pt
frames in `artifacts/native-250/`, which is the same division of labour #3954
recorded in `CalibrationSourceTableGeometry`'s own header: the arithmetic model
that could have answered a fit question was measured wrong by ~21pt in the
safe-looking direction, so the frames own it and the tests own the rest.

A mutant that SURVIVES is a hole in the guard suite, not a curiosity. A mutant
whose anchor does not match is a NON-RESULT and is reported as one — a refused
patch runs the unmutated tree and prints a green indistinguishable from an
unkillable mutant.

Runs only from this lane's own worktree; every path is absolute.

Usage:  python3 -u tools/native-250-mutations-7174.py [--list]
        (`-u`: a buffered nohup log shows nothing for the whole run — n242 trap 5)
"""
import subprocess, sys, pathlib, signal, atexit

WORKTREE = pathlib.Path("/Users/bain/bainluck-dev/native")
ROOT = WORKTREE / "ios/Bain Luck"
MATH = ROOT / "Bain Luck/Utilities/CalibrationMath.swift"
GEOM = ROOT / "Bain Luck/Utilities/CalibrationSourceTableGeometry.swift"
VIEW = ROOT / "Bain Luck/Views/CalibrationView.swift"
SIM = "D2DA47A0-85F6-4BF8-AEFF-33146AE3EB05"

MEAN_BODY = "        return cal.reduce(0.0) { $0 + abs($1.error) } / Double(cal.count)"
MAX_BODY = "        return cal.map { abs($0.error) }.max() ?? 0"
NWEIGHTED_BODY = (
    "        let totalN = cal.reduce(0) { $0 + $1.n }\n"
    "        guard totalN > 0 else { return 0 }\n"
    "        return cal.reduce(0.0) { $0 + (Double($1.n) / Double(totalN)) * abs($1.error) }")

# The view's header row, verbatim. Mutant 3 reverts the drawn word alone, leaving
# the width model measuring the new one — the silent-clip direction.
DRAWN_BUCKET = "                    Text(header.bucket).frame(width: widths.mce, alignment: .trailing)"

# Each mutant: (name, file, find, replace-or-callable, expected-anchor-count, why)
MUTANTS = [
    ("1-the-column-becomes-the-maximum-it-was-named-after", MATH, MEAN_BODY, MAX_BODY, 1,
     "the value silently becomes a genuine worst-bucket maximum while every label on "
     "the surface now says it averages the buckets. The defect inverted: same two "
     "artefacts disagreeing, the other way round, and nothing on screen looks odd"),

    ("2-the-column-becomes-the-ECE-beside-it", MATH, MEAN_BODY, NWEIGHTED_BODY, 1,
     "two columns print the same digits under two headers. Nothing truncates, nothing "
     "errors, and the page quietly stops publishing a second statistic at all"),

    ("3-the-view-reverts-to-MCE-and-the-model-keeps-sizing-Bucket", VIEW,
     DRAWN_BUCKET,
     '                    Text("MCE").frame(width: widths.mce, alignment: .trailing)', 1,
     "🔴 THE SHIP REVERTED ON THE HALF A READER SEES. The header says MCE again over "
     "the same mean, in a column the model still sizes for the longer word — so it "
     "even looks tidy. This is the mutant the header constants exist for"),

    ("4-the-width-model-reverts-to-MCE-and-the-view-keeps-drawing-Bucket", GEOM,
     "            mce: columnWidth(header: Header.bucket, values: mce, typeSize: typeSize),",
     '            mce: columnWidth(header: "MCE", values: mce, typeSize: typeSize),', 1,
     "the drift the constants were introduced to make unreachable: a column measured "
     "against a word it does not draw. Trailing-aligned, so the header loses its "
     "FIRST characters and prints a plausible fragment rather than visible damage"),

    # Measured: `Bucket` draws 37.8pt at `.large` and the box is 46, so 46 is NOT
    # a defect and a 52→46 mutant is EQUIVALENT — it survived, correctly, and the
    # ship was reverted to 46 rather than the guard loosened to bless the widening.
    # The mutant that matters is a box the word genuinely does not fit.
    ("5-the-category-box-shrinks-below-the-word-it-holds", GEOM,
     "    static let categoryBucketColumnWidth: Double = 46",
     "    static let categoryBucketColumnWidth: Double = 30", 1,
     "the literal drops under the header's 37.8pt ink. Trailing-aligned, so the clip "
     "eats the FIRST characters and the column heads itself `cket` — in the one "
     "table #3954 never converted to a measured model"),

    ("6-the-header-goes-back-to-the-false-word", GEOM,
     '        static let bucket = "Bucket"',
     '        static let bucket = "MCE"', 1,
     "the whole rename undone at its single source of truth — both tables, both "
     "spellings, consistently wrong again, and the width model agreeing with itself"),

    ("7-the-header-loses-web-parity", GEOM,
     '        static let bucket = "Bucket"',
     '        static let bucket = "Per-bucket"', 1,
     "honest, and NOT the word web ships. #894 exists so the two surfaces describe "
     "one figure identically; web measured `Per-bucket` and rejected it on width"),
]

# TRAP (banked by native/234): on a FAILING run xcodebuild calls
# `simctl diagnose --timeout=600`, i.e. ~10 minutes per KILLED mutant.
XCB = ["xcodebuild", "test",
       "-project", str(ROOT / "Bain Luck.xcodeproj"),
       "-scheme", "Bain Luck",
       "-destination", f"platform=iOS Simulator,id={SIM}",
       "-disableAutomaticPackageResolution",
       "-collect-test-diagnostics", "never",
       "-only-testing:BainLuckTests/TheBucketColumnIsAMeanNotAMaximum7174Tests",
       "-only-testing:BainLuckTests/CalibrationSourceTableGeometryTests",
       "-only-testing:BainLuckTests/CalibrationMathTests",
       "-only-testing:BainLuckTests/CalibrationParityTests",
       "OTHER_SWIFT_FLAGS=$(inherited) -Xfrontend -disable-sandbox"]


def run_tests():
    r = subprocess.run(XCB, capture_output=True, text=True, cwd=str(ROOT))
    out = r.stdout + r.stderr
    return r.returncode, ("Executed" in out), out


_IN_FLIGHT = {}


def _restore_all(*_):
    for path, original in list(_IN_FLIGHT.items()):
        try:
            path.write_text(original)
            print(f"  restored {path.name} on exit")
        except Exception as e:      # noqa: BLE001 — best effort on the way down
            print(f"  !! COULD NOT RESTORE {path}: {e}\n     git checkout it BY HAND before committing")
        _IN_FLIGHT.pop(path, None)


atexit.register(_restore_all)
for _sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
    signal.signal(_sig, lambda s, f: (_restore_all(), sys.exit(128 + s)))


def main():
    if "--list" in sys.argv:
        for m in MUTANTS:
            print(f"  {m[0]}  [{m[1].name}]")
        return 0

    print("baseline (unmutated tree)")
    code, _, out = run_tests()
    if code != 0:
        print(f"  BASELINE IS RED (exit {code}) — fix that before reading any mutant")
        print("\n".join(out.splitlines()[-25:]))
        return 2
    print("  baseline GREEN\n")

    killed, survived = [], []
    for name, path, find, repl, expected, why in MUTANTS:
        original = path.read_text()
        # A refused patch prints a green indistinguishable from an unkillable
        # mutant, so refusal is reported as a NON-result, never a pass.
        found = original.count(find)
        if found != expected:
            print(f"  REFUSED  {name} — anchor occurs {found}x in {path.name}, expected {expected}")
            survived.append((name, "REFUSED"))
            continue
        mutated = repl(original) if callable(repl) else original.replace(find, repl)
        if mutated == original:
            print(f"  REFUSED  {name} — the patch changed nothing")
            survived.append((name, "REFUSED-NOOP"))
            continue
        try:
            _IN_FLIGHT[path] = original
            path.write_text(mutated)
            code, compiled, _ = run_tests()
            if code != 0:
                how = "assertions" if compiled else "COMPILE ONLY"
                print(f"  killed   {name}  [{how}]")
                if not compiled:
                    print("           ^ a compile kill does not prove the suite would catch it")
                killed.append(name)
            else:
                print(f"  SURVIVED {name}\n           {why}")
                survived.append((name, "SURVIVED"))
        finally:
            path.write_text(original)
            _IN_FLIGHT.pop(path, None)

    print(f"\n{len(killed)}/{len(MUTANTS)} killed")
    for n, s in survived:
        print(f"  {s}: {n}")

    dirty = subprocess.run(["git", "-C", str(WORKTREE), "diff", "--stat", "--", "ios/"],
                           capture_output=True, text=True).stdout.strip()
    print("\ntree on exit (expect ONLY this ship's own edits):")
    print("  " + (dirty.replace("\n", "\n  ") if dirty else "(clean)"))
    return 0 if not survived else 1


if __name__ == "__main__":
    sys.exit(main())
