#!/usr/bin/env python3
"""native/256 — mutation run for #7285 (a null 24h change spoken as "unchanged").

The ship is four decisions, and they pull in OPPOSITE directions, which is the
whole reason this needs mutating rather than eyeballing:

  * absence must stop being spoken as zero          (the defect)
  * a MEASURED zero must keep being spoken as zero  (#5899, the over-application)
  * the DRAWN delta must treat both alike           (#7285 asked for no visual move)
  * the DRAWN price must stop treating both alike   (a null printed a flat `0%`)

A suite that only checks the first of those passes happily on a fix that deletes
"unchanged over 24 hours" outright, and that fix is wrong. Mutants 2, 4 and 5 are
the ones aimed at that hole.

🔴 MUTANTS 6 AND 7 ARE THE ONES THAT MATTER. They are the defect restored at the
CALL SITE — one `?? 0` put back in `EvolutionLeaderboardRow` — and they COMPILE,
because a `Double` promotes to `Double?` silently. No behavioural assertion on the
geometry can see them: every function still behaves, the row just stops handing
them the truth. They are killed only by
`ANullChangeIsNotSpokenAsUnchanged7285Tests.testTheRowCarriesTheOptionalToBothLabels`,
which scans the call site the way #5899's and #5949's scans do. That is #4624's
shape, and it is why the scan is in the suite at all.

A mutant that SURVIVES is a hole in the guard suite, not a curiosity.

Runs only from this lane's own worktree; every path is absolute.

Usage:  python3 tools/native-256-mutations-7285.py [--list]
"""
import subprocess, sys, pathlib, signal, atexit

WORKTREE = pathlib.Path("/Users/bain/bainluck-dev/native")
ROOT = WORKTREE / "ios/Bain Luck"
GEOM = ROOT / "Bain Luck/Utilities/EvolutionLeaderboardGeometry.swift"
ROW = ROOT / "Bain Luck/Components/EvolutionChartView.swift"
SIM = "D2DA47A0-85F6-4BF8-AEFF-33146AE3EB05"

# (name, file, find, replace, why-it-matters)
MUTANTS = [
    ("1-the-defect-verbatim-absence-spoken-as-unchanged", GEOM,
     '        guard let pct else { return "24-hour change not available" }',
     '        guard let pct else { return "unchanged over 24 hours" }',
     "THE REPORTED DEFECT: VoiceOver asserts a market did not move when we have no "
     "reading. The screen is identical, so nothing visual can catch it"),

    ("2-over-application-a-measured-zero-loses-its-sentence", GEOM,
     '        return pct == 0 ? "unchanged over 24 hours"',
     '        return pct == 0 ? "24-hour change not available"',
     "the lazy fix: delete the claim instead of qualifying it. A market we DID read "
     "and that did not move is now described as unreadable — the opposite lie"),

    ("3-absent-price-prints-a-flat-zero-again", GEOM,
     "        guard let pct else { return absentProbabilityMarker }",
     '        guard let pct else { return "0%" }',
     "the visible half of the same coalesce: three rows of 60268421 claim a priced "
     "outcome is impossible, while the ladder above prints no percentage for them"),

    ("4-over-application-a-measured-zero-becomes-a-dash", GEOM,
     "        return pct < 1 && pct > 0 ? String(format: \"%.1f%%\", pct) : \"\\(Int(pct.rounded()))%\"",
     "        return pct <= 1 && pct >= 0 ? absentProbabilityMarker : \"\\(Int(pct.rounded()))%\"",
     "#5899 regression: a MEASURED zero is a fact and prints `0%`. Absence is not "
     "this function's business — and a suite that only knows the nil arm lets this by"),

    ("5-the-visible-delta-column-moves", GEOM,
     '        guard let pct else { return "-" }\n        if pct > 0',
     '        guard let pct else { return absentProbabilityMarker }\n        if pct > 0',
     "#7285 asked for the DRAWN column not to move. An em dash beside a hyphen is a "
     "redesign riding a correctness fix, and it re-measures every column with it"),

    ("6-CALL-SITE-the-row-coalesces-the-change-again", ROW,
     "    private var changePct: Double? { outcome.probabilityChange24h.map { $0 * 100 } }",
     "    private var changePct: Double? { (outcome.probabilityChange24h ?? 0) * 100 }",
     "🔴 THE DEFECT RESTORED WHERE IT LIVED. Compiles clean — `Double` promotes to "
     "`Double?` — and every geometry test stays green. Only the call-site scan sees it"),

    ("7-CALL-SITE-the-row-coalesces-the-price-again", ROW,
     "    private var probPct: Double? { outcome.currentProbability.map { $0 * 100 } }",
     "    private var probPct: Double? { (outcome.currentProbability ?? 0) * 100 }",
     "same shape on the price, and this one is VISIBLE on the page — `0%` comes back "
     "and no behavioural assertion in the suite is looking at the row"),

    ("8-CALL-SITE-the-spoken-price-reverts-to-the-silent-em-dash", ROW,
     "EvolutionLeaderboardGeometry.spokenProb(probPct)",
     "EvolutionLeaderboardGeometry.probLabel(probPct)",
     "the row names a participant and then states no number at all: an em dash is "
     "silent to a screen reader. Compiles, draws identically, unreachable behaviourally"),

    ("9-the-measurement-keeps-the-coalesce", GEOM,
     "            probs: outcomes.map { probLabel($0.currentProbability.map { $0 * 100 }) },",
     "            probs: outcomes.map { probLabel(($0.currentProbability ?? 0) * 100) },",
     "EXPECTED SURVIVOR — EQUIVALENT, AND MEASURED SO. The column is sized on `0%` "
     "while the row draws a dash, which is exactly the divergence this file forbids, "
     "but the `Prob` HEADER's ink floors the column above both spellings, so no board "
     "can tell them apart. Pinned by "
     "`testTheProbHeaderFloorsBothAbsentSpellings`, which fails the day the absent "
     "spelling grows long enough for this to become real. 8/9 is the passing score"),
]

# TRAP (banked by native/234): on a FAILING run xcodebuild calls
# `simctl diagnose --timeout=600`, i.e. ~10 minutes per KILLED mutant.
XCB = ["xcodebuild", "test",
       "-project", str(ROOT / "Bain Luck.xcodeproj"),
       "-scheme", "Bain Luck",
       "-destination", f"platform=iOS Simulator,id={SIM}",
       "-disableAutomaticPackageResolution",
       "-collect-test-diagnostics", "never",
       "-only-testing:BainLuckTests/ANullChangeIsNotSpokenAsUnchanged7285Tests",
       "-only-testing:BainLuckTests/EvolutionLeaderboardWidthTests",
       "-only-testing:BainLuckTests/FuturesZeroPercentLabel5899Tests",
       "-only-testing:BainLuckTests/AHeroMoveAgreesWithTheTable6931Tests",
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
            print(f"  !! COULD NOT RESTORE {path}: {e}\n"
                  f"     git checkout it BY HAND before committing")
        _IN_FLIGHT.pop(path, None)


atexit.register(_restore_all)
for _sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
    signal.signal(_sig, lambda s, f: (_restore_all(), sys.exit(128 + s)))


def main():
    if "--list" in sys.argv:
        for n, *_ in MUTANTS:
            print(f"  {n}")
        return 0

    print("baseline (unmutated tree)")
    code, ran, _ = run_tests()
    if code != 0 or not ran:
        print(f"  BASELINE IS RED (exit {code}, ran={ran}) — fix that before reading any mutant")
        return 2
    print("  baseline GREEN\n")

    killed, survived = [], []
    for name, path, find, repl, why in MUTANTS:
        original = path.read_text()
        # A refused patch prints a green indistinguishable from an unkillable
        # mutant, so refusal is reported as a NON-result, never a pass.
        if find not in original:
            print(f"  REFUSED  {name} — anchor not found; the mutant patched NOTHING")
            survived.append((name, "REFUSED"))
            continue
        if original.count(find) != 1:
            print(f"  REFUSED  {name} — anchor is not unique ({original.count(find)} hits)")
            survived.append((name, "REFUSED"))
            continue

        _IN_FLIGHT[path] = original
        path.write_text(original.replace(find, repl))
        try:
            code, ran, out = run_tests()
        finally:
            path.write_text(original)
            _IN_FLIGHT.pop(path, None)

        if not ran and code != 0:
            # Did not compile. That IS a kill — the mutant cannot ship — but say
            # which kind it was, because a compile kill proves nothing about the
            # suite (gotcha #124: read the exit code's VALUE).
            print(f"  KILLED*  {name}  (did not compile — the type system, not the suite)")
            killed.append((name, "compile"))
        elif code != 0:
            first = next((l.strip() for l in out.splitlines()
                          if " error: " in l or "XCTAssert" in l), "")
            print(f"  KILLED   {name}\n           {first[:150]}")
            killed.append((name, "suite"))
        else:
            print(f"  SURVIVED {name}\n           WHY IT MATTERS: {why}")
            survived.append((name, "survived"))

    print(f"\nkilled {len(killed)}/{len(MUTANTS)}   survived {len(survived)}")
    for n, how in survived:
        print(f"  SURVIVOR  {n}  ({how})")
    return 1 if survived else 0


if __name__ == "__main__":
    sys.exit(main())
