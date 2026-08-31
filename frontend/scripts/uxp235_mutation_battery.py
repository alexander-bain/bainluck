#!/usr/bin/env python3
"""UX-P235 mutation battery — board item 14, "a wrong logo is worse than no logo".

This ship has TWO directions to get wrong and the battery attacks both:
  * refusing too LITTLE — the bird and the fruit come back (A-D);
  * refusing too MUCH — the four real companies lose their logos, which "passes"
    a wrong-logo test while losing the thing Alex said he liked (E-G).

Plus the fallback-treatment half (H-J) and the absence rule (K).

For every mutant we PROVE the edit applied and require a non-zero exit. Sources are
restored inside `finally:` and verified byte-for-byte by sha256.

Run from `frontend/`:  python3 scripts/uxp235_mutation_battery.py
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path

IMAGES = Path("lib/images.ts")
ENTITY = Path("components/EntityImage.tsx")

TEST_PATTERN = "brandLogoRefusal|entityImageFallback"

MUTANTS: list[tuple[str, Path, str, str, str]] = [
    (
        "A",
        IMAGES,
        "      if (wikipediaSummaryIsNotABrand(data)) {\n        cacheSet(cacheKey, null);\n        return null;\n      }\n",
        "",
        "🔴 THE SHIPPED DEFECT — the resolver stops refusing, so Peacock is a bird "
        "and Apple is a fruit again",
    ),
    (
        "B",
        IMAGES,
        "  if (summary.type === \"disambiguation\") return true;",
        "",
        "an ambiguous name is no longer refused, though Wikipedia says so outright",
    ),
    (
        "C",
        IMAGES,
        "  /\\b(fruit|vegetable|plant|tree|flower|herb)\\b(?!.*\\b(company|brand|logo|band|film)\\b)/i,",
        "",
        "the fruit rule goes and Apple is a photograph of a Pink Lady again. "
        "⚠️ This anchor was originally the narrower `edible fruit` line, which "
        "SURVIVED — because the broader rule already covered it, so that line was "
        "dead weight. It has been deleted rather than kept as a passenger",
    ),
    (
        "D",
        IMAGES,
        "  return NOT_A_BRAND_DESCRIPTIONS.some((re) => re.test(d));",
        "  return false;",
        "the description rules are built and never consulted — a vacuous list",
    ),
    (
        "E",
        IMAGES,
        "  return NOT_A_BRAND_DESCRIPTIONS.some((re) => re.test(d));",
        "  return true;",
        "🔴 OVER-CORRECTION: everything is refused. A wrong logo is worse than no "
        "logo, but no logo ANYWHERE throws away the thing Alex said he liked",
    ),
    (
        "F",
        IMAGES,
        "  /\\b(fruit|vegetable|plant|tree|flower|herb)\\b(?!.*\\b(company|brand|logo|band|film)\\b)/i,",
        "  /\\b(fruit|vegetable|plant|tree|flower|herb|service|club|team)\\b/i,",
        "🔴 OVER-CORRECTION: the guard widens until it eats 'American video "
        "streaming service' — Netflix, Hulu and Paramount+ all lose their logos",
    ),
    (
        "G",
        IMAGES,
        "  /\\b(bird|fish|mammal|insect|reptile|amphibian)s?\\b(?!.*\\b(team|club|logo|company|brand)\\b)/i,",
        "  /\\b(bird|fish|mammal|insect|reptile|amphibian|horse|racehorse)s?\\b/i,",
        "OVER-CORRECTION into an adjacent surface: a RACEHORSE outcome loses its "
        "picture, and horse racing is a real market here",
    ),
    (
        "H",
        IMAGES,
        "  if (!d) return false;",
        "  if (!d) return true;",
        "🔴 ABSENCE READ AS A VERDICT (gotcha #53): a page with no short "
        "description is treated as proven-not-a-brand and silently loses its image",
    ),
    (
        "I",
        ENTITY,
        "  const isPlaceholder = fallbackColor === DEFAULT_FALLBACK_COLOR;",
        "  const isPlaceholder = false;",
        "the fallback goes back to a solid disc with bold white initials — a "
        "non-answer impersonating a brand mark, which is item 14's other half",
    ),
    (
        "J",
        ENTITY,
        "  const isPlaceholder = fallbackColor === DEFAULT_FALLBACK_COLOR;",
        "  const isPlaceholder = true;",
        "OVER-CORRECTION: a real TEAM COLOUR is thrown away and rendered as a "
        "placeholder, losing information the caller actually had",
    ),
    (
        "K",
        ENTITY,
        'aria-label={isPlaceholder ? `${name} (no logo available)` : name}',
        "aria-label={initials}",
        "the accessible name becomes two letters — a screen reader hears 'A', not "
        "'Amazon', and cannot tell a resolved logo from a placeholder",
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
    files = (IMAGES, ENTITY)
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
