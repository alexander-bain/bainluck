#!/usr/bin/env python3
"""ux/1304 — mutation battery for #6445's Browse gate.

Six mutants. Two of them (M4, M5) are the whole point of the ship: they are the
#6501 failure mode itself — a promotion that moves to a file the guard does not
name, and a promotion in a file the OLD guard did name but for the OTHER route.
A battery that only kills M1/M2 grades a guard nobody needed widening.

Every mutant must be KILLED (the named tests fail). A SURVIVOR is a hole.

Run from the worktree root with a clean tree; each mutant is applied, tested and
reverted with `git checkout --` — which reads the INDEX, so COMMIT FIRST.
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "ios/Bain Luck/Bain Luck"
BROWSE = APP / "Views/LeaguesView.swift"
DISCOVER = APP / "Views/DiscoverView.swift"
NEW_FILE = APP / "Views/UXMutantPromotionView.swift"

GATE_OPEN = "            if ReleaseSurfaces.predictionsExperienceEnabled {\n"
TILE = """                BrowseFeatureCard(
                    title: "Daily Challenge",
                    subtitle: "Five probability calls",
                    icon: "flame.fill",
                    color: .orange,
                    route: .dailyChallenge
                )
"""


def run_tests() -> tuple[bool, str]:
    """True if the guard suite passed."""
    proc = subprocess.run(
        [
            "xcodebuild", "-project", str(ROOT / "ios/Bain Luck/Bain Luck.xcodeproj"),
            "-scheme", "Bain Luck",
            "-destination", "platform=iOS Simulator,name=iPhone 17",
            "-disableAutomaticPackageResolution",
            "OTHER_SWIFT_FLAGS=$(inherited) -Xfrontend -disable-sandbox",
            "test",
            "-only-testing:BainLuckTests/BrowseHidesTheChallengeTile6445Tests",
            "-only-testing:BainLuckTests/PredictionsExperienceIsGatedEverywhere6501Tests",
        ],
        cwd=ROOT, capture_output=True, text=True,
    )
    out = proc.stdout + proc.stderr
    failed = [
        line.split("'")[1].split(".")[-1]
        for line in out.splitlines()
        if "Test Case '" in line and "' failed" in line
    ]
    # A compile error is a kill too — the mutant did not build — but say which.
    if "** TEST SUCCEEDED **" in out:
        return True, ""
    if not failed and "error:" in out:
        return False, "COMPILE ERROR"
    return False, ", ".join(sorted(set(failed))) or "no named failure"


def revert():
    subprocess.run(["git", "checkout", "--", str(BROWSE), str(DISCOVER)], cwd=ROOT, check=True)
    NEW_FILE.unlink(missing_ok=True)


def mutate_m1():
    """The gate is removed — the pre-fix state."""
    text = BROWSE.read_text()
    body = text[text.index(GATE_OPEN) + len(GATE_OPEN):]
    end = body.index("            }\n")
    BROWSE.write_text(
        text[:text.index(GATE_OPEN)]
        + "".join(l[4:] if l.startswith("    ") else l for l in body[:end].splitlines(True))
        + body[end + len("            }\n"):]
    )


def mutate_m2():
    """The tile is DELETED rather than gated — passes any refusal assertion."""
    text = BROWSE.read_text()
    start = text.index(GATE_OPEN)
    end = text.index("            }\n", start) + len("            }\n")
    BROWSE.write_text(text[:start] + text[end:])


def mutate_m3():
    """The gate is inverted — shown exactly when it must be hidden."""
    BROWSE.write_text(BROWSE.read_text().replace(
        GATE_OPEN, "            if !ReleaseSurfaces.predictionsExperienceEnabled {\n"
    ))


def mutate_m4():
    """The promotion MOVES to a new file the guard does not name.

    This is #6501's failure mode reproduced exactly: its scan lists two files,
    so a promotion in a third is invisible. A walk sees it.
    """
    mutate_m2()
    NEW_FILE.write_text(
        "import SwiftUI\n\n"
        "struct UXMutantPromotionView: View {\n"
        "    var body: some View {\n"
        "        NavigationLink(value: Route.dailyChallenge) { Text(\"Daily Challenge\") }\n"
        "    }\n"
        "}\n"
    )


def mutate_m5():
    """Discover's Stats toolbar button loses its gate.

    Already covered by #6501's own test — asserted here so a refactor that
    weakens THIS file's walk is caught even if #6501's file is ever retired.
    """
    text = DISCOVER.read_text()
    marker = "            if ReleaseSurfaces.predictionsExperienceEnabled {\n                ToolbarItem"
    assert marker in text, "the toolbar gate moved — update M5"
    DISCOVER.write_text(text.replace(marker, "            if true {\n                ToolbarItem"))


def mutate_m6():
    """The route is no longer registered — the screen is orphaned.

    A promotion hidden behind a flag whose destination has been deleted cannot
    be restored by flipping the flag, and a bainluck:// link in the wild dies.
    """
    route = APP / "Views/Route.swift"
    route.write_text(route.read_text().replace(
        "case .dailyChallenge: DailyChallengeView()",
        "case .dailyChallenge: EmptyView()",
    ))


MUTANTS = [
    ("M1 gate removed (the pre-fix state)", mutate_m1),
    ("M2 tile deleted rather than gated", mutate_m2),
    ("M3 gate inverted", mutate_m3),
    ("M4 promotion moved to a NEW file (#6501's own failure mode)", mutate_m4),
    ("M5 Discover's toolbar button ungated", mutate_m5),
    ("M6 destination unregistered (the screen is orphaned)", mutate_m6),
]

if __name__ == "__main__":
    dirty = subprocess.run(
        ["git", "status", "--porcelain", "--", "ios/"], cwd=ROOT,
        capture_output=True, text=True,
    ).stdout.strip()
    if dirty:
        sys.exit(f"REFUSING — ios/ is dirty, commit first:\n{dirty}")

    print("control: the unmutated tree must PASS")
    ok, _ = run_tests()
    print(f"  {'PASS' if ok else 'FAIL — the battery is measuring nothing'}")
    if not ok:
        sys.exit(1)

    killed = 0
    for name, apply in MUTANTS:
        apply()
        ok, failures = run_tests()
        subprocess.run(
            ["git", "checkout", "--", "ios/"], cwd=ROOT, check=True
        )
        NEW_FILE.unlink(missing_ok=True)
        if ok:
            print(f"  🔴 SURVIVED  {name}")
        else:
            killed += 1
            print(f"  killed      {name}  ->  {failures}")

    print(f"\n{killed}/{len(MUTANTS)} killed")
    sys.exit(0 if killed == len(MUTANTS) else 1)
