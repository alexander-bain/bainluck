"""Precompute category page responses and cache in Redis.

The politics, entertainment, economics, and weather endpoints query
FuturesMarket with eagerly-loaded outcomes, run classification/grouping,
and build cross-source comparisons. On production data volumes this
exceeds Heroku's 30-second request timeout.

This task runs every hour to pre-warm Redis caches.  The route handlers
read from cache first and only fall back to a live query when the cache
is missing.
"""

import json
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Redis key prefix and TTL (2 hours — task runs every 1h, so there's overlap)
CACHE_PREFIX = "bainluck:category:"
CACHE_TTL = 7200
STALE_CACHE_TTL = 86400  # 24 hours — served when primary cache is cold


async def _precompute_politics():
    """Build the politics response and cache it.

    Writes the ``:stale`` mirror alongside the primary key, as entertainment and
    economics already did. Politics was the one page in the family missing it, so
    a lapsed 2h primary key had nothing behind it and every visitor paid the full
    rebuild — 10.4s here on 2026-08-09 against a 294ms cache hit (#1607).

    Also records per-stage wall times into the run report, so the dominant stage
    of that rebuild is attributable from the admin rail instead of guessed. This
    build is the same code the request path falls back to, so timing it here times
    the user's worst case.
    """
    from app.tasks.base import get_task_session
    from app.tasks.redis_state import get_redis_client
    from app.routes.politics import get_politics

    stage_ms: dict = {}
    async with get_task_session() as db:
        response = await get_politics(db, stage_ms=stage_ms)

    rc = get_redis_client()
    payload = json.dumps(response, default=str)
    rc.set(f"{CACHE_PREFIX}politics", payload, ex=CACHE_TTL)
    rc.set(f"{CACHE_PREFIX}politics:stale", payload, ex=STALE_CACHE_TTL)
    total = response.get("total_markets", 0)
    logger.info(
        "Cached politics category page (%d markets) stages=%s", total, stage_ms
    )
    return {"total_markets": total, "stage_ms": stage_ms}


async def _precompute_entertainment():
    """Build the entertainment response and cache it."""
    from app.tasks.base import get_task_session
    from app.tasks.redis_state import get_redis_client
    from app.routes.entertainment import get_entertainment

    async with get_task_session() as db:
        response = await get_entertainment(db)

    rc = get_redis_client()
    payload = json.dumps(response, default=str)
    rc.set(f"{CACHE_PREFIX}entertainment", payload, ex=CACHE_TTL)
    rc.set(f"{CACHE_PREFIX}entertainment:stale", payload, ex=STALE_CACHE_TTL)
    logger.info("Cached entertainment category page (%d markets)", response.get("total_markets", 0))
    return response.get("total_markets", 0)


async def _precompute_economics():
    """Build the economics response and cache it."""
    from app.tasks.base import get_task_session
    from app.tasks.redis_state import get_redis_client
    from app.routes.economics import get_economics

    async with get_task_session() as db:
        response = await get_economics(db)

    rc = get_redis_client()
    payload = json.dumps(response, default=str)
    rc.set(f"{CACHE_PREFIX}economics", payload, ex=CACHE_TTL)
    rc.set(f"{CACHE_PREFIX}economics:stale", payload, ex=STALE_CACHE_TTL)
    logger.info("Cached economics category page (%d markets)", response.get("total_markets", 0))
    return response.get("total_markets", 0)


async def _precompute_weather():
    """Build all weather sub-endpoint responses and cache them."""
    from app.tasks.base import get_task_session
    from app.tasks.redis_state import get_redis_client
    from app.routes.weather import (
        get_featured,
        get_cities,
        get_rain,
        get_events,
        get_climate,
        get_wildcards,
        get_cross_source,
    )

    async with get_task_session() as db:
        featured = await get_featured(db)
        cities = await get_cities(db)
        rain = await get_rain(db)
        events = await get_events(db)
        climate = await get_climate(db)
        wildcards = await get_wildcards(db)
        cross_source = await get_cross_source(db)

    rc = get_redis_client()
    for key, data in [
        ("weather:featured", featured),
        ("weather:cities", cities),
        ("weather:rain", rain),
        ("weather:events", events),
        ("weather:climate", climate),
        ("weather:wildcards", wildcards),
        ("weather:cross-source", cross_source),
    ]:
        rc.set(f"{CACHE_PREFIX}{key}", json.dumps(data, default=str), ex=CACHE_TTL)

    logger.info("Cached all 7 weather sub-endpoints")
    return 7


async def _precompute_golf():
    """Build the golf response and cache the category page + the feed base.

    In addition to the category-page cache, this publishes the user-independent
    golf listing *base* (Queue 278) so ``GET /api/feed`` reads it from Redis on
    process-cold rather than paying the ~8.9s inline ``get_golf`` rebuild
    (#1475/#1459). Keeping this on the worker means the web dyno never runs the
    heavy rebuild after a restart — Redis already holds a servable base.
    """
    from datetime import datetime, timezone
    from app.tasks.base import get_task_session
    from app.tasks.redis_state import get_redis_client
    from app.routes.golf import get_golf
    from app.utils.golf_base import build_envelope, publish_envelope_sync

    async with get_task_session() as db:
        response = await get_golf(db)

    rc = get_redis_client()
    rc.set(f"{CACHE_PREFIX}golf", json.dumps(response, default=str), ex=CACHE_TTL)

    # Publish the freshness-tagged feed base (fresh + last-good keys).
    envelope = build_envelope(
        datetime.now(timezone.utc), response.get("tournaments", [])
    )
    publish_envelope_sync(rc, envelope)
    logger.info(
        "Cached golf category page + published feed base (%d tournaments)",
        len(envelope["tournaments"]),
    )
    return "ok"


async def _precompute_discover_candidate_base():
    """Every-2-minute Discover warm pass: candidate-ID base, then cold responses.

    Two independent units of work share this beat (LAT-P001 adds the second
    rather than a new beat entry, which the queue forbids):

    1. ``_publish_discover_candidate_base`` — the Queue 285 candidate-ID base.
    2. ``_prewarm_discover_feed_responses`` — the anonymous Discover + Sports
       first-paint response cache.

    They are deliberately decoupled: the base build has three early-return paths
    (kill switch, deadline, empty build), and if the pre-warm hung off the success
    path a base hiccup would silently stop warming the feed — reintroducing the
    exact 5–11s cold miss this was added to remove, with no signal. Each unit is
    independently guarded and reported.
    """
    base_result = None
    try:
        base_result = await _publish_discover_candidate_base()
    except Exception:
        logger.exception("Discover candidate base publish failed")
        base_result = "error"

    try:
        prewarm_result = await _prewarm_discover_feed_responses()
    except Exception:
        logger.exception("Discover feed response pre-warm failed")
        prewarm_result = "error"

    return {"candidate_base": base_result, "feed_prewarm": prewarm_result}


async def _publish_discover_candidate_base():
    """Precompute + publish the anonymous-default Discover candidate-ID base (Queue 285).

    Runs the exact ordered candidate-pool queries the feed uses
    (``feed._compute_ordered_candidate_ids`` — the same source both the request
    path and this task call) for the anonymous default key (``sport=None``,
    ``static_tag_filter=None``) and publishes the user-independent ordered ID list
    as a versioned, freshness-tagged envelope. ``GET /api/feed`` then reads this
    on a cold response-cache key instead of re-running the ~3–6s nine-query
    discovery, so page one and page two of the same anonymous scroll (and native's
    50/200 shapes) reuse one base.

    Contracts honoured:

    * **Kill switch** — when the Redis ``discover_candidate_base:enabled`` key is
      ``"0"`` the build is skipped entirely (the feed also ignores the base and
      runs direct queries).
    * **Failed/partial builds never replace last-good** — the envelope is
      published ONLY when the build produced a non-empty, valid ID list within the
      deadline. An empty/invalid/timed-out build leaves the prior last-good key
      untouched.
    * **Measured** — build wall time and per-pool DB row counts are logged.
    * **Bounded** — the build is deadline-guarded so it can never run long.

    Only the anonymous default key is beat-warmed; arbitrary sport/static-tag feed
    requests populate their own correctly-keyed base on first request (or fall
    back to direct queries), per ``candidate_base.get_candidate_base``.
    """
    import asyncio
    import os
    import time
    from datetime import datetime, timezone

    from app.tasks.base import get_task_session
    from app.tasks.redis_state import get_redis_client
    from app.routes.feed import _compute_ordered_candidate_ids
    from app.utils.candidate_base import (
        CANDIDATE_BASE_ENABLED_KEY,
        base_identity,
        build_envelope,
        payload_valid,
        publish_candidate_base_sync,
    )

    rc = get_redis_client()

    # Kill switch — skip the build (and DB load) entirely when disabled.
    try:
        raw_enabled = rc.get(CANDIDATE_BASE_ENABLED_KEY)
        if raw_enabled is not None:
            value = (
                raw_enabled.decode()
                if isinstance(raw_enabled, (bytes, bytearray))
                else raw_enabled
            )
            if str(value).strip() == "0":
                logger.info("Discover candidate base precompute skipped — kill switch off")
                return "disabled"
    except Exception:
        logger.debug("candidate base kill-switch read failed", exc_info=True)

    try:
        deadline_s = float(os.getenv("CANDIDATE_BASE_BUILD_DEADLINE_S", "20"))
    except (TypeError, ValueError):
        deadline_s = 20.0

    now = datetime.now(timezone.utc)
    t0 = time.perf_counter()
    try:
        async with get_task_session() as db:
            market_ids, pool_counts, curator_ids = await asyncio.wait_for(
                _compute_ordered_candidate_ids(db, now, None, None),
                timeout=deadline_s,
            )
    except asyncio.TimeoutError:
        logger.warning(
            "Discover candidate base build exceeded %.0fs deadline — keeping last-good",
            deadline_s,
        )
        return "timeout"
    build_ms = round((time.perf_counter() - t0) * 1000, 1)

    identity = base_identity(None, None)
    envelope = build_envelope(
        now,
        identity,
        market_ids,
        pool_counts=pool_counts,
        external_curator_recall_ids=curator_ids,
    )

    # Failed/partial builds never replace last-good: only publish a fully-built,
    # non-empty, valid envelope.
    if not market_ids or not payload_valid(envelope, expected_identity=identity):
        logger.warning(
            "Discover candidate base build empty/invalid (%d ids, %.1fms) — keeping last-good",
            len(market_ids),
            build_ms,
        )
        return "empty"

    publish_candidate_base_sync(rc, envelope)
    logger.info(
        "Published Discover candidate base (%d ids, pools=%s, build=%.1fms)",
        len(market_ids),
        pool_counts,
        build_ms,
    )
    return len(market_ids)


GRID_WARM_TIMEOUT_S = 120
GRID_WARM_LEAGUES = ["mlb", "nba", "nhl", "golf"]

# Where the run report lands for the read-only admin rail. One key, overwritten
# per run, TTL well past the hourly beat so a missed beat reads as STALE rather
# than vanishing (Redis is allkeys-lru — a cold key is evicted regardless of
# TTL, and an absent report is itself the signal that the beat is not running).
PRECOMPUTE_STATUS_KEY = "bainluck:precompute:category_pages:last"
PRECOMPUTE_STATUS_TTL = 6 * 3600


# --- Discover/Sports cold-response pre-warm (LAT-P001) -----------------------
#
# Measured on production 2026-08-05 (see PROGRAM-LATENCY-REPORT.md): `/api/feed`
# is bimodal — a cache hit/stale_hit serves in 13–16ms, a genuine miss cost a
# p50 of 10,981ms. Nothing warmed the response cache except a user request that
# had already paid for the cold build, and at the observed ~8 feed requests/hour
# both the 60s fresh TTL and the 300s :stale mirror routinely lapsed between
# visitors. So the *first* visitor after a quiet period paid 5–11s.
#
# This warms the two cold first-paint shapes web actually issues. It is hosted
# inside the existing every-2-minute candidate-base beat rather than a new beat
# entry (the queue forbids a beat-schedule edit) — and 2min is comfortably inside
# the 300s stale window, so the mirror never decays and the worst case a visitor
# can see becomes a stale_hit, not a cold build.
#
# 🔴 **#2236 AMENDMENT — the sentence above is true of exactly the payloads it
# was written about, and false of the ones that matter most.** "2 min is
# comfortably inside the 300s stale window" stopped covering live-containing
# payloads the day #2216 gave them a 60s stale ceiling: their mirror is gone at
# 60s, a full minute before this beat's next tick can republish it. Measured on
# production v3911 as a clean repeating sawtooth — miss → hit → stale_hit →
# stale_hit → miss, every 60s, on `limit=50&mode=sports` and `limit=20&
# mode=sports` alike.
#
# The correction is NOT to loosen the ceiling and it is NOT to speed this pass
# up: this pass costs p50 9.8s / p95 14.2s (`measure_beat_cost.py`, 233 runs/24h,
# 2026-08-27) and running all of it three times as often to cover the shapes
# that happen to be live is paying for six warm targets to keep one warm. Live
# republication is its own, much narrower pass — `_prewarm_live_feed_shapes`
# below — firing at `FEED_LIVE_REPUBLISH_PERIOD_S` over ONLY the shapes this
# pass observed to be live, and skipping to near-zero cost when none are.
#
# The general clause, because this is the second time a period and a TTL have
# been set in different files: **a warm rail's period is part of the cache's
# freshness contract, not an implementation detail of the beat.** Whoever
# shortens a TTL is changing the period requirement of every warmer that feeds
# it, and will not know it. That is why `FEED_LIVE_REPUBLISH_PERIOD_S` is
# declared in `feed_cache.py` beside the ceiling instead of here beside the beat.
FEED_PREWARM_ENABLED_KEY = "discover_feed_prewarm:enabled"
# LAT-P099: 25.0 -> 20.0, because the worst case is a SUM and the fourth shape
# put it exactly on the task's soft limit — `test_prewarm_is_bounded` computes
# `20 (base) + DEADLINE * len(SHAPES)` and 20 + 25*4 = 120 == soft_time_limit.
#
# Lowering it costs nothing real, and the reason is not headroom arithmetic but
# what the deadline is FOR. It bounds the beat; it is not a licence for a slow
# build. The native client gives up at 6 s (`DiscoverViewModel.retryBudget`), so
# any shape still building at 20 s is warming a payload no user would have
# waited for — the request that shape serves has already failed. Against
# measurement it is not close: the WHOLE beat (base + every shape) runs at
# p50 9.8 s / p95 14.2 s on production (`measure_beat_cost.py`, 2026-08-27,
# 233 runs/24 h), and the shape this cycle adds measured 872 ms.
#
# The general form, because the next shape will hit this again: a per-item
# deadline multiplied by an item count is a budget that silently tightens every
# time someone adds an item, and it fails at the moment of the addition rather
# than at the moment of the mistake.
#
# LAT-P100 builds that general form. The pass now has ONE wall budget instead of
# a per-item deadline, so adding a target costs coverage inside a fixed bound
# rather than pushing the bound up until it hits `soft_time_limit`.
#
# 80.0 s is not a new number: it is EXACTLY the worst case the per-item form
# already permitted (`FEED_PREWARM_DEADLINE_S 20.0` x 4 shapes). The pass gains
# three targets at no increase in its own bound, which is the whole point of the
# change — the previous shape had to buy its room by cutting everyone's deadline.
FEED_PREWARM_PASS_BUDGET_S = 80.0


def _prewarm_target_deadline(
    remaining_budget_s: float, remaining_targets: int
) -> float:
    """Fair share of what is LEFT, over what is LEFT to do.

    🔴 **Gotcha #34, as an invariant rather than a caution.** A shared budget
    consumed in loop order starves whatever is last: give the pass 80 s and let
    each target take what it wants, and one slow first shape spends the lot while
    the shapes behind it get nothing — and the failure is invisible, because a
    starved warmer reports the same "the beat ran" as a healthy one.

    Dividing the REMAINING budget by the REMAINING targets fixes it with an
    arithmetic guarantee, not with care:

        deadline_i >= PASS_BUDGET / N   for EVERY i, in EVERY order.

    Proof (the test executes it; this is why it is true). Let B_i be the budget
    left before target i of N. B_0 = B. Target i is given B_i / (N - i) and
    cannot use more, so

        B_{i+1} >= B_i - B_i/(N-i) = B_i * (N-i-1)/(N-i).

    With B_i >= B * (N-i)/N by induction, B_{i+1} >= B * (N-i-1)/N — which is the
    hypothesis at i+1. Therefore every target's share B_i/(N-i) >= B/N.

    The upside is free and is the reason to divide the remainder rather than hand
    out fixed slices: a target that finishes early returns its unspent time to
    everyone behind it, so the common case (every shape warm in ~1 s) leaves the
    LAST target with almost the whole budget, while the pathological case still
    cannot push any target below its floor.
    """
    if remaining_targets <= 0:
        return 0.0
    return max(0.0, remaining_budget_s) / remaining_targets
FEED_PREWARM_STATUS_KEY = "bainluck:precompute:feed_prewarm:last"
FEED_PREWARM_STATUS_TTL = 6 * 3600

# --- #2236: the live republish pass ------------------------------------------
#: Its own kill switch, separate from `FEED_PREWARM_ENABLED_KEY` on purpose. The
#: two passes have different costs and different blast radii: turning the main
#: warm off makes every first paint cold, turning this one off restores exactly
#: the pre-#2236 behaviour (a 60s sawtooth) and nothing worse. An operator who
#: needs to shed the 40s beat must not have to take the 120s one down with it.
#: This pass ALSO honours the main switch — "the warm rail is off" must mean the
#: whole rail, or the switch is a lie.
FEED_LIVE_PREWARM_ENABLED_KEY = "discover_feed_live_prewarm:enabled"
FEED_LIVE_PREWARM_STATUS_KEY = "bainluck:precompute:feed_live_prewarm:last"

#: Redis hash: shape label -> "1" for every shape whose last warm produced a
#: payload containing a live card. Written by `_prewarm_feed_shape`, i.e. by the
#: SAME function for both passes, so the live set can never describe a warmer
#: other than the one that ran.
#:
#: A hash and not a per-key marker because the reader needs the whole set in one
#: round trip, and because a per-key marker would have to re-derive the response
#: cache key outside the route — the LAT-P001 two-writers-one-key trap, re-entered
#: for no gain. A label is what this pass actually selects on.
FEED_PREWARM_LIVE_SHAPES_KEY = "bainluck:precompute:feed_prewarm:live_shapes"

#: TTL on that hash, refreshed on every main pass. Deliberately > the 120s host
#: beat period and only just: if the main warm rail dies, this pass must stop
#: believing a stale liveness picture within a couple of its own periods rather
#: than republishing shapes that stopped being live an hour ago. It is a
#: dead-man's switch, not a cache.
FEED_PREWARM_LIVE_SHAPES_TTL_S = 300


def _record_shape_liveness(rc, label: str, live: bool) -> None:
    """Record (or clear) one shape's liveness in the shared live set. Never raises.

    Clearing matters as much as setting. A shape that goes not-live must LEAVE
    the set, or the 40s pass keeps rebuilding a payload whose own TTL is 60/300
    and which the 120s pass already covers — paying three times over for nothing.
    The set is therefore always written, in both directions, on every warm.
    """
    try:
        if live:
            rc.hset(FEED_PREWARM_LIVE_SHAPES_KEY, label, "1")
            rc.expire(FEED_PREWARM_LIVE_SHAPES_KEY, FEED_PREWARM_LIVE_SHAPES_TTL_S)
        else:
            rc.hdel(FEED_PREWARM_LIVE_SHAPES_KEY, label)
    except Exception:
        logger.debug("live-shape marker write failed for %s", label, exc_info=True)


def _live_prewarm_labels(rc) -> set[str]:
    """Labels the last warm observed to be live. Empty on any failure.

    Empty means "republish nothing", which is the correct direction: the cost of
    being wrong here is one 60s sawtooth (the pre-#2236 status quo), where the
    cost of failing the other way is a 40s beat rebuilding every feed shape on
    the site off a Redis error.
    """
    try:
        raw = rc.hgetall(FEED_PREWARM_LIVE_SHAPES_KEY) or {}
    except Exception:
        logger.debug("live-shape marker read failed", exc_info=True)
        return set()
    labels = set()
    for key in raw:
        labels.add(key.decode() if isinstance(key, (bytes, bytearray)) else str(key))
    return labels

# The exact anonymous first-paint requests the clients issue:
#   Discover  frontend/app/discover/page.tsx -> initialFeedRequest() + event_pct 0.15
#   Sports    frontend/app/sports/page.tsx   -> initialFeedRequest() + mode "sports"
#   Native    DiscoverViewModel.firstPageLimit = 50, eventPct 0.15
#   Native    FeedViewModel.fetchSportsFeed -> fetchFeed(mode: "sports") at
#             APIClient.fetchFeed's DEFAULT limit of 50 (LAT-P099)
# The two web shapes are anonymous by the L2-242 shared-anon contract (no
# x-session-id on the cold first request), which is what makes ONE warmed key
# serve every first-time visitor. `test_feed_prewarm.py` pins each shape against
# its own client's constant.
#
# LAT-P089: the NATIVE shape is a different limit, so it is a different key, and
# nothing warmed it — measured cold on production 2026-08-25 at 6.5s
# server-side, alone over the client's whole 6s budget. Q407 rejected enrolling
# it, correctly, as a fix ON ITS OWN: the native client always sends
# x-session-id, so it is never the `anon` principal this warmer can reach. It is
# the other half of one fix. The inert-principal share in `routes/feed.py`
# routes such a request to the anonymous key; this entry is what makes that key
# warm when it gets there. Neither half is worth much without the other.
# LAT-P099: the SPORTS half of LAT-P089's fix was never applied, and the tab
# paid for it every single open. Measured on production 2026-08-27 (v3908,
# `06fdad74`), one fresh `x-session-id` per sample, the client's exact
# first-paint shape:
#
#     Discover native  limit=50 event_pct=0.15   57 ms   shared_hit  3/3
#     Sports   native  limit=50 mode=sports     872 ms   MISS        3/3
#     Sports   web     limit=20 mode=sports      18 ms   hit         3/3
#
# Same client, same release, same second — and the only difference between the
# 57 ms row and the 872 ms row is that one of them has a line in this tuple.
# Native asks `mode=sports` at APIClient.fetchFeed's DEFAULT limit of 50
# (`FeedViewModel.swift:499` -> `APIClient.swift:606`); the warmed sports shape
# is the WEB's limit of 20. A different limit is a different cache key, so the
# inert-principal share (`routes/feed.py:2224`) looked up an anonymous entry
# that nothing had ever published and fell through to a full cold build —
# 3 of 3 samples, `X-Feed-Cache: miss`, on the request that gates the tab's
# first paint.
#
# This is LAT-P089's own lesson arriving a second time, which is the part worth
# recording: that cycle explained at length that the native shape is a
# different key and enrolled `discover_native` — for the tab it was looking at.
# The sibling tab, one line below, was reasoned about in the same comment
# ("the anonymous Discover + Sports first-paint response cache") and left
# warming the wrong key. A fix scoped to the surface that surfaced the bug is
# how a class survives its own repair.
# LAT-P100: every shape now declares `include_events` and `include_futures`
# EXPLICITLY, because `_prewarm_feed_shape` used to hardcode both to True and
# both are part of the cache key (`feed_cache.feed_response_cache_key`). That
# hardcoding did not merely omit a shape — it made an entire class of shape
# UNWARMABLE, silently, and the Sports tab's events backfill was in that class
# from the day the warmer was written. A default here would rebuild the same
# trap one indirection deeper, so `test_feed_prewarm.py` asserts the declaration
# rather than trusting a default.
FEED_PREWARM_SHAPES: tuple[dict, ...] = (
    {
        "label": "discover",
        "limit": 20,
        "offset": 0,
        "event_pct": 0.15,
        "mode": None,
        "include_events": True,
        "include_futures": True,
    },
    {
        "label": "sports",
        "limit": 20,
        "offset": 0,
        "event_pct": None,
        "mode": "sports",
        "include_events": True,
        "include_futures": True,
    },
    {
        "label": "discover_native",
        "limit": 50,
        "offset": 0,
        "event_pct": 0.15,
        "mode": None,
        "include_events": True,
        "include_futures": True,
    },
    {
        "label": "sports_native",
        "limit": 50,
        "offset": 0,
        "event_pct": None,
        "mode": "sports",
        "include_events": True,
        "include_futures": True,
    },
    # LAT-P100: the native Sports tab's events-only backfill — the second of its
    # three requests, and the one that fills Live Now / Upcoming after the board
    # paints. `FeedViewModel.supplementalEventLimit = 200` via
    # `APIClient.fetchSportsEventBackfill` -> `fetchFeed(limit:, includeFutures:
    # false)`, which sends NO mode and NO event_pct. The Discover-default guard
    # at `routes/feed.py:1822` requires `include_futures` to be true, so it skips
    # this request and both stay None — and `{mode or 'discover'}` in the key
    # builder is what makes the warmer's None land on the route's None.
    #
    # Measured cold on production 2026-08-27 (slug 7833da68, fresh session per
    # sample): 151.5 ms p50, `X-Feed-Cache: miss` 8 of 8, max 721 ms.
    {
        "label": "sports_native_events",
        "limit": 200,
        "offset": 0,
        "event_pct": None,
        "mode": None,
        "include_events": True,
        "include_futures": False,
    },
)

#: The two real shapes of `GET /api/futures/grouped-feed` — the Sports tab's
#: THIRD request, on both surfaces. Enrolled by LAT-P100 together with that
#: route's first response cache; before it, the route had none at all and both
#: shapes were rebuilt from scratch on every open by every person.
#:
#: The native tab does NOT send `sports_only`; the web page does
#: (`app/sports/page.tsx:109`). That is a different key and therefore a different
#: entry — the same "one row below the line being edited" shape difference that
#: cost the Sports tab 872 ms for two days in LAT-P099, written down here rather
#: than rediscovered.
GROUPED_FEED_PREWARM_SHAPES: tuple[dict, ...] = (
    {
        "label": "grouped_native",
        "category": None,
        "sport": None,
        "sports_only": False,
        "limit": 20,
    },
    {
        "label": "grouped_web",
        "category": None,
        "sport": None,
        "sports_only": True,
        "limit": 20,
    },
)

#: The WEB first-paint shapes, i.e. the ones whose `limit` must track
#: `FEED_PAGE_LIMIT`. Named so the guard test asserts over a declared set rather
#: than over "all shapes", which silently stopped being the same thing the
#: moment the native shape was enrolled.
FEED_PREWARM_WEB_LABELS: frozenset[str] = frozenset({"discover", "sports"})

#: The NATIVE first-paint shapes, whose `limit` must track the iOS client's
#: constant instead. Declared as its own set for the reason the web set is:
#: LAT-P099 shipped because "the native shape is enrolled" was true of one tab
#: and false of the other, and a test that asserts over a NAMED set fails when a
#: member goes missing, where a test asserting over "all shapes" cannot.
FEED_PREWARM_NATIVE_LABELS: frozenset[str] = frozenset(
    {"discover_native", "sports_native"}
)


def _build_prewarm_request(scope_key: str):
    """A synthetic anonymous ASGI request carrying the internal pre-warm marker."""
    from starlette.requests import Request

    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/feed",
            "headers": [],
            "query_string": b"",
            scope_key: True,
        }
    )


async def _prewarm_feed_shape(
    shape: dict, rc, *, deadline_s: float = FEED_PREWARM_PASS_BUDGET_S
) -> dict:
    """Rebuild and publish ONE anonymous feed shape. Never raises.

    ``deadline_s`` is this target's slice of the pass budget, allocated by
    ``_prewarm_target_deadline``. The default is the WHOLE budget on purpose: it
    exists so a direct call in a test is not a ``TypeError``, and making it the
    full pass budget rather than a plausible per-shape number means nobody can
    mistake it for a second, quieter definition of a per-shape allowance.
    """
    import asyncio
    import time as _time

    from fastapi import Response

    from app.tasks.base import get_task_session
    from app.routes.feed import get_feed
    from app.utils.feed_cache import (
        FEED_PREWARM_KEY_SCOPE_KEY,
        FEED_PREWARM_SCOPE_KEY,
        feed_response_cache_ttls,
        payload_contains_live_event,
    )

    label = shape["label"]
    started = _time.monotonic()
    request = _build_prewarm_request(FEED_PREWARM_SCOPE_KEY)
    try:
        async with get_task_session() as db:
            payload = await asyncio.wait_for(
                get_feed(
                    response=Response(),
                    request=request,
                    limit=shape["limit"],
                    offset=shape["offset"],
                    sport=None,
                    include_events=shape["include_events"],
                    include_futures=shape["include_futures"],
                    my_teams_only=False,
                    mode=shape["mode"],
                    tags=None,
                    event_pct=shape["event_pct"],
                    debug=False,
                    debug_ground_truth=False,
                    debug_personalization=False,
                    exclude_reviewed=False,
                    reviewer=None,
                    reviewed_surface=None,
                    secret=None,
                    db=db,
                    user=None,
                ),
                timeout=deadline_s,
            )
    except asyncio.TimeoutError:
        logger.error(
            "Feed pre-warm TIMEOUT for %s after %.1fs — the request path will "
            "rebuild cold (LAT-P001)",
            label,
            deadline_s,
        )
        return {"outcome": "timeout", "duration_s": round(_time.monotonic() - started, 1)}
    except Exception as exc:
        logger.exception("Feed pre-warm failed for %s", label)
        return {
            "outcome": "error",
            "duration_s": round(_time.monotonic() - started, 1),
            "error": str(exc)[:200],
        }

    duration_s = round(_time.monotonic() - started, 1)

    # A DEGRADED build must never become shared truth — same contract the request
    # path enforces (Queue 283 / C80). Leave the prior last-good in place.
    if not isinstance(payload, dict) or payload.get("build_quality", "complete") != "complete":
        logger.warning(
            "Feed pre-warm produced a degraded build for %s (%s) — keeping last-good",
            label,
            (payload or {}).get("degraded_reason") if isinstance(payload, dict) else "no_payload",
        )
        return {
            "outcome": "degraded",
            "duration_s": duration_s,
            "degraded_reason": (payload or {}).get("degraded_reason")
            if isinstance(payload, dict)
            else None,
        }

    items = payload.get("items") or []
    if not items:
        logger.warning(
            "Feed pre-warm produced an EMPTY feed for %s — keeping last-good", label
        )
        return {"outcome": "empty", "duration_s": duration_s}

    # Publish under the key the route itself resolved (scope readback), so the
    # warmed key cannot drift from the key the request path reads.
    cache_key = request.scope.get(FEED_PREWARM_KEY_SCOPE_KEY)
    if not cache_key:
        logger.error(
            "Feed pre-warm got no resolved cache key for %s — the route did not take "
            "the cacheable path; nothing published (LAT-P001)",
            label,
        )
        return {"outcome": "no_key", "duration_s": duration_s}

    # #2216: the warmer is the SECOND writer on these keys and it must apply the
    # live ceiling identically to the route. This matters more here than on the
    # request path, not less: the warmer REPUBLISHES on a beat, so a warmer left
    # on the 60s/300s principal TTLs would keep the anonymous Discover key alive
    # at up to 360s forever, and a live score inside it with it. Same failure
    # shape LAT-P001 closed on the key builder — two writers, one of them quietly
    # disagreeing — which is why both now go through one function.
    live = payload_contains_live_event(payload)
    ttl, stale_ttl = feed_response_cache_ttls(
        my_teams_only=False, identified=False, live=live
    )
    body = json.dumps(payload, default=str)
    rc.setex(cache_key, ttl, body)
    rc.setex(f"{cache_key}:stale", stale_ttl, body)
    # #2236: the shape's liveness is recorded by the writer that just measured
    # it. Whichever pass called this — the 120s one or the 40s one — the live set
    # now describes the payload actually on the key, so the republish pass can
    # never be selecting on a belief no warmer holds.
    _record_shape_liveness(rc, label, live)
    logger.info(
        "Pre-warmed %s feed in %.1fs (%d items, ttl=%ds, stale=%ds, live=%s)",
        label,
        duration_s,
        len(items),
        ttl,
        stale_ttl,
        live,
    )
    return {
        "outcome": "ok",
        "duration_s": duration_s,
        "items": len(items),
        "live": live,
    }


async def _prewarm_grouped_feed_shape(
    shape: dict, rc, *, deadline_s: float = FEED_PREWARM_PASS_BUDGET_S
) -> dict:
    """Rebuild and publish ONE ``/api/futures/grouped-feed`` shape. Never raises.

    Unlike the feed warmer this one does NOT publish anything itself — it calls
    the route with the pre-warm scope marker set, and the ROUTE writes its own
    cache on the way out. That is deliberate and it is the stronger arrangement:
    with exactly one writer, the warmed key cannot drift from the read key, which
    is the defect class LAT-P001 closed for the feed and LAT-P099 then hit anyway
    from the other direction. The marker only suppresses the READ, so the warmer
    always rebuilds instead of re-publishing an ageing payload forever.
    """
    import asyncio
    import time as _time

    from fastapi import Response

    from app.tasks.base import get_task_session
    from app.routes.futures import grouped_feed
    from app.utils.grouped_feed_cache import GROUPED_FEED_PREWARM_SCOPE_KEY

    label = shape["label"]
    started = _time.monotonic()
    request = _build_prewarm_request(GROUPED_FEED_PREWARM_SCOPE_KEY)
    try:
        async with get_task_session() as db:
            payload = await asyncio.wait_for(
                grouped_feed(
                    request=request,
                    response=Response(),
                    category=shape["category"],
                    sport=shape["sport"],
                    sports_only=shape["sports_only"],
                    limit=shape["limit"],
                    db=db,
                ),
                timeout=deadline_s,
            )
    except asyncio.TimeoutError:
        logger.error(
            "Grouped-feed pre-warm TIMEOUT for %s after %.1fs — the request path "
            "will rebuild cold (LAT-P100)",
            label,
            deadline_s,
        )
        return {
            "outcome": "timeout",
            "duration_s": round(_time.monotonic() - started, 1),
        }
    except Exception as exc:
        logger.exception("Grouped-feed pre-warm failed for %s", label)
        return {
            "outcome": "error",
            "duration_s": round(_time.monotonic() - started, 1),
            "error": str(exc)[:200],
        }

    duration_s = round(_time.monotonic() - started, 1)
    items = (payload or {}).get("feed") or [] if isinstance(payload, dict) else []
    if not items:
        # The route refuses to publish an empty feed for the same reason: an empty
        # read must not become shared truth for three minutes.
        logger.warning(
            "Grouped-feed pre-warm produced an EMPTY feed for %s — keeping "
            "last-good",
            label,
        )
        return {"outcome": "empty", "duration_s": duration_s}

    logger.info(
        "Pre-warmed grouped-feed %s in %.1fs (%d items)", label, duration_s, len(items)
    )
    return {"outcome": "ok", "duration_s": duration_s, "items": len(items)}


def _prewarm_targets() -> list[tuple[str, object]]:
    """Every warm target in the pass, as ``(label, callable)`` pairs.

    One list so ONE budget covers all of them. Feed shapes and grouped-feed
    shapes warm different routes and publish through different writers, but they
    compete for the same two minutes, and a budget that only knows about some of
    the work it is bounding is not a budget.
    """
    import functools

    targets: list[tuple[str, object]] = [
        (s["label"], functools.partial(_prewarm_feed_shape, dict(s)))
        for s in FEED_PREWARM_SHAPES
    ]
    targets += [
        (s["label"], functools.partial(_prewarm_grouped_feed_shape, dict(s)))
        for s in GROUPED_FEED_PREWARM_SHAPES
    ]
    return targets


async def _prewarm_discover_feed_responses():
    """Keep the anonymous Discover + Sports first-paint responses warm.

    Bounded by ONE pass wall budget (LAT-P100), kill-switchable, and it never
    replaces a good cached payload with a degraded or empty one. Each target is
    independent: one failing must not stop the others from being warmed, and a
    slow one must not be able to eat the budget of the ones behind it — see
    `_prewarm_target_deadline`.
    """
    import time as _time
    from datetime import datetime, timezone

    from app.tasks.redis_state import get_redis_client

    rc = get_redis_client()

    try:
        raw_enabled = rc.get(FEED_PREWARM_ENABLED_KEY)
        if raw_enabled is not None:
            value = (
                raw_enabled.decode()
                if isinstance(raw_enabled, (bytes, bytearray))
                else raw_enabled
            )
            if str(value).strip() == "0":
                logger.info("Discover feed pre-warm skipped — kill switch off")
                return "disabled"
    except Exception:
        logger.debug("feed pre-warm kill-switch read failed", exc_info=True)

    targets = _prewarm_targets()
    budget_left = FEED_PREWARM_PASS_BUDGET_S
    shapes: dict[str, dict] = {}
    for index, (label, warm) in enumerate(targets):
        deadline_s = _prewarm_target_deadline(budget_left, len(targets) - index)
        started = _time.monotonic()
        shapes[label] = await warm(rc, deadline_s=deadline_s)
        budget_left = max(0.0, budget_left - (_time.monotonic() - started))

    report = {
        "ran_at": datetime.now(timezone.utc).isoformat(),
        "shapes": shapes,
        "pass_budget_s": FEED_PREWARM_PASS_BUDGET_S,
        "budget_left_s": round(budget_left, 1),
    }
    try:
        rc.setex(
            FEED_PREWARM_STATUS_KEY,
            FEED_PREWARM_STATUS_TTL,
            json.dumps(report, default=str),
        )
    except Exception:
        logger.debug("feed pre-warm status write failed", exc_info=True)

    return sum(1 for s in shapes.values() if s.get("outcome") == "ok")


async def _prewarm_live_feed_shapes():
    """Republish the live-containing feed shapes inside their own 60s ceiling (#2236).

    The narrow half of the warm rail. Where `_prewarm_discover_feed_responses`
    warms every first-paint shape every 120s, this fires every
    `FEED_LIVE_REPUBLISH_PERIOD_S` over ONLY the shapes the last warm observed to
    be live — because those are the only ones whose cache entry dies at 60s and
    therefore the only ones the 120s pass structurally cannot keep warm.

    Three properties, each of which is the reason a line of this is shaped the
    way it is:

    * **It usually does nothing.** Off-hours the live set is empty and the pass
      is one `HGETALL` — this is what makes a 40s beat affordable next to a
      120s pass that costs p50 9.8s. The cost scales with the number of shapes
      that are actually live, which is the only thing it should scale with.
    * **It builds through the same function as the main pass.**
      `_prewarm_feed_shape` resolves the key by scope readback, applies the live
      ceiling, refuses degraded and empty payloads, and records liveness. A
      second, faster republisher that reimplemented any of that would be the
      LAT-P001 two-writers defect with a new period attached.
    * **A shape that stops being live leaves on its own.** The warm it just ran
      rewrites the live set, so the set converges within one pass in both
      directions and no separate expiry logic exists to get wrong.

    COST, stated rather than left to be discovered — `worker-background` runs
    `--concurrency=2` against ~57 beats and this makes 58:
      * Idle (the overnight case): one `HGETALL` + one `SETEX`, ~2,160 passes/day,
        well under a minute of slot time across the whole day.
      * Live, taking 8h/day with two live shapes as the working figure: ~720
        passes x 2 builds x ~1.2s ~= 29 min/day, about 1% of the two-slot pool.
      * Worst case for a SINGLE pass — 20s budget, 35s hard limit — is strictly
        smaller than the pass it sits beside, which may hold a slot for 80s of
        budget under a 120s soft limit.

    NOT DONE, and named so it is a decision rather than an oversight: this does
    not skip a shape whose current publication would survive to the next pass.
    With zero headroom in the #2236 invariant (40 + 20 == 60) such a skip can
    never fire, so it would be a Redis `TTL` read per shape buying nothing. If
    the period is ever shortened, the skip becomes real and worth adding — and
    the duplicate it would remove is the one this pass performs when its tick
    happens to coincide with the 120s pass's.

    Never raises; the caller wraps it too.
    """
    import time as _time
    from datetime import datetime, timezone

    from app.tasks.redis_state import get_redis_client
    from app.utils.feed_cache import (
        FEED_LIVE_REPUBLISH_BUDGET_S,
        FEED_LIVE_REPUBLISH_PERIOD_S,
    )

    rc = get_redis_client()

    for switch, name in (
        (FEED_PREWARM_ENABLED_KEY, "the warm rail"),
        (FEED_LIVE_PREWARM_ENABLED_KEY, "the live republish"),
    ):
        try:
            raw_enabled = rc.get(switch)
        except Exception:
            logger.debug("live pre-warm kill-switch read failed", exc_info=True)
            continue
        if raw_enabled is None:
            continue
        value = (
            raw_enabled.decode()
            if isinstance(raw_enabled, (bytes, bytearray))
            else raw_enabled
        )
        if str(value).strip() == "0":
            logger.info("Live feed republish skipped — %s kill switch is off", name)
            return "disabled"

    live_labels = _live_prewarm_labels(rc)
    targets = [
        (s["label"], s) for s in FEED_PREWARM_SHAPES if s["label"] in live_labels
    ]

    budget_left = float(FEED_LIVE_REPUBLISH_BUDGET_S)
    shapes: dict[str, dict] = {}
    for index, (label, shape) in enumerate(targets):
        deadline_s = _prewarm_target_deadline(budget_left, len(targets) - index)
        started = _time.monotonic()
        shapes[label] = await _prewarm_feed_shape(
            dict(shape), rc, deadline_s=deadline_s
        )
        budget_left = max(0.0, budget_left - (_time.monotonic() - started))

    # The idle pass reports too, and that is deliberate (gotcha #53). "Nothing was
    # live" and "this beat has not run since the deploy" are different facts with
    # opposite remedies, and an absent status key states both. One `setex` per
    # 40 s is not a cost worth buying that ambiguity with.
    report = {
        "ran_at": datetime.now(timezone.utc).isoformat(),
        "period_s": FEED_LIVE_REPUBLISH_PERIOD_S,
        "live_labels": sorted(live_labels),
        "shapes": shapes,
        "pass_budget_s": FEED_LIVE_REPUBLISH_BUDGET_S,
        "budget_left_s": round(budget_left, 1),
    }
    try:
        rc.setex(
            FEED_LIVE_PREWARM_STATUS_KEY,
            FEED_PREWARM_STATUS_TTL,
            json.dumps(report, default=str),
        )
    except Exception:
        logger.debug("live feed pre-warm status write failed", exc_info=True)

    if not targets:
        # The common case, and it must stay cheap enough to be uninteresting:
        # one HGETALL, one SETEX, no build.
        return "no_live_shapes"
    return sum(1 for s in shapes.values() if s.get("outcome") == "ok")


async def _precompute_grids(report: dict | None = None):
    """Pre-warm championship grid caches for MLB, NBA, NHL, Golf.

    #901: golf was missing from this warm list, so `/playoffs/golf` read an
    unwarmed `bainluck:category:playoffs:golf` key on every load → cold rebuild
    via ~15 sequential DataGolf calls (~12s) and frequent skeleton stalls. Golf
    is warmed here so the request path hits Redis like the other leagues.

    #1484 observability: every league's warm is now recorded with an explicit
    outcome (``ok`` / ``timeout`` / ``error`` / ``not_attempted``), its duration,
    and the team count it produced. Before this, a league whose warm timed out
    was swallowed into ``logger.exception`` and the return value listed only the
    SUCCESSES — so "MLB timed out at 120s" and "MLB was never reached because
    the task ran out of budget" were indistinguishable from the outside. That
    ambiguity is precisely why the MLB grid could sit cold for days. Nothing here
    tunes a time limit; it makes the limits' effects visible first.
    """
    from app.tasks.base import get_task_session
    from app.routes.playoffs import get_playoff_grid
    from app.tasks.redis_state import get_redis_client
    import asyncio
    import time as _time

    rc = get_redis_client()
    warmed = []
    leagues: dict[str, dict] = {
        slug: {"outcome": "not_attempted"} for slug in GRID_WARM_LEAGUES
    }
    if report is not None:
        report["grid_leagues"] = leagues
        report["grid_warm_timeout_s"] = GRID_WARM_TIMEOUT_S

    for slug in GRID_WARM_LEAGUES:
        started = _time.monotonic()
        leagues[slug] = {"outcome": "started"}
        try:
            async with get_task_session() as session:
                result = await asyncio.wait_for(
                    get_playoff_grid(slug, hours=None, top=10, debug=False, db=session),
                    timeout=GRID_WARM_TIMEOUT_S,
                )
                payload = json.dumps(result, default=str)
                cache_key = f"bainluck:category:playoffs:{slug}"
                rc.setex(cache_key, 3600, payload)
                rc.setex(f"{cache_key}:stale", 86400, payload)
                warmed.append(slug)
                leagues[slug] = {
                    "outcome": "ok",
                    "duration_s": round(_time.monotonic() - started, 1),
                    "teams": len(result.get("teams") or []),
                    "columns": len(result.get("columns") or []),
                }
                logger.info(
                    "Warmed %s grid in %.1fs (%d teams)",
                    slug, leagues[slug]["duration_s"], leagues[slug]["teams"],
                )
        except asyncio.TimeoutError:
            leagues[slug] = {
                "outcome": "timeout",
                "duration_s": round(_time.monotonic() - started, 1),
                "timeout_s": GRID_WARM_TIMEOUT_S,
            }
            logger.error(
                "Grid warm TIMEOUT for %s after %ss — the request path will "
                "rebuild cold and may degrade (#1484)",
                slug, GRID_WARM_TIMEOUT_S,
            )
        except Exception as exc:
            leagues[slug] = {
                "outcome": "error",
                "duration_s": round(_time.monotonic() - started, 1),
                "error": str(exc)[:200],
            }
            logger.exception("Failed to precompute %s grid", slug)
    return warmed


def _write_precompute_report(report: dict) -> None:
    """Persist the run report for the read-only admin rail. Never raises."""
    try:
        from app.tasks.redis_state import get_redis_client

        get_redis_client().setex(
            PRECOMPUTE_STATUS_KEY,
            PRECOMPUTE_STATUS_TTL,
            json.dumps(report, default=str),
        )
    except Exception as exc:
        logger.warning("Category precompute report write failed: %s", exc)


async def _precompute_all_category_pages():
    """Precompute all category page caches.

    #1484: the run is now self-reporting. Each section records dispatch →
    start → success/failure with a duration, and the whole report is written to
    Redis even when a section blows up, so ``/api/admin/category-precompute/last``
    can answer "did the MLB grid warm actually run, and how long did it take?"
    without reading worker logs.
    """
    import time as _time

    sections = [
        ("politics", _precompute_politics),
        ("entertainment", _precompute_entertainment),
        ("economics", _precompute_economics),
        ("weather", _precompute_weather),
        ("golf", _precompute_golf),
        ("grids", _precompute_grids),
    ]
    run_started = _time.monotonic()
    report: dict = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        # Ordered dispatch plan — a section still listed as "not_attempted" when
        # the report lands means the task died or ran out of budget before
        # reaching it (grids run LAST, so they starve first).
        "sections": {name: {"outcome": "not_attempted"} for name, _ in sections},
        "section_order": [name for name, _ in sections],
    }
    results = {}
    try:
        for name, fn in sections:
            started = _time.monotonic()
            report["sections"][name] = {"outcome": "started"}
            try:
                results[name] = (
                    await fn(report) if name == "grids" else await fn()
                )
                report["sections"][name] = {
                    "outcome": "ok",
                    "duration_s": round(_time.monotonic() - started, 1),
                    "result": results[name],
                }
            except Exception as exc:
                logger.exception("Failed to precompute %s category page", name)
                results[name] = "error"
                report["sections"][name] = {
                    "outcome": "error",
                    "duration_s": round(_time.monotonic() - started, 1),
                    "error": str(exc)[:200],
                }
    finally:
        # Written in `finally` so a soft-time-limit kill (SoftTimeLimitExceeded
        # is a BaseException-derived signal Celery raises in-thread) still
        # leaves evidence of exactly how far the run got.
        report["duration_s"] = round(_time.monotonic() - run_started, 1)
        report["finished_at"] = datetime.now(timezone.utc).isoformat()
        _write_precompute_report(report)

    logger.info("Category page precompute complete: %s", results)
    return {"status": "ok", "results": results}
