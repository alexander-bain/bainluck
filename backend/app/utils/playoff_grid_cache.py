"""Cache policy for the championship progression grids (`/api/playoffs/{league}`).

Extracted under ruling 005 (extract-on-touch): #7109 gives this tier a rebuild
path, and a rebuild that does not share the reader's key layout, TTLs and
usability predicate is a second writer that drifts from the first.

🔴 **#7109: THE MIRROR WAS A TERMINUS, NOT A FALLBACK.** The route cached the
grid for 3900 s with a 24 h `:stale` mirror beside it, and on a primary miss it
served the mirror **and stopped** — it rebuilt nothing and rewrote neither key.
Only `tasks/precompute_category_pages._precompute_grids` could refresh a grid,
so a league that lost its warm stayed frozen at whatever the last successful
warm produced, for as long as the mirror survived. Measured on production
2026-09-19 04:13Z:

    /api/playoffs/mlb   last_updated 2026-09-19T00:26:33Z   stale=true   3h47m old
    /api/playoffs/nba   last_updated 2026-09-19T03:26:45Z   fresh
    /api/playoffs/nhl   last_updated 2026-09-19T03:26:28Z   fresh
    /api/playoffs/nfl   last_updated 2026-09-19T03:26:51Z   fresh

Three leagues warmed inside one 23-second window while MLB sat four hours cold,
and every MLB reader — the grid page, and `services/league_context` which calls
`get_playoff_grid_cached` with the same cache-eligible arguments to answer a team
card's "Make Playoffs" — was served the four-hour-old number.

WHY THE BEAT COULD NOT FIX ITSELF, AND WHY THE READER CAN.
`/api/admin/category-precompute/last` for the 01:25Z pass records MLB as
`{"outcome": "timeout", "duration_s": 89.4, "timeout_s": 66.1}` — not
`budget_exhausted`: `ncaa-basketball` ran AFTER mlb in the same pass and
succeeded with 23.1 s of budget to spare. The warm's build of MLB genuinely
exceeds its share on the worker, and it overran its own cancellation by 23.3 s
on top (`duration_s` − `timeout_s`), which is a build sitting in a section
`asyncio.wait_for` cannot interrupt.

The SAME build on the web dyno is fast. Measured the same minute, against the
cache-ineligible door that builds exactly what the cache-eligible request builds
(`trend_hours = hours or config.trend_hours`, and MLB's config is 168 — so
`?hours=168` is byte-for-byte the default build, unlike `?hours=24` which
quietly measures a cheaper chart):

    /api/playoffs/mlb?hours=168   200   7.62 s      <- the real shape
    /api/playoffs/mlb?hours=24    200   7.09 s
    /api/playoffs/nba?hours=168   200   2.51 s      <- control

7.6 s against the route's own 25 s wall. So the request path can build what the
beat cannot, and the fix is to let it: serve the mirror, rebuild behind it.

WHAT THIS MODULE DOES NOT DO.
It does not touch the warm beat. The beat's MLB timeout is real and is its own
defect — this makes it stop reaching the reader, which is what #7109 is. Nor
does it age-bound the mirror the way `futures_categories_cache` does: that tier
prints counts a reader can reproduce by tapping a tile, so a day-old mirror is a
lie; a championship probability is not reproducible by inspection and the
existing `stale` label already discloses it. Turning a stale grid into a 503 for
a league whose build is broken is a product call, not a latency fix, and it is
not taken here.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from app.utils.event_concept_cache import (
    ConceptCacheKeys,
    cache_keys,
    serve_stale_and_refresh,
)

logger = logging.getLogger(__name__)

#: This tier's Redis namespace. The keys are ALREADY LIVE in production under
#: this prefix, and `cache_keys` produces exactly `<prefix><slug>` and
#: `<prefix><slug>:stale` — so adopting the shared layout here is an adoption of
#: the existing policy and not a migration. It also hands this tier the
#: `:refreshing` slot, which is the single-flight lock the rebuild needs and the
#: only key in the layout that is new.
CACHE_PREFIX = "bainluck:category:playoffs:"

#: How long a freshly-built grid answers directly. Unchanged at 3900 s (#901:
#: raised from 900 so a request-rebuilt grid outlives the hourly warm instead of
#: forcing repeated cold rebuilds). What #7109 changes is that expiring no longer
#: ends the grid's life — it schedules its replacement.
PRIMARY_TTL = 3900

#: The mirror. A full day, because its job is to outlive an outage of the thing
#: that writes it.
MIRROR_TTL = 86400

#: Ceiling on a refresh-behind build. The measured worst case is 7.6 s (MLB, the
#: slowest grid, at its true shape); this is an order of magnitude above it and
#: deliberately BELOW `event_concept_cache.REFRESH_LOCK_TTL` (120 s), so a
#: rebuild can never outlive its own single-flight lease and admit a second
#: builder while the first is still running.
REFRESH_TIMEOUT_S = 90


def grid_cache_keys(league_slug: str) -> ConceptCacheKeys:
    """Every Redis key one league's grid owns.

    Shared by the route, the refresh-behind and the degradation path so the three
    can never disagree about where the mirror lives — the `:stale` suffix was
    being re-derived at three call sites before this.
    """
    return cache_keys(league_slug, prefix=CACHE_PREFIX)


def publish_grid(rc, league_slug: str, payload: Any) -> bool:
    """Write both slots for `league_slug`, but only for a servable payload.

    Returns True when the grid was published, False when it was refused.

    🔴 The refusal is the load-bearing half and it asks *the route's own
    read-side predicate*, not a private copy. This write owns the 24 h mirror,
    so publishing a transiently-empty build does not merely fail to help: it
    replaces a working grid with one the reader then refuses as a fallback,
    turning a healthy page into a live rebuild — and for a league whose build
    straddles the wall a live rebuild is the 503. Several leagues build empty
    out of season, so this is the ordinary case, not a hypothetical.
    """
    from app.routes.playoffs import _grid_payload_usable

    if not _grid_payload_usable(payload):
        return False

    keys = grid_cache_keys(league_slug)
    body = json.dumps(payload, default=str)
    rc.setex(keys.primary, PRIMARY_TTL, body)
    rc.setex(keys.stale, MIRROR_TTL, body)
    return True


async def rebuild_grid(league_slug: str) -> bool:
    """Build one league's grid on its OWN session and publish it.

    Returns True when a servable grid was published.

    🔴 The session is opened here and not passed in. This runs BEHIND a response
    that has already been served, and the request's `AsyncSession` is not ours to
    hold past it — reusing it is how a background task ends up writing into a
    closed session (`serve_stale_and_refresh`'s contract, and the reason it takes
    a zero-arg coroutine function rather than a coroutine).

    The arguments are `get_playoff_grid_cached`'s `cache_eligible` arguments
    exactly (`hours is None`, `top == 10`, `debug` false). A refresh that built a
    different shape than the one the cache serves would publish a payload the
    next reader is not asking for.
    """
    import asyncio

    from app.routes.playoffs import get_playoff_grid
    from app.tasks.base import get_task_session
    from app.tasks.redis_state import get_redis_client

    async with get_task_session() as session:
        result = await asyncio.wait_for(
            get_playoff_grid(league_slug, None, 10, False, session),
            timeout=REFRESH_TIMEOUT_S,
        )

    published = publish_grid(get_redis_client(), league_slug, result)
    if not published:
        logger.warning(
            "playoff grid: refresh-behind for %s built an unusable payload — "
            "keeping last-good",
            league_slug,
        )
    return published


def schedule_grid_refresh(league_slug: str, rc=None) -> bool:
    """Kick exactly one fleet-wide rebuild of `league_slug` and return at once.

    Returns True when a rebuild is now running (here or in another process).

    Single-flight across the fleet, not just this process: a burst of readers
    arriving behind one TTL expiry produces one rebuild. `rc` is left None on
    purpose at the route's call site — the lock is taken with the shared SYNC
    client, and the route's async client cannot answer `set(nx=True)`.

    🔴 BEST-EFFORT, AND THE RETURN VALUE IS INFORMATION, NOT AN INSTRUCTION. The
    caller has already decided to serve the mirror and nothing here may change
    that decision or raise into it. False means the sync client is unreachable —
    in which case a synchronous rebuild could not have published its result
    either, so making the reader pay for one would buy nothing. The mirror's own
    TTL is what bounds a refresh that never succeeds.
    """

    async def _rebuild() -> None:
        await rebuild_grid(league_slug)

    try:
        return serve_stale_and_refresh(grid_cache_keys(league_slug), _rebuild, rc=rc)
    except Exception:  # noqa: BLE001
        logger.warning(
            "playoff grid: could not schedule refresh-behind for %s",
            league_slug,
            exc_info=True,
        )
        return False
