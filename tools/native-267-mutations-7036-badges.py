#!/usr/bin/env python3
"""native/267 — mutation run for #7036 arm 4 (the BADGE LETTER sites).

Arm 1 mutation-tested the floor's maths (`native-234-mutations-7036.py`); arm 2
the wiring of the two paired cards (`native-236`); arm 3 the single-colour text
sites (`native-238`). None of those is re-run here.

What arm 4 adds that the earlier arms had no reason to carry:

  * A HALF-FIX family (mutants 3, 4). `MyStuffView` has TWO crest circles — the
    playoff-journey header and the merged-future row — wired through the same
    helper. Fixing one and leaving the other compiles, renders, and leaves every
    helper assertion green. Only the COUNT assertion in the wiring test sees it,
    which is why that test counts instead of using `contains`.

  * A PINNED-DEFAULT mutant (6). The ladder's default is `#059669` at 3.77:1 —
    the tightest of the three against a 3.0 floor. Swapping it for another
    perfectly legible colour keeps every "is it readable" assertion green and
    silently repaints a surface. Only the pinned ratio catches it.

  * A CONTRACT mutant (11). `TeamLogoView` cannot enforce in its type that its
    `color:` is drawn as TEXT — `OnboardingView` legitimately passes `.blue`. The
    contract therefore lives in a docstring, and a docstring that can be deleted
    without a test failing is not a contract. This deletes it.

A mutant that SURVIVES is a hole in the guard suite, not a curiosity.

Runs only from this lane's own worktree; every path below is absolute
(native/236 left a script in the shared checkout and blocked the desk's
fast-forward).

Usage:  python3 tools/native-267-mutations-7036-badges.py [--list]
"""
import subprocess, sys, pathlib, signal, atexit

WORKTREE = pathlib.Path("/Users/bain/bainluck-dev/native")
ROOT = WORKTREE / "ios/Bain Luck"
HELPER = ROOT / "Bain Luck/Utilities/TeamTextContrast+TextOnCard.swift"
LADDER = ROOT / "Bain Luck/Components/LadderCardView.swift"
LOGOVIEW = ROOT / "Bain Luck/Components/TeamLogoView.swift"
TEAMPAGE = ROOT / "Bain Luck/Views/TeamDetailView.swift"
MYSTUFF = ROOT / "Bain Luck/Views/MyStuffView.swift"
SIM = "D2DA47A0-85F6-4BF8-AEFF-33146AE3EB05"

# 🪤 `TeamTextContrast.textHexOnCard(primaryColor, fallback: fallbackHex)` now
# appears TWICE in MyStuffView — `probabilityHex` (arm 3) and `logoTintHex`
# (this arm) are the same one-line rule. An anchor of just that expression is
# ambiguous, is reported REFUSED, and would read as "unkillable". So the seam
# mutants below carry their whole function.
LOGOTINT_WIRED = """    static func logoTintHex(_ primaryColor: String?) -> String {
        TeamTextContrast.textHexOnCard(primaryColor, fallback: fallbackHex)
    }"""
LOGOTINT_HOLLOW = """    static func logoTintHex(_ primaryColor: String?) -> String {
        primaryColor ?? fallbackHex
    }"""

BADGEHEX_WIRED = """    static func badgeHex(_ storedHex: String?) -> String {
        TeamTextContrast.textHexOnCard(storedHex, fallback: fallbackHex)
    }"""
BADGEHEX_HOLLOW = """    static func badgeHex(_ storedHex: String?) -> String {
        storedHex ?? fallbackHex
    }"""

TILEHEX_WIRED = """    static func logoTileHex(_ storedHex: String?) -> String {
        TeamTextContrast.textHexOnCard(storedHex, fallback: fallbackHex)
    }"""
TILEHEX_HOLLOW = """    static func logoTileHex(_ storedHex: String?) -> String {
        storedHex ?? fallbackHex
    }"""

# (name, file, find, replace, why-it-matters)
MUTANTS = [
    ("1-ladder-badge-reverts-to-raw-primaryColor", LADDER,
     "            teamColor: Color(hex: LadderCardTeamColour.badgeHex(team.primaryColor)),",
     "            teamColor: team.primaryColor.map { Color(hex: $0) } ?? DS.emeraldDark,",
     "THE REPORTED DEFECT on the league screen's ranked ladder: a white-shirted "
     "club's 24pt badge is blank in both branches at once"),

    ("2-team-page-tile-reverts-to-raw-primaryColor", TEAMPAGE,
     "                                .fill(Color(hex: TeamDetailTeamColour.logoTileHex(team.primaryColor)))",
     "                                .fill(Color(hex: team.primaryColor ?? \"#6B7280\"))",
     "THE REPORTED DEFECT in its white-text-on-fill direction: the team page's own "
     "64pt identity tile renders as an empty square"),

    ("3-mystuff-merged-row-crest-reverts-to-raw", MYSTUFF,
     "                color: Color(hex: MyStuffTeamTextColour.logoTintHex(item.matchedTeam?.primaryColor)),",
     "                color: Color(hex: item.matchedTeam?.primaryColor ?? \"#6b7280\"),",
     "the crest circle beside a probability that arm 3 already floored — the row "
     "would print a legible number next to an invisible badge"),

    ("4-mystuff-journey-crest-reverts-to-raw", MYSTUFF,
     "                    color: Color(hex: MyStuffTeamTextColour.logoTintHex(journey.teamColor)),",
     "                    color: Color(hex: journey.teamColor ?? \"#6b7280\"),",
     "THE HALF-FIX. One of two crest circles in one file. Every helper assertion "
     "stays green; only the COUNT in the wiring test can see one site left behind"),

    ("5-ladder-fallback-goes-under-the-floor", LADDER,
     '    static let fallbackHex = "#059669"',
     '    static let fallbackHex = "#f8fafc"',
     "THE FALLBACK MUTANT. Wiring perfect, every colour 'floored' — onto a "
     "near-white that reads as a real colour in a diff"),

    ("6-ladder-fallback-swapped-for-another-LEGIBLE-colour", LADDER,
     '    static let fallbackHex = "#059669"',
     '    static let fallbackHex = "#2563EB"',
     "THE PINNED-DEFAULT MUTANT. 5.17:1, entirely readable, and a silent repaint "
     "of every crest-less club on the league screen. Only the pinned 3.77 sees it"),

    ("7-team-page-fallback-goes-under-the-floor", TEAMPAGE,
     '    static let fallbackHex = "#6B7280"',
     '    static let fallbackHex = "#fafafa"',
     "the same on the team page, where the fill is what white letters sit ON"),

    ("8-ladder-seam-hollowed-out", LADDER,
     BADGEHEX_WIRED, BADGEHEX_HOLLOW,
     "the named seam kept and its contents removed — what a later refactor does "
     "when it trusts the name"),

    ("9-team-page-seam-hollowed-out", TEAMPAGE,
     TILEHEX_WIRED, TILEHEX_HOLLOW,
     "the same on the team page"),

    ("10-mystuff-logo-seam-hollowed-out", MYSTUFF,
     LOGOTINT_WIRED, LOGOTINT_HOLLOW,
     "the same on both My Stuff crests at once, with `probabilityHex` beside it "
     "still correct — so the file looks wired"),

    ("11-logo-view-contract-deleted", LOGOVIEW,
     "    /// **This is drawn as TEXT, not only as a tint — #7036, fourth arm.**",
     "    /// The tint colour.",
     "THE CONTRACT MUTANT. `TeamLogoView` cannot enforce this in its type, so the "
     "docstring IS the contract. If it can be deleted with the suite green, the "
     "next caller reads `color:` as a tint and hands it a raw primary_color"),

    ("12-floor-removed-from-under-every-site", HELPER,
     "        usableForText(hex) ?? fallback",
     "        hex ?? fallback",
     "all four sites unwired at once, from a file none of them mentions, while "
     "every call site still reads as correctly routed"),

    ("13-floor-applied-to-everyone", HELPER,
     "        usableForText(hex) ?? fallback",
     "        fallback",
     "over-application: Liverpool loses its red too. A suite that only ever checks "
     "the WHITE case cannot tell this from a fix"),
]

# TRAP (banked by native/234): on a FAILING test run xcodebuild runs
# `simctl diagnose --timeout=600` — ~10 min per KILLED mutant, i.e. per mutant a
# working suite catches. `-collect-test-diagnostics never` is the fix.
XCB = ["xcodebuild", "test",
       "-project", str(ROOT / "Bain Luck.xcodeproj"),
       "-scheme", "Bain Luck",
       "-destination", f"platform=iOS Simulator,id={SIM}",
       "-collect-test-diagnostics", "never",
       "-only-testing:BainLuckTests/BadgeLettersResolveTeamColourThroughTheFloor7036Tests",
       "-only-testing:BainLuckTests/TextSitesResolveTeamColourThroughTheFloor7036Tests",
       "-only-testing:BainLuckTests/TeamTextContrastTests",
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
