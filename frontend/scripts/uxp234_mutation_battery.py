#!/usr/bin/env python3
"""UX-P234 mutation battery — one pin affordance, both places (board items 15 + 16).

The mutants that matter here are the DRIFT ones: this ship exists because `PinIcon`
was defined three times and the detail page had drifted away from all three into a
bare word. So the battery attacks the ways the affordance could silently stop being
one thing (A-D), the ways a state could stop being visible or reachable (E-H), and
the architecture regression I caused and fixed (I-J).

For every mutant we PROVE the edit applied and require a non-zero exit. Sources are
restored inside `finally:` and verified byte-for-byte by sha256.

Run from `frontend/`:  python3 scripts/uxp234_mutation_battery.py
"""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
import sys
from pathlib import Path

BTN = Path("components/PinButton.tsx")
PAGE = Path("app/futures/[id]/page.tsx")
CARD = Path("components/discover/FuturesCard.tsx")
SHARED = Path("components/discover/shared.tsx")
DISCOVER = Path("app/discover/page.tsx")

TEST_PATTERN = "pinAffordance"

MUTANTS: list[tuple[str, Path, str, str, str]] = [
    (
        "A",
        PAGE,
        "<PinButton",
        "<button onClick={() => togglePin(marketId)}>Pin</button>{/*",
        "🔴 THE SHIPPED DEFECT — item 15's bare word comes back on the detail page",
    ),
    (
        "B",
        SHARED,
        "      {pin && (\n",
        "      {false && (\n",
        "🔴 THE SHIPPED DEFECT — item 16: Discover loses its pin entirely",
    ),
    (
        "C",
        DISCOVER,
        "                      pinFor={pinForFutures}\n",
        "",
        "the page stops handing the binding down, so the affordance is built and "
        "never reaches a card",
    ),
    (
        "D",
        CARD,
        "onShare={onShare} pin={pin} />",
        "onShare={onShare} />",
        "ONE of the four card variants loses its pin — the drift this ship exists "
        "to prevent, and invisible to any test that renders only one variant",
    ),
    (
        "E",
        BTN,
        '      {variant === "labelled" && <span>{pinned ? "Pinned" : "Pin"}</span>}',
        "",
        "the labelled variant loses its word — item 15 over-corrected into an "
        "unlabelled icon on a surface with room for the word",
    ),
    (
        "F",
        BTN,
        "className={PIN_ICON_SIZE[variant]} />",
        'className="hidden" />',
        "the icon is present in the markup but never painted — a bare word again, "
        "wearing an svg",
    ),
    (
        "G",
        BTN,
        '  if (pinned) return "Unpin";\n  return disabled ? "Max 6 pins" : "Pin";',
        '  return disabled ? "Max 6 pins" : pinned ? "Unpin" : "Pin";',
        "🔴 AT THE CEILING A PINNED ITEM READS 'Max 6 pins' — a reader with 6 pins "
        "can then never unpin anything and is stuck forever",
    ),
    (
        "H",
        BTN,
        "  const disabled = atMax && !pinned;",
        "  const disabled = atMax;",
        "the same trap in the DISABLED attribute rather than the wording — the "
        "pinned button goes dead at the ceiling",
    ),
    (
        "I",
        BTN,
        "      aria-pressed={pinned}",
        "",
        "the state stops being exposed to assistive tech — visible only as a "
        "colour, which is not a state",
    ),
    (
        "J",
        BTN,
        "    preventDefault: opts.swallow,\n    stopPropagation: opts.swallow,",
        "    preventDefault: false,\n    stopPropagation: false,",
        "the click guard goes, so pinning a Discover card also navigates to the "
        "detail page and the pin appears to do nothing",
    ),
    (
        "K",
        SHARED,
        "          pinned={pin.pinned}",
        "          pinned={false}",
        "the pin renders but stops reflecting state — always shows 'Pin', so a "
        "reader can never see what they have already pinned",
    ),
    (
        "L",
        BTN,
        '      fill="none"\n      stroke="currentColor"',
        '      fill="currentColor"\n      stroke="currentColor"',
        "pinned and unpinned become the SAME glyph — the state is no longer "
        "legible without comparing colours",
    ),
]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_guards() -> int:
    proc = subprocess.run(
        ["npx", "jest", "--testPathPatterns", TEST_PATTERN],
        capture_output=True,
        text=True,
        env={**os.environ, "TZ": "UTC"},
    )
    return proc.returncode


def main() -> int:
    files = (BTN, PAGE, CARD, SHARED, DISCOVER)
    originals = {p: p.read_text() for p in files}
    original_shas = {p: sha(p) for p in files}

    baseline = run_guards()
    if baseline != 0:
        print(f"BASELINE IS NOT GREEN (exit {baseline}) — battery is meaningless")
        return 2
    print("baseline: GREEN\n")

    killed, survived = [], []
    try:
        for mid, path, find, repl, why in MUTANTS:
            src = originals[path]
            hits = src.count(find)
            # Mutant D deliberately targets a repeated anchor: dropping the pin from
            # exactly ONE of the four variants is the defect being modelled, so it
            # replaces the first occurrence only rather than demanding uniqueness.
            if mid == "D":
                if hits < 2:
                    print(f"{mid}: ANCHOR APPEARS {hits}x, expected the repeated one — battery invalid")
                    return 2
                mutated = src.replace(find, repl, 1)
            else:
                if hits != 1:
                    print(f"{mid}: ANCHOR NOT UNIQUE ({hits} hits) — battery invalid")
                    return 2
                mutated = src.replace(find, repl)

            assert mutated != src, f"{mid}: mutation is a no-op"
            path.write_text(mutated)
            assert sha(path) != original_shas[path], f"{mid}: file unchanged on disk"

            code = run_guards()
            path.write_text(src)
            assert sha(path) == original_shas[path], f"{mid}: restore not byte-identical"

            if code != 0:
                killed.append(mid)
                print(f"{mid}: KILLED (exit {code}) — {why}")
            else:
                survived.append(mid)
                print(f"{mid}: *** SURVIVED *** — {why}")
    finally:
        for path, src in originals.items():
            path.write_text(src)
            assert sha(path) == original_shas[path], f"RESIDUE: {path} not restored"
        print("\nall sources restored, sha256 verified")

    print(f"\n{len(killed)}/{len(MUTANTS)} killed")
    if survived:
        print(f"SURVIVORS: {', '.join(survived)}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
