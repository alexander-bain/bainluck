#!/usr/bin/env python3
"""native/238 — mutation run for #7036 arm 3 (the SINGLE-COLOUR text sites).

Arm 1 mutation-tested the floor's maths (`tools/native-234-mutations-7036.py`);
arm 2 tested the wiring of the two paired CARDS
(`tools/native-236-mutations-7036-cards.py`). Neither is re-run here.

What arm 3 adds is a different shape again: sites with no pair and no palette,
each falling back to its OWN hardcoded default. So this run has two families of
mutant that the earlier arms had no reason to carry —

  * CALL-SITE mutants (1-4, 7): a site going back to raw `primaryColor`. Mutants
    1 and 3 are the reported defect verbatim, so this doubles as the red-first
    proof on both surfaces.
  * FALLBACK mutants (5, 6): the default itself moved under the floor. These are
    the ones worth the run. Every "is it readable" assertion still passes when the
    fallback is invisible, because the floored branch happily hands back a second
    unreadable colour — the fix looks wired and the reader still sees nothing.

A mutant that SURVIVES is a hole in the guard suite, not a curiosity.

Runs only from this lane's own worktree; every path below is absolute
(native/236 left a script in the shared checkout and blocked the desk's
fast-forward).

Usage:  python3 tools/native-238-mutations-7036-text-sites.py [--list]
"""
import subprocess, sys, pathlib, signal, atexit

WORKTREE = pathlib.Path("/Users/bain/bainluck-dev/native")
ROOT = WORKTREE / "ios/Bain Luck"
HELPER = ROOT / "Bain Luck/Utilities/TeamTextContrast+TextOnCard.swift"
DISCOVER = ROOT / "Bain Luck/Views/DiscoverView.swift"
MYSTUFF = ROOT / "Bain Luck/Views/MyStuffView.swift"
SIM = "D2DA47A0-85F6-4BF8-AEFF-33146AE3EB05"

# 🪤 BOTH call sites in each file are the SAME expression, twice. An anchor of
# just that expression patches nothing (count != 1) and is reported REFUSED, which
# would read as "unkillable". Each anchor below therefore carries the branch above
# it, which is what makes it unique.
THRESHOLD_WIRED = """        case .futures:
            return .primary
        case .event(let event):
            return Color(hex: GuessCardTeamTextColour.homeHex(event))"""
THRESHOLD_RAW = """        case .futures:
            return .primary
        case .event(let event):
            return Color(hex: event.homeTeamData?.primaryColor ?? "#2563eb")"""

RESULT_WIRED = """        case .futures:
            return nil
        case .event(let event):
            return Color(hex: GuessCardTeamTextColour.homeHex(event))"""
RESULT_RAW = """        case .futures:
            return nil
        case .event(let event):
            return Color(hex: event.homeTeamData?.primaryColor ?? "#2563eb")"""

MULTI_WIRED = """                Text(displayProb.map { formatProbability($0) } ?? "—")
                    .font(.subheadline)
                    .fontWeight(.semibold)
                    .monospacedDigit()
                    .foregroundStyle(Color(hex: MyStuffTeamTextColour.probabilityHex(item.matchedTeam?.primaryColor)))"""
MULTI_RAW = """                Text(displayProb.map { formatProbability($0) } ?? "—")
                    .font(.subheadline)
                    .fontWeight(.semibold)
                    .monospacedDigit()
                    .foregroundStyle(Color(hex: item.matchedTeam?.primaryColor ?? "#6b7280"))"""

SINGLE_WIRED = """                Text(formatProbability(prob))
                    .font(.subheadline)
                    .fontWeight(.semibold)
                    .monospacedDigit()
                    .foregroundStyle(Color(hex: MyStuffTeamTextColour.probabilityHex(item.matchedTeam?.primaryColor)))"""
SINGLE_RAW = """                Text(formatProbability(prob))
                    .font(.subheadline)
                    .fontWeight(.semibold)
                    .monospacedDigit()
                    .foregroundStyle(Color(hex: item.matchedTeam?.primaryColor ?? "#6b7280"))"""

# (name, file, find, replace, why-it-matters)
MUTANTS = [
    ("1-guess-card-threshold-reverts-to-raw-primaryColor", DISCOVER,
     THRESHOLD_WIRED, THRESHOLD_RAW,
     "THE REPORTED DEFECT. A white-shirted home team's 46pt threshold number is "
     "painted white on the app's default landing surface"),

    ("2-guess-card-result-reverts-to-raw-primaryColor", DISCOVER,
     RESULT_WIRED, RESULT_RAW,
     "the same defect one property down; a suite that only drives thresholdColor passes on this"),

    ("3-mystuff-multisource-reverts-to-raw-primaryColor", MYSTUFF,
     MULTI_WIRED, MULTI_RAW,
     "THE REPORTED DEFECT on My Stuff's merged rows, multi-source branch"),

    ("4-mystuff-singlesource-reverts-to-raw-primaryColor", MYSTUFF,
     SINGLE_WIRED, SINGLE_RAW,
     "the other branch. Half a fix: the same row is invisible whenever the outcome "
     "has exactly one source, which is the common case"),

    ("5-guess-card-fallback-goes-under-the-floor", DISCOVER,
     '    static let fallbackHex = "#2563eb"',
     '    static let fallbackHex = "#ffffff"',
     "THE FALLBACK MUTANT. Wiring is perfect and every colour is 'floored' — onto "
     "white. Only an assertion about the DEFAULT ITSELF can see this"),

    ("6-mystuff-fallback-goes-under-the-floor", MYSTUFF,
     '    static let fallbackHex = "#6b7280"',
     '    static let fallbackHex = "#fafafa"',
     "the same, with a near-white that looks like a real colour in a diff"),

    ("7-guess-card-paints-the-away-side", DISCOVER,
     "        TeamTextContrast.textHexOnCard(event.homeTeamData?.primaryColor, fallback: fallbackHex)",
     "        TeamTextContrast.textHexOnCard(event.awayTeamData?.primaryColor, fallback: fallbackHex)",
     "a legible colour, from the wrong team. Every readability assertion still passes"),

    ("8-helper-drops-the-floor-entirely", HELPER,
     "        usableForText(hex) ?? fallback",
     "        hex ?? fallback",
     "the floor removed from under both surfaces at once, leaving the call sites "
     "looking correctly wired"),

    ("9-helper-always-returns-the-fallback", HELPER,
     "        usableForText(hex) ?? fallback",
     "        fallback",
     "over-application: every club loses its brand colour. A suite that only ever "
     "checks the WHITE case cannot tell this from a fix"),

    ("10-mystuff-helper-ignores-the-floor", MYSTUFF,
     "        TeamTextContrast.textHexOnCard(primaryColor, fallback: fallbackHex)",
     "        primaryColor ?? fallbackHex",
     "the named seam kept, its contents hollowed out — what a later refactor does "
     "when it trusts the name"),
]

# TRAP (banked by native/234): on a FAILING test run xcodebuild runs
# `simctl diagnose --timeout=600` — ~10 min per KILLED mutant, i.e. per mutant a
# working suite catches. `-collect-test-diagnostics never` is the fix.
XCB = ["xcodebuild", "test",
       "-project", str(ROOT / "Bain Luck.xcodeproj"),
       "-scheme", "Bain Luck",
       "-destination", f"platform=iOS Simulator,id={SIM}",
       "-collect-test-diagnostics", "never",
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
