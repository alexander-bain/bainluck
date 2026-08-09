"""Generic Event Concept page route — slice 1 (#999).

`GET /api/event/{key}` renders any individual-competitor event (golf tournament,
and — future slices — tennis slam / UFC card / F1 GP / awards) through one
domain-parameterized aggregator. The key is `event:<domain>:<slug>`
(e.g. `event:golf:2026-masters`). Golf delegates to the existing golf aggregation
(parity bar); other domains add an adapter in `utils/event_concept.py`.
"""

import json as _json
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import get_db
from app.utils.event_concept import (
    parse_event_key,
    get_adapter,
    strip_competitor_wire_leaks,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["event-concept"])

# Whole-envelope cache TTL (#1107). The golf event-detail path recomputes the
# full UNCACHED get_golf aggregation on every request (a selectinload over every
# open golf market, a cold-dyno-synchronous DataGolf schedule HTTP call, and a
# 2×N winner-market probe loop) — measured ~4-16s cold and it never warms. A
# short primary TTL keeps live-play probabilities fresh (underlying live polling
# runs every ~2 min) while serving warm reads well under the 2s reliability bar.
_ENVELOPE_TTL = 60
_STALE_TTL = 86400

# LAT-P014/#1107: a MISS used to cost what a hit costs, every single time.
#
# Only successful envelopes were cached, so a key that resolves to nothing re-ran
# the adapter's full build on every request. Measured in production 2026-08-09
# against a cycling control on the same route: a bad golf key 404'd in
# 6,931-14,518ms and a bad tennis key in 7,923ms, where a bad CYCLING key — whose
# adapter proves absence from an in-memory config — 404'd in 290ms.
#
# Deliberately SHORT. The consequence of caching a negative is that a key which
# becomes valid inside the window keeps 404ing for up to that long, so the window
# is kept to the same 60s the envelope itself uses: a tournament that appears
# mid-window is at most 60s late, which is well inside the polling cadence that
# would have created it. Domain-agnostic on purpose — it protects tennis and the
# unknown-domain path too, not just the golf case that exposed it.
_NEGATIVE_TTL = 60
_NEGATIVE_SENTINEL = "404"


@router.get("/{key}")
async def get_event_concept(key: str, db: AsyncSession = Depends(get_db)):
    """Return the generic event envelope for `key` (event:<domain>:<slug>)."""
    domain, slug = parse_event_key(key)
    adapter = get_adapter(domain)
    if adapter is None:
        raise HTTPException(status_code=404, detail=f"No event adapter for domain '{domain}'")

    # Whole-envelope Redis cache (#1107), mirroring the hub pattern
    # (routes/hub.py): short primary TTL + 24h stale fallback. This can never do
    # worse than the pre-cache path — a miss (or a dead Redis) falls straight
    # through to the live build; the stale key only rescues a build that errors.
    _cache_key = f"bainluck:event_concept:{key}"
    _stale_key = f"{_cache_key}:stale"
    _negative_key = f"{_cache_key}:404"
    _rc = None
    try:
        from app.tasks.redis_state import get_redis_client

        _rc = get_redis_client()
        cached = _rc.get(_cache_key)
        if cached:
            return _json.loads(cached.decode() if isinstance(cached, bytes) else cached)
        # LAT-P014: a known-absent key short-circuits before the adapter runs. Read
        # AFTER the positive key so a value written since cannot be shadowed by a
        # still-live negative.
        if _rc.get(_negative_key):
            raise HTTPException(status_code=404, detail=f"Event '{key}' not found")
    except HTTPException:
        raise
    except Exception:
        _rc = None

    try:
        envelope = await adapter.build_event(slug, db)
    except Exception:
        # Live build failed — serve the last good snapshot rather than 500-ing on
        # the year's biggest golf day. If there is no stale snapshot, re-raise
        # (identical to the pre-cache behavior).
        if _rc is not None:
            try:
                stale = _rc.get(_stale_key)
                if stale:
                    logger.warning("event-concept build failed for %s — serving stale", key)
                    return _json.loads(stale.decode() if isinstance(stale, bytes) else stale)
            except Exception:
                pass
        raise

    if envelope is None:
        # LAT-P014: record the absence, so the next request for this key does not
        # re-run the build. Best-effort — a dead Redis must never turn a 404 into
        # a 500, which is why this mirrors the write below rather than sharing it.
        try:
            if _rc is not None:
                _rc.setex(_negative_key, _NEGATIVE_TTL, _NEGATIVE_SENTINEL)
        except Exception:
            pass
        raise HTTPException(status_code=404, detail=f"Event '{key}' not found")

    # L2-48/L2-118: probability-only product — strip odds from the wire.
    result = strip_competitor_wire_leaks(envelope)

    try:
        if _rc is not None:
            payload = _json.dumps(result, default=str)
            _rc.setex(_cache_key, _ENVELOPE_TTL, payload)
            _rc.setex(_stale_key, _STALE_TTL, payload)
            # LAT-P014: a key that now resolves must not keep a negative entry
            # behind it. The positive key is read first so it already wins, but
            # dropping it removes the question entirely rather than leaving it to
            # a TTL-ordering argument.
            _rc.delete(_negative_key)
    except Exception:
        pass

    return result
