"""Keep the golf-major concept payloads warm (#1107, LAT-P021).

Two entry points, one build path:

``_warm_event_concepts``
    Scheduled. Rebuilds every key in ``WARM_CONCEPT_KEYS`` so the 24h mirror
    stays content-fresh and the very first build of the day is never paid by a
    reader.

``_refresh_event_concept``
    Dispatched by the route when it serves the mirror on a miss. This is the
    "revalidate" half of serve-stale-while-revalidate, and it is what keeps the
    warmer from having to race the 60s primary TTL.

WHY THE CADENCE IS NOT SUB-TTL. LAT-P021 was staged asking for "a schedule
shorter than the TTL". Item 0 measured the TTL at **60s** and the four builds at
10.98 + 15.96 + 20.04 + ~35s = **~82s**, so a sub-60s cadence cannot complete a
>60s job — runs would overlap and the global ``task_time_limit=300`` is a hard
SIGKILL that reads as ``no_data``. The route change dissolves the conflict: with
a miss served from the mirror in ~0.44s, the primary TTL no longer governs
user-visible latency, so the warmer only has to keep the CONTENT fresh. Five
minutes does that comfortably.

The warmer is not load-bearing. A cold miss still builds inline in the route
(``build_and_cache`` at step 4), so turning this task off makes the page slow
again — never broken. ``tests/test_warm_event_concepts.py`` asserts that.
"""

import asyncio
import logging
import time

logger = logging.getLogger(__name__)

#: Bound on ONE key's build, not on the loop. The longest measured single
#: uninterrupted operation is The Open at ~35s; this is the op that has to be
#: bounded, because bounding only the loop boundary lets one pathological build
#: consume the whole budget and take the other three keys down with it.
PER_KEY_TIMEOUT_SECONDS = 55


async def _build_one(key: str, *, token: str | None) -> dict:
    """Rebuild and re-cache one concept key. Never raises.

    `token` is the refresh-lock owner token THIS producer holds, and it is
    keyword-only and mandatory so that no caller acquires one by accident. Only
    that token releases the lock; a producer holding nothing releases nothing.

    Passing `None` is legal and means "I hold no lock" — the build still runs (a
    caller that got here wants content) but the lock is left alone. That is the
    transitional case for a `refresh_event_concept` message enqueued by the
    pre-#1678 route, which is already in the broker at deploy time with no token
    in its args; its old `"1"`-valued lock simply expires on its own TTL.
    """
    from app.tasks.base import get_task_session
    from app.utils.event_concept_cache import cache_keys, get_client, release_refresh_lock

    rc = get_client()
    keys = cache_keys(key)
    started = time.monotonic()

    try:
        from app.utils.event_concept_cache import build_and_cache

        async def _run():
            async with get_task_session() as db:
                return await build_and_cache(key, db, rc)

        payload = await asyncio.wait_for(_run(), timeout=PER_KEY_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        elapsed = time.monotonic() - started
        logger.warning("warm_event_concepts: %s timed out after %.1fs", key, elapsed)
        return {"key": key, "ok": False, "reason": "timeout", "seconds": round(elapsed, 2)}
    except Exception as exc:
        elapsed = time.monotonic() - started
        logger.warning("warm_event_concepts: %s failed: %s", key, exc, exc_info=True)
        return {"key": key, "ok": False, "reason": "error", "seconds": round(elapsed, 2)}
    finally:
        # Release the lock THIS producer holds, whatever happened, so the key can
        # schedule another refresh without waiting out REFRESH_LOCK_TTL.
        #
        # It is a compare-and-delete against our own token, and that is the whole
        # fix for #1678 finding 1. This `finally` used to delete the key
        # unconditionally while `_build_one` never acquired anything — so the
        # 5-minute scheduled warmer reliably deleted the lock of an in-flight
        # route-dispatched refresh, and the next reader past the TTL acquired the
        # now-free lock and dispatched a SECOND rebuild alongside the running one.
        # A single-flight primitive that admits a third builder is not one.
        release_refresh_lock(rc, keys, token)

    elapsed = time.monotonic() - started

    if payload is None:
        # Not an error: the key genuinely resolves to nothing (an unscheduled
        # major, a slug that has not been created yet). Recorded as a distinct
        # reason rather than folded into the error count, because "absent" and
        # "broken" are different facts and gotcha #53 is about exactly that.
        logger.info("warm_event_concepts: %s resolves to nothing", key)
        return {"key": key, "ok": False, "reason": "absent", "seconds": round(elapsed, 2)}

    return {"key": key, "ok": True, "reason": "built", "seconds": round(elapsed, 2)}


async def _warm_event_concepts(keys: tuple[str, ...] | None = None) -> dict:
    """Rebuild every warm-listed concept payload. Returns a contract summary.

    The summary speaks the ``task_verdict`` vocabulary (``terminal`` +
    ``completed``/``total`` + ``errors``) so a run that warms three of four
    majors reads PARTIAL rather than GREEN. A warmer whose whole purpose is that
    all four are warm must not be able to report success while one is cold.
    """
    from app.config.event_concept_warm_keys import WARM_CONCEPT_KEYS
    from app.utils.event_concept_cache import acquire_refresh_lock, cache_keys, get_client

    targets = tuple(keys) if keys is not None else WARM_CONCEPT_KEYS

    rc = get_client()

    results = []
    for key in targets:
        # ACQUIRE FIRST, and skip the key if we cannot. This loop is the producer
        # that used to barge in: it never took the lock and then deleted whatever
        # was there on the way out (#1678 finding 1). A key already being rebuilt
        # by a route-dispatched refresh is a key that is being handled — the right
        # move is to leave it alone, not to build it a second time in parallel.
        token = acquire_refresh_lock(rc, cache_keys(key))
        if token is None:
            logger.info("warm_event_concepts: %s already being rebuilt, skipping", key)
            results.append({"key": key, "ok": False, "reason": "locked", "seconds": 0.0})
            continue
        results.append(await _build_one(key, token=token))

    built = [r for r in results if r["ok"]]
    absent = [r for r in results if r["reason"] == "absent"]
    locked = [r for r in results if r["reason"] == "locked"]
    errors = [r for r in results if r["reason"] in ("timeout", "error")]

    # `absent` and `locked` are accounted-for, not failures: the run did everything
    # it could for them — one genuinely resolves to nothing, the other is mid-build
    # in another producer. Only real damage lands in `errors`. `locked` is reported
    # as its own list rather than folded into a count, because a key that is locked
    # on run after run is a wedged lock, and that must stay visible.
    completed = len(built) + len(absent) + len(locked)

    summary = {
        "terminal": "complete" if not errors else "partial",
        "completed": completed,
        "total": len(targets),
        "built": len(built),
        "absent": [r["key"] for r in absent],
        "locked": [r["key"] for r in locked],
        "errors": [{"key": r["key"], "reason": r["reason"]} for r in errors],
        "seconds": {r["key"]: r["seconds"] for r in results},
    }
    logger.info(
        "warm_event_concepts: %d/%d accounted (%d built, %d absent, %d locked, %d errors)",
        completed,
        len(targets),
        len(built),
        len(absent),
        len(locked),
        len(errors),
    )
    return summary


async def _refresh_event_concept(key: str, token: str | None = None) -> dict:
    """Revalidate one key after the route served its mirror.

    The route acquired the refresh lock before dispatching us and hands the owner
    token across in the message, because the acquire and the release live in
    different processes here. `token` defaults to None so a message enqueued by
    the pre-#1678 route still runs after deploy — it rebuilds and lets that old
    lock lapse on its TTL rather than deleting a lock it cannot prove it owns.
    """
    result = await _build_one(key, token=token)
    return {
        "terminal": "complete" if result["ok"] or result["reason"] == "absent" else "failed",
        "completed": 1 if result["ok"] or result["reason"] == "absent" else 0,
        "total": 1,
        "key": key,
        "reason": result["reason"],
        "seconds": result["seconds"],
    }
