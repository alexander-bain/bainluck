#!/usr/bin/env python3
"""native/197 (#6595) — is every guard in the pre-kickoff-certainty ship load-bearing?

Each mutant is a single edit to SHIPPED source that reintroduces a specific way
the defect comes back. A mutant that does not turn the suite red is a guard that
is not guarding, and it is reported as SURVIVED by name.

A mutant whose needle is not found is reported NEEDLE NOT FOUND and is NOT
counted as a kill — a mutation that never applied reads exactly like one the
suite caught (native/086's lesson).

Run from the worktree root, on a CLEAN tree: restoration is `git checkout --`,
which reads the INDEX, so uncommitted work would be silently reverted.
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "ios/Bain Luck/Bain Luck"
HELPER = SRC / "Utilities/PreKickoffCertainty.swift"
VIEW = SRC / "Components/SpecialEventMarketsView.swift"
CALLSITE = SRC / "Views/EventDetailView.swift"

MUTANTS = [
    (
        "M1 the certainty clause is dropped — every pre-kickoff row freezes",
        HELPER,
        "return isCertainty(probability)\n            && wasObservedBeforeKickoff(observedAt: observedAt, commenceTime: commenceTime)",
        "return wasObservedBeforeKickoff(observedAt: observedAt, commenceTime: commenceTime)",
    ),
    (
        "M2 the pre-kickoff clause is dropped — every certainty freezes, live ones too",
        HELPER,
        "return isCertainty(probability)\n            && wasObservedBeforeKickoff(observedAt: observedAt, commenceTime: commenceTime)",
        "return isCertainty(probability)",
    ),
    (
        "M3 'before kick-off' becomes 'at or before' — the opening price freezes",
        HELPER,
        "return at < commenceTime",
        "return at <= commenceTime",
    ),
    (
        "M4 the certainty band widens to reach a 0.99 favourite",
        HELPER,
        "static let certaintyEpsilon = 0.0005",
        "static let certaintyEpsilon = 0.02",
    ),
    (
        "M5 the has-started guard is dropped — a pregame page freezes its rows",
        HELPER,
        "guard EventState.hasStarted(commenceTime: commenceTime, now: now) else { return false }",
        "",
    ),
    (
        "M6 the finished-event guard is dropped — two mechanisms own one row",
        HELPER,
        "guard !SettledQuote.isSettled(eventStatus) else { return false }",
        "",
    ),
    (
        "M7 only the low end counts as certainty — a 1.0 row stays a live price",
        HELPER,
        "probability >= 1.0 - certaintyEpsilon || probability <= certaintyEpsilon",
        "probability <= certaintyEpsilon",
    ),
    (
        "M8 the card stops consulting the predicate (the inline-condition mutant)",
        VIEW,
        "(isGameFinished || isFrozen(o)) ? .frozenQuote : .livePrice",
        "isGameFinished ? .frozenQuote : .livePrice",
    ),
    (
        "M9 the card freezes everything once the predicate fires for any reason",
        VIEW,
        "(isGameFinished || isFrozen(o)) ? .frozenQuote : .livePrice",
        ".frozenQuote",
    ),
    (
        # ANCHORED TO THE WHOLE CALL, and that is the finding, not a detail.
        # The bare `commenceTime: event.commenceTime?.asDate` occurs NINE times
        # in EventDetailView. The first draft of this mutant used it and silently
        # mutated occurrence #1 — MarketMapView, a different view — so M10
        # reported SURVIVED against a guard that was never under test. A needle
        # that matches more than once is a needle that grades the wrong code.
        "M10 the event page stops passing its clock — the guard is disarmed in production",
        CALLSITE,
        "SpecialEventMarketsView(\n"
        "                            markets: otherMarkets,\n"
        "                            eventStatus: event.status,\n"
        "                            commenceTime: event.commenceTime?.asDate\n"
        "                        )",
        "SpecialEventMarketsView(\n"
        "                            markets: otherMarkets,\n"
        "                            eventStatus: event.status,\n"
        "                            commenceTime: nil\n"
        "                        )",
    ),
]


def run_suite() -> tuple[bool, str]:
    """Green? plus the line that says so. Never piped (gotcha #54)."""
    proc = subprocess.run(
        [
            "xcodebuild", "test",
            "-project", str(ROOT / "ios/Bain Luck/Bain Luck.xcodeproj"),
            "-scheme", "Bain Luck",
            "-destination", "platform=iOS Simulator,name=iPhone 17 Pro",
            "-disableAutomaticPackageResolution",
            "-only-testing:BainLuckTests/APreKickoffCertaintyIsNotALivePriceTests",
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
            # Measured the hard way: M10's first needle matched nine times and
            # mutated a different view, then reported SURVIVED. An ambiguous
            # needle grades code nobody chose, so it is a refusal, not a warning.
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
