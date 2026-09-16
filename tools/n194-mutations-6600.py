#!/usr/bin/env python3
"""native/194 (#6600) — mutation battery for the featured-hub subtitle clock.

Each mutant is a one-site edit that restores some version of the defect the ship
fixed. A mutant that SURVIVES its named killer is a guard that does not guard.

Two killers, deliberately:

  swift — `FeaturedTournamentSubtitleTests`, run with `-only-testing` so the
          battery costs minutes rather than an hour. Proves the picker.
  jest  — `featuredHubSubtitleGoesThroughTheClock`, a source scan. Proves the two
          view BODIES call the picker, which XCTest structurally cannot see.

Mutants 8 and 9 are the point of having both: they rewrite a render site to one
arm of the pair, which is the original defect exactly, and they are EXPECTED to
survive Swift. The battery asserts that survival rather than glossing it — a
guard whose necessity is claimed and not measured is the class this repo keeps
re-learning.

Restores with `git checkout HEAD -- <file>`, never `git checkout -- <file>`: the
latter reads the INDEX, and a stale `git add` silently reverts newer work.
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CATALOG = ROOT / "ios/Bain Luck/Bain Luck/Utilities/FeaturedTournaments.swift"
LEAGUES = ROOT / "ios/Bain Luck/Bain Luck/Views/LeaguesView.swift"
SEARCH = ROOT / "ios/Bain Luck/Bain Luck/Views/SearchView.swift"

SIM = "platform=iOS Simulator,name=iPhone 17"

# (name, file, find, replace, killer)  killer ∈ {"swift", "jest"}
MUTANTS = [
    ("comparison inverted: now >= end", CATALOG,
     "now <= end", "now >= end", "swift"),
    ("boundary exclusive: now < end", CATALOG,
     "now <= end", "now < end", "swift"),
    ("an undated hub goes live forever", CATALOG,
     "            return restingSubtitle\n        }", "            return liveSubtitle\n        }", "swift"),
    ("the picker always rests", CATALOG,
     "        return liveSubtitle\n    }", "        return restingSubtitle\n    }", "swift"),
    ("catalog end date pushed a year out", CATALOG,
     'liveThrough: "2026-09-14T06:00:00+00:00"', 'liveThrough: "2027-09-14T06:00:00+00:00"', "swift"),
    ("catalog resting line claims live", CATALOG,
     'restingSubtitle: "Results and title odds"', 'restingSubtitle: "Live results and title odds"', "swift"),
    ("catalog entry loses its end date", CATALOG,
     '        liveThrough: "2026-09-14T06:00:00+00:00",\n', "", "swift"),
    ("Browse renders liveSubtitle directly", LEAGUES,
     "subtitle: tournament.subtitle(),", "subtitle: tournament.liveSubtitle,", "jest"),
    ("Search renders liveSubtitle directly", SEARCH,
     "Text(hub.subtitle())", "Text(hub.liveSubtitle)", "jest"),
]


def run(cmd, cwd=ROOT):
    return subprocess.run(cmd, cwd=cwd, shell=True, capture_output=True, text=True)


def swift_green() -> bool:
    r = run(
        f'xcodebuild test -project "ios/Bain Luck/Bain Luck.xcodeproj" '
        f'-scheme "Bain Luck" -destination \'{SIM}\' '
        f"-disableAutomaticPackageResolution "
        f"-only-testing:BainLuckTests/FeaturedTournamentSubtitleTests "
        f"-only-testing:BainLuckTests/FeaturedTournamentMatchTests "
        f"OTHER_SWIFT_FLAGS='$(inherited) -Xfrontend -disable-sandbox' 2>&1"
    )
    return "** TEST SUCCEEDED **" in r.stdout


def jest_green() -> bool:
    r = run("npx jest --testPathPatterns=featuredHubSubtitleGoesThroughTheClock",
            cwd=ROOT / "frontend")
    return r.returncode == 0


def restore(path: Path):
    rel = path.relative_to(ROOT)
    run(f'git checkout HEAD -- "{rel}"')


def main() -> int:
    # Scoped to the files this battery actually edits, and to TRACKED changes.
    # A bare `git status --porcelain` refuses on the lane's untracked artifacts
    # directory, which is every session — a guard nobody can get past is a guard
    # nobody runs.
    targets = " ".join(f'"{p.relative_to(ROOT)}"' for p in {CATALOG, LEAGUES, SEARCH})
    dirty = run(f"git status --porcelain --untracked-files=no -- {targets}").stdout.strip()
    if dirty:
        print("REFUSING: a file this battery mutates has uncommitted changes —")
        print("commit first, or the restore eats them.")
        print(dirty)
        return 2

    print("=== baseline")
    base_swift, base_jest = swift_green(), jest_green()
    print(f"  swift {'GREEN' if base_swift else 'RED'}   jest {'GREEN' if base_jest else 'RED'}")
    if not (base_swift and base_jest):
        print("REFUSING: baseline is not green; every kill below would be meaningless.")
        return 2

    killed, survived = 0, []
    for name, path, find, repl, killer in MUTANTS:
        source = path.read_text()
        if source.count(find) != 1:
            print(f"  SKIP  {name}: pattern hits {source.count(find)} sites, need exactly 1")
            survived.append(f"{name} (pattern did not apply)")
            continue
        path.write_text(source.replace(find, repl))

        s_green, j_green = swift_green(), jest_green()
        restore(path)

        died_to = "swift" if not s_green else ("jest" if not j_green else None)
        if died_to == killer:
            extra = ""
            if killer == "jest" and s_green:
                extra = "  (survived swift, as claimed — the scan is load-bearing)"
            print(f"  KILLED  {name}  ← {killer}{extra}")
            killed += 1
        elif died_to is not None:
            print(f"  KILLED  {name}  ← {died_to}  (expected {killer})")
            killed += 1
        else:
            print(f"  SURVIVED  {name}")
            survived.append(name)

    print(f"\n=== {killed}/{len(MUTANTS)} mutants killed")
    for s in survived:
        print(f"  survivor: {s}")
    return 0 if not survived else 1


if __name__ == "__main__":
    sys.exit(main())
