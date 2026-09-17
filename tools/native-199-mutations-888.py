#!/usr/bin/env python3
"""native/199 — mutation battery for #888 (the league page draws what it fetched).

Each mutant rewrites the SHIPPED Swift and asks whether
`LeagueGridSectionKeysMatchTheAPI888Tests` notices. The defect class is a SILENT
dictionary miss — `leagueData.sections[key]` renders an absent key and an empty
section identically — so the guard's whole job is to notice a key that cannot
match. M1-M4 restore the shipped defect; M5-M9 attack the second arm and the
three-parallel-collection drift the rename could have caused.

Same four rules as the #6671 battery: a needle that is absent OR matches more
than once fails the battery rather than counting as a kill; the dirty-tree guard
is scoped to the mutated file with --untracked-files=no; restores with
`git checkout HEAD --`, never `git checkout --` (that reads the INDEX); and any
xcodebuild exit outside {0, 65} is a harness story, not a grade.

Usage:  python3 -u tools/native-199-mutations-888.py
"""

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SWIFT = "ios/Bain Luck/Bain Luck/Views/LeagueGridView.swift"
TARGET = ROOT / SWIFT

PROJECT = ROOT / "ios/Bain Luck/Bain Luck.xcodeproj"
SCHEME = "Bain Luck"
SWIFT_FLAGS = "$(inherited) -Xfrontend -disable-sandbox"
TEST_CLASS = "BainLuckTests/LeagueGridSectionKeysMatchTheAPI888Tests"

ORDER = 'static let sectionOrder = ["series", "awards", "props", "season_stats", "more_markets"]'

MUTANTS = [
    ("M1 restore `playoff_props` (THE ORIGINAL DEFECT)", ORDER,
     ORDER.replace('"props"', '"playoff_props"'),
     "every Props market vanishes again — 31 of them on NCAAF alone"),
    ("M2 restore `novelty` (THE BIGGEST BUCKET)", ORDER,
     ORDER.replace('"more_markets"', '"novelty"'),
     "the classifier's DEFAULT bucket disappears — the single biggest section on most leagues"),
    ("M3 restore both dead keys — the exact shipped state", ORDER,
     ORDER.replace('"props"', '"playoff_props"').replace('"more_markets"', '"novelty"'),
     "378 markets dropped against 189 rendered; NBA shows 11 of 64"),
    ("M4 a plausible near-miss spelling", ORDER,
     ORDER.replace('"more_markets"', '"moreMarkets"'),
     "camelCase against a snake_case API — silent, and exactly how this class recurs"),
    ("M5 drop `more_markets` rather than misspell it", ORDER,
     'static let sectionOrder = ["series", "awards", "props", "season_stats"]',
     "an API section neither rendered nor declared — the second arm must catch this"),
    ("M6 render a section the API never emits at all", ORDER,
     ORDER.replace('"season_stats"', '"season_stats", "player_props"'),
     "a key invented on the client; renders nothing, says nothing"),
    ("M7 silently widen the exemption instead of rendering", ORDER,
     'static let sectionOrder = ["series", "awards", "props", "season_stats"]\n    // exempt: more_markets',
     "a comment is not a declaration; the set must move, not the prose"),
    ("M8 strand a label on the old key (rename drift)",
     '"props": "Props",', '"playoff_props": "Props",',
     "the header falls back to `key.capitalized` and reads 'Props' by luck, 'More_markets' by default"),
    ("M9 strand an icon on the old key", '"more_markets": "sparkles",',
     '"novelty": "sparkles",',
     "the section draws a generic list.bullet with no test noticing"),
]

EQUIVALENT = [
    ("E1 reword the rationale comment (must SURVIVE)",
     "// #888: these keys must be keys the API actually emits.",
     "// #888: every key here has to be one the API actually emits."),
    ("E2 reorder two sections (must SURVIVE — this guard is about membership)",
     ORDER, 'static let sectionOrder = ["awards", "series", "props", "season_stats", "more_markets"]'),
]


def udid() -> str:
    out = subprocess.run(["xcrun", "simctl", "list", "devices", "available"],
                         capture_output=True, text=True, check=True).stdout
    for line in out.splitlines():
        if re.match(r"^\s+iPhone ", line):
            m = re.search(r"\(([0-9A-Fa-f-]{36})\)", line)
            if m:
                return m.group(1)
    raise SystemExit("NO iPhone SIMULATOR AVAILABLE — the battery cannot run.")


def run_guard(device: str) -> bool:
    r = subprocess.run(
        ["xcodebuild", "test", "-project", str(PROJECT), "-scheme", SCHEME,
         "-destination", f"id={device}", "-only-testing:" + TEST_CLASS,
         f"OTHER_SWIFT_FLAGS={SWIFT_FLAGS}"],
        cwd=ROOT, capture_output=True, text=True)
    if r.returncode not in (0, 65):
        raise SystemExit(f"xcodebuild exited {r.returncode} — the gate never ran.\n{r.stdout[-3000:]}")
    return r.returncode == 0


def main() -> int:
    dirty = subprocess.run(["git", "status", "--porcelain", "--untracked-files=no", "--", SWIFT],
                           cwd=ROOT, capture_output=True, text=True).stdout.strip()
    if dirty:
        print(f"REFUSING: {SWIFT} has uncommitted changes — commit first.")
        return 2

    device = udid()
    print(f"simulator: {device}\n")
    original = TARGET.read_text()

    print("BASE: ", end="", flush=True)
    if not run_guard(device):
        print("RED before any mutant. The battery cannot grade anything.")
        return 2
    print("GREEN\n", flush=True)

    killed, survived, unapplied = [], [], []
    for name, needle, replacement, harm in MUTANTS:
        hits = original.count(needle)
        if hits != 1:
            unapplied.append(f"{name} (needle matches {hits}x)")
            print(f"  NEEDLE {'ABSENT' if hits == 0 else 'AMBIGUOUS'}   {name}", flush=True)
            continue
        TARGET.write_text(original.replace(needle, replacement, 1))
        green = run_guard(device)
        subprocess.run(["git", "checkout", "HEAD", "--", SWIFT], cwd=ROOT, check=True)
        if green:
            survived.append((name, harm))
            print(f"  SURVIVED          {name}\n                    -> {harm}", flush=True)
        else:
            killed.append(name)
            print(f"  killed            {name}", flush=True)

    print(flush=True)
    for name, needle, replacement in EQUIVALENT:
        if original.count(needle) != 1:
            unapplied.append(f"{name} (needle not unique)")
            print(f"  NEEDLE NOT FOUND  {name}", flush=True)
            continue
        TARGET.write_text(original.replace(needle, replacement, 1))
        green = run_guard(device)
        subprocess.run(["git", "checkout", "HEAD", "--", SWIFT], cwd=ROOT, check=True)
        print(f"  {'survived (correct)' if green else 'KILLED (over-tight — BAD)'}  {name}", flush=True)
        if not green:
            survived.append((name, "the guard reads cosmetics/order as contract"))

    print(f"\n{len(killed)}/{len(MUTANTS)} defect mutants killed.")
    if unapplied:
        print(f"BATTERY FAILURE — {len(unapplied)} never applied: {unapplied}")
        return 2
    if survived:
        print("SURVIVORS — the guard has holes:")
        for n, h in survived:
            print(f"  {n}: {h}")
        return 1
    print("No survivors.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
