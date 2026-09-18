#!/usr/bin/env python3
"""native/216 — mutation battery for #6681's guards.

A guard that cannot fail is worse than no guard: it reports safety it does not
provide. Every mutation below reintroduces the defect (or breaks the assumption
the Swift width model rests on) and must turn at least one named test RED. The
last entry is a CONTROL that changes nothing and must stay GREEN — without it a
battery that reds on everything, including a broken harness, reads as success.

Backend mutants run pytest (~1.5s each). Swift mutants run the iOS unit test
and are marked `swift: True` — they are slower and are run with --swift.

    tools/native-216-mutations-6681.py            # backend battery
    tools/native-216-mutations-6681.py --swift    # include the Swift mutants
"""

import pathlib
import shutil
import subprocess
import sys
import tempfile

REPO = pathlib.Path(__file__).resolve().parents[1]
VIEW = REPO / "ios/Bain Luck/Bain Luck/Views/PreferencesView.swift"
MODELS = REPO / "ios/Bain Luck/Bain Luck/Models/OnboardingModels.swift"
PYTEST_TARGET = "tests/test_ios_interest_tile_names_readable_6681.py"
SWIFT_CLASS = "BainLuckTests/SettingsInterestTileNamesAreReadable6681Tests"
SIM = "D2DA47A0-85F6-4BF8-AEFF-33146AE3EB05"

# (name, file, old, new, swift, why)
MUTANTS = [
    (
        "drop the scale floor from the tile name",
        VIEW,
        "                    .lineLimit(1)\n"
        "                    .minimumScaleFactor(AffinityRowMetrics.nameMinimumScaleFactor)",
        "                    .lineLimit(1)",
        False,
        "the defect itself, restored — three names truncate again",
    ),
    (
        "drop lineLimit(1) from the tile name",
        VIEW,
        "                    .lineLimit(1)\n"
        "                    .minimumScaleFactor(AffinityRowMetrics.nameMinimumScaleFactor)",
        "                    .minimumScaleFactor(AffinityRowMetrics.nameMinimumScaleFactor)",
        False,
        "the row wraps instead of scaling and the measured budget stops describing it",
    ),
    (
        "raise the floor to the rejected 0.85",
        VIEW,
        "static let nameMinimumScaleFactor: CGFloat = 0.65",
        "static let nameMinimumScaleFactor: CGFloat = 0.85",
        False,
        "College Basketball (needs 0.757) truncates again — a fix that fixes nothing",
    ),
    (
        "raise the floor to a tidy 1.0",
        VIEW,
        "static let nameMinimumScaleFactor: CGFloat = 0.65",
        "static let nameMinimumScaleFactor: CGFloat = 1.0",
        False,
        "equivalent to deleting the fix while leaving the modifier in place",
    ),
    (
        "drop the floor to an illegible 0.3",
        VIEW,
        "static let nameMinimumScaleFactor: CGFloat = 0.65",
        "static let nameMinimumScaleFactor: CGFloat = 0.3",
        False,
        "fits everything by making it unreadable — the guard must refuse both directions",
    ),
    (
        "re-inline the capsule padding literal",
        VIEW,
        ".padding(.horizontal, AffinityRowMetrics.capsuleHorizontalPadding)",
        ".padding(.horizontal, 10)",
        False,
        "same pixels today, but the Swift model silently stops tracking the view",
    ),
    (
        "re-inline the emoji width literal",
        VIEW,
        ".frame(width: AffinityRowMetrics.emojiWidth)",
        ".frame(width: 28)",
        False,
        "ditto — drift becomes invisible at the next padding change",
    ),
    (
        "re-inline the card padding literal",
        VIEW,
        ".padding(.horizontal, AffinityRowMetrics.cardHorizontalPadding)",
        ".padding(.horizontal, 14)",
        False,
        "ditto",
    ),
    (
        "widen the capsules so the name budget shrinks",
        VIEW,
        "static let capsuleHorizontalPadding: CGFloat = 10",
        "static let capsuleHorizontalPadding: CGFloat = 16",
        True,
        "a real regression a literal-only guard cannot see: the row still uses the "
        "constants, but the name no longer fits at the shipped floor",
    ),
    (
        "add a tile name longer than any today",
        MODELS,
        'SportItem(key: "culture", name: "Culture"',
        'SportItem(key: "culture", name: "Culture and Performing Arts"',
        True,
        "the fit test must refuse a new display name the row cannot show",
    ),
    (
        "CONTROL — no mutation",
        VIEW,
        "static let nameMinimumScaleFactor: CGFloat = 0.65",
        "static let nameMinimumScaleFactor: CGFloat = 0.65",
        False,
        "must stay GREEN; if this reds the harness is broken, not the code",
    ),
]


def run_backend() -> tuple[bool, str]:
    proc = subprocess.run(
        ["python3", "-m", "pytest", PYTEST_TARGET, "-q", "--no-header", "-x"],
        cwd=REPO / "backend",
        capture_output=True,
        text=True,
    )
    return proc.returncode == 0, proc.stdout.strip().splitlines()[-1] if proc.stdout else ""


def run_swift() -> tuple[bool, str]:
    proc = subprocess.run(
        [
            "xcodebuild", "test",
            "-project", str(REPO / "ios/Bain Luck/Bain Luck.xcodeproj"),
            "-scheme", "Bain Luck",
            "-destination", f"platform=iOS Simulator,id={SIM}",
            "-disableAutomaticPackageResolution",
            "-only-testing:" + SWIFT_CLASS,
            "OTHER_SWIFT_FLAGS=$(inherited) -Xfrontend -disable-sandbox",
        ],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    line = ""
    for ln in proc.stdout.splitlines():
        if "Executed" in ln and "test" in ln:
            line = ln.strip()
            break
    return proc.returncode == 0, line


def main() -> int:
    include_swift = "--swift" in sys.argv
    results = []

    for name, path, old, new, is_swift, why in MUTANTS:
        if is_swift and not include_swift:
            results.append((name, "SKIPPED (--swift)", why))
            continue

        original = path.read_text(encoding="utf-8")
        is_control = old == new

        if not is_control:
            if original.count(old) != 1:
                print(f"!! ANCHOR MISS for {name!r}: {original.count(old)} matches", file=sys.stderr)
                return 2
            path.write_text(original.replace(old, new), encoding="utf-8")

        try:
            with tempfile.TemporaryDirectory():
                green, summary = run_swift() if is_swift else run_backend()
        finally:
            path.write_text(original, encoding="utf-8")

        if is_control:
            verdict = "GREEN (correct)" if green else "RED (HARNESS BROKEN)"
            ok = green
        else:
            verdict = "RED (bites)" if not green else "GREEN (SURVIVED — guard is blind)"
            ok = not green

        results.append((name, verdict, why))
        print(f"{'ok ' if ok else 'XX '}{name:52s} {verdict}  {summary}")

    print()
    bad = [r for r in results if "SURVIVED" in r[1] or "HARNESS BROKEN" in r[1]]
    ran = [r for r in results if "SKIPPED" not in r[1]]
    print(f"{len(ran) - len(bad)}/{len(ran)} mutants behaved as required")
    for name, verdict, why in results:
        print(f"  - {name}: {verdict}\n      {why}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
