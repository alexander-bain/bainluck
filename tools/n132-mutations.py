#!/usr/bin/env python3
"""#5655 mutation sweep — does BrowseGridWidth5655Tests actually catch anything?

Each mutant is an EXACT string replacement, and the script asserts the pattern
matched exactly once before it writes (rig note 14: a `sed` that silently
no-ops leaves an unmutated tree that reads as SURVIVED).

Run from the worktree root:  python3 tools/n132-mutations.py
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
METRICS = ROOT / "ios/Bain Luck/Bain Luck/Utilities/BrowseGridMetrics.swift"
MASONRY = ROOT / "ios/Bain Luck/Bain Luck/Utilities/DiscoverMasonry.swift"

MUTANTS = [
    ("M1  league regular 200 -> 150 (the fix undone)",
     METRICS, "case .league:   return regularWidth ? 200 : 150",
              "case .league:   return regularWidth ? 150 : 150"),
    ("M2  featured regular 280 -> 230 (the fix undone)",
     METRICS, "case .featured: return regularWidth ? 280 : 230",
              "case .featured: return regularWidth ? 230 : 230"),
    ("M3  league regular 200 -> 180 (a plausible nearby constant)",
     METRICS, "case .league:   return regularWidth ? 200 : 150",
              "case .league:   return regularWidth ? 180 : 150"),
    ("M4  featured regular 280 -> 250 (a plausible nearby constant)",
     METRICS, "case .featured: return regularWidth ? 280 : 230",
              "case .featured: return regularWidth ? 250 : 230"),
    ("M5  maximum 320 -> 400",
     METRICS, "static let maximumTileWidth: CGFloat = 320",
              "static let maximumTileWidth: CGFloat = 400"),
    ("M6  spacing 12 -> 10",
     METRICS, "static let spacing: CGFloat = 12",
              "static let spacing: CGFloat = 10"),
    ("M7  columnWidth drops the maximum cap",
     MASONRY, "return min(share, maximumCardWidth)",
              "return share"),
    ("M8  columnWidth counts spacing n times instead of n-1",
     MASONRY, "let share = (availableWidth - (n - 1) * spacing) / n",
              "let share = (availableWidth - n * spacing) / n"),
    ("M9  columnWidth returns 1 for an unresolved canvas",
     MASONRY, "guard availableWidth > 0 else { return 0 }",
              "guard availableWidth > 0 else { return 1 }"),
    ("M10 compact league 150 -> 200 (a phone tile moves)",
     METRICS, "case .league:   return regularWidth ? 200 : 150",
              "case .league:   return regularWidth ? 200 : 200"),
]

TEST_CMD = [
    "xcodebuild", "test",
    "-project", "ios/Bain Luck/Bain Luck.xcodeproj",
    "-scheme", "Bain Luck",
    "-destination", "platform=iOS Simulator,name=iPhone 17",
    "-disableAutomaticPackageResolution",
    "-only-testing:BainLuckTests/BrowseGridWidth5655Tests",
    "OTHER_SWIFT_FLAGS=$(inherited) -Xfrontend -disable-sandbox",
]


def run_tests():
    p = subprocess.run(TEST_CMD, cwd=ROOT, capture_output=True, text=True, timeout=900)
    return p.returncode == 0, p.stdout + p.stderr


def main():
    killed, survived = [], []
    for name, path, old, new in MUTANTS:
        original = path.read_text()
        hits = original.count(old)
        assert hits == 1, f"{name}: pattern matched {hits} times, expected exactly 1 — refusing to write"
        try:
            path.write_text(original.replace(old, new))
            ok, _ = run_tests()
            (survived if ok else killed).append(name)
            print(f"  {'SURVIVED' if ok else 'KILLED  '}  {name}", flush=True)
        finally:
            path.write_text(original)

    print(f"\n{len(killed)}/{len(MUTANTS)} killed")
    if survived:
        print("SURVIVORS:")
        for s in survived:
            print(f"  - {s}")
    return 1 if survived else 0


if __name__ == "__main__":
    sys.exit(main())
