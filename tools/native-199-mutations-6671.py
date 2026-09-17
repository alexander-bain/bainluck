#!/usr/bin/env python3
"""native/199 — mutation battery for #6671 (Settings shows what the reader stored).

Each mutant rewrites the SHIPPED Swift and asks whether
`SettingsInterestsShowWhatTheReaderStored6671Tests` notices. A mutant the guard
does not notice is a hole in the guard, not a curiosity.

M1-M6 reconstruct the defect exactly as it shipped: the tile keys spelled in the
onboarding vocabulary while the server serves the compressed one. M7-M12 attack
the two translation helpers the fix added, because a helper that is never
measured at the reader's scale is a helper that can be quietly wrong.

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

Usage:  python3 tools/native-199-mutations-6671.py
"""

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

MODELS = "ios/Bain Luck/Bain Luck/Models/OnboardingModels.swift"
VIEWMODEL = "ios/Bain Luck/Bain Luck/ViewModels/PreferencesViewModel.swift"
FILES = [MODELS, VIEWMODEL]

PROJECT = ROOT / "ios/Bain Luck/Bain Luck.xcodeproj"
SCHEME = "Bain Luck"
SWIFT_FLAGS = "$(inherited) -Xfrontend -disable-sandbox"
TEST_CLASS = "BainLuckTests/SettingsInterestsShowWhatTheReaderStored6671Tests"

# (name, file, needle, replacement, what a reader would see if this shipped)
MUTANTS = [
    # ── The defect as it actually shipped ──────────────────────────────────
    (
        "M1 NFL back to the onboarding spelling (THE ORIGINAL DEFECT)",
        MODELS,
        'SportItem(key: "nfl", name: "NFL"',
        'SportItem(key: "football", name: "NFL"',
        "the NFL tile reads Nah for a reader who set it to Love it",
    ),
    (
        "M2 College Football back to `cfb`",
        MODELS,
        'SportItem(key: "college_football", name: "College Football"',
        'SportItem(key: "cfb", name: "College Football"',
        "the tile reads Nah AND the tap is stored verbatim where nothing reads it",
    ),
    (
        "M3 NBA back to `basketball`",
        MODELS,
        'SportItem(key: "nba", name: "NBA"',
        'SportItem(key: "basketball", name: "NBA"',
        "the NBA tile reads Nah, and one tap moves College Basketball too",
    ),
    (
        "M4 College Basketball back to `cbb`",
        MODELS,
        'SportItem(key: "college_basketball", name: "College Basketball"',
        'SportItem(key: "cbb", name: "College Basketball"',
        "the tile reads Nah and the tap is inert",
    ),
    (
        "M5 Golf reads its own write key, as it did before",
        MODELS,
        'servedKeys: ["golf_pga", "golf_dp_world", "golf_lpga", "golf_liv"]',
        'servedKeys: ["golf"]',
        "Golf reads Nah for every reader — the server never serves `golf` back",
    ),
    (
        "M6 Golf reads only the PGA tour",
        MODELS,
        'servedKeys: ["golf_pga", "golf_dp_world", "golf_lpga", "golf_liv"]',
        'servedKeys: ["golf_pga"]',
        "an LPGA-only reader sees Nah on the one golf tile there is",
    ),
    # ── The read helper ────────────────────────────────────────────────────
    (
        "M7 the view model stores the served dict raw again",
        VIEWMODEL,
        "sportAffinities = OnboardingSportsData.tileAffinities(fromServed: response.sportAffinities)",
        "sportAffinities = response.sportAffinities",
        "the pre-fix line: the grid asks by tile key and the dict is server-keyed",
    ),
    (
        "M8 take the FIRST served value instead of the strongest",
        MODELS,
        "if let best = item.servedKeys.compactMap({ served[$0] }).max() {",
        "if let best = item.servedKeys.compactMap({ served[$0] }).first {",
        "Golf shows whichever tour is listed first, not what the reader cares most about",
    ),
    (
        "M9 an absent preference becomes a stored zero",
        MODELS,
        "if let best = item.servedKeys.compactMap({ served[$0] }).max() {\n                affinities[item.key] = best\n            }",
        "affinities[item.key] = item.servedKeys.compactMap({ served[$0] }).max() ?? 0.0",
        "every untouched tile is PUT back as an explicit Nah the reader never chose",
    ),
    # ── The write helper ───────────────────────────────────────────────────
    (
        "M10 the save stops preserving categories with no tile",
        MODELS,
        "var payload = served.filter { !ownedKeys.contains($0.key) }",
        "var payload: [String: Double] = [:]",
        "one tap in iOS Settings erases the reader's Motorsport preference",
    ),
    (
        "M11 the save sends the served dict plus the tiles (THE CLOBBER)",
        MODELS,
        "var payload = served.filter { !ownedKeys.contains($0.key) }",
        "var payload = served",
        "`golf_lpga` rides along with `golf`; expansion order decides the answer",
    ),
    (
        "M12 ownedKeys forgets the served spellings",
        MODELS,
        "Set(allItems.flatMap { [$0.key] + $0.servedKeys })",
        "Set(allItems.map(\\.key))",
        "the four golf tours survive the filter and fight the legacy key",
    ),
]

# Mutants that must SURVIVE. A guard that reddens on a comment edit or on a
# purely cosmetic field is a guard that gets suppressed the first time someone
# rewords a doc block.
EQUIVALENT = [
    (
        "E1 reword a doc comment (must SURVIVE)",
        MODELS,
        "/// Static catalog of sports and non-sports categories shown during onboarding.",
        "/// The catalog of sports and non-sports categories the grids draw.",
    ),
    (
        "E2 change a tile's emoji (must SURVIVE — this guard is about keys)",
        MODELS,
        'SportItem(key: "cricket", name: "Cricket", emoji: "\\u{1F3CF}"',
        'SportItem(key: "cricket", name: "Cricket", emoji: "\\u{1F3AF}"',
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
    print(f"simulator: {device}\n")

    originals = {f: (ROOT / f).read_text() for f in FILES}

    print("BASE: ", end="", flush=True)
    if not run_guard(device):
        print("RED before any mutant. The battery cannot grade anything.")
        return 2
    print("GREEN\n")

    killed, survived, unapplied = [], [], []

    for name, target, needle, replacement, harm in MUTANTS:
        source = originals[target]
        hits = source.count(needle)
        if hits == 0:
            unapplied.append(f"{name} (needle absent)")
            print(f"  NEEDLE NOT FOUND  {name}")
            continue
        if hits > 1:
            unapplied.append(f"{name} (needle matches {hits}x)")
            print(f"  NEEDLE AMBIGUOUS  {name} — matches {hits} places, grades code nobody chose")
            continue
        (ROOT / target).write_text(source.replace(needle, replacement, 1))
        green = run_guard(device)
        restore()
        if green:
            survived.append((name, harm))
            print(f"  SURVIVED          {name}\n                    -> {harm}")
        else:
            killed.append(name)
            print(f"  killed            {name}")

    print()
    for name, target, needle, replacement in EQUIVALENT:
        source = originals[target]
        if source.count(needle) != 1:
            unapplied.append(f"{name} (needle not unique)")
            print(f"  NEEDLE NOT FOUND  {name}")
            continue
        (ROOT / target).write_text(source.replace(needle, replacement, 1))
        green = run_guard(device)
        restore()
        print(f"  {'survived (correct)' if green else 'KILLED (over-tight — BAD)'}  {name}")
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
