#!/usr/bin/env python3
"""#4577 mutation sweep — does the suite actually catch the tick going wrong?

Each mutant is an EXACT string replacement asserted to match exactly once, so a
typo'd pattern aborts instead of quietly reading as SURVIVED (the no-op-`sed`
trap). Every mutant is reverted in a `finally`, including on Ctrl-C.

Run from the native worktree root:  python3 tools/n134-mutations-4577.py
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HELPER = ROOT / "ios/Bain Luck/Bain Luck/Utilities/PlayerPropsScript.swift"
VIEW = ROOT / "ios/Bain Luck/Bain Luck/Components/PlayerPropsCardView.swift"

# (id, file, find, replace, the test that MUST go red)
MUTANTS = [
    ("M1 feature off — no tick ever draws",
     HELPER, "        return min(max(0, mark), 1)", "        return nil",
     "testALiveGameStillDrawsItsTick"),
    ("M2 the finished-game guard is removed",
     HELPER, "guard let mark = pregameMark, !isFinished else { return nil }",
     "guard let mark = pregameMark else { return nil }",
     "testNoTickOnAFinishedGame"),
    ("M3 the unit-range clamp is removed",
     HELPER, "        return min(max(0, mark), 1)", "        return mark",
     "testAMarkOutsideTheUnitRangeIsClampedOntoTheTrack"),
    ("M4 the non-finite guard is removed",
     HELPER, "        guard mark.isFinite else { return nil }\n", "",
     "testANonFiniteMarkDrawsNoTick"),
    ("M5 the tick is no longer centred",
     HELPER, "let centred = trackWidth * CGFloat(fraction) - tickWidth / 2",
     "let centred = trackWidth * CGFloat(fraction)",
     "testTheTickIsCentredOnItsFraction"),
    ("M6 the right-hand clamp is removed",
     HELPER, "        return min(max(0, centred), maxOffset)", "        return max(0, centred)",
     "testTheTickCannotHangOffTheRightEnd"),
    ("M7 the maxOffset floor is removed",
     HELPER, "let maxOffset = max(0, trackWidth - tickWidth)",
     "let maxOffset = trackWidth - tickWidth",
     "testATrackNarrowerThanItsOwnTickStillYieldsARealOffset"),
    # M8 DELETES the overlay rather than renaming the call. A rename dies at the
    # compiler, which kills the mutant without ever proving the source scan runs
    # — the scan is the only thing standing between a decoded field and an inert
    # ship, so it has to be killed by a FAILING TEST, not by a build error.
    ("M8 the view stops drawing the tick (overlay deleted, still compiles)",
     VIEW, """                    // #4577 — THE SCRIPT's tick: where this market opened. Drawn
                    // OVER the fill, because the interesting case is a market
                    // that has moved up and would otherwise bury its own
                    // baseline. See ``PlayerPropsScript`` for why there is no
                    // caption and no fallback.
                    .overlay(alignment: .leading) {
                        if let fraction = PlayerPropsScript.tickFraction(
                            pregameMark: rung.pregameMark,
                            isFinished: isDone
                        ) {
                            Capsule()
                                .fill(Color.primary.opacity(0.45))
                                .frame(width: Self.pregameTickWidth)
                                .offset(x: PlayerPropsScript.tickOffset(
                                    fraction: fraction,
                                    trackWidth: geo.size.width,
                                    tickWidth: Self.pregameTickWidth
                                ))
                        }
                    }
""", "",
     "testTheRungTrackDrawsTheTickThroughTheSharedRule"),
    ("M9 the tick falls back to the LIVE price",
     VIEW, "pregameMark: rung.pregameMark", "pregameMark: rung.probability",
     "testTheRungNeverSubstitutesAnotherNumberForAMissingMark"),
    ("M10 the rung is built with no mark (feature off one layer earlier)",
     VIEW, "pregameMark: prop.pregameMark", "pregameMark: nil",
     "testTheRungNeverSubstitutesAnotherNumberForAMissingMark"),
]

SIM = "platform=iOS Simulator,name=iPhone 17 Pro"
PROJ = ROOT / "ios/Bain Luck/Bain Luck.xcodeproj"


def run_suite():
    """Run only this ship's test class. Returns (exit_code, output)."""
    cmd = [
        "xcodebuild", "test",
        "-project", str(PROJ),
        "-scheme", "Bain Luck",
        "-destination", SIM,
        "-only-testing:BainLuckTests/PropsScriptPregameTickTests",
        "OTHER_SWIFT_FLAGS=$(inherited) -Xfrontend -disable-sandbox",
    ]
    p = subprocess.run(cmd, capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr


def main():
    print("=== baseline (unmutated) ===", flush=True)
    code, out = run_suite()
    if code != 0:
        print("BASELINE IS RED — fix that before trusting any mutant below.")
        print("\n".join(l for l in out.splitlines() if "error:" in l or "failed" in l)[:3000])
        return 1
    print("baseline GREEN\n", flush=True)

    only = sys.argv[1] if len(sys.argv) > 1 else None
    killed, survived = [], []
    for name, path, find, repl, expect in MUTANTS:
        if only and not name.startswith(only):
            continue
        original = path.read_text()
        n = original.count(find)
        if n != 1:
            print(f"ABORT {name}: pattern matched {n} times, expected exactly 1")
            return 2
        try:
            path.write_text(original.replace(find, repl))
            code, out = run_suite()
            if code == 0:
                survived.append(name)
                print(f"SURVIVED  {name}", flush=True)
            else:
                # A compile error is not a kill — the mutant must FAIL A TEST.
                compiled = "Executed" in out or "Test Case" in out
                hit = f"{expect}]' failed" in out
                tag = "killed" if compiled else "killed(compile)"
                if compiled and not hit:
                    print(f"KILLED*   {name}  -- but NOT by {expect}", flush=True)
                else:
                    print(f"KILLED    {name}  ({tag}, by {expect})", flush=True)
                killed.append(name)
        finally:
            path.write_text(original)

    print(f"\n=== {len(killed)} killed / {len(MUTANTS)} mutants; survivors: {survived or 'none'}")
    return 0 if not survived else 3


if __name__ == "__main__":
    sys.exit(main())
