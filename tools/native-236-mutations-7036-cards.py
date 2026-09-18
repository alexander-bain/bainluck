#!/usr/bin/env python3
"""native/236 — mutation run for #7036 arm 2 (the two game CARDS).

Arm 1 (native/234) put the WCAG floor under the event page and mutation-tested
the FLOOR. This run tests the thing arm 2 actually adds: the **wiring of two more
surfaces into it**. So the mutants here are call-site mutants, not maths mutants —
the maths is already covered by `tools/native-234-mutations-7036.py` and is not
re-run.

Mutants 1 and 2 are the reported defect verbatim on each card (the call site going
back to raw `primaryColor`), so this run doubles as the red-first proof for both.

A mutant that SURVIVES is a hole in the guard suite, not a curiosity.

Usage:  python3 tools/native-236-mutations-7036-cards.py [--list]
"""
import subprocess, sys, pathlib, signal, atexit

WORKTREE = pathlib.Path("/Users/bain/bainluck-dev/native")
ROOT = WORKTREE / "ios/Bain Luck"
HELPER = ROOT / "Bain Luck/Utilities/TeamTextContrast.swift"
ROW = ROOT / "Bain Luck/Components/EventCardView.swift"
CARD = ROOT / "Bain Luck/Components/DiscoverEventCard.swift"
PAGE = ROOT / "Bain Luck/Views/EventDetailView.swift"
SIM = "D2DA47A0-85F6-4BF8-AEFF-33146AE3EB05"

WIRED = """        TeamTextContrast.cardColorHexes(
            awayHex: event.awayTeamData?.primaryColor,
            homeHex: event.homeTeamData?.primaryColor
        )"""
REVERTED = """        ProbabilityBarPalette.pair(
            awayHex: event.awayTeamData?.primaryColor,
            homeHex: event.homeTeamData?.primaryColor
        )"""

# (name, file, find, replace, why-it-matters)
MUTANTS = [
    ("1-sports-row-reverts-to-raw-primaryColor", ROW, WIRED, REVERTED,
     "THE PHOTOGRAPHED DEFECT. Rennes v Lyon renders with no percentage at all."),

    ("2-discover-card-reverts-to-raw-primaryColor", CARD, WIRED, REVERTED,
     "the same defect on the app's default landing surface, where BOTH numbers are painted"),

    ("3-event-page-reverts-to-raw-primaryColor", PAGE,
     """        TeamTextContrast.cardColors(
            awayHex: event.awayTeamData?.primaryColor,
            homeHex: event.homeTeamData?.primaryColor
        )""",
     """        ProbabilityBarPalette.colors(
            awayHex: event.awayTeamData?.primaryColor,
            homeHex: event.homeTeamData?.primaryColor
        )""",
     "arm 1 regressed by arm 2's rename — the exact way a rename loses a fix"),

    ("4-sports-row-floors-the-away-side-only", ROW, WIRED,
     """        ProbabilityBarPalette.pair(
            awayHex: TeamTextContrast.usableForText(event.awayTeamData?.primaryColor),
            homeHex: event.homeTeamData?.primaryColor
        )""",
     "half a fix. Lyon is the HOME side in the photographed card, so an away-only "
     "floor leaves the reported specimen exactly as broken while looking fixed"),

    ("5-discover-card-floors-the-home-side-only", CARD, WIRED,
     """        ProbabilityBarPalette.pair(
            awayHex: event.awayTeamData?.primaryColor,
            homeHex: TeamTextContrast.usableForText(event.homeTeamData?.primaryColor)
        )""",
     "the other half. A suite that only ever asserts the home slot passes on this"),

    ("6-sports-row-reads-the-other-sides-colour", ROW,
     """            awayHex: event.awayTeamData?.primaryColor,
            homeHex: event.homeTeamData?.primaryColor
        )
    }
    private var barColors: (away: Color, home: Color) {""",
     """            awayHex: event.homeTeamData?.primaryColor,
            homeHex: event.homeTeamData?.primaryColor
        )
    }
    private var barColors: (away: Color, home: Color) {""",
     "both slots fed the same team — the #2902 flat-bar defect, re-introduced"),

    ("7-discover-card-drops-the-floor-for-absent-colours", CARD,
     "    var barColorHexes: (away: String, home: String) {\n" + WIRED,
     "    var barColorHexes: (away: String, home: String) {\n"
     '        (event.awayTeamData?.primaryColor ?? ProbabilityBarPalette.awayDefault,\n'
     '         event.homeTeamData?.primaryColor ?? ProbabilityBarPalette.homeDefault)',
     "a plausible 'simplification' that keeps the defaults but loses the floor entirely"),

    ("8-floor-becomes-a-no-op-under-both-cards", HELPER,
     "        readableOnCard(hex) ? hex : nil\n    }",
     "        hex\n    }",
     "the shared entry point stops flooring; every name in the file still reads right"),

    ("9-shared-entry-point-floors-neither-slot", HELPER,
     """        ProbabilityBarPalette.pair(
            awayHex: usableForText(awayHex),
            homeHex: usableForText(homeHex)
        )""",
     """        ProbabilityBarPalette.pair(
            awayHex: awayHex,
            homeHex: homeHex
        )""",
     "the funnel all three surfaces now share, hollowed out in one line"),

    # ── A KNOWN LIMIT, RUN RATHER THAN ASSUMED ──────────────────────────────
    # `barColors` is a private SwiftUI-view derivation of `barColorHexes`, and no
    # XCTest can call it. Arm 1 has the same exposure (see
    # `TeamTextContrastTests.testTheEventPageIsWiredThroughTheFloor`, which is a
    # source scan for exactly this reason). This mutant is here so the limit is
    # MEASURED each run instead of asserted in prose: if it survives, the hole is
    # real and named in the report; if a future change makes it killable, the run
    # will say so.
    ("10-sports-row-paints-both-segments-the-away-colour", ROW,
     "        return (Color(hex: hexes.away), Color(hex: hexes.home))",
     "        return (Color(hex: hexes.away), Color(hex: hexes.away))",
     "the hex pair is correct and the VIEW throws half of it away"),
]

# TRAP (banked by native/234, re-stated because it is the difference between a
# 4-minute run and one that reads as a hung rig): on a FAILING test run xcodebuild
# runs `simctl diagnose --timeout=600` — ~10 min per KILLED mutant, i.e. per
# mutant a working suite catches. `-collect-test-diagnostics never` is the fix.
XCB = ["xcodebuild", "test",
       "-project", str(ROOT / "Bain Luck.xcodeproj"),
       "-scheme", "Bain Luck",
       "-destination", f"platform=iOS Simulator,id={SIM}",
       "-collect-test-diagnostics", "never",
       "-only-testing:BainLuckTests/CardsResolveTeamColourThroughTheFloor7036Tests",
       "-only-testing:BainLuckTests/TeamTextContrastTests",
       "-only-testing:BainLuckTests/ProbabilityBarPaletteTests",
       "OTHER_SWIFT_FLAGS=$(inherited) -Xfrontend -disable-sandbox"]


def run_tests():
    r = subprocess.run(XCB, capture_output=True, text=True, cwd=str(ROOT))
    out = r.stdout + r.stderr
    return r.returncode, ("Executed" in out), out


# TRAP (also banked by native/234): `finally` does not survive SIGTERM. A killed
# run once left a one-word mutant in the worktree, where `git diff` reads it as
# deliberate. So restore is registered against the process dying, and the tree is
# CHECKED on the way out rather than assumed.
_IN_FLIGHT = {}


def _restore_all(*_):
    for path, original in list(_IN_FLIGHT.items()):
        try:
            path.write_text(original)
            print(f"  restored {path.name} on exit")
        except Exception as e:      # noqa: BLE001 — best effort on the way down
            print(f"  !! COULD NOT RESTORE {path}: {e}\n     git checkout it BY HAND before committing")
        _IN_FLIGHT.pop(path, None)


atexit.register(_restore_all)
for _sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
    signal.signal(_sig, lambda s, f: (_restore_all(), sys.exit(128 + s)))


def main():
    if "--list" in sys.argv:
        for n, f, *_ in MUTANTS:
            print(f"  {n}  ({f.name})")
        return 0

    print("baseline (unmutated tree)")
    code, _, _ = run_tests()
    if code != 0:
        print(f"  BASELINE IS RED (exit {code}) — fix that before reading any mutant")
        return 2
    print("  baseline GREEN\n")

    killed, survived = [], []
    for name, path, find, repl, why in MUTANTS:
        original = path.read_text()
        # A refused patch prints a green that is indistinguishable from an
        # unkillable mutant, so refusal is reported as a NON-result, never a pass.
        if find not in original:
            print(f"  REFUSED  {name} — anchor not found; the mutant patched NOTHING")
            survived.append((name, "REFUSED"))
            continue
        if original.count(find) != 1:
            print(f"  REFUSED  {name} — anchor occurs {original.count(find)}x, not unique")
            survived.append((name, "REFUSED-AMBIGUOUS"))
            continue
        try:
            _IN_FLIGHT[path] = original
            path.write_text(original.replace(find, repl, 1))
            code, compiled, _ = run_tests()
            if code != 0:
                how = "assertions" if compiled else "COMPILE ONLY"
                print(f"  killed   {name}  [{how}]")
                if not compiled:
                    print("           ^ a compile kill does not prove the suite would catch it")
                killed.append(name)
            else:
                print(f"  SURVIVED {name}\n           {why}")
                survived.append((name, "SURVIVED"))
        finally:
            path.write_text(original)
            _IN_FLIGHT.pop(path, None)

    print(f"\n{len(killed)}/{len(MUTANTS)} killed")
    for n, s in survived:
        print(f"  {s}: {n}")

    dirty = subprocess.run(["git", "-C", str(WORKTREE), "diff", "--stat", "--", "ios/"],
                           capture_output=True, text=True).stdout.strip()
    print("\ntree on exit (expect ONLY this arm's own edits):")
    print("  " + (dirty.replace("\n", "\n  ") if dirty else "(clean)"))
    return 0 if not survived else 1


if __name__ == "__main__":
    sys.exit(main())
