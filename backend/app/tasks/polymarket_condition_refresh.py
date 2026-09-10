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

═══ #4827: THE CONDITION ID IS ON THE LEG, AND THAT IS WHERE THE POPULATION WAS ═══

Until 2026-09-10 the pool above carried one more clause — ``fm.external_id LIKE
'0x%'`` — and the test beside it said why: "an event-keyed row addressed this way
is a request that cannot return." That is true of the MARKET's external_id and
only of it. For a Gamma event written as a parent ladder the market row is keyed
by the EVENT id (``31552``, ``106232``) while every one of its legs carries the
bare condition id one level down, in ``futures_outcomes.external_id`` — the same
column ``_write_refreshed_prices``'s ``by_condition`` lookup (#3868) already
keys on. So the clause did not exclude the unaddressable; it excluded rows whose
address was in the next table.

Measured on production 2026-09-10 17:2xZ, over ``LIVE_MARKET_SQL`` ×
``source='polymarket'``, split by which rail could address each row:

    condition-keyed (this rail, before)   8,951 mkts   18,028 legs   13.5% >24h
    high-value only (`futures_price_refresh`) 1,257    13,001 legs   51.0% >24h
    NO TARGETED ARM AT ALL                7,608 mkts   35,244 legs   73.1% >24h
                                                        10,201 legs  >30 DAYS

The rail's own cohort is healthy at 13.5%; the hole was everything else. All
35,244 of those legs — 35,244 of 35,244, no NULLs and no non-``0x`` values —
already carry a condition id. Venue-side, 2026-09-10 17:1xZ: ``Epstein storage
units raided in 2026?`` read 0.095 at Gamma (``updatedAt`` 16:58Z, open and
active) while we served 0.260 stamped 2026-07-21, and ``Maranhão Governor
Election Winner`` (tier 1, resolving 2026-10-05) was serving June prices with
seven legs still at the 0.500 placeholder.

So the pool now admits any live Polymarket market that has at least one ungraded
leg carrying a condition id, and the ids it REQUESTS come from the market's own
external_id when that is a condition and from its legs otherwise. Nothing sends
an event id to ``/markets?condition_ids=…``; the old test's claim is preserved
exactly, and the population it was fencing off is now addressed the way it was
always addressable.

🔴 THE BUDGET IS NOW IN CONDITION IDS, NOT MARKETS, AND THAT IS FORCED — see
:data:`CONDITION_BUDGET`. A market cost one id when every row in the pool was a
bare condition. A ladder costs one per leg, and the pool's ladders average 5.5.
A market budget alone would have let one run ask for 6,600 ids on a wall sized
for 452.

TWO COUNTERS CHANGE SCALE UNDER #4827 AND NEITHER IS AN ALARM. ``markets_returned``
now counts Gamma child markets rather than roughly one per due row, and
``not_returned`` rises because a ladder legitimately carries legs the venue has
delisted — ``Maranhão Governor Election Winner`` still holds seven rows named
"Candidate G/H/I/J" at the 0.500 placeholder that Gamma no longer lists at all.
Neither feeds a terminal (``snapshots_written`` and the census do). Retiring a
delisted Polymarket leg is a real defect and a separate one: Kalshi has that arm
in ``futures_price_refresh``, Polymarket has none, and #4827 names it as out of
scope rather than leaving it to be rediscovered.

WHAT THIS DOES NOT TOUCH: the discovery scan, the closed-event sync, identity,
``status``, and any market with no condition-keyed leg to address. It never
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
from app.utils.futures_liveness import LIVE_MARKET_SQL, writable_leg_sql

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
#:
#: #4827 AMENDMENT: this is no longer the binding cap and is kept as the second
#: one. Since the pool admits ladders addressed by their legs, a market is worth
#: between one and ~130 condition ids, so the cap that has to be true of a run is
#: :data:`CONDITION_BUDGET`. Both are enforced; whichever binds first stops the
#: admission loop, and both are reported.
MARKET_BUDGET = 1_200

#: Condition ids requested per run — THE cap, sized against this rail's own
#: measured throughput rather than against the population it would like to cover.
#:
#: MEASURED, production ``task-metrics`` 2026-09-10 16:09Z: the run before this
#: change requested **452 conditions**, wrote **1,311 outcomes + 1,311 snapshots**
#: and took **73.1 s** of the 200 s wall. That is ~0.162 s per condition end to
#: end, so 1,000 ids is ~162 s — inside the wall with margin, and the margin is
#: the point: :data:`_TIME_BUDGET_S` exhausting is reported as PARTIAL, so a
#: budget sized at the wall would put this rail permanently amber and the amber
#: would mean nothing.
#:
#: WHAT IT BUYS, STATED RATHER THAN IMPLIED. The addressable population measured
#: 2026-09-10 17:2xZ is ~8,950 market-keyed ids + ~45,400 leg ids ≈ **54,400**.
#: At 1,000 an hour that is a **~55-hour full rotation**, and the priority class
#: (tier 1-2 or resolving inside :data:`IMMINENT_DAYS`, ~37,400 ids) leads it.
#: That does NOT meet #3879's 24-hour acceptance across the whole widened
#: population and it is not claimed to: before this change 7,608 of those markets
#: had no rail at all and 10,201 of their legs had not been read in 30 days. The
#: two things that would shorten the rotation — a faster beat than hourly, and a
#: write path that does better than ~18 rows/s — are #4827's named follow-ups and
#: neither is done here.
#:
#: 🔴 THE FIRST ~2 DAYS ARE A DRAIN, NOT THE STEADY STATE, and the ordering makes
#: that deliberate: stalest-first inside the priority class means a 90-day-old
#: tier-1 election price is taken before a 25-hour-old one. So the market-keyed
#: cohort's own >24h share will RISE while the months-stale backlog clears. That
#: is the correct trade and it is visible in ``stale_markets`` without anyone
#: having to be told.
CONDITION_BUDGET = 1_000

#: A market resolving inside this window is priority whatever its tier — an
#: imminent question is the one a reader is most likely to be looking at, and
#: 9,281 legs sit in the ≤2d bucket (#3879's own table).
IMMINENT_DAYS = 2

#: How far ahead of a linked event's own START this rail treats its markets as
#: the most urgent thing in the pool. See :data:`_KICKOFF_SQL` for why the
#: market's ``resolution_date`` cannot answer this question.
#:
#: 24 BECAUSE #4896's ACCEPTANCE SAYS 24 — "for every event kicking off within
#: 24h ... no ungraded leg older than the game's own refresh cadence (target
#: <1h, matching Kalshi)". A previous cut of this constant read 12, which met
#: that bar for the last half-day before kickoff and left games 12-24h out on
#: the ordinary 12-hour window. CERT-2549 blocked it, correctly: narrowing the
#: horizon to fit the budget is amending the acceptance, not meeting it.
#:
#: WHAT IT COSTS, MEASURED rather than assumed, production 2026-09-10 22:1xZ,
#: with :data:`KICKOFF_STALE_MINUTES` in force — STEADY-STATE per-beat cost,
#: what the class spends on EVERY beat:
#:
#:      lead    markets   ids/beat   % of CONDITION_BUDGET   left for the drain
#:       6 h      130        341            34.1%                   659
#:      12 h      137        348            34.8%                   652
#:      24 h      230        656            65.6%                   344
#:
#: THE ABSOLUTE FIGURE MOVES and is quoted as a range rather than a point: the
#: same 24h class read 656 ids at 22:1xZ and 539 at 22:2xZ, because games leave
#: through :data:`KICKOFF_TAIL_HOURS` as the window slides. The lead comparison
#: above is a single-moment comparison, which is what makes it a fair one; the
#: standing cost is ~540-660 ids a beat.
#:
#: So this is not free and the number is stated rather than buried: the kickoff
#: class takes roughly two thirds of each run and #4827's backlog rotation keeps
#: the remaining ~340-460 ids an hour. That rotation is a TRANSIENT catch-up over a
#: ~54,000-id population while this class is permanent, so the trade is "the
#: backlog drains slower for a few days, and no game a reader can open is ever
#: stale". The drain rate is its own follow-up; it is not solved by shortening
#: the horizon, which is what the blocked cut tried.
KICKOFF_LEAD_HOURS = 24

#: How long AFTER its start an uncompleted event stays in that class. A game in
#: progress is the single most-read blend on the site, and ``completed_at`` is
#: the primary exit — this bound only stops a row whose ``completed_at`` never
#: arrives from claiming the head of the queue forever, the same fixed point
#: :data:`_ATTEMPT_TTL_SECONDS` exists to break.
KICKOFF_TAIL_HOURS = 6

#: How stale a KICKOFF row may get before this rail re-reads it — the whole
#: second half of #4896, and CERT-2546's required repair.
#:
#: 🔴 AN ORDERING KEY ALONE DOES NOT SET A CADENCE, and the first cut of #4896
#: shipped believing it did. Leading the queue only decides who goes first among
#: the rows that are ELIGIBLE, and both eligibility gates were sized for the
#: 12-hour producer window: the selector's own ``stalest <`` test, and the
#: attempt marker, which :data:`_ATTEMPT_TTL_SECONDS` pins to the same 12 hours.
#: So a game reached once left the pool for eleven of the next twelve hourly
#: beats and could be up to 12 hours stale at kickoff — against #4896's stated
#: acceptance of under an hour, matching what Kalshi already does on the same
#: events. Ordering fixed WHICH row is taken and left WHEN untouched.
#:
#: 45 minutes rather than 60 because the bound has to be strictly under the beat
#: interval: at exactly 60 a row refreshed at :08 becomes eligible at :08, and
#: whether the next beat sees it depends on which of the two fires first. 45
#: leaves a quarter-hour of margin and still means every hourly beat re-admits
#: the whole class.
#:
#: WHAT IT COSTS, MEASURED rather than assumed: the kickoff class is 72 markets
#: / 277 condition ids, so re-admitting it EVERY beat spends 277 of the 1,000-id
#: :data:`CONDITION_BUDGET` and leaves ~723 for the backlog drain. That is the
#: same figure the ordering key was sized against — the class was always meant
#: to be swept whole every hour, and until this constant existed it simply was
#: not.
KICKOFF_STALE_MINUTES = 45

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

#: The same marker for a kickoff row, and it tracks
#: :data:`KICKOFF_STALE_MINUTES` for the same reason the constant above tracks
#: :data:`SERVED_STALE_HOURS`: a marker that outlives its own eligibility window
#: IS the eligibility window, and then the shorter one is decoration. Both
#: gates have to agree or the stricter one silently wins — which is exactly the
#: half-leg gap #4840 closed one level down, in the same file.
#:
#: The starvation argument the marker exists for still holds, and is bounded
#: rather than argued away: an imminent market the venue will not price does
#: re-present every beat, but the whole class is 277 ids against a 1,000-id
#: budget, so the worst case costs a quarter of a run and cannot hold the tail.
#: Retrying a game that is about to start is the correct trade at that price.
_KICKOFF_ATTEMPT_TTL_SECONDS = KICKOFF_STALE_MINUTES * 60


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
#: :func:`writable_leg_sql` IS the write path's own refusal (CERT-452, #4840) —
#: one definition in ``futures_liveness``, applied here and by
#: ``_write_refreshed_prices``, so a market is not selected on the staleness of a
#: leg the writer would decline. A market with no writable legs left produces a
#: NULL ``stalest`` and is excluded by the comparison — there is nothing here to
#: write. Before #4840 this said only ``is_winner IS NOT TRUE`` while the writer
#: also refused ``resolution_source = 'api_settlement'``, and the half-leg gap
#: pinned 155 permanently-unwritable markets to the head of a ``stalest ASC``
#: queue.
#: #4827: ADDRESSABILITY IS A PROPERTY OF THE LEGS, so it is tested on the legs.
#: ``fm.external_id LIKE '0x%'`` used to be the pool's fence and it fenced out
#: 7,608 live markets whose every leg carried a condition id. The fence is now
#: "has at least one ungraded leg we can name to Gamma", which is what the old
#: clause was trying to say. It is an EXISTS rather than a join so the pool stays
#: one row per market, and it rides ``ix_futures_outcomes_market_id``.
#:
#: The ids to REQUEST come out of the same LATERAL that decides staleness, in one
#: pass over the market's legs: the market's own external_id when that is a bare
#: condition (byte-identical to the old behaviour for every row the rail already
#: swept), and otherwise the DISTINCT bare condition ids of its ungraded legs.
#: ``regexp_replace`` strips the ``_yes``/``_no`` suffix the sub-market ingest
#: writes — measured 2026-09-10, 45,435 of 46,175 event-keyed legs carry the bare
#: id and 735 carry a suffixed one, and both name the same book.
_ADDRESSABLE_LEG_SQL = f"""
           EXISTS (
                SELECT 1 FROM futures_outcomes fo_a
                 WHERE fo_a.market_id = fm.id
                   AND {writable_leg_sql("fo_a")}
                   AND fo_a.external_id LIKE '0x%'
              )
"""

#: THE EVENT'S OWN CLOCK, because the market's does not answer this question.
#:
#: ``priority`` above asks the MARKET when it resolves. For a Polymarket game
#: market that field is a padded venue window, not the fixture: measured
#: 2026-09-10 20:5xZ, ``Pegula vs Sabalenka`` (US Open semi-final, court
#: 23:00Z that night) carried ``resolution_date`` 2026-09-17, ``Rybakina vs
#: Gauff`` (02:00Z) carried 2026-09-18, and ``Rockies @ Yankees`` (23:05Z)
#: carried 2026-09-16 — all a full WEEK late, all ``market_tier`` 5, so every
#: arm of ``priority`` read false for a game about to be played. They ranked
#: 7,947 / 10,667 / 7,670 of 10,675 stale candidates, below ``CANDIDATE_LIMIT``
#: 3,600 — not merely starved but never selectable at all. The event row knew
#: the right time the whole while.
#:
#: So the key is the LINKED EVENT's ``commence_time`` and it is NULL for every
#: row that is not a game about to be played, which is what lets it sit in front
#: of the existing ordering without disturbing it: ``ASC NULLS LAST`` puts the
#: 73 imminent markets first, soonest kickoff first, and ties every other row at
#: NULL so they fall through to ``priority DESC, stalest ASC`` exactly as before.
#:
#: ``completed_at IS NULL`` is the primary exit and :data:`KICKOFF_TAIL_HOURS`
#: the backstop. A market with no event (``event_id IS NULL`` — 6,337 of the
#: pool, the futures) LEFT JOINs to NULL and is untouched by this.
_KICKOFF_SQL = f"""
               CASE
                 WHEN e.commence_time IS NOT NULL
                  AND e.completed_at IS NULL
                  AND e.commence_time <= NOW() + make_interval(hours => {KICKOFF_LEAD_HOURS})
                  AND e.commence_time >  NOW() - make_interval(hours => {KICKOFF_TAIL_HOURS})
                 THEN e.commence_time
               END
"""

_CANDIDATE_SQL = f"""
    WITH pool AS MATERIALIZED (
        SELECT fm.id,
               fm.external_id,
               {_KICKOFF_SQL.strip()} AS kickoff,
               (
                    fm.market_tier IN (1, 2)
                 OR (
                        fm.resolution_date IS NOT NULL
                    AND fm.resolution_date <= NOW() + make_interval(days => {IMMINENT_DAYS})
                    )
               ) AS priority
          FROM futures_markets fm
          LEFT JOIN events e ON e.id = fm.event_id
         WHERE fm.source = 'polymarket'
           AND {_ADDRESSABLE_LEG_SQL.strip()}
           AND {LIVE_MARKET_SQL}
    )
    SELECT p.id,
           s.request_ids,
           p.priority,
           COUNT(*) OVER () AS stale_markets,
           (SELECT COUNT(*) FROM pool) AS served_markets,
           (p.kickoff IS NOT NULL) AS imminent
      FROM pool p
      JOIN LATERAL (
            SELECT MIN(COALESCE(fo.last_updated, TIMESTAMP WITH TIME ZONE 'epoch')) AS stalest,
                   CASE
                     WHEN p.external_id LIKE '0x%' THEN ARRAY[p.external_id]
                     ELSE ARRAY_AGG(
                            DISTINCT regexp_replace(fo.external_id, '_(yes|no)$', '')
                          ) FILTER (WHERE fo.external_id LIKE '0x%')
                   END AS request_ids
              FROM futures_outcomes fo
             WHERE fo.market_id = p.id
               AND {writable_leg_sql("fo")}
           ) s ON TRUE
     WHERE s.stalest < NOW() - CASE
                                 WHEN p.kickoff IS NOT NULL
                                 THEN make_interval(mins => {KICKOFF_STALE_MINUTES})
                                 ELSE make_interval(hours => :stale_hours)
                               END
       AND COALESCE(ARRAY_LENGTH(s.request_ids, 1), 0) > 0
     ORDER BY p.kickoff ASC NULLS LAST, p.priority DESC, s.stalest ASC
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


def _mark_attempted(market_ids: list[int], imminent: set[int] | None = None) -> None:
    """Record an ATTEMPT, not a success — see ``_ATTEMPT_TTL_SECONDS``.

    #4896 / CERT-2546: a kickoff row's marker expires on
    :data:`_KICKOFF_ATTEMPT_TTL_SECONDS` instead, so it is eligible again on the
    next hourly beat rather than the next half-day. The TTL is chosen per market
    rather than per call because one batch legitimately mixes the two classes —
    ``_pack_batches`` groups on id count, not on urgency.
    """
    if not market_ids:
        return
    imminent = imminent or set()
    try:
        from app.tasks.redis_state import get_redis_client

        rc = get_redis_client(socket_timeout=2.0, socket_connect_timeout=2.0)
        pipe = rc.pipeline()
        for mid in market_ids:
            ttl = (
                _KICKOFF_ATTEMPT_TTL_SECONDS
                if mid in imminent
                else _ATTEMPT_TTL_SECONDS
            )
            pipe.setex(_attempt_key(mid), ttl, "1")
        pipe.execute()
    except Exception:  # noqa: BLE001
        pass


def _pack_batches(
    due: list[tuple[int, list[str]]],
) -> list[list[tuple[int, list[str]]]]:
    """Group markets into Gamma requests of at most :data:`BATCH_SIZE` ids.

    #4827. Before the widening every market was one id, so ``BATCH_SIZE`` markets
    per request and ``BATCH_SIZE`` ids per request were the same statement and
    slicing ``due`` did both. A ladder is 5 to 130 ids, so they part company and
    the one that matters is the ID count — ``BATCH_SIZE`` is a property of the
    URL (a query string with hundreds of repeated parameters is a 414 in
    waiting), not of our bookkeeping.

    🔴 A MARKET IS NEVER SPLIT ACROSS TWO BATCHES, which is the module docstring's
    unit-of-work rule reaching the packer: the wall check happens BETWEEN batches,
    so a ladder split across the boundary is precisely the half-refreshed row this
    rail exists to prevent. A market whose own id list is wider than
    ``BATCH_SIZE`` therefore gets a batch to itself and
    ``get_markets_by_conditions`` chunks it internally — the whole market still
    reaches the writer in one call, which is what the rule is about.
    """
    batches: list[list[tuple[int, list[str]]]] = []
    current: list[tuple[int, list[str]]] = []
    current_ids = 0
    for mid, cids in due:
        if current and current_ids + len(cids) > BATCH_SIZE:
            batches.append(current)
            current = []
            current_ids = 0
        current.append((mid, cids))
        current_ids += len(cids)
    if current:
        batches.append(current)
    return batches


async def _select_stale_conditions(
    *, stale_hours: int, limit: int
) -> tuple[list[tuple[int, list[str]]], int, int, set[int]]:
    """``([(market_id, [cid, …]), …], stale_markets, served_markets, imminent)``.

    #4896 / CERT-2546: the fourth element is the set of KICKOFF market ids, and
    it travels because the attempt marker needs it — a kickoff row's marker must
    expire inside its own 45-minute window or the marker becomes the eligibility
    gate and the shorter window is decoration. Returned as a set rather than
    folded into the tuples so ``_pack_batches`` and the admission loop keep the
    two-element shape #4827 gave them.

    Ordered kickoff-first, then priority-first, then stalest-first, which is the
    whole starvation argument: within a class the row that has waited longest is
    always next, so no member of a class can be passed over twice for the same
    reason.

    #4896 put the kickoff key in front of that, and it is the only key here that
    is not about waiting. Staleness cannot express urgency — a 90-day-old
    election price is always "staler" than a game starting in two hours, and
    under a budget that is a permanent loss for the game. The kickoff key is
    NULL for everything that is not a linked event about to be played
    (:data:`_KICKOFF_SQL`), so it re-orders 73 rows and leaves the argument
    above governing the other ~10,600.

    #4827: the second element is a LIST because a ladder is addressed by its
    legs. It holds exactly one id for every row this rail swept before the
    change, so the ordering argument above is unchanged.
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
        return [], 0, await _served_market_count(), set()
    return (
        # `list(r[1] or ())` — asyncpg hands an ARRAY back as a list already, but
        # the copy is what stops a driver-owned buffer travelling into the batch
        # packer, and `or ()` keeps a NULL out of it rather than letting a None
        # reach `len()` three frames later.
        [(r[0], list(r[1] or ())) for r in rows],
        int(rows[0][3]),
        int(rows[0][4]),
        {r[0] for r in rows if r[5]},
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
       AND {_ADDRESSABLE_LEG_SQL.strip()}
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
    *,
    budget: int = MARKET_BUDGET,
    condition_budget: int = CONDITION_BUDGET,
    stale_hours: int = SERVED_STALE_HOURS,
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
        # #4827: `conditions_requested` counts CONDITION IDS and `markets_due`
        # counts markets. Before the widening they were the same number and only
        # the first was reported; a ladder makes them differ by ~5.5x, and the
        # cap that has to be read against the wall is the id one.
        "markets_due": 0,
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
        (
            candidates,
            stale_markets,
            served_markets,
            imminent_ids,
        ) = await _select_stale_conditions(
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
    eligible = [(mid, cids) for mid, cids in candidates if mid not in skips]

    # #4827: ADMISSION IS WHOLE MARKETS UNDER TWO CAPS. The market cap is the old
    # one; the id cap is the one sized against the wall. A market is admitted
    # only if it fits entirely — the unit-of-work rule in the module docstring is
    # a correctness bound (a half-refreshed ladder is worse than a stale one), so
    # a market is never split across the budget line. The FIRST market is always
    # admitted whatever its size, because a ladder wider than the whole id budget
    # would otherwise be permanently unreachable while sitting at the head of a
    # stalest-first ordering — the fixed point the attempt markers exist to break.
    due: list[tuple[int, list[str]]] = []
    ids_taken = 0
    id_cap = max(condition_budget, 0)
    for mid, cids in eligible:
        if len(due) >= max(budget, 0) or id_cap <= 0:
            break
        if due and ids_taken + len(cids) > id_cap:
            break
        due.append((mid, cids))
        ids_taken += len(cids)
    # Reported rather than merely enforced: a budget that binds every run is the
    # signal that the population has outgrown it, and it is invisible from
    # `conditions_requested` alone, which reads the same at 900-of-900 and
    # 900-of-90,000.
    stats["budget_exhausted"] = len(eligible) > len(due)
    stats["markets_due"] = len(due)
    stats["conditions_requested"] = ids_taken
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

    for batch in _pack_batches(due):
        if time.monotonic() - started > _TIME_BUDGET_S:
            # Between batches, never inside one: a run that stopped mid-market
            # would leave exactly the half-refreshed ladder this rail exists to
            # prevent.
            stats["wall_exhausted"] = True
            break
        conditions = [cid for _, cids in batch for cid in cids]
        stats["batches"] += 1
        # Marked BEFORE the fetch, and that ordering is the starvation fix
        # rather than a detail: every early exit below — a refused fetch, a
        # market Gamma does not return, a book that cannot be priced — leaves
        # rows unwritten, and unwritten rows are exactly the ones that would
        # re-present at the head of a stalest-first ordering on the next run and
        # hold the tail behind them forever. An ATTEMPT is recorded because it
        # was attempted.
        _mark_attempted([mid for mid, _ in batch], imminent_ids)
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
