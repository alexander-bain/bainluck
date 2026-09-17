#!/usr/bin/env python3
"""native/201 — mutation battery for #6705 (a thumb on the chart stops the page).

Each mutant rewrites the SHIPPED Swift and asks whether
`AReaderCanScrollPastTheChart6705Tests` notices. A mutant the guard does not
notice is a hole in the guard, not a curiosity.

THE SPLIT THIS BATTERY EXISTS TO PROVE. #6705 is two defects with two different
kinds of guard, and the risk is that one of them is only apparently covered:

  * M1-M5 attack the VIEW and the UIKit surface — the `simultaneousGesture` modifier and the wire into
    the state machine. Nothing but a source scan can see these; Swift's type
    checker is perfectly happy with the defect, and fifteen green state-machine
    tests sit beside a chart that swallows every scroll. If any of M1-M5
    survives, the source scan is decorative.
  * M6-M14 attack the RULE in `ChartScrub.swift`, which the unit arms own.

Run with `python3 -u`: `print()` to a redirected file is block-buffered, so a
40-minute battery looks hung for 39 of them.

Four things this battery does on purpose:

  * **A mutant that did not apply reads exactly like a kill.** A missing needle
    is reported NEEDLE-NOT-FOUND and graded as a FAILURE of the battery.
  * **A needle that matches more than once grades code nobody chose.** Every
    needle is asserted unique in the file before it is used.
  * **The dirty-tree guard is SCOPED to the files it mutates**, with
    `--untracked-files=no` — a bare porcelain refuses on the lane's
    `artifacts/` directory, which exists every session.
  * Restores with `git checkout HEAD -- <file>`, never `git checkout -- <file>`:
    the latter reads the INDEX, so a stale `git add` silently reverts newer work.

Usage:  python3 -u tools/native-201-mutations-6705.py
"""

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

VIEW = "ios/Bain Luck/Bain Luck/Components/EvolutionChartView.swift"
RULE = "ios/Bain Luck/Bain Luck/Utilities/ChartScrub.swift"
SURFACE = "ios/Bain Luck/Bain Luck/Components/ChartScrubSurface.swift"
FILES = [VIEW, RULE, SURFACE]

PROJECT = ROOT / "ios/Bain Luck/Bain Luck.xcodeproj"
SCHEME = "Bain Luck"
SWIFT_FLAGS = "$(inherited) -Xfrontend -disable-sandbox"
TEST_CLASS = "BainLuckTests/AReaderCanScrollPastTheChart6705Tests"

# The shipped guard, used whole as a needle because the mutant that matters —
# "consult the rule and then ignore it" — cannot be expressed by swapping one
# token without leaving an orphaned `else`.
GUARD_BLOCK = """                                guard scrub.change(
                                    width: drag.translation.width,
                                    height: drag.translation.height
                                ) else {
                                    // Latched vertical: this is the reader
                                    // scrolling the page. Drop any crosshair
                                    // already placed by the undecided opening
                                    // frames rather than leaving it stranded.
                                    crosshair = nil
                                    return
                                }
"""

IGNORED_BLOCK = """                                _ = scrub.change(
                                    width: drag.translation.width,
                                    height: drag.translation.height
                                )
"""

# (name, file, needle, replacement, what a reader would see if this shipped)
MUTANTS = [
    # ── The view and the surface: the half no state machine can see ────────
    (
        "M1 back to a SwiftUI DragGesture (THE ORIGINAL DEFECT)",
        VIEW,
        "ChartScrubSurface(",
        "ChartScrubSurfaceDISABLED(",
        "a thumb on the chart scrolls nothing — measured 0.0pt against a ~330pt control",
    ),
    (
        "M2a the constant flips (THE FIRST BATTERY'S ONLY SURVIVOR)",
        SURFACE,
        "static let sharesTheTouchWithTheScrollView = true",
        "static let sharesTheTouchWithTheScrollView = false",
        "the pan starves UIScrollView again — this one value IS the fix",
    ),
    (
        "M2b the delegate answers with its own literal instead of the constant",
        SURFACE,
        "            ChartScrubSurface.sharesTheTouchWithTheScrollView\n        }",
        "            false\n        }",
        "same defect, and invisible to a test that reads only the constant — "
        "which is why both halves are mutated separately",
    ),
    (
        "M3 the delegate is never attached",
        SURFACE,
        "pan.delegate = context.coordinator",
        "_ = context.coordinator",
        "shouldRecognizeSimultaneouslyWith is never asked; the scroll dies",
    ),
    (
        "M4 consult the rule and ignore the answer",
        VIEW,
        "guard scrub.change(",
        "_ = scrub.change(",
        "the crosshair rides the reader's scroll down the page",
    ),
    (
        "M5 the latch is never cleared",
        VIEW,
        "                        scrub.end()\n",
        "",
        "the first drag the chart resolves is the last one it treats as a scrub",
    ),
    # ── The rule ───────────────────────────────────────────────────────────
    (
        "M6 latch on arrival instead of on movement",
        RULE,
        "static let axisThreshold: CGFloat = 12",
        "static let axisThreshold: CGFloat = 0",
        "the first onChanged is (0,0), abs(0) > abs(0) is false, so every touch "
        "latches VERTICAL and the crosshair never appears at all",
    ),
    (
        "M7 a tie goes to the scrub",
        RULE,
        "isHorizontal = abs(width) > abs(height)",
        "isHorizontal = abs(width) >= abs(height)",
        "a sloppy diagonal scroll scrubs instead of scrolling",
    ),
    (
        "M8 the axis test is inverted",
        RULE,
        "isHorizontal = abs(width) > abs(height)",
        "isHorizontal = abs(width) < abs(height)",
        "scrolling scrubs and scrubbing scrolls",
    ),
    (
        "M9 the threshold is measured on the smaller axis",
        RULE,
        "max(abs(width), abs(height)) >= Self.axisThreshold",
        "min(abs(width), abs(height)) >= Self.axisThreshold",
        "a straight vertical flick never latches, so the crosshair follows it",
    ),
    (
        "M10 the threshold boundary is exclusive",
        RULE,
        "max(abs(width), abs(height)) >= Self.axisThreshold",
        "max(abs(width), abs(height)) > Self.axisThreshold",
        "a drag landing exactly on the threshold is undecided for one more frame",
    ),
    (
        "M11 tracking ignores the undecided state (press-and-hold dies)",
        RULE,
        "var tracks: Bool { !axisLatched || isHorizontal }",
        "var tracks: Bool { isHorizontal }",
        "a reader who presses and holds gets no crosshair — the chart's only "
        "interaction is gone",
    ),
    (
        "M12 tracking is unconditional (the legacy behaviour, restored)",
        RULE,
        "var tracks: Bool { !axisLatched || isHorizontal }",
        "var tracks: Bool { true }",
        "exactly the shipped defect: every drag scrubs, including the scroll",
    ),
    (
        "M13 the axis is re-decided every frame",
        RULE,
        "if !axisLatched, max(abs(width), abs(height)) >= Self.axisThreshold {",
        "if max(abs(width), abs(height)) >= Self.axisThreshold {",
        "a drag that wanders across the diagonal flickers between scroll and scrub",
    ),
    (
        "M14 end() forgets to clear the latch",
        RULE,
        "        axisLatched = false\n        isHorizontal = false\n    }\n}",
        "    }\n}",
        "the latch outlives its gesture — #1773's defect one layer down",
    ),
]

# Mutants that must SURVIVE. A guard that reddens on a comment edit or on a
# constant the tests deliberately do not pin is a guard that gets suppressed the
# first time someone rewords a doc block.
EQUIVALENT = [
    (
        "E1 reword a doc comment (must SURVIVE)",
        RULE,
        "/// Movement, in points, after which a drag's axis is decided.",
        "/// How far a drag must travel before its axis is decided.",
    ),
    (
        "E2 nudge the threshold 12 -> 11 (must SURVIVE — the tests pin BEHAVIOUR)",
        RULE,
        "static let axisThreshold: CGFloat = 12",
        "static let axisThreshold: CGFloat = 11",
    ),
]


def udid() -> str:
    listing = subprocess.run(
        ["xcrun", "simctl", "list", "devices", "available"],
        capture_output=True, text=True, check=True,
    ).stdout
    for line in listing.splitlines():
        if re.match(r"^\s+iPhone ", line):
            found = re.search(r"\(([0-9A-Fa-f-]{36})\)", line)
            if found:
                return found.group(1)
    raise SystemExit("NO iPhone SIMULATOR AVAILABLE — the battery cannot run.")


def run_guard(device: str) -> bool:
    """True when the one test class is GREEN.

    gotcha #124: read the exit code's VALUE. 65 is 'the tests failed', which is
    this battery working. 70/127/137/143 mean xcodebuild never ran the tests at
    all, and grading those as a kill would manufacture a clean sheet.
    """
    result = subprocess.run(
        ["xcodebuild", "test",
         "-project", str(PROJECT), "-scheme", SCHEME,
         "-destination", f"id={device}",
         "-only-testing:" + TEST_CLASS,
         f"OTHER_SWIFT_FLAGS={SWIFT_FLAGS}"],
        cwd=ROOT, capture_output=True, text=True,
    )
    if result.returncode not in (0, 65):
        raise SystemExit(
            f"xcodebuild exited {result.returncode} — the gate never ran, so nothing "
            f"here can be graded.\n{result.stdout[-3000:]}"
        )
    return result.returncode == 0


def restore() -> None:
    subprocess.run(["git", "checkout", "HEAD", "--", *FILES], cwd=ROOT, check=True)


def main() -> int:
    dirty = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=no", "--", *FILES],
        cwd=ROOT, capture_output=True, text=True,
    ).stdout.strip()
    if dirty:
        print(f"REFUSING: a mutated file has uncommitted changes — commit first.\n{dirty}")
        return 2

    device = udid()
    print(f"simulator: {device}\n", flush=True)

    originals = {f: (ROOT / f).read_text() for f in FILES}

    print("BASE: ", end="", flush=True)
    if not run_guard(device):
        print("RED before any mutant. The battery cannot grade anything.")
        return 2
    print("GREEN\n", flush=True)

    killed, survived, unapplied = [], [], []

    for name, target, needle, replacement, harm in MUTANTS:
        source = originals[target]
        hits = source.count(needle)
        if hits == 0:
            unapplied.append(f"{name} (needle absent)")
            print(f"  NEEDLE NOT FOUND  {name}", flush=True)
            continue
        if hits > 1:
            unapplied.append(f"{name} (needle matches {hits}x)")
            print(f"  NEEDLE AMBIGUOUS  {name} — matches {hits} places, grades code nobody chose",
                  flush=True)
            continue
        (ROOT / target).write_text(source.replace(needle, replacement, 1))
        green = run_guard(device)
        restore()
        if green:
            survived.append((name, harm))
            print(f"  SURVIVED          {name}\n                    -> {harm}", flush=True)
        else:
            killed.append(name)
            print(f"  killed            {name}", flush=True)

    print(flush=True)
    for name, target, needle, replacement in EQUIVALENT:
        source = originals[target]
        if source.count(needle) != 1:
            unapplied.append(f"{name} (needle not unique)")
            print(f"  NEEDLE NOT FOUND  {name}", flush=True)
            continue
        (ROOT / target).write_text(source.replace(needle, replacement, 1))
        green = run_guard(device)
        restore()
        print(f"  {'survived (correct)' if green else 'KILLED (over-tight — BAD)'}  {name}",
              flush=True)
        if not green:
            survived.append((name, "the guard reads cosmetics as contract"))

    print(f"\n{len(killed)}/{len(MUTANTS)} defect mutants killed.")
    if unapplied:
        print(f"BATTERY FAILURE — {len(unapplied)} mutant(s) never applied: {unapplied}")
        return 2
    if survived:
        print("SURVIVORS — the guard has holes:")
        for name, harm in survived:
            print(f"  {name}: {harm}")
        return 1
    print("No survivors.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
