"""LAT-P021 (#1107): keep the completed majors' event envelopes warm.

The four golf majors 503'd at Heroku's 30.3s H12 boundary. LAT-P014 made the
build far cheaper and LAT-P020 cheaper again, but two of the four still never
completed — and a request that never completes never writes the cache, so there
was **no exit from the loop via user traffic**. Every visitor paid the full cold
build and every visitor timed out.

A warmer breaks that loop from the other side: a worker with no 30s router bound
pays the cold cost once, off the request path, and every visitor thereafter reads
a warm key.

Two things make this actually pay off, and the task is worthless without both:

1. **The settled TTL** (`routes/event.py::_envelope_ttl`). The primary key used to
   live 60 seconds. No sane beat cadence keeps a 60s key warm, so a warmer alone
   would have been a task that ran, reported success, and left the endpoint cold
   for 59 of every 60 seconds — the "it returned, therefore it worked" failure
   this repo has an entire module about (`app/utils/task_verdict.py`).
2. **Warming through the same code path the request uses**, so a warm write is
   provably the thing a reader will read. A warmer with its own bespoke build
   would drift from the endpoint silently.

Deliberately NOT a general crawler. It warms a short, named list of keys that are
settled, expensive and documented as never-dead (#1063). Warming everything would
reintroduce the cost this is removing, just on the worker.
"""

import logging

from app.services.database import async_session_maker
from app.utils.event_concept import get_adapter, parse_event_key

logger = logging.getLogger(__name__)

#: The four majors. #1063 documents these exact slugs as "guaranteed never-dead",
#: which is precisely why serving them a 503 was the outage it was. They are
#: listed rather than discovered because the point is a BOUNDED warm set: a query
#: for "all settled golf tournaments" would grow without limit and put the cost
#: back, just on a worker instead of a dyno.
MAJOR_EVENT_KEYS = [
    "event:golf:the-masters",
    "event:golf:pga-championship",
    "event:golf:us-open",
    "event:golf:the-open-championship",
]


async def _warm_one(key: str) -> tuple[str, str]:
    """Build one envelope through the request path and cache it. Never raises."""
    from app.routes.event import (
        _ENVELOPE_TTL,
        _STALE_TTL,
        _envelope_ttl,
        strip_competitor_wire_leaks,
    )
    import json as _json

    try:
        domain, slug = parse_event_key(key)
        adapter = get_adapter(domain)
        if adapter is None:
            return key, "no_adapter"

        async with async_session_maker() as db:
            envelope = await adapter.build_event(slug, db)

        if envelope is None:
            # Do NOT write a negative here. A warmer failing to find a key is a
            # fact about the warmer's list, and caching a 404 from a background
            # task would let a stale list take a live page down — the blast
            # radius of a background write is every visitor, not one request.
            return key, "absent"

        result = strip_competitor_wire_leaks(envelope)
        ttl = _envelope_ttl(envelope)

        from app.tasks.redis_state import get_redis_client

        rc = get_redis_client()
        payload = _json.dumps(result, default=str)
        rc.setex(f"bainluck:event_concept:{key}", ttl, payload)
        rc.setex(f"bainluck:event_concept:{key}:stale", _STALE_TTL, payload)
        rc.delete(f"bainluck:event_concept:{key}:404")

        # A settled key that came back with the SHORT ttl means the envelope did
        # not report `settled`, so this warm will have evaporated before the next
        # beat. Loud, because the silent version is a green task and a cold page.
        if ttl == _ENVELOPE_TTL:
            logger.warning(
                "warm_event_concepts: %s warmed with the SHORT %ss ttl — its "
                "envelope did not report status=settled, so this warm expires "
                "long before the next beat and the endpoint stays cold",
                key,
                _ENVELOPE_TTL,
            )
            return key, "warm_short_ttl"
        return key, "warm"
    except Exception as exc:  # noqa: BLE001 - one bad key must not kill the pass
        logger.warning("warm_event_concepts: %s failed: %s", key, exc)
        return key, "error"


async def _run_warm_major_event_concepts() -> dict:
    """Warm every major key. Returns an HONEST summary for `_tracked_run`."""
    results: dict[str, str] = {}
    for key in MAJOR_EVENT_KEYS:
        k, state = await _warm_one(key)
        results[k] = state

    warmed = sum(1 for v in results.values() if v == "warm")
    total = len(MAJOR_EVENT_KEYS)

    # Gotcha #53 / `app/utils/task_verdict.py`: "it returned" is not "it worked".
    # A pass that warmed NOTHING must not read like a pass with nothing to do —
    # this task exists because a zero-yield loop looked like success for weeks.
    if warmed == 0:
        logger.error(
            "warm_event_concepts: warmed ZERO of %d keys — the majors are still "
            "cold and #1107 is NOT mitigated. states=%s",
            total,
            results,
        )
        terminal = "failed"
    elif warmed < total:
        logger.warning(
            "warm_event_concepts: warmed %d/%d. states=%s", warmed, total, results
        )
        terminal = "partial"
    else:
        logger.info("warm_event_concepts: warmed %d/%d", warmed, total)
        terminal = "ok"

    return {
        "warmed": warmed,
        "total": total,
        "terminal": terminal,
        "states": results,
    }
