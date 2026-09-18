#!/usr/bin/env python3
"""native/234 — mutation run for #7036 (the white-on-white Championship Path card).

Each mutant is a one-edit change that re-introduces a real way this fix can be
lost. A mutant that SURVIVES is a hole in the guard suite, not a curiosity.

Mutant 1 is the reported defect verbatim — the call site going back to raw
`primaryColor` — so this run doubles as the red-first proof.

Usage:  python3 tools/native-234-mutations-7036.py [--list]
"""
import subprocess, sys, pathlib, signal, atexit

ROOT = pathlib.Path("/Users/bain/bainluck-dev/native/ios/Bain Luck")
HELPER = ROOT / "Bain Luck/Utilities/TeamTextContrast.swift"
VIEW = ROOT / "Bain Luck/Views/EventDetailView.swift"
SIM = "D2DA47A0-85F6-4BF8-AEFF-33146AE3EB05"

# (name, file, find, replace, why-it-matters)
MUTANTS = [
    ("1-callsite-reverts-to-raw-primaryColor", VIEW,
     """        TeamTextContrast.eventPageColors(
            awayHex: event.awayTeamData?.primaryColor,
            homeHex: event.homeTeamData?.primaryColor
        )""",
     """        ProbabilityBarPalette.colors(
            awayHex: event.awayTeamData?.primaryColor,
            homeHex: event.homeTeamData?.primaryColor
        )""",
     "THE REPORTED DEFECT. Compiles, renders, and every unit test still passes."),

    ("2-usableForText-stops-flooring", HELPER,
     "        readableOnCard(hex) ? hex : nil\n    }",
     "        hex\n    }",
     "the floor becomes a no-op while every name in the file still reads right"),

    ("3-floor-dropped-to-1", HELPER,
     "    static let minimumRatio = 3.0",
     "    static let minimumRatio = 1.0",
     "only literally-identical-to-white is rejected; #ffffff at 1.0 squeaks through"),

    ("4-floor-raised-to-AA", HELPER,
     "    static let minimumRatio = 3.0",
     "    static let minimumRatio = 4.5",
     "silent drift away from the number the web arm chose (#5165)"),

    # EQUIVALENT MUTANT — expected to survive, and proven so rather than waved
    # through. Brute-forced all 2^24 8-bit colours: ZERO have a contrast-vs-white
    # of exactly 3.0, and the nearest (`#E969A1`) clears it by 1.9e-07. `>=` and
    # `>` therefore cannot disagree on any input this function can receive. Kept
    # in the run so the claim is re-tested if the floor or the maths ever moves —
    # if this ever starts being KILLED, something reachable landed on the bound.
    ("5-floor-becomes-exclusive [EQUIVALENT, expected to survive]", HELPER,
     "        return ratio >= minimumRatio",
     "        return ratio > minimumRatio",
     "no 8-bit colour sits exactly on 3.0 — see TeamTextContrastTests boundary case"),

    ("6-unparseable-treated-as-readable", HELPER,
     '        guard let ratio = contrastVsCardSurface(hex) else { return false }',
     '        guard let ratio = contrastVsCardSurface(hex) else { return true }',
     "a colour we cannot parse is handed to the palette as if it were fine"),

    ("7-luminance-coefficients-swapped", HELPER,
     "        return 0.2126 * channel(rgb.r) + 0.7152 * channel(rgb.g) + 0.0722 * channel(rgb.b)",
     "        return 0.7152 * channel(rgb.r) + 0.2126 * channel(rgb.g) + 0.0722 * channel(rgb.b)",
     "red/green weights transposed — black and white still come out 0 and 1"),

    ("8-contrast-loses-the-offset", HELPER,
     "        return (cardSurfaceLuminance + 0.05) / (l + 0.05)",
     "        return cardSurfaceLuminance / l",
     "the WCAG 0.05 ambient term dropped; ratios explode near black"),

    ("9-linear-channel-branch-disabled", HELPER,
     "            return c <= 0.04045 ? c / 12.92 : pow((c + 0.055) / 1.055, 2.4)",
     "            return pow((c + 0.055) / 1.055, 2.4)",
     "the sRGB low-end branch never runs"),

    ("10-floor-applied-to-home-side-only", HELPER,
     """        ProbabilityBarPalette.pair(
            awayHex: usableForText(awayHex),
            homeHex: usableForText(homeHex)
        )""",
     """        ProbabilityBarPalette.pair(
            awayHex: awayHex,
            homeHex: usableForText(homeHex)
        )""",
     "half a fix: Fulham is the AWAY side in the reported specimen"),

    ("11-surface-luminance-becomes-black", HELPER,
     "    static let cardSurfaceLuminance = 1.0",
     "    static let cardSurfaceLuminance = 0.0",
     "floors against a dark surface — exactly inverts which teams are repainted"),

    ("12-floored-colour-gets-a-substitute-here", HELPER,
     "        readableOnCard(hex) ? hex : nil\n    }",
     '        readableOnCard(hex) ? hex : "#F59E0B"\n    }',
     "takes the choice away from the palette AND picks the one illegible rung"),
]


# ── TRAP 1: a killed mutant costs ten minutes, so a GOOD suite runs slowest ──
# On a failing test run, xcodebuild collects simulator diagnostics —
# `simctl diagnose --timeout=600`. That is ~10 min of wall clock PER KILLED
# MUTANT, which is every mutant a working suite catches. Measured here: the
# first pass took 35 min to reach mutant 10 and read exactly like a hung rig.
# `-collect-test-diagnostics never` is the whole fix.
XCB = ["xcodebuild", "test",
       "-project", str(ROOT / "Bain Luck.xcodeproj"),
       "-scheme", "Bain Luck",
       "-destination", f"platform=iOS Simulator,id={SIM}",
       "-collect-test-diagnostics", "never",
       "-only-testing:BainLuckTests/TeamTextContrastTests",
       "-only-testing:BainLuckTests/ProbabilityBarPaletteTests",
       "OTHER_SWIFT_FLAGS=$(inherited) -Xfrontend -disable-sandbox"]


def run_tests():
    r = subprocess.run(XCB, capture_output=True, text=True, cwd=str(ROOT))
    out = r.stdout + r.stderr
    # A mutant that does not COMPILE is killed too, but say which it was: a
    # compile kill proves nothing about the assertions.
    compiled = "Executed" in out
    return r.returncode, compiled, out


# ── TRAP 2: `finally` does not survive the harness being killed ──────────────
# The first pass was stopped with SIGTERM while mutant 10 was applied, and the
# `finally` restore did NOT run: it left `awayHex: awayHex` — a one-word change
# that compiles, renders, and half-defeats the fix — sitting in the worktree,
# where the next `git diff` reads it as something the author wrote on purpose.
# So the restore is also registered against the process dying, and the tree is
# checked on the way out rather than assumed.
_IN_FLIGHT = {}   # path -> original text


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
    code, compiled, _ = run_tests()
    if code != 0:
        print(f"  BASELINE IS RED (exit {code}) — fix that before reading any mutant")
        return 2
    print("  baseline GREEN\n")

    killed, survived = [], []
    for name, path, find, repl, why in MUTANTS:
        original = path.read_text()
        if find not in original:
            print(f"  REFUSED  {name} — anchor not found; the mutant patched NOTHING")
            print(f"           (a refused patch prints a green indistinguishable from an unkillable mutant)")
            survived.append((name, "REFUSED"))
            continue
        if original.count(find) != 1:
            print(f"  REFUSED  {name} — anchor occurs {original.count(find)}x, not unique")
            survived.append((name, "REFUSED-AMBIGUOUS"))
            continue
        try:
            _IN_FLIGHT[path] = original
            path.write_text(original.replace(find, repl, 1))
            code, compiled, out = run_tests()
            if code != 0:
                how = "assertions" if compiled else "COMPILE ONLY"
                print(f"  killed   {name}  [{how}]")
                if not compiled:
                    print(f"           ^ a compile kill does not prove the suite would catch it")
                killed.append(name)
            else:
                print(f"  SURVIVED {name}")
                print(f"           {why}")
                survived.append((name, "SURVIVED"))
        finally:
            path.write_text(original)
            _IN_FLIGHT.pop(path, None)

    print(f"\n{len(killed)}/{len(MUTANTS)} killed")
    for n, s in survived:
        print(f"  {s}: {n}")

    # The run is only trustworthy if the tree it leaves behind is the tree it
    # started from. Says so out loud rather than leaving it to the reader.
    dirty = subprocess.run(["git", "-C", "/Users/bain/bainluck-dev/native",
                            "diff", "--stat", "--", "ios/"],
                           capture_output=True, text=True).stdout.strip()
    print("\ntree on exit (expect ONLY the fix's own edit to EventDetailView.swift):")
    print("  " + (dirty.replace("\n", "\n  ") if dirty else "(clean)"))
    return 0 if not survived else 1


if __name__ == "__main__":
    sys.exit(main())
