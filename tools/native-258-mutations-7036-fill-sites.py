#!/usr/bin/env python3
"""native/258 — mutation run for #7036 arm 4 (the SHAPE sites).

Arm 1 mutation-tested the floor's maths (`native-234-mutations-7036.py`), arm 2
the two paired CARDS (`native-236-…`), arm 3 the single-colour TEXT sites
(`native-238-…`). None is re-run here.

What arm 4 adds that the earlier arms had no reason to carry:

  * A PAIR-COLLAPSE mutant (3). This arm's guess-card tiles are drawn side by
    side, and Fulham and Lyon are both `#ffffff`. A floor applied per side hands
    back the same default twice and the matchup becomes two identical squares —
    legible, and a different lie. Arms 1-3 had no surface drawing two floored
    fills at once, so nothing before this could have caught it.
  * FOUND-BY-GUARD mutants (6, 7). Two of My Stuff's four sites key on
    `journey.teamColor`, not `primaryColor`. Arm 3 named one My Stuff site; the
    blanket source assertion found these two. They are part of why the count
    assertion is 6 and not 2, so a mutant that removes one must die.
  * A FALLBACK mutant (9), inherited in spirit from arm 3 and still the one worth
    the run: every "is it readable" assertion keeps passing when the default
    itself is invisible, because the floored branch happily returns a second
    unreadable colour. The fix looks wired and the reader still sees nothing.

A mutant that SURVIVES is a hole in the guard suite, not a curiosity.

Runs only from this lane's own worktree; every path below is absolute
(native/236 left a script in the shared checkout and blocked the desk's
fast-forward).

  * A FOLD mutant (11). Mutant 9's anchor matched TWICE on the first run, which
    is how the duplicate `MyStuffTeamTextColour` was found: two byte-identical
    fallbacks in one file, both suites green. The helpers are now one, so 9
    scores — and 11 covers the two probability rows the fold moved onto the new
    spelling, which arm 3's battery no longer recognises.

Usage:  python3 tools/native-258-mutations-7036-fill-sites.py [--list] [--only 9,11]
"""
import subprocess, sys, pathlib, signal, atexit

WORKTREE = pathlib.Path("/Users/bain/bainluck-dev/native")
ROOT = WORKTREE / "ios/Bain Luck"
DISCOVER = ROOT / "Bain Luck/Views/DiscoverView.swift"
MYSTUFF = ROOT / "Bain Luck/Views/MyStuffView.swift"
SIM = "D2DA47A0-85F6-4BF8-AEFF-33146AE3EB05"
SUITE = "BainLuckTests/FillSitesResolveTeamColourThroughTheFloor7036Tests"

# 🪤 Anchors carry enough surrounding lines to be UNIQUE. An anchor that matches
# twice patches nothing (count != 1) and is reported REFUSED, which reads as
# "unkillable" when it is really "badly written" — arm 3 lost a cycle to this.

TILES_WIRED = """        let tiles = GuessCardTeamTileColours.pair(event)
        let homeColor = tiles.home
        let awayColor = tiles.away"""
TILES_RAW = """        let homeColor = Color(hex: event.homeTeamData?.primaryColor ?? "#2563eb")
        let awayColor = Color(hex: event.awayTeamData?.primaryColor ?? "#64748b")"""

HEXES_WIRED = """        TeamTextContrast.cardColorHexes(
            awayHex: event.awayTeamData?.primaryColor,
            homeHex: event.homeTeamData?.primaryColor
        )"""
HEXES_NO_FLOOR = """        ProbabilityBarPalette.pair(
            awayHex: event.awayTeamData?.primaryColor,
            homeHex: event.homeTeamData?.primaryColor
        )"""
HEXES_SWAPPED = """        TeamTextContrast.cardColorHexes(
            awayHex: event.homeTeamData?.primaryColor,
            homeHex: event.awayTeamData?.primaryColor
        )"""
# Per-side flooring with no pair re-derivation: the collapse mutant.
HEXES_PER_SIDE = """        (away: TeamTextContrast.textHexOnCard(event.awayTeamData?.primaryColor, fallback: ProbabilityBarPalette.awayDefault),
         home: TeamTextContrast.textHexOnCard(event.homeTeamData?.primaryColor, fallback: ProbabilityBarPalette.awayDefault))"""

LOGO_WIRED = "                    color: MyStuffTeamColour.color(journey.teamColor),"
LOGO_RAW = '                    color: Color(hex: journey.teamColor ?? "#6b7280"),'

MERGED_WIRED = "                color: MyStuffTeamColour.color(item.matchedTeam?.primaryColor),"
MERGED_RAW = '                color: Color(hex: item.matchedTeam?.primaryColor ?? "#6b7280"),'

CAPSULE_WIRED = "                                          : MyStuffTeamColour.color(journey.teamColor).opacity(0.5))"
CAPSULE_RAW = '                                          : Color(hex: journey.teamColor ?? "#6b7280").opacity(0.5))'

STRIPE_WIRED = "                    .fill(MyStuffTeamColour.color(c))"
STRIPE_RAW = "                    .fill(Color(hex: c))"

# 🪤 THIS ANCHOR IS WHY THE FOLD HAPPENED. On the first run it matched TWICE —
# arm 3's `MyStuffTeamTextColour` and arm 4's draft enum each carried a
# byte-identical `fallbackHex`, 400 lines apart in one file — so mutant 9 was
# REFUSED rather than scored, and a refusal reads exactly like an unkillable
# mutant if you stop at the count. Following it found two constants that must
# never disagree with nothing to make them disagree loudly. They are now one
# helper, so the anchor is unique and mutant 9 scores.
FALLBACK_WIRED = '    static let fallbackHex = "#6b7280"'
FALLBACK_INVISIBLE = '    static let fallbackHex = "#fffffe"'

# The two probability rows the fold brought onto this helper (arm 3's sites, arm
# 3's battery — under a spelling that battery no longer knows). Both branches are
# byte-identical, so the anchor carries the branch keyword above it.
PROB_ROW_WIRED = """            if isMultiSource {
                Text(displayProb.map { formatProbability($0) } ?? "—")
                    .font(.subheadline)
                    .fontWeight(.semibold)
                    .monospacedDigit()
                    .foregroundStyle(MyStuffTeamColour.color(item.matchedTeam?.primaryColor))"""
PROB_ROW_RAW = """            if isMultiSource {
                Text(displayProb.map { formatProbability($0) } ?? "—")
                    .font(.subheadline)
                    .fontWeight(.semibold)
                    .monospacedDigit()
                    .foregroundStyle(Color(hex: item.matchedTeam?.primaryColor ?? "#6b7280"))"""

FLOOR_WIRED = """    static func hex(_ stored: String?) -> String {
        TeamTextContrast.textHexOnCard(stored, fallback: fallbackHex)
    }"""
FLOOR_BYPASSED = """    static func hex(_ stored: String?) -> String {
        stored ?? fallbackHex
    }"""

MUTANTS = [
    (1, DISCOVER, TILES_WIRED, TILES_RAW,
     "the guess card's tiles go back to the raw primary_color (the reported defect verbatim)"),
    (2, DISCOVER, HEXES_WIRED, HEXES_NO_FLOOR,
     "the tile helper keeps the pair but drops the FLOOR"),
    (3, DISCOVER, HEXES_WIRED, HEXES_PER_SIDE,
     "the floor is applied PER SIDE, so two white-shirted clubs collapse onto one colour"),
    (4, DISCOVER, HEXES_WIRED, HEXES_SWAPPED,
     "the tile helper swaps away for home"),
    (5, MYSTUFF, LOGO_WIRED, LOGO_RAW,
     "the journey row's logo goes back to the raw team colour"),
    (6, MYSTUFF, CAPSULE_WIRED, CAPSULE_RAW,
     "the probability capsule goes back to raw (the 'white capsule on a near-white track')"),
    (7, MYSTUFF, STRIPE_WIRED, STRIPE_RAW,
     "the 3pt leading stripe goes back to raw"),
    (8, MYSTUFF, MERGED_WIRED, MERGED_RAW,
     "the merged row's logo goes back to the raw team colour"),
    (9, MYSTUFF, FALLBACK_WIRED, FALLBACK_INVISIBLE,
     "the fallback itself moves under the floor — the fix looks wired, the reader still sees nothing"),
    (10, MYSTUFF, FLOOR_WIRED, FLOOR_BYPASSED,
     "the helper keeps its name and shape but stops flooring"),
    (11, MYSTUFF, PROB_ROW_WIRED, PROB_ROW_RAW,
     "a folded probability row goes back to raw (arm 3's site, this arm's spelling)"),
]

ORIGINALS = {}


def restore():
    for path, text in ORIGINALS.items():
        pathlib.Path(path).write_text(text, encoding="utf-8")


atexit.register(restore)
signal.signal(signal.SIGINT, lambda *_: sys.exit(130))
signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))


def run_suite():
    """Returns True when the suite is GREEN (the mutant SURVIVED)."""
    r = subprocess.run(
        ["xcodebuild", "test",
         "-project", str(ROOT / "Bain Luck.xcodeproj"),
         "-scheme", "Bain Luck",
         "-destination", f"platform=iOS Simulator,id={SIM}",
         "-only-testing:" + SUITE,
         "-disableAutomaticPackageResolution",
         "OTHER_SWIFT_FLAGS=$(inherited) -Xfrontend -disable-sandbox"],
        cwd=str(WORKTREE), capture_output=True, text=True)
    out = r.stdout + r.stderr
    # A COMPILE failure is not a kill by assertion. Say which it was: a mutant
    # that cannot build proves nothing about the guards (arm 2's lesson).
    if "** TEST SUCCEEDED **" in out:
        return "SURVIVED"
    if "error:" in out and "Executed" not in out:
        return "COMPILE-FAILED"
    return "KILLED"


def main():
    if "--list" in sys.argv:
        for n, path, _, _, why in MUTANTS:
            print(f"{n:2d}  {pathlib.Path(path).name:20s}  {why}")
        return 0

    # `--only 9,11` re-scores named mutants without paying the whole battery
    # again (~4.5 min each). A partial run prints its own scope so a report can
    # never quote it as the full one.
    only = None
    if "--only" in sys.argv:
        only = {int(n) for n in sys.argv[sys.argv.index("--only") + 1].split(",")}
        print(f"PARTIAL RUN — mutants {sorted(only)} only")
    mutants = [m for m in MUTANTS if only is None or m[0] in only]

    for path in {m[1] for m in mutants}:
        ORIGINALS[str(path)] = pathlib.Path(path).read_text(encoding="utf-8")

    # A CONTROL run first: if the unmutated tree is not green, every "KILLED"
    # below is a lie about a suite that was already red.
    print("control (unmutated tree) ... ", end="", flush=True)
    control = run_suite()
    print(control)
    if control != "SURVIVED":
        print("CONTROL IS NOT GREEN — the run proves nothing. Stopping.")
        return 2

    results = []
    for n, path, wired, mutated, why in mutants:
        original = ORIGINALS[str(path)]
        if original.count(wired) != 1:
            print(f"{n:2d}  REFUSED (anchor matched {original.count(wired)}×, not 1) — {why}")
            results.append((n, "REFUSED", why))
            continue
        pathlib.Path(path).write_text(original.replace(wired, mutated), encoding="utf-8")
        print(f"{n:2d}  running ... ", end="", flush=True)
        verdict = run_suite()
        print(f"{verdict:14s} — {why}")
        results.append((n, verdict, why))
        pathlib.Path(path).write_text(original, encoding="utf-8")

    restore()
    killed = sum(1 for _, v, _ in results if v == "KILLED")
    survived = [r for r in results if r[1] != "KILLED"]
    print(f"\n{killed}/{len(mutants)} killed, control green"
          + (" (PARTIAL RUN)" if only is not None else ""))
    for n, v, why in survived:
        print(f"  HOLE  mutant {n} {v}: {why}")
    return 1 if survived else 0


if __name__ == "__main__":
    sys.exit(main())
