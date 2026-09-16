#!/usr/bin/env python3
"""native/196 — mutation battery for #6612 (the gutter crest stands up).

Each mutant rewrites the SHIPPED Swift and asks whether
`chartGuttersDrawOneCrest.test.ts` notices. A mutant that the guard does not
notice is a hole in the guard, not a curiosity.

Two things this battery does on purpose, both learned the hard way:

  * **A mutant that did not apply reads exactly like a kill.** If the needle is
    absent the run is reported NEEDLE-NOT-FOUND and graded as a FAILURE of the
    battery, never as a kill.
  * **The dirty-tree guard is SCOPED to the file it mutates**, with
    `--untracked-files=no`. A bare `git status --porcelain` refuses on the
    lane's `artifacts/` directory, which exists every session — a guard nobody
    can get past is a guard nobody runs.

Restores with `git checkout HEAD -- <file>`, never `git checkout -- <file>`:
the latter reads the INDEX, so a stale `git add` silently reverts newer work.
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SWIFT = "ios/Bain Luck/Bain Luck/Components/ChartGutterLabel.swift"
TARGET = ROOT / SWIFT

# (name, needle, replacement, what a reader would see if this shipped)
MUTANTS = [
    (
        "M1 delete the crest's counter-rotation (THE ORIGINAL DEFECT)",
        "        .rotationEffect(.degrees(Self.counterRotationDegrees))\n",
        "",
        "the StL and SF wordmarks lie on their side again",
    ),
    (
        "M2 right the crest with a bare literal instead of the constant",
        ".rotationEffect(.degrees(Self.counterRotationDegrees))",
        ".rotationEffect(.degrees(90))",
        "correct today; silently stops tracking the label's turn",
    ),
    (
        "M3 flip the sign — rotate WITH the label instead of against it",
        ".rotationEffect(.degrees(Self.counterRotationDegrees))",
        ".rotationEffect(.degrees(ChartGutter.rotationDegrees))",
        "the mark is upside down: a half turn, not none",
    ),
    (
        "M4 define the counter-rotation as a literal, breaking the derivation",
        "static var counterRotationDegrees: Double { -ChartGutter.rotationDegrees }",
        "static var counterRotationDegrees: Double { 90 }",
        "two copies of one fact, free to drift (#1832)",
    ),
    (
        "M5 zero the gutter's turn — nothing is sideways, nothing needs righting",
        "static let rotationDegrees: Double = -90",
        "static let rotationDegrees: Double = 0",
        "labels stop running along the axis; the block would pass vacuously",
    ),
    (
        "M6 the LABEL rotates by a literal, so the constant anchors nothing",
        ".rotationEffect(.degrees(ChartGutter.rotationDegrees))\n",
        ".rotationEffect(.degrees(-90))\n",
        "changing the constant would rotate the crest alone",
    ),
    (
        "M7 double-negate — still reads the constant, still lies on its side",
        ".rotationEffect(.degrees(Self.counterRotationDegrees))",
        ".rotationEffect(.degrees(-Self.counterRotationDegrees))",
        "the original defect, wearing the derivation that was supposed to prevent it",
    ),
]

# A mutant that must SURVIVE. A guard that reddens on a comment edit is a guard
# that gets suppressed the first time someone rewords a doc block.
EQUIVALENT = (
    "E1 reword a doc comment (must SURVIVE)",
    "/// The crest's square. It is laid out along the label's RUN",
    "/// The crest's square, laid out along the label's RUN",
)


def run_guard() -> bool:
    """True when the guard is GREEN."""
    result = subprocess.run(
        ["npx", "jest", "--testPathPatterns=chartGuttersDrawOneCrest"],
        cwd=ROOT / "frontend",
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def main() -> int:
    dirty = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=no", "--", SWIFT],
        cwd=ROOT,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if dirty:
        print(f"REFUSING: {SWIFT} has uncommitted changes — commit first.")
        return 2

    original = TARGET.read_text()

    print("BASE: ", end="", flush=True)
    if not run_guard():
        print("RED before any mutant. The battery cannot grade anything.")
        return 2
    print("GREEN\n")

    killed, survived, unapplied = [], [], []

    for name, needle, replacement, harm in MUTANTS:
        if needle not in original:
            unapplied.append(name)
            print(f"  NEEDLE NOT FOUND  {name}")
            continue
        TARGET.write_text(original.replace(needle, replacement, 1))
        green = run_guard()
        subprocess.run(["git", "checkout", "HEAD", "--", SWIFT], cwd=ROOT, check=True)
        if green:
            survived.append((name, harm))
            print(f"  SURVIVED          {name}\n                    -> {harm}")
        else:
            killed.append(name)
            print(f"  killed            {name}")

    name, needle, replacement = EQUIVALENT
    if needle not in original:
        unapplied.append(name)
        print(f"  NEEDLE NOT FOUND  {name}")
    else:
        TARGET.write_text(original.replace(needle, replacement, 1))
        green = run_guard()
        subprocess.run(["git", "checkout", "HEAD", "--", SWIFT], cwd=ROOT, check=True)
        print(f"  {'survived (correct)' if green else 'KILLED (guard is comment-sensitive — BAD)'}  {name}")
        if not green:
            survived.append((name, "the guard reads comments as code"))

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
