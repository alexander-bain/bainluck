#!/usr/bin/env python3
"""native/305 — mutation battery for #8144.

Each mutant is a single edit that RESTORES the defect or severs one wire the fix
depends on. A mutant that survives is a guard that does not guard.

Run from the worktree root:  python3 tools/native-305-mutations-8144.py
"""
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CARD = ROOT / "ios/Bain Luck/Bain Luck/Components/DiscoverEventCard.swift"
MODEL = ROOT / "ios/Bain Luck/Bain Luck/Utilities/GameCardStatusColumn.swift"
SIM = "D2DA47A0-85F6-4BF8-AEFF-33146AE3EB05"
CLASS = "BainLuckTests/TheInningColumnIsMeasuredNotPinned8144Tests"

# (label, file, find, replace) — `find` MUST occur exactly once, which is itself
# the check that the mutation landed. A mutation that silently applied nowhere
# reports the suite's own green as a kill.
MUTANTS = [
    (
        "M1 the defect itself: the status column is pinned at 50pt again",
        CARD,
        """                    if case let .inline(statusWidth) = statusLayout {
                        statusLabel(maximumLines: GameCardStatusColumn.maximumInlineStatusLines)
                            .frame(width: statusWidth)
                    }""",
        """                    statusLabel(maximumLines: GameCardStatusColumn.maximumInlineStatusLines)
                        .frame(width: 50)""",
    ),
    (
        "M2 the hero stops measuring itself — the model always sees width 0",
        CARD,
        "availableWidth: heroContentWidth,",
        "availableWidth: 0,",
    ),
    (
        "M3 the card reads the APP's text size instead of the view's",
        CARD,
        "typeSize: dynamicTypeSize",
        "typeSize: .large",
    ),
    (
        "M4 the reflowed arm is never drawn",
        CARD,
        """                if statusLayout == .stacked {
                    statusLabel(maximumLines: GameCardStatusColumn.maximumStackedStatusLines)
                        .frame(maxWidth: .infinity)
                }""",
        "",
    ),
    (
        "M5 the share bound is dropped — only the team floor is left",
        MODEL,
        """        let budget = min(
            availableWidth - teamColumnFloor(scores: scores, typeSize: typeSize) * 2,
            availableWidth * maximumInlineStatusShare)""",
        """        let budget = availableWidth - teamColumnFloor(scores: scores, typeSize: typeSize) * 2""",
    ),
    (
        "M6 the team floor is dropped — only the share bound is left",
        MODEL,
        """        let budget = min(
            availableWidth - teamColumnFloor(scores: scores, typeSize: typeSize) * 2,
            availableWidth * maximumInlineStatusShare)""",
        """        let budget = availableWidth * maximumInlineStatusShare""",
    ),
    (
        "M7 the floor forgets the score and is the avatar forever",
        MODEL,
        "        return max(avatarWidth, widest)",
        "        return avatarWidth",
    ),
    (
        "M8 the status is measured in the label's face, not its own",
        MODEL,
        "            forTextStyle: isLive ? .caption2 : .footnote, compatibleWith: traits)",
        "            forTextStyle: .caption1, compatibleWith: traits)",
    ),
    (
        "M9 the share becomes a half — the period may outgrow both crests",
        MODEL,
        "    static let maximumInlineStatusShare: Double = 1.0 / 3.0",
        "    static let maximumInlineStatusShare: Double = 1.0 / 2.0",
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
            killed, detail = run_suite()
            verdict = "SURVIVED" if killed else "KILLED"
            print(f"{verdict:8} {label}\n         {detail}")
            if killed:
                survivors.append(label)
        finally:
            shutil.copy(backup, path)
            backup.unlink()

    print()
    if survivors:
        print(f"{len(survivors)} SURVIVOR(S):")
        for s in survivors:
            print(f"  - {s}")
        return 1
    print(f"all {len(MUTANTS)} mutants killed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
