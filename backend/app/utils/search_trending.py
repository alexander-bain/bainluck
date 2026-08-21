"""The trending-search window — bucketed, so that "24h" is true (#2072).

WHAT WAS WRONG, in the two lines this module replaces::

    rc.zincrby("search:trending:24h", 1, normalized)
    rc.expire("search:trending:24h", 86400)

The `expire` was re-issued on **every write**. The TTL was therefore reset
thousands of times a day and the key never reached it, so `search:trending:24h`
was an **all-time cumulative counter with a 24 h label**. It could only reset by
the site taking zero typeahead traffic for a full day, which has never happened.
Nothing decayed: a zset TTL lives on the KEY, and a key TTL cannot expire
members.

Measured on production 2026-08-21 (build `ec636bae` / v3881)::

    world cup 5414   red sox 5411   celtics 5403   yankees 5400   patriots 5399

Real `/search` volume over **thirty** days tops out at 102.

WHY IT MATTERED TWICE OVER — and the second one is the reason this is not
cosmetic. `typeahead_warmer.resolve_head` reads the top 40 of this zset. #1866
(LAT-P078) found the warmer was voting for its own head — the route's last act
was to `zincrby` the query it had just been asked to warm — and fixed it in two
halves: the route stops counting the warmer's calls, and `resolve_head` blends
the `/search` log in rather than cascading. **Neither half drains what was
already there.** The ~5,400 accumulated scores stayed pinned at the top of the
very zset the warmer reads, so the loop-break stopped NEW pollution while the
OLD pollution kept selecting. A wrong window re-pollutes exactly what the
loop-break just cleaned. This module is the other half of that head.

THE SHAPE, and why the obvious fix was rejected. Moving the `expire` to fire
only on creation does not give a rolling window — it gives "everything, then
suddenly nothing": a full cliff every 24 h from the first write, after which the
warmer cold-starts on `_STATIC_FLOOR` once a day. So the window is bucketed by
hour, each bucket with a fixed TTL, and a read sums the buckets still in range.
Old buckets expire on their own; no sweeper exists to fall over.

🔴 **YES, `EXPIRE` IS STILL RE-ISSUED ON EVERY WRITE, AND THAT IS NOT THE OLD
BUG.** The difference is the key's NAME. `search:trending:24h` had no time in
it, so writes to it never stopped and its refreshed TTL never came due.
`search:trending:24h:2026082113` can only be written during the hour it names —
once that hour ends nothing touches it again and the last refresh runs down to
zero. The bound is structural, not a matter of traffic. (`EXPIRE ... NX` would
express the intent more directly but needs Redis >= 7.0, and a fallback path
that is exercised only on old servers is a second shape nobody tests.)

MIGRATION IS A NO-OP, DELIBERATELY. The legacy key is not read, not written and
not deleted here. It carries a live TTL — set by the very bug being removed —
and with its only writer gone it now reaches that TTL and disappears on its own
within 24 h of deploy. Deleting it would be a production write in a request
path. Its all-time scores are the pollution; seeding them into the new buckets
would import the defect.

TRANSITION COST, STATED: for the first hour after deploy the window is thin, and
for the first minutes it is empty. `resolve_head` already handles an empty zset
— it falls through to `db:search_query_logs:30d`, which is the unpolluted
source #1866 made reachable — so the warmer degrades to the BETTER half of its
blend, never to nothing. `GET /api/events/search/trending` returns a short list
for that first hour, which is an honest answer to "what is trending" on a
counter that has just started.

NOT DECIDED HERE (raised in #2072, out of scope): whether the public endpoint
should be counting `/typeahead` keystrokes at all, given that every prefix of
every query lands in the same zset as the completed phrases. Changing that
changes what the warmer heads from too, so it is one decision, not two.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

#: Bucket keys live UNDER the legacy name, which is deliberate: the old key is a
#: zset at `search:trending:24h` and the new ones are hashes of an hour beneath
#: it, so the two cannot collide, the namespace still reads as one thing, and
#: `resolve_head`'s reported source string stays literally true.
TRENDING_BUCKET_PREFIX = "search:trending:24h:"

#: The key this module exists to stop writing. Referenced only so the guard test
#: can name it; nothing here reads, writes or deletes it.
LEGACY_TRENDING_KEY = "search:trending:24h"

#: Whole hours the window must ALWAYS cover. `window_bucket_keys` returns this
#: many buckets plus the current partial one, so real coverage is 24-25 h.
#: Over-covering is the honest direction for a window whose name reads as a
#: floor; under-covering would break the promise for part of every hour.
TRENDING_WINDOW_HOURS = 24

#: A bucket's last possible write is at the end of the hour it names, and it
#: stays in the window until ~25 h after that hour STARTS. 27 h clears that with
#: margin and still bounds a bucket's life at 28 h — it must not be so generous
#: that a bucket becomes the immortal key by another route.
BUCKET_TTL_SECONDS = 27 * 3600

#: Scratch destination for the `ZUNIONSTORE`. Deliberately OUTSIDE
#: `TRENDING_BUCKET_PREFIX`: a scratch zset sitting inside the bucket namespace
#: is a scratch zset that eventually gets summed into itself.
AGGREGATE_KEY = "search:trending:agg:24h"

#: The aggregate is written by a READ path, so an orphan must clear itself. It
#: is recomputed on every read — this TTL is insurance, not a cache.
AGGREGATE_TTL_SECONDS = 300

#: Carried over unchanged from the route. Two-character prefixes are typed on
#: the way to every query and would dominate any count that admitted them.
MIN_QUERY_CHARS = 3


def _now() -> float:
    """Wall clock, isolated to one function so tests can pin it.

    Callers pass `now=` explicitly wherever they can; this is the default for
    the request path, which has no clock of its own to hand down.
    """
    return time.time()


def bucket_key(now: float) -> str:
    """The key for the UTC hour containing `now`.

    UTC, not local: a bucket name that shifts twice a year would silently
    duplicate one hour and lose another.
    """
    stamp = datetime.fromtimestamp(float(now), tz=timezone.utc).strftime("%Y%m%d%H")
    return TRENDING_BUCKET_PREFIX + stamp


def window_bucket_keys(now: float, hours: int = TRENDING_WINDOW_HOURS) -> list[str]:
    """Every bucket in range, newest first.

    `hours + 1` keys: the current partial hour plus `hours` whole ones. Missing
    keys are fine — `ZUNIONSTORE` treats a non-existent key as empty, so a quiet
    hour needs no placeholder and a purged bucket needs no special case.
    """
    return [bucket_key(now - i * 3600.0) for i in range(hours + 1)]


def normalize(query: str) -> str:
    return (query or "").strip().lower()


def record_query(rc: Any, query: str, *, now: float | None = None) -> bool:
    """Count one search into the current hour's bucket. Returns whether it counted.

    Fire-and-forget, exactly as the route's write was: a trending counter is
    never worth failing a user's request over. The boolean is for tests and for
    callers that want to know, not a signal anyone must act on.
    """
    normalized = normalize(query)
    if len(normalized) < MIN_QUERY_CHARS:
        return False
    try:
        key = bucket_key(_now() if now is None else now)
        rc.zincrby(key, 1, normalized)
        rc.expire(key, BUCKET_TTL_SECONDS)
        return True
    except Exception:  # noqa: BLE001 — a trending counter never takes a request down
        logger.warning("search_trending: write failed", exc_info=True)
        return False


def read_window(
    rc: Any,
    limit: int,
    *,
    now: float | None = None,
    hours: int = TRENDING_WINDOW_HOURS,
) -> list[tuple[str, float]]:
    """Top `limit` queries in the rolling window, as `(query, count)`.

    Server-side `ZUNIONSTORE` rather than summing `limit` rows per bucket in
    Python: a per-bucket top-N is an approximation that can rank a term which
    was 1st in one hour above a term that was 21st in all twenty-four, and the
    whole point of this module is that the number means what it says.

    Recomputed on every call, never cached. A cache over a 24 h window would be
    harmless and is still not free: it is a second staleness to reason about on
    the exact statistic whose staleness was the bug.
    """
    if limit <= 0:
        return []
    try:
        keys = window_bucket_keys(_now() if now is None else now, hours)
        rc.zunionstore(AGGREGATE_KEY, keys)
        rc.expire(AGGREGATE_KEY, AGGREGATE_TTL_SECONDS)
        raw = rc.zrevrange(AGGREGATE_KEY, 0, limit - 1, withscores=True)
    except Exception:  # noqa: BLE001
        logger.warning("search_trending: window unreadable", exc_info=True)
        return []

    out: list[tuple[str, float]] = []
    for member, score in raw or []:
        q = member.decode() if isinstance(member, (bytes, bytearray)) else str(member)
        out.append((q, float(score)))
    return out
