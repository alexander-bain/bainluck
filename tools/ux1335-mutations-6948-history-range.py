#!/usr/bin/env python3
"""#6948 mutation battery — is the guard suite non-vacuous?

Each mutant is a defect a future edit could plausibly introduce. A SURVIVOR is a hole in the
guards, not a curiosity. Run from the repo root on a COMMITTED tree; the script restores every
file it touches and prints `applied`/`restored` for each so a crashed run is visible rather than
silent.

Anchors are asserted to appear EXACTLY ONCE before a mutation is applied. A mutation that cannot
find its anchor has measured nothing, and says so rather than counting as a kill.
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FRONTEND = ROOT / "frontend"

RANGE_LIB = FRONTEND / "lib/event/historyRange.ts"
BOOT_LIB = FRONTEND / "lib/event/detailBoot.ts"
PAGE = FRONTEND / "app/events/[id]/page.tsx"

BAND = "eventHistoryRange|eventDetailBoot"

MUTANTS = [
    (
        "latch is no longer one-way (derived fresh each render) -> the oscillation returns",
        RANGE_LIB,
        "  if (prev) return true;\n",
        "",
    ),
    (
        "latch keys on the range alone -> a duplicate request for every scheduled game",
        RANGE_LIB,
        'return chartTimeRange === "all" && preWindowOmitted === true;',
        'return chartTimeRange === "all";',
    ),
    (
        "latch treats an absent flag as a trim -> guesses at an older payload",
        RANGE_LIB,
        "preWindowOmitted === true;",
        "preWindowOmitted !== false;",
    ),
    (
        "latch fires on 'live' too -> the trimmed body is abandoned for the range it was built for",
        RANGE_LIB,
        'chartTimeRange === "all" &&',
        "true &&",
    ),
    (
        "range param inverted -> the full body is asked for first and the saving is gone",
        RANGE_LIB,
        "return fullHistoryRequested ? undefined : EVENT_BOOT_HISTORY_RANGE;",
        "return fullHistoryRequested ? EVENT_BOOT_HISTORY_RANGE : undefined;",
    ),
    (
        "range param re-spelt as a literal -> the two-builders shape returns",
        RANGE_LIB,
        "return fullHistoryRequested ? undefined : EVENT_BOOT_HISTORY_RANGE;",
        'return fullHistoryRequested ? undefined : "since-start";',
    ),
    (
        "'All' sends a made-up token instead of omitting the parameter",
        RANGE_LIB,
        "return fullHistoryRequested ? undefined : EVENT_BOOT_HISTORY_RANGE;",
        'return fullHistoryRequested ? ("all" as HistoryRangeParam) : EVENT_BOOT_HISTORY_RANGE;',
    ),
    (
        "effective range reverts to the state variable -> the transient 'all' race returns "
        "(measured: KC-DEN fetched BOTH bodies on every load)",
        RANGE_LIB,
        "return chartRangeUserSet ? chartTimeRange : evidenceChartTimeRange;",
        "return chartTimeRange;",
    ),
    (
        "effective range ignores the reader -> tapping 'All' never asks for the head back",
        RANGE_LIB,
        "return chartRangeUserSet ? chartTimeRange : evidenceChartTimeRange;",
        "return evidenceChartTimeRange;",
    ),
    (
        "effective range inverted -> the reader's choice and the evidence swap places",
        RANGE_LIB,
        "return chartRangeUserSet ? chartTimeRange : evidenceChartTimeRange;",
        "return chartRangeUserSet ? evidenceChartTimeRange : chartTimeRange;",
    ),
    (
        "the page feeds the latch the raw state variable again, bypassing the helper",
        PAGE,
        "effectiveChartRange(chartRangeUserSet, chartTimeRange, evidenceChartTimeRange),",
        "chartTimeRange,",
    ),
    (
        "the boot stops parking the range -> the claim misses and every cold load double-fetches",
        BOOT_LIB,
        "/history?hours=${EVENT_BOOT_HISTORY_HOURS}&range=${EVENT_BOOT_HISTORY_RANGE}`",
        "/history?hours=${EVENT_BOOT_HISTORY_HOURS}`",
    ),
    (
        "the boot parks a different range token than the page sends",
        BOOT_LIB,
        'export const EVENT_BOOT_HISTORY_RANGE = "since_start";',
        'export const EVENT_BOOT_HISTORY_RANGE = "sincestart";',
    ),
    (
        "the page re-spells the token at the call site instead of using the helper",
        PAGE,
        "historyRangeParam(fullHistoryRequested)",
        '(fullHistoryRequested ? undefined : "since_start")',
    ),
]


def run_band() -> bool:
    """True when the band is GREEN."""
    proc = subprocess.run(
        ["npx", "jest", f"--testPathPatterns={BAND}"],
        cwd=FRONTEND,
        capture_output=True,
        text=True,
    )
    return proc.returncode == 0


def main() -> int:
    dirty = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=no"],
        cwd=ROOT, capture_output=True, text=True,
    ).stdout.strip()
    if dirty:
        print("REFUSING: tree is dirty. Commit first — this script restores from disk, not git.")
        print(dirty)
        return 2

    print("baseline: ", end="", flush=True)
    if not run_band():
        print("RED — the battery measures nothing against a red baseline.")
        return 2
    print("GREEN\n")

    killed, survived, unmeasured = 0, [], []

    for name, path, anchor, replacement in MUTANTS:
        original = path.read_text()
        count = original.count(anchor)
        if count != 1:
            print(f"?? ANCHOR NOT FOUND ({count}x) — MEASURED NOTHING: {name}")
            unmeasured.append(name)
            continue

        path.write_text(original.replace(anchor, replacement))
        print(f"   applied  : {name}")
        try:
            green = run_band()
        finally:
            path.write_text(original)
            print(f"   restored : {path.relative_to(ROOT)}")

        if green:
            print(f"🔴 SURVIVED: {name}\n")
            survived.append(name)
        else:
            print(f"✅ killed  : {name}\n")
            killed += 1

    total = len(MUTANTS)
    print(f"\n=== {killed}/{total} killed, {len(survived)} survived, {len(unmeasured)} unmeasured ===")
    for s in survived:
        print(f"  SURVIVOR : {s}")
    for u in unmeasured:
        print(f"  UNMEASURED: {u}")

    final = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=no"],
        cwd=ROOT, capture_output=True, text=True,
    ).stdout.strip()
    if final:
        print("\n🔴 TREE LEFT DIRTY — restore failed:")
        print(final)
        return 2
    print("tree restored clean")

    return 0 if (not survived and not unmeasured) else 1


if __name__ == "__main__":
    sys.exit(main())
