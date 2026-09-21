#!/usr/bin/env python3
"""native/284 — mutation battery for #7759 / #7763 (corrections log copy + order).

Each mutant is a defect a reader would SEE (or that silently unhooks a guard).
A mutant that survives means the guard for it is decoration.

TWO HARNESS RULES THIS SCRIPT EXISTS TO OBEY
--------------------------------------------

1. `xcodebuild` prints **"with 1 failure"** — SINGULAR — when exactly one test
   fails. A harness matching `with (\\d+) failures` misses that line entirely and
   falls through to a sibling class's "0 failures", reporting a KILLED mutant as
   SURVIVED. native/283 lost time to exactly this. So: gate on the EXIT CODE
   (65 = tests failed), and only use the text as a label.

2. Only exit code `1` (jest) / `65` (xcodebuild) is a RESULT. Anything else —
   70 (bad destination), 127, 137, 143 — is a story about the harness and is
   reported as ERROR, never as KILLED.
"""

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LIB = ROOT / "ios/Bain Luck/Bain Luck/Utilities/CalibrationCorrections.swift"
VIEW = ROOT / "ios/Bain Luck/Bain Luck/Views/CalibrationView.swift"
SIM = "D2DA47A0-85F6-4BF8-AEFF-33146AE3EB05"

# (label, file, find, replace, runner)
#   runner "jest"  — killed by the cross-surface parity guard (a CI deploy gate)
#   runner "swift" — killed by CorrectionsLogReadsInEnglish7759Tests
MUTANTS = [
    # ── the copy (#7759) ────────────────────────────────────────────────────
    ("M1 drop a map entry the issue names",
     LIB,
     '        "Malformed-binary exclusion":\n'
     '            "Yes-or-no markets that settled with no winner, or with two, are no longer scored",\n',
     "", "jest"),
    ("M2 the app says something the site does not",
     LIB,
     '"Yes-or-no markets that settled with no winner, or with two, are no longer scored"',
     '"Malformed binary markets are excluded"', "jest"),
    ("M3 the view stops calling the map",
     VIEW, "Text(CalibrationCorrections.title(c.title))", "Text(c.title)", "jest"),
    ("M4 the auditor paragraph comes back",
     VIEW,
     "                                Text(CalibrationCorrections.title(c.title))\n",
     "                                Text(c.description)\n"
     "                                Text(CalibrationCorrections.title(c.title))\n", "jest"),
    ("M5 the map is consulted but ignored",
     LIB, "if let override = titleOverrides[title] { return override }", "", "swift"),
    ("M6 the withhold floor stops withholding",
     LIB, "return carriesInternalReference(title) ? withheldInternalReference(title) : title",
     "return title", "swift"),
    ("M7 the tracker detector fails open",
     LIB, "return re.firstMatch(in: title, range: NSRange(title.startIndex..., in: title)) != nil",
     "return false", "swift"),
    ("M8 the word-boundary on the single-letter arms goes",
     LIB, r"(?:\b(?:Queue|Issue|CERT|OPS|CAL-P|L2|UX-P|D|q)[\s-]?#?\d+|#\d{2,})",
     r"(?:(?:Queue|Issue|CERT|OPS|CAL-P|L2|UX-P|D|q)[\s-]?#?\d+|#\d{2,})", "swift"),
    # ── the order (#7763) ───────────────────────────────────────────────────
    ("M9 the view stops sorting",
     VIEW, "CalibrationCorrections.ordered(viewModel.corrections)", "viewModel.corrections", "jest"),
    ("M10 the sort loses its stability tie-break",
     LIB, "return lhs.offset < rhs.offset", "return false", "jest"),
    ("M11 the log reads newest-first",
     LIB, "return lhs.element.date < rhs.element.date", "return lhs.element.date > rhs.element.date",
     "swift"),
]


def run_jest():
    p = subprocess.run(
        ["npx", "jest", "--testPathPatterns=correctionsLogCopyParity7759"],
        cwd=ROOT / "frontend", capture_output=True, text=True,
    )
    return p.returncode, (p.stdout + p.stderr)


def run_swift():
    p = subprocess.run(
        ["xcodebuild", "-project", str(ROOT / "ios/Bain Luck/Bain Luck.xcodeproj"),
         "-scheme", "Bain Luck", "-destination", f"id={SIM}",
         "-disableAutomaticPackageResolution",
         "-only-testing:BainLuckTests/CorrectionsLogReadsInEnglish7759Tests",
         "OTHER_SWIFT_FLAGS=$(inherited) -Xfrontend -disable-sandbox", "test"],
        capture_output=True, text=True,
    )
    return p.returncode, (p.stdout + p.stderr)


# NOTE the `s?`: xcodebuild writes "with 1 failure", singular.
COUNT = re.compile(r"with (\d+) failures?")


def label(out):
    hits = [int(m) for m in COUNT.findall(out)]
    return f"{sum(hits)} failing assertion group(s)" if hits else "no count line"


def main():
    results = []
    for name, path, find, repl, runner in MUTANTS:
        original = path.read_text()
        if find not in original:
            results.append((name, "ERROR", "anchor not found — mutant never applied"))
            continue
        if original.count(find) != 1:
            results.append((name, "ERROR", f"anchor matches {original.count(find)}x, want 1"))
            continue

        path.write_text(original.replace(find, repl, 1))
        try:
            code, out = run_jest() if runner == "jest" else run_swift()
        finally:
            path.write_text(original)

        expected_fail = 1 if runner == "jest" else 65
        if code == expected_fail:
            results.append((name, "KILLED", f"{runner} exit {code} — {label(out)}"))
        elif code == 0:
            results.append((name, "SURVIVED", f"{runner} exit 0 — NO TEST NOTICED"))
        else:
            # gotcha #124: not a result, a story about the harness.
            results.append((name, "ERROR", f"{runner} exit {code} — harness, not a verdict"))
        print(f"  {results[-1][1]:9} {name}  ({results[-1][2]})", flush=True)

    killed = sum(1 for _, v, _ in results if v == "KILLED")
    print(f"\n{killed}/{len(MUTANTS)} killed")
    bad = [r for r in results if r[1] != "KILLED"]
    if bad:
        print("\nNOT KILLED:")
        for n, v, d in bad:
            print(f"  {v}: {n} — {d}")
    return 0 if killed == len(MUTANTS) else 1


if __name__ == "__main__":
    sys.exit(main())
