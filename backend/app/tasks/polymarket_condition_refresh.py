"""Condition-addressed price refresh for the served Polymarket long tail (#3879).

═══ THE DEFECT THIS EXISTS TO FIX ═══

Three rails can re-price a Polymarket futures outcome and each is bounded in a
way that leaves the same population unwritten:

1. ``polymarket._poll_polymarket_markets`` — the discovery scan. Gamma caps
   offset pagination at 2000, so #219E bounded it to a 20-page window ordered
   ``startDate`` newest-first. That fixed *creation*. It means an event is
   re-priced only when the rotating cursor lands inside the newest ~2,000 active
   events; anything older is never revisited.
2. ``futures_price_refresh`` — addressed by tier and traded volume
   (``HIGH_VALUE_SQL``: volume ≥ 10,000, or tier-1-unpriced), plus page-one and
   register identity arms. That is the right bound for a platform sweep and the
   wrong one for a long tail.
3. ``tournament_price_refresh`` — addressed by a committed register. Today that
   is ``us-open-2026`` and nothing else.

So a market that is neither newly-started, nor high-volume, nor page-one, nor
register-pinned is written once at ingest and then never again. Measured on
production 2026-09-07 (#3879), over the Polymarket futures legs the league pages
will actually serve — ``source='polymarket'``, ``status='open'``, resolution date
null or future, bare ``0x…`` condition id, ungraded:

    served                     22,034 markets    76,006 legs
    legs not read in 24h            —            56,721
    legs not read in 7 days         —            37,041

and it is **not only a long-tail problem**: 1,219 TIER-1 markets carry 9,986 of
those day-stale legs.

This rail's own selector adds the shared liveness predicate to that definition,
so the population it sweeps is a SUBSET of the issue's — the graded and the
venue-settled are already out. Measured with the statement below, production
2026-09-08 07:2xZ: **13,746 served markets, 11,693 of them stale beyond 12
hours.** Both figures are quoted because they answer different questions and a
reader comparing them should not have to guess which is which.

═══ WHY IT IS INVISIBLE, WHICH IS WHY THE TERMINAL CARRIES THE CENSUS ═══

A stale ladder renders exactly like a fresh one. There is no blank state and no
error — the numbers simply age, wearing whatever freshness word the gates award
them. #3868 is what it looks like when someone finally reads one aloud: Carlos
Alcaraz at 78% to reach a quarterfinal he had already reached, thirteen days
after the price was written, in the same scroll as the FINISHED list that said
so.

So this rail reports ``served_markets`` and ``stale_markets`` in its own summary
every run (#3879 acceptance 2). Both are computed by the selector it already
runs, over the population it is responsible for. A rail that silently stops does
not go quiet — its own census climbs, and ``terminal``/``reason`` say which of
the zero-yield states it reached (gotcha #53: "it returned" is not "it worked").

═══ HOW IT REACHES THEM: THE ADDRESSING, NOT A BIGGER SCAN ═══

``/markets?condition_ids=a&condition_ids=b`` is the one Gamma read that is not
subject to the offset cap, because it does not paginate at all — it asks for
named markets. Every row in the population above is keyed by exactly such a
name, so this rail asks for them BY ID rather than waiting to be scanned. That
is the same addressing ``tournament_price_refresh`` uses; the only difference is
what supplies the ids, and it is the difference the issue turns on: **a query
over served-and-stale legs instead of a register.**

The durable fix for the *scans* is Gamma's own ``/events/keyset`` (#219E's
follow-up, still owed). It belongs with **#2637** — the same offset cap on the
closed-event scan, already owned — so that both scans migrate under one owner.
This is the interim #3879 names, and it is deliberately not that migration.

⚠️  **THE UNIT OF WORK IS THE WHOLE MARKET, and that is a correctness bound, not
a batching convenience.** A ladder with some legs from today and some from
August is worse than a wholly stale one: the reader has no way to tell that the
two numbers beside each other were observed thirteen days apart, and every
comparison between them is false. So selection is per MARKET (its stalest
ungraded leg decides), and the write path re-prices every leg of the condition
it fetched.

═══ WHAT IT WRITES, AND THE BLAST RADIUS SAID PLAINLY ═══

It writes through ``tournament_price_refresh._write_refreshed_prices``, unchanged
and unforked — the same function, the same book-travels-with-the-price rule
(Q428), the same ``is_winner IS NOT TRUE`` refusal (CERT-452), the same
both-copies-of-the-condition lookup (#3868). Reuse is the point: a second writer
would be a second answer to "what does a Gamma market mean for these rows".

🔴 THAT WRITER'S SIDE-OF-BOOK TEST HAS TO RESOLVE FOR THIS POPULATION OR THIS
RAIL WRITES NOTHING AT ALL, so it was checked rather than assumed — it is the
#3868 quiet half, where a lookup found the rows and ``leg_side`` skipped every
one of them. Measured over the whole condition-keyed open population,
production 2026-09-08 07:3xZ (28,917 ungraded legs):

    suffix `_yes` / `_no`   28,789   (99.6%, the id arm)
    bare condition id           80   (the ladder-parent arm, #3868's fix)
    unresolvable                48   (0.17%, counted by `unpriced`, not silent)

That function also GRADES a leg whose venue book has closed with a terminal
``outcomePrices`` (``≥0.95`` / ``≤0.05``, ``resolution_source='api_settlement'``),
and inheriting that here widens its blast radius from one tournament register to
the whole served Polymarket population. That is deliberate and it is the #3868
lesson generalised — a refresh rail that cannot see a result freezes forever on
the last wrong number, because ``/markets?condition_ids=…`` applies a
``closed=false`` filter the caller never asked for and a settled leg simply stops
coming back. The bars, the field and the ``resolution_source`` are
``_sync_polymarket_resolved_status``'s own, to the digit, so the two rails cannot
come to different verdicts about the same condition id; the only thing that
changes is WHEN a child is reached, which for a round-by-round ladder is weeks
before its parent event closes.

WHAT THIS DOES NOT TOUCH: the discovery scan, the closed-event sync, identity,
``status``, and any market that is not Polymarket-condition-keyed. It never
creates a market and never creates an outcome.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any

#: Condition ids per Gamma request, and the write path itself. Both are shared
#: with the register rail rather than restated: the batch size is a property of
#: the endpoint (a URL with hundreds of repeated query parameters is a 414 in
#: waiting), and a second writer would be a second answer to "what does a Gamma
#: market mean for these rows".
from app.tasks.tournament_price_refresh import BATCH_SIZE
from app.utils.futures_liveness import LIVE_MARKET_SQL

logger = logging.getLogger(__name__)

#: How stale a SERVED leg may get before this rail re-reads its market.
#:
#: #3879's acceptance is 24 hours on tier 1 and 2. This is the *producer*
#: interval and it is deliberately half of that, for the reason
#: ``futures_price_refresh.REGISTERED_REFRESH_MINUTES`` records: a sweep whose
#: window equals the bar it must not breach is always one cycle behind the thing
#: it exists to prevent. At 12 hours a priority market has ~12 hourly runs in
#: which to be reached before it could breach 24.
SERVED_STALE_HOURS = 12

#: Markets re-priced per run.
#:
#: SIZED AGAINST THIS RAIL'S OWN MEASURED POPULATION, not against #3879's
#: headline. The issue counts 22,034 served markets; this selector composes the
#: shared liveness predicate on top of that definition, so it excludes the ones
#: already graded or venue-settled and its population is a subset. Run against
#: production 2026-09-08 07:2xZ, the statement below returned **13,746 served,
#: 11,693 of them stale beyond 12 hours, in 1.83 s**.
#:
#: 1,200 an hour x the 12-hour window is 14,400 >= 13,746, so every served market
#: is reachable inside ONE staleness window — the budget and
#: :data:`SERVED_STALE_HOURS` are one sizing, not two. The priority class (tier 1
#: and 2, plus anything resolving within :data:`IMMINENT_DAYS`) leads the
#: ordering, so #3879's 24-hour acceptance has roughly double the margin the
#: whole-population figure gives.
#:
#: The Gamma cost is small and is not what bounds this: 1,200 markets is 30
#: batches of 40, and ``include_closed`` makes each batch two requests, so ~60
#: requests an hour against the ~1,000/hr ceiling — the same order as the
#: register rail's ~66. What bounds it is the write loop, which issues a handful
#: of indexed statements per market; see ``_TIME_BUDGET_S``.
MARKET_BUDGET = 1_200

#: A market resolving inside this window is priority whatever its tier — an
#: imminent question is the one a reader is most likely to be looking at, and
#: 9,281 legs sit in the ≤2d bucket (#3879's own table).
IMMINENT_DAYS = 2

#: Wall budget for the fetch/write loop, checked BETWEEN batches so a run always
#: stops on a whole market (see the unit-of-work note in the module docstring).
#: Well under the task's 300s soft limit, leaving room for the selector.
_TIME_BUDGET_S = 200.0

#: How many rows the candidate query may return. Above ``MARKET_BUDGET`` so the
#: attempt markers below can be applied to a real surplus rather than to the
#: exact set we were going to take anyway.
CANDIDATE_LIMIT = MARKET_BUDGET * 3

_ATTEMPT_KEY_PREFIX = "bainluck:polymarket_condition_refresh:attempted:"

#: An ATTEMPT marker outlives one run and dies inside the staleness window, so a
#: market whose book cannot be priced — or which Gamma does not return at all,
#: the ``not_returned`` case — cannot sit at the head of a stalest-first
#: ordering forever and starve the tail behind it (the fixed-point failure
#: ``futures_price_refresh`` records under ``_mark_attempted``). Its own prefix,
#: not that rail's: the two sweep overlapping rows on different budgets, and a
#: shared marker would silently make each one's coverage depend on the other's.
_ATTEMPT_TTL_SECONDS = SERVED_STALE_HOURS * 3600


def _attempt_key(market_id: int) -> str:
    return f"{_ATTEMPT_KEY_PREFIX}{market_id}"


#: THE SELECTOR. One statement, and it answers three questions at once so the
#: census in the summary costs no second scan:
#:
#: * which markets to refresh (the rows),
#: * how many served markets are stale right now (``stale_markets``, a window
#:   count taken BEFORE the LIMIT),
#: * how many served markets there are at all (``served_markets``).
#:
#: ``MATERIALIZED`` is load-bearing, for the reason ``futures_price_refresh``'s
#: pool comment gives: PG12+ inlines a single-reference CTE by default, and this
#: CTE is referenced twice — inlining it would run the open-market scan twice.
#:
#: MEASURED, so nobody has to guess later: run against production 2026-09-08
#: 07:2xZ this statement returned in **1.83 s** — 13,746 served, 11,693 stale
#: beyond 12 hours. That is 1.83 s of a 300 s task once an hour. The pool is a
#: BitmapAnd over ``ix_futures_markets_status`` and ``ix_fm_source_created_at``;
#: the row estimate on it is badly off (308 planned against ~13,700 actual, the
#: ``events``-style bloat this database carries), which is another reason the
#: LIMIT is not left to bound the work.
#:
#: The staleness probe is a LATERAL aggregate per candidate rather than a join
#: over ``futures_outcomes``: it rides ``ix_futures_outcomes_market_id`` and
#: touches only this market's legs. ``COALESCE(..., 'epoch')`` makes a leg that
#: has NEVER been written the stalest thing there is, rather than a NULL that
#: MIN() would skip — "nobody has ever read this book" is the strongest possible
#: claim on the budget, not an absence.
#:
#: ``is_winner IS NOT TRUE`` mirrors the write path's own refusal (CERT-452), so
#: a market is not selected on the staleness of a leg the writer would decline.
#: A market with no ungraded legs left produces a NULL ``stalest`` and is
#: excluded by the comparison — there is nothing here to write.
_CANDIDATE_SQL = f"""
    WITH pool AS MATERIALIZED (
        SELECT fm.id,
               fm.external_id,
               (
                    fm.market_tier IN (1, 2)
                 OR (
                        fm.resolution_date IS NOT NULL
                    AND fm.resolution_date <= NOW() + make_interval(days => {IMMINENT_DAYS})
                    )
               ) AS priority
          FROM futures_markets fm
         WHERE fm.source = 'polymarket'
           AND fm.external_id LIKE '0x%'
           AND {LIVE_MARKET_SQL}
    )
    SELECT p.id,
           p.external_id,
           p.priority,
           COUNT(*) OVER () AS stale_markets,
           (SELECT COUNT(*) FROM pool) AS served_markets
      FROM pool p
      JOIN LATERAL (
            SELECT MIN(COALESCE(fo.last_updated, TIMESTAMP WITH TIME ZONE 'epoch')) AS stalest
              FROM futures_outcomes fo
             WHERE fo.market_id = p.id
               AND fo.is_winner IS NOT TRUE
           ) s ON TRUE
     WHERE s.stalest < NOW() - make_interval(hours => :stale_hours)
     ORDER BY p.priority DESC, s.stalest ASC
     LIMIT :limit
"""


def _terminal(stats: dict[str, Any], terminal: str, reason: str) -> dict[str, Any]:
    """Stamp the contract fields and log once. Every return goes through here."""
    stats["terminal"] = terminal
    stats["reason"] = reason
    logger.info("polymarket condition refresh: %s", stats)
    return stats


def _load_attempt_skips(market_ids: list[int]) -> set[int]:
    """Market ids already attempted inside the current staleness window.

    Best-effort. Gotcha #39: only ever through ``get_redis_client()``, which is
    socket-timeout bounded — an unbounded sync client here would freeze the
    async task. A Redis outage degrades this to "no rotation", which is strictly
    better than not running.
    """
    if not market_ids:
        return set()
    try:
        from app.tasks.redis_state import get_redis_client

        rc = get_redis_client(socket_timeout=2.0, socket_connect_timeout=2.0)
        values = rc.mget([_attempt_key(mid) for mid in market_ids])
    except Exception:  # noqa: BLE001 — see the best-effort note above
        return set()
    return {mid for mid, val in zip(market_ids, values) if val}


def _mark_attempted(market_ids: list[int]) -> None:
    """Record an ATTEMPT, not a success — see ``_ATTEMPT_TTL_SECONDS``."""
    if not market_ids:
        return
    try:
        from app.tasks.redis_state import get_redis_client

        rc = get_redis_client(socket_timeout=2.0, socket_connect_timeout=2.0)
        pipe = rc.pipeline()
        for mid in market_ids:
            pipe.setex(_attempt_key(mid), _ATTEMPT_TTL_SECONDS, "1")
        pipe.execute()
    except Exception:  # noqa: BLE001
        pass


async def _select_stale_conditions(
    *, stale_hours: int, limit: int
) -> tuple[list[tuple[int, str]], int, int]:
    """``([(market_id, condition_id), …], stale_markets, served_markets)``.

    Ordered priority-first and then stalest-first, which is the whole starvation
    argument: within a class the row that has waited longest is always next, so
    no member of a class can be passed over twice for the same reason.
    """
    from sqlalchemy import text

    from app.tasks.base import get_task_session

    async with get_task_session() as session:
        rows = (
            await session.execute(
                text(_CANDIDATE_SQL),
                {"stale_hours": stale_hours, "limit": limit},
            )
        ).all()
    if not rows:
        # No stale rows says nothing about how many served rows there are, and
        # the census must not silently read zero on a healthy run. Asked
        # separately only in this branch, where it is one cheap scan a run that
        # is otherwise doing no work at all.
        return [], 0, await _served_market_count()
    return (
        [(r[0], r[1]) for r in rows],
        int(rows[0][3]),
        int(rows[0][4]),
    )


#: The census on its own, for the run that found nothing stale and so has no
#: candidate row to read the window counts off. The SAME population statement as
#: the pool above — composed from the shared predicate, not hand-copied — because
#: a census that describes a different set from the one the rail sweeps is a
#: number that cannot be checked against anything.
_SERVED_COUNT_SQL = f"""
    SELECT COUNT(*)
      FROM futures_markets fm
     WHERE fm.source = 'polymarket'
       AND fm.external_id LIKE '0x%'
       AND {LIVE_MARKET_SQL}
"""


async def _served_market_count() -> int:
    """The served population, for the run that found nothing stale in it.

    ``-1`` on a read error, never ``0``: "I could not count" and "there are
    none" are opposite states, and a census whose failure mode is a plausible
    number is worse than no census.
    """
    from sqlalchemy import text

    from app.tasks.base import get_task_session

    try:
        async with get_task_session() as session:
            return int((await session.execute(text(_SERVED_COUNT_SQL))).scalar() or 0)
    except Exception:  # noqa: BLE001
        logger.exception("polymarket condition refresh: served census failed")
        return -1


async def _refresh_stale_polymarket_conditions(
    *, budget: int = MARKET_BUDGET, stale_hours: int = SERVED_STALE_HOURS
) -> dict[str, Any]:
    """Re-price the served Polymarket markets the three existing rails miss."""
    from app.services.polymarket_api import PolymarketAPIService
    from app.tasks.tournament_price_refresh import _write_refreshed_prices

    stats: dict[str, Any] = {
        # THE CENSUS (#3879 acceptance 2). Reported every run, including the
        # runs that write nothing, because a refresh rail's failure is silent by
        # construction — the page keeps rendering and every number on it ages.
        "served_markets": 0,
        "stale_markets": 0,
        # What this run actually did with that population.
        "candidates": 0,
        "skipped_recent_attempt": 0,
        "conditions_requested": 0,
        "batches": 0,
        "markets_returned": 0,
        "volume_observed": 0,
        "outcomes_updated": 0,
        "snapshots_written": 0,
        "unpriced": 0,
        "not_returned": 0,
        "legs_settled": 0,
        "closed_without_result": 0,
        "legs_reached_by_condition": 0,
        "budget_exhausted": False,
        "wall_exhausted": False,
        "errors": [],
    }

    try:
        candidates, stale_markets, served_markets = await _select_stale_conditions(
            stale_hours=stale_hours, limit=min(CANDIDATE_LIMIT, max(budget, 1) * 3)
        )
    # (This comment is load bearing for `scan_mutation_residue.py` Pass B —
    # without a line here, the closing paren above plus the bare `noqa` below
    # reproduce `typeahead_outcome_arm_mutations:M2-NO-LIMIT`'s replacement
    # literal verbatim and this file reads as mutation residue. Do not delete.)
    except Exception as exc:  # noqa: BLE001 — reported, never swallowed
        logger.exception("polymarket condition refresh: selector failed")
        stats["errors"].append(f"selector failed: {exc}")
        # NOT `no_work`. A selector that could not run has not established that
        # there is nothing to do, and the two must never read the same.
        return _terminal(stats, "failed", "selector_failed")

    stats["served_markets"] = served_markets
    stats["stale_markets"] = stale_markets
    stats["candidates"] = len(candidates)

    if not candidates:
        # Authoritative UNKNOWN, never green: a refresh rail that refreshed
        # nothing has not proved it can refresh anything. With `served_markets`
        # beside it this is a readable state — "13,746 served, none stale" is a
        # healthy quiet run and "0 served" is a broken selector wearing one.
        # (13,746 is THIS rail's population, not the issue's 22,034; the module
        # docstring keeps the two apart on purpose.)
        return _terminal(stats, "no_work", "nothing_stale")

    skips = _load_attempt_skips([mid for mid, _ in candidates])
    stats["skipped_recent_attempt"] = len(skips)
    eligible = [(mid, cid) for mid, cid in candidates if mid not in skips]
    due = eligible[: max(budget, 0)]
    # Reported rather than merely enforced: a budget that binds every run is the
    # signal that the population has outgrown it, and it is invisible from
    # `conditions_requested` alone, which reads the same at 900-of-900 and
    # 900-of-90,000.
    stats["budget_exhausted"] = len(eligible) > len(due)
    stats["conditions_requested"] = len(due)
    if not due:
        # THE TWO EMPTY-`due` STATES ARE NOT THE SAME STATE, and this file has
        # already argued that once (`nothing_stale` vs here). A caller that
        # passed a zero budget refreshed nothing BY INSTRUCTION; a window whose
        # whole candidate set is marked refreshed nothing because it could not.
        # One shared reason would have made a mis-set budget indistinguishable
        # from a rail whose every candidate is unwritable.
        if not eligible:
            return _terminal(stats, "no_work", "all_recently_attempted")
        return _terminal(stats, "no_work", "no_budget")

    service = PolymarketAPIService()
    now = datetime.now(timezone.utc)
    started = time.monotonic()
    fetch_failures = 0

    for start in range(0, len(due), BATCH_SIZE):
        if time.monotonic() - started > _TIME_BUDGET_S:
            # Between batches, never inside one: a run that stopped mid-market
            # would leave exactly the half-refreshed ladder this rail exists to
            # prevent.
            stats["wall_exhausted"] = True
            break
        batch = due[start : start + BATCH_SIZE]
        conditions = [cid for _, cid in batch]
        stats["batches"] += 1
        # Marked BEFORE the fetch, and that ordering is the starvation fix
        # rather than a detail: every early exit below — a refused fetch, a
        # market Gamma does not return, a book that cannot be priced — leaves
        # rows unwritten, and unwritten rows are exactly the ones that would
        # re-present at the head of a stalest-first ordering on the next run and
        # hold the tail behind them forever. An ATTEMPT is recorded because it
        # was attempted.
        _mark_attempted([mid for mid, _ in batch])
        try:
            markets = await service.get_markets_by_conditions(
                conditions,
                batch_size=BATCH_SIZE,
                # #3868: without this the fetch cannot see a result. The
                # endpoint applies a `closed=false` filter the caller never
                # asked for, so a leg that settles stops coming back at all and
                # its last LIVE price is frozen on the page for good.
                include_closed=True,
            )
        except Exception as exc:  # noqa: BLE001 — counted, never swallowed
            fetch_failures += 1
            stats["errors"].append(f"gamma fetch failed: {exc}")
            continue

        stats["markets_returned"] += len(markets)
        stats["not_returned"] += len(conditions) - len({m.condition_id for m in markets})
        if markets:
            try:
                await _write_refreshed_prices(markets, stats, now=now)
            except Exception as exc:  # noqa: BLE001
                # A WRITE THAT FAILED IS THE QUIETEST FAILURE THIS RAIL HAS: the
                # fetch worked, the numbers are in memory, and nothing reaches
                # the page. Counted per batch so one bad commit cannot wipe the
                # run's other 22 (gotcha #42).
                logger.exception("polymarket condition refresh: write failed")
                stats["errors"].append(f"write failed: {exc}")

    if fetch_failures and fetch_failures == stats["batches"]:
        return _terminal(stats, "failed", "fetch_failed")
    if not stats["snapshots_written"]:
        # Markets were due, and not one price landed. The pages keep rendering
        # and every number on them keeps ageing — the exact invisible failure
        # this rail was built to end.
        return _terminal(stats, "failed", "no_prices_written")
    if stats["wall_exhausted"]:
        # It wrote, and it could not finish the work it had already decided to
        # do. PARTIAL, which is not green: the budget below is what bounds a
        # healthy run, so a run that the CLOCK bounded instead is a run whose
        # sizing has stopped being true.
        return _terminal(stats, "partial", "wall_exhausted")
    # 🔴 `budget_exhausted` IS DELIBERATELY NOT PARTIAL, and this is the one
    # place the difference is decided.
    #
    # The precedent points the other way and is worth answering rather than
    # ignoring: `settlement_sweep` is enrolled precisely so that its
    # budget-capped nights read PARTIAL, because its backlog is supposed to
    # DRAIN and a growing one must not read healthy. This population does not
    # drain — a price that was refreshed an hour ago is stale again tomorrow, so
    # a steady-state rotation over 22,034 markets has the budget binding on
    # every single run, forever. Reporting that as PARTIAL would be an alarm
    # that can never clear, which is a monitor that lies rather than a monitor
    # that is strict.
    #
    # The thing that must not go unnoticed — the population outgrowing the rail
    # — is carried by the census instead: `stale_markets` against
    # `served_markets`, both in this summary, both measured by the selector this
    # run already executed.
    return _terminal(stats, "complete", "prices_written")
