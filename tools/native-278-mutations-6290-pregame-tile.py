#!/usr/bin/env python3
"""native/278 — mutation run for #6290 (a PRE-GAME tile drawing the live line).

The claim under test is small — "while the game is on, a tile captioned
`PRE-GAME` names the served opening or nothing" — and it is spent in SIX places:
three map tiles, one empty-chrome mirror, one live strip, and the page wiring
that carries the number at all. A rule this thin is exactly the kind whose guard
suite passes on a tree where the rule has been disconnected, so every site is
mutated separately rather than the helper alone.

What this battery adds that the helper's own unit tests cannot:

  * THE INERT-FIX MUTANTS (7, 8). The whole ship is a number arriving from a new
    payload field. Hand the view `nil`, or hand it `current_odds` under the
    opening's name, and every assertion about the rule still passes while the
    phone shows exactly what #6290 photographed. If these survive, the suite is
    grading a function nobody calls.

  * THE RENAME-AROUND MUTANT (10). `liveStrip` is SwiftUI and cannot be asserted
    without rasterising it, so its guard is a source scan — and a scan for a NAME
    is satisfied by a body that reads the right name and the wrong value
    (`pregameTotal ?? centerLine`). The scan asserts the absence of `centerLine`
    for this reason; the mutant is what proves that clause is load-bearing.

  * THE COMMENT-STRIPPER MUTANT (11). Every needle the scans match also appears
    in the prose explaining it — `"PRE-GAME"` appears in this file's own comments
    a dozen times. A scan of the raw source is a guard grading its own
    explanation (native/276 banked this one; it is re-run because this arm's
    scans are new).

A mutant that SURVIVES is a hole in the guard suite, not a curiosity. A mutant
the battery cannot APPLY is reported REFUSED and never counted as a kill.

Runs only from this lane's own worktree; every path below is absolute.

Usage:  python3 tools/native-278-mutations-6290-pregame-tile.py [--list]
"""
import subprocess, sys, pathlib, signal, atexit

WORKTREE = pathlib.Path("/Users/bain/bainluck-dev/native")
ROOT = WORKTREE / "ios/Bain Luck"
GUARD = WORKTREE / "tools/reserved-sim-guard.sh"
RAIL = ROOT / "Bain Luck/Utilities/MarketMapRail.swift"
MAPS = ROOT / "Bain Luck/Components/MarketMapView.swift"
SPECTRUM = ROOT / "Bain Luck/Components/TotalPointsSpectrumView.swift"
PAGE = ROOT / "Bain Luck/Views/EventDetailView.swift"
TESTS = ROOT / "BainLuckTests/ATileSaysPregameOnlyOverAPregameNumber6290Tests.swift"


def disposable_sim():
    """A device this run may install to, from the rig's shared picker.

    🪤 NOT A HARD-CODED UDID, AND NOT `name=iPhone 17`. Two simulators hold
    Alex's signed-in account and both carry that name, so a destination written
    by NAME resolves to one of them — measured this session: a hand-rolled
    `xcodebuild test -destination 'name=iPhone 17'` installed onto DD0DC456,
    Alex's device. `tools/reserved-sim-guard.sh` is the authority and asking it
    is the only spelling that stays correct when the list changes.
    """
    pick = subprocess.run(["bash", "-c", f'. "{GUARD}" && bl_default_shoot_sim'],
                          capture_output=True, text=True)
    udid = (pick.stdout or "").strip().splitlines()
    udid = udid[-1].strip() if udid else ""
    if not udid:
        sys.exit("FATAL: no disposable iPhone simulator on this machine")
    check = subprocess.run(["bash", "-c", f'. "{GUARD}" && bl_is_reserved_sim "{udid}"'])
    if check.returncode == 0:
        sys.exit(f"FATAL: the picker returned RESERVED device {udid} — refusing to install")
    return udid


SIM = disposable_sim()

RULE_WIRED = """    static func pregameLine(isLive: Bool, opening: Double?, current: Double?) -> Double? {
        isLive ? opening : current
    }"""
RULE_DEFECT = """    static func pregameLine(isLive: Bool, opening: Double?, current: Double?) -> Double? {
        current
    }"""
RULE_HELPFUL = """    static func pregameLine(isLive: Bool, opening: Double?, current: Double?) -> Double? {
        isLive ? (opening ?? current) : current
    }"""
RULE_EAGER = """    static func pregameLine(isLive: Bool, opening: Double?, current: Double?) -> Double? {
        isLive ? opening : (opening ?? current)
    }"""

FULL_TILE_WIRED = """        if MarketMapRail.drawsPregameMarker(canStillBeGraded: canStillBeGraded),
           let ou = MarketMapRail.pregameLine(
               isLive: isLive,
               opening: fullGameOpeningTotal(mapUnit),
               current: ouLine
           ) {"""
FULL_TILE_UNWIRED = """        if MarketMapRail.drawsPregameMarker(canStillBeGraded: canStillBeGraded),
           let ou = ouLine {"""

HALF_TOTAL_WIRED = """        if MarketMapRail.drawsPregameMarker(canStillBeGraded: canStillBeGraded),
           let ou = MarketMapRail.pregameLine(
               isLive: isLive,
               opening: nil,
               current: thresholds.first(where: { abs($0.overProb - 0.5) < 0.1 })?.threshold
           ) {"""
HALF_TOTAL_UNWIRED = """        if MarketMapRail.drawsPregameMarker(canStillBeGraded: canStillBeGraded),
           let ou = thresholds.first(where: { abs($0.overProb - 0.5) < 0.1 })?.threshold {"""

HALF_MARGIN_WIRED = """        if MarketMapRail.drawsPregameMarker(canStillBeGraded: canStillBeGraded),
           let pv = MarketMapRail.pregameLine(isLive: isLive, opening: nil, current: projValue) {"""
HALF_MARGIN_UNWIRED = """        if MarketMapRail.drawsPregameMarker(canStillBeGraded: canStillBeGraded), let pv = projValue {"""

MIRROR_WIRED = """            lineMarker: MarketMapRail.pregameLine(
                isLive: isLive,
                opening: fullGameOpeningTotal(mapUnit),
                current: sportUnitLineApplies(mapUnit) ? overUnder : nil
            ),"""
MIRROR_UNWIRED = """            lineMarker: sportUnitLineApplies(mapUnit) ? overUnder : nil,"""

STRIP_WIRED = """            if let pregame = pregameTotal {"""
STRIP_RENAME_AROUND = """            if let pregame = pregameTotal ?? centerLine {"""

STRIPPER_ON = """        return try String(contentsOf: url, encoding: .utf8)
            .split(separator: "\\n", omittingEmptySubsequences: false)
            .filter { !$0.trimmingCharacters(in: .whitespaces).hasPrefix("//") }
            .joined(separator: "\\n")"""
STRIPPER_OFF = """        return try String(contentsOf: url, encoding: .utf8)"""

# (name, file, find, replace, why-it-matters)
MUTANTS = [
    ("1-the-tile-reverts-to-the-line-right-now", RAIL, RULE_WIRED, RULE_DEFECT,
     "THE REPORTED DEFECT, byte for byte — the tile draws current_odds again. "
     "If this survives, the arm proves nothing"),

    ("2-live-falls-back-to-the-live-line", RAIL, RULE_WIRED, RULE_HELPFUL,
     "THE HELPFUL SHORTCUT, and the likeliest future edit: 'draw something rather "
     "than nothing'. It is #6290 exactly, on every event whose opening columns "
     "are unpopulated and on all four half cards"),

    ("3-a-scheduled-card-is-re-pointed-at-the-opening", RAIL, RULE_WIRED, RULE_EAGER,
     "OVER-APPLICATION. Before the off the current line IS the pre-game line and "
     "is fresher; a suite that only ever checks the live case cannot tell this "
     "from the fix"),

    ("4-the-full-totals-tile-is-unwired", MAPS, FULL_TILE_WIRED, FULL_TILE_UNWIRED,
     "THE PHOTOGRAPHED SITE, back to master's behaviour while the helper and all "
     "of its unit tests stay green. Only the blanket count can see this"),

    ("5-the-half-totals-tile-is-unwired", MAPS, HALF_TOTAL_WIRED, HALF_TOTAL_UNWIRED,
     "the site in n278-before-2150.png reading PRE-GAME 31.5 mid-game"),

    ("6-the-half-margin-tile-is-unwired", MAPS, HALF_MARGIN_WIRED, HALF_MARGIN_UNWIRED,
     "the third tile — the one NOT in the photograph, which is why the rule is "
     "counted across the file instead of pinned to the two that were"),

    ("7-the-page-hands-the-card-nothing", PAGE,
     "                            openingOverUnder: event.openingOdds?.overUnder,\n"
     "                            homeScore: event.homeScore,\n"
     "                            awayScore: event.awayScore,\n"
     "                            absenceStatedAbove: absenceStatedAbove",
     "                            openingOverUnder: nil,\n"
     "                            homeScore: event.homeScore,\n"
     "                            awayScore: event.awayScore,\n"
     "                            absenceStatedAbove: absenceStatedAbove",
     "THE INERT FIX. Every rule still right, every test still green, and the map "
     "silently takes the `opening: nil` arm for ever — the tile just disappears "
     "instead of lying, which reads as a deliberate withholding"),

    ("8-the-page-hands-the-card-the-live-line", PAGE,
     "                            // #6290 — as on the maps above.\n"
     "                            openingOverUnder: event.openingOdds?.overUnder,",
     "                            // #6290 — as on the maps above.\n"
     "                            openingOverUnder: event.currentOdds?.overUnder,",
     "THE WORST INERT FIX: the defect restored through the new parameter, on the "
     "card whose strip prints a SENTENCE about the number"),

    ("9-the-decoded-field-is-dropped", MAPS,
     "    var openingOverUnder: Double? = nil",
     "    var openingOverUnder: Double? = nil\n    private var openingOverUnderIgnored: Double? { openingOverUnder }",
     "a no-op edit that must NOT be reported as a kill — the battery's own "
     "control. A run that 'kills' this is failing for a reason unrelated to the "
     "mutant"),

    ("10-the-strip-reads-the-right-name-and-the-wrong-value", SPECTRUM,
     STRIP_WIRED, STRIP_RENAME_AROUND,
     "THE RENAME-AROUND. `liveStrip`'s guard is a source scan, and a scan for the "
     "NAME `pregameTotal` passes here while the bar draws centerLine again. The "
     "scan's `centerLine` clause is what must catch it"),

    ("11-the-scan-reads-the-raw-file-again", TESTS, STRIPPER_ON, STRIPPER_OFF,
     "THE SELF-GRADING MUTANT. `\"PRE-GAME\"` appears a dozen times in the comments "
     "that explain the tiles, so a raw-file scan counts prose as sites"),
]

# TRAP (banked by native/234): on a FAILING run xcodebuild calls
# `simctl diagnose --timeout=600` — ~10 min per KILLED mutant.
# `-collect-test-diagnostics never` is the fix.
XCB = ["xcodebuild", "test",
       "-project", str(ROOT / "Bain Luck.xcodeproj"),
       "-scheme", "Bain Luck",
       "-destination", f"platform=iOS Simulator,id={SIM}",
       "-collect-test-diagnostics", "never",
       "-disableAutomaticPackageResolution",
       "-only-testing:BainLuckTests/ATileSaysPregameOnlyOverAPregameNumber6290Tests",
       "-only-testing:BainLuckTests/MarketMapRailTests",
       "-only-testing:BainLuckTests/TotalPointsSpectrumRungCaptionTests",
       "OTHER_SWIFT_FLAGS=$(inherited) -Xfrontend -disable-sandbox"]


def run_tests():
    r = subprocess.run(XCB, capture_output=True, text=True, cwd=str(ROOT))
    out = r.stdout + r.stderr
    return r.returncode, ("Executed" in out), out


# TRAP (also banked by native/234): `finally` does not survive SIGTERM.
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

    print(f"simulator {SIM} (disposable, via reserved-sim-guard)")
    print("baseline (unmutated tree)")
    code, _, _ = run_tests()
    if code != 0:
        print(f"  BASELINE IS RED (exit {code}) — fix that before reading any mutant")
        return 2
    print("  baseline GREEN\n")

    killed, survived = [], []
    for name, path, find, repl, why in MUTANTS:
        original = path.read_text()
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
    print("\n  (mutant 9 is the battery's CONTROL: it must SURVIVE. Any other survivor is a hole.)")

    dirty = subprocess.run(["git", "-C", str(WORKTREE), "diff", "--stat", "--", "ios/"],
                           capture_output=True, text=True).stdout.strip()
    print("\ntree on exit (expect ONLY this ship's own edits):")
    print("  " + (dirty.replace("\n", "\n  ") if dirty else "(clean)"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
