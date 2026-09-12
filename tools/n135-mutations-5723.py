#!/usr/bin/env python3
"""#5723 — mutation sweep for the category-label guards (native/135).

Each mutant reverts ONE of the six sites this ship changed, back to exactly the
text that was on master, then runs the guard class. A mutant that SURVIVES is a
guard that would not have caught the defect it was written for.

Two rules learned on #5709 and applied here:

  * A mutant that dies at the COMPILER is a weaker kill — it proves the code did
    not build, not that the test ran. Every mutant below is a valid Swift
    expression of the same type, so all of them compile.
  * A survivor may be EQUIVALENT. Look at the mutant before weakening the
    assertion: M6 survived a first draft of this sweep because the two
    formatters agree on all 77 production keys, which is a fact about the
    population, not a hole in the test — it is why that guard is a source rule
    rather than a behaviour rule.

Usage:  python3 tools/n135-mutations-5723.py [--list]
"""
from __future__ import annotations

import argparse
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
IOS = ROOT / "ios" / "Bain Luck"
PROJECT = IOS / "Bain Luck.xcodeproj"
TEST_CLASS = "BainLuckTests/SportCategoryLabelSingleSourceTests"

# (id, file, what it is, the shipped text, the master text it reverts to)
MUTANTS = [
    (
        "M1",
        "Bain Luck/Utilities/SportDisplayNames.swift",
        "the helper's fallback goes back to the repair-only formatter",
        "    return toTitleCaseAcronymSafe(key)",
        '    return properTitleCase(key.replacingOccurrences(of: "_", with: " "))',
    ),
    (
        "M2",
        "Bain Luck/Views/SearchView.swift",
        "the search row cases the raw key again ('Mma')",
        "                    Text(sportCategoryDisplayName(category))",
        "                    Text(category.capitalized)",
    ),
    (
        "M3",
        "Bain Luck/Views/MyStuffView.swift",
        "the My Stuff row cases the raw key again",
        "                Text(futures.llmSportCategory.map(sportCategoryDisplayName) ?? \"Futures\")",
        '                Text(futures.llmSportCategory?.capitalized ?? "Futures")',
    ),
    (
        "M4",
        "Bain Luck/Views/FuturesDetailView.swift",
        "the hero pill upper-cases the raw key again ('TABLE_TENNIS')",
        "                        Text(sportCategoryDisplayName(category).uppercased())",
        "                        Text(category.uppercased())",
    ),
    (
        "M5",
        "Bain Luck/Components/FuturesBrowseComponents.swift",
        "the Browse ROW reaches past the shared rule to the formatter under it",
        "            title: market.llmSportCategory.map(sportCategoryDisplayName) ?? \"Futures\",",
        '            title: market.llmSportCategory.map(toTitleCaseAcronymSafe) ?? "Futures",',
    ),
    (
        "M6",
        "Bain Luck/Components/FuturesBrowseComponents.swift",
        "the Browse CHIP reaches past the shared rule to the formatter under it",
        "        sportCategoryDisplayName(tag)",
        "        toTitleCaseAcronymSafe(tag)",
    ),
    # M7 is not a revert: it is the anti-vacuity probe for the scan's window.
    # A line-local scan reads the tree as clean while the defect sits one line
    # away, which is the single most likely way this guard rots.
    (
        "M7",
        "BainLuckTests/SportCategoryLabelSingleSourceTests.swift",
        "the casing scan's context window shrinks to the line itself",
        "        _ lines: [String], _ index: Int, window: Int = 4",
        "        _ lines: [String], _ index: Int, window: Int = 0",
    ),
]


def sim_udid() -> str:
    out = subprocess.run(
        ["xcrun", "simctl", "list", "devices", "available"],
        capture_output=True, text=True, check=True,
    ).stdout
    for line in out.splitlines():
        m = re.match(r"\s+iPhone .*\(([0-9A-Fa-f-]{36})\)", line)
        if m:
            return m.group(1)
    sys.exit("no iPhone simulator available — the sweep cannot run")


def run_guard(udid: str) -> tuple[int, str]:
    p = subprocess.run(
        [
            "xcodebuild", "test",
            "-project", str(PROJECT),
            "-scheme", "Bain Luck",
            "-destination", f"id={udid}",
            f"-only-testing:{TEST_CLASS}",
            "OTHER_SWIFT_FLAGS=$(inherited) -Xfrontend -disable-sandbox",
        ],
        capture_output=True, text=True,
    )
    return p.returncode, p.stdout + p.stderr


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true", help="print the mutants and stop")
    args = ap.parse_args()

    if args.list:
        for mid, path, what, _, _ in MUTANTS:
            print(f"{mid}  {path}\n      {what}")
        return 0

    udid = sim_udid()
    print(f"simulator: {udid}")

    # M7 edits the test file; when it is the subject, the file under mutation IS
    # the guard, which is fine — a window of 0 must still red.
    results = []
    for mid, rel, what, shipped, master in MUTANTS:
        path = IOS / rel
        original = path.read_text(encoding="utf-8")
        if shipped not in original:
            print(f"{mid}: SHIPPED TEXT NOT FOUND in {rel} — the sweep is stale, not the code")
            results.append((mid, "STALE", what))
            continue
        if original.count(shipped) != 1:
            print(f"{mid}: shipped text appears {original.count(shipped)}x — ambiguous patch")
            results.append((mid, "AMBIGUOUS", what))
            continue
        path.write_text(original.replace(shipped, master), encoding="utf-8")
        try:
            code, log = run_guard(udid)
            failing = sorted(set(re.findall(r"'-\[\S+ (test\w+)\]' failed", log)))
            # `xcodebuild test` exits 65 for BOTH "your code does not compile"
            # and "a test failed", so the exit code alone cannot tell a real
            # kill from a compiler kill — a first draft of this sweep reported
            # two genuine kills as COMPILER on exactly that confusion. The
            # discriminator is whether a test was named as failing: a mutant
            # that never built names none (gotcha #124 — read what the code
            # MEANS here, not just its value).
            if code == 0:
                verdict = "SURVIVED"
            elif failing:
                verdict = "KILLED"
            elif "error:" in log:
                verdict = "COMPILER"
            else:
                verdict = f"UNCLEAR({code})"
            print(f"{mid}: {verdict:8} exit={code}  {what}")
            for f in failing:
                print(f"        killed by {f}")
            results.append((mid, verdict, what))
        finally:
            path.write_text(original, encoding="utf-8")

    print("\n--- SUMMARY ---")
    for mid, verdict, what in results:
        print(f"{mid}: {verdict:8} {what}")
    killed = sum(1 for _, v, _ in results if v == "KILLED")
    print(f"{killed} of {len(results)} killed by a test that RAN")
    return 0 if killed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
