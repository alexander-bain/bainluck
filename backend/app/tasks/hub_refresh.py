"""Background revalidation for the competition hub tier (#1651).

Dispatched by `routes/hub.py` under a single-flight lock after it has served the
24h mirror, so a burst of readers behind one TTL expiry produces one rebuild
rather than one per reader.

There is deliberately no scheduled warmer here. The hubs are cheap enough that
stale-while-revalidate keeps them warm off real traffic alone, and a beat entry
would be a second producer racing the route's for the same lock — the shape that
made #1678 finding 1.
"""

import asyncio
import logging
import time

logger = logging.getLogger(__name__)

#: Bounds the single rebuild. Comfortably above the slowest measured cold hub
#: build (golf, 2.7s in production on 2026-08-10) and well under the task's own
#: soft_time_limit, so a wedged build is reported by this timeout rather than
#: vanishing into a SIGKILL (project_celery_sigkill_untracked).
PER_HUB_TIMEOUT_SECONDS = 60


async def _refresh_hub(slug: str, token: str | None = None) -> dict:
    """Rebuild and re-cache one hub. Never raises.

    `token` is the refresh-lock owner token the ROUTE acquired: the acquire and
    the release live in different processes, so ownership travels in the message
    (#1678 finding 1). It is optional only so a message already in the broker at
    deploy time still executes — a signature that drops an argument rejects every
    in-flight message with a TypeError. Passing `None` means "I hold no lock", and
    the build still runs while that lock is left to lapse on its own TTL rather
    than being deleted by a producer that cannot prove it owns it.
    """
    from app.routes.hub import HUB_CONFIGS, build_and_cache_hub, hub_cache_keys
    from app.tasks.base import get_task_session
    from app.utils.event_concept_cache import get_client, release_refresh_lock

    rc = get_client()
    keys = hub_cache_keys(slug)
    started = time.monotonic()

    cfg = HUB_CONFIGS.get((slug or "").lower())
    if cfg is None:
        # Not an error worth retrying: the slug is config, so it cannot appear
        # later the way a concept key can. Release and report it distinctly —
        # "unknown" and "broken" are different facts (gotcha #53).
        release_refresh_lock(rc, keys, token)
        logger.warning("refresh_hub: no hub configured for %r", slug)
        return {
            "terminal": "complete",
            "completed": 0,
            "total": 1,
            "slug": slug,
            "reason": "unknown_slug",
            "seconds": 0.0,
        }

    try:
        async def _run():
            async with get_task_session() as db:
                return await build_and_cache_hub(cfg, db, rc)

        await asyncio.wait_for(_run(), timeout=PER_HUB_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        elapsed = time.monotonic() - started
        logger.warning("refresh_hub: %s timed out after %.1fs", slug, elapsed)
        return {
            "terminal": "failed",
            "completed": 0,
            "total": 1,
            "slug": slug,
            "reason": "timeout",
            "seconds": round(elapsed, 2),
        }
    except Exception as exc:
        elapsed = time.monotonic() - started
        logger.warning("refresh_hub: %s failed: %s", slug, exc, exc_info=True)
        return {
            "terminal": "failed",
            "completed": 0,
            "total": 1,
            "slug": slug,
            "reason": "error",
            "seconds": round(elapsed, 2),
        }
    finally:
        # Release the lock THIS producer holds, whatever happened, so the hub can
        # schedule another refresh without waiting out REFRESH_LOCK_TTL. It is a
        # compare-and-delete against our own token; a failed check leaves the lock
        # to expire rather than deleting someone else's.
        release_refresh_lock(rc, keys, token)

    elapsed = time.monotonic() - started
    return {
        "terminal": "complete",
        "completed": 1,
        "total": 1,
        "slug": slug,
        "reason": "built",
        "seconds": round(elapsed, 2),
    }
