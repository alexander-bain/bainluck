#!/usr/bin/env python3
"""#7015 mutation battery — does the guard suite actually hold the fix down?

Each mutant edits a tracked file, runs ONLY the #7015 suite, and restores the
file. A mutant that survives is a hole in the suite, not a curiosity.

Mutant D is the pre-fix tree verbatim: the eight-key register that shipped the
three placeholder cards. It is the red-first proof.

Mutant M mutates the TEST, not the product: it breaks the authority reader's
regex so it matches nothing. It must ERROR (the reader throws), not pass — that
is the anti-vacuity proof, and without it every "for slug of authoritySlugs"
assertion could be green over an empty list.

    cd ~/bainluck-dev/ux && python3 tools/ux1343-mutations-7015.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MODULE = REPO / "frontend" / "lib" / "sportDirectory.ts"
SUITE = REPO / "frontend" / "__tests__" / "sportDirectoryNamesEverySport7015.test.ts"

BOXING_ENTRY = """  boxing: {
    icon: "\U0001f94a",
    description: "Title fights & marquee bouts",
    tint: "bg-amber-50 hover:bg-amber-100",
  },
"""
MOTORSPORTS_ENTRY = """  motorsports: {
    icon: "\U0001f3ce️",
    description: "Formula 1, NASCAR",
    tint: "bg-blue-50 hover:bg-blue-100",
  },
"""
ESPORTS_ENTRY = """  esports: {
    icon: "\U0001f3ae",
    description: "League of Legends, Counter-Strike 2, Valorant",
    tint: "bg-indigo-50 hover:bg-indigo-100",
  },
"""

PLURAL_LINE = '  return `${leagueCount} league${leagueCount === 1 ? "" : "s"}`;'

FALLBACK_BLOCK = """  if (!entry) {
    return {
      icon: FALLBACK_SPORT_ICON,
      subtitle: leagueCountLabel(leagueCount),
      tintClass: FALLBACK_SPORT_TINT,
      isFallback: true,
    };
  }
"""

# (id, description, target file, old, new)
MUTANTS: list[tuple[str, str, Path, str, str]] = [
    ("A", "Boxing dropped from the register", MODULE, BOXING_ENTRY, ""),
    ("B", "Motorsports dropped from the register", MODULE, MOTORSPORTS_ENTRY, ""),
    ("C", "Esports dropped from the register", MODULE, ESPORTS_ENTRY, ""),
    (
        "D",
        "THE PRE-FIX TREE: all three missing (eight-key register)",
        MODULE,
        BOXING_ENTRY + MOTORSPORTS_ENTRY + ESPORTS_ENTRY,
        "",
    ),
    (
        "E",
        'always plural — restores "1 leagues"',
        MODULE,
        PLURAL_LINE,
        "  return `${leagueCount} leagues`;",
    ),
    (
        "F",
        "always singular",
        MODULE,
        PLURAL_LINE,
        "  return `${leagueCount} league`;",
    ),
    (
        "G",
        "THE TEMPTING FIX: Boxing gets the glove, MMA keeps it too",
        MODULE,
        '  mma: {\n    icon: "\U0001f94b",',
        '  mma: {\n    icon: "\U0001f94a",',
    ),
    (
        "H",
        "Boxing mapped, but to the trophy",
        MODULE,
        '  boxing: {\n    icon: "\U0001f94a",',
        '  boxing: {\n    icon: "\U0001f3c6",',
    ),
    (
        "I",
        "the three mapped with empty copy — back to a bare count",
        MODULE,
        '    description: "Title fights & marquee bouts",',
        '    description: "",',
    ),
    (
        "J",
        "fallback deleted — an unknown sport crashes",
        MODULE,
        FALLBACK_BLOCK,
        '  if (!entry) {\n    throw new Error(`unknown sport ${slug}`);\n  }\n',
    ),
    (
        "K",
        "fallback never flags itself",
        MODULE,
        "      isFallback: true,",
        "      isFallback: false,",
    ),
    (
        "L",
        "a phantom sport the site does not serve",
        MODULE,
        "  esports: {",
        '  cricket: {\n    icon: "\U0001f3cf",\n    description: "IPL",\n'
        '    tint: "bg-teal-50 hover:bg-teal-100",\n  },\n  esports: {',
    ),
    (
        "N",
        "Boxing mapped, but to the grey fallback tint",
        MODULE,
        '    tint: "bg-amber-50 hover:bg-amber-100",',
        '    tint: "bg-surface-elevated hover:bg-surface-card",',
    ),
    (
        "M",
        "ANTI-VACUITY (mutates the TEST): authority reader matches nothing",
        SUITE,
        r'/^ {4}"([a-z_]+)": \{$/gm',
        r'/^ {4}"([A-Z_]+)": \{$/gm',
    ),
]


def run_suite() -> tuple[int, str]:
    proc = subprocess.run(
        ["npx", "jest", "--testPathPatterns=sportDirectoryNamesEverySport7015"],
        cwd=REPO / "frontend",
        capture_output=True,
        text=True,
    )
    return proc.returncode, proc.stdout + proc.stderr


def main() -> int:
    baseline_code, baseline_out = run_suite()
    if baseline_code != 0:
        print("BASELINE IS RED — fix the suite before measuring mutants.")
        print(baseline_out[-3000:])
        return 2
    print(f"baseline: GREEN ({baseline_out.strip().splitlines()[-4].strip()})\n")

    killed, survived = [], []
    for mid, desc, target, old, new in MUTANTS:
        original = target.read_text()
        if old not in original:
            print(f"  {mid}  ?? NOT APPLIED — anchor missing: {desc}")
            survived.append((mid, desc, "anchor missing"))
            continue
        try:
            target.write_text(original.replace(old, new, 1))
            code, out = run_suite()
        finally:
            target.write_text(original)

        if code == 0:
            print(f"  {mid}  SURVIVED  {desc}")
            survived.append((mid, desc, "suite stayed green"))
        else:
            failing = [
                line.strip()
                for line in out.splitlines()
                if line.strip().startswith(("●", "✕"))
            ]
            first = failing[0] if failing else f"exit {code}"
            print(f"  {mid}  killed    {desc}\n           by: {first}")
            killed.append(mid)

    print(f"\n{len(killed)}/{len(MUTANTS)} killed: {', '.join(killed)}")
    if survived:
        print("SURVIVORS (holes in the suite):")
        for mid, desc, why in survived:
            print(f"  {mid}  {desc} — {why}")
        return 1
    print("No survivors.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
