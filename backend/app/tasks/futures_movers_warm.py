"""Publish the "Biggest Movers" answer from the task that ranks it (LAT-P115).

WHAT A PERSON WAITS FOR TODAY. `FuturesListView.swift:51` calls `loadMovers()`
on appear, which issues `GET /api/futures/movers?hours=24&limit=10`. The route
caches for 60 s and there is no warmer, so on a site with no steady traffic the
strip is cold essentially every time anyone opens the Futures tab. Measured on
production slug `b8ee7e14`, 2026-08-29: **1,404 ms cold, then 16-20 ms warm for
a minute, then cold again.** LAT-P108 took this endpoint from 11,129 ms to a
sub-second warm read; what it left behind is that almost nobody gets the warm
read.

WHERE THE COLD SECOND ACTUALLY GOES — measured, not assumed.
`EXPLAIN (ANALYZE, BUFFERS)` on the emitted statement, production, same day::

    Limit                                    1,421.6 ms
      Sort                                   1,421.6 ms
        Nested Loop                          1,416.0 ms
          Nested Loop                          772.9 ms
            Aggregate                          763.9 ms
              Limit                            761.9 ms
                Sort                           761.9 ms
                  Index Scan futures_markets   704.8 ms   rows=30,133  blocks=30,048
          Index Scan futures_outcomes            1.6 ms   loops=400

**54 % of the request is choosing the pool.** `ORDER BY max_movement_24h DESC
LIMIT 400` has no index to walk, so every open/active market with a non-null
`max_movement_24h` — 30,133 rows, one heap block each — is read and sorted to
keep 400. That is the shape LAT-P108's own note predicted when it measured pool
200 -> 627 ms and 2500 -> 2,833 ms.

WHY THIS IS NOT AN INDEX. `CREATE INDEX ON futures_markets (max_movement_24h
DESC) WHERE status IN ('open','active')` is the permanent form and it would take
the 762 ms to roughly nothing. It is DDL, the migration slot is integrator-owned
(ruling 080), and this lane has parked three such requests already (P109-1,
P110-1, P111-1). **REQUESTED and parked as P115-1, not taken.** Parking a fourth
index is not a ship, so this queue ships the half it owns.

WHY THE PRODUCER, AND NOT A NEW BEAT. `update_max_movement` already runs every
10 minutes and already computes `MAX(ABS(probability_change_24h))` per market —
it is the task that DECIDES this ranking. The answer cannot change faster than
its own input, so the producer is the honest place to publish it, and riding an
existing beat means **no new beat entry**: the two ledger constants
(`BACKGROUND_INTERVAL_FLOOR`, `BACKGROUND_BEAT_COUNT`) that have conflicted on
several consecutive integration cycles are untouched by this branch, and
`beat_schedule_change` is FALSE.

🔴 A SEPARATE 40 s `realtime` BEAT WAS THE OTHER CANDIDATE AND WAS REFUSED WITH
ITS REASON. LAT-P112 measured `background` delivering p50 138-152 s against a
declared 120 s, max 2,511 s, while `realtime` held p50 40 s against a declared
40 s — so a punctual rail exists and this could have used it. It is refused
because the payload is only as fresh as `update_max_movement`, which is itself
on `background` every 10 minutes: a 40 s warmer would rebuild the identical
bytes ~15 times per change and put a 762 ms pool sort on the realtime queue to
do it. Riding the producer costs one build per change, which is the number of
builds the data justifies.

THE TTL, AND WHY IT IS NOT 60. The route's 60 s is a READER's TTL — "somebody
paid for this, let the next reader have it" — and it stays 60 s, unchanged. A
PRODUCER's TTL has to answer a different question: how long may the last good
answer outlive the beat that should have replaced it? `background`'s measured
worst gap is ~2,511 s, so a TTL at the beat period would leave the strip cold
through every late delivery — the hole LAT-P112 shipped a fix for on a different
surface. `WARM_TTL_SECONDS` covers three missed deliveries, so the strip stays
warm across the delivery jitter that rail actually has, and the answer is at
worst ~30 minutes old on a statistic whose own input refreshes every 10.

WHAT THIS DOES NOT DO. It does not make the cold build cheaper — the 1,404 ms is
still there for the first request after a deploy or a Redis flush, and the route
still serves it exactly as before. It changes no payload, no key, no predicate
and no ordering: the bytes it writes are produced by `build_and_cache_movers`,
the same function the route calls, which is the whole reason that function was
extracted rather than copied.

ONE BAD SHAPE MUST NOT WIPE THE PASS (gotcha #42): each shape is warmed inside
its own try/except and damage lands in ``errors``. The summary speaks
`task_verdict`'s vocabulary and the unit is **shapes WARMED**, never bytes
written, so a pass that visited nothing reads `failed` rather than green —
gotcha #53's shape, "it returned" is not "it worked".
"""

from __future__ import annotations

import logging
import time

logger = logging.getLogger(__name__)


#: The `(hours, limit)` shapes a real client actually asks for, declared as a
#: frozen literal rather than discovered from the cache or from a range.
#:
#: There is exactly one, and naming it is a decision rather than an oversight:
#: shipped iOS asks `hours=24, limit=10` (`APIClient.swift:875`, called by
#: `FuturesListViewModel.loadMovers()` with both values written out). The web
#: client defines `fetchFuturesMovers` at `frontend/lib/api.ts:814` and **calls
#: it from nowhere** — verified by grep over `frontend/` at LAT-P115 — so warming
#: the route's own `limit=20` default would be warming a shape no user requests,
#: paying a 762 ms pool sort every ten minutes to do it.
#:
#: A predicate over observed keys would silently adopt whatever a probe last
#: asked for, which is how a measurement harness ends up steering a production
#: warmer. A new shape joins by an explicit edit, which is a visible commit.
WARMED_MOVERS_SHAPES: tuple[tuple[int, int], ...] = ((24, 10),)

#: Three `background` deliveries of the 10-minute producer beat, so a late or
#: dropped delivery does not uncover the strip. Bounded rather than generous: at
#: 30 minutes the served answer is at worst three refreshes old on a statistic
#: labelled "24h", and a longer TTL would start to make the freshness claim in
#: the payload's own name untrue.
WARM_TTL_SECONDS = 30 * 60

#: The bound on the longest uninterrupted operation — one shape's build. The
#: measured cold build is ~1.4 s; 30 s is far above that and far below
#: `update_max_movement`'s own 120 s `soft_time_limit`, so a wedged build is
#: reported by this timeout instead of eating the column update's budget.
#: Bounding the inner op rather than the loop is the shape gotcha #124's sibling
#: entry records for budget guards.
PER_SHAPE_TIMEOUT_SECONDS = 30


async def warm_futures_movers(db, rc=None) -> dict:
    """Rebuild and re-cache every declared movers shape. Never raises.

    Called as `update_max_movement`'s last act, INSIDE its own guard, so a warm
    failure can never roll back or fail the column update that is that task's
    actual job.
    """
    import asyncio

    from app.routes.futures import build_and_cache_movers

    if rc is None:
        from app.tasks.redis_state import get_redis_client

        rc = get_redis_client()

    started = time.monotonic()
    warmed = 0
    errors: list[str] = []

    for hours, limit in WARMED_MOVERS_SHAPES:
        try:
            await asyncio.wait_for(
                build_and_cache_movers(hours, limit, db, rc, ttl=WARM_TTL_SECONDS),
                timeout=PER_SHAPE_TIMEOUT_SECONDS,
            )
            warmed += 1
        except asyncio.TimeoutError:
            errors.append(f"{hours}:{limit}:timeout")
            logger.warning(
                "warm_futures_movers: shape %s:%s timed out after %ss",
                hours,
                limit,
                PER_SHAPE_TIMEOUT_SECONDS,
            )
        except Exception as exc:  # noqa: BLE001 — one shape must not wipe the pass
            errors.append(f"{hours}:{limit}:error")
            logger.warning(
                "warm_futures_movers: shape %s:%s failed: %s",
                hours,
                limit,
                exc,
                exc_info=True,
            )

    total = len(WARMED_MOVERS_SHAPES)
    if warmed == total:
        terminal = "complete"
    elif warmed:
        terminal = "partial"
    else:
        terminal = "failed"

    return {
        "terminal": terminal,
        "completed": warmed,
        "total": total,
        "errors": errors,
        "ttl_s": WARM_TTL_SECONDS,
        "elapsed_ms": round((time.monotonic() - started) * 1000, 2),
    }
