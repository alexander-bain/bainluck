"""Background task: write the Oscars category previews the page reads.

This is the ONLY place an OpenAI call is made for the Oscars previews — the request
path only reads the Redis key this task writes (the house rule: never run LLM calls
inside a GET). See `app/utils/oscars_previews.py` for the contract and #3322 for the
measurement that moved them here (10.83s cold on production, six synchronous calls
`asyncio.gather`ed so they could not interleave).

Flow (every `PREVIEWS_REFRESH_SECONDS`):
  1. Build the page's payload with the SAME function the route calls, so a preview
     can never describe a nominee list the page does not show.
  2. Skip — making no OpenAI call — when there is nothing to preview.
  3. Generate each major category's blurb, plus the movers summary, each bounded in
     a worker thread so a hung provider can neither block the loop nor walk the task
     into its soft limit.
  4. Publish all of them as one envelope with a TTL of twice the interval, so a
     stopped beat clears the previews instead of freezing a stale percentage.

Best-effort throughout: a failure records a task verdict but never leaves the page
broken — absent previews simply render as no previews.
"""

import asyncio
import logging

from app.utils.oscars_previews import (
    PREVIEWS_REDIS_KEY,
    PREVIEWS_TTL_SECONDS,
    build_previews_envelope,
)

logger = logging.getLogger(__name__)

# Inner-operation timeouts. The Celery soft limit is 120s (hard 150s), and the two
# unbounded operations are the payload build and the OpenAI calls. We bound EACH op
# rather than only the loop boundary, and we bound the generation phase as a WHOLE
# as well as per call — seven calls that each finish just under a per-call bound
# would still overrun the task (the budget-guard-inner-op lesson, #1280):
#   build (25s) + generation phase (75s) + overhead < 120s soft limit.
_BUILD_TIMEOUT_S = 25.0
_GENERATE_TIMEOUT_S = 15.0
_GENERATE_PHASE_TIMEOUT_S = 75.0

# How many nominees the blurb is allowed to describe — unchanged from the request
# path it replaces, so the text does not change shape on the day this ships.
_TOP_NOMINEES = 5


async def _build_payload() -> dict | None:
    """Build the Oscars payload in its own session scope.

    Isolated so the whole DB interaction sits inside one `asyncio.wait_for`: if the
    aggregation overruns, cancellation unwinds the `async with` and closes the
    session cleanly rather than leaking a connection.
    """
    from app.routes.oscars import build_oscars_payload
    from app.tasks.base import get_task_session

    async with get_task_session() as db:
        return await build_oscars_payload(db)


async def _generate_category_preview(category: dict) -> tuple[str, str | None]:
    """One category's blurb, bounded. Returns `(key, text_or_None)`."""
    from app.services.llm import generate_oscars_category_preview

    top_nominees = [
        {
            "name": n["name"],
            "probability": n["probability"],
            "movement_24h": n["movement_24h"],
            "opening_probability": n["opening_probability"],
        }
        for n in category["nominees"][:_TOP_NOMINEES]
    ]
    try:
        text = await asyncio.wait_for(
            asyncio.to_thread(
                generate_oscars_category_preview, category["name"], top_nominees
            ),
            timeout=_GENERATE_TIMEOUT_S,
        )
    except asyncio.TimeoutError:
        logger.warning(
            "Oscars preview for %s exceeded %.0fs — skipping it",
            category["key"],
            _GENERATE_TIMEOUT_S,
        )
        return category["key"], None
    except Exception as exc:
        logger.warning("Oscars preview failed for %s: %s", category["key"], exc)
        return category["key"], None

    return category["key"], text or None


async def _generate_movers_summary(biggest_movers: list) -> str | None:
    """The movers blurb, bounded. `None` means 'no movers line this run'."""
    from app.services.llm import generate_oscars_movers_summary

    try:
        return (
            await asyncio.wait_for(
                asyncio.to_thread(generate_oscars_movers_summary, biggest_movers),
                timeout=_GENERATE_TIMEOUT_S,
            )
            or None
        )
    except asyncio.TimeoutError:
        logger.warning(
            "Oscars movers summary exceeded %.0fs — skipping it", _GENERATE_TIMEOUT_S
        )
        return None
    except Exception as exc:
        logger.warning("Oscars movers summary failed: %s", exc)
        return None


async def _generate_all(payload: dict) -> dict[str, str]:
    """Every blurb for one run. Concurrent, because each call is now in a thread."""
    major = [c for c in payload.get("categories", []) if c.get("is_major")]
    movers = payload.get("biggest_movers") or []

    jobs = [_generate_category_preview(c) for c in major]
    if movers:
        jobs.append(_movers_job(movers))

    previews: dict[str, str] = {}
    for result in await asyncio.gather(*jobs, return_exceptions=True):
        if isinstance(result, BaseException):
            logger.warning("Oscars preview job raised: %s", result)
            continue
        key, text = result
        if text:
            previews[key] = text
    return previews


async def _movers_job(movers: list) -> tuple[str, str | None]:
    """Wrap the movers summary in the `(key, text)` shape `_generate_all` gathers."""
    return "biggest_movers", await _generate_movers_summary(movers)


async def _refresh_oscars_previews() -> dict:
    from app.tasks.redis_state import get_redis_client

    try:
        payload = await asyncio.wait_for(_build_payload(), timeout=_BUILD_TIMEOUT_S)
    except asyncio.TimeoutError:
        # A slow build is not proof there is nothing to say, so leave the published
        # previews alone and let them expire on their own if this keeps happening.
        logger.warning(
            "Oscars payload build exceeded %.0fs — degrading to skip", _BUILD_TIMEOUT_S
        )
        return {"skipped": "build_timeout", "degraded": True}
    except Exception as exc:
        logger.error("Oscars payload build failed: %s", exc)
        return {"skipped": "build_error", "degraded": True}

    if not payload:
        return {"skipped": "no_payload"}

    major = [c for c in payload.get("categories", []) if c.get("is_major")]
    if not major:
        # Self-suppressing on DATA, not on a date: if the markets go away the beat
        # costs one query and makes no OpenAI call, and it heals itself when they
        # come back — no hardcoded ceremony window to go stale.
        return {"skipped": "no_major_categories"}

    try:
        previews = await asyncio.wait_for(
            _generate_all(payload), timeout=_GENERATE_PHASE_TIMEOUT_S
        )
    except asyncio.TimeoutError:
        logger.warning(
            "Oscars preview generation phase exceeded %.0fs — publishing nothing",
            _GENERATE_PHASE_TIMEOUT_S,
        )
        return {"skipped": "generate_phase_timeout", "degraded": True}

    if not previews:
        # Generation unavailable or every call failed. Do NOT touch the key: an
        # existing envelope keeps rendering until it naturally expires, and a
        # missing one stays missing. Publishing `{}` here would blank the page's
        # previews on one bad provider minute.
        return {"skipped": "no_previews_generated", "degraded": True}

    try:
        get_redis_client().setex(
            PREVIEWS_REDIS_KEY, PREVIEWS_TTL_SECONDS, build_previews_envelope(previews)
        )
    except Exception as exc:
        logger.error("Failed to publish Oscars previews: %s", exc)
        return {"error": "redis_write_failed"}

    return {
        "published": True,
        "previews": len(previews),
        "major_categories": len(major),
    }
