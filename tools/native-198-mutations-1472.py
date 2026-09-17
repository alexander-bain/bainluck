#!/usr/bin/env python3
"""native/198 (#1472) — is every guard in the footer-refresh ship load-bearing?

Each mutant is a single edit to SHIPPED source that reintroduces a specific way
"Bottom Refresh produces no visible response or loading feedback" comes back. A
mutant that does not turn the suite red is a guard that is not guarding, and it
is reported as SURVIVED by name.

A needle that is not found, or that matches MORE THAN ONCE, is reported and is
NOT counted as a kill — an ambiguous needle grades code nobody chose and then
says SURVIVED about it (native/197's M10).

Run from the worktree root, on a CLEAN tree: restoration is `git checkout --`,
which reads the INDEX, so uncommitted work would be silently reverted.
"""
import subprocess
import sys
from pathlib import Path

# Resolved from the CWD, not from this script's own path (#5480, and
# native-gates.sh carries the same fix for the same reason). A copy of this file
# sitting in the SHARED master checkout's tools/ would otherwise mutate Alex's
# tree and grade master — measured: the first run of this battery refused on
# `~/bainluck` being dirty, which is the only reason it did not.
ROOT = Path(
    subprocess.run(["git", "rev-parse", "--show-toplevel"],
                   capture_output=True, text=True, check=True).stdout.strip()
)
SRC = ROOT / "ios/Bain Luck/Bain Luck"
CARD = SRC / "Components/ResolutionCard.swift"
VIEW = SRC / "Views/DiscoverView.swift"

MUTANTS = [
    (
        # The defect itself: the in-flight phase looks like the resting one.
        "M1 'Refreshing…' reverts to 'Refresh' — the press does not land",
        CARD,
        'title: "Refreshing…", systemImage: nil, isEnabled: false, status: nil',
        'title: "Refresh", systemImage: "arrow.clockwise", isEnabled: false, status: nil',
    ),
    (
        "M2 the in-flight phase keeps its glyph — no spinner, nothing animates",
        CARD,
        'title: "Refreshing…", systemImage: nil, isEnabled: false, status: nil',
        'title: "Refreshing…", systemImage: "arrow.clockwise", isEnabled: false, status: nil',
    ),
    (
        "M3 the control stays tappable in flight — a second press re-enters refreshFeed",
        CARD,
        'title: "Refreshing…", systemImage: nil, isEnabled: false, status: nil',
        'title: "Refreshing…", systemImage: nil, isEnabled: true, status: nil',
    ),
    (
        "M4 success says nothing — a finished refresh is silent again",
        CARD,
        'title: "Refresh", systemImage: "arrow.clockwise", isEnabled: true,\n                status: "Checked just now")',
        'title: "Refresh", systemImage: "arrow.clockwise", isEnabled: true,\n                status: nil)',
    ),
    (
        "M5 success claims content it cannot know about",
        CARD,
        'status: "Checked just now")',
        'status: "New markets added")',
    ),
    (
        "M6 failure says nothing — the only notice at this end of the page is gone",
        CARD,
        'title: "Try again", systemImage: "arrow.clockwise", isEnabled: true,\n                status: "Couldn\'t refresh")',
        'title: "Refresh", systemImage: "arrow.clockwise", isEnabled: true,\n                status: nil)',
    ),
    (
        "M7 failure offers no way out — the retry is dead",
        CARD,
        'title: "Try again", systemImage: "arrow.clockwise", isEnabled: true,\n                status: "Couldn\'t refresh")',
        'title: "Try again", systemImage: "arrow.clockwise", isEnabled: false,\n                status: "Couldn\'t refresh")',
    ),
    (
        "M8 the control speaks in jargon on a reader's screen",
        CARD,
        'status: "Couldn\'t refresh")',
        'status: "Feed request error")',
    ),
    (
        # The call-site mutant. `phase: footerRefreshPhase` occurs twice by
        # design, so each site is anchored to its WHOLE call — see M10 of
        # native/197 for why a needle that matches twice grades nothing.
        "M9 the caught-up call site is frozen on a literal — the fix ships inert there",
        VIEW,
        "NativeFeedEndCard(\n"
        "                            onRefresh: { Task { await refreshFeed() } },\n"
        "                            phase: footerRefreshPhase\n"
        "                        )\n"
        "                            .frame(maxWidth: .infinity)",
        "NativeFeedEndCard(\n"
        "                            onRefresh: { Task { await refreshFeed() } },\n"
        "                            phase: .idle\n"
        "                        )\n"
        "                            .frame(maxWidth: .infinity)",
    ),
    (
        "M10 the BOTTOM-OF-FEED call site — the one Alex pressed — is frozen on a literal",
        VIEW,
        "NativeFeedEndCard(\n"
        "                            onRefresh: { Task { await refreshFeed() } },\n"
        "                            phase: footerRefreshPhase\n"
        "                        )\n"
        "                            .padding(.horizontal)",
        "NativeFeedEndCard(\n"
        "                            onRefresh: { Task { await refreshFeed() } },\n"
        "                            phase: .idle\n"
        "                        )\n"
        "                            .padding(.horizontal)",
    ),
    (
        "M11 the confirmation window is unbounded — 'Checked just now' becomes a lie",
        VIEW,
        "static let refreshConfirmationWindow: TimeInterval = 4",
        "static let refreshConfirmationWindow: TimeInterval = 86_400",
    ),
    (
        "M12 the confirmation timer is awaited inline — every pull pins the header for 4s",
        VIEW,
        "            Task { @MainActor in\n"
        "                try? await Task.sleep(nanoseconds: UInt64(Self.refreshConfirmationWindow * 1_000_000_000))",
        "            do {\n"
        "                try? await Task.sleep(nanoseconds: UInt64(Self.refreshConfirmationWindow * 1_000_000_000))",
    ),
    (
        "M13 the refresh path's resolutions fetch is ungated again — the pull holds on a dead round trip",
        VIEW,
        "if ReleaseSurfaces.predictionsExperienceEnabled,\n"
        "           let r = try? await APIClient.shared.fetchResolutions() {",
        "if let r = try? await APIClient.shared.fetchResolutions() {",
    ),
    (
        "M14 the cold-open resolutions fetch is ungated again",
        VIEW,
        "if ReleaseSurfaces.predictionsExperienceEnabled, resolutions.isEmpty {",
        "if resolutions.isEmpty {",
    ),
]

TESTS = "BainLuckTests/FooterRefreshSaysWhatItIsDoing1472Tests"


def run_suite() -> tuple[bool, str]:
    """Green? plus the line that says so. Never piped (gotcha #54)."""
    proc = subprocess.run(
        [
            "xcodebuild", "test",
            "-project", str(ROOT / "ios/Bain Luck/Bain Luck.xcodeproj"),
            "-scheme", "Bain Luck",
            "-destination", "platform=iOS Simulator,name=iPhone 17 Pro",
            "-disableAutomaticPackageResolution",
            "-only-testing:" + TESTS,
            "OTHER_SWIFT_FLAGS=$(inherited) -Xfrontend -disable-sandbox",
        ],
        capture_output=True, text=True, cwd=ROOT,
    )
    out = proc.stdout + proc.stderr
    line = next(
        (l.strip() for l in out.splitlines() if "Executed" in l and "test" in l),
        "",
    )
    if proc.returncode not in (0, 65):
        # 65 is a normal failure; anything else is a story about the harness.
        return False, f"xcodebuild exit {proc.returncode} — THE RUN MAY NOT HAVE HAPPENED: {line}"
    return proc.returncode == 0, line or f"exit {proc.returncode}"


def main() -> int:
    dirty = subprocess.run(
        ["git", "status", "--porcelain", "--", "ios"],
        capture_output=True, text=True, cwd=ROOT,
    ).stdout.strip()
    if dirty:
        print("REFUSING: ios/ is dirty. Restoration reads the index; commit first.")
        print(dirty)
        return 2

    print("=== baseline (unmutated) ===")
    green, line = run_suite()
    print(f"  {'GREEN' if green else 'RED'}  {line}")
    if not green:
        print("  baseline is not green — every verdict below would be meaningless.")
        return 2

    killed, survived, notfound = [], [], []
    for name, path, needle, replacement in MUTANTS:
        text = path.read_text()
        occurrences = text.count(needle)
        if occurrences == 0:
            print(f"\n=== {name}\n  NEEDLE NOT FOUND — not graded, not a kill")
            notfound.append(name)
            continue
        if occurrences > 1:
            print(f"\n=== {name}\n  NEEDLE AMBIGUOUS ({occurrences} matches) — not graded, not a kill")
            notfound.append(f"{name} [ambiguous x{occurrences}]")
            continue
        path.write_text(text.replace(needle, replacement, 1))
        try:
            print(f"\n=== {name}")
            green, line = run_suite()
            if green:
                print(f"  🔴 SURVIVED — the suite stayed green. {line}")
                survived.append(name)
            else:
                print(f"  ✅ killed. {line}")
                killed.append(name)
        finally:
            subprocess.run(["git", "checkout", "--", str(path)], cwd=ROOT, check=True)

    total = len(MUTANTS)
    print(f"\n=== VERDICT  {len(killed)}/{total} killed, "
          f"{len(survived)} survived, {len(notfound)} not applied")
    for n in survived:
        print(f"  SURVIVED: {n}")
    for n in notfound:
        print(f"  NOT APPLIED: {n}")
    return 0 if (survived == [] and notfound == []) else 1


if __name__ == "__main__":
    sys.exit(main())
