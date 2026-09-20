"""Targeted price refresh for register-pinned tournament markets (UX-P139).

═══ THE DEFECT THIS EXISTS TO FIX ═══

Alex, item 2: "was that the real current price-dark state or a mock artifact?
Then state the production guarantee: with the freshness gates, silently-stale
data can never render."

The freshness gates work — that half of the guarantee has held since UX-P131.
What the gates cannot do is make a number fresh, and measured 2026-08-26 the
entire playoff grid was 27 hours old:

    futures_odds_snapshots, all 672 US Open ladder outcomes
        newest captured_at : 2026-08-25 20:21:47 UTC
        oldest captured_at : 2026-08-25 16:15:28 UTC
    futures_odds_snapshots, Polymarket overall
        newest captured_at : 2026-08-26 23:39:28 UTC   (current to the minute)

So the poller was healthy and these particular markets were not being reached.
The cause is structural, not a bug: Gamma caps offset pagination at 2000
(gotcha "Poly creation freeze"), so ``_poll_polymarket_markets`` rotates a
20-page window across the active-event space and re-prices a given event only
when the cursor lands on it.  For most of the catalogue a once-a-day reading is
fine.  For the 336 markets that ARE the bracket grid on the page whose subject
is what the market thinks right now, it is not.

═══ WHY A REGISTER MAKES THE FIX TRIVIAL ═══

The scanning poll has to discover what exists.  This task does not: the
register already names every market the page will render, as an exact
``(source, market_id, outcome_id)`` triple.  So it asks Gamma for precisely
those condition ids — ``/markets?condition_ids=...``, which does not paginate
and is therefore not subject to the offset cap at all — and updates them.

The whole US Open register is ~420 Polymarket markets, which is 11 batched
requests.  At the 10-minute cadence below that is ~66 Gamma calls an hour
against a limit around 1,000, and it is bounded by the register rather than by
the catalogue: a tournament that ends stops costing anything the moment its
register is retired.

⚠️  "CHEAP" WAS ABOUT THE GAMMA CALLS AND WAS READ AS BEING ABOUT THE TASK
(LAT-P240, #3402).  The 11 requests really are cheap.  What this paragraph did
not say is that ``_write_refreshed_prices`` then issues TWO DATABASE STATEMENTS
PER RETURNED MARKET, and until #3402 both of them probed
``futures_markets.external_id`` without ``source`` — the leading column of the
only index that covers it — so each one scanned the whole index instead of
seeking.  Measured: 994 ms per statement, 190 statements, ``last_duration_ms``
188,869.  This "cheap" task was the largest latency-tolerant consumer on the
2-slot ``background`` queue and held a slot through half the search warmer's
dead time.  The fix is two predicates and it is in the loop with the numbers.

The lesson is kept rather than edited out, because the sentence above is the
sentence a reader will write again: a cost claim about the REMOTE call is not a
cost claim about the TASK, and a per-item loop behind it is where the time goes.

This task NEVER creates a market and never touches identity.  It updates prices
for outcomes the register already pins, which is why it is safe to run at a
cadence the discovery poll could not sustain.

═══ AND IT GRADES THEM, BECAUSE A REFRESH RAIL THAT CANNOT SEE A RESULT IS A
    RAIL THAT FREEZES ON THE LAST WRONG NUMBER (#3868) ═══

Twelve days after the paragraph above was written, `/sport/tennis/atp` was
showing **Carlos Alcaraz at 78% to reach a quarterfinal he had already reached**
and **Novak Djokovic at 58% for one he was out of**, in the same scroll as the
FINISHED list that said so. Two causes, both of them here:

**(a) This rail could not see a result.**  `get_markets_by_conditions` applies a
`closed=false` filter the caller never asked for (its own docstring, measured
under Q499), so the moment a leg settled it stopped coming back — `not_returned`,
no write, and the last LIVE price frozen for good.  Measured 2026-09-07:
Djokovic's leg was refreshed to 0.470 at 08:50Z and settled at the venue to
`["0","1"]` minutes later.  0.470 is what this task would have served forever.
The fetch now passes `include_closed=True` and a closed book with a terminal
`outcomePrices` grades the leg — the same field, the same bars, the same
`resolution_source='api_settlement'` that `_sync_polymarket_resolved_status`
writes when the parent EVENT closes.  **The gap between those two is the whole
bug: a round-by-round ladder settles its children weeks before its event
closes,** so the event-level rail cannot reach them and this one can.

**(b) This rail could not see the row the page renders.**  `_process_event_batch`
writes one Gamma event into this database TWICE — a `polymarket_sub_market` row
per child keyed `external_id = <condition>` with legs `<condition>_yes`/`_no`,
and a `polymarket_event` PARENT ladder row keyed by the Gamma EVENT id with one
leg per child under the BARE `<condition>`.  The register pins the sub-markets;
the writer keyed its outcome lookup on the MARKET's external_id; so it reached
those and nothing else.  The league page renders the parent.  Measured: the
sub-market leg refreshed 2026-09-06 22:33Z, the ladder leg carrying the SAME
condition id last written 2026-08-25 18:17Z.  Thirteen days, one condition, two
rows, and only one of them had a writer.  A second lookup keyed on the OUTCOME's
own external_id now reaches both, and they stop disagreeing.

The side-of-book test is (b)'s hinge and was the quiet half: it read the outcome
NAME and skipped anything that was neither "Yes" nor "No".  Every ladder leg is
named for a player, so even a lookup that found those rows would have written
none of them.  `leg_side` reads the id first for that reason.

WHAT THIS DOES NOT FIX, SAID PLAINLY.  Only tournaments with a committed
register (today: us-open-2026) are reached, because that is what this task is
addressed by.  The general case — ~76,000 served Polymarket futures legs, 56,721
of them over a day stale, measured 2026-09-07 — is the discovery poll's
offset-2000 cap and belongs to #219E's keyset migration, not here.

═══ WHY BOTH RAILS SPEAK THE TERMINAL VOCABULARY (CERT P2, gotcha #53) ═══

Both functions here return a ``terminal`` and both labels are in
``task_verdict.ENFORCED_TASKS``.  CERT C-UX-P139-GRID-REGISTER-1's P2 found them
returning a bare ``verdict`` string that nothing reads: ``verdict_for`` produced
``TaskVerdict(unknown, authoritative=False)``, whose ``blocks_success`` is False,
so a rail that refreshed nothing forever was indistinguishable from a healthy one
in task metrics.

That is this codebase's founding false-GREEN shape and it is especially sharp
here, because the failure is SILENT BY CONSTRUCTION: the page keeps rendering.
A dead refresh rail does not blank the grid — it lets every number on it age,
wearing whatever freshness word the gates give it, which is precisely the
27-hour state this task was written to end.  "It returned" is not "it worked",
so the zero-yield states below are terminals and not log lines.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from app.utils.futures_liveness import LIVE_MARKET_SQL, writable_leg_sql

logger = logging.getLogger(__name__)

#: 🔴 THIS TASK IS A PRICE ASKER AND MUST ASK THE SHARED QUESTION (CERT-452).
#:
#: `futures_price_refresh` and the freshness guard compose
#: `futures_liveness.LIVE_MARKET_SQL`, and a census test asserts that every
#: asker does. That census enumerated a fixed dictionary of six, so it could not
#: discover a seventh — and this task was the seventh. It runs every ten
#: minutes, it neither imported the predicate nor filtered on market status,
#: resolution date, the venue-settled stamp or `is_winner`, so a registered
#: market that the hourly refresher and its guard had both correctly retired
#: kept being fetched here and its settled outcomes overwritten. The bound was
#: real and something was walking round it on a faster cadence.
#:
#: The register pins identities BY ID, which is exactly why this needs saying:
#: an id does not expire, so nothing about being register-pinned makes a market
#: still live. Filtering happens BEFORE the venue fetch, so a retired market
#: also stops costing a Gamma request.
_LIVE_REGISTERED_CONDITIONS_SQL = f"""
    SELECT fm.external_id
      FROM futures_markets fm
     WHERE fm.external_id = ANY(:conditions)
       AND {LIVE_MARKET_SQL}
"""

#: How many condition ids per Gamma request.  See
#: ``PolymarketAPIService.get_markets_by_conditions``.
BATCH_SIZE = 40

#: The bars at which a CLOSED venue book stops being a price and becomes a
#: result.  Not new numbers: they are
#: ``polymarket._sync_polymarket_resolved_status``'s own settlement test, to the
#: digit, so the two rails cannot come to different verdicts about the same
#: condition id.  That task grades a leg the moment its Gamma EVENT closes; this
#: one grades the same leg the moment its own CHILD MARKET closes, which for a
#: round-by-round tournament ladder happens weeks earlier (#3868).
SETTLED_YES_BAR = 0.95
SETTLED_NO_BAR = 0.05

#: A hard ceiling on how many markets one run will refresh, so a mis-sized
#: register can never turn a 10-minute task into a Gamma flood.  Well above the
#: US Open's ~420 and well below anything that would matter.
MAX_MARKETS = 2000

#: What the scheduled run refreshes when nobody named anything.  Named, like the
#: route's own table.
DEFAULT_PRICE_TARGETS: list[tuple[str, str]] = [("us-open", "2026")]
DEFAULT_RESULT_TARGETS: list[tuple[str, str]] = [("us-open", "US Open")]

#: Hub slug -> the ``majors_calendar.yaml`` entry that carries the tournament's
#: OWN dates.
#:
#: ═══ #7010: THE MORNING AFTER, THE HUB GOES BACK TO DAY ONE ═══
#:
#: ``fetch_tournament_results`` defaults to ESPN's CURRENT day, which is what a
#: live tournament wants and is a bug the day after one ends.  Measured on
#: production 2026-09-18, five days after the final: ``/tournaments/us-open``
#: served ``ROUND OF 128 · 47 matches`` dated ``SATURDAY, AUG 29`` as the
#: current round, and ``FINISHED — No match has finished yet`` on a completed
#: 128-draw Slam.  Four reads across three ``generated_at`` values, identical
#: every time: this was the steady state, not a regeneration window.
#:
#: ONE CAUSE, BOTH HALVES.  Today's board carries no US Open competition, so
#: ``order_of_play`` is empty; ``DECIDED`` is the slate's only route out
#: (``tournament_slate``, "this is the ONLY route to DECIDED"), so all 96
#: main-draw register fixtures are re-served as the current card — and
#: ``build_results`` sees no finished match to put under them.
#:
#: THE VENUE STILL HAS IT.  Read venue-side before this was written (notice 26):
#: ``dates=20260913`` returns the event with 625 competitions on BOTH tours;
#: ``dates=20260918`` returns no US Open at all.  A date INSIDE the window
#: returns the whole tournament rather than that day's slice, which is why one
#: extra request recovers the entire board rather than a final's worth of it.
#:
#: The dates themselves stay in the calendar — one file owns when a major runs,
#: and this map holds no date at all.  The mapping is WRITTEN DOWN rather than
#: derived, for the reason the calendar itself gives beside ``us-open-tennis``:
#: golf has a US Open too, and a slug match is exactly the inference that file
#: refuses to make.  A slug with no entry here keeps today's answer and says so.
RESULT_CALENDAR_SLUGS: dict[str, str] = {"us-open": "us-open-tennis-2026"}


def settled_yes_probability(market: Any) -> float | None:
    """``1.0``/``0.0`` when the venue has SETTLED this book, else ``None``.

    #3868.  A ``closed`` child market is not a stale price, it is an answer, and
    the two have to be told apart before anything is written — which is why this
    returns ``None`` rather than a number for the third case.

    THE THIRD CASE IS THE POINT.  A book that is closed but whose ``outcomePrices``
    sit between the bars has closed without telling us who won: void, mis-settled,
    or caught mid-settlement.  Grading it would be inventing a result, and pricing
    it would be quoting a dead book, so this rail does neither and the caller
    counts it (gotcha #53 — the zero-yield case has to be loud, not absent).
    """
    if not getattr(market, "closed", False):
        return None
    prices = getattr(market, "outcome_prices", None) or []
    if not prices:
        return None
    try:
        yes = float(prices[0])
    except (TypeError, ValueError):
        return None
    if yes >= SETTLED_YES_BAR:
        return 1.0
    if yes <= SETTLED_NO_BAR:
        return 0.0
    return None


def leg_side(outcome_name: str | None, outcome_external_id: str | None, condition_id: str) -> str | None:
    """``"yes"``, ``"no"`` or ``None`` — which side of the book this row is.

    READ FROM THE ID FIRST, AND THAT IS THE #3868 FIX (see the caller).  The
    original writer read the side off the outcome NAME and skipped anything that
    was neither "Yes" nor "No".  That was correct for the sub-market rows the
    register pins, whose legs really are named ``Yes``/``No`` — and it silently
    skipped every row of the LADDER copy of the same condition, whose legs are
    named ``Carlos Alcaraz`` and ``Novak Djokovic``.

    The id says the side without ambiguity, because the id is what the ingest
    wrote it as: ``_parent_outcome_data`` stores a ladder leg under the BARE
    condition id and that leg is by construction the Yes side of that child
    book (P(this player advances)), while ``_process_event_batch`` stores the
    sub-market's two legs under ``…_yes`` and ``…_no``.  The name test is kept
    as the fallback so no row this function used to resolve stops resolving.
    """
    ext = (outcome_external_id or "").strip()
    if ext:
        if ext.endswith("_no"):
            return "no"
        if ext.endswith("_yes") or ext == condition_id:
            return "yes"
    label = (outcome_name or "").strip().lower()
    if label in ("yes", "no"):
        return label
    return None


def registered_polymarket_conditions(register: dict[str, Any]) -> dict[str, list[int]]:
    """``condition_id -> [outcome_id, ...]`` for every Polymarket identity pinned.

    Walks players, matchups AND reaches.  Matchups are included even though
    their identities live under ``sides`` — the slate is the other half of the
    page and it has the same problem for the same reason.
    """
    out: dict[str, list[int]] = {}

    def add(block: Any) -> None:
        if not isinstance(block, dict) or block.get("source") != "polymarket":
            return
        condition = block.get("market_external_id")
        if not isinstance(condition, str) or not condition:
            return
        ids = out.setdefault(condition, [])
        if isinstance(block.get("outcome_id"), int):
            ids.append(block["outcome_id"])
        for side in (block.get("sides") or {}).values():
            if isinstance(side, dict) and isinstance(side.get("outcome_id"), int):
                ids.append(side["outcome_id"])

    for player in register.get("players") or []:
        if isinstance(player, dict):
            for block in player.get("sources") or []:
                add(block)
    for matchup in register.get("matchups") or []:
        if isinstance(matchup, dict):
            for block in matchup.get("sources") or []:
                add(block)
    for reach in register.get("reaches") or []:
        if isinstance(reach, dict):
            for block in reach.get("sources") or []:
                add(block)
    return out


async def _refresh_registered_tournament_prices(
    tournaments: list[tuple[str, str]] | None = None,
) -> dict[str, Any]:
    """Re-price every Polymarket market a committed tournament register pins."""
    from app.services.polymarket_api import PolymarketAPIService
    from app.utils.tournament_register import load_register

    # Explicit, like the route's own table: a register is refreshed because
    # somebody said so, never because a file appeared in a directory.
    #
    # `is None` and not `or`: an explicitly EMPTY list means "refresh nothing"
    # and must reach the `no_work` terminal below. Falling back to the default
    # on `[]` would turn a deliberate no-op into a full run, and — worse for
    # this file — make the terminal unreachable and its guard untestable.
    targets = DEFAULT_PRICE_TARGETS if tournaments is None else tournaments
    if not targets:
        return _refresh_terminal(
            {"tournaments": 0, "conditions_requested": 0, "errors": []},
            "no_work",
            "no_targets",
        )

    stats: dict[str, Any] = {
        "tournaments": 0,
        "conditions_requested": 0,
        "markets_returned": 0,
        # UX-P158: how many markets had their venue volume figure written down
        # with a stamp. Counted separately from `outcomes_updated` because the
        # two can diverge — an unpriced market is observed but not re-priced —
        # and a rail whose volume writes silently stopped would otherwise look
        # exactly like one whose prices are fine.
        "volume_observed": 0,
        "outcomes_updated": 0,
        "snapshots_written": 0,
        "unpriced": 0,
        "not_returned": 0,
        # #3868. Counted apart from `outcomes_updated` because they are a
        # different KIND of write and a run can do a lot of one and none of the
        # other: `legs_settled` are rows this pass graded from a closed venue
        # book, and after grading they leave the population for good.
        "legs_settled": 0,
        # #6919. Legs graded vs MARKET ROWS closed, and they differ on purpose:
        # one condition can be two rows here (the ladder copy and the
        # sub-market copy) and each row has two legs. The row count is the one
        # a reader feels, because `status` is what decides whether we are still
        # asking the question.
        #
        # ASSIGNED FROM `rowcount`, never incremented per settled book: this
        # counter is what the #6919 after-check reads as proof the fix is live
        # and working, so it says how many rows CHANGED and nothing else. Its
        # first cut counted intentions and reported 4 on a pass that moved one
        # row — see the deferred close in `_write_refreshed_prices`.
        "markets_settled": 0,
        # #6598 / CERT-3182. Rows whose `rank` this pass corrected after moving
        # the price it is derived from. Reported unconditionally: the statement
        # is a no-op on a field that was already right, so "0" is the healthy
        # reading and its absence is the one that means the wiring is gone.
        "ranks_rederived": 0,
        # A closed book that named no winner — see `settled_yes_probability`.
        # Reported rather than dropped: a register whose legs all close without
        # a result is a venue change, and it would otherwise look like a quiet
        # run that simply had nothing to grade (gotcha #53).
        "closed_without_result": 0,
        # Rows reached only through their OWN external_id — the ladder copy the
        # market-keyed lookup cannot see. Zero here after the US Open ladders
        # are graded is fine; zero on the FIRST run would mean the widened
        # lookup never fired and #3868's user-visible half did not ship.
        "legs_reached_by_condition": 0,
        "errors": [],
    }

    wanted: dict[str, list[int]] = {}
    for tournament, season in targets:
        register = load_register(tournament, season)
        if register is None:
            stats["errors"].append(f"{tournament}-{season}: no readable register")
            continue
        stats["tournaments"] += 1
        for condition, outcome_ids in registered_polymarket_conditions(register).items():
            wanted.setdefault(condition, []).extend(outcome_ids)

    if not stats["tournaments"]:
        # NOT `no_work`. The registers are committed files in this repo; if none
        # of the named ones loads, something is broken here, not absent upstream.
        return _refresh_terminal(stats, "failed", "no_readable_register")

    pinned = sorted(wanted)[:MAX_MARKETS]
    # CERT-452: the register says which markets the page renders, not which are
    # still worth asking a venue about. Drop the settled ones here, before the
    # fetch, through the SAME predicate the hourly refresher and the freshness
    # guard compose — a second answer to "can this be priced" is a second answer.
    conditions = await _live_conditions(pinned)
    stats["conditions_requested"] = len(conditions)
    # Reported, not merely dropped: a rail that quietly shrinks its own input is
    # one whose "refreshed everything" cannot be checked against anything.
    stats["conditions_settled"] = len(pinned) - len(conditions)
    if not conditions and pinned:
        # Every pinned identity is retired. Authoritative UNKNOWN, not failed
        # and never green: a finished tournament whose register is still
        # committed is the honest case, and it has nothing to refresh.
        return _refresh_terminal(stats, "no_work", "all_registered_markets_settled")
    if not conditions:
        # A loaded register that pins no Polymarket identity. Authoritative
        # UNKNOWN rather than failed — a retired tournament is the honest case —
        # but never GREEN: a refresh rail that refreshed nothing has not proved
        # it can refresh anything.
        return _refresh_terminal(stats, "no_work", "no_registered_polymarket_identities")

    service = PolymarketAPIService()
    try:
        markets = await service.get_markets_by_conditions(
            # #3868: `include_closed` — WITHOUT IT THIS RAIL CANNOT SEE A RESULT.
            # `/markets?condition_ids=…` applies a `closed=false` filter the
            # caller never asked for (that method's own docstring, measured
            # under Q499), so the instant a leg settles it stops coming back at
            # all: it lands in `not_returned`, nothing is written, and the last
            # LIVE price freezes on the page for good. Measured on production
            # 2026-09-07 09:3xZ, Djokovic's "advance to the Quarterfinals" leg
            # was refreshed at 08:50Z to 0.470 and then settled at the venue to
            # `["0","1"]` — the 0.470 was the last thing this task would ever
            # have written to it.
            #
            # It costs one extra request per batch of 40 and buys the settlement
            # branch below. On the US Open register that is ~10 more Gamma calls
            # per run against the ~1,000/hr ceiling the module docstring cites.
            conditions,
            batch_size=BATCH_SIZE,
            include_closed=True,
        )
    except Exception as exc:  # noqa: BLE001 — reported, never swallowed
        stats["errors"].append(f"gamma fetch failed: {exc}")
        return _refresh_terminal(stats, "failed", "fetch_failed")

    stats["markets_returned"] = len(markets)
    stats["not_returned"] = len(conditions) - len({m.condition_id for m in markets})

    if not markets:
        # We asked for identities the register pins BY ID and Gamma returned
        # none of them. Either the ids are wrong or the rail cannot reach Gamma;
        # both are ours to fix and neither is a run that worked.
        return _refresh_terminal(stats, "failed", "no_markets_returned")

    now = datetime.now(timezone.utc)
    try:
        await _write_refreshed_prices(markets, stats, now=now)
    except Exception as exc:  # noqa: BLE001
        # A WRITE THAT FAILED IS THE QUIETEST FAILURE THIS RAIL HAS. The fetch
        # worked, the numbers are in memory, and nothing reaches the page. It is
        # caught here rather than left to raise so the summary itself carries the
        # terminal — task metrics then distinguish "could not write" from "wrote
        # nothing to write" instead of showing one bare exception string.
        logger.exception("tournament price refresh: write failed")
        stats["errors"].append(f"write failed: {exc}")
        return _refresh_terminal(stats, "failed", "write_failed")

    if not stats["snapshots_written"]:
        # Markets came back and not one price landed. The grid keeps rendering
        # and every number on it keeps ageing — the exact invisible failure.
        return _refresh_terminal(stats, "failed", "no_prices_written")

    return _refresh_terminal(stats, "complete", "prices_written")


async def _live_conditions(conditions: list[str]) -> list[str]:
    """The subset of these Polymarket condition ids still worth pricing.

    Order-preserving and NULL-safe by construction: it returns the members of
    the input that the shared predicate admits, so a condition with no
    `futures_markets` row at all is simply absent rather than silently kept.

    FAILS OPEN on a read error, deliberately. If the database cannot answer
    "which of these are live", the honest fallback is to refresh everything and
    let `_write_prices`' per-outcome `is_winner` refusal hold the line — a
    filter that fails CLOSED would blank the grid on a transient error, which is
    the loud version of the silent staleness this whole task exists to end.
    """
    if not conditions:
        return []
    from sqlalchemy import text

    from app.tasks.base import get_task_session

    try:
        async with get_task_session() as session:
            rows = (
                await session.execute(
                    text(_LIVE_REGISTERED_CONDITIONS_SQL),
                    {"conditions": list(conditions)},
                )
            ).all()
    except Exception:  # noqa: BLE001 — see the fail-open note above
        logger.exception(
            "tournament price refresh: liveness filter failed, refreshing all "
            "%d pinned conditions",
            len(conditions),
        )
        return list(conditions)
    live = {r[0] for r in rows}
    return [c for c in conditions if c in live]


def _refresh_terminal(stats: dict[str, Any], terminal: str, reason: str) -> dict[str, Any]:
    """Stamp the contract fields and log once. Every return goes through here."""
    stats["terminal"] = terminal
    stats["reason"] = reason
    logger.info("tournament price refresh: %s", stats)
    return stats


async def _write_refreshed_prices(
    markets: list[Any], stats: dict[str, Any], *, now: datetime
) -> None:
    """Update every registered outcome these markets price, and snapshot it."""
    from sqlalchemy import select, text, update
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    from app.models import FuturesMarket, FuturesOddsSnapshot, FuturesOutcome
    from app.tasks.base import get_task_session
    from app.tasks.polymarket import (
        _resolve_market_probability,
        complementary_book,
    )
    from app.utils.futures_rank import rerank_market_fields_stmt  # #6598
    from app.utils.odds_math import probability_to_american
    from app.utils.winner_field_coherence import DUPLICATE_CONDITION_LEG_SQL

    # #6919: conditions whose book this pass read as SETTLED. Collected in the
    # loop, spent once after it — see the deferred close at the bottom.
    settled_conditions: list[str] = []

    # #6598 / CERT-3182: legs this pass gave a LIVE price to. Collected here
    # rather than the market ids because this loop never learns one — it walks
    # Gamma CONDITIONS, and #3868's whole finding is that a condition's legs sit
    # on two different market rows. The ids are resolved to their markets once,
    # after the loop.
    #
    # LIVE ONLY, and the exclusion is the settled-board exemption the helper's
    # header states rather than a shortcut. A leg this pass GRADED is written
    # 1.0 or 0.0 by `settled_yes_probability`, and a board whose last write was
    # its settlement is a record of how it finished; #6325 refused to renumber
    # one and that refusal holds here. A ladder with live siblings still
    # re-derives — an eliminated player really is behind everyone still playing,
    # which is what the page already shows by sorting on the price.
    live_priced_outcome_ids: list[int] = []

    async with get_task_session() as session:
        for market in markets:
            # ── BOTH LOOKUPS BELOW SUPPLY `source`, AND THAT IS A PLAN FIX, NOT
            # A NARROWING (LAT-P240, #3402).
            #
            # The only index covering `external_id` is the composite
            # `uq_futures_source_external (source, external_id)`. A probe that
            # omits the LEADING column still uses that index — Postgres will
            # happily choose it — but it cannot SEEK. It scans the whole thing.
            # Measured on production, same row, same plan shape:
            #
            #     WHERE external_id = :cid                    5,458.591 ms   31,160 blocks read
            #     WHERE source = 'polymarket' AND external_id  = :cid
            #                                                     0.059 ms        2 blocks read
            #
            # This loop issues TWO such statements per market. The run that
            # measured it returned 95 markets — 190 statements — and took
            # `last_duration_ms` 188,869, i.e. 994 ms each. The arithmetic
            # closes, and it is the whole of this task's cost: the 11 batched
            # Gamma calls the docstring calls cheap really are cheap.
            #
            # 🔴 WHY IT MATTERS SOMEWHERE ELSE ENTIRELY. `background` is a
            # 2-slot queue measured ~1.9x oversubscribed, and this task was
            # holding a slot through **50.7% of the search warmer's dead time**
            # — attributed, not inferred, by overlaying `recent_durations_at` +
            # `recent_durations_ms` occupancy intervals on the warmer ring's own
            # holes (654s of 1,290 dead seconds; present in all four of the
            # longest). The warmed typeahead head is entirely cold 42% of the
            # time because of runs like this one. That is why a plan fix in a
            # tournament rail is filed under a search ship.
            #
            # NOT A NARROWING, measured rather than argued: every `0x…`
            # `external_id` in `futures_markets` is Polymarket's —
            # `GROUP BY source` over the 518,851 of them returns exactly one
            # row, `polymarket`. It is also true by construction, because the
            # register these condition ids come from is
            # `registered_polymarket_conditions`. The predicate cannot exclude a
            # row the old form would have matched.
            #
            # The sibling rail beside this one in the beat schedule,
            # `refresh_stale_futures_prices`, is pinned to `heavy` with the note
            # that a multi-minute beat "does not share [background], it closes
            # it". This task was that beat and did not know.
            # ── THE VOLUME OBSERVATION TRAVELS WITH THE PRICE TOO (UX-P158).
            #
            # Q428 taught this rail to write the BOOK alongside the price it
            # produced, for the reason its own comment gives: two observations
            # must not wear one timestamp. The venue's 24h volume is the third
            # thing in that same Gamma response and it was still being thrown
            # away, so the illiquidity mark's "did anybody trade it" half was
            # reading a column the hourly scan last wrote on 2026-08-25 —
            # measured 83 hours stale on every one of the 336 US Open ladder
            # rows, against a price this task had refreshed nine minutes
            # earlier. A fact graded from those two together is not one
            # observation, and `market_liquidity` now refuses it as such.
            #
            # `volume_updated_at` is what makes the NULL readable. UX-P158
            # measured, on 328 markets against the Polymarket trade tape with
            # no exceptions, that Gamma OMITS a zero-valued `volume24hr` rather
            # than serving it — so "asked at 05:10, no figure came back" is a
            # measured zero, while "never asked" is nothing at all. The stamp
            # is the only thing that separates them, which is why it is written
            # unconditionally and the figure is written NULL-preserving.
            #
            # Written for every market Gamma RETURNED, including one this task
            # cannot price: whether we could resolve a probability is a fact
            # about the book, and how much of it traded is a fact about the
            # market. Skipping the unpriced ones would leave the stalest rows
            # on the surface permanently unreadable.
            await session.execute(
                update(FuturesMarket)
                .where(
                    # LAT-P240: leading column first. See the block at the top
                    # of this loop — without it this UPDATE scans the index.
                    FuturesMarket.source == "polymarket",
                    FuturesMarket.external_id == market.condition_id,
                )
                .values(
                    volume_24h=(
                        int(market.volume_24h)
                        if market.volume_24h is not None
                        else None
                    ),
                    volume_updated_at=now,
                )
            )
            stats["volume_observed"] += 1

            # ── #3868: SETTLEMENT IS READ BEFORE PRICE, BECAUSE A CLOSED BOOK IS
            # NOT A PRICE. `_resolve_market_probability` is a book reader — bid,
            # ask, midpoint, last trade — and on a settled market those are the
            # residue of trading that has stopped, not an opinion about anything.
            # The venue's own `outcomePrices` is the answer, and it is the same
            # field, read at the same bars, that `_sync_polymarket_resolved_status`
            # grades on when the parent EVENT closes.
            settled = settled_yes_probability(market)
            if settled is None and getattr(market, "closed", False):
                stats["closed_without_result"] += 1
                continue

            # ── #6919: THE ROW THE READER MEETS SAYS WHETHER THE QUESTION IS
            # STILL BEING ASKED, AND UNTIL NOW THIS RAIL NEVER WROTE IT.
            #
            # Below, a settled book grades the legs `api_settlement` — tier-3,
            # the venue's own answer. The market row was left `status='open'`
            # with `settled_at IS NULL`, so the same market both had a winner
            # and was still open: 18 markets / 34 legs in that shape on
            # production 2026-09-18, 11 of them linked to an event and so on a
            # game page, presented as a live question under a result we had
            # already written.
            #
            # It is this rail's job and not the poll's. `submarket_is_open`
            # (#6734) is the other status writer and it lives only in
            # `_process_event_batch`, whose population is the newest 2,000
            # active+unclosed Gamma events by `startDate` (#219E's offset cap).
            # Replayed against the venue that morning, that window reached back
            # ~11 hours and excluded 218 of the 226 Gamma events on our live
            # slate; for those the only other settlement rail is a CLOB
            # `market_resolved` websocket push, which has no reconciliation.
            # This rail addresses markets BY CONDITION ID, so it is the one door
            # that does not care how long ago the event was listed.
            #
            # THE GATE IS NOT WIDENED: `settled_yes_probability` is the same
            # decision that gates the grade, unchanged. An open book falls
            # through here untouched, and a closed book between the bars already
            # `continue`d above into `closed_without_result` — we write down the
            # settlement we are acting on, and never one we had to infer.
            #
            # `settled_at` is COALESCEd, the LINKLOSS-02 idiom
            # `_process_event_batch` uses for the same pair of columns: status
            # and settled_at are one fact, and a re-run must not restamp a
            # settlement that already has a date.
            #
            # ── AMENDED: THE CLOSE IS DEFERRED AND KEYED THROUGH THE LEGS,
            # BECAUSE THIS LOOP REACHES MARKET ROWS TWO WAYS AND ONLY ONE OF
            # THEM IS KEYED ON THE CONDITION.
            #
            # The first cut of this write did the UPDATE here, keyed
            # `external_id == market.condition_id`. That is the SUB-MARKET row
            # only. `by_condition` below (#3868) reaches a second, equally real
            # market row — the PARENT LADDER, keyed on the Gamma EVENT id, whose
            # legs carry the bare condition — and for those the UPDATE matched
            # nothing at all. Measured on production in this rail's own
            # 16:08:00–16:08:37Z pass, 2026-09-18: the counter claimed 4 markets
            # settled and exactly ONE row changed, while 60755454 / 60755456 /
            # 60755459 (CPBL, one `Yes` leg each, `external_id` 1004380 /
            # 1004378 / 1004376) had that leg graded `api_settlement` at
            # 16:08:02 and kept `status='open'`, `settled_at NULL`,
            # `updated_at` still 09-11. The defect this write exists to fix,
            # reproduced by the write itself on the arm it could not see.
            #
            # So the condition is REMEMBERED here and the rows are closed once,
            # after the grading loop, addressed through the outcomes that
            # actually carry the condition. Deferred and not merely re-keyed
            # because the guard below has to see THIS pass's grades: run before
            # them, it reads every leg we are about to answer as unanswered.
            if settled is not None:
                settled_conditions.append(market.condition_id)

            probability = settled
            if probability is None:
                probability = _resolve_market_probability(market)
            if probability is None:
                # A placeholder or an untradeable book. Not an error, and not a
                # number: gotcha #19's rule, unchanged.
                stats["unpriced"] += 1
                continue

            rows = (
                await session.execute(
                    select(
                        FuturesOutcome.id,
                        FuturesOutcome.name,
                        FuturesOutcome.external_id,
                    )
                    .join(FuturesMarket, FuturesMarket.id == FuturesOutcome.market_id)
                    .where(
                        # LAT-P240: leading column first, same reason as the
                        # UPDATE above — this SELECT ran 994 ms without it.
                        FuturesMarket.source == "polymarket",
                        FuturesMarket.external_id == market.condition_id,
                        # CERT-452: never overwrite a graded outcome. The
                        # condition filter above is the market-level bound; this
                        # is the per-outcome one, and both are needed — a market
                        # can be live while one of its legs has already resolved,
                        # which is the whole reason the market-level winner
                        # shortcut had to be narrowed in `futures_liveness`.
                        #
                        # `IS NOT TRUE`, never `= FALSE`: `is_winner` is nullable
                        # with `default=False`, so FALSE is ambiguous between
                        # "lost" and "nobody has looked". This is the same
                        # refusal `futures_price_refresh._write_prices` makes,
                        # said the same way.
                        FuturesOutcome.is_winner.is_not(True),
                    )
                )
            ).all()

            # ── #3868: THE SAME CONDITION IS IN THIS DATABASE TWICE, AND THE
            # LOOKUP ABOVE CAN ONLY SEE ONE OF THEM.
            #
            # `_process_event_batch` writes a Gamma event two ways at once: a
            # SUB-MARKET row per child, keyed `external_id = <condition>` with
            # legs `<condition>_yes` / `<condition>_no`, and a PARENT ladder row
            # keyed by the Gamma EVENT id with one leg per child under the BARE
            # `<condition>`. The register pins the sub-markets, so the lookup
            # above — which keys on the MARKET's external_id — reaches those and
            # nothing else.
            #
            # `/sport/tennis/atp` renders the parent. Measured on production
            # 2026-09-07 (#3868): sub-market leg `…3d06…_yes` (Alcaraz) refreshed
            # 2026-09-06 22:33Z; the ladder leg `…3d06…` carrying the SAME
            # condition, last written 2026-08-25 18:17Z and reading 78% for a
            # quarterfinal he had already reached. Thirteen days, one condition
            # id, two rows, and only one of them had a writer.
            #
            # Keyed on the outcome's OWN external_id, which is an indexed exact
            # IN (`ix_futures_outcomes_external_id`) and not a `regexp_replace`
            # — LAT-P240's lesson is that the probe in this loop must seek.
            #
            # `DUPLICATE_CONDITION_LEG_SQL` is Q487's rule and it is exactly
            # right here, unchanged: it excludes a `_yes`/`_no` leg only when
            # the BARE row sits on the SAME market, which is the duplicate case.
            # Our two rows are on DIFFERENT markets and are both legitimate, so
            # both are written and they stop disagreeing.
            by_condition = (
                await session.execute(
                    text(
                        f"""
                        SELECT fo.id, fo.name, fo.external_id
                          FROM futures_outcomes fo
                         WHERE fo.external_id IN (:cid, :cid_yes, :cid_no)
                           AND {writable_leg_sql("fo")}
                           AND {DUPLICATE_CONDITION_LEG_SQL}
                        """
                    ),
                    {
                        "cid": market.condition_id,
                        "cid_yes": f"{market.condition_id}_yes",
                        "cid_no": f"{market.condition_id}_no",
                    },
                )
            ).all()

            # Merged by outcome id, so a row both lookups return is written once.
            merged: dict[int, tuple[str | None, str | None]] = {
                r[0]: (r[1], r[2]) for r in rows
            }
            for oid, name, ext in by_condition:
                if oid not in merged:
                    stats["legs_reached_by_condition"] += 1
                merged[oid] = (name, ext)

            if not merged:
                continue

            for outcome_id, (name, outcome_ext) in merged.items():
                # WHICH SIDE OF THE BOOK THIS ROW IS. The YES side carries the
                # market's resolved probability; the NO side is its complement.
                # Never from position: `outcome_prices[1]` and "the row called
                # No" are the same thing only when the source ordered them the
                # way we assumed, and this task has no business re-deriving an
                # ordering the ingest already pinned.
                #
                # #3868 reads the ID before the name — see `leg_side`. A ladder
                # leg is named "Carlos Alcaraz", and the name test alone skipped
                # every one of them.
                label = leg_side(name, outcome_ext, market.condition_id)
                if label == "yes":
                    value = probability
                    bid, ask, last = (
                        market.best_bid,
                        market.best_ask,
                        market.last_trade_price,
                    )
                elif label == "no":
                    value = 1.0 - probability
                    # The two tokens of a binary share ONE book, so the No side
                    # is the same orders addressed from the other token — an
                    # identity, not an estimate. Shared rather than restated:
                    # CAL-P095 measured 493,415 Under/No legs carrying no book
                    # at all precisely because a writer named these columns on
                    # one leg and not the other.
                    bid, ask, last = complementary_book(
                        market.best_bid, market.best_ask, market.last_trade_price
                    )
                else:
                    continue

                value = max(0.0, min(1.0, value))

                # #3868: a settled book grades the leg as well as pricing it.
                # `resolution_source='api_settlement'` is the SAME grade
                # `_sync_polymarket_resolved_status` writes from the same field
                # at the same bars — this is that write reaching a leg whose
                # parent event has not closed and, for a round-by-round ladder,
                # will not close for weeks. A graded row leaves this rail's
                # population for good (both lookups refuse it), so the grade is
                # written once and never revised here.
                graded: dict[str, Any] = {}
                if settled is not None:
                    graded = {
                        "is_winner": value >= 0.5,
                        "resolution_source": "api_settlement",
                    }
                    stats["legs_settled"] += 1

                await session.execute(
                    update(FuturesOutcome)
                    .where(FuturesOutcome.id == outcome_id)
                    .values(
                        current_probability=value,
                        current_american_odds=probability_to_american(value),
                        **graded,
                        # Q428: THE BOOK TRAVELS WITH THE PRICE IT PRODUCED.
                        # Without these two columns this rail moved the number
                        # every ten minutes and left the book frozen at whatever
                        # the last full poll wrote, so 181 of 328 US Open ladder
                        # rows held a probability sitting OUTSIDE their own
                        # stored [bid, ask] — not a stale book but two different
                        # observations wearing one timestamp. Every book-based
                        # predicate downstream (is_fabricated_midpoint #1578,
                        # classify_fabricated_book UX-P011, the wide-spread
                        # exclusion in precompute_calibration) was therefore
                        # judging the wrong book on this surface, and the site
                        # had no signal with which to mark an illiquid cell as
                        # illiquid — which is what Alex's 2026-08-28 ruling asks
                        # for. NULL-preserving: a market that arrives with no
                        # book leaves with no book, never with a fabricated 0
                        # that would read downstream as a real, empty one.
                        current_yes_bid=bid,
                        current_yes_ask=ask,
                        last_updated=now,
                    )
                )
                stats["outcomes_updated"] += 1
                if settled is None:
                    live_priced_outcome_ids.append(outcome_id)

                # The snapshot is what `price_observed_at` reads, so a refresh
                # that updated the outcome and wrote no snapshot would move the
                # price while leaving the page's freshness verdict at 27 hours
                # — a number that changed without admitting it had.
                #
                # Q428: and a snapshot without its book is a permanent one. The
                # outcome row is at least overwritten by the next full poll;
                # 34,638 ladder snapshots written in 12 hours carry a NULL book
                # and that history cannot be reconstructed from anywhere.
                await session.execute(
                    pg_insert(FuturesOddsSnapshot).values(
                        outcome_id=outcome_id,
                        bookmaker="polymarket",
                        probability=value,
                        american_odds=probability_to_american(value),
                        yes_bid=bid,
                        yes_ask=ask,
                        last_price=last,
                        captured_at=now,
                    )
                )
                stats["snapshots_written"] += 1

        # ── #6598 / CERT-3182. Every leg this pass re-priced moved the value
        # `rank` is derived from, and this rail never wrote `rank` at all — so a
        # price CROSSING here left the ladder ordered by the last full poll's
        # opinion. One statement for every market touched (`PARTITION BY`),
        # before the close and inside the same transaction as the prices.
        if live_priced_outcome_ids:
            market_ids = [
                r[0]
                for r in (
                    await session.execute(
                        select(FuturesOutcome.market_id)
                        .where(FuturesOutcome.id.in_(live_priced_outcome_ids))
                        .distinct()
                    )
                ).all()
            ]
            stats["ranks_rederived"] = (
                await session.execute(rerank_market_fields_stmt(market_ids))
            ).rowcount

        # ── #6919, THE DEFERRED CLOSE. One statement, after every leg this
        # pass answers has been written.
        #
        # ADDRESSED THROUGH THE LEGS, NOT THE MARKET KEY. A condition reaches
        # us as up to three outcome `external_id`s — the bare `<condition>` on
        # a parent ladder row, and `<condition>_yes` / `<condition>_no` on the
        # sub-market row — and the two live on DIFFERENT market rows. Keying
        # the close on `futures_markets.external_id` saw only the second, which
        # is how a fix for "a settled market is served as an open question"
        # shipped and left 10 of them open (measured, production, 16:35Z
        # 2026-09-18; the other 39 in that residue are arm one's and this
        # statement reaches them by the same route).
        #
        # 🛑 THE `resolution_source IS NULL` GUARD IS THE WHOLE SAFETY OF THIS
        # STATEMENT AND IT IS LOAD-BEARING, MEASURED, NOT ARGUED. A parent
        # ladder owns one leg per child, so "this market owns a leg we just
        # graded" is true of a US Open draw the moment ONE player's condition
        # settles. Without the guard this UPDATE would close 389 open markets
        # on production, 322 of them tier 1–3 — every live tournament ladder on
        # a marquee surface, retired mid-event. With it, a market closes only
        # when no leg it owns is still unanswered. The `EXISTS` beside it is
        # not decoration: `NOT EXISTS` is vacuously true for a legless row.
        #
        # `status <> 'resolved'` is what makes `rowcount` honest, and honesty
        # here is the point — the first cut incremented the counter once per
        # settled book with no regard for whether a row moved, so the rail
        # reported `markets_settled: 4` on a pass that changed ONE row. A
        # counter that cannot be wrong about its own write is the cheapest
        # liveness oracle we have; one that counts intentions is worse than
        # none, because an after-check reads it as proof.
        if settled_conditions:
            leg_keys = [
                key
                for cid in settled_conditions
                for key in (cid, f"{cid}_yes", f"{cid}_no")
            ]
            closed = await session.execute(
                text(
                    """
                    UPDATE futures_markets fm
                       SET status = 'resolved',
                           settled_at = COALESCE(fm.settled_at, :now),
                           updated_at = :now
                     WHERE fm.source = 'polymarket'
                       AND fm.status <> 'resolved'
                       AND EXISTS (SELECT 1 FROM futures_outcomes fo
                                    WHERE fo.market_id = fm.id
                                      AND fo.external_id = ANY(:leg_keys))
                       AND NOT EXISTS (SELECT 1 FROM futures_outcomes fo2
                                        WHERE fo2.market_id = fm.id
                                          AND fo2.resolution_source IS NULL)
                       AND EXISTS (SELECT 1 FROM futures_outcomes fo3
                                    WHERE fo3.market_id = fm.id)
                    """
                ),
                {"now": now, "leg_keys": leg_keys},
            )
            stats["markets_settled"] = closed.rowcount

        await session.commit()


# ---------------------------------------------------------------------------
# ESPN results sync (UX-P139, Alex's item 9)
# ---------------------------------------------------------------------------

#: How long a cached results payload stays servable.  Generous relative to the
#: 3-minute sync so one missed run does not blank the section; a genuinely dead
#: task lets it expire, which is the honest outcome — an empty section with a
#: stated reason beats an hour-old result presented as current.
RESULTS_TTL_SECONDS = 900
RESULTS_PREFIX = "bainluck:tournament-results:"

#: THE LAST SCOREBOARD WE ARE SURE OF (#3304).
#:
#: The primary key above expiring does not degrade the slate gracefully — it
#: inverts it.  `build_slate`'s only route to `DECIDED` needs the fixture to be
#: NAMED by the scoreboard, so an absent map cannot retire anything, and the
#: pinned-fixture clock exemption (CERT-544) then prints the entire decided main
#: draw as "what is on".  Measured on production 2026-09-05 at 19:04Z during the
#: US Open: 96 rows, 0 in progress, 0 results, 12.2h-old prices, recovering on
#: its own by 19:25Z.  Reproduced exactly with `order_of_play={}`.
#:
#: So the map gets a second, longer-lived copy.  A blip in the fetch now costs
#: an hour-old ANSWER TO "WHO IS ON" rather than the collapse of the question —
#: and it costs nothing in price freshness, because prices come from our own
#: database and never from this key.
#:
#: An hour, not a day, and the asymmetry is the point.  Serving a stale map is
#: only the better error while it is plausibly still true; past that the honest
#: outcome is the one the primary TTL already gives.  Long enough to ride out
#: every outage we have measured, short enough that it can never become the
#: reason a card is wrong for an afternoon.
RESULTS_LAST_GOOD_TTL_SECONDS = 3600
RESULTS_LAST_GOOD_PREFIX = "bainluck:tournament-results-last-good:"


def _board_is_silent(results: dict[str, Any]) -> bool:
    """A CLEAN scoreboard read that named no competition of this tournament.

    THREE EMPTIES WEAR THIS SHAPE AND ONLY ONE OF THEM MEANS "ASK FOR OTHER
    DAYS" (gotcha #53):

    * a tour FAILED — ``errors`` is non-empty, so the half we are missing is
      UNKNOWN, not absent.  Re-asking a different date answers a question
      nobody asked and would publish a partial board as if it were a whole one.
      Every fetch failure appends to ``errors`` in the same ``try``, so this one
      clause covers both tours.
    * the read is clean and the parser counted NO competition of ours — the
      window moved out from under the default ``dates`` (#7010).  This is the
      one this returns True for.
    * the parser counted some — nothing to do.

    Counted on ``competitions`` rather than ``events``, for CERT-532's reason: a
    payload that NAMES the tournament and then carries an empty competitions
    list satisfies "we saw the event" and speaks for not one match.

    A payload with no ``stats`` census at all returns False, deliberately.
    ``parse_results`` always writes one, so this is not a reachable production
    shape; and a missing count is not a count of zero — reading it as "the board
    was silent" would be inventing the very census whose absence is the problem.
    """
    if results.get("errors"):
        return False
    stats = results.get("stats")
    if not isinstance(stats, dict):
        return False
    return not stats.get("competitions")


def _tournament_window_dates(slug: str, now: datetime) -> str | None:
    """ESPN ``dates`` covering this tournament's own window, or ``None``.

    ``None`` — and today's answer stands, whatever it says — when the hub slug
    is not in :data:`RESULT_CALENDAR_SLUGS`, the calendar cannot be read, its
    dates are unusable, or the tournament has NOT STARTED YET.

    The last of those is the clause that matters.  Before the first ball a
    silent board is the honest answer, and re-asking for a window that is still
    in the future would put a draw on the hub days before the tournament earned
    the right to show one.  ``calendar_window_state`` is the house's one clock
    for that question and is read rather than restated.

    A RANGE, not the end date.  The entry carries ``date_confidence:
    approximate``, and a single date is one editing slip away from landing
    outside the tournament — which reads EXACTLY like the defect it is here to
    fix, silently and with every counter green.  A range that overlaps the
    window anywhere returns the whole event, so the slip costs nothing.

    Pure and defensive, like the calendar loader it reads: a bad edit to that
    file returns ``None`` here and never raises inside a beat.
    """
    calendar_slug = RESULT_CALENDAR_SLUGS.get(slug)
    if not calendar_slug:
        return None
    from app.utils.majors_calendar import (
        _as_utc_date,
        calendar_window_state,
        load_calendar,
    )

    entry = next(
        (e for e in load_calendar() if str(e.get("slug")) == calendar_slug), None
    )
    if entry is None:
        return None
    if calendar_window_state(entry, now) == "upcoming":
        return None
    start = _as_utc_date(entry.get("start"))
    end = _as_utc_date(entry.get("end"))
    if start is None or end is None or end < start:
        return None
    return f"{start:%Y%m%d}-{end:%Y%m%d}"


def _is_last_good(results: dict[str, Any]) -> bool:
    """Whether this fetch is fit to become the fallback scoreboard.

    ONLY A CLEAN, COMPLETE, NON-EMPTY READ.  `_sync_tournament_results` writes a
    PARTIAL fetch to the primary key on purpose — half the tours beats none for
    fifteen minutes, and the `errors` list travels with it so the section can
    say so.  A partial read must not be preserved for an hour: the half it is
    missing is a whole tour, and "the WTA draw is not on today" is exactly the
    lie this would tell through a women's final.

    `order_of_play_complete` is the flag `fetch_tournament_results` already
    computes for this question (both tours fetched, the event seen, every
    competition understood, no errors).  It is read here rather than restated —
    and it is checked ALONGSIDE a non-empty map, not instead of it, because
    completeness is a fact about the REQUEST and emptiness is a fact about the
    ANSWER (CERT-548 draws that line for the slate; it holds here too).
    """
    return bool(results.get("order_of_play")) and results.get(
        "order_of_play_complete"
    ) is True


async def _sync_tournament_results(
    tournaments: list[tuple[str, str]] | None = None,
) -> dict[str, Any]:
    """Fetch ESPN's tennis results into Redis for the hub route to read.

    THE FETCH LIVES HERE AND NOT IN THE ROUTE, and that is the point of the
    task rather than an implementation detail.  A third-party call inside
    ``GET /api/tournaments/{slug}`` is the shape the feed's standing rule
    forbids by name: the first request after every cache expiry pays the round
    trip, a slow ESPN becomes a slow page for whoever is unlucky, and the route
    contract tests start making live network calls.

    Three minutes, because a finished match should appear while the reader is
    still on the page, and because two scoreboard requests every three minutes
    is nothing.
    """
    from app.tasks.redis_state import get_async_redis_client

    # Named, like the route's own table: a tournament is synced because
    # somebody wrote it down. `espn_event_name` selects it out of a scoreboard
    # that also carries whatever else is on that week. `is None`, not `or`, for
    # the reason given on the price rail: an explicit `[]` means nothing to sync
    # and has to be able to say so.
    targets = DEFAULT_RESULT_TARGETS if tournaments is None else tournaments

    stats: dict[str, Any] = {"tournaments": 0, "written": 0, "errors": []}
    if not targets:
        return _results_terminal(stats, "no_work", "no_targets")

    for slug, event_name in targets:
        try:
            from app.services.espn_tennis import fetch_tournament_results

            results = await fetch_tournament_results(event_name)
        except Exception as exc:  # noqa: BLE001 — reported, never swallowed
            stats["errors"].append(f"{slug}: {exc}")
            continue

        stats["tournaments"] += 1

        # ── #7010: the board rolled over, so ask for the tournament's OWN days ─
        #
        # Checked BEFORE the error extend below, so whichever read we end up
        # publishing is the one whose errors travel with it.
        if _board_is_silent(results):
            window = _tournament_window_dates(slug, datetime.now(timezone.utc))
            if window is None:
                # LOUD, NOT ABSENT (gotcha #53). A clean read that speaks for no
                # match is how this hub reverts to day one and stays there, and
                # without this line every counter stays green while it does:
                # nothing failed, the request succeeded on an empty day.
                stats["errors"].append(
                    f"{slug}: scoreboard names no competition and no window to re-ask"
                )
            else:
                stats["window_reads"] = stats.get("window_reads", 0) + 1
                try:
                    windowed = await fetch_tournament_results(
                        event_name, dates=window
                    )
                except Exception as exc:  # noqa: BLE001 — reported, never silent
                    stats["errors"].append(f"{slug} window {window}: {exc}")
                else:
                    if _board_is_silent(windowed):
                        # The venue really has nothing under the tournament's own
                        # dates. That is a claim about the SOURCE and it gets
                        # said out loud rather than published as an empty page.
                        stats["errors"].append(
                            f"{slug}: scoreboard silent on its own window {window}"
                        )
                    else:
                        results = windowed
                        stats["window_recovered"] = (
                            stats.get("window_recovered", 0) + 1
                        )

        if results.get("errors"):
            # A partial fetch is written anyway — half the tours is better than
            # none — but the failure travels in the payload so the section can
            # say "we could not reach the feed" rather than "nothing finished".
            stats["errors"].extend(f"{slug}: {e}" for e in results["errors"])

        try:
            encoded = json.dumps(results, default=str)
            await get_async_redis_client().setex(
                f"{RESULTS_PREFIX}{slug}",
                RESULTS_TTL_SECONDS,
                encoded,
            )
            stats["written"] += 1
            # The fallback copy is written from the SAME bytes, in the same
            # try, and only for a read that earned it (`_is_last_good`).  A
            # separate encode could drift the two apart; a separate try could
            # leave the hour-long copy alive while the fifteen-minute one it is
            # supposed to shadow was never written.
            if _is_last_good(results):
                await get_async_redis_client().setex(
                    f"{RESULTS_LAST_GOOD_PREFIX}{slug}",
                    RESULTS_LAST_GOOD_TTL_SECONDS,
                    encoded,
                )
                stats["last_good_written"] = stats.get("last_good_written", 0) + 1
        except Exception as exc:  # noqa: BLE001
            stats["errors"].append(f"{slug} cache write: {exc}")

    # gotcha #53: "it returned" is not "it worked". A run that wrote nothing is
    # a failure even when nothing raised — and it is INVISIBLE from the page,
    # because the results section falls back to its cached payload and then to
    # an honest empty. Neither of those is a signal that the rail is dead.
    if not stats["written"]:
        return _results_terminal(stats, "failed", "nothing_written")
    # A run that wrote SOME tours and errored on others returns `complete` here
    # and is downgraded to PARTIAL by the contract's own damage rule — the
    # `errors` list is the caveat, and it is read rather than restated.
    return _results_terminal(stats, "complete", "results_cached")


def _results_terminal(stats: dict[str, Any], terminal: str, reason: str) -> dict[str, Any]:
    """Stamp the contract fields and log once. Every return goes through here."""
    stats["terminal"] = terminal
    stats["reason"] = reason
    logger.info("tournament results sync: %s", stats)
    return stats
