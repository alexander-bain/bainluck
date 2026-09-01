"""Backfill true pixel dimensions for artwork enriched before we stored them.

WHY A BACKFILL AT ALL
---------------------
`enrich_markets` and `enrich_tmdb` now record the delivered raster size beside
every image_url they write, but they only ever touch markets whose image_url is
NULL. Rows enriched before that existed are never revisited, so without this
task the columns would stay empty for the entire live population and the
consumers that need real widths would never get them.

WHAT IT COSTS, AND WHY THAT IS SMALL
------------------------------------
Dimensions are a property of the URL, not of the market, so the work is per
DISTINCT url. Measured against production: 117,264 markets carry an image, but
101,018 of those are `resolved` and never render, and the 16,246 open ones share
only 6,034 distinct photos. So the real job is ~6k fetches, not ~117k — a 19x
difference that is the whole reason this is affordable.

Each fetch reads a bounded PREFIX of the raster, not the whole thing.
images.pexels.com ignores `Range` (verified: it answers 200 with the full body),
so the saving comes from closing the stream early instead of asking politely.
A 4 KB prefix was enough to parse every specimen tested, against both formats
the host content-negotiates.

SAFETY
------
Per-item try/except: one unreachable photo must never wipe the pass. A URL we
cannot parse is left NULL and simply retried on a later run — NULL already means
"we do not know" and every consumer falls back to its previous behaviour, so
failure costs nothing but a retry. The task is bounded by `limit` and idles at
zero work once the population is covered.
"""

from __future__ import annotations

import asyncio
import logging

import httpx
from sqlalchemy import text

from app.tasks.base import get_task_session
from app.utils.image_dimensions import dimensions_from_header

logger = logging.getLogger(__name__)

# The host content-negotiates on Accept and 403s a bare urllib default, so we
# ask exactly as a browser does. Measuring the format no browser receives would
# still give correct DIMENSIONS here, but asking honestly costs nothing and
# keeps this consistent with how the image is actually delivered.
_BROWSER_HEADERS = {
    "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
    ),
}

# First read attempt; enough for every specimen measured. The second bound is
# the give-up point for an unusual container that front-loads a large payload.
_PREFIX_BYTES = 4096
_MAX_BYTES = 65536


def _terminal_for(urls: int, measured: int) -> str:
    """Classify a pass for `app.utils.task_verdict`.

    Every URL sized is a finished pass; a mixed result is real-but-unfinished
    progress; sizing nothing while having work to do is a failure worth seeing,
    because an unreachable host otherwise looks exactly like a quiet no-op.
    """
    if urls == 0:
        return "no_work"
    if measured == urls:
        return "complete"
    if measured > 0:
        return "partial"
    return "failed"


async def _measure_url(client: httpx.AsyncClient, url: str) -> tuple[int, int] | None:
    """Read the leading bytes of `url` and return its true (width, height)."""
    async with client.stream("GET", url, headers=_BROWSER_HEADERS) as resp:
        if resp.status_code != 200:
            logger.debug("image dims: %s returned %d", url, resp.status_code)
            return None
        buffer = bytearray()
        async for chunk in resp.aiter_bytes():
            buffer.extend(chunk)
            if len(buffer) >= _PREFIX_BYTES:
                size = dimensions_from_header(bytes(buffer))
                if size:
                    return size
            if len(buffer) >= _MAX_BYTES:
                break
        # Stream ended (or hit the cap) — last chance on everything we read.
        return dimensions_from_header(bytes(buffer))


async def backfill_image_dimensions(limit: int = 150) -> dict:
    """Measure and store dimensions for up to `limit` distinct un-sized images.

    Open markets first and highest 24h volume first, so the photos a user is
    most likely to actually see are sized before the long tail.
    """
    stats = {"urls": 0, "measured": 0, "markets_updated": 0, "failed": 0}

    async with get_task_session() as session:
        result = await session.execute(
            text(
                """
                SELECT image_url
                FROM futures_markets
                WHERE image_url IS NOT NULL
                  AND image_width IS NULL
                  AND status IN ('open', 'active')
                GROUP BY image_url
                ORDER BY MAX(volume_24h) DESC NULLS LAST
                LIMIT :limit
                """
            ),
            {"limit": limit},
        )
        urls = [row[0] for row in result.all()]

    if not urls:
        # Drained. A run that banked nothing must not vouch for the task's
        # health, so it says so rather than returning a bare zeroed dict
        # (app/utils/task_verdict.py — "it returned" is not "it worked").
        logger.info("image dimension backfill: nothing to size")
        stats["terminal"] = _terminal_for(0, 0)
        return stats

    async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
        for url in urls:
            stats["urls"] += 1
            try:
                size = await _measure_url(client, url)
            except Exception as e:  # noqa: BLE001 — one bad photo never wipes the pass
                logger.warning("image dims: fetch failed for %s: %s", url, e)
                stats["failed"] += 1
                continue

            if not size:
                stats["failed"] += 1
                continue

            width, height = size
            try:
                # Every market sharing this exact URL gets the same raster.
                async with get_task_session() as session:
                    updated = await session.execute(
                        text(
                            """
                            UPDATE futures_markets
                            SET image_width = :w, image_height = :h
                            WHERE image_url = :url
                              AND image_width IS NULL
                            """
                        ),
                        {"w": width, "h": height, "url": url},
                    )
                    await session.commit()
                stats["markets_updated"] += updated.rowcount or 0
                stats["measured"] += 1
            except Exception as e:  # noqa: BLE001
                logger.warning("image dims: write failed for %s: %s", url, e)
                stats["failed"] += 1
                continue

            await asyncio.sleep(0.2)

    stats["terminal"] = _terminal_for(stats["urls"], stats["measured"])

    logger.info("Image dimension backfill: %s", stats)
    return stats
