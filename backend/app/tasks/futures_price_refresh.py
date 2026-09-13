"""#2199 — refresh prices for high-value open futures markets that the
discovery polls structurally cannot reach.

THE DEFECT THIS EXISTS FOR
--------------------------
Price capture for an *already-known* futures market was, until this module, a
side effect of a *discovery* scan. Both discovery scans are bounded, and both
orderings put already-known markets last:

* **Polymarket** (`_poll_polymarket_markets`). Gamma capped offset pagination at
  2000 in July 2026, so #219E flipped the scan to ``order=startDate&ascending=
  false`` — newest-listed first — to stop the *new*-market starvation. Measured
  2026-08-25: the deepest reachable page (offset 1900-1999) had an oldest
  ``startDate`` of **the same day**, and 73/100 events on page 0 were crypto
  up/down five-minute binaries the poll then discards. The entire reachable
  universe is roughly the last ten hours of listings. The 2026 Men's US Open
  Winner field has ``startDate = 2026-01-02`` — seven months deep in a tail the
  poll can never reach. #219E did not fix the starvation, it mirrored it:
  oldest-first starved new markets, newest-first starves old-but-live ones.
  Gotcha #41: a bounded sweep needs BOTH bounds.

* **Kalshi** (`_poll_kalshi_markets`). ``_partition_new_events_first`` defers
  every already-known event behind every new one, and the 480s processing
  deadline truncates the run long before the tail. The comment justifying that
  ordering says deferring existing rows is safe because "kalshi_ws + live poll
  keep them fresh anyway". That premise is false for futures:
  ``poll_live_prediction_markets`` is scoped to markets *linked to live events*
  and an outright championship field has no ``event_id``.

Measured blast radius (production, 2026-08-25): of the **907** tier-1 `open`
markets above a $10K volume floor with a future resolution date, **900** had
received no price snapshot in six hours. Not a tennis problem — the Super Bowl
LXI, 2028 presidential, MLB / NBA / UCL / Premier League championship and March
Madness fields were all dark.

WHAT THIS TASK IS, AND IS NOT
-----------------------------
It is a **price refresh**, and nothing else. It selects markets that already
exist in our DB, fetches those specific markets by id, and writes
``futures_outcomes`` price columns plus a ``futures_odds_snapshots`` row.

It deliberately does NOT create markets, create outcomes, categorise, re-tier,
group, or touch ``event_id``. Discovery stays the polls' job. This separation is
the actual fix: refresh coverage no longer depends on a discovery ordering, so
the two can never starve each other again.

THREE ARMS, BECAUSE THERE ARE THREE KINDS OF WORTH REFRESHING
--------------------------------------------------------------
The sweep selects on **value** (volume above a floor at any tier, or tier 1
where no volume was recorded), on **curation** (any market a committed
tournament register renders —
:func:`app.utils.tournament_register.registered_market_ids`), and since
2026-09-05 on **what page one is actually showing**
(:func:`app.utils.feed_served_markets.served_market_ids`).

THE THIRD ARM, AND THE TIER FENCE IT REPLACED (#3315)
------------------------------------------------------
The value arm used to read ``market_tier = 1 AND volume >= 10000``. Measured on
production 2026-09-05 and reproduced against Polymarket Gamma before any code
was written: **all seven Polymarket cards on Discover page one were tier 2**, so
the safety net could not reach one of them however stale it got. "Brazil
Presidential Election" rendered Flávio Bolsonaro at **26.2%** against Gamma's
**39.9%** — 13.7 points, off outcome rows last written **1,109 hours** earlier,
on a market carrying **$114M** of volume. 11 of 73 matched page-one outcomes
were 3+ points wrong; the other 62 agreed to 0.15 points, so the ordinary polls
were fine and this net was the whole gap. Net reach across open tier 1-3
markets: **905 of 15,007**.

Nothing was red, and nothing should have been: the beat ran on time (ratio 1.04,
19 deliveries against 18.34 expected), wrote everything it selected, and
reported success — over a set that excluded the front page. A coverage gap is
invisible to every scheduling instrument there is.

:data:`HIGH_VALUE_SQL` fixes the two predicate holes (tier is no longer a fence;
NULL volume no longer reads as "measured, and small"). The third arm fixes the
premise: **a value floor is a proxy for "someone is looking at this", and the
served arm is the thing itself.** Both were needed. The predicate alone would
still have been a guess about which markets matter, re-made hourly, by a query
that cannot see the ranker.

THE SECOND ARM, AND THE US OPEN PROPS SECTION IT EMPTIED
---------------------------------------------------------
The second arm exists because the first one cannot express the US Open props
section. Measured 2026-08-27: every one of the three markets behind that
section was tier 5 — ``sinner-competes`` 215h stale, both ``*-second-major``
837h — and the eight curated Polymarket props were tier 2/5 with ``volume``
NULL. The predicate admitted **none of them, ever**. The page did exactly what
it was built to do (``propIsDark`` rotated the dark cards out) and rendered its
honest empty state, so the only symptom was an empty section and nothing
anywhere was red. A curated market's value is the curation; a volume floor
cannot see it.

The arms keep separate clocks and this is the second half of the same fix. The
class window and the *renderer's* ``LIVE_PRICE_STALE`` bound are both 6h, so the
sweep only became interested in a market once it had already breached the gate
the page renders through — it could not arrive before the dark window, only
after. Registered rows use :data:`REGISTERED_REFRESH_MINUTES` instead, which is
a sub-interval of the hourly beat, so they are re-priced hours before they could
go dark. Do not collapse the two constants back into one: that lockstep IS the
defect.

Identity rows (registered and served alike) are taken by
:func:`_take_for_source` BEFORE the per-source budget is applied, and lead the
list each source loop walks — both loops stop on the wall clock, so being taken
first and placed first is what makes "an identity row cannot be starved by the
class" a guarantee rather than a tendency. Neither arm can be grown by an
upstream: the register is committed on disk (81 markets, ≈9 extra Gamma calls
per beat) and the served set is bounded by the page (26 futures markets on
Discover page one on 2026-09-05, capped at
:data:`app.utils.feed_served_markets.MAX_SERVED_IDS_PER_SHAPE`).

STARVATION GUARDS (gotcha #41 — an ordering needs both bounds)
--------------------------------------------------------------
* **Value floor and liveness floor**, not a bare "oldest first":
  :data:`HIGH_VALUE_SQL` plus every clause of
  ``app.utils.futures_liveness.LIVE_MARKET_SQL``. Both identity arms drop the
  value floor and keep the liveness bounds verbatim, so a curated or rendered
  row is not a licence to re-animate the stale-open population.
  **#2222 corrected what "liveness" means here, and the correction is load
  bearing.** This module used to say the resolution-date bound "is what keeps
  the dead out of the queue". It is not: ``status='open'`` survives settlement
  (gotcha #33) and ``resolution_date`` was measurably wrong by one to two years
  on every market in #2222's population, so nineteen settled markets — the
  Champions League and Premier League winner fields, Eurovision, eight
  elections — sat at the head of this queue permanently, were attempted every
  run, wrote zero, and held ``futures-price-freshness`` red for a month. The two
  bounds that actually see settlement (our own ``is_winner`` flag, and a venue
  positively saying the market is over) live in ``futures_liveness`` with the
  full reasoning, and the guard imports the same string.
* **Ordered by value, not by staleness.** Oldest-capture-first looks right and
  is a trap here: a market that can never be priced (a stale-settled book
  returning no bid, ask or trade) has a NULL last-capture forever, so it would
  hold the head of the queue permanently and starve everything behind it. Volume
  DESC has no such fixed point.
* **Per-market attempt markers** in Redis with a TTL equal to the staleness
  window, so one run cannot re-attempt what the previous run just tried and the
  tail rotates into view. An *attempt* is marked, not a success — otherwise the
  unpriceable market is back at the front on the very next run.
* **A budget per source, not one shared cap** (#3315). Kalshi costs ~0.35 s per
  market (it has no batch event endpoint) and Polymarket ~0.065 s (twenty event
  ids per Gamma call). One 500-market cap over two populations priced 20x apart
  did not bound cost; it decided, by whichever source happened to hold the top of
  the volume ordering, which source got swept at all. See
  :data:`KALSHI_MARKET_BUDGET`.

VERDICT
-------
Enrolled in :data:`app.utils.task_verdict.ENFORCED_TASKS` from birth, per #1884.
The failure this task must never report as green is precisely the one it was
built to end: a run that fetched markets, wrote no snapshots, and returned.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.utils.futures_liveness import (
    LIVE_MARKET_SQL,
    VENUE_SETTLED_KEY,
    VENUE_SETTLED_NOW_SQL,
)
from app.utils.polymarket_settlement_scan import GAMMA_EVENT_ID_EXPR

logger = logging.getLogger(__name__)


class _VenueSettled:
    """Sentinel: the venue answered, and its answer is "this market is over".

    Distinct from ``None`` (the venue could not be asked, or does not know this
    id) and from ``[]`` (the venue has a book and every quote in it was refused
    by a price guard). All three used to arrive as an empty priced list and be
    counted as ``unpriceable`` — one word for three different facts, and the
    word implied the market was still live and merely awkward. #2222 lived in
    that conflation for a month.
    """

    __slots__ = ()

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return "VENUE_SETTLED"


#: See :class:`_VenueSettled`. Compared by identity (``is``), never truthiness.
VENUE_SETTLED = _VenueSettled()

#: Only markets at or above this traded volume are refreshed. The floor is what
#: makes the sweep bounded; the guard in ``routes/admin_source_health.py``
#: asserts the invariant over exactly this same set, so fix and guard cannot
#: disagree about what they cover.
HIGH_VALUE_VOLUME_FLOOR = 10_000

#: 🔴 THE VALUE TEST, AND IT IS NO LONGER A TIER TEST (#3315).
#:
#: This used to read ``fm.market_tier = 1 AND fm.volume >= :volume_floor``, and
#: both halves of that conjunction were wrong in a way that only showed up on the
#: front page.
#:
#: **The tier fence.** Measured on production 2026-09-05, all seven Polymarket
#: cards on Discover page one were ``market_tier = 2``, so the safety net could
#: not reach one of them however stale it got. "Brazil Presidential Election"
#: rendered Flávio Bolsonaro at 26.2% against Gamma's 39.9% — **13.7 points** —
#: off ``futures_outcomes`` rows last written **1,109 hours** earlier, on a market
#: carrying **$114,137,967** of volume: four orders of magnitude over the floor
#: below, refused for a reason that has nothing to do with value. Tier is a
#: PRESENTATION grade. Using it as a value gate meant the sweep's reach was
#: 909 of 15,007 open markets, and the 11,619 open tier-2 rows — where the front
#: page lives — were outside it by construction.
#:
#: **The NULL-volume comparison.** ``fm.volume >= 10000`` is NULL-rejecting, so a
#: market with no recorded volume failed the value test as if it had been
#: measured and found small. 1,199 of 3,081 open tier-1 markets (39%) have NULL
#: volume. "We have not measured this" and "this is worthless" are opposite
#: facts and they were arriving as the same one.
#:
#: So the test is now a DISJUNCTION of two positive value statements, and neither
#: mentions tier:
#:
#: * measured volume at or above the floor, at ANY tier — Brazil qualifies on the
#:   only evidence that was ever relevant;
#: * OR tier 1, at ANY volume — tier 1 is our own positive statement of
#:   importance, and it is the right authority wherever the venue's number is
#:   not one. It is a tier ADMISSION, never a tier fence: no market is excluded
#:   for its tier by this predicate.
#:
#: 🔴 THE SECOND ARM USED TO READ ``market_tier = 1 AND fm.volume IS NULL``, AND
#: THAT ``IS NULL`` WAS THE SAME HOLE ONE STEP SMALLER (#5268).
#:
#: #3315 fixed "we never measured this" being read as "this is worthless". It
#: left the neighbouring case untouched: a tier-1 market whose volume we DID
#: measure and which is merely SMALL failed both arms and was refreshed by
#: nothing. The rationale above — tier 1 is our own statement of importance —
#: does not become false when a number arrives; a small number is not a reason
#: to stop believing our own tier grade, and a thin market is precisely where a
#: stale quote is least likely to correct itself.
#:
#: MEASURED on production 2026-09-11, under the full liveness predicate:
#:
#:   live tier-1 markets with measured volume BELOW the floor   1,005
#:     of those, not refreshed in over 24h                        953   (95%)
#:     of those, not refreshed in over 7 days                     399
#:
#: The specimen is ``KXWBCHEAVYWEIGHTTITLE-27`` (market 2951423): **tier 1**,
#: ``mutually_exclusive``, open interest 2,171, volume 2,814 — so ``>= 10000``
#: is false and ``IS NULL`` is false, and it passed NEITHER arm. Its outcomes
#: were last written 2026-09-10 06:52Z and its 17 rows summed to **801%**, six
#: different boxers each reading 96% for one belt. That number is a last trade
#: the venue's own book had already priced out (the #5121 mechanism), and #5267
#: fixes that at the WRITE boundary — which can never reach a row nothing
#: writes. A forward fix needs the row to be visited.
#:
#: 🔴 AND THE THIRD ARM IS THE SAME HOLE ONE STEP WIDER AGAIN (#5781).
#:
#: #3315 said "we have not measured this" and "this is worthless" are opposite
#: facts. #5268 said a SMALL measured number is not a reason to stop believing
#: our own tier grade. Both closed the case for tier 1 and neither reached the
#: row that has NEITHER: **tier 2+, volume NULL.** Nothing admits it. Not the
#: measured arm (``NULL >= 10000`` is NULL, not true), not the tier arm.
#:
#: It is a FIXED POINT, which is what makes it different from ordinary
#: ineligibility: the only writer that would give the row a volume is the poll
#: that has stopped reaching it, and the sweep that would re-price it is gated on
#: the volume. You need volume to be swept and you need to be swept to get volume,
#: so the row never leaves the state it was born in.
#:
#: THE SPECIMEN, read on production 2026-09-12. ``NCAA Football 2026 Big Ten
#: Conference: Winner`` (market 57792790, Gamma event 779028), tier 2, reachable
#: by a reader through ``/api/events/search?q=Big+Ten+Conference``. Every rung was
#: last written **2026-08-01** — the day the venue opened the book, before a game
#: of the season was played, and the card was still serving it two game weeks in:
#:
#:   Michigan   4.5% served   vs  16.5% at the venue   +12.0 pts
#:   USC        4.5%              16.0%                +11.5
#:   Nebraska   4.0%              15.5%                +11.5
#:   Ohio State 32.5%             28.5%                 -4.0
#:
#: ITS NULL IS A BIRTHDAY, NOT A VERDICT, and the row says so itself: the ingest
#: of 2026-08-01 11:18Z wrote ``liquidity = 8930.67`` and ``volume = NULL`` in the
#: SAME statement — a posted book with no first trade yet. The venue today reports
#: volume 4,003.96 on that event. We never asked again.
#:
#: So the third positive value statement is the venue's OWN measure of the thing
#: that is actually present: **a posted book at or above a floor, where volume was
#: never measured.** ``fm.volume IS NULL`` is not decoration on it — without that
#: half the arm would re-admit every market whose volume we DID measure and found
#: tiny, which is a different question with a different answer (#5268 answered it
#: for tier 1 on purpose and left tier 2+ alone on purpose).
#:
#: MEASURED on production 2026-09-12 under the full liveness predicate, tier <> 1,
#: ``volume IS NULL``, by posted liquidity:
#:
#:   liquidity >= 10,000      polymarket   133     kalshi   0
#:   liquidity 1,000-10,000                844              0
#:   liquidity 100-1,000                 5,908              0
#:   liquidity < 100                     7,807              0
#:   liquidity NULL                      7,433          4,881
#:
#: AND THEN MEASURED AGAIN ON THE ARM ITSELF, because the table above is a census
#: of a hand-written predicate and the arm is the thing that ships. Running
#: ``LIVE_MARKET_SQL AND VALUE_LIQUID_SQL`` on production:
#:
#:   the arm selects                                   1,009   (100% polymarket)
#:     already in the tier-1 pool, deduped by the UNION       38
#:     NET-NEW candidates                                    971
#:     of those, actually stale at any moment                851
#:   by tier   t1 38 · t2 192 · t3 6 · t4 2 · t5 771
#:
#: 🔴 THREE QUARTERS OF THE ARM IS TIER 5 AND THAT IS THE POINT, NOT A SURPRISE.
#: #3315's finding was that tier is a PRESENTATION grade and a bad value gate.
#: A tier-5 market with a $1,000 book and no measured volume is the same row as
#: the tier-2 specimen, one grade down; the thing that bounds this arm is the
#: book, and the thing that protects the measured population from it is the outer
#: ordering (see :data:`_CANDIDATE_SQL`), not a tier fence.
#:
#: The Polymarket backlog therefore goes ~1,974 -> ~2,825 against ``1,200 x 6 =
#: 7,200``, and the pool scan costs **629 ms** more (measured with EXPLAIN
#: ANALYZE on production 2026-09-12: value branch 831 ms / 3,969 rows, tier-1
#: branch 919 ms / 2,523 rows, liquid branch 629 ms / 1,009 rows). The planner's
#: COST estimate for the new CTE equals the other two — it is the same ~45,000
#: row heap scan — but the measured time is not, so read the milliseconds.
#:
#: 🔴 KALSHI CARRIES NO ``liquidity`` AT ALL, so this arm admits **zero** Kalshi
#: rows today. Be precise about what that is: the arm is SOURCE-BLIND — it names
#: no source and would admit a Kalshi row the day we start writing the column —
#: and the zero above is a measured property of the data on 2026-09-12, not a
#: fence. Re-measure it before quoting it. The half that IS a code property, and
#: the half the guard pins, is that a NULL ``liquidity`` never qualifies at any
#: source: ``NULL >= 1000`` is NULL, which is the same NULL-rejecting semantics
#: #3315 was written about, pointing the right way this time.
#:
#: On today's data that makes the cost argument hold: the rows it adds are all
#: Polymarket, the batched source at ~0.065 s/market, against Kalshi's ~0.35 s.
#: If Kalshi liquidity ever lands, ``liquid_pool_size`` is the number that says
#: so before the budget does.
#:
#: The floor is the 1,000 boundary above and not a rounder number one line up:
#: at 100 the arm takes 6,885 rows, which is larger than the entire value pool and
#: would need a bigger budget rather than a bigger pool. 1,000 is where the
#: distribution's tail starts and it is a real book — the specimen's is 8,930.
POSTED_LIQUIDITY_FLOOR = 1_000

#: The three halves are named separately because the selector has to plan them
#: separately (see :data:`ELIGIBLE_POOL_SQL`) while every other reader wants the
#: disjunction. Naming them once and composing both forms from the same three
#: strings is what keeps "the pool" and "the predicate" from becoming two
#: definitions of eligibility — the drift ``futures_liveness`` exists to prevent,
#: one level down.
VALUE_MEASURED_SQL = "fm.volume >= :volume_floor"
VALUE_TIER1_SQL = "(fm.market_tier = 1)"
VALUE_LIQUID_SQL = "(fm.volume IS NULL AND fm.liquidity >= :liquidity_floor)"

#: One string, interpolated by every reader that wants the whole test, for the
#: reason ``futures_liveness`` exists: six hand-copied WHERE blocks agree until
#: the day one of them needs a sixth clause.
HIGH_VALUE_SQL = f"({VALUE_MEASURED_SQL} OR {VALUE_TIER1_SQL} OR {VALUE_LIQUID_SQL})"

#: A high-value open market older than this is stale. Matches the 6h
#: ``LIVE_PRICE_STALE`` contract that ``utils/tournament_register.py`` already
#: enforces at the render boundary (UX-P130), so the producer and the renderer
#: use one definition of stale rather than two.
STALE_AFTER_HOURS = 6

#: How stale a REGISTERED market may get before the sweep re-prices it.
#:
#: The class window above and the renderer's own bound are both 6h, and that
#: lockstep is a defect for a curated page: the sweep only becomes interested in
#: a market once it has *already* breached the gate the page renders through, so
#: the beat is always one cycle behind the thing it exists to prevent. A
#: registered market should be re-priced hours before it could go dark, not an
#: hour after it did.
#:
#: **45 minutes, not 60, and the 15 is the whole point.** The beat is hourly at
#: ``:50`` and the window is evaluated against ``NOW()`` at the moment the run
#: reaches the query — a few seconds *later* each hour than the capture it is
#: testing. At exactly 60 the previous run's own snapshot is still inside the
#: window (``21:50:10`` is newer than ``NOW() - 1h`` when now is ``22:50:05``),
#: so the market fails the staleness test, is skipped, and refreshes every
#: *other* hour. The same margin keeps the attempt marker from outliving its
#: next beat. Any sub-interval value works; this one leaves 15 minutes of slack
#: for a late or slow run.
#:
#: It is deliberately NOT ``STALE_AFTER_HOURS``: that constant is the *renderer's*
#: definition of stale and the freshness guard reads it. This is a *producer*
#: interval. Collapsing the two back into one constant is what created the
#: lockstep.
REGISTERED_REFRESH_MINUTES = 45

#: How stale a market PAGE ONE IS CURRENTLY RENDERING may get before the sweep
#: re-prices it (#3315). Same reasoning and same value as the registered window
#: above — a sub-interval of the hourly beat, so the previous run's own capture
#: cannot still be inside the window when the next run evaluates it, and the
#: attempt marker cannot outlive its next beat.
#:
#: A separate constant from :data:`REGISTERED_REFRESH_MINUTES` even though the
#: two are equal today, because they answer to different things: that one tracks
#: the tournament renderer's dark window, this one tracks the beat that serves
#: Discover. Collapsing them would recreate the lockstep the registered constant
#: was split out to break, one level up.
SERVED_REFRESH_MINUTES = 45

#: Markets refreshed per run, PER SOURCE, because the two sources cost 20x
#: different amounts per market and one shared cap over two unequally-priced
#: populations does not bound cost — it silently decides which source gets swept.
#:
#: Polymarket is addressed by Gamma ``/events?id=..&id=..``, twenty event ids per
#: HTTP call. Kalshi has no batch event endpoint, so it is one call per market
#: row. Measured against the live venues 2026-09-05: Kalshi ``get_event`` mean
#: **193 ms** over five real event tickers, plus this loop's own 0.15 s spacing,
#: so ~0.35 s per market; a Polymarket batch of twenty costs one call plus 0.3 s,
#: so ~0.065 s per market.
#:
#: Under the single 500-market cap those numbers meant that whichever source
#: happened to hold the top of the volume ordering consumed the whole budget and
#: the other was simply not swept that hour. The cap read like a cost bound and
#: behaved like a lottery.
#:
#: Sized against the measured standing backlog (production 2026-09-05, live and
#: >6h without a capture under the widened predicate): **2,010 Kalshi** and
#: **1,974 Polymarket**. The attempt marker's TTL is the staleness window, so a
#: source's whole backlog must fit in ``budget x 6`` runs for the 6h invariant to
#: be reachable:
#:
#:   Kalshi      500 x 6 = 3,000 >= 2,010   worst-case wall 500 x 0.35 s = 175 s
#:   Polymarket 1200 x 6 = 7,200 >= 1,974   worst-case wall  60 calls   =  78 s
#:
#: 253 s against the 420 s loop budget, which leaves room for the scans (~12 s
#: measured) and for a bad day at either venue.
KALSHI_MARKET_BUDGET = 500
POLYMARKET_MARKET_BUDGET = 1200

#: The whole-run cap, kept as a name because the guard suite and the manual-run
#: entry point both read it. It is the SUM of the per-source budgets, not a third
#: independent bound: a total that could bind before either source budget did
#: would be the shared cap again, wearing the per-source ones as decoration.
DEFAULT_MARKET_BUDGET = KALSHI_MARKET_BUDGET + POLYMARKET_MARKET_BUDGET

#: Extra ``/markets/{ticker}`` calls one pass may spend confirming that a leg the
#: venue no longer lists really is gone (#4253). One call per CANDIDATE leg, and
#: the candidate set is self-draining: a retired leg's ``current_probability`` is
#: NULL, so it stops matching :data:`_KALSHI_FROZEN_CERTAIN_SQL` forever after.
#:
#: Sized against the measured standing population (production 2026-09-09): **41
#: legs across 14 markets** carry ``current_probability = 1.0`` uncrowned in the
#: reachable Kalshi cohort, of which **23 across 9 markets** clear the ungraded
#: gate below. 60 clears today's whole backlog in one pass and costs at most
#: 60 x 0.35 s = 21 s against the 420 s loop budget.
KALSHI_DELISTED_CHECK_BUDGET = 60

#: How many rows each value pool carries into the expensive staleness anti-join.
#:
#: THE POOLS EXIST BECAUSE OF A PLAN, NOT A PREFERENCE. With the tier fence gone
#: the candidate query's ``ORDER BY fm.volume DESC LIMIT n`` stopped bounding any
#: work: production's plan puts a Sort above the anti-join, so the LIMIT is
#: applied AFTER every open market has been probed against the 179M-row snapshot
#: table. Measured 2026-09-05 the widened one-statement form did not finish
#: inside 10 s at any LIMIT, including 1,500 — the LIMIT was decoration. Selecting
#: the pool first on the cheap predicates and filtering it second on the
#: expensive one is the same rows in 2.8 s + 9.4 s.
#:
#: ``MATERIALIZED`` is load-bearing: PG12+ inlines a single-reference CTE by
#: default, which would hand the planner back the query it just mis-planned. The
#: obvious alternative — a derived table with an ``OFFSET 0`` fence — was tried
#: and is WORSE: measured on production it did not finish inside 24 s where the
#: materialised form returns in ~12 s.
#:
#: MEASURED COST, so nobody has to guess later. Production 2026-09-05: the value
#: pool plus its anti-join 9.4 s, the unpriced pool plus its anti-join 2.8 s, so
#: the combined statement is ~12 s. That is 12 s of a 420 s loop budget under a
#: 60 s statement timeout, once an hour — comfortable, and NOT free. The whole
#: cost is scanning ~45,000 ``status='open'`` heap rows because
#: ``futures_markets`` has no index on ``volume``; a partial
#: ``(volume DESC) WHERE status='open'`` index would remove most of it. That is a
#: migration, so it is deliberately NOT in this change (gotcha #31: a big index
#: goes via psql, attended, never through an Alembic release).
#:
#: Both limits are set ABOVE their live populations, measured under the FULL
#: liveness predicate. 2026-09-05: 3,864 value-eligible, 1,155 tier-1-unpriced.
#: 2026-09-11, after the tier-1 arm widened to any volume (#5268): **4,377
#: value-eligible and 2,786 tier-1**, so the tier-1 pool's population grew past
#: the old 2,000 and the limit moves with it. Headroom is now ~3% and ~44%.
#:
#: 🔴 THE VALUE POOL'S HEADROOM IS THIN AND THAT IS A KNOWN, NAMED RISK. 4,377
#: against 4,500 is 123 rows. When it is crossed the value pool truncates by
#: volume ASCENDING — the declared ordering — so the rows dropped are the least
#: valuable, which is the intended failure direction rather than an accident.
#: :data:`_POOL_LIMIT_HEADROOM_MIN` and the guard test below assert the margin
#: so the crossing is a red test and not a silent Tuesday.
#:
#: 🔴 THE TIER-1 POOL'S ORDERING IS ``fm.id`` AND THAT IS ONLY SAFE WHILE THE
#: LIMIT EXCEEDS THE POPULATION. A stable ordering under a binding limit is a
#: fixed point: the same head is selected every run and the tail — the highest
#: ids, meaning the NEWEST markets — is never seen at all. That is the exact
#: starvation this module exists to end, so the limit must lead the population
#: rather than follow it.
#:
#: The previous revision of this comment promised that a truncated tier-1 pool
#: "reports it (``unpriced_pool_hit``) rather than shrinking in silence". **No
#: such stat existed** — the name appeared in this docstring and nowhere in the
#: code. It does now (:data:`_STAT_TIER1_POOL_HIT`, set by :func:`_scan_candidates`),
#: because raising a limit while trusting a breach signal that was never built
#: is how the next silent starvation gets written.
#: 🔴 THE LIQUID POOL IS THIRD AND IT IS ORDERED BY THE THING THAT ADMITS IT
#: (#5781). Its rows have NO volume by definition, so ordering it by volume would
#: order it by nothing: a stable arbitrary order under a binding limit is the
#: fixed point the tier-1 note above describes. ``liquidity DESC`` is the only
#: value key these rows have, and it is the one the arm selected on.
#:
#: Population 2026-09-12, measured by running the arm itself rather than by
#: adding up a census: **1,009**, all Polymarket. 2,000 leads it by 50%, which is
#: the headroom the value pool's 3% is a named risk for.
VALUE_POOL_LIMIT = 4_500
TIER1_POOL_LIMIT = 4_000
LIQUID_POOL_LIMIT = 2_000


def pool_bind_params() -> dict:
    """Every bind :data:`ELIGIBLE_POOL_SQL` needs, in ONE place (#5781).

    🔴 THIS EXISTS BECAUSE THE THIRD ARM'S BIND WAS FORGOTTEN AT A SITE NO LOCAL
    TEST COULD REACH. ``HIGH_VALUE_SQL`` is composed by the PG-only integration
    suite, which does not run without a database, so the missing
    ``:liquidity_floor`` surfaced as ``InvalidRequestError`` in CI and nowhere
    else. A missing bind does not degrade — SQLAlchemy refuses the statement —
    and in the task's ``remaining_stale`` census it would do so inside a ``try``
    that then reports a number about nobody.

    The guard written first was a text scan asserting the parameter NAME appears
    in each composing file. It passed on a mutant that deleted the bind from the
    pool dict, because the same string appears three more times in that file for
    other reasons. A text test cannot tell WHICH dict holds a key. So the bind
    set is a value now, and the sites take it whole: adding a fourth arm's bind
    here reaches every caller, which is the same argument ``LIVE_MARKET_SQL``
    and ``ELIGIBLE_POOL_SQL`` are one string for.
    """
    return {
        "volume_floor": HIGH_VALUE_VOLUME_FLOOR,
        "liquidity_floor": POSTED_LIQUIDITY_FLOOR,
        "value_pool_limit": VALUE_POOL_LIMIT,
        "tier1_pool_limit": TIER1_POOL_LIMIT,
        "liquid_pool_limit": LIQUID_POOL_LIMIT,
    }

#: Fraction of a pool limit that must remain unused for the pool to be
#: considered safely sized. Read in two places on purpose: the guard test
#: asserts it against the production populations recorded above, and
#: :func:`_scan_candidates` asserts it against the population *at run time*.
#:
#: A CI constant can only ever catch someone LOWERING a limit; it cannot see a
#: population growing underneath a limit nobody touched, which is the way this
#: actually fails. Hence both.
_POOL_LIMIT_HEADROOM_MIN = 0.02

#: Stats keys set when a pool came back exactly at its limit — the LIMIT, not
#: the population, decided who was eligible. See :data:`TIER1_POOL_LIMIT`.
_STAT_TIER1_POOL_HIT = "tier1_pool_hit"
_STAT_VALUE_POOL_HIT = "value_pool_hit"
_STAT_LIQUID_POOL_HIT = "liquid_pool_hit"

#: 🔴 THE ONE THAT ARRIVES IN TIME. A ``*_pool_hit`` says the pool truncated,
#: which means markets were ALREADY starved on this run — it is a post-mortem,
#: not a warning. This fires while the pool is merely inside
#: :data:`_POOL_LIMIT_HEADROOM_MIN` of its limit, i.e. before anything is lost,
#: which is the only point at which raising the limit is still cheap.
_STAT_POOL_HEADROOM_LOW = "pool_headroom_low"

#: Polymarket ids per Gamma ``/events?id=..&id=..`` request. Verified against the
#: live API 2026-08-25: repeated ``id`` params return the full nested markets
#: payload for each event.
#:
#: 20 was Gamma's silent default page size, so this worked by coincidence rather
#: than by bound — see ``get_events_by_ids``, which now sends ``limit`` and
#: refuses over ``GAMMA_MAX_IDS_PER_REQUEST`` (#2637, measured 2026-09-02). Left
#: at 20 because nothing here needs it larger; it is now safe to raise.
POLYMARKET_ID_BATCH = 20

#: Wall budget, well under the task's 540s soft limit. Bounds the LOOP; each
#: individual HTTP call is separately bounded by the service clients' timeouts.
_TIME_BUDGET_S = 420.0

#: 🔴 THE POLYMARKET LOOP'S OWN SHARE OF THAT WALL, and it exists because
#: splitting the market budget per source did not finish the job.
#:
#: The two loops run in sequence, Polymarket first, against ONE clock. So a
#: per-source *market* budget bounds how many rows each source may take and
#: bounds nothing about how much of the RUN each source may consume: a slow
#: Gamma spends the whole 420s inside the first loop and the Kalshi loop — the
#: larger backlog, 2,010 rows against 1,974 — never executes at all. That is the
#: same starvation this module exists to end, reintroduced one level up from
#: where it was fixed.
#:
#: 180s against a measured worst case of 78s (1,200 markets, 60 batched Gamma
#: calls). It is deliberately more than twice the observed need, so it never
#: binds in normal operation and is purely a bound on the pathological case; and
#: it leaves the Kalshi loop at least 240s against its measured 175s. Both loops
#: still honour the whole-run budget, so this only ever makes the first loop stop
#: EARLIER — it can never let a run overrun.
_POLYMARKET_WALL_BUDGET_S = 180.0

_ATTEMPT_KEY_PREFIX = "bainluck:futures_price_refresh:attempted:"


def _attempt_key(market_id: int) -> str:
    return f"{_ATTEMPT_KEY_PREFIX}{market_id}"


# --- selection ---------------------------------------------------------------

#: ``NOT EXISTS`` with a time bound rather than ``MAX(captured_at)``: the
#: aggregate form timed out at 10s in production over the 179M-row snapshot
#: table, because it must read every snapshot for every candidate. The EXISTS
#: form rides ``idx_fos_outcome_captured`` (outcome_id, captured_at) and stops at
#: the first row inside the window.
#: The Gamma **event** id, which is not always ``external_id``.
#:
#: The reconciliation itself moved to
#: :data:`app.utils.polymarket_settlement_scan.GAMMA_EVENT_ID_EXPR` when #2637's
#: resolved-status sweep needed the same mapping. Two copies of "which Gamma
#: event answers for this row" is how settlement truth drifts, so there is one,
#: and this is the source-guarded, aliased form of it.
_POLY_EVENT_ID_SQL = f"""
        CASE WHEN fm.source = 'polymarket' THEN {GAMMA_EVENT_ID_EXPR} END
            AS poly_event_id
"""

#: 🔴 THE ELIGIBLE POPULATION, AS A CTE, AND BOTH SIDES OF THE INVARIANT USE IT.
#:
#: THREE POOLS, ONE PER VALUE REASON, and they are separate because the three
#: populations cannot be ordered by one key. A single ``ORDER BY fm.volume DESC
#: NULLS LAST`` over them would sort every row whose volume we do not have
#: BELOW every row whose volume we do, so an arm added to admit them would be
#: truncated out of existence by the arm it was added beside — a shared bound
#: over unequal populations, the same shape as the shared market budget the
#: per-source budgets replaced.
#:
#: The tier-1 pool orders by ``fm.id``: there is no value key to sort on, and
#: an oldest-capture ordering is the fixed point the module docstring forbids. A
#: stable ordering is safe here BECAUSE the pool limit exceeds the population, so
#: the Redis attempt markers — not the SQL — do the rotating.
#:
#: The liquid pool (#5781) orders by ``fm.liquidity DESC``, which is the key that
#: admitted it and the only value key its rows have. The same note applies: the
#: limit leads the population (2,000 over 1,009), so the ordering is a preference
#: and not a fence.
#:
#: 🔴 THE THREE ARMS ARE NAMED CTEs RATHER THAN AN INLINE ``UNION`` SO THEIR SIZES
#: CAN BE READ. The union semantics are unchanged — still ``UNION`` (not ALL) on
#: the id alone, which matters more since #5268 than it did before: a tier-1
#: market whose volume clears the floor now satisfies BOTH arms, and the dedupe
#: is what keeps it one candidate instead of two. What the names buy is
#: ``count(*)`` per arm out of an ALREADY MATERIALIZED CTE — free, where a
#: second scan to ask "did the limit bind?" would cost the ~12 s the pools exist
#: to avoid paying twice. See :data:`_STAT_TIER1_POOL_HIT`.
#:
#: It is one shared string rather than a shape each side re-types for exactly the
#: reason ``LIVE_MARKET_SQL`` is: the task refreshes this set and
#: ``/api/admin/source-health/futures-price-freshness`` asserts over it, and a
#: guard covering a different population than the fix is how a breach reads
#: green. Callers bind ``:volume_floor``, ``:liquidity_floor``,
#: ``:value_pool_limit``, ``:tier1_pool_limit`` and ``:liquid_pool_limit``, and
#: JOIN ``pool`` on ``fm.id``.
ELIGIBLE_POOL_SQL = f"""
    WITH value_pool AS MATERIALIZED (
          SELECT fm.id
            FROM futures_markets fm
           WHERE {LIVE_MARKET_SQL}
             AND {VALUE_MEASURED_SQL}
           ORDER BY fm.volume DESC
           LIMIT :value_pool_limit
    ),
    tier1_pool AS MATERIALIZED (
          SELECT fm.id
            FROM futures_markets fm
           WHERE {LIVE_MARKET_SQL}
             AND {VALUE_TIER1_SQL}
           ORDER BY fm.id
           LIMIT :tier1_pool_limit
    ),
    liquid_pool AS MATERIALIZED (
          SELECT fm.id
            FROM futures_markets fm
           WHERE {LIVE_MARKET_SQL}
             AND {VALUE_LIQUID_SQL}
           ORDER BY fm.liquidity DESC
           LIMIT :liquid_pool_limit
    ),
    pool AS MATERIALIZED (
        SELECT id FROM value_pool
        UNION
        SELECT id FROM tier1_pool
        UNION
        SELECT id FROM liquid_pool
    )
"""

#: 🔴 THE OUTER ORDERING IS THE LIQUID ARM'S WHOLE SAFETY ARGUMENT (#5781).
#:
#: ``fm.volume DESC NULLS LAST`` is unchanged and it is doing the work: every row
#: the liquid arm adds has ``volume IS NULL`` by construction, so all 971 net-new
#: ones sort BEHIND every measured market in the list :func:`_take_for_source`
#: slices. The new arm therefore cannot displace a single measured market from a
#: run's budget — it can only spend budget the measured population did not need.
#: The rotation that eventually reaches it is the Redis attempt marker plus the 6h
#: capture anti-join, exactly as for the tier-1 tail, and the arithmetic still
#: holds: Polymarket's backlog grows ~1,974 -> ~2,825 against ``1,200 x 6 =
#: 7,200``.
#:
#: 🔴 AND POSTGRES'S DEFAULT IS THE OPPOSITE OF THE ONE A TEST WILL TELL YOU.
#: ``DESC`` sorts NULLs FIRST in Postgres and LAST in sqlite, so the two words
#: ``NULLS LAST`` are the entire safety argument AND a sqlite-backed guard cannot
#: see them go. Deleting them moves all 971 rows to the FRONT of the budget.
#: ``test_the_volume_key_says_nulls_last_in_words`` is a text assertion for that
#: reason and demonstrates the inversion in its own body.
#:
#: The two new tiebreakers order a tail that was previously ARBITRARY. Every
#: NULL-volume row — the tier-1 ones since #5268 and the liquid ones now — used to
#: come back in whatever order the plan produced, which under a binding budget is
#: an unstated lottery. ``liquidity DESC NULLS LAST, id`` makes it the same value
#: key the arm selected on, then deterministic. It cannot touch a measured row's
#: position: those are separated by the first key before the second is read.
_CANDIDATE_SQL = text(
    f"""
    {ELIGIBLE_POOL_SQL}
    SELECT fm.id, fm.source, fm.external_id, fm.volume,
           {_POLY_EVENT_ID_SQL},
           fm.market_metadata->>'{VENUE_SETTLED_KEY}' AS venue_settled_since,
           (SELECT count(*) FROM value_pool) AS value_pool_size,
           (SELECT count(*) FROM tier1_pool) AS tier1_pool_size,
           (SELECT count(*) FROM liquid_pool) AS liquid_pool_size
      FROM futures_markets fm
      JOIN pool ON pool.id = fm.id
     WHERE NOT EXISTS (
             SELECT 1
               FROM futures_outcomes fo
               JOIN futures_odds_snapshots s ON s.outcome_id = fo.id
              WHERE fo.market_id = fm.id
                AND s.captured_at > NOW() - make_interval(hours => :stale_hours)
           )
     ORDER BY fm.volume DESC NULLS LAST, fm.liquidity DESC NULLS LAST, fm.id
    """
)

#: Registered markets, selected by identity instead of by value.
#:
#: No tier bound and no volume floor — that is the entire point, and both
#: omissions are load-bearing rather than lax. The liveness bounds are kept
#: verbatim from the class query: ``status='open'`` plus a future resolution date
#: (gotcha #33 — a settled Kalshi market keeps ``status='open'``, so the date is
#: what actually keeps the dead out of the queue), so this arm cannot re-animate
#: the stale-open population the US Open slate census fenced off.
#:
#: The set is bounded by what is committed on disk, not by anything a market can
#: do to itself, so no upstream can grow it.
_BY_ID_CANDIDATE_SQL = f"""
    SELECT fm.id, fm.source, fm.external_id, fm.volume,
           {_POLY_EVENT_ID_SQL},
           fm.market_metadata->>'{VENUE_SETTLED_KEY}' AS venue_settled_since
      FROM futures_markets fm
     WHERE fm.id = ANY(:market_ids)
       AND {LIVE_MARKET_SQL}
       AND NOT EXISTS (
             SELECT 1
               FROM futures_outcomes fo
               JOIN futures_odds_snapshots s ON s.outcome_id = fo.id
              WHERE fo.market_id = fm.id
                AND s.captured_at > NOW() - make_interval(mins => :stale_minutes)
           )
     ORDER BY fm.id
"""

_REGISTERED_CANDIDATE_SQL = text(_BY_ID_CANDIDATE_SQL)

#: 🔴 THE ARM THAT ANSWERS THE READER'S QUESTION (#3315).
#:
#: The two arms above select on value and on curation. Neither asks the only
#: question a wrong number on a card actually raises — *is anybody looking at
#: this* — and that is why the front page could carry a 13.7-point error for
#: 46 days behind a green sweep. This arm's membership is the set of futures
#: markets the Discover and Sports first-paint payloads LAST RENDERED, read back
#: from the pre-warmer that built them
#: (:mod:`app.utils.feed_served_markets`).
#:
#: Same statement as the registered arm, deliberately: no tier bound, no volume
#: floor, the liveness bounds kept verbatim, a short producer clock. It is
#: literally the same string, so the two identity arms cannot drift into two
#: different ideas of what "reachable by id" means; only the id list and the
#: window differ.
#:
#: It is a SUPERSET-safe arm. A market that has since rotated off page one costs
#: one re-price of a live market; a market that is on page one and outside every
#: other arm is the whole defect.
_SERVED_CANDIDATE_SQL = text(_BY_ID_CANDIDATE_SQL)


#: The arm a candidate came in on. ``class`` is the value sweep; the other two
#: are identity arms. Kept as a NAME rather than as a pair of booleans because
#: three of the run's decisions read it and each wants a different grouping:
#: head-position and the attempt TTL want "identity, either kind"
#: (``priority``), while the stats want the two apart — a served row counted as
#: ``registered_priced`` would make the tournament arm's own coverage number
#: unreadable.
_ARM_CLASS = "class"
_ARM_REGISTERED = "registered"
_ARM_SERVED = "served"


def _rows_to_markets(rows, *, arm: str) -> list[dict]:
    """The six market columns, however many the statement selected.

    The class arm's statement trails two pool-size columns (see
    :data:`_STAT_TIER1_POOL_HIT`) that the identity arms do not have, so this
    slices to the six it needs rather than destructuring the whole row. A fixed
    six-tuple unpack here would make adding a diagnostic column to one statement
    a runtime unpack error in the two that never changed.
    """
    return [
        {
            "id": mid,
            "source": source,
            "external_id": external_id,
            "volume": volume,
            "poly_event_id": poly_event_id,
            # Carried so a successful write knows whether there is a stamp to
            # clear, and can skip the UPDATE for the ~900 markets that never had
            # one. Selected, not re-queried.
            "venue_settled_since": venue_settled_since,
            "arm": arm,
            "registered": arm == _ARM_REGISTERED,
            "served": arm == _ARM_SERVED,
            # Identity arms are never truncated by a budget and always sort to
            # the head of their source loop.
            "priority": arm != _ARM_CLASS,
        }
        for (
            mid,
            source,
            external_id,
            volume,
            poly_event_id,
            venue_settled_since,
        ) in (tuple(row)[:6] for row in rows)
    ]


# --- the venue-settled stamp --------------------------------------------------

#: FIRST observation only. Without ``IS NULL`` every run would push the stamp
#: forward and the confirmation window could never elapse — the market would be
#: retried forever, which is precisely the state #2222 describes.
_STAMP_VENUE_SETTLED_SQL = text(
    f"""
    UPDATE futures_markets
       SET market_metadata = COALESCE(market_metadata, '{{}}'::jsonb)
             || jsonb_build_object('{VENUE_SETTLED_KEY}', {VENUE_SETTLED_NOW_SQL})
     WHERE id = :mid
       AND market_metadata->>'{VENUE_SETTLED_KEY}' IS NULL
    """
)

#: A price arrived, so whatever the venue said before is no longer true. Clearing
#: is what makes the bound reversible without anyone intervening, and it is why a
#: transient upstream outage costs a market nothing.
_CLEAR_VENUE_SETTLED_SQL = text(
    f"""
    UPDATE futures_markets
       SET market_metadata = market_metadata - '{VENUE_SETTLED_KEY}'
     WHERE id = :mid
       AND market_metadata->>'{VENUE_SETTLED_KEY}' IS NOT NULL
    """
)


async def _stamp_venue_settled(session, market_id: int) -> None:
    """Record that a source said this market is over. Core UPDATE, gotcha #4."""
    await session.execute(_STAMP_VENUE_SETTLED_SQL, {"mid": market_id})


async def _clear_venue_settled(session, market_id: int) -> None:
    await session.execute(_CLEAR_VENUE_SETTLED_SQL, {"mid": market_id})


async def _clear_if_stamped(session, market: dict, stats: dict) -> None:
    """A price landed, so retract any standing venue-settled claim.

    Guarded on the value the selector already read, so the ~900 markets that
    never carried a stamp cost no extra statement. Failure to clear must never
    lose the price that was just committed: the write is already durable at this
    point, and a stamp that survives one run is retracted by the next.
    """
    if not market.get("venue_settled_since"):
        return
    try:
        await _clear_venue_settled(session, market["id"])
        await session.commit()
        stats["venue_settled_cleared"] += 1
    except Exception as exc:
        await session.rollback()
        stats["errors"].append(f"clear venue-settled {market['external_id']}: {exc}")


async def _scan_candidates(
    session,
    *,
    volume_floor: int,
    stale_hours: int,
    value_pool_limit: int = VALUE_POOL_LIMIT,
    tier1_pool_limit: int = TIER1_POOL_LIMIT,
    liquid_pool_limit: int = LIQUID_POOL_LIMIT,
    liquidity_floor: int = POSTED_LIQUIDITY_FLOOR,
    stats: dict | None = None,
) -> list[dict]:
    """Stale valuable markets, most valuable first, at ANY tier.

    Scans wider than one run's budget on purpose: the caller then drops markets
    already attempted inside the staleness window, and without the headroom a run
    whose top-N were all just attempted would do nothing while the tail stayed
    dark. Since #3315 the headroom is the POOL rather than a ``scan_limit`` on
    the outer statement, because on this query an outer LIMIT bounded no work at
    all — see :data:`ELIGIBLE_POOL_SQL`.

    Records a pool-size stat per arm, and a ``*_pool_hit`` flag when an arm came
    back exactly at its limit — the state in which the LIMIT, not the population,
    decided who is eligible. That is reported rather than inferred because the
    two failures look identical from outside: a pool that returned everything and
    a pool that returned the first N of everything both just return N rows.

    🔴 ZERO ROWS IS NOT ZERO POOL. The sizes come off the pool CTEs, which are
    computed whether or not any market survives the staleness anti-join, but they
    can only be READ off a returned row. So an empty candidate list leaves the
    sizes unset rather than recording ``0`` — writing a zero here would report
    "the pools are empty" on the ordinary night when everything is simply fresh.
    """
    rows = (
        await session.execute(
            _CANDIDATE_SQL,
            {
                "volume_floor": volume_floor,
                "liquidity_floor": liquidity_floor,
                "stale_hours": stale_hours,
                "value_pool_limit": value_pool_limit,
                "tier1_pool_limit": tier1_pool_limit,
                "liquid_pool_limit": liquid_pool_limit,
            },
        )
    ).fetchall()
    # Length-guarded rather than assumed: the sizes are a DIAGNOSTIC, and a
    # diagnostic that can raise is a diagnostic that takes the sweep down with
    # it. `test_the_sizes_are_selected_from_the_materialised_pools` is what
    # holds the production statement to selecting them.
    if stats is not None and rows and len(rows[0]) > 8:
        value_size, tier1_size = int(rows[0][6]), int(rows[0][7])
        liquid_size = int(rows[0][8])
        stats["value_pool_size"] = value_size
        stats["tier1_pool_size"] = tier1_size
        stats["liquid_pool_size"] = liquid_size
        low = []
        for name, size, limit, hit_key in (
            ("value", value_size, value_pool_limit, _STAT_VALUE_POOL_HIT),
            ("tier1", tier1_size, tier1_pool_limit, _STAT_TIER1_POOL_HIT),
            ("liquid", liquid_size, liquid_pool_limit, _STAT_LIQUID_POOL_HIT),
        ):
            if size >= limit:
                stats[hit_key] = True
            elif size > limit * (1 - _POOL_LIMIT_HEADROOM_MIN):
                low.append(f"{name} {size}/{limit}")
        if low:
            stats[_STAT_POOL_HEADROOM_LOW] = ", ".join(low)
    return _rows_to_markets(rows, arm=_ARM_CLASS)


async def _scan_registered_candidates(
    session, *, market_ids: list[int], stale_minutes: int
) -> list[dict]:
    """Stale markets a committed tournament register renders, at any tier or volume."""
    if not market_ids:
        return []
    rows = (
        await session.execute(
            _REGISTERED_CANDIDATE_SQL,
            {"market_ids": market_ids, "stale_minutes": stale_minutes},
        )
    ).fetchall()
    return _rows_to_markets(rows, arm=_ARM_REGISTERED)


async def _scan_served_candidates(
    session, *, market_ids: list[int], stale_minutes: int
) -> list[dict]:
    """Stale markets page one is rendering right now, at any tier or volume."""
    if not market_ids:
        return []
    rows = (
        await session.execute(
            _SERVED_CANDIDATE_SQL,
            {"market_ids": market_ids, "stale_minutes": stale_minutes},
        )
    ).fetchall()
    return _rows_to_markets(rows, arm=_ARM_SERVED)


#: How many served ids this task CAN price. The unreachable count is derived
#: from it by subtraction, and the subtraction is the point.
#:
#: A ``GROUP BY reason`` over the ids would omit every id that matches no row at
#: all — the shape a bug in the payload walker produces — because a row that does
#: not exist cannot appear in a grouping of rows. Counting what is reachable and
#: subtracting from the list length catches both failure modes at once: an id
#: that names no futures market, and one that names a market this task may not
#: price (an ``odds_api`` row such as the tier-1 NFL Super Bowl Winner field on
#: page one, or a market the liveness bounds retired). The second is a real gap
#: in the page-one guarantee. It is just not one this task can close, and saying
#: so with a number beats leaving a card wrong with no trace.
_SERVED_REACHABLE_SQL = text(
    f"""
    SELECT COUNT(*)
      FROM futures_markets fm
     WHERE fm.id = ANY(:market_ids)
       AND {LIVE_MARKET_SQL}
    """
)


def _take_for_source(candidates: list[dict], source: str, budget: int) -> list[dict]:
    """This source's markets: every identity row, then the class up to ``budget``.

    Two properties, and the second is why this is a function rather than a slice:

    * **Identity rows are taken before the cap**, so a priority row can only be
      dropped by the wall clock. Under one shared budget, head position was
      enough; under two, an interleaved ``[:budget]`` would silently make the
      guarantee depend on how many class rows happened to sort in front.
    * **Identity rows lead the returned list**, which is what the source loops
      need — both stop on the wall clock, so position is the ordering guarantee.

    A budget below the identity count does NOT drop identity rows. That is
    deliberate: the budget bounds the discretionary sweep, and the whole point of
    an identity arm is that its membership is not discretionary. It is bounded by
    the page and by the register, not by this number.
    """
    priority = [m for m in candidates if m["source"] == source and m["priority"]]
    klass = [m for m in candidates if m["source"] == source and not m["priority"]]
    return priority + klass[: max(0, budget - len(priority))]


def _load_attempt_skips(market_ids: list[int]) -> set[int]:
    """Market ids attempted inside the current staleness window.

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
    except Exception:
        return set()
    return {mid for mid, val in zip(market_ids, values) if val}


def _mark_attempted(market_ids: list[int], ttl_seconds: int) -> None:
    """Record an ATTEMPT, not a success.

    A market whose book cannot be priced would otherwise return to the head of
    the queue on every single run and starve the tail behind it — the same
    fixed-point failure the volume ordering above avoids.
    """
    if not market_ids:
        return
    try:
        from app.tasks.redis_state import get_redis_client

        rc = get_redis_client(socket_timeout=2.0, socket_connect_timeout=2.0)
        pipe = rc.pipeline()
        for mid in market_ids:
            pipe.setex(_attempt_key(mid), ttl_seconds, "1")
        pipe.execute()
    except Exception:
        pass


# --- writing -----------------------------------------------------------------


async def _write_prices(
    session,
    market_id: int,
    bookmaker: str,
    priced: list[dict],
    stats: dict,
) -> int:
    """Write price columns + one snapshot per outcome. Returns snapshots written.

    ``priced`` items: ``external_id``, ``probability``, ``yes_bid``, ``yes_ask``,
    ``last_price``, and optionally a ``no`` sub-dict of the same shape.

    TWO OUTCOME-ID CONVENTIONS, ONE WRITER. ``external_id`` on a priced item is
    the provider's own market key (a Kalshi ticker, a Polymarket condition id).
    How that key appears in ``futures_outcomes`` depends on which ingest branch
    minted the row:

    * **bare** — Kalshi tickers, and the outcomes of a Polymarket negRisk field
      (``0x…``, one outcome per contender).
    * **suffixed** — the legs of a decomposed Polymarket binary, written
      ``{condition_id}_yes`` / ``{condition_id}_no`` by the sub-market branch of
      ``tasks/polymarket.py``.

    Matching only the bare form is why every curated prop counted as
    ``unknown_outcomes``: the price arrived, found no row named after it, and was
    discarded — a refusal that looked exactly like "we do not hold this market".
    A market row carries one convention or the other, never both, so resolving
    bare-then-suffixed cannot double-write.

    Three refusals, each load-bearing:

    * **Never creates an outcome.** An id we do not already hold is discovery's
      job; creating one here would let a price-only path mint identity with no
      categorisation, tier or grouping. Counted as ``unknown_outcomes`` so the
      refusal is visible rather than silent.
    * **Never touches a settled outcome** — crowned (``is_winner`` TRUE) *or*
      graded a loser by the venue's own settlement feed. Gotcha #21: a settled
      book stops quoting, and re-pricing it can only corrupt resolved state.

      🔴 THE LOSER HALF WAS MISSING AND IT IS #5246. ``is_winner IS NOT TRUE`` is
      a test for a CROWN, not for a GRADE: a leg the venue resolved NO carries
      ``is_winner = FALSE``, so it passed this filter and stayed eligible for
      re-pricing forever. Nothing has re-priced one yet only because the venue
      declines to quote a finalized contract — measured 2026-09-11 17:2xZ,
      ``GET /events/KXATP-26USO?with_nested_markets=true`` returns all 48 US Open
      men's markets and every ``finalized`` one carries ``yes_bid: null,
      yes_ask: null, last_price: null``. That is the VENUE's grace, not our
      guard, and a guard that holds only because the other side stayed quiet is
      one nobody can prove still works. ``resolution_source`` is the grade's own
      column, so the refusal is written against it directly.

      Scoped to ``api_settlement`` deliberately, and not to "any non-NULL
      ``resolution_source``". Most of the other sources are INFERENCES —
      ``pass2_guess``, ``multi_max_prob``, ``binary_higher_wins`` and the rest of
      ``OVERWRITABLE_WINNER_SOURCES_SQL`` are guesses the system is allowed to
      change its mind about — and a live quote is better evidence than a guess.
      ``api_settlement`` is the one source that is the venue saying the contract
      is over, which is the only case where a quote could not be an improvement.

      The predicate is ``IS NOT TRUE``, not ``IS NULL``, and the difference is
      the whole of #2199's first live failure. ``FuturesOutcome.is_winner``
      carries ``default=False`` (models.py), so **effectively no production row
      is NULL** — unsettled is stored as ``FALSE``. Measured across every
      eligible tier-1 open market at the time: 0 NULL, 10,762 FALSE, 42 TRUE;
      table-wide on 2026-08-31 the NULLs are 2,536 of 3,893,126, and every one
      of them also has a NULL ``resolution_source``. (The column is *nullable* —
      the model said otherwise until CAL-P157 corrected it — which is exactly
      why the predicate below must stay tri-state-safe.) A NULL test therefore
      matched nothing, every priced item
      fell through to ``unknown_outcomes``, and the task wrote zero snapshots by
      construction and permanently. ``IS NOT TRUE`` keeps the settled refusal
      against the tri-state that actually exists.
    * **Never writes a NULL probability.** Gotcha #19 / the Kalshi spread guard:
      "no price" is refused upstream, and a refusal must not arrive here as a
      write.
    """
    from app.models.models import FuturesOddsSnapshot, FuturesOutcome
    from app.utils.odds_math import probability_to_american
    from app.utils.price_change_stamp import price_changed_at_value
    from sqlalchemy import func, update as sa_update

    if not priced:
        return 0

    existing = {
        row[1]: row[0]
        for row in (
            await session.execute(
                text(ELIGIBLE_OUTCOMES_SQL),
                {"mid": market_id},
            )
        ).fetchall()
    }

    def _legs(item: dict) -> list[tuple[int, dict]]:
        """``(outcome_id, side)`` pairs, in whichever convention this market holds."""
        key = item["external_id"]
        bare = existing.get(key)
        if bare is not None:
            return [(bare, item)]
        legs: list[tuple[int, dict]] = []
        yes_id = existing.get(f"{key}_yes")
        if yes_id is not None:
            legs.append((yes_id, item))
        no_id = existing.get(f"{key}_no")
        no_side = item.get("no")
        if no_id is not None and no_side:
            legs.append((no_id, no_side))
        return legs

    now = datetime.now(timezone.utc)
    written = 0
    for item in priced:
        prob = item.get("probability")
        if prob is None or not (0 < prob < 1):
            continue

        legs = _legs(item)
        if not legs:
            stats["unknown_outcomes"] += 1
            continue

        for outcome_id, side in legs:
            side_prob = side.get("probability")
            if side_prob is None or not (0 < side_prob < 1):
                continue
            american = probability_to_american(side_prob)
            await session.execute(
                sa_update(FuturesOutcome)
                .where(FuturesOutcome.id == outcome_id)
                .values(
                    current_probability=side_prob,
                    current_american_odds=american,
                    current_yes_bid=side.get("yes_bid"),
                    current_yes_ask=side.get("yes_ask"),
                    last_updated=func.now(),
                    # #2024: `last_updated` records that a poll RAN; this records
                    # that the price MOVED. Both matter and they are not the same.
                    price_changed_at=price_changed_at_value(
                        FuturesOutcome.current_probability,
                        FuturesOutcome.price_changed_at,
                        side_prob,
                    ),
                )
            )
            await session.execute(
                pg_insert(FuturesOddsSnapshot).values(
                    outcome_id=outcome_id,
                    bookmaker=bookmaker,
                    probability=side_prob,
                    american_odds=american,
                    yes_bid=side.get("yes_bid"),
                    yes_ask=side.get("yes_ask"),
                    last_price=side.get("last_price"),
                    captured_at=now,
                )
            )
            written += 1

    return written


# --- source adapters ---------------------------------------------------------


def _venue_answered(result) -> bool:
    """Has Kalshi declared this contract's outcome?

    ``result`` is ``'yes'`` / ``'no'`` once the venue settles and the EMPTY
    STRING while the contract trades — not ``None``. So the test is truthiness
    after a strip, never ``is not None``: `result is not None` is true of every
    active market Kalshi sends and would retire the whole book.

    Read off whichever shape the caller holds (raw dict value or the parsed
    ``KalshiMarket.result``); both carry the venue's own word verbatim.
    """
    return bool(str(result or "").strip())


async def _fetch_kalshi_prices(service, external_id: str):
    """Prices for one Kalshi event ticker.

    Three returns, because there are three different facts (see
    :class:`_VenueSettled`):

    * ``None`` — the event could not be read at all (404, or a parse failure).
    * :data:`VENUE_SETTLED` — the event reads fine and the venue says the
      contest is over. TWO shapes say that, and the second is #5771's:

      1. it **carries no markets**. Kalshi keeps event rows forever and purges
         market rows (gotcha #35), so an event with an empty book is a settled
         contest whose book has aged out, and no number will ever come back
         from it. Measured 2026-08-30 on all eighteen Kalshi rows in #2222's
         population: HTTP 200, zero markets, unanimous. The control that makes
         that reading mean something is ``KXSB-27`` (live, 73M volume, same
         unauthenticated call): **32** markets.
      2. **every market it carries has a declared** ``result``. Between
         settlement and the purge there is a 74-to-86-day window (gotcha #35)
         in which the venue still LISTS the book and has already answered it.
         A finalized Kalshi market quotes ``yes_bid 0.0000 / yes_ask 1.0000``,
         which is the empty book — and ``_kalshi_yes_probability`` deliberately
         falls THROUGH that to the last trade (see its own docstring: the
         fall-through is load-bearing for ``kalshi_resolution_sweep``). So the
         settlement artifact ``0.0100`` / ``0.9900`` arrives here wearing the
         shape of a price, and we wrote it.

    * a list — the venue has a book; the list holds whatever survived the price
      guards, and may be empty if every quote was refused.

    🔴 WHAT (2) COSTS A READER, measured on production 2026-09-12 22:2xZ. Of the
    24 events kicking off in the future whose stored Kalshi blend leg sat at
    <=2% or >=98%, a venue read of all 24 tickers split them cleanly:

    * **13 NCAAF events read** ``status=active``\\ **, two-sided books, real
      24h volume** — LSU 99.5% over Louisiana Tech is a genuine blowout line and
      must not move. They are the control, and they are why the test here is the
      venue's ``result`` and not "the ladder looks extreme".
    * **10 read** ``status=finalized``\\ **, every rung at 0.00 bid / 1.00 ask,
      a declared result on every market.** `KXLALIGAGAME-26SEP13SEVVCF` settled
      2026-09-11T21:34Z for a game its own rules call "originally scheduled for
      Sep 13", and bainluck.com/events/15298125 served **99% – 1%** under a
      "Sep 13, 2026 · 12:00 PM PDT" header for a match that had not kicked off.

    The emptiness is read off the RAW payload, not off ``event.markets``, and so
    is the answered test. ``_parse_market`` drops a market it cannot parse, so a
    parsed-empty list is ambiguous between "no book" and "we failed to read the
    book" — and calling a parse failure a settlement is how a live market gets
    retired quietly. The same asymmetry applies to (2): deciding "the whole
    event is answered" over the parsed subset would let one dropped live market
    turn a mixed event into a settlement.

    A MIXED event is not a settlement. Kalshi settles a game's legs together,
    but a series event can hold both, so the answered markets are skipped
    individually and the rest are priced — the per-leg care CERT-751 already
    forced on the Polymarket resolved-status sweep, for the same reason.

    Two deliberate reuses rather than reimplementations:

    * ``service._parse_event`` for the payload. Kalshi v2 quotes prices in TWO
      formats — ``yes_bid_dollars`` as a decimal string, or legacy ``yes_bid`` as
      integer cents — and ``_parse_market`` already resolves the pair. Reading
      the raw dict here would mean re-deriving that, and a ``95`` arriving where
      ``0.95`` is expected is a coherent-looking wrong price, the worst kind.
    * ``_kalshi_yes_probability`` for the price itself — the same spread /
      one-sided-book guard the main poll applies, so this path cannot fabricate a
      price the poll would have refused. It is NOT touched here: its empty-book
      fall-through is depended on elsewhere, so the settled market is removed
      from its input rather than the helper taught a new refusal.
    """
    from app.tasks.kalshi import _kalshi_yes_probability

    raw = await service.get_event(external_id, with_nested_markets=True)
    if not raw:
        return None
    raw_markets = raw.get("markets") or []
    if not raw_markets:
        return VENUE_SETTLED
    # #5771 shape (2). Over the RAW list, for the reason the docstring gives.
    if all(_venue_answered(m.get("result")) for m in raw_markets):
        return VENUE_SETTLED
    event = service._parse_event(raw)
    if not event:
        return None

    priced: list[dict] = []
    for market in event.markets:
        if not market.ticker:
            continue
        if _venue_answered(market.result):
            # A mixed event's answered leg. Its quote is a settlement artifact,
            # not a price — see the docstring.
            continue
        prob = _kalshi_yes_probability(
            market.yes_bid, market.yes_ask, market.last_price
        )
        if prob is None:
            continue
        priced.append(
            {
                "external_id": market.ticker,
                "probability": prob,
                "yes_bid": market.yes_bid,
                "yes_ask": market.yes_ask,
                "last_price": market.last_price,
            }
        )
    return priced


#: Which outcomes of a market may be re-priced by a poll — the settled refusal,
#: in the one place that decides it.
#:
#: Both clauses are about SETTLEMENT and neither implies the other. ``is_winner
#: IS NOT TRUE`` refuses a CROWN; ``resolution_source IS DISTINCT FROM
#: 'api_settlement'`` refuses a GRADE, which is the half #5246 was missing — a
#: leg the venue resolved NO carries ``is_winner = FALSE`` and sailed through the
#: crown test. See `_write_prices`' docstring for the measurement and for why the
#: refusal names ``api_settlement`` alone rather than any non-NULL source.
#:
#: ``IS DISTINCT FROM`` and not ``!=``: ``resolution_source`` is nullable and an
#: ungraded row holds NULL, which ``!= 'api_settlement'`` evaluates to NULL —
#: falsy — so the plain inequality would refuse to price EVERY ungraded outcome
#: in the table. That is the tri-state trap this same predicate already records
#: for ``is_winner`` two clauses along, and it fails in the opposite direction:
#: silently pricing nothing rather than silently pricing everything.
ELIGIBLE_OUTCOMES_SQL = (
    "SELECT id, external_id FROM futures_outcomes "
    "WHERE market_id = :mid AND is_winner IS NOT TRUE "
    "AND resolution_source IS DISTINCT FROM 'api_settlement'"
)


#: Legs that claim CERTAINTY on a contract nobody has graded (#4253).
#:
#: Three conditions, and the third is the one that took the measuring:
#:
#: * ``current_probability = 1.0`` — not "near 1", exactly 1. A leg the venue
#:   quotes at 0.99 is a PRICE; 1.0 uncrowned is a claim of certainty with no
#:   result behind it, which is the thing #4253 is about.
#: * ``is_winner IS NOT TRUE`` — a crowned leg's 1.0 is its settlement.
#: * **the market has no crowned outcome at all.** Grading has never touched
#:   this market, so a 1.0 here cannot be a grading MISS — there is nothing to
#:   have missed. Where grading demonstrably runs, a 1.0 uncrowned is most often
#:   an ungraded YES whose price is the last surviving trace of the result, and
#:   withdrawing it would destroy information rather than restore truth.
#:
#: That third clause is a refusal, and the refusal is the safety argument.
#: Measured on production 2026-09-09 over the reachable Kalshi cohort: 41 legs
#: match the first two conditions, and this clause REFUSES 18 of them across five
#: markets — *Who will release a new song this year?* (12 legs beside 47 crowned
#: siblings: Don Toliver, Charlie Puth, BLACKPINK, Harry Styles), *top 20 song*
#: (3 beside 10), *#1 hit* (1 beside 4), *Texas gas prices* (1 beside 3),
#: *Nasdaq-100* (1 beside 7). Every one of those is a plausible ungraded YES.
#: The 23 it admits, across nine markets, are IPO and product ladders with ZERO
#: crowned outcomes — *When will Starlink/OpenAI/Anduril/Stripe/Deel/Discord/
#: Oura/Fannie Mae announce an IPO?* and *What flavors will JUUL relaunch?* —
#: where a leg reading "Before Sep 1, 2025" at 100% is contradicted by the parent
#: market still being open.
#:
#: ``price_changed_at IS NULL`` is deliberately NOT a condition. It was in the
#: census that found this population and it is a no-op on it (41 of 41 also
#: satisfy it), so including it would narrow the rule by an accident of the
#: sample rather than by anything about truth.
_KALSHI_FROZEN_CERTAIN_SQL = text(
    """
    SELECT fo.market_id, fo.external_id
      FROM futures_outcomes fo
     WHERE fo.market_id = ANY(:market_ids)
       AND fo.current_probability = 1.0
       AND fo.is_winner IS NOT TRUE
       AND fo.external_id IS NOT NULL
       AND NOT EXISTS (
             SELECT 1
               FROM futures_outcomes crowned
              WHERE crowned.market_id = fo.market_id
                AND crowned.is_winner IS TRUE
           )
     ORDER BY fo.market_id, fo.external_id
    """
)

#: The withdrawal itself. Mirrors `polymarket._retire_unpriced_legs` field for
#: field — ``current_probability``/``current_american_odds`` and nothing else —
#: rather than calling it, because the two rules are not the same rule and
#: folding them would hide that. Polymarket's says *the venue serves this leg and
#: quotes no price*; this one says *the venue no longer serves this leg at all*.
#:
#: Deliberately NOT touched, for the reasons that helper records: ``is_winner``
#: (a grade is not a quote), ``opening_probability`` (calibration truth, a
#: different owner), and ``last_updated`` — stamping a withdrawal fresh would
#: advertise a current price at the exact moment we stopped having one, and this
#: column is rendered to readers as the card's own date.
#:
#: ``current_probability = 1.0`` is repeated here and not just in the SELECT: the
#: confirmation is a network round trip, so a live poll may have written a real
#: price to the row in between. Re-asserting it makes the write a
#: compare-and-set instead of a blind UPDATE keyed on a stale read.
#:
#: 🔴 SO IS THE CROWNED-SIBLING REFUSAL, AND IT IS THE CLAUSE THE FIRST VERSION
#: FORGOT (CERT-2394). The scan's three conditions are not three tests of one
#: row: two are about the candidate, and the third — *this market has no crowned
#: outcome at all* — is about its SIBLINGS, which is the entire safety argument
#: for admitting the row (it is why 18 of 41 production candidates are refused).
#: Re-checking only the candidate's own two columns therefore left the decisive
#: boundary racy: between the scan and this write sit up to
#: :data:`KALSHI_DELISTED_CHECK_BUDGET` venue round trips, and
#: `backfill_winners` runs every 6h against exactly these markets. Let it crown
#: a SIBLING inside that window and the candidate's own columns are still
#: 1.0/not-true, so the old statement retired it — erasing a leg in a
#: now-graded market, the precise class the rule promises to preserve.
#:
#: Repeating the ``NOT EXISTS`` here closes the window to the statement's own
#: snapshot: a crowning that committed before this UPDATE begins is visible to
#: it, so the refusal is decided on the state at WRITE time rather than on a
#: read that may be a minute old. The refusal is deliberately whole-market — one
#: crowned sibling withdraws nothing anywhere in the market, matching the scan.
_KALSHI_RETIRE_DELISTED_SQL = text(
    """
    UPDATE futures_outcomes
       SET current_probability = NULL,
           current_american_odds = NULL
     WHERE market_id = :market_id
       AND external_id = ANY(:tickers)
       AND current_probability = 1.0
       AND is_winner IS NOT TRUE
       AND NOT EXISTS (
             SELECT 1
               FROM futures_outcomes crowned
              WHERE crowned.market_id = :market_id
                AND crowned.is_winner IS TRUE
           )
 RETURNING id
    """
)

#: Did a crowned outcome appear in this market between the scan and the write?
#:
#: Asked ONLY when the compare-and-set above retired nothing, and asked purely so
#: the refusal is countable. Without it the race's outcome is indistinguishable
#: from "the venue re-listed everything" — both arrive as zero rows — and a
#: safety boundary nobody can see firing is one nobody can prove still works.
_KALSHI_MARKET_NOW_GRADED_SQL = text(
    """
    SELECT EXISTS (
             SELECT 1
               FROM futures_outcomes crowned
              WHERE crowned.market_id = :market_id
                AND crowned.is_winner IS TRUE
           )
    """
)


#: #5771's SECOND HALF: unfreeze the settlement artifact this market already left
#: on a game that has not kicked off.
#:
#: A gate that only refuses to WRITE leaves the old number exactly where it was —
#: the lesson #5031 and #5273 both paid for, and it applies here with force,
#: because the number the gate now refuses is the number already on the row. The
#: page renders ``futures_outcomes`` and ``events.win_probability_sources``, not
#: this task's verdict, so without this statement `_fetch_kalshi_prices`'s new
#: refusal changes nothing a reader sees.
#:
#: 🔴 THE EVENT'S OWN CLOCK IS THE WHOLE SCOPE, AND IT IS WHY THIS IS SAFE.
#: "Settled means settled" — a finished contest SHOULD carry its terminal legs,
#: and withdrawing those would delete the result the hero and the card are built
#: to show. This statement fires only where the linked event is still
#: ``scheduled`` with a ``commence_time`` in the FUTURE: a row asserting the
#: answer to a contest that has not happened is refuted by its own event row, no
#: venue read required. On a completed or live event it is inert by construction.
#:
#: ``is_winner`` IS NOT EXCLUDED, and that is deliberate rather than an oversight
#: copied past. `KXLALIGAGAME-26SEP13SEVVCF` carries ``is_winner = TRUE`` at
#: 0.9900 on a match kicking off the following day — the crown is exactly the
#: half that reaches the hero, so a ``is_winner IS NOT TRUE`` clause borrowed
#: from :data:`_KALSHI_RETIRE_DELISTED_SQL` would leave the 99% on the screen and
#: withdraw only the two 1% rungs beside it. The crown itself is left standing:
#: this withdraws a QUOTE, it does not ungrade anything (grading is
#: `kalshi_resolution_sweep`'s rail, and asserting "Sevilla won" a day early
#: would be a worse lie than the price).
#:
#: ``last_updated`` is not stamped, for the reason
#: :data:`_KALSHI_RETIRE_DELISTED_SQL` records: a fresh stamp advertises a
#: current price at the moment we stop having one.
_KALSHI_WITHDRAW_PRE_KICKOFF_SQL = text(
    """
    UPDATE futures_outcomes fo
       SET current_probability = NULL,
           current_american_odds = NULL
      FROM futures_markets fm
      JOIN events e ON e.id = fm.event_id
     WHERE fo.market_id = :market_id
       AND fm.id = :market_id
       AND fo.current_probability IS NOT NULL
       AND e.status = 'scheduled'
       AND e.commence_time > NOW()
 RETURNING fo.id
    """
)


#: CERT-2772's required repair, `5771-WITHDRAW-THE-EVENT-KALSHI-HERO`.
#:
#: 🔴 WITHDRAWING THE LEG IS NOT WITHDRAWING THE NUMBER A READER SEES. The event
#: hero and the chart do not read ``futures_outcomes`` — they read
#: :attr:`Event.win_probability_sources`, which the 15-minute matcher stamps from
#: those rows, and a stamped key is not re-derived just because its source row
#: went quiet. Measured on the specimen at 01:07Z: the leg became NULL and
#: `bainluck.com/events/15298125` went on serving **99%** under a "Sep 13" header.
#: The statement above is the price; this one is the page.
#:
#: THE KEY IS REMOVED, NOT ZEROED, AND IT NAMES ITS OWN WRITER. The stored entry
#: carries the market that wrote it —
#: ``{'kalshi': {'value': 0.99, 'eligibility': {'market_id': 60482102, …}}}`` on
#: the specimen — so "is this the speaker we just silenced?" is a fact on the row
#: rather than an inference. A different valid Kalshi speaker (a second linked
#: Kalshi market, still quoting) writes its own ``market_id`` there and is
#: untouched by the first arm. The second arm is for the pre-attribution shape:
#: no ``market_id`` to check, so the key goes only when NO Kalshi market on the
#: event still holds a readable price. It runs after the withdrawal above, in the
#: same transaction, so "still holds a price" already excludes what we just
#: withdrew.
#:
#: Removal rather than a zero or a flag because the blend's vocabulary is
#: membership: :func:`compute_aggregate_probability` weighs the keys that are
#: there (kalshi 0.8), and every other value would be a number we do not have.
#: With the key gone the hero falls to the sources that are still speaking —
#: on the specimen, the 0.5856 opening line rather than a 99% settlement.
#:
#: SCOPED BY THE EVENT'S OWN CLOCK, exactly as its sibling is: a contest that has
#: already started or finished SHOULD carry its terminal number ("settled means
#: settled"), and this is inert there by construction. It never touches
#: ``polymarket``, ``betting``, ``espn`` or the ``betting_book_count`` metadata
#: key, and it never writes a probability.
_KALSHI_WITHDRAW_EVENT_HERO_SQL = text(
    """
    UPDATE events e
       SET win_probability_sources = e.win_probability_sources - 'kalshi'
      FROM futures_markets fm
     WHERE fm.id = :market_id
       AND e.id = fm.event_id
       AND e.status = 'scheduled'
       AND e.commence_time > NOW()
       AND jsonb_exists(e.win_probability_sources, 'kalshi')
       AND (
             (e.win_probability_sources #>> '{kalshi,eligibility,market_id}')
                 = CAST(:market_id AS text)
             OR NOT EXISTS (
                   SELECT 1
                     FROM futures_markets fm2
                     JOIN futures_outcomes fo2 ON fo2.market_id = fm2.id
                    WHERE fm2.event_id = e.id
                      AND fm2.source = 'kalshi'
                      AND fo2.current_probability IS NOT NULL
                )
           )
 RETURNING e.id
    """
)


#: Markets carrying frozen-certain legs that the PRICE pass will never hand us.
#:
#: 🔴 THE SWEEP SHIPPED WITH ITS REACH INVERTED, AND THIS IS THAT HALF.
#: :func:`_scan_kalshi_frozen_certain` is passed the ids of :data:`_CANDIDATE_SQL`'s
#: batch, and that query ends in a six-hour staleness anti-join — a market enters
#: it only after six hours of price silence. An ACTIVELY TRADED market is
#: re-priced continuously, therefore never goes stale, therefore never enters the
#: batch, therefore its delisted legs were never checked. Not "later": never. The
#: sweep reached quiet markets and missed busy ones, while reader harm scales with
#: busy-ness — the exact opposite of the ordering we want.
#:
#: Measured on production 2026-09-09, of 35 open Kalshi markets holding
#: frozen-certain legs, **15 were unreachable this way** — every one of them a
#: ``KXIPO*`` "When will X officially announce an IPO?" ladder, 54 stuck legs
#: between them, led by OpenAI at $1,083,106 of volume. Its page's HERO number
#: read ``100%`` / "Yes" off a leg for "Before Sep 1, 2025", ten months after that
#: date passed and with the market's own live legs at 41/63/73%. Both stuck legs
#: answered 404 at the venue while a 2027 sibling answered 200.
#:
#: Ordered by volume DESC so the budget, if it ever binds, is spent where the most
#: readers are. ``:exclude_ids`` drops the markets the price loop already handled,
#: so the two populations never pay for the same leg twice.
_KALSHI_UNREACHED_FROZEN_SQL = text(
    f"""
    SELECT fm.id, fm.volume
      FROM futures_markets fm
     WHERE fm.source = 'kalshi'
       AND {LIVE_MARKET_SQL}
       AND NOT (fm.id = ANY(:exclude_ids))
       AND EXISTS (
             SELECT 1
               FROM futures_outcomes fo
              WHERE fo.market_id = fm.id
                AND fo.current_probability = 1.0
                AND fo.is_winner IS NOT TRUE
                AND fo.external_id IS NOT NULL
           )
       AND NOT EXISTS (
             SELECT 1
               FROM futures_outcomes crowned
              WHERE crowned.market_id = fm.id
                AND crowned.is_winner IS TRUE
           )
     ORDER BY fm.volume DESC NULLS LAST
     LIMIT :market_limit
    """
)

#: The per-market POSITIVE CONTROL, and the reason this pass is allowed to exist.
#:
#: The batched arm gets its venue-reachability proof for free: it retires only
#: AFTER a successful price read on that same market, so a 404 on one leg cannot
#: be the venue being down. This pass has no such read — nothing here was priced —
#: so it must buy the same proof, and it buys it per market: one leg we believe is
#: still listed is probed FIRST, and only a definite ``True`` licenses reading any
#: 404 in that market as a delisting. ``False``/``None`` decline the whole market,
#: which is gotcha #53 in its original form: "we could not reach it" must never be
#: spent as evidence of absence.
#:
#: The control is the NON-candidate leg with the freshest ``last_updated`` —
#: the leg we most recently got a real number for, which is the strongest stored
#: evidence that the venue still serves this series. Picking the candidate legs'
#: own siblings matters: a control from another market would prove the venue is up
#: but not that THIS series is still listed, and a purged series is precisely the
#: case that must not retire silently.
_KALSHI_CONTROL_LEG_SQL = text(
    """
    SELECT fo.external_id
      FROM futures_outcomes fo
     WHERE fo.market_id = :market_id
       AND fo.external_id IS NOT NULL
       AND (fo.current_probability IS DISTINCT FROM 1.0)
     ORDER BY fo.last_updated DESC NULLS LAST
     LIMIT 1
    """
)

#: Markets the unreached arm may examine in one pass.
#:
#: Bounds wall clock, not correctness: each market costs one control call plus one
#: call per candidate leg, all of them counted against the SAME
#: :data:`KALSHI_DELISTED_CHECK_BUDGET` as the batched arm, so the pass's total
#: venue spend is unchanged in the worst case. 20 covers today's whole unreachable
#: population (15 markets) with headroom, and the set is self-draining — a retired
#: leg's ``current_probability`` is NULL and never matches again.
KALSHI_UNREACHED_MARKET_LIMIT = 20


async def _scan_kalshi_frozen_certain(session, market_ids: list[int]) -> dict[int, list[str]]:
    """Candidate legs for :data:`_KALSHI_FROZEN_CERTAIN_SQL`, grouped by market.

    Run ONCE per pass over the whole Kalshi batch rather than per market: the
    predicate matches nothing for all but a handful of markets (14 of 3,338
    reachable rows on production 2026-09-09), so a per-market query would be
    3,338 round trips to learn "no" 3,324 times.
    """
    if not market_ids:
        return {}
    rows = (
        await session.execute(
            _KALSHI_FROZEN_CERTAIN_SQL, {"market_ids": list(market_ids)}
        )
    ).fetchall()
    out: dict[int, list[str]] = {}
    for market_id, ticker in rows:
        out.setdefault(int(market_id), []).append(ticker)
    return out


async def _retire_delisted_kalshi_legs(
    session, service, market_id: int, tickers: list[str], stats: dict
) -> int:
    """Withdraw our number on legs the venue has delisted. Returns the count.

    The candidate list is a DATABASE claim; this function turns it into a VENUE
    fact before writing anything. Each ticker is confirmed with its own
    :meth:`KalshiAPIService.market_exists` call, and only a definite ``False``
    (an observed 404) retires. ``True`` and ``None`` both decline — the second
    because "we could not reach the venue" must never be spent as evidence of
    absence (gotcha #53).

    The write re-decides the crowned-sibling refusal for itself; those venue
    calls ARE the race window, so the scan's verdict is carried here as a
    candidate list and never as a permission (CERT-2394 —
    :data:`_KALSHI_RETIRE_DELISTED_SQL`).
    """
    confirmed: list[str] = []
    for ticker in tickers:
        if stats["delisted_checks"] >= KALSHI_DELISTED_CHECK_BUDGET:
            stats["delisted_check_budget_hit"] = True
            break
        stats["delisted_checks"] += 1
        try:
            exists = await service.market_exists(ticker)
        except Exception as exc:  # pragma: no cover - defensive
            stats["errors"].append(f"kalshi exists {ticker}: {exc}")
            continue
        if exists is False:
            confirmed.append(ticker)
        elif exists is None:
            stats["delisted_indeterminate"] += 1
        else:
            stats["delisted_still_listed"] += 1
        await asyncio.sleep(0.15)

    if not confirmed:
        return 0
    result = await session.execute(
        _KALSHI_RETIRE_DELISTED_SQL,
        {"market_id": market_id, "tickers": confirmed},
    )
    retired = len(result.fetchall())
    if not retired:
        # Zero rows has two causes and they are not the same news. Separate them
        # so the refusal is countable (CERT-2394) — see
        # `_KALSHI_MARKET_NOW_GRADED_SQL`.
        now_graded = await session.scalar(
            _KALSHI_MARKET_NOW_GRADED_SQL, {"market_id": market_id}
        )
        if now_graded:
            stats["delisted_refused_market_graded"] += 1
            logger.info(
                "futures_price_refresh: refused to withdraw %s delisted Kalshi "
                "leg(s) on market %s — a sibling was crowned after the scan "
                "(#4253/CERT-2394)",
                len(confirmed), market_id,
            )
    return retired


async def _sweep_unreached_kalshi_frozen(
    session, service, exclude_ids: list[int], stats: dict
) -> None:
    """Retire delisted legs on live Kalshi markets the price pass never selects.

    The batched arm rides on :data:`_CANDIDATE_SQL`'s six-hour staleness gate and
    so cannot see an actively traded market — see
    :data:`_KALSHI_UNREACHED_FROZEN_SQL` for the measurement and the reader harm.
    This arm addresses that population by its own query and pays for the
    reachability proof the batched arm gets free, one control call per market.

    Shares ``KALSHI_DELISTED_CHECK_BUDGET`` with the batched arm and runs AFTER
    it, so the budget is spent on priced markets first and this arm takes what is
    left; both directions of that ordering were considered and this one keeps the
    existing arm's behaviour bit-for-bit when the budget binds.

    Never raises: a failure here must not cost the pass its prices.
    """
    if stats["delisted_checks"] >= KALSHI_DELISTED_CHECK_BUDGET:
        stats["unreached_budget_exhausted"] = True
        return
    try:
        rows = (
            await session.execute(
                _KALSHI_UNREACHED_FROZEN_SQL,
                {
                    "exclude_ids": list(exclude_ids),
                    "market_limit": KALSHI_UNREACHED_MARKET_LIMIT,
                },
            )
        ).fetchall()
    except Exception as exc:
        await session.rollback()
        stats["errors"].append(f"kalshi unreached scan: {exc}")
        return

    stats["unreached_markets_found"] = len(rows)
    if not rows:
        return

    candidates = await _scan_kalshi_frozen_certain(session, [int(r[0]) for r in rows])
    for market_id, _volume in rows:
        market_id = int(market_id)
        tickers = candidates.get(market_id)
        if not tickers:
            continue
        if stats["delisted_checks"] >= KALSHI_DELISTED_CHECK_BUDGET:
            stats["delisted_check_budget_hit"] = True
            stats["unreached_budget_exhausted"] = True
            break

        control = await session.scalar(
            _KALSHI_CONTROL_LEG_SQL, {"market_id": market_id}
        )
        if not control:
            # Every leg in the market is a candidate, so there is nothing left to
            # prove the series is still listed with. Decline: this is the shape a
            # wholly purged series has, and it is the one that must not retire on
            # a 404 that means "the series is gone", not "this leg is gone".
            stats["unreached_no_control"] += 1
            continue

        stats["delisted_checks"] += 1
        try:
            control_live = await service.market_exists(control)
        except Exception as exc:  # pragma: no cover - defensive
            stats["errors"].append(f"kalshi control {control}: {exc}")
            continue
        await asyncio.sleep(0.15)
        if control_live is not True:
            # False = the control leg is gone too, so a 404 on a candidate proves
            # nothing about that candidate specifically. None = we could not tell.
            # Both decline, and they are counted apart because they are different
            # news: one is a stale control, the other is an unreachable venue.
            if control_live is False:
                stats["unreached_control_delisted"] += 1
            else:
                stats["unreached_control_indeterminate"] += 1
            continue

        stats["unreached_markets_checked"] += 1
        try:
            retired = await _retire_delisted_kalshi_legs(
                session, service, market_id, tickers, stats
            )
            await session.commit()
        except Exception as exc:
            await session.rollback()
            stats["errors"].append(f"kalshi unreached retire {market_id}: {exc}")
            continue
        if retired:
            stats["kalshi_legs_retired"] += retired
            stats["unreached_legs_retired"] += retired
            logger.info(
                "futures_price_refresh: withdrew %s delisted Kalshi leg(s) on "
                "unreached market %s (control %s live) — #4253 reach arm",
                retired, market_id, control,
            )


async def _kalshi_reach_arm(
    session, stats: dict, exclude_ids: list[int], service=None
) -> None:
    """Own the credential, the client and the call for :func:`_sweep_unreached_kalshi_frozen`.

    A helper with TWO call sites in the task, which is the whole point. The
    reach arm chooses its own population — live Kalshi markets holding
    frozen-certain legs, ordered by volume — and that population is disjoint
    from the stale batch by construction, since the batch is handed over as
    ``exclude_ids``. So the arm's work does not depend on the batch containing
    anything, and both of the task's exits have to run it:

    * the normal path, where the batched arm has already spent what it wants of
      the shared delisted budget, and
    * the early return taken when NOTHING is stale — the pass on which this arm
      is the only Kalshi reach there is.

    The arm shipped scoped inside the batched arm's ``if kalshi_markets:``, and
    that was argued from production's batch never being empty (1,044 Kalshi
    markets on the 22:53Z pass, 2026-09-09). That is a fact about today's data,
    not a property of the code, and it is the same shape of reasoning as the
    six-hour staleness gate that made the arm necessary in the first place.

    A missing key is recorded on the summary rather than in ``errors``:
    ``errors`` drives :func:`_terminal` to ``partial`` for the whole pass, which
    would be a verdict about the pricing run and not about this arm.
    """
    if service is None:
        import os

        if not os.getenv("KALSHI_API_KEY"):
            stats["unreached_skipped_no_key"] = True
            return
        from app.services.kalshi_api import KalshiAPIService

        service = KalshiAPIService()

    await _sweep_unreached_kalshi_frozen(session, service, list(exclude_ids), stats)


async def _fetch_polymarket_prices(service, event_ids: list[str]) -> tuple[dict, dict]:
    """Prices for a batch of Polymarket event ids, keyed by event id.

    Returns ``(priced_by_event, unpriced_legs_by_event)``. A value in the first
    is either a list of priced items or :data:`VENUE_SETTLED`; a value in the
    second is the condition ids this pass was SERVED and the venue quotes no
    price for (#4000) — see :func:`_retire_unpriced_legs` below.

    THE SECOND DICT EXISTS BECAUSE ``continue`` THROWS AWAY A FACT WE WERE TOLD.
    The per-leg refusal below drops an unpriced leg from the write set, which is
    right — there is no price to write — and leaves whatever number the row was
    last given standing. Declining to write is not withdrawing what is written,
    and #4000's first attempt shipped the withdrawal onto the discovery poll,
    which cannot reach these markets at all: `_poll_polymarket_markets`
    paginates newest-first under a hard 2,000-event cap (#219E), a window that
    measured ten hours wide on 2026-09-09, while all 104 affected events carry
    startDates between 2025-07 and 2026-07. Zero were reachable, so zero were
    retired. This task reaches them precisely because it does NOT paginate — it
    addresses known markets by id (#2199) — and bucketing the cohort's
    ``last_updated`` by minute-of-hour proves it is the only writer that does:
    1,168 rows across 83 of the 104 markets land in the ``:50`` bucket, and the
    ``:15`` bucket where the poll runs holds none.

    THE SETTLED CHECK RUNS BEFORE THE COHERENCE GUARD, and the order is the
    point. #2222's Polymarket row (``86515``, the Alpha Arena field) is closed
    and resolved: Gamma still serves it, and every losing leg quotes
    ``lastTradePrice = 1`` on its own No token, so eight of nine legs resolve to
    ``1.0``. ``field_is_incoherent`` refuses the field — correctly, it is not a
    price — and the event lands in ``not_found``, forever, because a settled
    field can never become coherent again. Checked in this order the market is
    reported as what it is (over) instead of as what it looks like from inside
    the price rail (unreadable).

    Applies the same two field-level refusals as the ingest path:
    ``_resolve_market_probability`` (placeholder/evidence gate, gotcha #19) and
    ``field_is_incoherent`` (#1527 — a negRisk field with several near-certain
    legs is not a price at any leg, and capturing it poisons
    ``opening_probability`` permanently because opening is COALESCEd).
    """
    from app.tasks.polymarket import _resolve_market_probability, complementary_book

    # Left on its own line rather than folded into the import above, because
    # `test_reuses_the_source_price_guards_rather_than_reimplementing` pins that
    # line's exact spelling to prove this path cannot write a price the ingest
    # path would have refused. Wrapping it to fit a third name would have bought
    # my own change by blunting a guard that is still doing its job — the pin is
    # brittle about formatting, but it is right about the rule.
    from app.tasks.polymarket import _unpriced_leg_external_ids
    from app.utils.winner_field_coherence import field_is_incoherent

    raw_events = await service.get_events_by_ids(event_ids)
    out: dict = {}
    unpriced_out: dict = {}
    for raw in raw_events:
        event = service._parse_event(raw)
        if not event or not event.markets:
            continue
        # The venue's own statement, taken before any price is looked at.
        # `event.markets` is known non-empty here, so `all()` cannot be
        # vacuously true — an empty parse must never read as a settlement.
        if event.closed or all(m.closed for m in event.markets):
            out[str(event.id)] = VENUE_SETTLED
            continue
        priced: list[dict] = []
        for market in event.markets:
            prob = _resolve_market_probability(market)
            if prob is None or prob <= 0:
                continue
            item = {
                "external_id": market.condition_id,
                "probability": prob,
                "yes_bid": market.best_bid,
                "yes_ask": market.best_ask,
                "last_price": market.last_trade_price,
            }

            # THE NO LEG. A decomposed binary stores two rows and the card is
            # only presented as live when BOTH are fresh, so refreshing Yes alone
            # leaves the prop exactly as dark as before — the write lands and the
            # user still sees nothing.
            #
            # It is the complement of the Yes price we ACCEPTED, never
            # ``outcome_prices[1]``, and the difference is not academic. Measured
            # against live Gamma 2026-08-27 on the four curated US Open prop
            # events: 92 priced markets, ``outcome_prices`` summed to exactly 1
            # in every single one — so whenever Yes came from ``outcome_prices``
            # the two rules agree exactly. They diverge only when Yes did NOT:
            # ``alcaraz-semifinals`` quoted ``[0.32, 0.68]`` over an untradeable
            # 0.11/0.53 book, so 0.32 was refused as a fabricated midpoint
            # (#1578) and Yes resolved to the 0.53 last trade. Writing 0.68
            # beside it would print a card whose two sides sum to 1.21 — and 0.68
            # is the complement of the very number we just refused.
            #
            # ``1 - accepted`` is coherent with what we publish by construction,
            # which is the same reasoning ``complementary_book`` applies to the
            # book: one binary CLOB addressed from the other token, an identity
            # rather than an estimate.
            no_bid, no_ask, no_last = complementary_book(
                market.best_bid, market.best_ask, market.last_trade_price
            )
            item["no"] = {
                "probability": 1.0 - prob,
                "yes_bid": no_bid,
                "yes_ask": no_ask,
                "last_price": no_last,
            }

            priced.append(item)
        if not priced:
            continue
        if field_is_incoherent(
            (p["probability"] for p in priced),
            mutually_exclusive=bool(event.neg_risk),
        ):
            logger.warning(
                "futures_price_refresh: polymarket event %s — incoherent negRisk "
                "field, refusing capture (#1527)",
                event.id,
            )
            continue
        out[str(event.id)] = priced
        # #4000: keyed to an event we DID price, on purpose. One live quote is
        # the venue answering for this event, which makes "no quote on this leg"
        # a statement about the leg rather than about the venue — the one
        # distinction a by-id refresh cannot otherwise make, since a dark venue
        # and a dead leg arrive down the same wire. A field nobody quotes at all
        # never reaches this line (`if not priced: continue` above) and so
        # retires nothing, which is stricter than the discovery poll's placement
        # and deliberately so.
        unpriced_out[str(event.id)] = _unpriced_leg_external_ids(event)
    return out, unpriced_out


# --- entry point -------------------------------------------------------------


async def _refresh_stale_futures_prices(
    *,
    volume_floor: int = HIGH_VALUE_VOLUME_FLOOR,
    stale_hours: int = STALE_AFTER_HOURS,
    kalshi_budget: int = KALSHI_MARKET_BUDGET,
    polymarket_budget: int = POLYMARKET_MARKET_BUDGET,
    registered_refresh_minutes: int = REGISTERED_REFRESH_MINUTES,
    served_refresh_minutes: int = SERVED_REFRESH_MINUTES,
) -> dict:
    """Refresh prices for stale high-value open futures markets. See module docstring."""
    from app.tasks.base import get_task_session
    from app.utils.feed_served_markets import (
        SERVED_EMPTY,
        SERVED_FRESH,
        note_served_signal_healthy,
        served_signal,
    )
    from app.utils.tournament_register import registered_market_ids

    started = time.monotonic()
    stats: dict = {
        "task": "futures_price_refresh",
        "candidates": 0,
        "markets_attempted": 0,
        "markets_priced": 0,
        "snapshots_written": 0,
        "unknown_outcomes": 0,
        "not_found": 0,
        "unpriceable": 0,
        # #2222. `venue_settled` is a source SAYING the market is over;
        # `venue_settled_cleared` is a market that came back and had its stamp
        # removed. Both are counted because the second is the evidence that the
        # first is reversible, and an irreversible retirement is the failure
        # mode this whole mechanism is engineered against.
        "venue_settled": 0,
        "venue_settled_cleared": 0,
        # #4000. Prices WITHDRAWN because the venue quotes none — the counterpart
        # to `unknown_outcomes`, which counts a price we could not place. Reported
        # unconditionally, including as zero: the first attempt at this fix ran to
        # a clean success on every pass while retiring nothing, and a stat that
        # only appears when it fires cannot tell that apart from a quiet cohort.
        "legs_retired": 0,
        # #4253. The Kalshi half of the same withdrawal, counted SEPARATELY from
        # `legs_retired` because it answers a different venue question — "the
        # venue no longer lists this contract", not "the venue lists it and
        # quotes no price". Folding them would make a Kalshi regression
        # invisible behind Polymarket's much larger number.
        #
        # The three refusal counters are reported unconditionally, including as
        # zero, for the reason `legs_retired` is: a pass that confirmed nothing
        # and a pass that had nothing to confirm both arrive as "0 retired", and
        # only `delisted_checks` separates them.
        "kalshi_legs_retired": 0,
        "delisted_checks": 0,
        "delisted_still_listed": 0,
        "delisted_indeterminate": 0,
        # CERT-2394. Markets where the venue confirmed the delisting but a
        # sibling was crowned between the scan and the write, so the whole
        # market was refused. Reported unconditionally for the same reason as
        # the three above: a boundary that is only visible when it fires cannot
        # be shown to be working on the passes where it doesn't.
        "delisted_refused_market_graded": 0,
        "delisted_check_budget_hit": False,
        # #5771. Quotes withdrawn because the venue had already answered a
        # contest whose event has not started. Unconditional, same rule again:
        # a run that found nothing frozen and a run whose withdrawal statement
        # silently matched nothing both report "0" otherwise, and this one sits
        # behind `venue_settled`, which is itself rare — so the pair
        # (`venue_settled`, `pre_kickoff_quotes_withdrawn`) is the only way to
        # read whether the second half ever fires.
        "pre_kickoff_quotes_withdrawn": 0,
        # CERT-2772's repair. Reported APART from the counter above rather than
        # folded into it, because the two can legitimately disagree and the
        # disagreement is the diagnosis: quotes withdrawn with no hero cleared
        # means either the event never had a Kalshi blend key or a different
        # Kalshi speaker is still standing (both fine), while a hero cleared
        # with no quote withdrawn would mean the key outlived every price and
        # is worth reading about. One number could say neither.
        "pre_kickoff_heroes_cleared": 0,
        # The #4253 reach arm (`_sweep_unreached_kalshi_frozen`). Reported
        # unconditionally, same rule as above: `unreached_markets_found` at 0 and
        # `unreached_markets_checked` at 0 are DIFFERENT passes — the first says
        # the backlog is drained, the second says every market in it declined its
        # own control — and a report that cannot tell them apart is the report
        # that let this population sit unswept since the arm shipped.
        "unreached_markets_found": 0,
        "unreached_markets_checked": 0,
        "unreached_legs_retired": 0,
        "unreached_no_control": 0,
        "unreached_control_delisted": 0,
        "unreached_control_indeterminate": 0,
        "unreached_budget_exhausted": False,
        # The reach arm now runs on every pass, including one whose stale batch
        # holds no Kalshi market at all, so "it found nothing" and "it never got
        # to look" are two more states that must not share a zero. A missing key
        # is NOT appended to `errors`: that would turn every keyless environment's
        # pass `partial` (see `_terminal`), which is a verdict about the pass and
        # not about this arm.
        "unreached_skipped_no_key": False,
        "errors": [],
        "by_source": {},
        "remaining_stale": None,
        "budget_hit": False,
        "registered_candidates": 0,
        "registered_attempted": 0,
        "registered_priced": 0,
        # #3315. `served_known` is how many market ids the pre-warm rail says
        # page one is rendering; the other three are what this run did about
        # them. `served_known` is reported even when it is zero, because "no
        # shape has warmed since the last deploy" and "page one holds no futures
        # cards" are opposite states that both arrive as an empty selection
        # (gotcha #53) — and the first of the two silently restores the coverage
        # this arm exists to end.
        "served_known": 0,
        # CERT-1970: the state, and whether it permits a green verdict. Reported
        # even on the happy path, because the field a reader needs in order to
        # trust `terminal: complete` must be present in every summary that
        # carries one — a diagnostic that appears only when things are broken
        # cannot be used to establish that they are not.
        "served_state": None,
        "served_signal_ok": True,
        "served_shapes": 0,
        "served_stale_shapes": 0,
        "served_unreadable_shapes": 0,
        "served_candidates": 0,
        "served_attempted": 0,
        "served_priced": 0,
        # Served ids this task structurally cannot refresh: an `odds_api` row
        # (LIVE_MARKET_SQL is Kalshi/Polymarket only) or a market the liveness
        # bounds retired. Counted so a page-one card that stays wrong has a
        # number pointing at the reason instead of an absence.
        "served_unreachable": 0,
    }

    # Bound the longest single uninterrupted DB op rather than the loop
    # boundaries (gotcha: budget-guard-inner-op). A loop-boundary check cannot
    # interrupt a statement already blocked on a row lock held by the live
    # poller.
    #
    # #4482: on the connection, not as a `SET` on the session. This body commits
    # per item, every commit returns the connection to the pool, and a recycled
    # or pre-ping-replaced connection would arrive with neither bound — 60 s
    # becoming the resting 30 min and 15 s becoming unbounded, silently.
    async with get_task_session(
        statement_timeout_ms=60_000, lock_timeout_ms=15_000
    ) as session:

        # THE IDENTITY ARMS FIRST, and on a shorter clock. Separate arms rather
        # than one loosened predicate: the class arm answers "is this valuable",
        # which is a question about the market, and the identity arms answer "is
        # somebody looking at this", which is a question about the product. A
        # single predicate would have to pick one of those to be, and #3315 is
        # what happened while it picked the first.
        # 🔴 A STATE, NOT A LIST (CERT-1970). `served_market_ids()` used to return
        # `[]` for a missing key, a corrupt hash, a failed read AND a page with no
        # futures cards, the run recorded only the count, and `_terminal` never
        # looked — so a low-value page-one card could stay stale forever behind
        # `terminal: complete`. Gotcha #53, in the plumbing of a change that cited
        # gotcha #53. `served_signal()` names the four facts; the sweep refuses a
        # green verdict on the one that means this arm is dark.
        signal = served_signal()
        served_ids = signal.ids
        stats["served_state"] = signal.state
        stats["served_signal_ok"] = signal.green_allowed
        stats["served_known"] = len(served_ids)
        stats["served_shapes"] = signal.shapes
        stats["served_stale_shapes"] = signal.stale_shapes
        stats["served_unreadable_shapes"] = signal.unreadable_shapes
        if signal.state in (SERVED_FRESH, SERVED_EMPTY):
            # The consumer's own memory that this arm has worked, which is what
            # the grace above is measured from. Written only on a POSITIVE
            # observation — writing it on `warming_up` would let the grace renew
            # itself forever and the signal could never be reported dark.
            note_served_signal_healthy()
        served_scan = await _scan_served_candidates(
            session,
            market_ids=served_ids,
            stale_minutes=served_refresh_minutes,
        )
        if served_ids:
            try:
                reachable = int(
                    (
                        await session.execute(
                            _SERVED_REACHABLE_SQL, {"market_ids": served_ids}
                        )
                    ).scalar()
                    or 0
                )
                stats["served_unreachable"] = max(0, len(served_ids) - reachable)
            except Exception as exc:
                stats["errors"].append(f"served reachability census: {exc}")
        registered_scan = await _scan_registered_candidates(
            session,
            market_ids=sorted(registered_market_ids()),
            stale_minutes=registered_refresh_minutes,
        )
        class_scan = await _scan_candidates(
            session,
            volume_floor=volume_floor,
            stale_hours=stale_hours,
            stats=stats,
        )

        # A market can qualify on more than one arm — every US Open winner field
        # is registered AND tier-1 high-volume, and a page-one card is routinely
        # both served and valuable. It must keep the IDENTITY classification or
        # it inherits the 6h attempt TTL and the shorter clock is undone.
        #
        # ATTRIBUTION, since a row can only be counted once: served wins over
        # registered, which wins over class. So `registered_candidates` is the
        # registered rows page one is NOT already covering, and reading it as
        # "the register's coverage" would understate it. The register's actual
        # coverage invariant is asserted by its own query in
        # `/api/admin/source-health/futures-price-freshness`, which is
        # independent of this run's bookkeeping — these counters describe the
        # RUN, not the population.
        served_scan_ids = {m["id"] for m in served_scan}
        registered_scan = [m for m in registered_scan if m["id"] not in served_scan_ids]
        priority_ids = served_scan_ids | {m["id"] for m in registered_scan}
        scan = (
            served_scan
            + registered_scan
            + [m for m in class_scan if m["id"] not in priority_ids]
        )

        stats["candidates"] = len(scan)
        stats["registered_candidates"] = len(registered_scan)
        stats["served_candidates"] = len(served_scan)

        skip_ids = _load_attempt_skips([m["id"] for m in scan])
        eligible = [m for m in scan if m["id"] not in skip_ids]

        # PER-SOURCE BUDGETS, AND THE PRIORITY ROWS ARE TAKEN BEFORE THE CAP IS
        # APPLIED, not merely sorted in front of it. Head position made "curated
        # rows cannot be starved" true only while one shared truncation held both
        # arms; with two caps a `[:budget]` over an interleaved list is a bound
        # nobody can reason about. Taking them explicitly makes the guarantee
        # structural — a priority row is dropped by the wall clock or not at all.
        kalshi_markets = _take_for_source(eligible, "kalshi", kalshi_budget)
        poly_markets = _take_for_source(eligible, "polymarket", polymarket_budget)
        selected = kalshi_markets + poly_markets

        if not selected:
            # THE REACH ARM RUNS ON THIS EXIT TOO. "Nothing is stale" is a
            # statement about the batch, and the arm's population is the markets
            # the batch cannot see — an actively traded market is never stale, so
            # this is the pass on which its delisted legs are MOST likely to be
            # sitting unswept. Returning here without it is the same defect as
            # the six-hour staleness gate, one level up.
            #
            # Before the terminal below, so the arm's own errors reach the
            # summary. This branch sets its terminal literally rather than
            # through `_terminal`, so an arm error does not downgrade it — that
            # is deliberate: a reach-arm failure is not a failure of a pricing
            # pass that had no prices to fetch.
            await _kalshi_reach_arm(session, stats, [])
            # Gotcha #53: an empty result is a response SHAPE, not an absence.
            # "Nothing stale" and "everything stale was just attempted" are
            # opposite states, so they get different terminals.
            stats["terminal"] = "complete" if not scan else "no_work"
            stats["reason"] = (
                "no stale valuable, registered or served markets"
                if not scan
                else "every stale market was attempted inside the current window"
            )
            # ...unless we could not see page one, in which case "nothing was
            # stale" is a claim about a population we were unable to enumerate.
            # Same rule as the main terminal below, applied on the path that
            # returns first (CERT-1970: a false green does not become true by
            # being reached through a shorter branch).
            if not stats["served_signal_ok"]:
                stats["terminal"] = "no_work"
                stats["reason"] = (
                    f"served page-one signal {stats['served_state']}: "
                    "page-one coverage could not be established"
                )
            stats["remaining_stale"] = len(scan)
            return stats

        attempted_ids: list[int] = []
        priority_attempted_ids: list[int] = []

        def _note_attempt(market: dict) -> None:
            stats["markets_attempted"] += 1
            if market["registered"]:
                stats["registered_attempted"] += 1
            if market["served"]:
                stats["served_attempted"] += 1
            if market["priority"]:
                priority_attempted_ids.append(market["id"])
            else:
                attempted_ids.append(market["id"])

        # --- Polymarket: batched by id, so the whole backlog costs ~25 calls ---
        if poly_markets:
            from app.services.polymarket_api import PolymarketAPIService
            from app.tasks.polymarket import _retire_unpriced_legs

            poly_service = PolymarketAPIService()
            try:
                # MANY MARKETS PER EVENT, so this is a list and not a scalar.
                # A negRisk field is one market on one event, but the decomposed
                # binaries are one event per QUESTION GROUP — the eight curated
                # US Open props sit on four events, two of them sharing one.
                # Keying market-per-event would have silently dropped the second
                # prop of every pair.
                by_event: dict[str, list[dict]] = {}
                for market in poly_markets:
                    event_id = market.get("poly_event_id")
                    if not event_id:
                        # No resolvable Gamma event id: the row cannot be
                        # addressed, and saying so is the point (gotcha #53).
                        # Counted, marked attempted so it rotates, never retried
                        # into a 422 loop against `/events?id=0x…`.
                        _note_attempt(market)
                        stats["no_event_id"] = stats.get("no_event_id", 0) + 1
                        continue
                    by_event.setdefault(str(event_id), []).append(market)

                ids = list(by_event.keys())
                poly_deadline = min(_POLYMARKET_WALL_BUDGET_S, _TIME_BUDGET_S)
                for i in range(0, len(ids), POLYMARKET_ID_BATCH):
                    if time.monotonic() - started > poly_deadline:
                        # `budget_hit` either way: the run's coverage is not
                        # proven, and which of the two clocks stopped it is not a
                        # difference the terminal should hide.
                        stats["budget_hit"] = True
                        stats["polymarket_wall_hit"] = True
                        break
                    chunk = ids[i : i + POLYMARKET_ID_BATCH]
                    try:
                        priced_by_event, unpriced_by_event = (
                            await _fetch_polymarket_prices(poly_service, chunk)
                        )
                    except Exception as exc:  # one bad batch must not wipe the run
                        stats["errors"].append(f"polymarket batch {i}: {exc}")
                        continue
                    for event_id in chunk:
                        priced = priced_by_event.get(event_id)
                        for market in by_event[event_id]:
                            _note_attempt(market)
                            if priced is VENUE_SETTLED:
                                stats["venue_settled"] += 1
                                try:
                                    await _stamp_venue_settled(session, market["id"])
                                    await session.commit()
                                except Exception as exc:
                                    await session.rollback()
                                    stats["errors"].append(
                                        f"polymarket stamp {market['external_id']}: {exc}"
                                    )
                                continue
                            if priced is None:
                                stats["not_found"] += 1
                                continue
                            try:
                                written = await _write_prices(
                                    session, market["id"], "polymarket", priced, stats
                                )
                                # #4000: same transaction as the refresh it rides,
                                # so a row can never be left retired by a pass whose
                                # prices rolled back. Runs after the write, so a leg
                                # that regained a price this pass has already been
                                # rewritten and is no longer in the unpriced list.
                                retired = await _retire_unpriced_legs(
                                    session,
                                    market["id"],
                                    unpriced_by_event.get(event_id) or [],
                                )
                                await session.commit()
                            except Exception as exc:
                                await session.rollback()
                                stats["errors"].append(
                                    f"polymarket {market['external_id']}: {exc}"
                                )
                                continue
                            if retired:
                                stats["legs_retired"] = (
                                    stats.get("legs_retired", 0) + retired
                                )
                                logger.info(
                                    "futures_price_refresh: market %s — withdrew our "
                                    "price on %d leg(s) the venue quotes no price "
                                    "for (#4000)",
                                    market["id"], retired,
                                )
                            if written:
                                stats["markets_priced"] += 1
                                stats["snapshots_written"] += written
                                stats["by_source"]["polymarket"] = (
                                    stats["by_source"].get("polymarket", 0) + written
                                )
                                if market["registered"]:
                                    stats["registered_priced"] += 1
                                if market["served"]:
                                    stats["served_priced"] += 1
                                await _clear_if_stamped(session, market, stats)
                            else:
                                stats["unpriceable"] += 1
                    await asyncio.sleep(0.3)
            finally:
                await poly_service.close()

        # --- Kalshi: one call per event ticker; no batch endpoint exists ---
        #
        # The credential check and the service gate BOTH Kalshi arms, not just
        # the batched one, because the #4253 reach arm selects its own
        # population and must run on a pass whose stale batch holds no Kalshi
        # market at all (CERT-2421 follow-up
        # `4253-RUN-UNREACHED-SWEEP-WITH-AN-EMPTY-STALE-BATCH`).
        import os

        kalshi_service = None
        if os.getenv("KALSHI_API_KEY"):
            from app.services.kalshi_api import KalshiAPIService

            kalshi_service = KalshiAPIService()
        elif kalshi_markets:
            # Unchanged, and still conditional on the BATCH: this error is about
            # markets that were selected and then not priced. Making it
            # unconditional would turn every keyless pass `partial` (see
            # `_terminal`), which is a verdict about the whole pass and not about
            # one arm — the reach arm reports its own skip in
            # `unreached_skipped_no_key`.
            stats["errors"].append("KALSHI_API_KEY not configured")

        if kalshi_service is not None and kalshi_markets:
            # One scan for the whole batch, before the loop — see
            # `_scan_kalshi_frozen_certain`. A failure here must not cost the
            # pass its prices, so it degrades to "no candidates".
            try:
                frozen_certain = await _scan_kalshi_frozen_certain(
                    session, [m["id"] for m in kalshi_markets]
                )
            except Exception as exc:
                await session.rollback()
                stats["errors"].append(f"kalshi frozen scan: {exc}")
                frozen_certain = {}
            for market in kalshi_markets:
                if time.monotonic() - started > _TIME_BUDGET_S:
                    stats["budget_hit"] = True
                    break
                _note_attempt(market)
                try:
                    priced = await _fetch_kalshi_prices(
                        kalshi_service, market["external_id"]
                    )
                except Exception as exc:
                    stats["errors"].append(f"kalshi {market['external_id']}: {exc}")
                    continue
                if priced is VENUE_SETTLED:
                    stats["venue_settled"] += 1
                    try:
                        await _stamp_venue_settled(session, market["id"])
                        # #5771's second half — see
                        # `_KALSHI_WITHDRAW_PRE_KICKOFF_SQL`. Same transaction as
                        # the stamp: the stamp is what stops us re-reading this
                        # market, so a withdrawal that committed separately could
                        # be lost while the "don't look again" marker survived.
                        withdrawn = (
                            await session.execute(
                                _KALSHI_WITHDRAW_PRE_KICKOFF_SQL,
                                {"market_id": market["id"]},
                            )
                        ).fetchall()
                        # CERT-2772's repair, and the ORDER is the argument: the
                        # hero statement asks whether any Kalshi price is still
                        # standing on this event, and the answer must already
                        # exclude the legs withdrawn one line above. Same
                        # transaction for the same reason as the stamp — a page
                        # left serving 99% while the "don't look again" marker
                        # survived is the state this repair exists to end.
                        heroes = (
                            await session.execute(
                                _KALSHI_WITHDRAW_EVENT_HERO_SQL,
                                {"market_id": market["id"]},
                            )
                        ).fetchall()
                        await session.commit()
                    except Exception as exc:
                        await session.rollback()
                        stats["errors"].append(
                            f"kalshi stamp {market['external_id']}: {exc}"
                        )
                    else:
                        if withdrawn:
                            stats["pre_kickoff_quotes_withdrawn"] += len(withdrawn)
                            logger.info(
                                "futures_price_refresh: withdrew %s settled Kalshi "
                                "quote(s) on market %s (%s) — the venue answered a "
                                "contest that has not started (#5771)",
                                len(withdrawn), market["id"], market["external_id"],
                            )
                        if heroes:
                            stats["pre_kickoff_heroes_cleared"] += len(heroes)
                            logger.info(
                                "futures_price_refresh: cleared the Kalshi blend "
                                "speaker on event(s) %s — the leg it was stamped "
                                "from is withdrawn, so the hero stops serving a "
                                "settlement as a price (#5771, CERT-2772)",
                                [r[0] for r in heroes],
                            )
                    continue
                if priced is None:
                    stats["not_found"] += 1
                    continue
                try:
                    written = await _write_prices(
                        session, market["id"], "kalshi", priced, stats
                    )
                    await session.commit()
                except Exception as exc:
                    await session.rollback()
                    stats["errors"].append(f"kalshi {market['external_id']}: {exc}")
                    continue
                if written:
                    stats["markets_priced"] += 1
                    stats["snapshots_written"] += written
                    stats["by_source"]["kalshi"] = (
                        stats["by_source"].get("kalshi", 0) + written
                    )
                    if market["registered"]:
                        stats["registered_priced"] += 1
                    if market["served"]:
                        stats["served_priced"] += 1
                    await _clear_if_stamped(session, market, stats)
                else:
                    stats["unpriceable"] += 1

                # #4253, AFTER the write on purpose. The event read above
                # proves the venue is reachable and this market is live, so
                # a 404 on one of its legs means that leg specifically is
                # gone — not that the venue is down. Running it before the
                # write would also race the fresh price the write is about
                # to put on the row.
                candidates = frozen_certain.get(market["id"])
                if candidates:
                    try:
                        retired = await _retire_delisted_kalshi_legs(
                            session, kalshi_service, market["id"], candidates, stats
                        )
                        await session.commit()
                    except Exception as exc:
                        await session.rollback()
                        stats["errors"].append(
                            f"kalshi retire {market['external_id']}: {exc}"
                        )
                    else:
                        if retired:
                            stats["kalshi_legs_retired"] += retired
                            logger.info(
                                "futures_price_refresh: withdrew %s delisted "
                                "Kalshi leg(s) on market %s (%s)",
                                retired, market["id"], market["external_id"],
                            )
                await asyncio.sleep(0.15)

        # #4253 reach arm, LAST and unconditional — see `_kalshi_reach_arm`. The
        # batched loop above spends the shared delisted budget first, so this
        # cannot change what that arm does on any pass; when the budget binds,
        # this one simply gets nothing.
        await _kalshi_reach_arm(
            session, stats, [m["id"] for m in kalshi_markets], service=kalshi_service
        )

        # Two TTLs, because there are two clocks. An identity market marked for
        # 6h would be unreachable for five hours after every refresh, which is
        # the lockstep this change exists to break — the shorter select window
        # would simply re-find it and the marker would veto it.
        #
        # The SHORTER of the two identity windows, not each arm's own: a market
        # on both arms holds one marker, and sizing it off the longer window
        # would let the marker outlive the shorter arm's next beat. `min` fails
        # in the direction of re-attempting a row an hour early, which costs one
        # HTTP call; the other direction costs a page-one card a refresh cycle.
        _mark_attempted(attempted_ids, ttl_seconds=stale_hours * 3600)
        _mark_attempted(
            priority_attempted_ids,
            ttl_seconds=max(1, min(registered_refresh_minutes, served_refresh_minutes))
            * 60,
        )

        # Measure what is LEFT, so the run reports the invariant's state and not
        # just its own throughput. This is the number the guard reads, so it
        # composes the SAME eligible pool the selector does — a census over a
        # narrower set than the sweep is a `remaining_stale` about nobody, which
        # is what it was while the tier fence was in it.
        try:
            remaining = (
                await session.execute(
                    text(
                        f"""
                        {ELIGIBLE_POOL_SQL}
                        SELECT COUNT(*) FROM futures_markets fm
                          JOIN pool ON pool.id = fm.id
                         WHERE NOT EXISTS (
                                 SELECT 1 FROM futures_outcomes fo
                                   JOIN futures_odds_snapshots s
                                     ON s.outcome_id = fo.id
                                  WHERE fo.market_id = fm.id
                                    AND s.captured_at
                                        > NOW() - make_interval(hours => :stale_hours)
                               )
                        """
                    ),
                    {
                        **pool_bind_params(),
                        # the run's own floor wins over the module default, so a
                        # manual invocation's census measures what it swept.
                        "volume_floor": volume_floor,
                        "stale_hours": stale_hours,
                    },
                )
            ).scalar()
            stats["remaining_stale"] = int(remaining or 0)
        except Exception as exc:
            stats["errors"].append(f"remaining_stale census: {exc}")

    stats["elapsed_s"] = round(time.monotonic() - started, 1)
    stats["terminal"] = _terminal(stats)
    return stats


def _terminal(stats: dict) -> str:
    """The honest terminal. #1884: enrolled from birth, so this is the contract.

    A run that attempted markets and wrote nothing is ``failed``, not
    ``complete`` — that is the exact false-green this task exists to end
    (gotcha #53: "it returned" is not "it worked"). A budget- or error-truncated
    run that did write is ``partial``: real work banked, coverage not proven.
    """
    if stats["markets_attempted"] == 0:
        return "no_work"
    if stats["snapshots_written"] == 0:
        return "failed"
    if stats["budget_hit"] or stats["errors"]:
        return "partial"
    # CERT-1970. The class arm can succeed completely while the arm that reaches
    # PAGE ONE is dark, and the run has no other way to say so. `partial` is the
    # existing word for exactly this — real work banked, coverage not proven —
    # and `task_verdict.NOT_GREEN` already contains it, so the enforced verdict
    # stops reading green without inventing a fifth terminal.
    #
    # `.get(..., True)` so a caller that assembles a summary without the field
    # (every existing test of this function, and any future partial dict) keeps
    # its old meaning. The states that DO permit green are enumerated in
    # `feed_served_markets.SERVED_GREEN_STATES`, not re-listed here.
    if not stats.get("served_signal_ok", True):
        return "partial"
    return "complete"
