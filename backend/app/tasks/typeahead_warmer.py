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


async def _warm_one(session, q: str) -> dict:
    """Run ONE query through the route's own code path. Never raises."""
    from app.routes.events import typeahead_search

    started = time.monotonic()
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
                "seconds": round(time.monotonic() - started, 3)}
    except asyncio.TimeoutError:
        # The route may have left an aborted transaction behind; the next query
        # in the loop shares this session and would fail on a poisoned one.
        await _safe_rollback(session)
        return {"q": q, "ok": False, "reason": "timeout",
                "seconds": round(time.monotonic() - started, 3)}
    except Exception:  # noqa: BLE001
        logger.warning("typeahead_warmer: %r failed", q, exc_info=True)
        await _safe_rollback(session)
        return {"q": q, "ok": False, "reason": "error",
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


async def _warm_typeahead(
    queries: list[str] | None = None,
    head_size: int = DEFAULT_HEAD_SIZE,
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
        }

    try:
        async with get_task_session() as session:
            if queries is None:
                head, source = await resolve_head(session, head_size)
            else:
                head, source = [q.strip().lower() for q in queries], "explicit"

            head = [q for q in head if _MIN_QUERY_CHARS <= len(q) <= _MAX_QUERY_CHARS]

            results = []
            for q in head:
                results.append(await _warm_one(session, q))
    finally:
        _release_run_lock()

    warmed = [r for r in results if r["ok"]]
    timeouts = [r for r in results if r["reason"] == "timeout"]
    errors = [r for r in results if r["reason"] == "error"]

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
    }
    logger.info(
        "typeahead_warmer: %d/%d warmed from %s in %.1fs (%d timeouts, %d errors)",
        len(warmed), len(head), source, summary["seconds_total"],
        len(timeouts), len(errors),
    )
    return summary
