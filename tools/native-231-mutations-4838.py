#!/usr/bin/env python3
"""native/231 — mutation battery for #4838's guards.

`ALadderDeltaTagNamesTheRung4838Tests` is the first test this component has ever
had, so nothing else in the fleet says whether it can fail. Every mutant below
restores the defect, or breaks an assumption the fix rests on, and must turn at
least one named test RED. The last entry is a CONTROL that changes nothing and
must stay GREEN — a battery that reds on everything, a broken harness included,
reads as success.

Both source files are mutated: the view (the fix) and, once, the view's own
DOCSTRING — the source-scan test strips comments before asserting, and its
strawman assertion (`raw.contains("case \"PLAYOFFS\"")`) exists so that the strip
cannot pass vacuously. A battery that never mutates the prose never tests that.

    tools/native-231-mutations-4838.py            # the whole battery (~8 runs)
    tools/native-231-mutations-4838.py --list     # print the mutants, run nothing
"""

import pathlib
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parents[1]
VIEW = REPO / "ios/Bain Luck/Bain Luck/Components/LadderCardView.swift"
SWIFT_CLASS = "BainLuckTests/ALadderDeltaTagNamesTheRung4838Tests"
# iPhone 17 Pro. NOT 76D961F0 — that one is Alex's reserved sign-in device and
# the fleet guard refuses it by name.
SIM = "D2DA47A0-85F6-4BF8-AEFF-33146AE3EB05"

# (name, file, old, new, why)
MUTANTS = [
    (
        "key the map on the display label again (#4838 itself)",
        VIEW,
        "    switch key {",
        "    switch label.uppercased() {",
        "the defect restored verbatim: no served label equals a case, so all four "
        "leagues fall to prefix(3) and three of them truncate again",
    ),
    (
        "drop the whitespace trim from the fallback",
        VIEW,
        '        return String(label.prefix(3))\n'
        '            .trimmingCharacters(in: .whitespaces)\n'
        '            .uppercased()',
        '        return String(label.prefix(3))\n'
        '            .uppercased()',
        "MLB's `AL / NL Champ` renders `AL  24H` with a double space the moment a "
        "column reorder makes it last",
    ),
    (
        "make the fallback return the championship word",
        VIEW,
        '        return String(label.prefix(3))\n'
        '            .trimmingCharacters(in: .whitespaces)\n'
        '            .uppercased()',
        '        return "WIN"',
        "a constant WIN satisfies every championship assertion; only the converse "
        "test can tell a fix from a rubber stamp",
    ),
    (
        "give `division` the championship word",
        VIEW,
        '    case "division":     return "DIV"',
        '    case "division":     return "WIN"',
        "proves the map has a second entry and that it is asserted, not assumed",
    ),
    (
        "drop the empty-abbreviation guard",
        VIEW,
        '    return abbrev.isEmpty ? "24H" : "\\(abbrev) 24H"',
        '    return "\\(abbrev) 24H"',
        "a label with nothing to abbreviate emits a LEADING space — the malformed "
        "tag the trim alone cannot prevent",
    ),
    (
        "stop passing the column key at the call site",
        VIEW,
        "headlineDeltaLabel: lastLabel.map { shortDeltaLabel(key: lastKey, label: $0) },",
        "headlineDeltaLabel: lastLabel.map { shortDeltaLabel(key: nil, label: $0) },",
        "the helper is correct and the CARD still truncates — the defect moved one "
        "line up, which only the source scan can see",
    ),
    (
        "re-add the dead PLAYOFFS case in CODE",
        VIEW,
        '    case "division":     return "DIV"',
        '    case "division":     return "DIV"\n    case "PLAYOFFS":     return "PO"',
        "a case for a string the API never sends is back; the scan strips comments "
        "precisely so it can still see this",
    ),
    (
        "delete the defect from the DOCSTRING (strawman check)",
        VIEW,
        'So three of four leagues printed a truncation, and `case "PLAYOFFS"` was dead',
        "So three of four leagues printed a truncation, and the dead case was dead",
        "the scan's strip is only meaningful while the prose it strips contains the "
        "defect string; without this mutant the strip could pass vacuously forever",
    ),
    (
        "CONTROL — no mutation",
        VIEW,
        '    case "championship": return "WIN"',
        '    case "championship": return "WIN"',
        "must stay GREEN; if this reds, the harness is broken, not the code",
    ),
]


def run_swift() -> tuple[bool, str]:
    proc = subprocess.run(
        [
            "xcodebuild", "test",
            "-project", str(REPO / "ios/Bain Luck/Bain Luck.xcodeproj"),
            "-scheme", "Bain Luck",
            "-destination", f"platform=iOS Simulator,id={SIM}",
            "-disableAutomaticPackageResolution",
            "-only-testing:" + SWIFT_CLASS,
            "OTHER_SWIFT_FLAGS=$(inherited) -Xfrontend -disable-sandbox",
        ],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    # A compile failure is a RED for a mutant and a broken harness for the
    # control; either way say which, because "0 tests executed" and "10 tests,
    # 3 failures" are different stories and only one of them is a guard biting.
    line = ""
    for ln in proc.stdout.splitlines():
        if "Test Suite 'All tests'" in ln or ("Executed" in ln and "test" in ln):
            line = ln.strip()
    if not line:
        line = "NO TEST RAN (compile failure or harness error)"
    return proc.returncode == 0, line


def main() -> int:
    if "--list" in sys.argv:
        for name, _, old, new, why in MUTANTS:
            print(f"- {name}\n    {'CONTROL' if old == new else 'mutates'}: {why}")
        return 0

    results = []
    for name, path, old, new, why in MUTANTS:
        original = path.read_text(encoding="utf-8")
        is_control = old == new

        if not is_control:
            if original.count(old) != 1:
                print(f"!! ANCHOR MISS for {name!r}: {original.count(old)} matches", file=sys.stderr)
                return 2
            path.write_text(original.replace(old, new), encoding="utf-8")

        try:
            green, summary = run_swift()
        finally:
            # Always restore, Ctrl-C included: a mutant left in the tree is a
            # defect shipped by the battery that was meant to catch it.
            path.write_text(original, encoding="utf-8")

        if is_control:
            verdict = "GREEN (correct)" if green else "RED (HARNESS BROKEN)"
            ok = green
        else:
            verdict = "RED (bites)" if not green else "GREEN (SURVIVED — guard is blind)"
            ok = not green

        results.append((name, verdict, why))
        print(f"{'ok ' if ok else 'XX '}{name:56s} {verdict}  {summary}")

    print()
    bad = [r for r in results if "SURVIVED" in r[1] or "HARNESS BROKEN" in r[1]]
    print(f"{len(results) - len(bad)}/{len(results)} mutants behaved as required")
    for name, verdict, why in results:
        print(f"  - {name}: {verdict}\n      {why}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
