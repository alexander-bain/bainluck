"""Cache policy for the season-market discovery query (LAT-P144, P136-1/P143-2).

Extracted out of `routes/events.py` under ruling 005 (extract-on-touch): this
queue changes when that query runs, so the policy comes out of the route into a
module that can be tested without a web request.

WHAT WAS MEASURED.

`GET /api/events/{id}/related-futures` is the event detail page's Bigger Picture
block. LAT-P136 gave the tier a shared cache and a mirror, and said in its own
docstring that **the build was not made faster** — "which of the 14-16 queries
dominates is a separate question ... it needs a production plan per event shape,
not a guess". It parked that as **P136-1**; LAT-P143 re-ranked the route as
**P143-2** at 34 requests over 5 s in 24 h, max 36,272 ms.

This is the answer to that question, and it is one query. Production
`pg_stat_statements`, 2026-08-30:

    SELECT futures_markets.id, futures_markets.market_tier FROM futures_markets ...
    8 fingerprints · 2,245 calls · mean 1,061 ms · max 30,773 ms · 2,381 s total

That is the `_tier_query` in `_build_related_futures` — the pass that answers
"which season-long markets belong to this sport". `EXPLAIN (ANALYZE, BUFFERS)`
on production, baseball, both shapes it takes:

    live/upcoming event   Bitmap Heap Scan   31,497 blocks    ~1,000 ms   ->  96 rows
    finished event        Parallel Seq Scan 126,177 blocks     3,413 ms   -> 400 rows

🔴 WHY IT CANNOT SIMPLY BE INDEXED, measured rather than assumed. The sport
predicate is a four-arm OR, and two of the arms match `external_id` by prefix
(`LIKE 'baseball%'` for Odds API rows, `ILIKE 'KXMLB%'`… for Kalshi tickers).
The database collation is `en_US.UTF-8`, so **a prefix `LIKE` cannot use a btree
index** — measured directly: `source='kalshi' AND external_id LIKE 'KXMLB%'`
takes a 126,137-block sequential scan, while the same bound written as an
explicit range uses `uq_futures_source_external` in 4 blocks. The range form is
NOT a substitute: it returned 0 rows where the `LIKE` returned 34,463, because
en_US collation is not byte order. That is exactly why Postgres refuses the
rewrite, and it is why an index here is a MIGRATION (`text_pattern_ops` or
trigram on `external_id`), not a query rewrite. Parked as **P144-1**.

🔴 AND WHY THE EXPENSIVE ARMS CANNOT JUST BE DROPPED. The tempting read is that
they are dead weight: for baseball the two `external_id` arms contribute
**zero** rows the indexed `llm_sport_category` arm does not already return, and
of 17,967 tier-1-4 open markets **17,966** carry a category. That read is wrong,
and it was checked across twelve sports before being discarded:

    americanfootball   the KX ticker arm adds 17 rows categorised 'other',
                       'economics', 'basketball', 'baseball', 'soccer'
    basketball         the KX ticker arm adds 1 row categorised 'football'
    tennis             the sport_id arm adds 46 rows categorised 'table_tennis'

So the arms are a working correction for classification gaps, and deleting them
would delete markets off the page. (The tennis 46 look like a *different* bug —
a `tennis%` sport-key prefix reaching table tennis — but that is a content
question for the MATCHING lane, not something a latency queue gets to decide.
Parked as **P144-2**.)

WHAT THIS MODULE CHANGES, AND WHY IT IS SOUND.

Not the query. **Who runs it.** Every input to that query derives from the
event's SPORT, not from the event:

    ext_id_patterns · compatible_sport_ids · llm_category · kalshi_roots
    is_womens / is_mens_specific                     <- all from `sport_key`
    rf_status_filter and the 90-day recency bound    <- from `event_is_finished`

Nothing else. So its result is shared by every event in the sport, and the
route was re-deriving it per event page: the second person to open a different
baseball game paid the same ~1,061 ms as the first. The cache key is therefore
exactly `(sport_key, event_is_finished)` — about two entries per sport, ~60 keys
for the whole site.

⚠️ THE ONE INPUT THAT IS NOT A PURE FUNCTION OF THE KEY, named rather than
glossed: the finished-event filter carries `updated_at >= NOW() - 90 days`, so
its boundary moves with the clock. A market can therefore sit up to `TTL_FOUND`
seconds past aging out of that window. The window is ninety days and the TTL is
five minutes, so the error is bounded at 0.004% of the window — but it is a real
approximation and it is the reason this is a short TTL rather than a long one.

TWO TTLs, WHICH IS A DECISION AND NOT AN OVERSIGHT.

  * `TTL_FOUND` (300 s) — a sport that HAS season markets. Tiers 1-4 are
    championship, conference, award and division markets: they are created and
    closed on the timescale of a season, so five minutes is far inside the rate
    at which the answer changes, and it is well under the mirror-age ceiling the
    event page already lives with.
  * `TTL_EMPTY` (60 s) — a sport that has NONE. This is cached, unlike the
    tier's *payload* cache which deliberately refuses to store `empty` answers,
    and the difference is the point. An empty payload is an answer shown to a
    reader ("this game has no futures"), so caching it would smuggle a content
    change into a latency change. An empty DISCOVERY is an internal index, and
    re-running a 1,061 ms scan to re-learn "still none" is the exact pathology
    this queue exists to remove — a boxing event measured 7.03 s to return 511
    bytes. It gets the SHORTER TTL so a sport recovers quickly once its markets
    are ingested: degrade to slightly-stale, never to a page that stays empty.

WHAT IS NOT DONE HERE, NAMED SO IT IS A DECISION.

  * **No in-process L1.** The sibling tier keeps one, but that dict predates its
    Redis layer and was carried across rather than chosen. Here it would buy a
    ~1 ms round trip against a ~1,061 ms query while adding a second, per-worker
    staleness horizon to reason about. Not worth the divergence.
  * **No warmer.** A miss costs what today costs, and the first reader of each
    sport pays it — which is already how the tier behaves.
  * **The series-market query at the bottom of the build shares the same
    expensive `sport_filters` OR** and is NOT covered here, because it also
    matches on both team names and so is not a function of the sport. Parked as
    **P144-3**.

ONE BUILDER PER SLOT (#2316, 2026-10-17).

The table under this query has doubled since the measurement above (1.9 GB
heap, 1.7M rows), and the FINISHED shape — whose status set admits every row —
is now a cold sequential scan. Production `pg_stat_statements` on 2026-10-17:
the two finished fingerprints averaged 19.2 s and 23.7 s (max 61.4 s), reading
83k-115k blocks from disk per call. The slow-event ring held 87 related-futures
requests since 2026-10-16 23:00Z whose single slowest statement was over 5 s,
and **27 of them started while another such statement was already running** —
several readers of one sport missing the same slot together, each paying for
its own copy of the scan and slowing the others down by competing for the same
disk.

So a miss now takes a short `single_flight` lease on the slot. The holder runs
the query and publishes as before. A reader that finds the lease held waits for
the holder's answer instead of running a second scan. It re-reads the slot
every `PEER_POLL_SECONDS` while the lease stands. If the lease disappears and
the slot is still empty, the holder ended without publishing (it failed, or
was cancelled), and the reader tries to take the lease itself. The query, the
key, the TTLs and what is stored are unchanged. The only thing that changes is
how many readers run the query at once.

Fails open, like the cache: no Redis, any lease error, or one poll slower than
`POLL_REDIS_BUDGET_SECONDS`, means the reader runs the query itself, exactly as
before. The wait is bounded by `BUILD_LEASE_TTL_SECONDS`, the longest any lease
can stand. A holder that keeps failing slowly is a degraded mode, not a hang:
each waiter takes over in turn, until its own deadline.

What this does NOT fix: the FIRST reader of each slot still pays the whole
scan. Only an index on the tier 1-4 rows removes that, and an index is a
migration (P144-1 above).
"""

from __future__ import annotations

import asyncio
import json
import logging
import time

from app.utils import single_flight as _single_flight

logger = logging.getLogger(__name__)

#: This cache's Redis namespace. The `v1` is a generation marker: if the shape
#: of what is stored ever changes, bump it rather than teaching the reader to
#: understand two shapes.
CACHE_PREFIX = "bainluck:season_markets:v1:"

#: How long a NON-EMPTY discovery stays fresh. See the module docstring.
TTL_FOUND = 300

#: How long an EMPTY discovery stays fresh. Deliberately shorter than
#: `TTL_FOUND`, so a sport whose markets have just been ingested recovers in a
#: minute rather than five.
TTL_EMPTY = 60


def cache_key(sport_key: str, event_is_finished: bool) -> str:
    """The Redis key for one `(sport, finishedness)` pair.

    `event_is_finished` is part of the key, not a filter applied afterwards,
    because it selects a genuinely different query — a wider status set plus a
    90-day recency bound — and so a genuinely different answer.
    """
    shape = "final" if event_is_finished else "live"
    return f"{CACHE_PREFIX}{sport_key}:{shape}"


def _client():
    """The bounded shared client, or None. Never raises.

    Routed through `event_concept_cache.get_client` rather than hand-rolled:
    gotcha #39 — a sync Redis client with no socket timeout can freeze the
    event loop, and `get_redis_client()` is bounded by default.
    """
    try:
        from app.utils.event_concept_cache import get_client

        return get_client()
    except Exception:
        return None


def decode(raw) -> list[int] | None:
    """Turn a stored slot back into a list of market ids, or None.

    Pure, and separated from `read` so the validation can be tested without a
    Redis. Anything that is not a JSON list of ints reads as a MISS rather than
    as an empty answer — the two are different facts (gotcha #53) and only one
    of them may suppress a rebuild.
    """
    if raw is None:
        return None
    if isinstance(raw, bytes):
        try:
            raw = raw.decode("utf-8")
        except Exception:
            return None
    if not isinstance(raw, str):
        return None
    try:
        value = json.loads(raw)
    except Exception:
        return None
    if not isinstance(value, list):
        return None
    out: list[int] = []
    for item in value:
        # `True` is an int in Python and would silently become market id 1.
        if isinstance(item, bool) or not isinstance(item, int):
            return None
        out.append(item)
    return out


def ttl_for(market_ids: list[int]) -> int:
    """The TTL this answer earns — shorter when it is empty."""
    return TTL_FOUND if market_ids else TTL_EMPTY


def read(sport_key: str, event_is_finished: bool, rc=None) -> list[int] | None:
    """The cached season-market ids for this sport, or None on any miss.

    Never raises: a cache that cannot be read must cost a rebuild, not a 500.
    """
    client = rc if rc is not None else _client()
    if client is None:
        return None
    try:
        raw = client.get(cache_key(sport_key, event_is_finished))
    except Exception:
        logger.warning(
            "season-market discovery: read failed for %s — reader will rebuild",
            sport_key,
        )
        return None
    return decode(raw)


def write(
    sport_key: str,
    event_is_finished: bool,
    market_ids: list[int],
    rc=None,
) -> bool:
    """Publish a discovery result. Returns whether the write was ATTEMPTED.

    Not whether Redis has it — the same honesty the sibling tier's `write`
    documents. Only the next read can establish durability.
    """
    client = rc if rc is not None else _client()
    if client is None:
        return False
    try:
        client.setex(
            cache_key(sport_key, event_is_finished),
            ttl_for(market_ids),
            json.dumps(list(market_ids)),
        )
    except Exception:
        logger.warning(
            "season-market discovery: write failed for %s", sport_key
        )
        return False
    return True


# ---------------------------------------------------------------------------
# One builder per slot (#2316)
# ---------------------------------------------------------------------------

#: How long one reader may hold the right to run a slot's discovery query.
#: Above the slowest discovery production has recorded (61.4 s,
#: `pg_stat_statements` 2026-10-17), so a holder that is still working is
#: never mistaken for a dead one. A holder killed mid-query (a dyno SIGKILL
#: skips its `finally`) leaves the lease to expire after this many seconds.
#: This is also the most a waiting reader can wait.
BUILD_LEASE_TTL_SECONDS = 75

#: How often a waiting reader re-reads the slot. Each poll is TWO synchronous
#: Redis round trips on the event loop (the slot GET and the lease EXISTS), so a
#: waiter costs 8 sync ops a second for as long as the holder's scan runs.
PEER_POLL_SECONDS = 0.25

#: The most one poll's round trips may take before the waiter stops waiting.
#: The poll's calls are synchronous, so a Redis that is slow WITHOUT erroring
#: (100 ms an op) would block this worker's whole event loop for most of every
#: second, for the holder's 19-24 s scan. Over this budget the waiter fails open
#: and runs the query itself, exactly as before #2316. A healthy Redis answers a
#: poll in a few milliseconds.
POLL_REDIS_BUDGET_SECONDS = 0.05


def build_task_name(sport_key: str, event_is_finished: bool) -> str:
    """The `single_flight` task name for one slot.

    One lease per cache key, never per sport: the live and finished shapes are
    different queries with different answers (see `cache_key`), so one must
    never wait for the other.
    """
    shape = "final" if event_is_finished else "live"
    return f"season_markets:{shape}:{sport_key}"


async def claim_or_await(
    sport_key: str,
    event_is_finished: bool,
    rc=None,
    *,
    sleep=asyncio.sleep,
    clock=time.monotonic,
):
    """After a MISS: take the slot's build lease, or wait for whoever holds it.

    Returns `(market_ids, lease)`:

    * `(ids, None)`  — a peer published while we waited. Use `ids` (possibly
      `[]`, a real answer — gotcha #53) and do not run the query.
    * `(None, lease)` — we hold the lease. Run the query, publish, then pass
      the lease to `release_build` in a `finally`.
    * `(None, None)` — fail open: no Redis, a lease error, or the wait bound
      ran out. Run the query exactly as before this lease existed.

    Call it ONLY on a genuine miss. A slot that was read and then rejected
    (the competition-scope re-check in the route) must not come here: the
    re-read below would hand back the rejected ids.
    """
    client = rc if rc is not None else _client()
    if client is None:
        return None, None
    task = build_task_name(sport_key, event_is_finished)
    deadline = clock() + BUILD_LEASE_TTL_SECONDS
    while True:
        lease = _single_flight.acquire(task, BUILD_LEASE_TTL_SECONDS, rc=client)
        if lease.acquired:
            if lease.token is None:
                # `redis_unavailable`: acquire failed open, there is no lease.
                return None, None
            # A peer can publish and release between our miss and our claim.
            # One GET here saves a whole scan.
            market_ids = read(sport_key, event_is_finished, rc=client)
            if market_ids is not None:
                _single_flight.release(lease, rc=client)
                return market_ids, None
            return None, lease
        # A peer is building. Wait for its answer while its lease stands.
        while True:
            poll_started = clock()
            market_ids = read(sport_key, event_is_finished, rc=client)
            if market_ids is not None:
                return market_ids, None
            if clock() >= deadline:
                logger.warning(
                    "season-market discovery: waited %ss for a peer's %s build "
                    "and got nothing — running it here",
                    BUILD_LEASE_TTL_SECONDS,
                    sport_key,
                )
                return None, None
            try:
                held = bool(client.exists(lease.key))
            except Exception:
                return None, None
            poll_seconds = clock() - poll_started
            if poll_seconds > POLL_REDIS_BUDGET_SECONDS:
                # Slow without erroring: polling on would stall every request
                # on this worker. Stop using Redis and run the query here.
                logger.warning(
                    "season-market discovery: one poll for %s took %.3fs "
                    "(budget %ss) — Redis is slow, running the build here",
                    sport_key,
                    poll_seconds,
                    POLL_REDIS_BUDGET_SECONDS,
                )
                return None, None
            if not held:
                # The holder ended without publishing. Try to take over.
                break
            await sleep(PEER_POLL_SECONDS)


def release_build(lease, rc=None) -> bool:
    """Release a lease from `claim_or_await`. Compare-and-delete; never raises.

    Through this module's client, the one the claim was taken with, rather
    than letting `single_flight` open its own.
    """
    if lease is None:
        return False
    client = rc if rc is not None else _client()
    return client is not None and _single_flight.release(lease, rc=client)
