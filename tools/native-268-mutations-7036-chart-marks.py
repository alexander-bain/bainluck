#!/usr/bin/env python3
"""native/268 — mutation run for #7036 arm 5 (the Evolution chart's MARKS).

Arm 1 mutation-tested the floor's maths (`native-234-mutations-7036.py`); arm 2
the wiring of the two paired cards (`native-236`); arm 3 the single-colour text
sites (`native-238`); arm 4 the badge-letter sites (`native-267`). None of those
is re-run here.

What arm 5 adds that the earlier arms had no reason to carry:

  * An INDEXED-FALLBACK family (mutants 5, 6). Every earlier arm fell onto ONE
    hardcoded default per site, so "did it land on the default" was the whole
    question. This one falls onto `paletteHexes[index % count]` — a different
    colour per display position — because a chart whose floored lines all
    collapse onto one colour is unreadable in a second, newer way. Mutant 5
    pins every floored outcome to slot 0; mutant 6 stops the palette wrapping.
    Both keep every legibility assertion green.

  * A LOOKUP mutant (4). The colour is found by NAME in the payload the chart is
    holding. A lookup that ignores the name and takes the first outcome paints
    the whole board in the leader's colour — legible, wrong, and invisible to
    any assertion that only asks "is this readable".

  * A HALF-FIX mutant (7). Three sites draw this colour. Wiring the series scale
    and letting the leaderboard bypass it compiles and renders. Only the COUNT
    in the wiring test sees it, which is why that test counts.

  * A PINNED-PALETTE mutant (8). Since this arm the palette is what a FLOORED
    outcome falls onto, so editing it repaints clubs that DO store a colour.
    Swapping the leader's crimson for another perfectly legible hue keeps every
    ratio assertion green. Only the pin catches it.

A mutant that SURVIVES is a hole in the guard suite, not a curiosity.

Runs only from this lane's own worktree; every path below is absolute
(native/236 left a script in the shared checkout and blocked the desk's
fast-forward).

Usage:  python3 tools/native-268-mutations-7036-chart-marks.py [--list]
"""
import subprocess, sys, pathlib, signal, atexit

WORKTREE = pathlib.Path("/Users/bain/bainluck-dev/native")
ROOT = WORKTREE / "ios/Bain Luck"
CHART = ROOT / "Bain Luck/Components/EvolutionChartView.swift"
HELPER = ROOT / "Bain Luck/Utilities/TeamTextContrast+TextOnCard.swift"
SIM = "D2DA47A0-85F6-4BF8-AEFF-33146AE3EB05"

# The chart's resolver, whole, because the fragment `EvolutionOutcomeColour.markHex(`
# appears in both overloads and an ambiguous anchor is reported REFUSED — which
# reads as "unkillable" rather than as "the harness could not aim".
RESOLVER_WIRED = """    private func colorForOutcome(name: String, index: Int) -> Color {
        Color(hex: EvolutionOutcomeColour.markHex(
            name: name, outcomes: data?.outcomes, index: index))
    }"""
RESOLVER_PRE_7036 = """    private func colorForOutcome(name: String, index: Int) -> Color {
        if let meta = data?.outcomes.first(where: { $0.name == name }),
           let hex = meta.primaryColor {
            return Color(hex: hex)
        }
        return Color(hex: EvolutionOutcomeColour.fallbackHex(index: index))
    }"""

SEAM_WIRED = """    static func markHex(_ storedHex: String?, index: Int) -> String {
        TeamTextContrast.textHexOnCard(storedHex, fallback: fallbackHex(index: index))
    }"""
SEAM_HOLLOW = """    static func markHex(_ storedHex: String?, index: Int) -> String {
        storedHex ?? fallbackHex(index: index)
    }"""

LOOKUP_WIRED = """        markHex(outcomes?.first(where: { $0.name == name })?.primaryColor, index: index)"""
LOOKUP_BY_POSITION = """        markHex(outcomes?.first?.primaryColor, index: index)"""

# (name, file, find, replace, why-it-matters)
MUTANTS = [
    ("1-chart-resolver-reverts-to-raw-primaryColor", CHART,
     RESOLVER_WIRED, RESOLVER_PRE_7036,
     "THE REPORTED DEFECT, exactly as it shipped: on NFC South Division Winner "
     "two of four lines, both legend dots and both crest badges go invisible"),

    ("2-floor-removed-at-the-seam", CHART,
     SEAM_WIRED, SEAM_HOLLOW,
     "the named seam kept and its contents removed — what a later refactor does "
     "when it trusts the name"),

    ("3-floor-removed-from-the-shared-helper", HELPER,
     "        usableForText(hex) ?? fallback",
     "        hex ?? fallback",
     "arms 3, 4 AND 5 unwired at once, from a file none of their call sites "
     "mentions, while every call site still reads as correctly routed"),

    ("4-colour-looked-up-by-position-not-by-name", CHART,
     LOOKUP_WIRED, LOOKUP_BY_POSITION,
     "THE LOOKUP MUTANT. Every line on the board is painted in the leader's "
     "colour: perfectly legible, perfectly wrong, and invisible to any assertion "
     "that only asks whether a mark can be seen"),

    ("5-every-floored-outcome-collapses-onto-slot-zero", CHART,
     "        paletteHexes[index % paletteHexes.count]",
     "        paletteHexes[0]",
     "THE INDEXED-FALLBACK MUTANT. Three white-shirted clubs on one board all "
     "become the same crimson line. Every legibility assertion stays green — the "
     "chart is readable and says nothing true"),

    ("6-palette-stops-wrapping-past-its-tenth-slot", CHART,
     "        paletteHexes[index % paletteHexes.count]",
     "        paletteHexes[min(index, paletteHexes.count - 1)]",
     "the chart serves up to 50 outcomes; this pins everything past the tenth to "
     "one colour instead of cycling, which looks like a wrap until you count"),

    ("7-leaderboard-row-bypasses-the-one-resolver", CHART,
     "                let color = colorForOutcome(name: outcome.name, index: index)",
     "                let color = outcome.primaryColor.map { Color(hex: $0) } ?? .gray",
     "THE HALF-FIX. The plotted line is floored and the legend dot beside it is "
     "not, so a reader sees a visible line whose key is blank. Only the COUNT in "
     "the wiring test can see one site left behind"),

    ("8-leader-slot-swapped-for-another-LEGIBLE-colour", CHART,
     '        "#c41e3a", // red (leader)',
     '        "#16a34a", // red (leader)',
     "THE PINNED-PALETTE MUTANT. 3.30:1, over the floor, and a silent repaint "
     "of the leader line on every chart in the app. Only the pin sees it"),

    ("9-a-palette-slot-goes-under-the-floor", CHART,
     '        "#0e7490", // teal',
     '        "#a5d8e8", // teal',
     "THE FALLBACK MUTANT. Wiring perfect, every colour 'floored' — onto a pale "
     "teal that reads as a real colour in a diff and is 1.55:1 on the card"),

    ("10-floor-applied-to-everyone", CHART,
     SEAM_WIRED,
     """    static func markHex(_ storedHex: String?, index: Int) -> String {
        fallbackHex(index: index)
    }""",
     "over-application: Tampa Bay loses its red too, and the chart stops showing "
     "club colours at all. A suite that only ever checks the PALE case cannot "
     "tell this from a fix"),
]

# TRAP (banked by native/234): on a FAILING test run xcodebuild runs
# `simctl diagnose --timeout=600` — ~10 min per KILLED mutant, i.e. per mutant a
# working suite catches. `-collect-test-diagnostics never` is the fix.
XCB = ["xcodebuild", "test",
       "-project", str(ROOT / "Bain Luck.xcodeproj"),
       "-scheme", "Bain Luck",
       "-destination", f"platform=iOS Simulator,id={SIM}",
       "-collect-test-diagnostics", "never",
       "-only-testing:BainLuckTests/EvolutionChartMarksResolveTeamColourThroughTheFloor7036Tests",
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
