#!/usr/bin/env python3
"""native/301 — mutation battery for #2095 (the game card's hero is a floor).

Same harness rules as `native-289-mutations-7878.py`: gate on the EXIT CODE, and
match `with (\\d+) failures?` — xcodebuild writes "with 1 failure", SINGULAR, and
a plural-only regex reads a sibling's "0 failures" and reports a killed mutant as
survived. Every anchor must match EXACTLY ONCE; a bad anchor wastes a slot and
reads as a survivor.

The subject is a SOURCE SCAN, which is a weak instrument by construction: a
`contains` needle passes on a file it has never understood. So the battery is
weighted entirely towards "can this scan say no":

  * M1 is the literal defect restored — the hero pinned at a height again. If
    this survives, the whole guard is decorative. (n300's lesson: fire the
    defect FIRST, not last. On #8109 the first mutant was the defect and it
    survived fourteen green assertions.)
  * M2 is the half-revert: the wiring goes back to a fixed height while the
    NAMED CONSTANT stays in the file. A scan that only asserts the constant
    exists cannot see this, and it is the likeliest real regression — someone
    "simplifying" the frame modifier and leaving the enum behind.
  * M3 moves the floor's VALUE. The measurement in `EventHero`'s doc comment is
    the reason 160 is 160; a guard that does not pin it lets a later session
    round it to 170 to match the futures card and silently make every game card
    taller.
  * M4 deletes the spacer that SPENDS the floor. Without it the floor pads the
    bottom instead of holding the matchup down, so every game card at default
    type changes shape — the "fix" that breaks the 99% case to repair the 1%.
  * M5 is the STRAWMAN. The anti-vacuity test asserts the scan is reading the
    right file; break the struct declaration it keys on and that test must fail,
    or every `XCTAssertFalse` in the class is passing on a file it never read.
  * M6 is the #8097 trap, armed: a SECOND copy of the `.background` needle is
    added to the file. `testEachEventNeedleOccursExactlyOnce2095` must fail, or
    a later half-revert of one of the two sites leaves the scan green on the
    defect.
"""

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CARD = ROOT / "ios/Bain Luck/Bain Luck/Components/DiscoverEventCard.swift"
VISUALS = ROOT / "ios/Bain Luck/Bain Luck/Utilities/DiscoverCardVisuals.swift"
SIM = "D2DA47A0-85F6-4BF8-AEFF-33146AE3EB05"

FRAME = """                .frame(
                    maxWidth: .infinity,
                    minHeight: EventHero.discoverCardMinimumHeight
                )
                .background { heroBackground }"""

MUTANTS = [
    ("M1 the defect restored — the hero is pinned at a height again",
     CARD,
     FRAME,
     """                .frame(height: 160)
                .background { heroBackground }"""),

    ("M2 the half-revert — the wiring goes fixed, the named constant stays",
     CARD,
     "                    minHeight: EventHero.discoverCardMinimumHeight\n"
     "                )",
     "                    maxHeight: EventHero.discoverCardMinimumHeight\n"
     "                )"),

    ("M3 the floor's value moves to the futures card's 170",
     VISUALS,
     "    static let discoverCardMinimumHeight: CGFloat = 160",
     "    static let discoverCardMinimumHeight: CGFloat = 170"),

    ("M4 the spacer that spends the floor is deleted",
     CARD,
     "            Spacer(minLength: 10)",
     "            Spacer(minLength: 0)"),

    ("M5 the STRAWMAN: the struct the scan keys on is renamed, so the "
     "anti-vacuity test has to be able to fail",
     CARD,
     "struct NativeEventDiscoverCard: View {",
     "struct NativeEventDiscoverCardRenamed: View {"),

    ("M6 the #8097 trap armed — a SECOND `.background { heroBackground }` "
     "site, which a bare `contains` cannot see",
     CARD,
     "                .background { heroBackground }",
     "                .background { heroBackground }\n"
     "                .background { heroBackground }"),
]

# Named rather than wrapped across two lines inside the argv list: two adjacent
# string literals there are indistinguishable from a missing comma, which is a
# whole test class silently not running.
GUARD_TEST = (
    "-only-testing:BainLuckTests/"
    + "TheHeroBackdropIsAFloorNotAHeight7074Tests"
)


def run_swift():
    p = subprocess.run(
        ["xcodebuild", "-project", str(ROOT / "ios/Bain Luck/Bain Luck.xcodeproj"),
         "-scheme", "Bain Luck", "-destination", f"id={SIM}",
         "-disableAutomaticPackageResolution",
         GUARD_TEST,
         "OTHER_SWIFT_FLAGS=$(inherited) -Xfrontend -disable-sandbox", "test"],
        capture_output=True, text=True,
    )
    return p.returncode, p.stdout + p.stderr


COUNT = re.compile(r"with (\d+) failures?")


def label(out):
    hits = [int(m) for m in COUNT.findall(out)]
    return f"{sum(hits)} failing assertion group(s)" if hits else "no count line"


def main():
    # A dry pass first: a bad anchor costs a whole slot and reads as a survivor.
    bad = False
    for name, path, find, _ in MUTANTS:
        n = path.read_text().count(find)
        if n != 1:
            print(f"  ANCHOR    {name}  (matches {n}x, want 1)")
            bad = True
    if bad:
        print("\nrefusing to run: fix the anchors first")
        return 2

    # The baseline must be green on THIS simulator before a single mutant runs,
    # or every KILLED is free and the one SURVIVED is noise.
    code, out = run_swift()
    if code != 0:
        print(f"  BASELINE  RED (exit {code}, {label(out)}) — refusing to run")
        return 2
    print(f"  BASELINE  green (exit 0, {label(out)})", flush=True)

    results = []
    for name, path, find, repl in MUTANTS:
        original = path.read_text()
        path.write_text(original.replace(find, repl, 1))
        try:
            code, out = run_swift()
        finally:
            path.write_text(original)
        verdict = "KILLED" if code != 0 else "SURVIVED"
        results.append((name, verdict, f"exit {code}, {label(out)}"))
        print(f"  {verdict:9} {name}  ({results[-1][2]})", flush=True)

    killed = sum(1 for _, v, _ in results if v == "KILLED")
    print(f"\n{killed}/{len(results)} killed")
    return 0 if killed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
