"""Keep `/typeahead`'s hot pages resident, so a user never pays the cold read (#1866).

WHAT THIS FIXES, measured rather than assumed (LAT-P056, production `da5e7992`).

`/typeahead`'s cache-MISS cost was decomposed end-to-end at the transport
boundary, n=24 paired miss/hit probes, and the answer was not ambiguous:

    segment    miss p50      share of the 1384.6ms miss cost
    dns          0.011ms     0.00%
    connect      0.165ms     0.00%
    tls        157.644ms     0.25%      <- a real FLOOR, but not the miss cost
    server    1455.496ms    99.74%      <- all of it
    transfer     0.516ms     0.01%      (1875-byte body)

So the miss is server-side. Then EXPLAIN ANALYZE on production named what the
server was doing, and it was not computing — it was **waiting on storage**:

    ILIKE '%red sox%' over futures_outcomes   cold 1094.5ms   hot  27.1ms
    ILIKE '%yankees%'                         cold  426.5ms   hot   5.5ms
    ILIKE '%bruins%'                          cold  219.9ms   hot   5.0ms

On every cold run 95-98% of the node's time was `Shared I/O Read Time` with
hundreds of `Shared Read Blocks`; on every hot run `Shared Read Blocks` was
**0** and the same query, same plan, same rows, cost single-digit ms. The plan
was never wrong — the pg_trgm GIN index pages simply were not resident.

WHY THAT SWINGS BY THE HOUR, and why "accumulating resource" was the wrong
reading (LAT-P054 withdrew it after it failed to replicate across a restart —
correctly, because nothing accumulates here). `ix_futures_outcomes_name_trgm` is
**406 MB** and `ix_futures_name_trgm` **172 MB**, against `shared_buffers` of
**1 GB**. Those two indexes alone want 56% of the entire buffer pool, and they
compete with scheduled work that sweeps it: the prediction-market matcher's
`futures_markets` scans run every 15 minutes and measure 13-21s mean in
`pg_stat_statements`, over a 977 MB table. Residency is therefore a shared
resource under periodic eviction pressure — which looks like drift, is not
monotone, and does not survive a restart, exactly as observed.

WHAT THIS TASK DOES ABOUT IT. It re-touches the head of the query distribution
every 30s, so the cold read is paid by a background worker instead of by
somebody typing.

THE CADENCE IS MEASURED, AND THE FIRST DRAFT OF IT WAS WRONG. It was written as
2 minutes on the reasoning that page residency is a shared resource worth
holding, and that the 45s response TTL was the less interesting of the two
effects. Then residency was measured directly instead of reasoned about:

    t=0 cold  245 read blocks / 221.7ms
    t=2s        0 / 35.5ms      t=30s   0 / 16.8ms
    t=15s       0 /  7.2ms      t=45s   0 /  9.9ms
    ...and a second query at t=60s: 701 blocks, fully EVICTED.

Residency survives 45s and is gone by 60s. A 2-minute warmer would therefore
have left the pages cold for most of every interval: it would have run, reported
success, and delivered nothing — the exact failure this module's tests are
built around, reached by the design rather than by a bug.

So 30s, and the ORDER OF THE TWO EFFECTS IS THE REVERSE of the first draft:

* **The head rides on the response cache.** 30s is inside the route's 45s TTL,
  so a head entry never expires and those users never reach the database at all.
  That is the guarantee.
* **Page residency is the weaker, shared bonus.** It reaches tail queries that
  touch the same index pages, which the response cache cannot do — but it decays
  inside a minute, so nothing is allowed to rest on it.

THAT GUARANTEE WAS FALSE IN PRODUCTION FOR THE WHOLE OF `-51`'s LIFE, and it
failed in TWO independent ways. LAT-P059 measured the first, LAT-P060 the
second; the fix needed both, which is why neither alone had been enough.

**Hole 1 — the beat is 30s but a PASS took 38s.** The head was warmed one query
at a time, so a pass ran 33-59s (median 38.0s, worst 58.9s) while the Redis
run-lock serialised the beats behind it. Measured over 50 invocations / 1246s:
**25 lock skips**, and an interval between real passes of **95.8s** — against a
45s TTL. The head was cold for roughly half of every cycle.

**Hole 2 — A PASS THAT HITS THE CACHE EXTENDS NOTHING, so cadence alone could
never have fixed it.** `routes/events.py` returns the cached body *before* it
reaches its own `setex`, so an entry's life is 45s from its last REBUILD and a
warm read resets no clock. In the same 50-invocation window **12 beats ran a
full 40-query pass in ~0.65s** — 40 Redis GETs, `terminal: complete`,
`warmed: 40/40`, and nothing rebuilt. A green run that did no warming, which is
the exact failure mode the rest of this module is built to refuse.

Hole 2 turns the duty cycle into a SAWTOOTH rather than a ratio. With pass
period T the rebuild period is `T*ceil(45/T)`, so the warm fraction is
`45/(T*ceil(45/T))`:

    T = 95.8s (as shipped)  ->  47.0%      T = 30s  ->  75.0%   <- NOT 100%
    T = 60s                 ->  75.0%      T = 25s  ->  90.0%
    T = 20s                 ->  75.0%      T = 15s  -> 100.0%

Read the T=30 row: making the pass fit inside the beat — the obvious fix, and
the one that was proposed — lands on 75%, and does so NON-MONOTONICALLY (a 20s
pass is no better than a 30s one). Tuning a cadence against a TTL the warmer
cannot refresh is tuning a sawtooth.

SO THE FIX IS TWO CHANGES, and the module now does both:

1. **`WARM_CONCURRENCY`** closes hole 1. A pass fans out over N sessions, so it
   fits inside the beat and stops being skipped.
2. **`REFRESH_AHEAD_SECONDS`** closes hole 2. A query whose cached entry is
   near expiry has that entry DROPPED before the route is called, so the route
   misses, recomputes, and writes a fresh 45s TTL. The rebuild period becomes
   the pass period, and the duty cycle becomes `min(45, T)/T` = 100% for any
   T < 45s — flat, not a sawtooth.

The cost of (2), stated because it is a real if small regression: between the
drop and the route's write there is a window in which a user typing that prefix
pays a database read. It is bounded by ONE recompute, and because the warmer
keeps the pages resident that recompute is the HOT cost (5-27ms), not the 1.4s
cold cost. It replaces a 30-50s cold window per cycle with a ~20ms one, and it
only ever fires on an entry that was seconds from expiring anyway.

THE HEAD IS MEASURED, NEVER GUESSED. Three sources, in order, each one real:

1. ``search:trending:24h`` — the Redis zset `/typeahead` itself writes on every
   call (`routes/events.py`). This IS the live typeahead distribution.
2. ``search_query_logs`` — the /search log (#239 Item 4). Measured 2026-08-14:
   3,423 rows / 210 distinct over 30 days, top-20 = 36% of volume, top-50 = 69%.
3. ``_STATIC_FLOOR`` — cold-start only, for a fresh Redis and an empty table.

NOT LOAD-BEARING, deliberately. A cold miss still builds inline in the route, so
turning this task off makes `/typeahead` slow again — never broken. The tests
assert that, the same contract `event_concept_warmer` carries.
"""

from __future__ import annotations

import asyncio
import logging
import time

from contextlib import AsyncExitStack

logger = logging.getLogger(__name__)

#: How many head queries to warm per run. 40 sits just past the measured
#: top-of-distribution knee (top-50 covered 69% of logged volume) while keeping
#: a warm run's total work small — every query after the first cycle is
#: single-digit-to-low-hundreds of ms because the pages it needs are resident.
DEFAULT_HEAD_SIZE = 40

#: Bound on ONE query, not on the loop. Bounding only the loop boundary lets a
#: single pathological query eat the whole budget and starve the rest of the
#: head — the same failure `event_concept_warmer.PER_KEY_TIMEOUT_SECONDS` exists
#: to prevent, and the reason `/typeahead`'s own deadline is per-request.
PER_QUERY_TIMEOUT_SECONDS = 10

#: How many head queries are warmed at once. FOUR, and the number is bounded by
#: measurement in both directions rather than picked for roundness:
#:
#: * FROM BELOW, by the worst pass rather than the median. The pass must clear
#:   the 30s beat or the run-lock skips the next one, and the worst measured
#:   pass was 58.9s. W=2 gives 29.5s — inside the beat by half a second, which
#:   is no margin at all. W=4 gives 14.7s worst / ~9.5s median, a 2x margin.
#: * FROM ABOVE, by what the concurrency does to the thing this task exists to
#:   protect. These are 40 pg_trgm reads against a 1 GiB `shared_buffers`
#:   (measured: `shared_buffers` = 131072 * 8kB), and production runs at 3
#:   ACTIVE backends, so W=4 roughly doubles peak concurrent query work. That
#:   is the real ceiling; connections are not (measured 2026-08-17:
#:   `max_connections` 500, 21 in use — 479 free, so a connection argument for
#:   any W in this range would be theatre).
#: * A THIRD bound applies if this is ever consolidated onto ONE engine:
#:   `base._get_task_engine()` is `pool_size=3, max_overflow=2`, so a single
#:   engine can hand out at most FIVE concurrent connections. W=4 fits with one
#:   spare; a larger W would silently serialise on pool checkout and the
#:   concurrency would be a lie the summary could not see.
#:
#: Why concurrency is safe here at all, rather than merely tolerable: LAT-P056
#: measured 95-98% of a cold query's time as `Shared I/O Read Time`. These are
#: I/O-WAIT bound, which is the one case where concurrency overlaps waiting
#: instead of multiplying work — and they contend for the buffer pool LESS than
#: four different queries would, because they want the same index pages.
WARM_CONCURRENCY = 4

#: Rebuild a cached entry when it has less than this much life left, instead of
#: reading it back and extending nothing (hole 2 in the module docstring).
#:
#: 35s = one 30s beat plus 5s of margin. The bound it has to satisfy: an entry
#: must survive from this pass until the NEXT pass reaches the same query. Each
#: query is warmed at a fixed offset inside the pass, so that gap is the pass
#: PERIOD (the 30s beat), not the period plus the duration — which is why a
#: 45s TTL has room for it at all, and why the margin can be small.
#:
#: Set this BELOW the beat and entries expire between passes; set it at or above
#: the 45s TTL and every entry is rebuilt unconditionally, which is what the
#: module did before and is merely wasteful rather than wrong. The `fresh` skip
#: it enables is a safety valve for a shortened beat, not an optimisation for
#: today's one — at a 30s beat against a 45s TTL an entry always has ~15s left
#: when a pass reaches it, so today it rebuilds every time, by design.
REFRESH_AHEAD_SECONDS = 35

#: `/typeahead`'s response-cache key, mirrored from `routes/events.py`. Mirrored
#: rather than imported for the same reason `_MAX_QUERY_CHARS` is — importing
#: the route at module scope would make this task's import graph the route's.
#: `test_typeahead_warmer.py` pins the two against each other, so a drift is a
#: red test rather than a warmer that silently refreshes a key nobody reads.
_CACHE_KEY_PREFIX = "bainluck:typeahead:"

#: Redis `TTL` sentinels, named because `-2` and `-1` at a call site are two
#: magic numbers that mean opposite things.
_TTL_NO_KEY = -2
_TTL_NO_EXPIRY = -1

#: Only used when BOTH measured sources are empty (fresh Redis + empty table).
#: Kept deliberately tiny: a static list is a guess about user behaviour, and a
#: long guess is a long wrong answer that also costs real query time every run.
_STATIC_FLOOR: tuple[str, ...] = (
    "world series",
    "stanley cup",
    "world cup",
    "super bowl",
    "nba champion",
)

#: `/typeahead` enforces this itself (`min_length=2`). A shorter string would be
#: rejected by the route, so warming it would burn a slot to raise a 422.
_MIN_QUERY_CHARS = 2

#: Single-run lock. At a 30s cadence a COLD run (every query paying a real disk
#: read) can outlast its own interval, and without this the next beat starts a
#: second copy doing the identical work against the same already-loaded pages —
#: doubling the load at exactly the moment the database is slowest.
_LOCK_KEY = "bainluck:typeahead_warmer:running"

#: Longer than a plausible cold run, short enough that a worker killed mid-run
#: (the 300s hard SIGKILL that records as `no_data`) cannot wedge the warmer
#: off permanently. A lock nobody can release is worse than no lock.
_LOCK_TTL_SECONDS = 120

#: `/typeahead`'s `max_length`. Mirrored rather than imported to keep this module
#: importable without pulling the route in at module scope; the test asserts the
#: two agree, so a drift is a red test rather than a silent 422 every run.
_MAX_QUERY_CHARS = 200


def _head_from_redis(limit: int) -> list[str]:
    """The live `/typeahead` distribution, straight from the zset it writes."""
    try:
        from app.tasks.redis_state import get_redis_client

        rc = get_redis_client()
        raw = rc.zrevrange("search:trending:24h", 0, limit - 1)
    except Exception:  # noqa: BLE001 — a warmer never takes the app down
        logger.warning("typeahead_warmer: trending zset unreadable", exc_info=True)
        return []

    out = []
    for item in raw or []:
        q = item.decode() if isinstance(item, (bytes, bytearray)) else str(item)
        q = q.strip().lower()
        if _MIN_QUERY_CHARS <= len(q) <= _MAX_QUERY_CHARS:
            out.append(q)
    return out


async def _head_from_query_log(session, limit: int) -> list[str]:
    """The /search log's 30-day head — a real distribution, a different surface.

    Second rather than first precisely BECAUSE it is a different surface: it
    records `/api/events/search`, while the zset records `/typeahead`. Both are
    measured; the one that measures the endpoint being warmed wins.
    """
    from sqlalchemy import text

    try:
        result = await session.execute(
            text(
                """
                SELECT lower(btrim(query)) AS q
                FROM search_query_logs
                WHERE created_at >= now() - interval '30 days'
                  AND length(btrim(query)) BETWEEN :lo AND :hi
                GROUP BY 1
                ORDER BY count(*) DESC
                LIMIT :lim
                """
            ),
            {"lo": _MIN_QUERY_CHARS, "hi": _MAX_QUERY_CHARS, "lim": limit},
        )
        return [row[0] for row in result.all() if row[0]]
    except Exception:  # noqa: BLE001
        logger.warning("typeahead_warmer: query-log head unreadable", exc_info=True)
        await session.rollback()
        return []


async def resolve_head(session, limit: int) -> tuple[list[str], str]:
    """Return `(queries, source)`. `source` is reported so a run is attributable.

    Falling back is not a silent degradation here — which source produced the
    head changes what the run MEANS, so it travels in the summary rather than
    being inferred from the query list.
    """
    head = _head_from_redis(limit)
    if head:
        return head[:limit], "redis:search:trending:24h"

    head = await _head_from_query_log(session, limit)
    if head:
        return head[:limit], "db:search_query_logs:30d"

    return list(_STATIC_FLOOR[:limit]), "static_floor"


def _cache_ttl_seconds(q: str) -> int | None:
    """Remaining life of `/typeahead`'s cached answer for `q`, in seconds.

    Returns None when Redis cannot answer — and None means "do not skip", so an
    unreadable Redis degrades into the old always-rebuild behaviour rather than
    into a warmer that decides everything is fresh and stops working. Fails
    toward doing the work, exactly as `_acquire_run_lock` fails open.

    Redis TTL is THREE-VALUED and the two negatives mean opposite things, so
    they are returned distinctly rather than collapsed (gotcha #53 — an absent
    value and a zero value must never read the same):

        >= 0                 seconds of life remaining
        _TTL_NO_KEY   (-2)   nothing is cached; the route will miss on its own
        _TTL_NO_EXPIRY(-1)   a key with no expiry, which should be impossible
                             here and is treated as NEEDING a rebuild, not as
                             infinitely fresh — an entry that never expires is
                             a bug to correct, not a state to rest on
        None                 REDIS DID NOT ANSWER. Not a TTL at all.

    Collapsing the last one into "no key" was the first draft of this function
    and it would have made an unreadable Redis report a successful rebuild.
    """
    try:
        from app.tasks.redis_state import get_redis_client

        ttl = get_redis_client().ttl(_CACHE_KEY_PREFIX + q)
    except Exception:  # noqa: BLE001 — a warmer never takes the app down
        logger.warning("typeahead_warmer: ttl read failed for %r", q, exc_info=True)
        return None

    return None if ttl is None else int(ttl)


def _drop_cached(q: str) -> bool:
    """Force the next route call for `q` to MISS, so it recomputes and re-setexes.

    This is the whole of hole 2's fix. The route writes its cache only on the
    miss path, so the sole way a warmer can extend an entry's life is to make
    the entry not be there.
    """
    try:
        from app.tasks.redis_state import get_redis_client

        get_redis_client().delete(_CACHE_KEY_PREFIX + q)
        return True
    except Exception:  # noqa: BLE001
        logger.warning("typeahead_warmer: cache drop failed for %r", q, exc_info=True)
        return False


async def _warm_one(session, q: str, refresh_ahead: int = REFRESH_AHEAD_SECONDS) -> dict:
    """Run ONE query through the route's own code path. Never raises."""
    from app.routes.events import typeahead_search

    started = time.monotonic()

    # REFRESH-AHEAD. Before LAT-P060 this call went straight to the route, which
    # returned the cached body without touching its TTL — so a "warm" of a warm
    # entry was a 16ms Redis GET that reset no clock, and 12 of every 50 beats
    # were exactly that. The entry is now dropped when it is close enough to
    # expiry that it would not survive until the next pass.
    ttl_before = _cache_ttl_seconds(q)

    if ttl_before is not None and ttl_before > refresh_ahead:
        # Genuinely fresh. Reported as its own reason rather than folded into
        # `warmed`: a pass that skipped everything as fresh and a pass that
        # rebuilt everything must not produce the same summary.
        return {"q": q, "ok": True, "reason": "fresh",
                "ttl_before": ttl_before, "dropped": False,
                "seconds": round(time.monotonic() - started, 3)}

    # Drop unless we KNOW there is nothing to drop. `None` (Redis silent) falls
    # through to the drop attempt on purpose: we would rather issue a redundant
    # DELETE than skip a needed one on the strength of a read that failed.
    dropped = False if ttl_before == _TTL_NO_KEY else _drop_cached(q)

    try:
        await asyncio.wait_for(
            # PASS THE DEBUG FLAGS EXPLICITLY. They default to `Query(False)`,
            # which is a FastAPI marker object and is TRUTHY — so omitting them
            # makes the route read `not debug_evidence` as False and skip BOTH
            # the cache read and the cache write. The warmer would then execute
            # the full query path, warm nothing into Redis, and report success:
            # a green run that did no warming, indistinguishable from a healthy
            # one (gotcha #53). `test_typeahead_warmer.py` pins this.
            typeahead_search(
                q=q,
                debug_evidence=False,
                debug_timing=False,
                db=session,
            ),
            timeout=PER_QUERY_TIMEOUT_SECONDS,
        )
        return {"q": q, "ok": True, "reason": "warmed",
                "ttl_before": ttl_before, "dropped": dropped,
                "seconds": round(time.monotonic() - started, 3)}
    except asyncio.TimeoutError:
        # The route may have left an aborted transaction behind; the next query
        # on THIS session would fail on a poisoned one. Under concurrency each
        # worker owns its own session, so this contains the damage to one
        # worker's slice of the head instead of the whole pass — the
        # per-item-guard rule (gotcha #42) now holds at the session level too.
        await _safe_rollback(session)
        return {"q": q, "ok": False, "reason": "timeout",
                "ttl_before": ttl_before, "dropped": dropped,
                "seconds": round(time.monotonic() - started, 3)}
    except Exception:  # noqa: BLE001
        logger.warning("typeahead_warmer: %r failed", q, exc_info=True)
        await _safe_rollback(session)
        return {"q": q, "ok": False, "reason": "error",
                "ttl_before": ttl_before, "dropped": dropped,
                "seconds": round(time.monotonic() - started, 3)}


def _acquire_run_lock() -> bool:
    """True if THIS run owns the lock. False means another run is in flight.

    Fails OPEN: if Redis is unreachable we warm anyway. The lock exists to stop
    duplicate work, not to enforce correctness — a doubled warm is wasteful, a
    warmer that silently stops warming because Redis blinked is the bug this
    whole file is about.
    """
    try:
        from app.tasks.redis_state import get_redis_client

        rc = get_redis_client()
        return bool(rc.set(_LOCK_KEY, "1", nx=True, ex=_LOCK_TTL_SECONDS))
    except Exception:  # noqa: BLE001
        logger.warning("typeahead_warmer: lock unavailable, warming anyway", exc_info=True)
        return True


def _release_run_lock() -> None:
    try:
        from app.tasks.redis_state import get_redis_client

        get_redis_client().delete(_LOCK_KEY)
    except Exception:  # noqa: BLE001
        logger.warning("typeahead_warmer: lock release failed", exc_info=True)


async def _safe_rollback(session) -> None:
    try:
        await session.rollback()
    except Exception:  # noqa: BLE001
        logger.warning("typeahead_warmer: rollback failed", exc_info=True)


async def _warm_head_concurrently(sessions: list, head: list[str]) -> list[dict]:
    """Warm `head` across `sessions`, one query in flight per session.

    A worker-pool over a shared cursor rather than a per-worker slice, because
    slices assume the queries cost the same and they do not — `seconds_max` was
    5.6s against a ~1.0s mean, so one slow query in a static slice idles its
    worker's whole remainder while another worker still has ten to go. Pulling
    from a shared cursor is self-balancing and needs no estimate.

    ONE query in flight per session is a hard invariant, not a tuning choice:
    an `AsyncSession` is not safe for concurrent use, so a second coroutine on
    the same session is a corruption bug, not a slowdown. The pool's width IS
    the session count for that reason.
    """
    cursor = iter(range(len(head)))
    results: list[dict | None] = [None] * len(head)

    async def _worker(session) -> None:
        for i in cursor:  # a shared iterator; next() is atomic under the GIL
            results[i] = await _warm_one(session, head[i])

    await asyncio.gather(*(_worker(s) for s in sessions))

    # Order is preserved by index, so the summary reads in head order rather
    # than in completion order — otherwise two identical passes would produce
    # differently-ordered evidence and diffing them would be noise.
    return [r for r in results if r is not None]


async def _warm_typeahead(
    queries: list[str] | None = None,
    head_size: int = DEFAULT_HEAD_SIZE,
    concurrency: int = WARM_CONCURRENCY,
) -> dict:
    """Warm the head of the `/typeahead` distribution. Returns a contract summary.

    The summary speaks the `task_verdict` vocabulary (`terminal` +
    `completed`/`total` + `errors`), and a run that warmed NOTHING reports
    `partial` with `total: 0` rather than a clean `complete`. A warmer whose
    entire purpose is that the head is hot must not be able to report success
    while it is cold — that is the ten-week failure `app/utils/task_verdict.py`
    exists to prevent.
    """
    from app.tasks.base import get_task_session

    if not _acquire_run_lock():
        # A skip is an accounted-for outcome, not a success and not damage: the
        # head IS being warmed, by the run that holds the lock. It gets its own
        # terminal value so a warmer that skips every single beat — a wedged
        # lock — cannot hide inside `complete`.
        logger.info("typeahead_warmer: another run holds the lock, skipping")
        return {
            "terminal": "skipped",
            "completed": 0,
            "total": 0,
            "head_source": "none",
            "warmed": 0,
            "timeouts": [],
            "errors": [],
            "seconds_total": 0.0,
            "seconds_max": 0.0,
            # Same KEYS as a real pass, so a consumer never has to branch on
            # terminal to know whether a field exists. An absent field and a
            # zero field must not read the same (gotcha #53) — here they are
            # both present and both honestly zero.
            "seconds_wall": 0.0,
            "concurrency": max(1, int(concurrency)),
            "rebuilt": 0,
            "fresh": 0,
            "refresh_ahead_s": REFRESH_AHEAD_SECONDS,
        }

    width = max(1, int(concurrency))
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
                head, source = [q.strip().lower() for q in queries], "explicit"

            head = [q for q in head if _MIN_QUERY_CHARS <= len(q) <= _MAX_QUERY_CHARS]

            results = await _warm_head_concurrently(sessions[:width], head)
    finally:
        _release_run_lock()
    seconds_wall = round(time.monotonic() - wall_started, 3)

    warmed = [r for r in results if r["ok"]]
    timeouts = [r for r in results if r["reason"] == "timeout"]
    errors = [r for r in results if r["reason"] == "error"]

    rebuilt = [r for r in results if r["reason"] == "warmed"]
    fresh = [r for r in results if r["reason"] == "fresh"]

    seconds = [r["seconds"] for r in results]
    summary = {
        # An empty head is a FAILURE of this task's purpose, not a quiet success.
        "terminal": "complete" if head and not timeouts and not errors else "partial",
        "completed": len(warmed),
        "total": len(head),
        "head_source": source,
        "warmed": len(warmed),
        "timeouts": [r["q"] for r in timeouts],
        "errors": [r["q"] for r in errors],
        "seconds_total": round(sum(seconds), 3),
        "seconds_max": round(max(seconds), 3) if seconds else 0.0,
        # LAT-P060. `seconds_total` is the SUM of per-query times and is what it
        # always was, so it stays comparable across the concurrency change. It
        # is NO LONGER the pass duration — that is `seconds_wall`, and it is the
        # number the 45s TTL has to be compared against. Reporting only the sum
        # after adding concurrency would have shown a pass "not getting faster"
        # while the thing that matters halved.
        "seconds_wall": seconds_wall,
        "concurrency": width,
        # The two halves of hole 2, separated. `rebuilt` is work that actually
        # reset a TTL; `fresh` is work correctly skipped. Before LAT-P060 every
        # run reported `warmed: 40/40` whether it rebuilt forty entries or read
        # forty warm ones back, and 12 of every 50 beats were the latter.
        "rebuilt": len(rebuilt),
        "fresh": len(fresh),
        "refresh_ahead_s": REFRESH_AHEAD_SECONDS,
    }
    logger.info(
        "typeahead_warmer: %d/%d warmed from %s (%d rebuilt, %d fresh) in %.1fs wall "
        "/ %.1fs summed at width %d (%d timeouts, %d errors)",
        len(warmed), len(head), source, len(rebuilt), len(fresh),
        seconds_wall, summary["seconds_total"], width,
        len(timeouts), len(errors),
    )
    return summary
