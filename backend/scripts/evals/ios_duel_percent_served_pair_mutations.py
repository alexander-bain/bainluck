"""LAT-P120 (#2279) — the served-duel-pair mutation class, on four native surfaces.

WHAT A MUTANT PROVES HERE
-------------------------
UX-P114 moved one decision to the server — the two whole percents a game strip
prints — so that four surfaces could stop each having an opinion about it. Four
native surfaces then adopted the FIELDS and kept their own opinion about how to
read them: all four coalesced per side,

    let awayPct = odds.awayRenderedPercent ?? duelFallback[0]
    let homePct = odds.homeRenderedPercent ?? duelFallback[1]

which prints a served value beside a locally derived one the moment a payload
carries one field and not the other, and that is the same 101 UX-P114 shipped to
close, arriving from the other side. The home-screen widget was worse again: it
took the preference and not the rule, so with the served fields absent it printed
101 on the very events UX-P114 measured.

Every failure in this class is INVISIBLE to a sum check taken on the happy path,
because on a fully-served payload all four surfaces are already right. So the
question this harness asks is not "does the strip render". It is: **would
`frontend/__tests__/ios/duelPercentServedPair.test.ts` NOTICE if a surface went
back?** Each mutant below breaks one property that file claims to defend, and a
SURVIVOR is a missing assertion, reported per mutant.

🔴 WHY THE ORACLE IS A SOURCE-READING SUITE, AND WHAT THAT DOES AND DOES NOT BUY
--------------------------------------------------------------------------------
Jest cannot execute Swift, and the Swift test target does not run in CI — the
contract file says so itself (`contracts/rendered_percent.json`, `$swift_note`).
So the guard suite is two halves and they defend different things:

  * the BEHAVIOUR half re-runs the rule in TypeScript, against the shared
    `renderedDuelPercents`, over the contract's own duel rows and over every
    half-percent. That is what proves the rule is *right*.
  * the SHAPE half reads the Swift as text and pins the exact expressions the
    transcription claims to mirror. That is what ties the Swift to it.

Only the shape half can see a Swift-level mutation, and this harness is
therefore a test OF THAT HALF: it asks whether the pins are specific enough. M4
and M10 exist because they are the mutants a loose pin would let through — a
transposed side that still sums to 100, and a served field handed to the wrong
parameter. If either survives, the pin is a decoration.

The oracle runs the real suite out of process, so a mutant is killed only by an
assertion that genuinely ships. Re-implementing the assertions here would prove
that this file's copy of them still fails, which is worth nothing.

THE TARGETS ARE `.swift`, WHICH IS NOT THIS DIRECTORY'S USUAL
-------------------------------------------------------------
`scan_mutation_residue.py` on master hardcodes `*.py` for its broad Pass B, so
Pass B cannot see residue in these targets. Pass A — the harness-shape pass — is
file-type agnostic and covers this file normally. The glob-derivation fix that
closes Pass B is LAT-P119's, already written and waiting on `program/latency-104`;
it is deliberately NOT duplicated here, because two copies of it would collide in
the one file every latency branch touches. In the meantime this harness restores
through `guarded_targets` (signal-safe, manifest-breadcrumbed) AND verifies at
exit that every target is byte-identical to how it started, which is the property
Pass B would otherwise be asserting.

USAGE

    python3 scripts/evals/ios_duel_percent_served_pair_mutations.py

Exit codes (gotcha #54): `0` all mutants killed, `1` at least one SURVIVOR — a
real result, `2` the battery could not be run.
"""

from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _mutation_guard import guarded_targets  # noqa: E402

EVALS = Path(__file__).resolve().parent
BACKEND = EVALS.parents[1]
ROOT = BACKEND.parent
FRONTEND = ROOT / "frontend"

IOS = ROOT / "ios/Bain Luck"
APP = IOS / "Bain Luck"

SHARED = APP / "Utilities/RenderedPercent.swift"
DISCOVER_CARD = APP / "Components/DiscoverEventCard.swift"
RELATED_ROW = APP / "Components/RelatedByTagView.swift"
MENU_BAR = APP / "Views/MenuBarView.swift"
WIDGET = IOS / "BainLuckWidget/WidgetAPIClient.swift"

TARGETS = [SHARED, DISCOVER_CARD, RELATED_ROW, MENU_BAR, WIDGET]

SUITE = "__tests__/ios/duelPercentServedPair.test.ts"

#: (id, description, target, old, new). `old` must appear EXACTLY once in its
#: target — a mutation that matches zero or many places is a harness bug reported
#: as such, never counted as a kill.
MUTANTS: list[tuple[str, str, Path, str, str]] = [
    (
        "M1",
        "the shared decision takes a lone served away — the mixed pair is back",
        SHARED,
        """    if let servedAway, let servedHome {
        return [servedAway, servedHome]
    }
    return renderedDuelPercents(away: awayProbability, home: homeProbability)""",
        """    let local = renderedDuelPercents(away: awayProbability, home: homeProbability)
    return [servedAway ?? local[0], servedHome ?? local[1]]""",
    ),
    (
        "M2",
        "the shared decision ignores the payload — the server stops being authoritative",
        SHARED,
        """    if let servedAway, let servedHome {
        return [servedAway, servedHome]
    }""",
        """    if false {
        return [servedAway ?? 0, servedHome ?? 0]
    }""",
    ),
    (
        "M3",
        "the Discover card coalesces per side again — UX-P114's own regression",
        DISCOVER_CARD,
        """                    let duel = duelPercents(
                        away: awayProbability,
                        home: homeProbability,
                        servedAway: event.currentOdds?.awayRenderedPercent,
                        servedHome: event.currentOdds?.homeRenderedPercent
                    )
                    let awayPct = duel[0]
                    let homePct = duel[1]""",
        """                    let duel = renderedDuelPercents(
                        away: awayProbability, home: homeProbability
                    )
                    let awayPct = event.currentOdds?.awayRenderedPercent ?? duel[0]
                    let homePct = event.currentOdds?.homeRenderedPercent ?? duel[1]""",
    ),
    (
        "M4",
        "the Discover card transposes the unpack — still sums to 100, still wrong",
        DISCOVER_CARD,
        """                    let awayPct = duel[0]
                    let homePct = duel[1]""",
        """                    let awayPct = duel[1]
                    let homePct = duel[0]""",
    ),
    (
        "M5",
        "the related-markets row coalesces per side again",
        RELATED_ROW,
        """                let duel = duelPercents(
                    away: awayProbability,
                    home: homeProbability,
                    servedAway: odds.awayRenderedPercent,
                    servedHome: odds.homeRenderedPercent
                )
                let awayPct = duel[0]
                let homePct = duel[1]""",
        """                let duel = renderedDuelPercents(
                    away: awayProbability, home: homeProbability
                )
                let awayPct = odds.awayRenderedPercent ?? duel[0]
                let homePct = odds.homeRenderedPercent ?? duel[1]""",
    ),
    (
        "M6",
        "the menu bar drops the source gate — current_odds' rounding beside opening_odds' probability",
        MENU_BAR,
        """                    servedAway: fromCurrentOdds ? odds?.awayRenderedPercent : nil,
                    servedHome: fromCurrentOdds ? odds?.homeRenderedPercent : nil""",
        """                    servedAway: odds?.awayRenderedPercent,
                    servedHome: odds?.homeRenderedPercent""",
    ),
    (
        "M7",
        "the menu bar re-grows its third-tier naive rounding — a fourth unshared copy",
        MENU_BAR,
        "                guard let awayPct = duel[0], let homePct = duel[1] else { return nil }",
        "                let awayPct = duel[0] ?? Int((awayProbability * 100).rounded())\n"
        "                let homePct = duel[1] ?? Int((homeProbability * 100).rounded())",
    ),
    (
        "M8",
        "the widget coalesces per side again — served home beside a derived away",
        WIDGET,
        """                homeProb: bothServed ? servedHomePct! : derivedHomePct,
                awayProb: bothServed ? servedAwayPct! : derivedAwayPct,""",
        """                homeProb: servedHomePct ?? derivedHomePct,
                awayProb: servedAwayPct ?? derivedAwayPct,""",
    ),
    (
        "M9",
        "the widget's fallback reverts to independent rounding — the original 101",
        WIDGET,
        """            let derivedHomePct = leaderIsHome ? leaderPct : 100 - leaderPct
            let derivedAwayPct = leaderIsHome ? 100 - leaderPct : leaderPct""",
        """            let derivedHomePct = Int((homeProbability * 100).rounded())
            let derivedAwayPct = Int((awayProbability * 100).rounded())""",
    ),
    (
        "M10",
        "the widget derives positionally instead of off the favourite — moves the number people check",
        WIDGET,
        "            let leaderIsHome = homeProbability >= awayProbability",
        "            let leaderIsHome = true",
    ),
    (
        "M11",
        "the widget drops the non-finite guard — Int(_:) traps and the widget goes blank",
        WIDGET,
        "                  homeProbability.isFinite else {",
        "                  true else {",
    ),
]


def _run_suite() -> int:
    return subprocess.run(
        ["npx", "jest", "--testPathPatterns", "ios/duelPercentServedPair"],
        cwd=FRONTEND,
        capture_output=True,
        text=True,
        env={**__import__("os").environ, "TZ": "UTC"},
    ).returncode


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    with guarded_targets(
        TARGETS, "/tmp/lat_p120_ios_duel_pair_backups", "ios_duel_percent_served_pair"
    ):
        return _main()


def _main() -> int:
    originals = {t: t.read_text() for t in TARGETS}
    opening = {t: _sha(t) for t in TARGETS}

    baseline = _run_suite()
    if baseline != 0:
        print(
            f"HARNESS FAILURE: the unmutated suite exits {baseline}, not 0. "
            "Nothing below is a verdict."
        )
        return 2
    print(f"baseline: suite GREEN on the unmutated tree ({len(MUTANTS)} mutants queued)\n")

    killed: list[str] = []
    survived: list[tuple[str, str]] = []
    broken: list[tuple[str, str]] = []
    try:
        for mid, desc, target, old, new in MUTANTS:
            original = originals[target]
            n = original.count(old)
            if n != 1:
                broken.append((mid, f"anchor matched {n} times, expected exactly 1"))
                print(
                    f"{mid:4} HARNESS  {desc}\n"
                    f"     anchor matched {n} times in {target.name} — not a verdict"
                )
                continue
            target.write_text(original.replace(old, new, 1))
            rc = _run_suite()
            target.write_text(original)  # restore before anything else runs
            if rc == 0:
                survived.append((mid, desc))
                print(f"{mid:4} SURVIVED {desc}")
            elif rc == 1:
                killed.append(mid)
                print(f"{mid:4} killed   {desc}")
            else:
                broken.append((mid, f"jest exit {rc}"))
                print(f"{mid:4} HARNESS  {desc}\n     jest exit {rc} — the gate never ran")
    finally:
        for target, original in originals.items():
            target.write_text(original)

    # Pass B of `scan_mutation_residue.py` cannot see `.swift` on master, so the
    # property it would assert is asserted here instead, by digest rather than by
    # believing the restore above happened.
    drifted = [t.name for t in TARGETS if _sha(t) != opening[t]]
    if drifted:
        print(f"\n🔴 RESIDUE: {', '.join(drifted)} are not byte-identical to the start")
        return 2
    print(f"\nresidue: all {len(TARGETS)} targets byte-identical to the start (sha256)")

    print(
        f"{len(killed)}/{len(MUTANTS)} killed, {len(survived)} survived, "
        f"{len(broken)} harness failures"
    )
    for mid, desc in survived:
        print(f"  SURVIVOR {mid}: {desc}")
    if broken:
        for mid, why in broken:
            print(f"  BROKEN {mid}: {why}")
        return 2
    return 1 if survived else 0


if __name__ == "__main__":
    sys.exit(main())
