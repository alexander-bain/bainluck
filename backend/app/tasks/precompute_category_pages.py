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
    """Build the politics response and cache it."""
    from app.tasks.base import get_task_session
    from app.tasks.redis_state import get_redis_client
    from app.routes.politics import get_politics

    async with get_task_session() as db:
        response = await get_politics(db)

    rc = get_redis_client()
    rc.set(f"{CACHE_PREFIX}politics", json.dumps(response, default=str), ex=CACHE_TTL)
    logger.info("Cached politics category page (%d markets)", response.get("total_markets", 0))
    return response.get("total_markets", 0)


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
FEED_PREWARM_ENABLED_KEY = "discover_feed_prewarm:enabled"
FEED_PREWARM_DEADLINE_S = 25.0
FEED_PREWARM_STATUS_KEY = "bainluck:precompute:feed_prewarm:last"
FEED_PREWARM_STATUS_TTL = 6 * 3600

# The exact anonymous first-paint requests the web clients issue:
#   Discover  frontend/app/discover/page.tsx -> initialFeedRequest() + event_pct 0.15
#   Sports    frontend/app/sports/page.tsx   -> initialFeedRequest() + mode "sports"
# Both are anonymous by the L2-242 shared-anon contract (no x-session-id on the
# cold first request), which is what makes ONE warmed key serve every first-time
# visitor. `test_feed_prewarm.py` pins these against the frontend's own constants.
FEED_PREWARM_SHAPES: tuple[dict, ...] = (
    {"label": "discover", "limit": 20, "offset": 0, "event_pct": 0.15, "mode": None},
    {"label": "sports", "limit": 20, "offset": 0, "event_pct": None, "mode": "sports"},
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


async def _prewarm_feed_shape(shape: dict, rc) -> dict:
    """Rebuild and publish ONE anonymous feed shape. Never raises."""
    import asyncio
    import time as _time

    from fastapi import Response

    from app.tasks.base import get_task_session
    from app.routes.feed import get_feed
    from app.utils.feed_cache import (
        FEED_PREWARM_KEY_SCOPE_KEY,
        FEED_PREWARM_SCOPE_KEY,
        FEED_RESPONSE_STALE_TTL_SECONDS,
        feed_response_cache_ttl,
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
                    include_events=True,
                    include_futures=True,
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
                timeout=FEED_PREWARM_DEADLINE_S,
            )
    except asyncio.TimeoutError:
        logger.error(
            "Feed pre-warm TIMEOUT for %s after %.0fs — the request path will "
            "rebuild cold (LAT-P001)",
            label,
            FEED_PREWARM_DEADLINE_S,
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

    ttl = feed_response_cache_ttl(my_teams_only=False, identified=False)
    body = json.dumps(payload, default=str)
    rc.setex(cache_key, ttl, body)
    rc.setex(f"{cache_key}:stale", FEED_RESPONSE_STALE_TTL_SECONDS, body)
    logger.info(
        "Pre-warmed %s feed in %.1fs (%d items, ttl=%ds, stale=%ds)",
        label,
        duration_s,
        len(items),
        ttl,
        FEED_RESPONSE_STALE_TTL_SECONDS,
    )
    return {"outcome": "ok", "duration_s": duration_s, "items": len(items)}


async def _prewarm_discover_feed_responses():
    """Keep the anonymous Discover + Sports first-paint responses warm.

    Bounded (per-shape deadline), kill-switchable, and it never replaces a good
    cached payload with a degraded or empty one. Each shape is independent: one
    shape failing must not stop the other from being warmed.
    """
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

    shapes: dict[str, dict] = {}
    for shape in FEED_PREWARM_SHAPES:
        shapes[shape["label"]] = await _prewarm_feed_shape(shape, rc)

    report = {
        "ran_at": datetime.now(timezone.utc).isoformat(),
        "shapes": shapes,
        "deadline_s": FEED_PREWARM_DEADLINE_S,
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
