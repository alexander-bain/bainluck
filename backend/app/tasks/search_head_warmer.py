"""Keep the head of the real `/search` distribution resident (LAT-P090, #2211).

WHAT THIS IS FOR, and why it is not another index.

LAT-P087 and LAT-P088 spent two cycles on string indexes for this endpoint. The
teams FTS index landed GREEN. The futures partial trigram GIN landed **RED** on
its pre-registered budget arm — median per-term collapse 0.7194 against a 0.5
ceiling — and Alex dropped it per the contract. The per-term table underneath
that median is the reason this module exists rather than a third index:

    super bowl 0.078 · world series 0.083 · best picture 0.368 · world cup 0.500
    champion 0.593 · presidential election 0.658 · winner 0.979 · election 0.998

Rare phrases collapse. Common single words do not, and the cause is mechanical:
a trigram index is a selectivity instrument, `%winner%` matches 42,336 of
858,938 futures rows, and a bitmap covering most of a table costs what the
sequential scan costs. **The common-word head cannot be fixed by any string
index.** It can only be answered before it is asked.

So: `app/utils/search_cache.py` gives `/search` a response cache, and this task
keeps the head of the measured distribution inside it.

THE HEAD IS ELECTED BY THE **USER-ATTESTED ROWS** OF `search_query_logs`, RANKED
BY DISTINCT SESSIONS, AND EVERY WORD OF THAT IS LOAD-BEARING (LAT-P102, #1916).

The first version of this module elected its head from the table WHOLE, and
shipped disabled because #1916 blocks exactly that. LAT-P102 re-measured the
table and the block turned out to be both resolvable and far understated:

    30-day census, 2026-08-27          rows    share
    total                              3,851
    carrying NO session_id and no user_id
                                       3,838   99.66 %
    in the 07:09-07:12 sentinel minute   922   23.9 %  (#1916's number)
    in a "burst" minute (>= 8 distinct
      queries in one clock minute)     2,858   74.2 %

`session_id` is the flag #1916 asks for, **and it already exists in the schema.**
`frontend/lib/api.ts:332` and `APIClient.swift` both attach `x-session-id` to
every search, so a row carrying one was written on behalf of a real client. That
is a write-time-recorded positive assertion, not a timestamp heuristic — which is
precisely the discriminator #1916's acceptance criteria demand, and it needs no
column and no migration.

Reading the table through that flag returns the clean distribution #1916 said had
to exist before a head could be sourced here. It exists. It is also **13 rows in
30 days, across 12 sessions, with exactly one query asked by two different
sessions** (`red sox`). So the honest finding is not "the head was contaminated
and here is the clean one" — it is that ELECTING A HEAD FROM THE WHOLE TABLE
WOULD HAVE WARMED OUR OWN PROBE TRAFFIC. Every one of the top eight terms
(`masters winner`, `stanley cup`, `world cup`, `nba champion`, `world series`,
`red sox`, `grammys`, `yankees`) is a sentinel or probe term.

Hence the two rules below, which are what make the switch safe to leave ON:

1. **A row with no session and no user is not demand.** `_head_from_user_rows`
   filters to `session_id IS NOT NULL OR user_id IS NOT NULL`. It never falls
   back to the unfiltered table — a fallback would silently reinstate the exact
   block this module was shipped disabled under.
2. **A head is ranked and floored by DISTINCT SESSIONS, not by rows.** One of
   the 13 organic rows is `patriots`, submitted four times in nine seconds by one
   session. Row-ranked, that single person out-votes everything. Session-ranked
   with `MIN_HEAD_SESSIONS = 2`, a query one person asked is never warmed.

Together those mean the warmer **self-gates on real demand**: today the clean
head is empty, so a pass warms nothing and reports `partial` at ~1 ms; the day
two different people search the same thing inside a month, it starts working
with no further human decision and no re-tuning. That is the resolution of
#1916's block for this source — not an argument that the contamination is
tolerable, but a head that cannot contain it.

THREE LESSONS ARE INHERITED RATHER THAN RE-LEARNED. Each one cost a cycle on
`/typeahead`, and each is a test in `tests/test_search_response_cache.py`:

1. **A warmer must not warm a key nobody reads** (LAT-P001). There is one key
   builder, `search_response_cache_key`, and both the route and this module call
   it. The warmed SHAPE is separately pinned against the route's declared
   defaults, because `frontend/lib/api.ts` and `APIClient.fetchSearch` both omit
   `days_back` and `include_upcoming` and therefore both depend on them.
2. **A pass that hits the cache extends nothing** (hole 2, LAT-P060). The route
   writes its cache only on the MISS path, so a warm read resets no clock and a
   "warm" of a warm entry is a Redis GET that reports success and delivers
   nothing. The only way to extend an entry's life is to make the entry not be
   there, so a near-dead entry is DROPPED before the route is called.
3. **A warmer must not be able to report success while the head is cold**
   (`app/utils/task_verdict.py`). An empty head is `partial`, never `complete`.

✅ **THIS TASK SHIPS ENABLED (LAT-P102). Unset now means ON**, in line with the
rest of the family. What changed is not the appetite for risk, it is the head:
the switch used to guard a head that could contain probe traffic, and now it
guards one that cannot. The block lives in `_head_from_user_rows`, where it is
structural, rather than in an env var an operator can flip past.

**The response cache is unaffected and was already live**; it caches what was
actually asked and has no opinion about what is popular, so it is
contamination-proof by construction.

THE COST, STATED, because this lane's own doctrine is that a warmer is not free.
`/search` is a much heavier call than `/typeahead`, so every knob here is set
below its sibling's: 8 terms rather than 40, concurrency 2 rather than 4, and a
45 s floor rather than 30 s. A steady-state pass rebuilds 8 entries at
concurrency 2, and production measures the pass wall at **3.3-26.1 s, p50
~7.9 s** (2026-09-06) — the "~1-2 s per query, ~4-8 s per pass" this paragraph
used to carry was 3-20x low, and it is corrected rather than quietly dropped
because it is the number the ENABLED decision was justified on. The load bound
is `MIN_PASS_PERIOD_SECONDS`: at most one pass per 45 s, whatever the beat does.

⚠️ TWO OPEN DEFECTS LIVE IN THE ARITHMETIC BELOW. Neither is fixed here; both are
named so nobody reads this docstring as a guarantee.

THE THREE CONSTANTS ARE ONE DECISION, not three. An entry lives
`SEARCH_RESPONSE_TTL_SECONDS`; a pass arrives at worst every
`MIN_PASS_PERIOD_SECONDS` and rebuilds anything with under
`REFRESH_AHEAD_SECONDS` left. For the head never to go cold both must hold:

    MIN_PASS_PERIOD_SECONDS < TTL                       (a pass arrives in time)
    TTL - MIN_PASS_PERIOD_SECONDS <= REFRESH_AHEAD       (and finds it eligible)

45 < 60, and 60 - 45 = 15 <= 25. Tuning one of these without the other two is
how `/typeahead` sat at a 47% duty cycle for two cycles while reporting 40/40
every pass, so the relation is asserted as a test rather than left as arithmetic
in a comment.

🔴 **#3539 — THAT RELATION IS UNSOUND, AND THE TEST ASSERTING IT PASSES ON A
PERIOD THE SYSTEM NEVER ACHIEVES.** `MIN_PASS_PERIOD_SECONDS` is a floor, not the
period: a 45 s floor against a 20 s beat quantizes up, so the smallest achievable
gap between two real passes is **60 s**, and the first clause is really `60 < 60`
= false. The relation also carries no rebuild-duration term at all, though the
entry is written at the END of a pass, not at its start. The sound form needs
`REFRESH_AHEAD - P_effective > D_max`; today that is `25 - 60 = -35`. Do not
tune any of the three without reading #3539 — its three candidate repairs are
each a product decision (rebuild load, a freshness ceiling, or #1866's DDL).

🔴 **#3364 — AND UNTIL 2026-09-06 THE PERIOD WAS NOT 60 s EITHER, IT WAS ~576 s.**
`_EXPIRING_WARMER_BEATS["warm-search-head"]` bounded the beat's messages at one
beat period, so on a `--concurrency=2` pool serving 57+ beats they were discarded
before a slot ever freed: 102 starts against 2,949 expected fires, and
`matched_delivered` **0** of `matched_emitted` **30** in one 600 s bucket. That
bound is now derived — see `derive_message_expiry_s` below — which makes the 60 s
above the real period and therefore makes #3539 the binding constraint rather
than a theoretical one.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from contextlib import AsyncExitStack

from app.utils.search_cache import (
    SEARCH_RESPONSE_TTL_SECONDS,
    SEARCH_WARM_SHAPE,
    normalize_search_query,
    search_response_cache_key,
)

logger = logging.getLogger(__name__)

#: How many head queries a pass keeps resident. Deliberately far below
#: `typeahead_warmer.DEFAULT_HEAD_SIZE` (40): a `/search` call assembles events,
#: odds, futures, families, teams and concepts, where a `/typeahead` call
#: assembles eight suggestions. The head is also genuinely short — the 30-day
#: log's top rows drop off quickly — so a wider window would spend real database
#: time on queries nobody is asking.
DEFAULT_HEAD_SIZE = 8

#: One query's hard bound, so the LONGEST UNINTERRUPTED OP is bounded and not
#: merely the loop boundary (the budget-guard rule). Under the route's own
#: 20,000 ms deadline, so a query this warmer abandons is one the route would
#: have degraded anyway.
PER_QUERY_TIMEOUT_SECONDS = 25

#: Sessions in flight. ONE query per session is an invariant, not a tuning
#: choice: an `AsyncSession` is not safe for concurrent use, so a second
#: coroutine on the same session is a corruption bug rather than a slowdown.
WARM_CONCURRENCY = 2

#: Rebuild an entry with less than this much life left. See the arithmetic in
#: the module docstring — this is what makes the duty cycle flat rather than a
#: sawtooth.
REFRESH_AHEAD_SECONDS = 25

#: The floor between two real passes, checked UNDER the run lock so two beats
#: cannot both pass it. This is the load bound: the beat may fire more often,
#: but a pass may not start more often than this.
MIN_PASS_PERIOD_SECONDS = 45

#: The head window. Matches the window `typeahead_warmer._head_from_query_log`
#: reads, so the two surfaces disagree about WHICH queries are hot and never
#: about HOW LONG a query stays hot.
HEAD_WINDOW_DAYS = 30

#: How many DISTINCT sessions must have asked a query before it is worth a warm
#: slot. **Two, and never one**, and this is the constant that makes
#: `SEARCH_HEAD_WARM_ENABLED` safe to leave on.
#:
#: One is not a floor, it is the absence of one: a single session retyping the
#: same word is the single most common shape in the organic rows — `patriots`
#: appears four times in nine seconds from one session in the 30-day sample,
#: which is more rows than any other real query has in total. Row-ranked and
#: unfloored, that one person's frustration elects half the head.
#:
#: Two is also what makes the number MEAN something: a query two unrelated
#: sessions asked inside a month is the weakest evidence of shared demand that is
#: still evidence, and the response cache's own 60 s TTL means warming it only
#: pays if somebody else is going to ask it again.
MIN_HEAD_SESSIONS = 2

#: ✅ THIS SHIPS **ON**, AND UNSET MEANS ON — the same convention as the rest of
#: the family, restored by LAT-P102.
#:
#: IT USED TO SHIP OFF, and the reason it no longer does is worth stating,
#: because the change is not a re-weighing of the same evidence. #1916 blocked
#: head selection from `search_query_logs` until a clean distribution existed.
#: LAT-P102 found that the clean distribution can be READ — `session_id` is a
#: write-time flag attached by every real client — and that reading it makes the
#: contaminated rows unreachable by the head query rather than merely
#: outnumbered. See the census in the module docstring; the short version is that
#: the table is **99.66 % session-less automation**, four times worse than
#: #1916's own 23.6 % figure, and all eight of the terms this warmer would have
#: warmed are probe terms.
#:
#: So the guard moved from the env var into `_head_from_user_rows`, and that is
#: strictly stronger: an env var can be flipped by an operator who has not read
#: #1916, whereas a head query that filters on attestation cannot elect a probe
#: term at all. Leaving the switch OFF would now protect nothing and would only
#: keep a fix dark.
#:
#: WHAT THIS SWITCH IS STILL FOR: turning the warmer off when it costs more
#: database time than it saves. Separate from `SEARCH_RESPONSE_CACHE` on purpose
#: — the two failures are
#: different and so are their remedies. If the CACHE is wrong, turn the cache
#: off. If the cache is fine but the WARMER is costing more database time than it
#: saves, turn the warmer off and let the cache keep serving organic repeats. One
#: switch would force an operator to give up the fix to relieve the load.
SEARCH_HEAD_WARM_ENV = "SEARCH_HEAD_WARM_ENABLED"
#: Byte-identical to `search_cache._CACHE_OFF_VALUES`, deliberately: an operator
#: reaching for the kill switch under load must not have to remember that these
#: two neighbouring vars disagree about what "off" spells.
_WARM_OFF_VALUES = frozenset({"0", "false", "no", "off"})

_LOCK_KEY = "bainluck:search_head_warmer:running"
_LOCK_TTL_SECONDS = 180
_LAST_PASS_START_KEY = "bainluck:search_head_warmer:last_pass_start"
_LAST_PASS_START_TTL_SECONDS = 3600

#: The beat's publish period, mirrored here so `derive_message_expiry_s` can be
#: read without the beat file open. `tests/test_tasks_wiring.py` asserts the two
#: agree, so this is a mirror and never a second source of truth.
BEAT_PERIOD_SECONDS = 20.0

#: How many of this beat's messages may be alive in the broker at once.
#: STRUCTURAL, not sampled: `expires / beat_period` of them coexist by
#: construction, and all but one are destined for the floor-skip path. The cap
#: exists so raising the bound stays a bounded act rather than an open one.
MAX_LIVE_MESSAGES = 16


def derive_message_expiry_s(
    *,
    beat_s: float = BEAT_PERIOD_SECONDS,
    lock_ttl_s: float = _LOCK_TTL_SECONDS,
    max_live: int = MAX_LIVE_MESSAGES,
) -> float:
    """How long a `warm-search-head` message must be allowed to live. Derived.

    ## The defect this repairs, measured rather than argued (#3364)

    `_EXPIRING_WARMER_BEATS["warm-search-head"]` was **20**, equal to the beat
    period, under a comment justifying it against the task's own wall: "this
    task's WALL (~4-8 s steady state) is shorter than its period, so a fire that
    could not start a pass IS a superseded message".

    **The reasoning is sound and its premise is the wrong quantity** — latency/182
    wrote exactly that on #3364 and did not claim it. An `expires` bound is not
    compared against the task's wall. It is compared against DELIVERY LATENCY:
    the time a message spends in the broker waiting for a free slot on
    `worker-background`, which runs `--concurrency=2` against 57+ beat entries
    (#1609). The wall governs whether a *delivered* fire can start; it says
    nothing about whether the fire is delivered at all.

    **Measured on production 2026-09-06, three independent ways:**

    * `task-metrics?task=warm_search_head`: **102 starts against 2,949 expected**
      fires over a 58,987 s window — 3.5 % of schedule.
    * `celery/schedule-adherence`: `matched_emitted` **30** in one 600 s bucket,
      i.e. *exactly* the 20 s beat cadence, so the beat is healthy; against
      `matched_delivered` **0**, `undelivered_fraction` **1.0**,
      `matched_coverage_proven` true, `bucket_attribution` `broker_or_worker`,
      and `self_gated_fires` **0**. Publishing is fine; nothing survives to a
      slot, and the task's own floor is not what is stopping it.
    * The same endpoint across the other `background` warmers, where the
      delivered-fire ratio tracks `expires` and not the queue::

          expires 300 -> 0.87   warm-event-concepts
          expires 120 -> 0.37   warm-typeahead        (0.35 candidate-base)
          expires 110 -> 0.23   flush-search-gin-pending-lists
          expires  20 -> 0.03   warm-search-head

      Messages routinely wait minutes for a slot. A 20 s bound discards
      essentially all of them, and it discards them for a delay the bound was
      never aimed at.

    This is the same shape as LAT-P075's repair of the sibling beat, arrived at
    from the other direction: there the messages were held off by the run lock,
    here by the pool. In both cases the fires that could not start were **not
    superseded messages — they were the only start opportunities there were.**

    ## The derived value, and why it is not derived from the delay

    There is no constant in this system that bounds delivery latency. That is
    #1609, it is unbounded by design on a shared pool, and a bound read off a
    sampled maximum has already been wrong twice in this program (42.6 s by
    11.3 s, then 53.920 s by 7.36 s). So the bound is not derived from the delay.

    It is derived from where this task's own responsibility ENDS.
    `_LOCK_TTL_SECONDS` is the longest this task can withhold a slot from its own
    message: the lock cannot be held past its own TTL. A message younger than
    that may still be waiting on a pass of this task; a message older than that
    is not being held off by this warmer at all, it is merely old. That is the
    honest place to stop, and it is a CONSTANT, so the next latency measurement
    cannot move it.

    ## What it costs, stated

    `expires / beat_s` messages are alive at once — 9 at these values — and all
    but one take the floor-skip path under `MIN_PASS_PERIOD_SECONDS`. Production
    measures that path at **11-89 ms**. So the surplus is ~8 skips per pass
    cycle against a >= 45 s floor: well under a second of slot time per cycle.

    The cost that is NOT negligible, and must not be reported as if it were: the
    passes that now actually run. At a delivered-fire ratio in the sibling's
    range the floor admits at most one pass per 45 s, and a real pass measures
    3.3-26.1 s wall (p50 ~7.9 s). That is single-digit percent of a two-slot pool
    and it lands on the queue #1609 and #3480 are both about. It is the load the
    beat's own budget always declared; it is not a new appetite.

    **This does not close #3539.** Restoring delivery makes the effective pass
    period the 60 s the cadence arithmetic assumes instead of the ~576 s it is
    today; #3539 is about that 60 s still not being sound against a 60 s TTL.
    """
    if beat_s <= 0 or lock_ttl_s <= 0:
        raise ValueError("beat period and lock TTL must both be positive")
    if lock_ttl_s <= beat_s:
        # Below the period the flat #1609 rule applies and this task does not
        # belong in the exempt set at all. A REFUSAL, not a quietly clamped value.
        raise ValueError(
            f"lock TTL {lock_ttl_s}s is not above the {beat_s}s beat period, so a "
            f"delivery-latency bound is not what this beat needs"
        )
    live = lock_ttl_s / beat_s
    if live > max_live:
        raise ValueError(
            f"expires {lock_ttl_s}s at a {beat_s}s beat leaves {live:.0f} messages "
            f"alive at once, over the declared cap of {max_live}"
        )
    return float(lock_ttl_s)

#: Redis `TTL` is THREE-VALUED and the two negatives mean opposite things, so
#: they are never collapsed (gotcha #53 — an absent value and a zero value must
#: not read the same).
_TTL_NO_KEY = -2
_TTL_NO_EXPIRY = -1

#: Mirrors the route's `Query(..., min_length=2)`. A query shorter than this
#: cannot be requested, so warming it would warm a key no caller can reach.
_MIN_QUERY_CHARS = 2
_MAX_QUERY_CHARS = 200


def head_warm_enabled() -> bool:
    """Whether a pass may run. **Unset means ON** — see `SEARCH_HEAD_WARM_ENV`.

    FAILS OPEN, like the rest of the family, because a typo must not silently
    disable a latency fix. It used to fail closed, and the asymmetry was doing
    real work at the time: it kept a head that could contain probe traffic from
    being warmed by accident. LAT-P102 moved that guarantee into
    `_head_from_user_rows`, where a filter enforces it instead of an env var, so
    the asymmetry now costs a dark fix and buys nothing.

    Only an EXPLICIT off value turns it off. An unrecognised value is a typo, and
    a typo resolves toward the working state.
    """
    raw = os.environ.get(SEARCH_HEAD_WARM_ENV)
    if raw is None:
        return True
    return str(raw).strip().lower() not in _WARM_OFF_VALUES


def _needs_rebuild(ttl: int | None) -> bool:
    """Whether an entry with remaining life `ttl` must be rebuilt this pass.

    FAILS TOWARD DOING THE WORK, in every ambiguous case, and each case is
    distinct rather than lumped into "falsy":

        >= REFRESH_AHEAD    genuinely fresh; leave it alone
        <  REFRESH_AHEAD    alive but will not survive to the next pass
        _TTL_NO_KEY   (-2)  nothing cached — the head is COLD right now
        _TTL_NO_EXPIRY(-1)  a key with no expiry, which should be impossible
                            here; a bug to correct, not a state to rest on
        None                REDIS DID NOT ANSWER. Not a TTL at all. We would
                            rather issue a redundant rebuild than skip a needed
                            one on the strength of a read that failed.
    """
    if ttl is None:
        return True
    if ttl < 0:
        return True
    return ttl < REFRESH_AHEAD_SECONDS


def _cache_ttl_seconds(key: str) -> int | None:
    """Remaining life of the cached `/search` answer at `key`. None = Redis silent."""
    try:
        from app.tasks.redis_state import get_redis_client

        ttl = get_redis_client().ttl(key)
    except Exception:  # noqa: BLE001 — a warmer never takes the app down
        logger.warning("search_head_warmer: ttl read failed for %s", key, exc_info=True)
        return None
    return None if ttl is None else int(ttl)


def _drop_cached(key: str) -> bool:
    """Force the next route call for `key` to MISS, so it recomputes and re-setexes.

    The whole of hole 2's fix. The route writes its cache only on the miss path,
    so the sole way a warmer can extend an entry's life is to make the entry not
    be there.

    THE COST, STATED: between this delete and the route's write there is a
    window in which a real user asking that question pays a database read. It is
    bounded by ONE recompute and it is strictly better than the alternative,
    which is the entry expiring on its own and EVERY user in the following gap
    paying it.
    """
    try:
        from app.tasks.redis_state import get_redis_client

        get_redis_client().delete(key)
        return True
    except Exception:  # noqa: BLE001
        logger.warning(
            "search_head_warmer: cache drop failed for %s", key, exc_info=True
        )
        return False


def _warm_request():
    """A synthetic anonymous ASGI request, the shape the route reads identity from.

    `search_events` touches the request in exactly two places — `request.state`
    and the `x-session-id` header — and both are for the analytics row, which
    `_suppress_search_log` suppresses for this caller anyway. An empty scope is
    therefore a faithful stand-in rather than a stub with behaviour.
    """
    from starlette.requests import Request

    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/events/search",
            "headers": [],
            "query_string": b"",
        }
    )


async def _warm_one(session, q: str) -> dict:
    """Run ONE head query through the route's own code path. Never raises.

    Running the route rather than a re-implementation is the point: it is what
    makes the warmed body byte-identical to the served one, and it is why there
    is no second assembly path to drift.
    """
    from fastapi import Response

    from app.routes.events import _suppress_search_log, search_events

    # #1866 ON THIS SURFACE. The route's other job is to write the query into
    # `search_query_logs`, which is the table `_head_from_query_log` reads to
    # decide what this warmer warms. Unsuppressed, every pass would vote for its
    # own head ~1,900 times a day per term against ~3 for a real query, and the
    # head would freeze closed within a day. Suppress the vote, keep the code
    # path.
    _suppress_search_log.set(True)

    key = search_response_cache_key(q=q, **SEARCH_WARM_SHAPE)
    started = time.monotonic()

    ttl_before = _cache_ttl_seconds(key)
    if not _needs_rebuild(ttl_before):
        # Reported as its own reason rather than folded into `warmed`: a pass
        # that skipped everything as fresh and a pass that rebuilt everything
        # must not produce the same summary.
        return {
            "q": q,
            "ok": True,
            "reason": "fresh",
            "ttl_before": ttl_before,
            "dropped": False,
            "seconds": round(time.monotonic() - started, 3),
        }

    # Drop unless we KNOW there is nothing to drop. `None` (Redis silent) falls
    # through to the drop attempt on purpose.
    dropped = False if ttl_before == _TTL_NO_KEY else _drop_cached(key)

    try:
        await asyncio.wait_for(
            # EVERY PARAMETER EXPLICIT. The declared defaults are `Query(...)`
            # marker objects and are TRUTHY outside FastAPI, so omitting
            # `debug_timing` would make the route treat this as a debug request,
            # skip the cache in BOTH directions, execute the full query path and
            # warm nothing — a green pass that did no warming, which is the
            # exact failure `app/utils/task_verdict.py` exists to refuse.
            # `typeahead_warmer` records the same trap.
            search_events(
                request=_warm_request(),
                response=Response(),
                q=q,
                debug_timing=False,
                db=session,
                current_user=None,
                **SEARCH_WARM_SHAPE,
            ),
            timeout=PER_QUERY_TIMEOUT_SECONDS,
        )
        return {
            "q": q,
            "ok": True,
            "reason": "warmed",
            "ttl_before": ttl_before,
            "dropped": dropped,
            "seconds": round(time.monotonic() - started, 3),
        }
    except asyncio.TimeoutError:
        # The route may have left an aborted transaction behind, and the next
        # query on THIS session would fail on a poisoned one. Each worker owns
        # its own session, so this contains the damage to one worker's slice
        # rather than to the whole pass (gotcha #42, at session level).
        await _safe_rollback(session)
        return {
            "q": q,
            "ok": False,
            "reason": "timeout",
            "ttl_before": ttl_before,
            "dropped": dropped,
            "seconds": round(time.monotonic() - started, 3),
        }
    except Exception:  # noqa: BLE001
        logger.warning("search_head_warmer: %r failed", q, exc_info=True)
        await _safe_rollback(session)
        return {
            "q": q,
            "ok": False,
            "reason": "error",
            "ttl_before": ttl_before,
            "dropped": dropped,
            "seconds": round(time.monotonic() - started, 3),
        }


async def _safe_rollback(session) -> None:
    try:
        await session.rollback()
    except Exception:  # noqa: BLE001
        logger.warning("search_head_warmer: rollback failed", exc_info=True)


def _acquire_run_lock() -> bool:
    """True if THIS run owns the lock. Fails OPEN if Redis is unreachable.

    The lock stops duplicate work; it does not enforce correctness. A doubled
    warm is wasteful, a warmer that silently stops warming because Redis blinked
    is the defect this whole family of modules is about.
    """
    try:
        from app.tasks.redis_state import get_redis_client

        got = get_redis_client().set(_LOCK_KEY, "1", nx=True, ex=_LOCK_TTL_SECONDS)
        return bool(got)
    except Exception:  # noqa: BLE001
        logger.warning(
            "search_head_warmer: lock unavailable, running anyway", exc_info=True
        )
        return True


def _release_run_lock() -> None:
    try:
        from app.tasks.redis_state import get_redis_client

        get_redis_client().delete(_LOCK_KEY)
    except Exception:  # noqa: BLE001
        logger.warning("search_head_warmer: lock release failed", exc_info=True)


def _seconds_since_last_pass(now: float) -> float | None:
    """Gap since the last pass STARTED. None when unknown — never 0.0.

    Zero would read as two passes starting at the same instant, which is a
    finding; "we do not know" is a different one (first pass after a restart, or
    Redis unreadable).
    """
    try:
        from app.tasks.redis_state import get_redis_client

        raw = get_redis_client().get(_LAST_PASS_START_KEY)
    except Exception:  # noqa: BLE001
        return None
    if not raw:
        return None
    try:
        return max(0.0, now - float(raw))
    except (TypeError, ValueError):
        return None


def _record_pass_start(now: float) -> None:
    try:
        from app.tasks.redis_state import get_redis_client

        get_redis_client().setex(
            _LAST_PASS_START_KEY, _LAST_PASS_START_TTL_SECONDS, str(now)
        )
    except Exception:  # noqa: BLE001
        logger.warning("search_head_warmer: pass-start write failed", exc_info=True)


#: The head query. Every clause in it is a finding from LAT-P102's census; see
#: the module docstring for the numbers.
#:
#: `session_id IS NOT NULL OR user_id IS NOT NULL` — the attestation filter, and
#: the whole resolution of #1916 for this source. Both shipping clients attach
#: `x-session-id` to every search, so a row carrying one was written on behalf of
#: a real client; no probe, sentinel or warmer in this repo sends that header.
#: The filter excludes by the ABSENCE of an attestation rather than including by
#: the presence of an automation flag, which is the conservative direction: it can
#: under-count a real user whose client sent no session, and it cannot count a
#: probe as one. #1916 asks for the opposite polarity (a positive `origin`
#: written by the writer) and that remains the better instrument — but it needs a
#: column, and this needs none, and the two agree on every row that matters.
#:
#: `count(DISTINCT ...)` in BOTH the HAVING and the ORDER BY — the anti-artifact.
#: Ranking by row count lets one session's retyping elect the head; see
#: `MIN_HEAD_SESSIONS`. Rows break ties only after sessions have spoken.
#:
#: `COALESCE(session_id, 'u:' || user_id)` — a signed-in request usually carries
#: both, and keying on the session first counts per-device rather than per-person.
#: Two devices of one person asking the same question IS two asks of the cache.
_USER_HEAD_SQL = """
    SELECT lower(btrim(query)) AS q,
           count(DISTINCT COALESCE(session_id, 'u:' || user_id)) AS sessions,
           count(*) AS rows_n
    FROM search_query_logs
    WHERE created_at >= now() - make_interval(days => :days)
      AND (session_id IS NOT NULL OR user_id IS NOT NULL)
      AND length(btrim(query)) BETWEEN :lo AND :hi
    GROUP BY 1
    HAVING count(DISTINCT COALESCE(session_id, 'u:' || user_id)) >= :min_sessions
    ORDER BY sessions DESC, rows_n DESC, q ASC
    LIMIT :lim
"""


async def _head_from_user_rows(session, limit: int) -> list[str]:
    """The `/search` head as elected by ATTESTED rows only. Never raises.

    Deliberately NOT `typeahead_warmer._head_from_query_log`, and the divergence
    is the point rather than drift. That function reads the table whole because
    its own surface needs the volume; this one reads it through the attestation
    filter because #1916 blocks the whole-table read for head selection here. Two
    different questions of one table, so two queries — sharing one would mean
    silently changing the typeahead head too.
    """
    from sqlalchemy import text

    try:
        result = await session.execute(
            text(_USER_HEAD_SQL),
            {
                "days": HEAD_WINDOW_DAYS,
                "lo": _MIN_QUERY_CHARS,
                "hi": _MAX_QUERY_CHARS,
                "min_sessions": MIN_HEAD_SESSIONS,
                "lim": limit,
            },
        )
        return [row[0] for row in result.all() if row[0]]
    except Exception:  # noqa: BLE001 — a warmer never takes the app down
        logger.warning("search_head_warmer: user head unreadable", exc_info=True)
        await _safe_rollback(session)
        return []


async def resolve_head(session, limit: int) -> tuple[list[str], str]:
    """Return `(queries, source)` for the `/search` head.

    `source` travels in the summary rather than being inferred, because which
    source produced a head changes what the run MEANS.

    ONE SOURCE AND NO FALLBACK, and the missing fallback is the load-bearing
    part. The obvious kindness here is "if the attested head is empty, fall back
    to the whole table so the warmer has something to do" — and that would
    reinstate #1916's block in the one state where it bites hardest, because the
    attested head is empty precisely when all the traffic is ours. An empty head
    is the correct answer to "what do users want warmed" when no user has asked
    for anything twice. `_summarize` turns it into `partial`, not `complete`.
    """
    rows = await _head_from_user_rows(session, limit)
    head = [normalize_search_query(r) for r in rows or []]
    head = [q for q in head if _MIN_QUERY_CHARS <= len(q) <= _MAX_QUERY_CHARS]
    if not head:
        # NOT an empty success, and the source string says which emptiness it is:
        # nobody asked twice, rather than the table being unreadable.
        return [], f"empty:user_attested:{HEAD_WINDOW_DAYS}d"
    return head, f"db:user_attested:{HEAD_WINDOW_DAYS}d:min{MIN_HEAD_SESSIONS}sess"


async def _warm_head_concurrently(sessions: list, head: list[str]) -> list[dict]:
    """Warm `head` across `sessions`, one query in flight per session.

    A worker pool over a shared cursor rather than per-worker slices: the head's
    queries do not cost the same, so a static slice idles a worker on its slow
    item while another still has several to go. A shared iterator is
    self-balancing and needs no estimate.
    """
    cursor = iter(range(len(head)))
    results: list[dict | None] = [None] * len(head)

    async def _worker(session) -> None:
        for i in cursor:  # next() is atomic under the GIL
            results[i] = await _warm_one(session, head[i])

    await asyncio.gather(*(_worker(s) for s in sessions))
    # Index order, so two identical passes produce comparable evidence rather
    # than completion-order noise.
    return [r for r in results if r is not None]


def _summarize(
    *,
    head: list[str],
    results: list[dict],
    source: str,
    seconds_wall: float,
    since_last: float | None,
    width: int,
    skip_reason: str | None = None,
) -> dict:
    """The contract summary. Speaks `task_verdict`'s vocabulary.

    AN EMPTY HEAD IS `partial`, and that is the load-bearing line. A warmer whose
    entire purpose is that the head is hot must not be able to report `complete`
    while it is cold — "it returned" is not "it worked". An empty head means the
    query log had nothing to say, which is a real finding and a broken guarantee,
    not a successful pass over zero items.
    """
    warmed = [r for r in results if r["ok"]]
    timeouts = [r for r in results if r["reason"] == "timeout"]
    errors = [r for r in results if r["reason"] == "error"]
    rebuilt = [r for r in results if r["reason"] == "warmed"]
    fresh = [r for r in results if r["reason"] == "fresh"]
    # `_TTL_NO_KEY` exactly — never "falsy", never "<= 0". All three non-positive
    # values mean different things and only this one means "the head was cold
    # when the pass reached it".
    expired = [r for r in results if r.get("ttl_before") == _TTL_NO_KEY]
    seconds = [r["seconds"] for r in results]

    return {
        "terminal": (
            "skipped"
            if skip_reason
            else "complete" if head and not timeouts and not errors else "partial"
        ),
        "skip_reason": skip_reason,
        "completed": len(warmed),
        "total": len(head),
        "head_source": source,
        "head": list(head),
        "warmed": len(warmed),
        "timeouts": [r["q"] for r in timeouts],
        "errors": [r["q"] for r in errors],
        # The two halves that `warmed` alone cannot separate: `rebuilt` is work
        # that actually reset a TTL, `fresh` is work correctly skipped. Reporting
        # only their sum is how a pass that rebuilt nothing reads as 8/8.
        "rebuilt": len(rebuilt),
        "fresh": len(fresh),
        # `rebuilt` cannot distinguish an entry that was ALIVE-but-stale from one
        # that was ALREADY DEAD, and those are opposite diagnoses: the first says
        # the threshold fired as designed, the second says a user asking that
        # question paid a database read.
        "expired": len(expired),
        "seconds_total": round(sum(seconds), 3),
        "seconds_max": round(max(seconds), 3) if seconds else 0.0,
        # The number the TTL has to be compared against — the pass DURATION, not
        # the sum of per-query times, which stopped being the same thing the
        # moment concurrency arrived.
        "seconds_wall": round(seconds_wall, 3),
        "concurrency": width,
        "refresh_ahead_s": REFRESH_AHEAD_SECONDS,
        "ttl_s": SEARCH_RESPONSE_TTL_SECONDS,
        "period_s": None if since_last is None else round(since_last, 3),
        "min_period_s": MIN_PASS_PERIOD_SECONDS,
    }


async def _warm_search_head(
    queries: list[str] | None = None,
    head_size: int = DEFAULT_HEAD_SIZE,
    concurrency: int = WARM_CONCURRENCY,
) -> dict:
    """Warm the head of the `/search` distribution. Returns a contract summary.

    Every early exit produces the SAME KEYS as a real pass. A consumer must
    never have to branch on `terminal` to know whether a field exists — an
    absent field and a zero field must not read the same (gotcha #53), and the
    sibling warmer's suite caught exactly this the first time a field was added
    to only one shape.
    """
    from app.tasks.base import get_task_session

    width = max(1, int(concurrency))

    def _no_work(reason: str, period_s: float | None) -> dict:
        return _summarize(
            head=[],
            results=[],
            source="none",
            seconds_wall=0.0,
            since_last=period_s,
            width=width,
            skip_reason=reason,
        )

    if not head_warm_enabled():
        # A deliberate operator state, reported as its own skip reason. "Turned
        # off on purpose" and "wedged" must never produce the same summary.
        logger.info("search_head_warmer: disabled by %s", SEARCH_HEAD_WARM_ENV)
        return _no_work("disabled", None)

    if not _acquire_run_lock():
        logger.info("search_head_warmer: another run holds the lock, skipping")
        return _no_work("lock", None)

    # THE FLOOR, checked under the lock so two beats cannot both pass it. A
    # check-then-act outside the lock would race exactly the way the lock exists
    # to prevent.
    now = time.time()
    since_last = _seconds_since_last_pass(now)
    if since_last is not None and since_last < MIN_PASS_PERIOD_SECONDS:
        _release_run_lock()
        logger.info(
            "search_head_warmer: last pass started %.1fs ago (floor %ds), skipping",
            since_last,
            MIN_PASS_PERIOD_SECONDS,
        )
        return _no_work("min_period", since_last)

    _record_pass_start(now)
    wall_started = time.monotonic()
    try:
        async with AsyncExitStack() as stack:
            sessions = [
                await stack.enter_async_context(get_task_session())
                for _ in range(width)
            ]
            if queries is None:
                head, source = await resolve_head(sessions[0], head_size)
            else:
                head, source = [normalize_search_query(x) for x in queries], "explicit"
            head = [q for q in head if _MIN_QUERY_CHARS <= len(q) <= _MAX_QUERY_CHARS]
            results = await _warm_head_concurrently(sessions[:width], head)
    finally:
        _release_run_lock()

    summary = _summarize(
        head=head,
        results=results,
        source=source,
        seconds_wall=time.monotonic() - wall_started,
        since_last=since_last,
        width=width,
    )
    logger.info(
        "search_head_warmer: %d/%d warmed from %s (%d rebuilt, %d fresh, %d expired) "
        "in %.1fs wall at width %d, %s since last pass (%d timeouts, %d errors)",
        summary["warmed"],
        summary["total"],
        source,
        summary["rebuilt"],
        summary["fresh"],
        summary["expired"],
        summary["seconds_wall"],
        width,
        "unknown" if since_last is None else f"{since_last:.1f}s",
        len(summary["timeouts"]),
        len(summary["errors"]),
    )
    return summary
