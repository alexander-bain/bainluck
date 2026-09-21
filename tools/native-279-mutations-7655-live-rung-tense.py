#!/usr/bin/env python3
"""native/279 — mutation run for #7655 (a live ladder rung captioned PRE-GAME).

The claim under test is one clause in one function: while a game is underway, no
ungraded rung of its totals ladder wears a pre-game tense. A rule that thin is
exactly the kind whose guard suite passes on a tree where the rule has been
disconnected, so the CALL SITE is mutated separately from the rule.

What this battery adds that the unit tests cannot:

  * THE INERT-FIX MUTANTS (5, 6, 7). Every assertion in
    ALiveLadderRungDoesNotSayPreGame7655Tests is about a pure function taking a
    `Bool`. Hand the view a constant, or the wrong predicate, and the rule stays
    perfect, the suite stays green and the phone shows exactly the frame
    n278-before-2150.png photographed. Only the source scan can see these, and
    these mutants are what prove the scan is load-bearing rather than decorative.

  * THE OVER-APPLICATION MUTANT (2). Reading `hasStarted` WITHOUT asking the
    tense silences #3925's settled `LAST QUOTE` too — a finished match has
    obviously started. Closing this issue by re-opening that one would pass every
    assertion that mentions #7655 and only #7655.

  * THE COMMENT-STRIPPER MUTANT (9). `hasStarted:` appears in the prose
    explaining the call site as often as in the call. A scan of the raw source is
    a guard grading its own explanation.

A mutant that SURVIVES is a hole in the guard suite, not a curiosity. A mutant
the battery cannot APPLY is reported REFUSED and never counted as a kill.

Runs only from this lane's own worktree; every path below is absolute.

Usage:  python3 tools/native-279-mutations-7655-live-rung-tense.py [--list]
"""
import subprocess, sys, pathlib, signal, atexit

WORKTREE = pathlib.Path("/Users/bain/bainluck-dev/native")
ROOT = WORKTREE / "ios/Bain Luck"
GUARD = WORKTREE / "tools/reserved-sim-guard.sh"
RAIL = ROOT / "Bain Luck/Utilities/MarketMapRail.swift"
SPECTRUM = ROOT / "Bain Luck/Components/TotalPointsSpectrumView.swift"
TESTS = ROOT / "BainLuckTests/ALiveLadderRungDoesNotSayPreGame7655Tests.swift"


def disposable_sim():
    """A device this run may install to, from the rig's shared picker.

    🪤 NOT A HARD-CODED UDID, AND NOT `name=iPhone 17`. Two simulators hold
    Alex's signed-in account and both carry that name, so a destination written
    by NAME resolves to one of them. `tools/reserved-sim-guard.sh` is the
    authority and asking it is the only spelling that stays correct when the
    list changes.
    """
    pick = subprocess.run(["bash", "-c", f'. "{GUARD}" && bl_default_shoot_sim'],
                          capture_output=True, text=True)
    udid = (pick.stdout or "").strip().splitlines()
    udid = udid[-1].strip() if udid else ""
    if not udid:
        sys.exit("FATAL: no disposable iPhone simulator on this machine")
    check = subprocess.run(["bash", "-c", f'. "{GUARD}" && bl_is_reserved_sim "{udid}"'])
    if check.returncode == 0:
        sys.exit(f"FATAL: the picker returned RESERVED device {udid} — refusing to install")
    return udid


SIM = disposable_sim()

GATE_WIRED = """        if hasStarted, SpectrumTense.of(finalTotal: finalTotal, isSettled: isSettled) == .projected {
            return nil
        }"""
GATE_GONE = """"""
GATE_CLOCK_ONLY = """        if hasStarted {
            return nil
        }"""
GATE_WRONG_ARM = """        if hasStarted, SpectrumTense.of(finalTotal: finalTotal, isSettled: isSettled) == .settled {
            return nil
        }"""
GATE_INVERTED = """        if !hasStarted, SpectrumTense.of(finalTotal: finalTotal, isSettled: isSettled) == .projected {
            return nil
        }"""

CALL_WIRED = """                    hasStarted: isLive || EventState.hasStarted(commenceTime: commenceTime),"""
CALL_CONSTANT_FALSE = """                    hasStarted: false,"""
CALL_STATUS_ONLY = """                    hasStarted: isLive,"""
CALL_WRONG_PREDICATE = """                    hasStarted: isDone,"""

STRIPPER_ON = """        return try String(contentsOf: url, encoding: .utf8)
            .split(separator: "\\n", omittingEmptySubsequences: false)
            .filter { !$0.trimmingCharacters(in: .whitespaces).hasPrefix("//") }
            .joined(separator: "\\n")"""
STRIPPER_OFF = """        return try String(contentsOf: url, encoding: .utf8)"""

# (name, file, find, replace, why-it-matters)
MUTANTS = [
    ("1-the-reported-defect-restored", RAIL, GATE_WIRED, GATE_GONE,
     "THE PHOTOGRAPHED DEFECT, byte for byte — every ungraded rung of a live "
     "ladder wears PRE-GAME again. If this survives, the ship proves nothing"),

    ("2-the-clock-alone-decides-it", RAIL, GATE_WIRED, GATE_CLOCK_ONLY,
     "OVER-APPLICATION, and the likeliest wrong simplification: drop the tense "
     "test and read `hasStarted` alone. A finished match has obviously started, "
     "so this silences #3925's settled LAST QUOTE — closing this issue by "
     "re-opening that one"),

    ("3-the-gate-is-hung-on-the-settled-arm", RAIL, GATE_WIRED, GATE_WRONG_ARM,
     "the same clause on the neighbouring case. The live ladder is unfixed AND "
     "the settled card loses its tense — a suite that only counts nils could "
     "call this a pass"),

    ("4-the-gate-fires-before-kickoff-instead", RAIL, GATE_WIRED, GATE_INVERTED,
     "the polarity flipped: PRE-GAME is suppressed on the one card where it is "
     "TRUE and printed on every card where it is false. "
     "testTheClockIsTheOnlyThingThatDecidesIt is the assertion that must catch "
     "it, and it is the reason that test states the positive as well as the nil"),

    ("5-the-card-is-handed-a-constant", SPECTRUM, CALL_WIRED, CALL_CONSTANT_FALSE,
     "THE INERT FIX. Rule right, every unit test green, phone unchanged. Only "
     "the call-site scan can see this, and this mutant is why that scan exists"),

    ("6-the-card-is-handed-the-status-and-not-the-clock", SPECTRUM,
     CALL_WIRED, CALL_STATUS_ONLY,
     "THE SUBTLE INERT FIX: correct on every well-behaved row and wrong on "
     "exactly the population the clock was added for — a `scheduled` status that "
     "has not caught up with kickoff, whose prices are already live"),

    ("7-the-card-is-handed-the-wrong-predicate", SPECTRUM,
     CALL_WIRED, CALL_WRONG_PREDICATE,
     "`isDone` reads as a plausible 'the game has happened' and is false for "
     "every live game — the defect, restored through the new parameter"),

    ("8-an-unused-alias-is-added", SPECTRUM,
     "    private var isPre: Bool { !isLive && !isDone }",
     "    private var isPre: Bool { !isLive && !isDone }\n"
     "    private var isPreIgnored: Bool { isPre }",
     "a no-op edit that must NOT be reported as a kill — the battery's own "
     "CONTROL. A run that 'kills' this is failing for a reason unrelated to the "
     "mutant"),

    ("9-the-scan-reads-the-raw-file-again", TESTS, STRIPPER_ON, STRIPPER_OFF,
     "THE SELF-GRADING MUTANT. `hasStarted:` appears in the comments explaining "
     "the call site, so a raw-file scan counts prose as wiring and the "
     "`hasStarted: false` clause starts matching this test's own text"),
]

# TRAP (banked by native/234): on a FAILING run xcodebuild calls
# `simctl diagnose --timeout=600` — ~10 min per KILLED mutant.
# `-collect-test-diagnostics never` is the fix.
XCB = ["xcodebuild", "test",
       "-project", str(ROOT / "Bain Luck.xcodeproj"),
       "-scheme", "Bain Luck",
       "-destination", f"platform=iOS Simulator,id={SIM}",
       "-collect-test-diagnostics", "never",
       "-disableAutomaticPackageResolution",
       "-only-testing:BainLuckTests/ALiveLadderRungDoesNotSayPreGame7655Tests",
       "-only-testing:BainLuckTests/ALiveRungTheScoreClearedReadsAsHit4907Tests",
       "-only-testing:BainLuckTests/TotalPointsSpectrumRungCaptionTests",
       "-only-testing:BainLuckTests/TotalPointsSpectrumTenseTests",
       "-only-testing:BainLuckTests/SuspendedProjectionTests",
       "OTHER_SWIFT_FLAGS=$(inherited) -Xfrontend -disable-sandbox"]


def run_tests():
    r = subprocess.run(XCB, capture_output=True, text=True, cwd=str(ROOT))
    out = r.stdout + r.stderr
    return r.returncode, ("Executed" in out), out


# TRAP (also banked by native/234): `finally` does not survive SIGTERM.
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

    print(f"simulator {SIM} (disposable, via reserved-sim-guard)")
    print("baseline (unmutated tree)")
    code, _, _ = run_tests()
    if code != 0:
        print(f"  BASELINE IS RED (exit {code}) — fix that before reading any mutant")
        return 2
    print("  baseline GREEN\n")

    killed, survived = [], []
    for name, path, find, repl, why in MUTANTS:
        original = path.read_text()
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
    print("\n  (mutant 8 is the battery's CONTROL: it must SURVIVE. Any other survivor is a hole.)")

    dirty = subprocess.run(["git", "-C", str(WORKTREE), "diff", "--stat", "--", "ios/"],
                           capture_output=True, text=True).stdout.strip()
    print("\ntree on exit (expect ONLY this ship's own edits):")
    print("  " + (dirty.replace("\n", "\n  ") if dirty else "(clean)"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
