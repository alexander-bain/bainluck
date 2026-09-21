#!/usr/bin/env python3
"""native/276 — mutation run for #7036 arm 6 (the playoff-journey CAPSULE).

Arm 1 mutation-tested the floor's maths (`native-234-mutations-7036.py`), arm 2
the paired cards (`native-236`), arm 3 the single-colour text sites
(`native-238`), arm 4 the badge letters (`native-267`), arm 5 the chart marks
(`native-268`). None of those is re-run here.

What arm 6 adds that no earlier arm had a reason to carry:

  * AN INSTRUMENT mutant (10). This arm's central claim is a PIXEL claim — that
    a white capsule composites LIGHTER than the track it is drawn in — and the
    composite depends on a reading of the view: the fill is a sibling INSIDE the
    track's `ZStack`, so it lands on the track, not on the card. Compositing over
    the card instead is the plausible shortcut, it flatters white by ~2%, and if
    the suite cannot tell the two apart then the numbers are decoration. So the
    test's own arithmetic is mutated, not only the app's.

  * A COMMENT-STRIPPER mutant (11). Every needle this suite matches also appears
    in the docstrings that explain it, so a scan of the raw file can be satisfied
    by prose. That is a guard grading its own explanation, and it is the shape
    that let the capsule survive five arms.

  * AN UNNAMED-SEVENTH-SITE mutant (12). The blanket "every `Color(hex:` in this
    file names a resolver" assertion exists to catch a site nobody thought of.
    The only way to test that claim is to break a site this arm never touched —
    here arm 4's journey crest — with arm 4's own suite left OUT of the run, so
    the kill can only be this arm's blanket rule.

  * A DROP-vs-RECOLOUR pair (4, 5). The stripe answers ABSENCE; handing an
    unreadable club the grey default is a different bug from handing it its own
    white, and a suite that only checks "not white" cannot see it.

A mutant that SURVIVES is a hole in the guard suite, not a curiosity. A mutant
the battery cannot APPLY is reported REFUSED and never counted as a kill.

Runs only from this lane's own worktree; every path below is absolute.

Usage:  python3 tools/native-276-mutations-7036-journey-capsule.py [--list]
"""
import subprocess, sys, pathlib, signal, atexit

WORKTREE = pathlib.Path("/Users/bain/bainluck-dev/native")
ROOT = WORKTREE / "ios/Bain Luck"
MYSTUFF = ROOT / "Bain Luck/Views/MyStuffView.swift"
HELPER = ROOT / "Bain Luck/Utilities/TeamTextContrast+TextOnCard.swift"
FLOOR = ROOT / "Bain Luck/Utilities/TeamTextContrast.swift"
TESTS = ROOT / "BainLuckTests/JourneyCapsuleResolvesTeamColourThroughTheFloor7036Tests.swift"
SIM = "D2DA47A0-85F6-4BF8-AEFF-33146AE3EB05"

# 🪤 `TeamTextContrast.textHexOnCard(primaryColor, fallback: fallbackHex)` is now
# the body of THREE functions in this one file (`probabilityHex`, `logoTintHex`,
# `progressFillHex`). An anchor of the expression alone is ambiguous, is reported
# REFUSED, and reads exactly like an unkillable mutant — so the seam mutants
# carry their whole function.
FILL_WIRED = """    static func progressFillHex(_ primaryColor: String?) -> String {
        TeamTextContrast.textHexOnCard(primaryColor, fallback: fallbackHex)
    }"""
FILL_HOLLOW = """    static func progressFillHex(_ primaryColor: String?) -> String {
        primaryColor ?? fallbackHex
    }"""
FILL_PALE_DEFAULT = """    static func progressFillHex(_ primaryColor: String?) -> String {
        TeamTextContrast.textHexOnCard(primaryColor, fallback: "#f5f5f5")
    }"""

ACCENT_WIRED = """    static func edgeAccentHex(_ primaryColor: String?) -> String? {
        TeamTextContrast.usableForText(primaryColor)
    }"""
ACCENT_HOLLOW = """    static func edgeAccentHex(_ primaryColor: String?) -> String? {
        primaryColor
    }"""
ACCENT_RECOLOURS = """    static func edgeAccentHex(_ primaryColor: String?) -> String? {
        TeamTextContrast.usableForText(primaryColor) ?? fallbackHex
    }"""

STRIPPER_ON = """        try String(contentsOf: myStuffViewURL, encoding: .utf8)
            .split(separator: "\\n", omittingEmptySubsequences: false)
            .filter { !$0.trimmingCharacters(in: .whitespaces).hasPrefix("//") }
            .joined(separator: "\\n")"""
STRIPPER_OFF = """        try String(contentsOf: myStuffViewURL, encoding: .utf8)"""

# (name, file, find, replace, why-it-matters)
MUTANTS = [
    ("1-capsule-reverts-to-the-reported-defect", MYSTUFF,
     "                                          : Color(hex: MyStuffTeamTextColour.progressFillHex(journey.teamColor)).opacity(0.5))",
     "                                          : Color(hex: journey.teamColor ?? \"#6b7280\").opacity(0.5))",
     "THE REPORTED DEFECT, byte for byte — the issue's opening 'white capsule on "
     "a near-white track'. If this survives, the arm proves nothing"),

    ("2-stripe-reverts-to-the-raw-stored-colour", MYSTUFF,
     "            if let c = MyStuffTeamTextColour.edgeAccentHex(journey.teamColor) {",
     "            if let c = journey.teamColor {",
     "THE HALF-FIX. One of two sites in one card; every helper assertion stays "
     "green and the file still reads as wired"),

    ("3-fill-seam-hollowed-out", MYSTUFF, FILL_WIRED, FILL_HOLLOW,
     "the named seam kept and its contents removed — what a later refactor does "
     "when it trusts the name"),

    ("4-stripe-seam-hollowed-out", MYSTUFF, ACCENT_WIRED, ACCENT_HOLLOW,
     "the same on the stripe: `String?` in, `String?` out, no floor between"),

    ("5-stripe-recolours-instead-of-dropping", MYSTUFF, ACCENT_WIRED, ACCENT_RECOLOURS,
     "DROP vs RECOLOUR. Perfectly readable, and it invents an accent this card "
     "has never drawn for a club it cannot use the colour of. A suite that only "
     "asserts 'not white' cannot see it"),

    ("6-fill-falls-back-to-a-near-white", MYSTUFF, FILL_WIRED, FILL_PALE_DEFAULT,
     "THE FALLBACK MUTANT. Wiring perfect, every colour 'floored' — onto a shade "
     "that is invisible in exactly the way the fix exists to stop"),

    ("7-floor-removed-from-under-every-site", HELPER,
     "        usableForText(hex) ?? fallback",
     "        hex ?? fallback",
     "both sites unwired at once from a file neither mentions, while every call "
     "site still reads as correctly routed"),

    ("8-floor-applied-to-everyone", HELPER,
     "        usableForText(hex) ?? fallback",
     "        fallback",
     "OVER-APPLICATION: a legible club loses its colour too. A suite that only "
     "ever checks the WHITE case cannot tell this from a fix"),

    ("9-floor-lowered-under-the-three-served-clubs", FLOOR,
     "    static let minimumRatio = 3.0",
     "    static let minimumRatio = 1.5",
     "the three clubs `/api/shared/team-futures` served on 2026-09-20 sit at "
     "1.72-1.85:1, so a floor at 1.5 passes every one of them through while the "
     "white case still reads as fixed"),

    ("10-the-composite-is-taken-over-the-CARD-not-the-track", TESTS,
     "        Self.composite(Self.opaque(hex), extraAlpha: 0.5, over: trackComposite)",
     "        Self.composite(Self.opaque(hex), extraAlpha: 0.5, over: cardSurface)",
     "THE INSTRUMENT MUTANT. The fill is a sibling inside the track's ZStack; "
     "compositing it over the card is the plausible misreading and flatters white. "
     "If the pixel numbers cannot tell those apart they are decoration"),

    ("11-the-scan-reads-the-raw-file-again", TESTS, STRIPPER_ON, STRIPPER_OFF,
     "THE SELF-GRADING MUTANT. Every needle also appears in the docstring that "
     "explains it, so a raw-file scan can be satisfied by prose about the fix "
     "rather than by the fix"),

    ("12-an-unnamed-seventh-site-appears", MYSTUFF,
     "                    color: Color(hex: MyStuffTeamTextColour.logoTintHex(journey.teamColor)),",
     "                    color: Color(hex: journey.teamColor ?? \"#6b7280\"),",
     "THE BLANKET RULE'S OWN TEST: a site this arm never touched (arm 4's journey "
     "crest) goes raw, with arm 4's suite deliberately NOT in the run — so only "
     "the 'every Color(hex: names a resolver' assertion can catch it"),
]

# TRAP (banked by native/234): on a FAILING run xcodebuild calls
# `simctl diagnose --timeout=600` — ~10 min per KILLED mutant, i.e. per mutant a
# working suite catches. `-collect-test-diagnostics never` is the fix.
XCB = ["xcodebuild", "test",
       "-project", str(ROOT / "Bain Luck.xcodeproj"),
       "-scheme", "Bain Luck",
       "-destination", f"platform=iOS Simulator,id={SIM}",
       "-collect-test-diagnostics", "never",
       "-only-testing:BainLuckTests/JourneyCapsuleResolvesTeamColourThroughTheFloor7036Tests",
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
