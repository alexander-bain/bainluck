#!/usr/bin/env python3
"""Mutation harness for #8066's remainder (#920 push reaching the source line).

Each mutant is a real defect the change could plausibly ship with. A SURVIVING
mutant means the guards in
`frontend/__tests__/lib/pushReachesTheSourceLineWithNoServedBlend8066.test.ts`
do not actually constrain that line — either the line is dead, or no specimen
builds the state where it matters.

    python3 tools/mutants-8066-remainder.py

Exit 0 = every mutant killed. Exit 1 = at least one survived (named in output).
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TARGET = ROOT / "frontend" / "lib" / "liveChartHistory.ts"
PATTERN = "pushReachesTheSourceLineWithNoServedBlend8066|liveChartHistory920"

# (name, what the defect would look like to a reader, old, new)
MUTANTS = [
    (
        "feature-reverted",
        "the source line never gets the push back; the page waits for the 32s poll",
        "  if (!served) return null;",
        "  if (!served) return null;\n  return null;",
    ),
    (
        "blend-on-the-source-line",
        "the blend's value is drawn as the source's own price",
        "        home_probability: point.source_probability as number,",
        "        home_probability: point.home_probability,",
    ),
    (
        "mints-an-unserved-series",
        "two pushed frames become a 2-vertex line with no legend entry (#8066 again)",
        "    if (!series?.length) continue;",
        "    if (!series) continue;",
    ),
    (
        "ties-go-to-the-push",
        "a reading stamped AT the served edge inserts beside a stale endpoint",
        "        Date.parse(point.timestamp) > edge)",
        "        Date.parse(point.timestamp) >= edge)",
    ),
    (
        "extends-even-when-blended",
        "multi-source pages get their source series rewritten for no reader gain",
        "  const extended = served.length === 0\n    ? extendServedSourceSeries(history.win_prob_history, points)\n    : null;",
        "  const extended = extendServedSourceSeries(history.win_prob_history, points);",
    ),
    (
        "mutates-the-served-payload",
        "SWR's cached object moves under the next merge; frames re-append forever",
        "    next ??= { ...served };",
        "    next ??= served;",
    ),
    (
        "accepts-an-out-of-range-reading",
        "a NaN/Infinity/out-of-band source_value reaches the plot",
        "  if (typeof frame.source === \"string\" && frame.source !== \"\" &&\n      typeof frame.source_value === \"number\" && Number.isFinite(frame.source_value) &&\n      frame.source_value >= 0 && frame.source_value <= 1) {",
        "  if (typeof frame.source === \"string\" && frame.source !== \"\" &&\n      typeof frame.source_value === \"number\") {",
    ),
    (
        "source-reading-leaks-into-the-blend",
        "the blend's array stops being plot-shaped",
        "    next.aggregate_line = [...served, ...added.map(\n      ({ timestamp, home_probability }) => ({ timestamp, home_probability }),\n    )].sort((a, b) => Date.parse(a.timestamp) - Date.parse(b.timestamp));",
        "    next.aggregate_line = [...served, ...added]\n      .sort((a, b) => Date.parse(a.timestamp) - Date.parse(b.timestamp));",
    ),
    (
        "invents-an-away-probability",
        "the complement is manufactured from a number the frame never carried",
        "        away_probability: null,",
        "        away_probability: 1 - (point.source_probability as number),",
    ),
    (
        "new-array-on-every-render",
        "the source series is rebuilt when nothing was added; every chart memo churns",
        "    if (added.length === 0) continue;",
        "    if (added.length === 0 && series.length === 0) continue;",
    ),
]


def run_suite() -> bool:
    """True when the focused suite passes."""
    proc = subprocess.run(
        ["npx", "jest", "--testPathPatterns", PATTERN],
        cwd=ROOT / "frontend",
        capture_output=True,
        text=True,
    )
    return proc.returncode == 0


def main() -> int:
    original = TARGET.read_text()

    if not run_suite():
        print("BASELINE IS RED — fix the suite before grading mutants.")
        return 2
    print("baseline: GREEN\n")

    survivors = []
    try:
        for name, story, old, new in MUTANTS:
            if original.count(old) != 1:
                print(f"  ?? {name}: anchor matched {original.count(old)} times "
                      "— the mutant never applied, which is not a kill.")
                survivors.append(name)
                continue
            TARGET.write_text(original.replace(old, new, 1))
            killed = not run_suite()
            print(f"  {'KILLED ' if killed else 'SURVIVED'} {name}  — {story}")
            if not killed:
                survivors.append(name)
    finally:
        TARGET.write_text(original)

    print()
    if survivors:
        print(f"{len(survivors)} SURVIVED: {', '.join(survivors)}")
        return 1
    print(f"all {len(MUTANTS)} mutants killed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
