"""Generic Event Concept page route — slice 1 (#999).

`GET /api/event/{key}` renders any individual-competitor event (golf tournament,
and — future slices — tennis slam / UFC card / F1 GP / awards) through one
domain-parameterized aggregator. The key is `event:<domain>:<slug>`
(e.g. `event:golf:2026-masters`). Golf delegates to the existing golf aggregation
(parity bar); other domains add an adapter in `utils/event_concept.py`.

Cache policy lives in `utils/event_concept_cache.py` (ruling 005, extract-on-touch)
and this tier carries the cache envelope (`docs/contracts/cache-envelope.md`), which
names it as the contract's first customer. The route is the serve decision and
nothing else.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import get_db
from app.utils.event_concept import get_adapter, parse_event_key
from app.utils.event_concept_cache import (
    AVAILABILITY_LIVE,
    AVAILABILITY_STALE_OK,
    ConceptCacheKeys,
    acquire_refresh_lock,
    build_and_cache,
    cache_keys,
    get_client,
    has_negative,
    read_slot,
    release_refresh_lock,
    with_availability,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["event-concept"])


def _schedule_refresh(rc, keys: ConceptCacheKeys, key: str) -> None:
    """Kick exactly one background rebuild for `key` and return immediately.

    Single-flight: a burst of readers arriving behind one TTL expiry produces one
    rebuild, not one per reader (the stampede Codex C224 found on this tier). The
    lock is released if the dispatch itself fails, so a dead broker costs the next
    reader a retry rather than wedging the key for REFRESH_LOCK_TTL.

    Best-effort throughout — the caller has already decided to serve the mirror,
    and nothing here may turn a served page into an error.
    """
    token = acquire_refresh_lock(rc, keys)
    if not token:
        return
    try:
        from app.tasks import celery_app

        # The token travels WITH the dispatch: this request acquires the lock and
        # the background task releases it, so the task has to be able to prove it
        # is releasing the lock this request took (#1678 finding 1). Without it the
        # task released whatever it found, including another producer's lock.
        celery_app.send_task(
            "app.tasks.refresh_event_concept",
            args=[key, token],
            queue="background",
        )
    except Exception:
        logger.warning("event-concept: refresh dispatch failed for %s", key, exc_info=True)
        release_refresh_lock(rc, keys, token)


@router.get("/{key}")
async def get_event_concept(key: str, db: AsyncSession = Depends(get_db)):
    """Return the generic event envelope for `key` (event:<domain>:<slug>)."""
    domain, slug = parse_event_key(key)
    adapter = get_adapter(domain)
    if adapter is None:
        raise HTTPException(status_code=404, detail=f"No event adapter for domain '{domain}'")

    keys = cache_keys(key)
    rc = get_client()

    # 1. A live hit inside the primary TTL.
    primary = read_slot(rc, keys.primary)
    if primary is not None:
        return with_availability(primary, AVAILABILITY_LIVE)

    # 2. LAT-P014: a known-absent key short-circuits before the adapter runs.
    #    Read AFTER the positive slot so a value written since cannot be shadowed
    #    by a still-live negative, and BEFORE the mirror so a key that has since
    #    stopped resolving 404s instead of serving a day-old tournament.
    if has_negative(rc, keys):
        raise HTTPException(status_code=404, detail=f"Event '{key}' not found")

    # 3. LAT-P021: the miss serves the mirror. This is the fix — measured in
    #    production, a TTL expiry used to walk past a 96-second-old healthy
    #    snapshot into an 18.5s rebuild, and The Open past a 30s H12 503.
    stale = read_slot(rc, keys.stale)
    if stale is not None:
        _schedule_refresh(rc, keys, key)
        return with_availability(stale, AVAILABILITY_STALE_OK)

    # 4. Nothing usable cached — build inline. A cold miss must still SERVE, so
    #    this path stays synchronous and is never gated on the warmer.
    try:
        built = await build_and_cache(key, db, rc, adapter=adapter)
    except Exception:
        # Live build failed. Re-read the mirror rather than trusting the check
        # above: a concurrent refresh may have landed one while we were building.
        rescued = read_slot(rc, keys.stale)
        if rescued is not None:
            logger.warning("event-concept build failed for %s — serving stale", key)
            return with_availability(rescued, AVAILABILITY_STALE_OK)
        raise

    if built is None:
        raise HTTPException(status_code=404, detail=f"Event '{key}' not found")

    return with_availability(built, AVAILABILITY_LIVE)
