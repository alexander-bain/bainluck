#!/usr/bin/env python3
"""#8182 mutation sweep — does the guard suite actually hold the fix down?

Each mutation is a single edit that breaks the ship in a way a reader would
notice, applied to the real source and then reverted. A SURVIVOR is a mutation
the suite does not catch, and it is a hole in the tests, not a curiosity.

Arm 1 is the STRAWMAN: it restores the exact defect #8182 was filed for.
Arm 9 is the one that matters most for this particular fix — it points the
page's drawability read at the page's OWN payload instead of the chart's, which
is the mistake the whole ship exists to correct. A suite that survives arm 9 is
testing the "two points" half of the rule and nothing about the RANGE half.

Usage: python3 tools/ux-8182-mutations.py
"""
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
FE = ROOT / "frontend"
PAGE = FE / "app/events/[id]/models/page.tsx"
RULE = FE / "lib/event/chartDrawableSources.ts"

TESTS = "modelsPageChartLineClaim8182"

# (label, file, find, replace)
MUTATIONS = [
    (
        "1 STRAWMAN: the footer is unconditional again (the filed defect)",
        PAGE,
        "{drawable.has(key) && (",
        "{true && (",
    ),
    (
        "2 the count is hard-plural again ('1 data points')",
        PAGE,
        '{meta.snapshot_count === 1 ? "" : "s"} captured',
        '{"s"} captured',
    ),
    (
        "3 the singular/plural test is inverted",
        PAGE,
        '{meta.snapshot_count === 1 ? "" : "s"} captured',
        '{meta.snapshot_count === 1 ? "s" : ""} captured',
    ),
    (
        "4 one point is enough to stroke a line",
        RULE,
        "export const MIN_POINTS_TO_STROKE = 2;",
        "export const MIN_POINTS_TO_STROKE = 1;",
    ),
    (
        "5 the chart's own too-loose test: non-empty is drawable",
        RULE,
        "return Array.isArray(points) && points.length >= MIN_POINTS_TO_STROKE;",
        "return Array.isArray(points) && points.length > 0;",
    ),
    (
        "6 betting is dropped from the rule (an UNDER-claim)",
        RULE,
        'if (strokes(chartRangeHistory.history)) drawable.add("betting");',
        "",
    ),
    (
        "7 the espn fallback stops being an `else` and always applies",
        RULE,
        "  } else if (strokes(chartRangeHistory.espn_history)) {\n    drawable.add(\"espn\");\n  }",
        "  }\n  if (strokes(chartRangeHistory.espn_history)) {\n    drawable.add(\"espn\");\n  }",
    ),
    (
        "8 an unknown payload is treated as drawable",
        RULE,
        "  if (!chartRangeHistory) return drawable;",
        '  if (!chartRangeHistory) return new Set(["betting"]);',
    ),
    (
        "9 RANGE: drawability is read off the page's own untrimmed payload",
        PAGE,
        "const drawable = drawableChartSources(chartRangeData);",
        "const drawable = drawableChartSources(historyData);",
    ),
    (
        "10 RANGE: the second read drops `range`, so it re-fetches the page's view",
        PAGE,
        "        EVENT_BOOT_HISTORY_RANGE\n      )",
        "        undefined\n      )",
    ),
]


def run_tests() -> bool:
    r = subprocess.run(
        ["npx", "jest", "--testPathPatterns", TESTS, "--ci", "--silent"],
        cwd=FE,
        capture_output=True,
        text=True,
    )
    return r.returncode == 0


def main() -> int:
    if not run_tests():
        print("BASELINE IS RED — fix the suite before mutating.", file=sys.stderr)
        return 2
    print("baseline GREEN\n")

    survivors = []
    for label, path, find, replace in MUTATIONS:
        original = path.read_text()
        if find not in original:
            print(f"  !! ANCHOR MISSING — {label}")
            survivors.append(label + "  (anchor missing: the mutation never applied)")
            continue
        path.write_text(original.replace(find, replace, 1))
        try:
            killed = not run_tests()
        finally:
            path.write_text(original)
        print(f"  {'KILLED ' if killed else 'SURVIVED'}  {label}")
        if not killed:
            survivors.append(label)

    print(f"\n{len(MUTATIONS) - len(survivors)}/{len(MUTATIONS)} killed")
    for s in survivors:
        print(f"  SURVIVOR: {s}")
    return 1 if survivors else 0


if __name__ == "__main__":
    sys.exit(main())
