"""Response cache contract for ``GET /api/futures/grouped-feed`` (LAT-P100).

Why this route gets its own module rather than a few lines inside the route:
``feed_cache.py`` exists because the pre-warm beat became a SECOND writer of the
feed's cache key, and a warmer that computes the key even slightly differently
warms a key nobody reads — it fails silently and looks exactly like a warmer
that is working (LAT-P001, and again in LAT-P099 where the native Sports tab
paid a full cold build on every open for two days behind a green test suite).
This route is about to acquire the same two writers, so it gets the same single
source of truth for its key on the way in, not after the same bug.

**What makes this route unusually safe to cache: it takes no principal at all.**
``grouped_feed`` reads ``category``/``sport``/``sports_only``/``limit`` and
nothing else — no user, no session, no personalization context, no request
headers. Its response is a pure function of those four values over the current
``futures_markets`` rows. So unlike the feed there is no ``anon``/``s:``/``u:``
segment to get wrong, no inert-principal share to route through, and no risk of
serving one person's content to another: there is only ever one entry per shape
and everyone reads it.

Measured before the cache existed (LAT-P100, production slug ``7833da68``,
server time, n=6 per shape):

    ?limit=20                     native Sports tab   1,034.5 ms p50   max 1,308
    ?limit=20&sports_only=true    web Sports page       683.0 ms p50   max   915

paid by every person, on every open of the tab, because the route had no cache
of any kind.

The TTLs are chosen against the warm cadence, which is the part that is easy to
get wrong in a way that shows up as "the cache does not seem to help":
``precompute_discover_candidate_base`` fires every 2 minutes, so a fresh TTL
BELOW 120 s would leave the entry expired for part of every cycle and hand a
cold build to whoever arrived in the gap. 180 s is above the cadence with
headroom for a slow pass; the 600 s stale mirror then covers a beat that fails
or is skipped entirely, exactly as ``FEED_RESPONSE_STALE_TTL_SECONDS`` does for
the feed. Both are far fresher than the data underneath them — the futures
pollers run on 1–2 hour cadences.
"""

from __future__ import annotations

import hashlib
from typing import Optional

#: Version segment. Bump it when the RESPONSE SHAPE changes, so a deploy cannot
#: serve a new client an old body — cheaper and more honest than a migration.
GROUPED_FEED_CACHE_PREFIX = "bainluck:grouped_feed:v1"

#: Fresh TTL. MUST stay above the 2-minute warm cadence (see the module
#: docstring); ``test_grouped_feed_cache.py`` asserts that relationship rather
#: than the number, so re-timing the beat fails the test instead of quietly
#: reintroducing the gap.
GROUPED_FEED_TTL_SECONDS = 180

#: Stale mirror, read only when the fresh entry is gone. This is what makes a
#: failed or skipped beat invisible to users instead of a 1-second stall.
GROUPED_FEED_STALE_TTL_SECONDS = 600

#: ASGI **scope** key marking an internal pre-warm rebuild. Read from the scope
#: and never from a header or query param, for the same reason the feed's marker
#: is: a client that could set it would have a free lever to force cold rebuilds
#: of an expensive endpoint, which is a DoS primitive, not a feature.
GROUPED_FEED_PREWARM_SCOPE_KEY = "bainluck_grouped_feed_prewarm"

#: Response header carrying the route's own cache verdict, so the cache can be
#: confirmed working in production without a timing argument. A timing argument
#: cannot tell a warm cache from a warm Postgres buffer pool; this can.
GROUPED_FEED_CACHE_HEADER = "X-Grouped-Cache"


def grouped_feed_cache_key(
    *,
    category: Optional[str] = None,
    sport: Optional[str] = None,
    sports_only: bool = False,
    limit: int,
) -> str:
    """Build the Redis key for one ``GET /api/futures/grouped-feed`` shape.

    Every parameter the route branches on appears here. That is the whole
    contract: a param that changes the response but not the key serves the wrong
    body, and a param that changes the key but not the response fragments the
    cache into entries nothing reuses. ``test_grouped_feed_cache.py`` derives the
    expected parameter set from the route's own signature, so adding a filter to
    the route without adding it here is a red test rather than a silent bug.
    """
    parts = (
        f"grouped:{category or ''}:{sport or ''}:" f"{bool(sports_only)}:{int(limit)}"
    )
    return f"{GROUPED_FEED_CACHE_PREFIX}:{hashlib.md5(parts.encode()).hexdigest()}"
