"""Background revalidation for the league tier (#1767).

Dispatched by `routes/league_futures.py` under a single-flight lock after it has
served the 24h mirror, so a burst of readers behind one TTL expiry produces one
rebuild rather than one per reader.

This is the league analogue of `hub_refresh`, and it exists because the league
route had the mirror WITHOUT the revalidation. The build path was reached only
when both cache slots missed, so a league rebuilt once per 24 hours and served a
stale copy for the other 23h55m — about 99.6% of loads. Measured in production an
hour after the UX-P062 deploy: every sampled league still returned a pre-deploy
payload, while an uncached key cold-built the complete current envelope.

There is deliberately no scheduled warmer here, for the same reason there is none
for hubs: stale-while-revalidate keeps the leagues warm off real traffic alone,
and a beat entry would be a second producer racing the route's for the same lock
— the shape that made #1678 finding 1.
"""

import asyncio
import logging
import time

logger = logging.getLogger(__name__)

#: Bounds the single rebuild. The build's own inner timeouts are 25s for the
#: markets query plus 10s for each games rail, so a fully pathological build can
#: legitimately run ~45s; 60s sits above that and well under the task's
#: `soft_time_limit`, so a wedged build is reported by this timeout rather than
#: vanishing into a SIGKILL (project_celery_sigkill_untracked).
PER_LEAGUE_TIMEOUT_SECONDS = 60


async def _refresh_league(sport_key: str, token: str | None = None) -> dict:
    """Rebuild and re-cache one league. Never raises.

    `token` is the refresh-lock owner token the ROUTE acquired: the acquire and the
    release live in different processes, so ownership travels in the message
    (#1678 finding 1). It is optional only so a message already in the broker at
    deploy time still executes — a signature that drops an argument rejects every
    in-flight message with a TypeError. Passing `None` means "I hold no lock", and
    the build still runs while that lock is left to lapse on its own TTL rather
    than being deleted by a producer that cannot prove it owns it.
    """
    from app.routes.league_futures import build_and_cache_league, league_cache_keys
    from app.tasks.base import get_task_session
    from app.utils.event_concept_cache import get_client, release_refresh_lock

    rc = get_client()
    keys = league_cache_keys(sport_key)
    started = time.monotonic()

    try:

        async def _run():
            async with get_task_session() as db:
                return await build_and_cache_league(sport_key, db, rc)

        await asyncio.wait_for(_run(), timeout=PER_LEAGUE_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        elapsed = time.monotonic() - started
        logger.warning("refresh_league: %s timed out after %.1fs", sport_key, elapsed)
        return {
            "terminal": "failed",
            "completed": 0,
            "total": 1,
            "sport_key": sport_key,
            "reason": "timeout",
            "seconds": round(elapsed, 2),
        }
    except Exception as exc:
        elapsed = time.monotonic() - started
        logger.warning("refresh_league: %s failed: %s", sport_key, exc, exc_info=True)
        return {
            "terminal": "failed",
            "completed": 0,
            "total": 1,
            "sport_key": sport_key,
            "reason": "error",
            "seconds": round(elapsed, 2),
        }
    finally:
        # Release the lock THIS producer holds, whatever happened, so the league can
        # schedule another refresh without waiting out REFRESH_LOCK_TTL. It is a
        # compare-and-delete against our own token; a failed check leaves the lock
        # to expire rather than deleting someone else's.
        release_refresh_lock(rc, keys, token)

    elapsed = time.monotonic() - started
    return {
        "terminal": "complete",
        "completed": 1,
        "total": 1,
        "sport_key": sport_key,
        "reason": "built",
        "seconds": round(elapsed, 2),
    }
