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

THE HEAD IS ELECTED BY `search_query_logs`, WHOLE, AND THAT IS A DECISION.
`typeahead_warmer` blends two sources — the `/search` log and the
`search:trending:24h` zset — because a typeahead head needs the PREFIXES a user
passes through on the way to a phrase, and `/search` never sees those. This
surface has the opposite need and exactly one unpolluted source that measures
it: `search_query_logs` is written only by `/search`, is time-windowed by its
own query, records SUBMITTED intent, and — since the suppression in
`_record_search_query` — cannot be written by this warmer. Warm the surface you
measure. The 30-day head at the time of writing was `masters winner` (102),
`stanley cup` (101), `world series` (95), `nba champion` (90).

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

🔴 **THIS TASK SHIPS DISABLED. `SEARCH_HEAD_WARM_ENABLED` is unset in production
and unset means OFF.** #1916 measured `search_query_logs` as 23.6% gold-sentinel
traffic and says, in bold, not to source a warmer head from it until a clean
distribution exists. That block is respected rather than stepped over. The full
argument — including why the closed-loop harm #1916 is about cannot occur here,
and what a future window needs to flip it — is on `SEARCH_HEAD_WARM_ENV` below.
**The response cache itself is unaffected and ships live**; it caches what was
actually asked and has no opinion about what is popular, so it is
contamination-proof by construction.

THE COST, STATED, because this lane's own doctrine is that a warmer is not free.
`/search` is a much heavier call than `/typeahead`, so every knob here is set
below its sibling's: 8 terms rather than 40, concurrency 2 rather than 4, and a
45 s floor rather than 30 s. ENABLED, a steady-state pass rebuilds 8 entries at
concurrency 2; at the ~1-2 s per query this endpoint measures that is ~4-8 s of
database time per 45 s, against `background`'s roughly one effective slot
(#1609). DISABLED — the shipping state — a fire takes the `disabled` skip path
at ~1 ms and the beat's draw is negligible.

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

#: 🔴 THIS SHIPS **OFF**, AND UNSET MEANS OFF. That is the opposite of every
#: other switch in this family and it is deliberate.
#:
#: **#1916 blocks head selection from this source, in bold, and that block is
#: respected rather than stepped over.** It measured `search_query_logs` as
#: **23.6 % gold-sentinel traffic** — 848 of 3,600 rows landing in a single
#: 07:09-07:12 UTC minute across 26 of 30 days, which is #1206's nightly gold
#: query sentinel, and whose family phrasings ARE the top of the "real"
#: distribution. Its instruction is *do not tune, re-rank, resize or re-source a
#: warmer head until a clean distribution exists*. Electing a head from that
#: table today means possibly warming a sentinel's echo and calling it demand.
#:
#: TWO THINGS FOR WHOEVER UN-BLOCKS IT, because they are the argument and they
#: should not have to be re-derived:
#:
#: * The specific harm #1916 exists to stop — a CLOSED SELF-ELECTING LOOP — is
#:   structurally absent here. `_warm_one` sets `_suppress_search_log`, so unlike
#:   the `/typeahead` warmer (89 % of whose head score was its own echo) this one
#:   cannot vote for its own head at all. The contamination it would inherit is
#:   fixed at 23.6 % and does not compound.
#: * The cost of being wrong is therefore bounded at WASTED WARM SLOTS — some of
#:   8 — not at a corrupted distribution.
#:
#: That is an argument for flipping it. It is not a decision to flip it, and a
#: build lane is not the right place to overrule a standing block on its own
#: judgment in the same cycle. **`SEARCH_HEAD_WARM_ENABLED=1` is one config var
#: and needs no deploy**, so the cost of shipping off and flipping later is a
#: config change; the cost of shipping on and being wrong is a warmer tuned
#: against our own echo, which is precisely #1916's thesis.
#:
#: The response cache itself is UNAFFECTED and ships live. It is
#: contamination-proof by construction: it caches whatever was actually asked,
#: and has no opinion about what is popular.
#:
#: Separate from `SEARCH_RESPONSE_CACHE` on purpose — the two failures are
#: different and so are their remedies. If the CACHE is wrong, turn the cache
#: off. If the cache is fine but the WARMER is costing more database time than it
#: saves, turn the warmer off and let the cache keep serving organic repeats. One
#: switch would force an operator to give up the fix to relieve the load.
SEARCH_HEAD_WARM_ENV = "SEARCH_HEAD_WARM_ENABLED"
_WARM_ON_VALUES = frozenset({"1", "true", "yes", "on"})

_LOCK_KEY = "bainluck:search_head_warmer:running"
_LOCK_TTL_SECONDS = 180
_LAST_PASS_START_KEY = "bainluck:search_head_warmer:last_pass_start"
_LAST_PASS_START_TTL_SECONDS = 3600

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
    """Whether a pass may run. **Unset means OFF** — see `SEARCH_HEAD_WARM_ENV`.

    FAILS CLOSED, and this is the one switch in this family that does. The
    others default on because a typo must not silently disable a latency fix;
    this one defaults off because a typo must not silently ENABLE head selection
    from a distribution #1916 has measured as contaminated. The asymmetry is the
    point: the expensive mistake runs in opposite directions for the two.
    """
    raw = os.environ.get(SEARCH_HEAD_WARM_ENV)
    if raw is None:
        return False
    return str(raw).strip().lower() in _WARM_ON_VALUES


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


async def resolve_head(session, limit: int) -> tuple[list[str], str]:
    """Return `(queries, source)` for the `/search` head.

    `source` travels in the summary rather than being inferred, because which
    source produced a head changes what the run MEANS.

    One source, whole, and the reasoning is in the module docstring: warm the
    surface you measure. `_head_from_query_log` is imported from
    `typeahead_warmer` rather than copied — it is the same SQL over the same
    table, and two copies of a head query is two heads that can drift.
    """
    from app.tasks.typeahead_warmer import _head_from_query_log

    rows = await _head_from_query_log(session, limit)
    head = [normalize_search_query(r) for r in rows or []]
    head = [q for q in head if _MIN_QUERY_CHARS <= len(q) <= _MAX_QUERY_CHARS]
    if not head:
        # NOT an empty success. `_summarize` turns this into `partial`.
        return [], "empty:search_query_logs:30d"
    return head, "db:search_query_logs:30d"


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
