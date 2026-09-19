#!/usr/bin/env python3
"""Mutation battery for #6929's guard — is every clause load-bearing?

A green guard proves nothing until the defect it was written for can make it red. This restores
the shipped markup (and several near-misses that a careless fix would have produced), runs the
guard against each, and requires a RED.

Runs against the COMMITTED tree, so a crash cannot leave the fix on the floor; each mutant prints
`applied` / `restored` and the anchor count is asserted to be exactly 1 — an anchor that matches 0
or 2 places has measured nothing and says so instead of passing quietly.

Usage: python3 tools/ux1334-mutations-6929-chip.py
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FE = ROOT / "frontend"
GROUP = FE / "components/discover/GroupCard.tsx"
THEME = FE / "components/discover/ThemeBundleCard.tsx"

FIXED = "min-w-0 max-w-full truncate"
SHIPPED = "whitespace-nowrap"

# (name, file, find, replace, why this mutant exists)
MUTANTS = [
    (
        "revert-GroupCard",
        GROUP, FIXED, SHIPPED,
        "the exact defect, in the file the issue measured it in",
    ),
    (
        "revert-ThemeBundleCard",
        THEME, FIXED, SHIPPED,
        "the sibling file; the two shipped identical markup, so a one-file fix is the likely miss",
    ),
    (
        "drop-truncate-GroupCard",
        GROUP, FIXED, "min-w-0 max-w-full",
        "chip shrinks but the text is cut with NO ellipsis — the reader-visible defect, smaller",
    ),
    (
        "drop-min-w-0-GroupCard",
        GROUP, FIXED, "max-w-full truncate",
        "a flex item with min-width:auto never shrinks, so the ellipsis can never engage",
    ),
    (
        "drop-max-w-full-GroupCard",
        GROUP, FIXED, "min-w-0 truncate",
        "the cap against the container is gone; the predicate must want all three",
    ),
    (
        "drop-truncate-ThemeBundleCard",
        THEME, FIXED, "min-w-0 max-w-full",
        "same near-miss on the branch a one-file reviewer is least likely to open",
    ),
    (
        "card-stops-clipping",
        GROUP, 'shadow-lg overflow-hidden"', 'shadow-lg"',
        "PREMISE CONTROL: 'fixing' the cut by letting the chip paint over the page instead",
    ),
    (
        "blanket-sweep-sibling",
        THEME, 'text-xs text-text-muted whitespace-nowrap', 'text-xs text-text-muted truncate',
        "SCOPE CONTROL: running truncate over every nowrap also degrades '· N related'",
    ),
]

TEST = "groupCardChipStopsCuttingWords6929"


def run_guard() -> bool:
    """True when the guard passes."""
    p = subprocess.run(
        ["npx", "jest", f"--testPathPatterns={TEST}"],
        cwd=FE, capture_output=True, text=True,
    )
    return p.returncode == 0


def main() -> int:
    dirty = subprocess.run(
        ["git", "status", "--porcelain", "frontend/components/discover"],
        cwd=ROOT, capture_output=True, text=True,
    ).stdout.strip()
    if dirty:
        print("REFUSING: components are dirty; commit first so a crash cannot lose the fix.")
        print(dirty)
        return 2

    if not run_guard():
        print("REFUSING: the guard is RED on the unmutated tree. Nothing below would mean anything.")
        return 2
    print(f"baseline: guard GREEN on the committed tree\n")

    caught, survived = [], []
    for name, path, find, repl, why in MUTANTS:
        src = path.read_text()
        n = src.count(find)
        if n != 1:
            print(f"  {name:28s} ANCHOR NOT FOUND (count={n}) — measured nothing")
            survived.append(f"{name} (bad anchor)")
            continue
        try:
            path.write_text(src.replace(find, repl))
            print(f"  {name:28s} applied   ", end="", flush=True)
            green = run_guard()
        finally:
            path.write_text(src)
            assert path.read_text() == src, f"RESTORE FAILED for {path}"
        print(f"restored  -> {'SURVIVED (guard still green)' if green else 'CAUGHT (red)'}   [{why}]")
        (survived if green else caught).append(name)

    print(f"\nCAUGHT {len(caught)}/{len(MUTANTS)}")
    if survived:
        print("SURVIVORS (each is a hole in the guard):")
        for s in survived:
            print(f"  - {s}")
        return 1
    print("No survivors: every clause in the guard is load-bearing.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
