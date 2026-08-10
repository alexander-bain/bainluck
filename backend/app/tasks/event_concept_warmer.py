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


async def _build_one(key: str) -> dict:
    """Rebuild and re-cache one concept key. Never raises."""
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
        # The route holds this lock while it waits for us. Release it whatever
        # happened, or the key cannot schedule another refresh until the lock's
        # own TTL expires.
        release_refresh_lock(rc, keys)

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

    targets = tuple(keys) if keys is not None else WARM_CONCEPT_KEYS

    results = []
    for key in targets:
        results.append(await _build_one(key))

    built = [r for r in results if r["ok"]]
    absent = [r for r in results if r["reason"] == "absent"]
    errors = [r for r in results if r["reason"] in ("timeout", "error")]

    # `absent` keys are counted as accounted-for, not as failures: the run did
    # everything it could for them. Only real damage lands in `errors`.
    completed = len(built) + len(absent)

    summary = {
        "terminal": "complete" if not errors else "partial",
        "completed": completed,
        "total": len(targets),
        "built": len(built),
        "absent": [r["key"] for r in absent],
        "errors": [{"key": r["key"], "reason": r["reason"]} for r in errors],
        "seconds": {r["key"]: r["seconds"] for r in results},
    }
    logger.info(
        "warm_event_concepts: %d/%d accounted (%d built, %d absent, %d errors)",
        completed,
        len(targets),
        len(built),
        len(absent),
        len(errors),
    )
    return summary


async def _refresh_event_concept(key: str) -> dict:
    """Revalidate one key after the route served its mirror."""
    result = await _build_one(key)
    return {
        "terminal": "complete" if result["ok"] or result["reason"] == "absent" else "failed",
        "completed": 1 if result["ok"] or result["reason"] == "absent" else 0,
        "total": 1,
        "key": key,
        "reason": result["reason"],
        "seconds": result["seconds"],
    }
