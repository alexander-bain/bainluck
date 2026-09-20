#!/usr/bin/env python3
"""native/268 — mutation run for #7496 (the iPhone accuracy hero's over-claim).

Four mutants, and two of them are aimed at the GUARD rather than at the fix,
because the guard is a banned-phrase sweep and a sweep is the shape that most
easily stops meaning anything:

  * 1, 2 are the defect returning — the whole old sentence, and each of its two
    over-claims on its own. A fix that only repaired one of them would pass a
    test written against the other.
  * 3 empties the sweep's banned list. A list-driven assertion with an empty list
    passes on every input, including the bug. If nothing catches this, the sweep
    is decoration.
  * 4 deletes the scoping from the hero while leaving `(N measured in all)` — the
    half-fix. It is caught only by the CONTROL test, which exists because a
    banned-phrase list is also satisfied by a page that prints nothing at all.

A mutant that SURVIVES is a hole in the guard suite, not a curiosity.

Runs only from this lane's own worktree; every path is absolute.

Usage:  python3 tools/native-268b-mutations-7496.py [--list]
"""
import subprocess, sys, pathlib, signal, atexit

WORKTREE = pathlib.Path("/Users/bain/bainluck-dev/native")
ROOT = WORKTREE / "ios/Bain Luck"
VM = ROOT / "Bain Luck/ViewModels/CalibrationViewModel.swift"
AVAIL = ROOT / "BainLuckTests/CalibrationAvailabilityTests.swift"
SIM = "D2DA47A0-85F6-4BF8-AEFF-33146AE3EB05"

HERO_FIXED = '''        return "\\(formattedCohortOutcomes) resolved predictions \\u{2014} every outcome we measured "
            + "except the \\(Self.fmt(unchangedN)) whose price never moved off its opening line "
            + "(\\(Self.fmt(fullN)) measured in all)"'''

HERO_PRE_7496 = '''        return "\\(formattedCohortOutcomes) resolved predictions \\u{2014} every outcome except the "
            + "\\(Self.fmt(unchangedN)) whose price never moved off its opening line "
            + "(\\(Self.fmt(fullN)) in total)"'''

HERO_TOTAL_ONLY = '''        return "\\(formattedCohortOutcomes) resolved predictions \\u{2014} every outcome we measured "
            + "except the \\(Self.fmt(unchangedN)) whose price never moved off its opening line "
            + "(\\(Self.fmt(fullN)) in total)"'''

HERO_SCOPE_DROPPED = '''        return "\\(formattedCohortOutcomes) resolved predictions \\u{2014} every outcome except the "
            + "\\(Self.fmt(unchangedN)) whose price never moved off its opening line "
            + "(\\(Self.fmt(fullN)) measured in all)"'''

BANLIST_WIRED = '''        let banned = ["in total", "total outcomes", "the total", "in all markets",
                      "every outcome except", "all resolved outcomes"]'''
BANLIST_EMPTY = '''        let banned: [String] = []'''

# (name, file, find, replace, why-it-matters)
MUTANTS = [
    ("1-hero-reverts-to-the-whole-pre-7496-sentence", VM,
     HERO_FIXED, HERO_PRE_7496,
     "THE REPORTED DEFECT, verbatim: a post-exclusion population called the total, "
     "with one cut named as the only cut"),

    ("2-only-the-total-half-of-the-defect-returns", VM,
     HERO_FIXED, HERO_TOTAL_ONLY,
     "THE HALF-REVERT. The scoping stays and `(N in total)` comes back — the shape "
     "a later copy edit produces when it only remembers one of the two claims"),

    ("3-the-sweeps-banned-list-is-emptied", AVAIL,
     BANLIST_WIRED, BANLIST_EMPTY,
     "THE VACUOUS-SWEEP MUTANT. The loop still runs over all seven strings and "
     "both toggle states and asserts nothing. If this survives, the sweep is "
     "decoration and only the two equality pins are real"),

    ("4-scoping-dropped-but-the-new-total-wording-kept", VM,
     HERO_FIXED, HERO_SCOPE_DROPPED,
     "THE OTHER HALF. `(N measured in all)` is honest and `every outcome except` "
     "is not; the banned list catches this one, so it also proves the list is not "
     "carrying only the `in total` entry"),
]

# TRAP (banked by native/234): on a FAILING test run xcodebuild runs
# `simctl diagnose --timeout=600`. `-collect-test-diagnostics never` is the fix.
XCB = ["xcodebuild", "test",
       "-project", str(ROOT / "Bain Luck.xcodeproj"),
       "-scheme", "Bain Luck",
       "-destination", f"platform=iOS Simulator,id={SIM}",
       "-collect-test-diagnostics", "never",
       "-only-testing:BainLuckTests/CalibrationAvailabilityTests",
       "-only-testing:BainLuckTests/CalibrationSurfaceTests",
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
        for n, f, *_ in MUTANTS:
            print(f"  {n}  ({f.name})")
        return 0

    print("baseline (unmutated tree)")
    code, _, _ = run_tests()
    if code != 0:
        print(f"  BASELINE IS RED (exit {code}) — fix that before reading any mutant")
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
            print(f"  REFUSED  {name} — anchor occurs {original.count(find)}x, not unique")
            survived.append((name, "REFUSED-AMBIGUOUS"))
            continue
        try:
            _IN_FLIGHT[path] = original
            path.write_text(original.replace(find, repl, 1))
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
