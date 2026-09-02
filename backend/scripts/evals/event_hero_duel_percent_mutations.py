"""LAT-P119 / #2085 — the pair-that-prints-101 mutation class.

WHAT A MUTANT PROVES HERE
-------------------------
This fix has the failure mode that every rendering fix has: it can be *present*
and *inert*. The percents can be computed correctly and then not printed; the
served pair can be attached to the wrong source and still sum to 100; the
component can quietly fall back to its own `Math.round` when a caller stops
passing them. All three read as a clean diff and a green suite.

So the question is not "does `renderedDuelPercents` work" — the contract suite
already answers that in three runtimes. It is: **would
`__tests__/components/eventHeroDuelInvariant.test.tsx` and
`__tests__/ios/eventDetailHeroDuel.test.ts` NOTICE if the event page went back
to printing 101?** Each mutant below breaks one property those files claim to
defend, and a SURVIVOR is a missing assertion, reported as such per mutant.

🔴 THE MUTANTS THAT MATTER MOST ARE NOT THE ARITHMETIC ONES. `M3` and `M4`
restore the bug that a copy of `FeedCard`'s one-liner would have shipped: the
served `current_odds` percents printed beside the BLEND's probability. Both
still sum to 100. A battery that only checked the sum would score them killed
when nothing had caught them.

WHY THE ORACLE IS JEST, OUT OF PROCESS
--------------------------------------
Re-implementing the assertions here would prove that this file's copy of them
still fails, which is worth nothing. The oracle runs the two real jest modules
against the mutated tree, so a mutant is killed only by an assertion that
genuinely ships and genuinely gates CI.

WHY THIS ONE WRITES TO DISK, WHEN THE PREFERRED SHAPE DOES NOT
--------------------------------------------------------------
The in-memory harnesses `exec` a mutated Python string. There is no equivalent
for a TypeScript module that jest must resolve through the Next.js `@/` path
alias and ts-jest — the oracle IS a subprocess, and a subprocess reads the file
system. So this harness takes the on-disk route and pays its price in full:
every target goes through `guarded_targets`, which converts the catchable
signals into an exception so `finally` restores, and leaves a manifest behind if
the process is SIGKILLed. `test_every_on_disk_harness_is_guarded` enforces that.

EVERY MUTATION IS PROVEN TO HAVE APPLIED. A needle that no longer matches makes
the mutant a no-op, and a no-op mutant scores KILLED-looking-green for the worst
possible reason. `NOT-APPLIED` is reported as its own outcome and fails the run
(exit 1), because a battery that silently shrinks is a battery that stops
testing what it says it tests.

USAGE

    python3 backend/scripts/evals/event_hero_duel_percent_mutations.py

Exit codes (gotcha #54 — read the VALUE): `0` all mutants killed, `1` at least
one SURVIVOR or NOT-APPLIED — a real result, `2` the battery could not be run.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _mutation_guard import guarded_targets  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
FRONTEND = REPO / "frontend"
RESOLVER = FRONTEND / "lib/eventKeyStats.ts"
COMPONENT = FRONTEND / "components/EventHeroProbabilityPair.tsx"
VIEW = REPO / "ios/Bain Luck/Bain Luck/Views/EventDetailView.swift"

BACKUP_DIR = Path("/tmp/lat_p119_backups")

#: The jest modules that ARE the oracle. Named, not globbed: a pattern that
#: matched nothing would run zero tests and score every mutant killed.
ORACLE_PATTERNS = ("eventHeroDuelInvariant", "eventDetailHeroDuel")


# --------------------------------------------------------------------------
# Mutants, in THREE tables, one per target file.
#
# One table with a per-entry `target` would read better here and is what this
# harness had first. It is split because `scan_mutation_residue.py` harvests a
# `(table, needle_key, replacement_key, TARGET_CONST)` shape — the target is a
# MODULE-level constant, not a dict key — and a harness the scanner cannot
# harvest is a harness whose residue nothing looks for. Registering in the shape
# the guard already understands beats teaching the guard a second shape.
# --------------------------------------------------------------------------
RESOLVER_MUTATIONS: list[dict] = [
    {
        "id": "M1-round-each-side-independently",
        "needle": """  const [localAwayPct, localHomePct] = renderedDuelPercents(
    resolved.awayProb,
    resolved.homeProb,
  );""",
        "replacement": """  const localAwayPct =
    resolved.awayProb == null ? null : Math.round(resolved.awayProb * 100);
  const localHomePct =
    resolved.homeProb == null ? null : Math.round(resolved.homeProb * 100);""",
        "why": "THE ORIGINAL BUG, restored exactly: two sides of one complement "
        "rounded independently. Prints 101 on every discriminating row.",
        "property": "the pair is decided together",
    },
    {
        "id": "M2-single-sided-served-coalesce",
        "needle": "  const bothServed = servedAway != null && servedHome != null;",
        "replacement": "  const bothServed = servedAway != null || servedHome != null;",
        "why": "Takes a served value beside a locally derived one. Re-opens 101 "
        "from the other direction on a payload that carries one field and "
        "not the other — an older deploy, or a partially rolled-out one.",
        "property": "both served values or neither",
    },
    {
        "id": "M3-attribute-served-pair-to-the-blend",
        "needle": """      return withRenderedPercents(
        {
          homeProb,
          awayProb,
          probSourceLabel,
          openingHomeProb,
          openingAwayProb,
        },
        odds,
        false,
      );""",
        "replacement": """      return withRenderedPercents(
        {
          homeProb,
          awayProb,
          probSourceLabel,
          openingHomeProb,
          openingAwayProb,
        },
        odds,
        true,
      );""",
        "why": "🔴 THE COPY-PASTE TRAP. Prints `current_odds`' rounding beside the "
        "BLEND's probability on every live game. STILL SUMS TO 100, so a "
        "sum-only assertion scores it killed while nothing caught it.",
        "property": "the served pair is attributed to its own source",
    },
    {
        "id": "M4-keep-served-pair-after-history-override",
        "needle": """          // #2085 — the pair has been REPLACED by a history row. The served
          // percents describe the `current_odds` pair this branch just
          // overrode, and the override only fires when the two differ by more
          // than 5 points, so keeping them would print a number off by five.
          fromCurrentOdds = false;""",
        "replacement": "",
        "why": "The history branch only fires when the pair moved by MORE than 5 "
        "points, so the stale served percents are wrong by at least five — "
        "and still sum to 100.",
        "property": "an overridden pair drops its served percents",
    },
]

COMPONENT_MUTATIONS: list[dict] = [
    {
        "id": "M5-component-re-rounds-when-percent-missing",
        # live/034 re-target. The rendered expression now reads `shownHome`,
        # the output of `shownPair`, because the hero can COUNT to a new value
        # on a pushed live event. The property under attack is unchanged — the
        # component must refuse to re-derive a percent it was not given — so
        # this is a new anchor for the same mutant, not a new mutant.
        "needle": """        {homeProb !== null && shownHome !== null ? shownHome : "—"}""",
        "replacement": """        {homeProb !== null ? (shownHome ?? Math.round(homeProb * 100)) : "—"}""",
        "why": "The component quietly re-derives when a caller stops passing the "
        "decided percent. The fix becomes invisible the moment anyone "
        "refactors the page, with no test going red.",
        "property": "the component refuses to re-round on its own",
    },
]

RESOLVER_MUTATIONS += [
    {
        "id": "M6-opening-line-rounds-independently",
        "needle": """  const [openingAwayPct, openingHomePct] = renderedDuelPercents(
    resolved.openingAwayProb,
    resolved.openingHomeProb,
  );""",
        "replacement": """  const openingAwayPct =
    resolved.openingAwayProb == null
      ? null
      : Math.round(resolved.openingAwayProb * 100);
  const openingHomePct =
    resolved.openingHomeProb == null
      ? null
      : Math.round(resolved.openingHomeProb * 100);""",
        "why": "'Opened 50 – 51'. The same defect one line lower on the same "
        "screen, and the one most likely to be forgotten because the hero "
        "is the part everybody looks at.",
        "property": "the opening line gets the same treatment",
    },
    {
        "id": "M7-scheduled-branch-forgets-the-served-pair",
        "needle": """    homeProb = odds?.home_probability ?? null;
    awayProb = odds?.away_probability ?? null;
    fromCurrentOdds = true;
    const count = odds?.bookmaker_count ?? 0;
    if (count > 0) {""",
        "replacement": """    homeProb = odds?.home_probability ?? null;
    awayProb = odds?.away_probability ?? null;
    const count = odds?.bookmaker_count ?? 0;
    if (count > 0) {""",
        "why": "The scheduled hero stops honouring the server's decision and "
        "always re-derives. The printed numbers still sum to 100 and are "
        "usually identical — so this is only visible to a test that asserts "
        "the SERVED value is printed verbatim, which is the one that lets a "
        "future server-side rule change reach the screen.",
        "property": "the served pair IS used when the hero really is current_odds",
    },
]

VIEW_MUTATIONS: list[dict] = [
    {
        "id": "M8-ios-hero-drops-the-override",
        "needle": "Text(formatProbability(away, renderedPercent: awayPct))",
        "replacement": "Text(formatProbability(away))",
        "why": "Native's hero goes back to rounding its own side. The Swift "
        "contract test still passes — it tests the HELPER — so only a guard "
        "that reads this view can catch it, and CI cannot run Swift.",
        "property": "the iOS hero pair goes through the decided percent",
    },
    {
        "id": "M9-ios-single-sided-served-coalesce",
        "needle": "let bothServed = odds.awayRenderedPercent != nil && odds.homeRenderedPercent != nil",
        "replacement": "let bothServed = odds.awayRenderedPercent != nil || odds.homeRenderedPercent != nil",
        "why": "M2 on native — and the pattern the neighbouring `DiscoverEventCard` "
        "still uses, so this is the mutation most likely to arrive as a "
        "well-meaning consistency edit.",
        "property": "both served values or neither, on native too",
    },
    {
        "id": "M10-ios-live-opening-line-left-bare",
        "needle": """                        let openDuel = renderedDuelPercents(away: awayOpen, home: homeOpen)
                        HStack(spacing: 4) {
                            Text("Opened \\(formatProbability(awayOpen, renderedPercent: openDuel[0])) \\u{2013} \\(formatProbability(homeOpen, renderedPercent: openDuel[1]))")""",
        "replacement": """                        HStack(spacing: 4) {
                            Text("Opened \\(formatProbability(awayOpen)) \\u{2013} \\(formatProbability(homeOpen))")""",
        "why": "HALF THE FIX. The settled branch's opening line stays fixed and the "
        "LIVE one regresses — the exact asymmetry a hand-edit produces, and "
        "the reason the guard names both call sites instead of counting one.",
        "property": "both opening lines are covered, not just the settled one",
    },
]

#: The three tables, paired with the target each one mutates. This is the same
#: mapping `SHAPES["event_hero_duel_percent_mutations"]` declares in
#: `scan_mutation_residue.py`; if the two ever disagree, the scanner harvests a
#: needle against the wrong file and Pass A reports DRIFT rather than passing.
TABLES: tuple[tuple[str, list[dict], Path], ...] = (
    ("RESOLVER_MUTATIONS", RESOLVER_MUTATIONS, RESOLVER),
    ("COMPONENT_MUTATIONS", COMPONENT_MUTATIONS, COMPONENT),
    ("VIEW_MUTATIONS", VIEW_MUTATIONS, VIEW),
)


def _mutants() -> list[tuple[dict, Path]]:
    return [(m, target) for _name, table, target in TABLES for m in table]


def _run_oracle() -> tuple[bool, str]:
    """Run the two jest modules. Returns (passed, tail)."""
    args = ["npx", "jest"]
    for pattern in ORACLE_PATTERNS:
        args += ["--testPathPatterns", pattern]
    proc = subprocess.run(
        args,
        cwd=FRONTEND,
        capture_output=True,
        text=True,
        env={**__import__("os").environ, "TZ": "UTC"},
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode == 0, out.strip().splitlines()[-6:]


def main() -> int:
    for target in (RESOLVER, COMPONENT, VIEW):
        if not target.exists():
            print(f"🔴 battery cannot run — missing target {target}")
            return 2
    if not (FRONTEND / "node_modules").exists():
        print(
            "🔴 battery cannot run — frontend/node_modules is absent. "
            "Symlink master's (see .gitignore's note on worktree installs)."
        )
        return 2

    baseline_ok, baseline_tail = _run_oracle()
    if not baseline_ok:
        print("🔴 battery cannot run — the oracle is RED before any mutation:")
        print("\n".join(baseline_tail))
        return 2
    mutants = _mutants()
    print(f"baseline: oracle GREEN ({len(mutants)} mutants to run)\n")

    killed: list[str] = []
    survived: list[dict] = []
    not_applied: list[dict] = []

    targets = [target for _name, _table, target in TABLES]
    with guarded_targets(targets, BACKUP_DIR, "lat-p119-hero-duel"):
        for m, target in mutants:
            original = target.read_text()
            if m["needle"] not in original:
                not_applied.append(m)
                print(f"🔴 {m['id']}: NOT-APPLIED — needle absent from {target.name}")
                continue
            mutated = original.replace(m["needle"], m["replacement"], 1)
            if mutated == original:
                not_applied.append(m)
                print(f"🔴 {m['id']}: NOT-APPLIED — replacement is a no-op")
                continue
            target.write_text(mutated)
            try:
                ok, tail = _run_oracle()
            finally:
                target.write_text(original)
            if ok:
                survived.append(m)
                print(f"🔴 {m['id']}: SURVIVED — {m['property']}")
                print(f"     {m['why']}")
            else:
                killed.append(m["id"])
                print(f"✅ {m['id']}: killed — {m['property']}")

    print()
    print(
        f"RESULT: {len(killed)}/{len(mutants)} killed, "
        f"{len(survived)} survived, {len(not_applied)} not-applied"
    )
    for m in survived:
        print(f"  SURVIVOR {m['id']} — missing assertion: {m['property']}")
    for m in not_applied:
        print(f"  NOT-APPLIED {m['id']} — the needle has drifted; this mutant is inert")
    return 0 if (not survived and not not_applied) else 1


if __name__ == "__main__":
    raise SystemExit(main())
