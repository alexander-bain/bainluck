"""Rebuild the Search page's category census before a reader has to (LAT-P137).

WHAT A PERSON WAITS FOR TODAY. ``/search`` renders ``CategoryBrowser``
(`frontend/app/search/page.tsx:355`), whose first act on mount is
``fetchFuturesCategories()`` (`components/CategoryBrowser.tsx:70`). Until that
answers there is no category grid — the whole content of the empty-query search
page is a skeleton. LAT-P122 gave that tier a shared Redis slot and a 24 h
mirror, which took the cost off the second reader. **It gave it no producer.**
Nothing on the fleet rebuilds the census; only a reader does.

So the tier's cost did not go away, it became conditional, and the condition is
one nobody watches: ``futures_categories_cache.stale_serve_ceiling_seconds()``
— 25 minutes — is how old the mirror may be and still be served. Past that the
reader blocks and rebuilds. Measured on production slug ``fe5ec72c``,
2026-08-30 (LAT-P137, `x-timing-split`)::

    00:41:37Z  wall=1365.4; db=1330.7; app=34.7; q=1   <- mirror over the ceiling
    00:50:08Z  wall=28.0;   db=0.0;    app=28.0; q=0   <- mirror serve, 9 min later
    00:50:11Z  wall=23.8;   db=0.0;    app=23.8; q=0

The 1,365 ms read is not a cold-start artifact: it is what the tier does
whenever the last build is more than 25 minutes old, and on 2026-08-30 the last
build was more than 25 minutes old at the first probe of the session. Both fast
reads are the SAME payload (``created_at`` 00:41:37 on each), which is the point
— one visitor pays 1.4 s so the next few get 28 ms.

WHY A WARMER AND NOT A CHEAPER QUERY. The statement reads 39,014 shared blocks
because the two negated ``ILIKE``s are unindexable; LAT-P122 measured it and
said so, and this ship does not make it faster either. What changes is WHO runs
it: a background beat, every 5 minutes, instead of whichever person happened to
open Search after a quiet half hour.

🔴 THE PERIOD IS DERIVED FROM THE TIER'S OWN CEILING, NOT CHOSEN. A literal 300
here would be a second copy of a number that already exists in
``futures_categories_cache``, and #2236 is the incident where a 120 in one file
and a 60 in another, with nothing comparing them, left a payload uncovered for a
full minute of every two. ``WARM_PERIOD_SECONDS`` is computed from
``stale_serve_ceiling_seconds()`` so that ``MISSED_DELIVERY_ALLOWANCE``
consecutive lost deliveries still cannot uncover a reader — and if a later
queue shortens the ceiling (it is a FRESHNESS contract: these counts are printed
to the user as "6,581" beside Politics), the period follows it down instead of
silently becoming too slow.

WHAT THIS DOES NOT DO, named so it is a decision rather than an oversight.

* It does not change the route, the payload, the keys, the predicate or the
  TTLs. It calls ``routes.futures._rebuild_futures_categories`` — the same
  zero-argument coroutine the route's own serve-stale path dispatches — so the
  bytes a warm publishes and the bytes a reader's rebuild publishes cannot
  drift. Turning this beat off restores exactly today's behaviour: slow for
  whoever arrives after a quiet 25 minutes, never wrong.
* It does not touch ``/api/feed/tag-counts``, whose futures half is the same
  predicate family with no cache of any kind (parked P136-2). That surface needs
  a cache before it needs a producer, which is a different ship.
* It does not extend the mirror's serve ceiling. A warmer that "fixed" this by
  serving older counts would be shipping a formatting lie through a latency fix.

A ZERO-YIELD RUN READS FAILED, NOT GREEN (gotcha #53). ``write()`` reports that
a client accepted the bytes, never that Redis kept them, so this task READS THE
CENSUS BACK and compares ``created_at`` with the value it saw before the
rebuild. "The build returned" is not "the next reader is covered", and those two
are exactly the states a warmer is capable of confusing.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

logger = logging.getLogger(__name__)


#: Bound on the ONE uninterrupted operation this task performs — the census
#: build. The measured build is 1.37-1.59 s across three production reads
#: (LAT-P122 and LAT-P137); 30 s is far above that and far below the task's own
#: soft limit, so a wedged build is reported by this timeout with a reason
#: instead of dying against the task limit with none. Bounding the inner op
#: rather than the loop is the shape the budget-guard gotcha records.
BUILD_TIMEOUT_SECONDS = 30

#: How many consecutive deliveries of this beat may be lost or held off before a
#: reader is uncovered. Four, because `background` is the queue LAT-P112
#: measured delivering p50 138-152 s against a declared 120 s: on a rail with
#: that much jitter, a period sized to survive exactly one missed delivery is a
#: period sized to fail.
#:
#: It is stated as an ALLOWANCE rather than as a period because the allowance is
#: the thing a reader of this file can judge. The period is arithmetic.
MISSED_DELIVERY_ALLOWANCE = 4


def warm_period_seconds() -> int:
    """The beat period, derived from the tier's own stale-serve ceiling.

    ``ceiling / (allowance + 1)``: with the ceiling at 25 minutes and four
    permitted misses, a rebuild every 5 minutes means the mirror is at most
    5 x 5 = 25 minutes old when the fifth delivery in a row fails — the exact
    edge of servable. Anything better than that worst case leaves the reader on
    the mirror, which is a 28 ms Redis read.

    Derived at call time and not frozen into a module constant so that a queue
    editing ``STALE_SERVE_CEILING`` or ``FRESH_TTL`` moves this too. The guard
    test asserts the arithmetic AND that the result is a whole number of minutes
    that divides an hour, because the beat spells it ``*/N`` and a period like
    7 minutes would fire at :00 and :07 and then again at :00 — a silently
    uneven cadence that no assertion on the number itself would catch.
    """
    from app.utils.futures_categories_cache import stale_serve_ceiling_seconds

    return stale_serve_ceiling_seconds() // (MISSED_DELIVERY_ALLOWANCE + 1)


def warm_period_minutes() -> int:
    """`warm_period_seconds()` as the whole minutes the crontab spells."""
    return warm_period_seconds() // 60


def _census_created_at(rc=None) -> str | None:
    """The ``created_at`` of whatever the census currently serves, or None.

    Reads through the tier's own ``read()`` so the primary/mirror ladder and its
    age bound are the ones the READER gets, never a second opinion assembled
    here. A tier that would refuse to serve its mirror to a person must not
    report that mirror to this task as coverage.
    """
    from app.utils import futures_categories_cache as fcc

    try:
        body, _state = fcc.read(rc)
    except Exception:  # noqa: BLE001 — an unreadable cache is a warm reason, not a crash
        logger.warning("warm_futures_categories: census read failed", exc_info=True)
        return None
    if not isinstance(body, dict):
        return None
    created = (body.get("cache") or {}).get("created_at")
    return created if isinstance(created, str) else None


async def _warm_futures_categories(rc=None) -> dict[str, Any]:
    """Rebuild and republish the category census. Never raises.

    The summary speaks the ``task_verdict`` vocabulary, and the unit is a census
    a reader can actually be served — ``published`` — never a build that
    returned. ``terminal`` is ``complete`` only when the census reads back with a
    ``created_at`` this run put there.
    """
    from app.routes.futures import _rebuild_futures_categories

    started = time.monotonic()
    before = _census_created_at(rc)
    error: str | None = None

    try:
        await asyncio.wait_for(
            _rebuild_futures_categories(), timeout=BUILD_TIMEOUT_SECONDS
        )
    except asyncio.TimeoutError:
        error = "timeout"
        logger.warning(
            "warm_futures_categories: build timed out after %ss", BUILD_TIMEOUT_SECONDS
        )
    except Exception as exc:  # noqa: BLE001 — a failed warm must not fail the beat
        error = "error"
        logger.warning("warm_futures_categories: build failed: %s", exc, exc_info=True)

    after = _census_created_at(rc)
    # A republish is a NEW timestamp, not merely a present one: a run whose write
    # was swallowed leaves the previous build readable, and "there is a census"
    # would grade that green forever while the reader's clock runs out on it.
    published = after is not None and after != before

    return {
        "terminal": "complete" if published else "failed",
        "published": published,
        "created_at": after,
        "previous_created_at": before,
        "error": error,
        "period_s": warm_period_seconds(),
        "elapsed_ms": round((time.monotonic() - started) * 1000, 2),
    }
