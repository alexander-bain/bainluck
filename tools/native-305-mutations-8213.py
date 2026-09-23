#!/usr/bin/env python3
"""native/305 — mutation battery for #8213.

Each mutant is a single edit that RESTORES the defect or severs one wire the fix
depends on. A mutant that survives is a guard that does not guard.

Run from the worktree root:  python3 tools/native-305-mutations-8213.py
"""
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CARD = ROOT / "ios/Bain Luck/Bain Luck/Components/DiscoverFuturesCard.swift"
MODEL = ROOT / "ios/Bain Luck/Bain Luck/Utilities/FuturesOutcomeRowColumns.swift"
SIM = "D2DA47A0-85F6-4BF8-AEFF-33146AE3EB05"
CLASS = "BainLuckTests/TheFuturesPercentColumnIsMeasured8213Tests"

# (label, file, find, replace) — `find` MUST occur exactly once, which is itself
# the check that the mutation landed. A mutation that silently applied nowhere
# reports the suite's own green as a kill.
MUTANTS = [
    (
        "M1 the defect itself: the percent column is pinned at 34pt again",
        CARD,
        "                .frame(width: columns.percentWidth, alignment: .trailing)",
        "                .frame(width: 34, alignment: .trailing)",
    ),
    (
        "M2 the row's other literal: the name cap is 140 again",
        CARD,
        "                    maxWidth: columns.nameMaximum,",
        "                    maxWidth: 140,",
    ),
    (
        "M3 the rows stop measuring themselves — the model always sees width 0",
        CARD,
        "                        availableWidth: outcomeRowWidth,",
        "                        availableWidth: 0,",
    ),
    (
        "M4 the card stops reading its own text size — frozen at .large",
        CARD,
        "                        typeSize: dynamicTypeSize",
        "                        typeSize: .large",
    ),
    (
        "M5 the shared column becomes the FIRST row's ink, not the widest",
        MODEL,
        "        let ink = (percentLabels\n            .map { percentWidth($0, typeSize: typeSize) }\n            .max() ?? 0) + inkSlack",
        "        let ink = (percentLabels\n            .map { percentWidth($0, typeSize: typeSize) }\n            .first ?? 0) + inkSlack",
    ),
    (
        "M6 the bar loses its guaranteed share — the name may take the row",
        MODEL,
        "    static let barMinimumShare: Double = 1.0 / 3.0",
        "    static let barMinimumShare: Double = 0.0",
    ),
    (
        "M7 the slack goes, so a fractional overflow clips the last glyph",
        MODEL,
        "    static let inkSlack: Double = 1",
        "    static let inkSlack: Double = 0",
    ),
    (
        "M8 the percentage is measured in a face the row does not draw",
        MODEL,
        "        let base = UIFont.preferredFont(forTextStyle: .caption1, compatibleWith: traits)",
        "        let base = UIFont.preferredFont(forTextStyle: .caption2, compatibleWith: traits)",
    ),
    (
        "M9 the name floor goes — a narrow card collapses the column",
        MODEL,
        "        return Layout(percentWidth: ink, nameMaximum: max(nameMinimum, remaining))",
        "        return Layout(percentWidth: ink, nameMaximum: remaining)",
    ),
    (
        "M10 the percentage may wrap again inside its measured box",
        CARD,
        "                .lineLimit(1)\n                .frame(width: columns.percentWidth, alignment: .trailing)",
        "                .frame(width: columns.percentWidth, alignment: .trailing)",
    ),
    (
        "M11 the row's spacing drifts from the spacing the model subtracts",
        CARD,
        "        HStack(spacing: FuturesOutcomeRowColumns.interColumnSpacing) {",
        "        HStack(spacing: 8) {",
    ),
    (
        "M12 the model measures the APP's text size, not the VIEW's",
        MODEL,
        "        let traits = UITraitCollection(\n            preferredContentSizeCategory:\n                CalibrationSourceTableGeometry.CellFont.contentSizeCategory(typeSize))\n        let base = UIFont.preferredFont(forTextStyle: .caption1, compatibleWith: traits)",
        "        let base = UIFont.preferredFont(forTextStyle: .caption1)",
    ),
]


def run_suite() -> tuple[bool, str]:
    proc = subprocess.run(
        [
            "xcodebuild", "test",
            "-project", str(ROOT / "ios/Bain Luck/Bain Luck.xcodeproj"),
            "-scheme", "Bain Luck",
            "-destination", f"id={SIM}",
            "-only-testing:" + CLASS,
            "OTHER_SWIFT_FLAGS=$(inherited) -Xfrontend -disable-sandbox",
        ],
        capture_output=True, text=True,
    )
    out = proc.stdout + proc.stderr
    executed = re.findall(r"Executed (\d+) tests?, with (\d+) failures?", out)
    if not executed:
        return False, "NO PASS LINE — the run never finished (compile error or harness)"
    tests, failures = executed[-1]
    return int(failures) == 0, f"{tests} tests, {failures} failures"


def main() -> int:
    ok, baseline = run_suite()
    print(f"BASELINE: {baseline}")
    if not ok:
        print("baseline is not green — fix that before mutating")
        return 2

    survivors = []
    for label, path, find, replace in MUTANTS:
        original = path.read_text()
        count = original.count(find)
        if count != 1:
            print(f"SKIPPED  {label}\n         anchor occurs {count} times, not 1")
            survivors.append(label + " (anchor did not land)")
            continue
        backup = Path(tempfile.mkstemp(suffix=".swift")[1])
        shutil.copy(path, backup)
        try:
            path.write_text(original.replace(find, replace, 1))
            green, detail = run_suite()
            verdict = "SURVIVED" if green else "KILLED"
            print(f"{verdict:8} {label}\n         {detail}")
            if green:
                survivors.append(label)
        finally:
            shutil.copy(backup, path)
            backup.unlink(missing_ok=True)

    print()
    if survivors:
        print(f"{len(survivors)} SURVIVOR(S) of {len(MUTANTS)}:")
        for s in survivors:
            print(f"  - {s}")
        return 1
    print(f"all {len(MUTANTS)} mutants killed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
