#!/usr/bin/env python3
"""Q050 mutation battery — is the drain PINNED, or does the suite just run?

The ship: `/api/events/15300759` — a `kalshi_ticker` duplicate of the completed
US Open match on 15293804 — stops answering "scheduled, 2026-08-30" and answers
with the row ESPN had final at 2026-09-01 23:05Z.

The fix is a read-side resolution driven by an id-keyed contradiction:
`event_provider_anchors` says market `KXATPMATCH-26AUG30VALMON` created 15300759,
and the market itself now says its event is 15293804. Seven refusals stand
between that contradiction and serving a different row to a reader, and EVERY ONE
of them is a place a later edit could quietly widen. That is what these mutants
are for. A SURVIVOR is a hole in the suite; the fix is the missing assertion,
never deleting the mutant.

Two mutants are not about a refusal and are the two that matter most:

* **M15 turns the whole feature off** (`canonical_id = None` at the call site) —
  the literal pre-Q050 state. If M15 survives, nothing here ships anything.
* **M17 swaps the id without swapping the body**, which is the shape of a
  half-fix that looks right in a diff: the response would carry the canonical
  `id` over the ghost's own `status` and `commence_time`.

Both halves of every mutant are VERBATIM literals, never `\\n`-escaped ones —
`scan_mutation_residue.py` Pass B flags a file holding a REPLACEMENT whose NEEDLE
is absent, and an escaped needle is absent by construction.

Mutations are applied to the real source files, the suite runs to completion, and
the files are restored — SERIALLY, and never while another pytest is in flight: a
source edit under a running suite produces phantom failures that read as real
reds.

Run:  python3 backend/scripts/evals/market_born_duplicate_drain_mutations.py
Exit: 0 = every mutant killed. 1 = at least one survived. Anything else is the
      harness failing, not a verdict (gotcha #54).
"""

from __future__ import annotations

import pathlib
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _mutation_guard import guarded_targets  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[2]
CHANNEL = ROOT / "app" / "services" / "anchor_channel.py"
ROUTE = ROOT / "app" / "routes" / "events.py"
SUITE = ROOT / "tests" / "test_market_born_duplicate_reads_as_canonical_q050.py"

#: (id, description, old, new, target). `old` must appear EXACTLY once in
#: `target` — a mutation that matches zero or many places is a harness bug
#: reported as such, never counted as a kill.
MUTANTS: list[tuple[str, str, str, str, pathlib.Path]] = [
    # ── the seven refusals, one at a time ────────────────────────────────
    (
        "M1",
        "a row a real schedule named is drained anyway (game anchor ignored)",
        """        verdict["game_anchors"]
        or verdict["provenance"] not in MARKET_BORN_COMMENCE_SOURCES""",
        """        verdict["provenance"] not in MARKET_BORN_COMMENCE_SOURCES""",
        CHANNEL,
    ),
    (
        "M2",
        "an odds_api fixture that merely ACQUIRED a market anchor is drained",
        """        or verdict["provenance"] not in MARKET_BORN_COMMENCE_SOURCES
""",
        "",
        CHANNEL,
    ),
    (
        "M3",
        "a NULL provenance reads as market-born — q076's narrowness undone, "
        "which puts most of the historic table in this class",
        """    {SOURCE_KALSHI, SOURCE_POLYMARKET, TICKER_DERIVED_COMMENCE_SOURCE}""",
        """    {SOURCE_KALSHI, SOURCE_POLYMARKET, TICKER_DERIVED_COMMENCE_SOURCE, None}""",
        CHANNEL,
    ),
    (
        "M4",
        "an anchor whose market we no longer hold counts as agreement "
        "(gotcha #53: silence read as evidence)",
        """        or verdict["unresolved"]
""",
        "",
        CHANNEL,
    ),
    (
        "M5",
        "destinations counted by ROW instead of by value, so a segment that "
        "moved three markets off one ghost reads as a three-way ambiguity — "
        "the clearest evidence the system can produce, refused",
        """    (SELECT count(DISTINCT target) FROM mkt""",
        """    (SELECT count(target) FROM mkt""",
        CHANNEL,
    ),
    (
        "M6",
        "two destinations resolve to the lowest id — a coin flip dressed as "
        "a reconciliation",
        """        or verdict["other_targets"] != 1""",
        """        or verdict["other_targets"] < 1""",
        CHANNEL,
    ),
    (
        "M7",
        "a row carrying its own score is drained onto another row",
        """        or verdict["carries_truth"]
""",
        "",
        CHANNEL,
    ),
    (
        "M8",
        "a row still holding markets is drained — and this is the mutant that "
        "makes CHAINS possible, because the no-markets refusal is the whole "
        "reason a canonical can never itself resolve onward",
        """        or verdict["holds_markets"]
""",
        "",
        CHANNEL,
    ),
    # ── the sport guard, from both sides ─────────────────────────────────
    (
        "M9",
        "the family check tightened to the raw sport key, which refuses the "
        "ENTIRE measured class (tennis_atp -> tennis_atp_us_open, 505 of 505)",
        """    return get_llm_category_for_prefix(sport_key.split("_", 1)[0])""",
        """    return sport_key""",
        CHANNEL,
    ),
    (
        "M10",
        "the family check removed — a tennis url may serve a soccer match",
        """    if ghost_family is None or ghost_family != canonical_family:""",
        """    if False:""",
        CHANNEL,
    ),
    # ── the SQL itself ───────────────────────────────────────────────────
    (
        "M11",
        "the market-kind filter dropped, so a GAME anchor is resolved as "
        "though it were a market",
        """     WHERE anch.id_kind = :market_kind""",
        """     WHERE 1 = 1""",
        CHANNEL,
    ),
    (
        "M12",
        "the join stops qualifying by source — a Polymarket condition id that "
        "collides with a Kalshi ticker resolves through the wrong provider",
        """             ON fm.source = anch.source
            AND fm.external_id = anch.source_id""",
        """             ON fm.external_id = anch.source_id""",
        CHANNEL,
    ),
    # ── the cheap gate ───────────────────────────────────────────────────
    (
        "M13",
        "the gate refuses everything, so the verdict never runs and the ship "
        "silently does nothing",
        """    return commence_time_source in MARKET_BORN_COMMENCE_SOURCES""",
        """    return False""",
        CHANNEL,
    ),
    (
        "M14",
        "the gate stops reading the score, so every completed event page pays "
        "for a verdict query it can never pass",
        """    if (
        home_score is not None
        or away_score is not None
        or completed_at is not None
    ):
        return False""",
        """    if False:
        return False""",
        CHANNEL,
    ),
    # ── the route wiring: the half that actually ships ───────────────────
    (
        "M15",
        "RED-FIRST: the resolver is never called. This is the literal pre-Q050 "
        "state of the route, so a suite that stays green here proves nothing",
        """        canonical_id = await resolve_market_born_duplicate(db, event_id)""",
        """        canonical_id = None""",
        ROUTE,
    ),
    (
        "M16",
        "the row is looked up and thrown away — the resolution computed and "
        "not served",
        """                event = canonical
                event_id = canonical_id""",
        """                event_id = canonical_id""",
        ROUTE,
    ),
    (
        "M17",
        "the body swaps but the id does not, so the odds read and the cache "
        "key both stay on the ghost — a half-fix that reads fine in a diff",
        """                event = canonical
                event_id = canonical_id""",
        """                event = canonical""",
        ROUTE,
    ),
    (
        "M18",
        "the response is cached only under the id it was SERVED, so the one "
        "population that always needs the verdict never caches",
        """    for _cache_key in {requested_event_id, event_id}:""",
        """    for _cache_key in {event_id}:""",
        ROUTE,
    ),
]


def _run_suite() -> int:
    return subprocess.run(
        [sys.executable, "-m", "pytest", str(SUITE), "-q", "--no-header"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    ).returncode


def main() -> int:
    with guarded_targets(
        [CHANNEL, ROUTE],
        "/tmp/q050_market_born_duplicate_drain_backups",
        "market_born_duplicate_drain",
    ):
        return _main()


def _main() -> int:
    originals = {CHANNEL: CHANNEL.read_text(), ROUTE: ROUTE.read_text()}

    print(
        f"denominator: {len(MUTANTS)} mutants queued against "
        f"{CHANNEL.name} + {ROUTE.name}"
    )
    baseline = _run_suite()
    if baseline != 0:
        print(
            f"HARNESS FAILURE: the unmutated suite exits {baseline}, not 0. "
            "Nothing below is a verdict."
        )
        return 2
    print("baseline: suite GREEN on the unmutated tree\n")

    killed, survived, broken = [], [], []
    try:
        for mid, desc, old, new, target in MUTANTS:
            original = originals[target]
            n = original.count(old)
            if n != 1:
                broken.append((mid, f"anchor matched {n} times, expected exactly 1"))
                print(
                    f"{mid:5} HARNESS  {desc}\n"
                    f"      anchor matched {n} times in {target.name} — not a verdict"
                )
                continue
            mutated = original.replace(old, new, 1)
            if mutated == original:
                broken.append((mid, "replacement is a no-op — NOT APPLIED"))
                print(f"{mid:5} HARNESS  {desc}\n      NOT APPLIED")
                continue
            target.write_text(mutated)
            # Prove the mutation is on disk before believing its result: a
            # mutant that failed to apply reports a green suite as a survivor.
            on_disk = target.read_text()
            if on_disk != mutated or old in on_disk:
                target.write_text(original)
                broken.append((mid, "write-back verification failed"))
                print(f"{mid:5} HARNESS  {desc}\n      NOT APPLIED on disk")
                continue
            rc = _run_suite()
            target.write_text(original)  # restore before anything else runs
            if rc == 0:
                survived.append((mid, desc))
                print(f"{mid:5} SURVIVED {desc}")
            elif rc == 1:
                killed.append(mid)
                print(f"{mid:5} killed   {desc}")
            else:
                broken.append((mid, f"pytest exit {rc}"))
                print(
                    f"{mid:5} HARNESS  {desc}\n"
                    f"      pytest exit {rc} — the gate never ran"
                )
    finally:
        for path, text in originals.items():
            path.write_text(text)

    print(
        f"\n{len(killed)}/{len(MUTANTS)} killed, {len(survived)} survived, "
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
