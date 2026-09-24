#!/usr/bin/env python3
"""native/327 (#8415) — mutants for FeedInterleave.spaced. Each must turn the
focused Swift tests red. Restores the file after every mutant."""
import subprocess, sys
F = "ios/Bain Luck/Bain Luck/Utilities/DiscoverPresentation.swift"
SIM = sys.argv[1] if len(sys.argv) > 1 else "D2DA47A0-85F6-4BF8-AEFF-33146AE3EB05"
MUTANTS = {
    "M1 old defect: a sports card whenever the cap allows": (
        "            let rungs: [(Queue) -> Bool] = [\n",
        "            let rungs: [(Queue) -> Bool] = [\n                { sportsCategories.contains($0.category) && allowedBySportsRules($0) },\n"),
    "M2 no sports run cap": (
        "(sportsSinceNonSport < maxSportsRun && q.category != lastCategory)",
        "(q.category != lastCategory)"),
    "M3 same-sport pairs allowed": (
        "(sportsSinceNonSport < maxSportsRun && q.category != lastCategory)",
        "(sportsSinceNonSport < maxSportsRun)"),
    "M4 web-exact: phone's non-sports rules dropped": (
        "                { allowedBySportsRules($0) && $0.category != lastCategory && $0.family != lastFamily },\n                { allowedBySportsRules($0) && $0.category != lastCategory },\n                { allowedBySportsRules($0) && $0.family != lastFamily },\n",
        ""),
    "M5 story rule dropped": (
        "                { allowedBySportsRules($0) && $0.family != lastFamily },\n",
        ""),
    "M6 lowest-ranked head wins": (
        "if best[r].map({ queues[$0].members[queues[$0].head] > rank }) ?? true { best[r] = q }",
        "if best[r].map({ queues[$0].members[queues[$0].head] < rank }) ?? true { best[r] = q }"),
    "M7 classifier re-run per slot": (
        "            lastCategory = categories[picked]\n",
        "            lastCategory = category(items[picked])\n"),
}
orig = open(F).read()
bad = 0
try:
    for name, (a, b) in MUTANTS.items():
        assert orig.count(a) == 1, f"{name}: anchor count {orig.count(a)}"
        open(F, "w").write(orig.replace(a, b))
        r = subprocess.run(["xcodebuild", "test", "-project", "ios/Bain Luck/Bain Luck.xcodeproj",
            "-scheme", "Bain Luck", "-destination", f"platform=iOS Simulator,id={SIM}",
            "-disableAutomaticPackageResolution",
            "OTHER_SWIFT_FLAGS=$(inherited) -Xfrontend -disable-sandbox",
            "-only-testing:BainLuckTests/DiscoverSpacingTests",
            "-only-testing:BainLuckTests/DiscoverCategoryTests"], capture_output=True, text=True)
        out = r.stdout + r.stderr
        fails = sorted({l.split("error: -[")[1].split("]")[0] for l in out.splitlines() if "error: -[" in l})
        killed = r.returncode != 0 and bool(fails)
        bad += not killed
        print(f"{'KILLED ' if killed else 'SURVIVED'} {name} (exit {r.returncode}) {fails[:4]}", flush=True)
finally:
    open(F, "w").write(orig)
print(f"{len(MUTANTS) - bad}/{len(MUTANTS)} killed")
sys.exit(1 if bad else 0)
