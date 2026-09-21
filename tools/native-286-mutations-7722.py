#!/usr/bin/env python3
"""native/286 — mutation battery for #7722 (Accuracy screen category labels).

Same two harness rules as `native-285-mutations-7794.py`: gate on the EXIT CODE
(65 xcodebuild / 1 jest), and match `with (\\d+) failures?` — xcodebuild writes
"with 1 failure", SINGULAR, and a plural-only regex reads a sibling class's
"0 failures" and reports a killed mutant as survived.

The mutants worth naming here:

  * M1 is the defect itself: the fallback goes back to the bare title-caser and
    both rows print a prettified database key again. If anything survives, it
    should not be this one.
  * M6 removes the `table_tennis` entry and CANNOT be killed by Swift — the
    labeller derives the identical string, which is exactly why that entry is a
    parity pin rather than a label. It is in the battery to prove the jest guard
    is carrying weight the Swift suite cannot.
  * M7 is #7532's trap as a mutant: add the bare `aussierules` parent key. The
    label still reads "AFL", so a label-only suite passes — what moves is
    `normalizedCategory`, i.e. which buckets the row COUNTS.
  * M10 mutates the GUARD, not the product. It empties the swept population, and
    every `for … in` assertion in the file passes against an empty list. This
    asserts that the non-vacuity test added beside them is load bearing.
"""

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VM = ROOT / "ios/Bain Luck/Bain Luck/ViewModels/CalibrationViewModel.swift"
NICHE = ROOT / "ios/Bain Luck/Bain Luck/Utilities/NicheCategoryLabel.swift"
SPORTS = ROOT / "ios/Bain Luck/Bain Luck/Utilities/SportDisplayNames.swift"
GUARD = ROOT / "ios/Bain Luck/BainLuckTests/CalibrationPublishedCategoryLabelTests7722.swift"
SIM = "D2DA47A0-85F6-4BF8-AEFF-33146AE3EB05"

MUTANTS = [
    ("M1 the defect restored — the table falls back to the bare title-caser",
     VM, "categoryDisplayNames[category] ?? nicheCategoryLabel(category)",
     "categoryDisplayNames[category] ?? toTitleCaseAcronymSafe(category)", "swift"),

    ("M2 the AFL entry is dropped from the app's league vocabulary",
     NICHE, '    "aussierules_afl": "AFL",\n', "", "swift"),

    ("M3 the AFL entry survives but stops being an acronym",
     NICHE, '"aussierules_afl": "AFL",', '"aussierules_afl": "Afl",', "swift"),

    ("M4 `nrl` leaves the chip acronym set — NRL is derived, not curated",
     NICHE, '"nbl", "nrl", "pll",', '"nbl", "pll",', "swift"),

    ("M5 `rugbyleague` stops being a sport family, so its prefix stops dropping",
     SPORTS, '"rugbyleague": "Rugby", "rugbyunion": "Rugby",',
     '"rugbyunion": "Rugby",', "swift"),

    ("M6 the table_tennis parity pin is removed (Swift CANNOT see this one)",
     VM, '        "table_tennis": "Table Tennis",\n', "", "jest"),

    ("M7 #7532's trap — the bare `aussierules` parent key is added to the map",
     VM, '"tech": "Tech", "motorsports": "Motorsports",',
     '"tech": "Tech", "motorsports": "Motorsports", "aussierules": "Aussie Rules",', "swift"),

    ("M8 the curated-name lookup stops consulting the chip vocabulary",
     NICHE, "if let curated = leagueAcronyms[raw] ?? nicheLeagueNames[raw] { return curated }",
     "if let curated = leagueAcronyms[raw] { return curated }", "swift"),

    ("M9 the sport prefix stops being dropped from a two-token key",
     NICHE, "let named = tokens.count > 1 && sportFamilyDisplayNames[tokens[0]] != nil",
     "let named = tokens.count > 2 && sportFamilyDisplayNames[tokens[0]] != nil", "swift"),

    ("M10 the GUARD's swept population is emptied (the vacuity this ship found)",
     GUARD,
     '    private static let fallbackCategories = [\n'
     '        "rugbyleague_nrl", "aussierules_afl", "other",\n    ]',
     "    private static let fallbackCategories: [String] = []", "swift"),
]


def run_jest():
    p = subprocess.run(
        ["npx", "jest", "--testPathPatterns=calibrationCategoryLabelParity7722"],
        cwd=ROOT / "frontend", capture_output=True, text=True,
    )
    return p.returncode, p.stdout + p.stderr


def run_swift():
    p = subprocess.run(
        ["xcodebuild", "-project", str(ROOT / "ios/Bain Luck/Bain Luck.xcodeproj"),
         "-scheme", "Bain Luck", "-destination", f"id={SIM}",
         "-disableAutomaticPackageResolution",
         "-only-testing:BainLuckTests/CalibrationPublishedCategoryLabelTests7722",
         "-only-testing:BainLuckTests/CalibrationNicheChipLabelTests",
         "-only-testing:BainLuckTests/CalibrationDisplayNameTests",
         "OTHER_SWIFT_FLAGS=$(inherited) -Xfrontend -disable-sandbox", "test"],
        capture_output=True, text=True,
    )
    return p.returncode, p.stdout + p.stderr


COUNT = re.compile(r"with (\d+) failures?")


def label(out):
    hits = [int(m) for m in COUNT.findall(out)]
    return f"{sum(hits)} failing assertion group(s)" if hits else "no count line"


def main():
    results = []
    for name, path, find, repl, runner in MUTANTS:
        original = path.read_text()
        if original.count(find) != 1:
            results.append((name, "ERROR", f"anchor matches {original.count(find)}x, want 1"))
            print(f"  {results[-1][1]:9} {name}  ({results[-1][2]})", flush=True)
            continue
        path.write_text(original.replace(find, repl, 1))
        try:
            code, out = run_jest() if runner == "jest" else run_swift()
        finally:
            path.write_text(original)
        expected = 1 if runner == "jest" else 65
        if code == expected:
            verdict, detail = "KILLED", f"{runner} exit {code} — {label(out)}"
        elif code == 0:
            verdict, detail = "SURVIVED", f"{runner} exit 0 — NO TEST NOTICED"
        else:
            verdict, detail = "ERROR", f"{runner} exit {code} — harness, not a verdict"
        results.append((name, verdict, detail))
        print(f"  {verdict:9} {name}  ({detail})", flush=True)

    killed = sum(1 for _, v, _ in results if v == "KILLED")
    print(f"\n{killed}/{len(MUTANTS)} killed")
    for n, v, d in results:
        if v != "KILLED":
            print(f"  {v}: {n} — {d}")
    return 0 if killed == len(MUTANTS) else 1


if __name__ == "__main__":
    sys.exit(main())
