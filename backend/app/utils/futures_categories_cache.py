"""Cache policy for the Search tab's category grid (`/api/futures/categories`).

Extracted under ruling 005 (extract-on-touch): this queue gives the tier its
serve decision, its fallback and its write path, so the policy lives in a module
that can be tested without a web request, and the tier converts to the cache
envelope (`docs/contracts/cache-envelope.md`) on its way through.

WHAT A PERSON WAITS FOR.

`/search` renders `CategoryBrowser`, whose first act on mount is
`fetchFuturesCategories()`. Until that answers, the category grid — the whole
content of the page — is not there. Measured on production slug `a68b2a1b`,
2026-08-29, two consecutive requests ten seconds apart:

    /api/futures/categories   wall=1585.9; db=1577.6; app=8.3; q=1
    /api/futures/categories   wall=1365.1; db=1357.2; app=7.9; q=1

`q=1`. One statement, ~99% of the request, and **the second read is as slow as
the first** — because this tier has no cache of any kind. Not a small one, not a
per-process one: none. Every visitor, every load, pays the whole thing.

WHERE THE SECOND AND A HALF GOES, and it is not a mystery.

`EXPLAIN (ANALYZE, BUFFERS)` on the emitted statement, production, same day:

    Sort  (count DESC)                                  1,696.2 ms
      GroupAggregate  llm_sport_category   rows=42
        Sort  llm_sport_category            rows=21,439  1,651.8 ms
          Bitmap Heap Scan futures_markets  rows=21,439  1,565.9 ms
            Filter: name !~~* '% vs %' AND name !~~* '% vs. %'
            Rows Removed by Filter: 27,897
            Exact Heap Blocks: 38,201
    Shared Hit Blocks: 39,014

**39,014 blocks — ~305 MB of buffer traffic — to produce 42 rows of `(key,
count)`.** The two negated `ILIKE`s cannot be served by any index, so 49,336 open
futures markets are visited on the heap; the planner then estimates 728 rows,
gets 21,439, and sorts all of them to group into 42.

WHAT THIS MODULE CHANGES, AND WHAT IT DOES NOT.

It does **not** make that statement faster. The scan is still the scan. What
changes is HOW MANY PEOPLE PAY IT: the answer is a fleet-wide census with no
per-user, per-session or per-argument variation whatsoever — literally one dict
for everybody — so it belongs in one shared slot that everybody reads.

  1. A SHARED slot in Redis. The second visitor to `/search` anywhere on the
     fleet gets what the first one built. There is deliberately no in-memory L1:
     a Redis round trip is single-digit milliseconds against a 1,400 ms build,
     and an L1 here would be a second freshness rule to keep in phase for no
     measured win (LAT-P121's L1 exists because it was already there).
  2. A 24 h mirror that is a first-class SERVE path, not an error handler. On a
     primary miss the reader gets the mirror immediately and exactly one rebuild
     runs behind it — `serve_stale_and_refresh`, which this ship moved into
     `event_concept_cache` so a second customer does not make a third copy.
  3. The five envelope fields on the stored artifact, so a served payload
     discloses when its content was computed and whether it is live or stale.

🔴 THE MIRROR IS AGE-BOUNDED, AND FOR THIS TIER THE BOUND IS THE HONEST PART.
A latency fix here can ship a formatting lie exactly as easily as LAT-P121's
could: these numbers are printed to the user as "6,614" beside `Politics` and as
"21,439 markets" at the top of the page. A day-old mirror would print a count
nobody can reproduce by tapping the tile. So the mirror is only served while it
is younger than `STALE_SERVE_CEILING` x `FRESH_TTL`; past that the reader blocks
and rebuilds, which is exactly today's behaviour. A permanently-failing refresh
degrades this tier to slow, never to wrong.

WHAT IS NOT DONE HERE, NAMED SO IT IS A DECISION.

  * `lifecycle_watermark` is published as **null**, and that is the contract's
    own answer for a watermark that cannot be computed rather than a field left
    off. The only honest watermark for this census is
    `max(updated_at)` over the population it counts — which is a second pass over
    the 39,014 blocks this ship exists to stop reading. Buying a freshness field
    with the cost the fix removes is not a trade worth making; the `created_at`
    the contract already requires answers the question a reader actually asks.
  * `/api/futures/browse`'s `COUNT(*)` is the SAME predicate over the SAME
    population and is the other half of this surface's cost (measured 2,038 ms of
    a 2,424 ms request with no category). It is derivable from this census
    exactly — `browse(category=X).total == census[X]` — and it is **not taken
    here**: `program/ux-122` is in flight and rewrites `browse_futures`' item
    loop, so touching it this cycle buys a merge conflict rather than a ship.
    Parked as P122-2 with the derivation, not forgotten.
  * No warmer. Serve-stale needs no schedule to fail (LAT-P116): the rebuild is
    triggered BY the request that would otherwise have paid for it.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from app.utils.event_concept_cache import (
    AVAILABILITY_LIVE,
    AVAILABILITY_STALE_OK,
    STALE_TTL as _SHARED_STALE_TTL,
    ConceptCacheKeys,
    cache_keys,
    get_client,
    payload_age_seconds,
    read_slot,
    stamp_envelope,
    with_availability,
    write_payload,
)

logger = logging.getLogger(__name__)

#: This tier's own Redis namespace. `cache_keys` takes a prefix precisely so a
#: further customer does not re-derive the four-key layout (its docstring names
#: #1651 as the first such case; game-markets was the second, this is the third).
CACHE_PREFIX = "bainluck:futures_categories:"

#: The census has no arguments — `/categories` takes none — so the tier owns
#: exactly one entry. It is still keyed rather than being a bare string constant
#: so the four slots (primary / stale / negative / refresh_lock) come from the
#: shared `cache_keys` and cannot drift apart.
CACHE_KEY = "all"

#: Fresh TTL. The population is "open futures markets with an unpassed resolution
#: date": it changes when ingest lands (Kalshi every 2 h, Polymarket every 1 h)
#: and when a resolution date passes. 300 s is far below either cadence, so a
#: live hit is never meaningfully behind — and this number is not a latency knob,
#: because expiring no longer costs the reader a rebuild.
FRESH_TTL = 300

#: The mirror. **Imported, not re-declared** — `write_payload` does not
#: parameterize the stale TTL ("the mirror's job is to outlive an outage, and
#: that is the same job for every tier"), so a literal here would be a constant
#: the writer never reads. This name exists so a reader of this tier can see the
#: number; it IS the shared one.
STALE_TTL = _SHARED_STALE_TTL

#: How far past `FRESH_TTL` a mirror may still be served while a rebuild runs
#: behind it. 5x — `_STALE_SERVE_CEILING` in `routes/events.py` and
#: `STALE_SERVE_CEILING` in `game_markets_cache` — deliberately the same number,
#: because two serve-stale ceilings that disagree are a coin flip about which one
#: a reader gets. 5 x 300 s = 25 minutes, against counts that move on an hourly
#: ingest: the bound binds long before the numbers become unreproducible.
STALE_SERVE_CEILING = 5


def stale_serve_ceiling_seconds() -> int:
    """How old a mirror may be and still be served, in seconds."""
    return STALE_SERVE_CEILING * FRESH_TTL


def keys() -> ConceptCacheKeys:
    """Every Redis key the census owns."""
    return cache_keys(CACHE_KEY, prefix=CACHE_PREFIX)


def stamp(
    response: dict[str, Any], *, created_at: datetime | None = None
) -> dict[str, Any]:
    """Attach the producer half of the envelope.

    Pure. `availability` stays None on purpose — it is the SERVE decision, and
    the same stored bytes are `live` from the primary and `stale_ok` from the
    mirror, so it is stamped on the way out by `with_availability`.

    `lifecycle_watermark` is None by construction; see the module docstring for
    why that is a published answer here and not an omission.
    """
    return stamp_envelope(
        response,
        created_at=created_at or datetime.now(timezone.utc),
        lifecycle_watermark=None,
    )


def mirror_is_servable(payload: Any, now: datetime | None = None) -> tuple[bool, str]:
    """Is this mirror young enough to serve? Returns `(servable, reason)`.

    The reason is returned rather than logged so a test can assert WHICH branch
    fired — "too old" and "no timestamp" are different facts about the tier and a
    bool collapses them.
    """
    if not isinstance(payload, dict):
        return False, "absent"
    age = payload_age_seconds(payload, now)
    if age is None:
        # A payload that cannot say when it was computed must not be served as
        # though it could — and here it would additionally be served under an age
        # bound we are unable to evaluate.
        return False, "no_created_at"
    if age > stale_serve_ceiling_seconds():
        return False, "too_old"
    return True, "fresh_enough"


def read(rc=None) -> tuple[dict[str, Any] | None, str]:
    """Read the census. Returns `(body, state)`.

    `state` is one of `live`, `stale_ok`, `stale_too_old`, `miss` — the serve
    decision, made here and published in the body's envelope, never re-derived by
    a consumer (contract rule 1).

    Never raises: every Redis helper below is best-effort by construction, and a
    cache that cannot be read must cost a rebuild, not a 500.
    """
    client = rc if rc is not None else get_client()
    if client is None:
        return None, "miss"
    slots = keys()

    primary = read_slot(client, slots.primary)
    if primary is not None:
        return with_availability(primary, AVAILABILITY_LIVE), "live"

    mirror = read_slot(client, slots.stale)
    if mirror is None:
        return None, "miss"
    servable, reason = mirror_is_servable(mirror)
    if not servable:
        logger.info(
            "futures-categories mirror refused (%s) — reader will rebuild", reason
        )
        return None, "stale_too_old"
    return with_availability(mirror, AVAILABILITY_STALE_OK), "stale_ok"


def write(enveloped: dict[str, Any], rc=None) -> bool:
    """Publish a stamped payload to both slots. Returns whether it was ATTEMPTED.

    `write_payload` swallows its own Redis failures and returns None, so the
    honest thing this can report is "there was a client and we handed it the
    bytes", not "Redis has them". A caller must not read the return value as
    durability — the next read is the only thing that can establish that.
    """
    client = rc if rc is not None else get_client()
    if client is None:
        return False
    write_payload(client, keys(), enveloped, primary_ttl=FRESH_TTL)
    return True
