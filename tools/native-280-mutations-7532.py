#!/usr/bin/env python3
"""#7532 mutation battery — does the new guard actually catch its own defect?

Each mutation below is a DIFFERENT way to reintroduce "a niche chip wears the
name of a category the table above is publishing", or to break one of the
clauses the ported ruling (L2-103 Item 3b, Alex D5) is made of. A mutation that
SURVIVES is a hole in `CalibrationNicheChipLabelTests`, not a curiosity.

Only `BainLuckTests/CalibrationNicheChipLabelTests` is run per mutation — the
full suite is the gate, this is the aim check, and 11 tests answer in ~40s where
3,176 take 80s plus a link.

Every mutation edits BEHAVIOUR, never a docstring: an anchor that lands in prose
kills nothing and reads exactly like a vacuous guard (the trap native/279 hit).

    python3 tools/native-280-mutations-7532.py
"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IOS = ROOT / "ios" / "Bain Luck"
PROJECT = IOS / "Bain Luck.xcodeproj"
HELPER = IOS / "Bain Luck" / "Utilities" / "NicheCategoryLabel.swift"
VIEWMODEL = IOS / "Bain Luck" / "ViewModels" / "CalibrationViewModel.swift"

# (name, file, find, replace, why it must die)
MUTATIONS = [
    (
        "the defect itself: normalise, then look the parent up",
        VIEWMODEL,
        "        nicheCategoryLabel(raw)",
        "        categoryDisplayNames[normalizedCategory(raw)] ?? toTitleCaseAcronymSafe(raw)",
        "this IS #7532 — 67 of 109 chips wear a published parent's name",
    ),
    (
        "a well-meant parent fallback when no curated name exists",
        HELPER,
        "    if let curated = leagueAcronyms[raw] ?? nicheLeagueNames[raw] { return curated }",
        "    if let curated = leagueAcronyms[raw] ?? nicheLeagueNames[raw] { return curated }\n"
        "    if let parent = sportFamilyDisplayNames[raw.split(separator: \"_\").first.map(String.init) ?? raw] { return parent }",
        "the shape the issue warns about — kind, and still says Soccer 613",
    ),
    (
        "drop segment 0 by POSITION instead of membership",
        HELPER,
        "    let named = tokens.count > 1 && sportFamilyDisplayNames[tokens[0]] != nil\n"
        "        ? Array(tokens.dropFirst())\n"
        "        : tokens",
        "    let named = tokens.count > 1 ? Array(tokens.dropFirst()) : tokens",
        "web's UX-P189 finding: track_and_field becomes 'And Field'",
    ),
    (
        "curated names are re-cased instead of returned verbatim",
        HELPER,
        "    if let curated = leagueAcronyms[raw] ?? nicheLeagueNames[raw] { return curated }",
        "    if let curated = leagueAcronyms[raw] ?? nicheLeagueNames[raw] { return toTitleCaseAcronymSafe(curated) }",
        "this is how web's 'NCAAF' became 'Ncaaf'",
    ),
    (
        "key-only acronyms stop being shouted",
        HELPER,
        "    if nicheKeyAcronyms.contains(lower) { return lower.uppercased() }",
        "    if false, nicheKeyAcronyms.contains(lower) { return lower.uppercased() }",
        "CFL arrives as 'Cfl', FA Cup as 'Fa Cup'",
    ),
    (
        "small words are title-cased like any other token",
        HELPER,
        "    if !isFirst, nicheTitleSmallWords.contains(lower) { return lower }",
        "",
        "'League of Ireland' becomes 'League Of Ireland'",
    ),
    (
        "a leading small word is lowercased too (isFirst ignored)",
        HELPER,
        "    if !isFirst, nicheTitleSmallWords.contains(lower) { return lower }",
        "    if nicheTitleSmallWords.contains(lower) { return lower }",
        "'The Masters' becomes 'the Masters' — a lowercase chip",
    ),
    (
        "the chip-only names are promoted into the shared vocabulary",
        HELPER,
        '    "icehockey_sweden_hockey_league": "SHL",',
        "",
        "removing SHL sends the Swedish league back to a bare title-case",
    ),
]

UDID_CMD = ["bash", "-c", f'source "{ROOT}/tools/native-gates.sh" --explain >/dev/null 2>&1; true']


def run_class() -> tuple[bool, str]:
    """Run just the #7532 class. Returns (passed, pass_line)."""
    proc = subprocess.run(
        [
            "xcodebuild", "test",
            "-project", str(PROJECT),
            "-scheme", "Bain Luck",
            "-destination", f"id={UDID}",
            "-clonedSourcePackagesDirPath", SPM_STORE,
            "-only-testing:BainLuckTests/CalibrationNicheChipLabelTests",
            "OTHER_SWIFT_FLAGS=$(inherited) -Xfrontend -disable-sandbox",
        ],
        cwd=ROOT, capture_output=True, text=True,
    )
    out = proc.stdout + proc.stderr
    line = ""
    for m in re.finditer(r"Executed \d+ tests?, with \d+ failures?[^\n]*", out):
        line = m.group(0)
    if proc.returncode not in (0, 65):
        return False, f"xcodebuild exit {proc.returncode} — the run never happened: {line}"
    return proc.returncode == 0, line


def main() -> int:
    original = {p: p.read_text() for p in {HELPER, VIEWMODEL}}
    results = []
    try:
        print("=== baseline (unmutated) ===", flush=True)
        ok, line = run_class()
        print(f"  {'PASS' if ok else 'FAIL'}  {line}", flush=True)
        if not ok:
            print("  baseline is red — fix that before reading any mutation below.")
            return 2

        for i, (name, path, find, repl, why) in enumerate(MUTATIONS, 1):
            text = original[path]
            if find not in text:
                results.append((name, "ANCHOR MISS", why))
                print(f"\n=== {i}. {name}\n  ANCHOR MISS — mutation never applied", flush=True)
                continue
            if text.count(find) != 1:
                results.append((name, "ANCHOR AMBIGUOUS", why))
                print(f"\n=== {i}. {name}\n  ANCHOR AMBIGUOUS ({text.count(find)} sites)", flush=True)
                continue
            path.write_text(text.replace(find, repl))
            print(f"\n=== {i}. {name}\n  expect RED: {why}", flush=True)
            ok, line = run_class()
            verdict = "SURVIVED" if ok else "KILLED"
            results.append((name, verdict, why))
            print(f"  {verdict}  {line}", flush=True)
            path.write_text(text)
    finally:
        for p, t in original.items():
            p.write_text(t)
        print("\n(sources restored)")

    killed = sum(1 for _, v, _ in results if v == "KILLED")
    print(f"\n=== SUMMARY: {killed}/{len(MUTATIONS)} killed")
    for name, verdict, why in results:
        print(f"  {verdict:16} {name}")
    return 0 if killed == len(MUTATIONS) else 1


if __name__ == "__main__":
    UDID = subprocess.run(
        ["bash", "-c",
         'xcrun simctl list devices available | grep -m1 "iPhone 17 Pro (" | sed -E "s/.*\\(([0-9A-F-]{36})\\).*/\\1/"'],
        capture_output=True, text=True).stdout.strip()
    # The SAME store native-gates.sh resolves. A `ls | head -1` glob picks
    # whichever of ~90 DerivedData dirs sorts first, and the partial ones make
    # xcodebuild re-resolve the package graph, time out on the Firebase binary
    # targets and exit 74 — "the run never happened", which is not a verdict on
    # any mutation (gotcha #124: read the exit code's VALUE).
    SPM_STORE = subprocess.run(
        ["bash", "-c",
         'echo "${BAINLUCK_SPM_STORE:-$HOME/Library/Developer/Xcode/DerivedData/'
         'Bain_Luck-cwkxplfeuucvrvbplvqqlcgmpcgx/SourcePackages}"'],
        capture_output=True, text=True).stdout.strip()
    if not UDID:
        print("no iPhone 17 Pro simulator — the battery never ran")
        sys.exit(2)
    print(f"simulator {UDID}\nSPM store {SPM_STORE}\n")
    sys.exit(main())
