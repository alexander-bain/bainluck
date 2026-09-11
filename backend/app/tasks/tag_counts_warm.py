"""Measure what each Browse category actually renders, so the tile can say it (#4920).

WHAT A PERSON SEES TODAY. ``/categories`` advertises ``Tennis — 368 events ·
4,627 markets``; the page behind that tile renders **eleven** cards. Measured on
production 2026-09-11 04:36-05:05Z, **all 28 visible tiles over-promise and not
one is correct**::

    cricket        784 promised ->   1 delivered   (784x)
    table_tennis  3,102          ->   4            (776x)
    tennis        4,995          ->  11            (454x)
    esports       1,510          ->   6            (252x)
    politics      6,757          -> 100            (68x)

`app/utils/tag_counts_cache.py` carries the why. This module is the producer.

WHY A PRODUCER AND NOT A BETTER QUERY. The honest number already exists:
``GET /api/feed?category=X`` builds the very list the page draws, and counting
that list the way the renderer counts it is the answer. (NOT the response's
``total``, which counts feed slots — measured on production, tennis reported
``total=9`` for a page rendering 11, because one of the nine was a bundle. See
`tag_counts_cache.split_rendered_items` and CERT-2589.)
What is missing is anybody keeping it. Serving it on demand is the one shape
that cannot work — 28 categories x ~1 s measured is half a minute per page load
— so it is measured on a beat and read from Redis, the shape
`futures_categories_warm` uses for the same reason.

🔴 IT CALLS THE ROUTE, NOT A COPY OF THE ROUTE. ``get_feed`` is invoked with a
worker session (`get_task_session`), the way ``_prewarm_feed_shape`` and
``_precompute_politics`` do, so the number published here and the number the
page renders cannot drift into two implementations of one promise. Turning this
beat off restores exactly today's behaviour: every tile falls back to its
candidate count, wrong in the same direction it has always been wrong, and no
tile disappears.

🔴 IT DOES NOT PASS THE PRE-WARM MARKER, AND THAT IS DELIBERATE.
``_prewarm_feed_shape`` tags its synthetic request with
``FEED_PREWARM_SCOPE_KEY`` because it is publishing the anonymous FIRST-PAINT
slot and must be allowed to. This pass is not a first paint and must never
become one: it asks at ``COUNT_LIMIT``, a limit no reader sends, so it can
neither poison nor pre-empt the shared anon feed. It reads like any anonymous
visitor and takes whatever the reader would have got, cache hit included.

A ZERO-YIELD RUN READS FAILED, NOT GREEN (gotcha #53). ``set()`` reports that a
client accepted the bytes, never that Redis kept them, so this task reads the
slot back and requires a ``created_at`` this run put there. "The build returned"
is not "the tile is telling the truth".

ONE BAD CATEGORY MUST NOT WIPE THE PASS (gotcha #42). Every category is measured
under its own try/except and its own timeout; a category that errors is simply
absent from the publish, which the route reads as "not measured" and answers
with the candidate count. `test_one_failing_category_does_not_wipe_its_siblings`
pins that both ways.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

logger = logging.getLogger(__name__)

#: How many items to ask for. It must exceed the pipeline's own per-category
#: candidate ceiling or the SPLIT would be truncated: `politics` returns
#: ``total=100`` and exactly 100 items at every limit from 20 to 400 (measured
#: 2026-09-11 04:38Z), so 100 is that ceiling and 250 clears it with room. Note
#: ``total`` itself is limit-independent — politics reports 100 even at
#: ``limit=20`` — but the events/markets split is counted from ``items``, and
#: items ARE capped by the limit. Asking small would publish a confident
#: undercount.
COUNT_LIMIT = 250

#: Bound on ONE category's measurement. The measured spread is 0.9-1.2 s across
#: five production categories; 25 s is far above that and far below the pass
#: budget, so a single wedged category is reported by this timeout with a reason
#: rather than eating the whole pass.
PER_CATEGORY_TIMEOUT_SECONDS = 25

#: The pass stops starting new categories past this. 28 visible tiles x ~1 s is
#: ~30 s of work, so 240 s is an ~8x margin: it is a backstop against a slow
#: afternoon, not a budget anyone should be planning against.
PASS_BUDGET_SECONDS = 240

#: The most categories one pass will measure, ordered by candidate total
#: descending (the biggest liars first) then by name. 46 categories exist;
#: 32 covers every tile `/categories` can display today (28) with headroom,
#: and bounds the pass whatever the classifier starts emitting.
MAX_CATEGORIES = 32

#: How many consecutive lost deliveries may pass before a reader is uncovered.
#: Four, matching `futures_categories_warm`: `background` was measured
#: delivering p50 138-152 s against a declared 120 s, and a period sized to
#: survive exactly one miss is a period sized to fail.
MISSED_DELIVERY_ALLOWANCE = 4


def warm_period_seconds() -> int:
    """The beat period, derived from the slot's own freshness TTL.

    ``ttl / (allowance + 1)``: at a 3600 s TTL and four permitted misses, a
    rebuild every 12 minutes means the slot is at most 5 x 12 = 60 minutes old
    when the fifth delivery in a row fails — the exact edge of servable.

    Derived at call time rather than frozen into a constant so a queue editing
    ``FRESH_TTL_SECONDS`` moves this too. #2236 is the incident where a period
    lived as a literal in one file and its ceiling in another, with nothing
    comparing them.
    """
    from app.utils.tag_counts_cache import FRESH_TTL_SECONDS

    return FRESH_TTL_SECONDS // (MISSED_DELIVERY_ALLOWANCE + 1)


def warm_period_minutes() -> int:
    """`warm_period_seconds()` as the whole minutes the crontab spells."""
    return warm_period_seconds() // 60


def _anonymous_feed_request():
    """A synthetic anonymous ASGI request carrying no internal marker.

    No ``FEED_PREWARM_SCOPE_KEY``: see the module docstring. Empty headers means
    no session id, so the route treats this as an anonymous visitor.
    """
    from starlette.requests import Request

    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/feed",
            "headers": [],
            "query_string": b"",
        }
    )


async def _measure_one_category(category: str) -> dict[str, int] | None:
    """What ``/categories/<category>`` renders, as ``{events, futures}``.

    ``None`` means NOT MEASURED — a timeout, an error, or a payload without a
    usable ``items`` list. The caller leaves such a category out of the publish
    entirely so the route keeps its candidate count; returning a zero here would
    delete the tile (#2627). Never raises.
    """
    from fastapi import Response

    from app.routes.feed import get_feed
    from app.tasks.base import get_task_session
    from app.utils.tag_counts_cache import split_rendered_items

    try:
        async with get_task_session() as db:
            payload = await asyncio.wait_for(
                get_feed(
                    response=Response(),
                    request=_anonymous_feed_request(),
                    limit=COUNT_LIMIT,
                    offset=0,
                    sport=None,
                    # Every parameter is passed EXPLICITLY. An omitted route
                    # parameter arrives as the `Query(...)` object itself, which
                    # is truthy and would stringify into the cache key — the
                    # trap `_prewarm_feed_shape` records above `category=None`.
                    category=category,
                    include_events=True,
                    include_futures=True,
                    my_teams_only=False,
                    mode=None,
                    tags=None,
                    event_pct=None,
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
                timeout=PER_CATEGORY_TIMEOUT_SECONDS,
            )
    except asyncio.TimeoutError:
        logger.warning(
            "tag_counts_warm: %s timed out after %ss — leaving it unmeasured",
            category,
            PER_CATEGORY_TIMEOUT_SECONDS,
        )
        return None
    except Exception:  # noqa: BLE001 — one bad category must not wipe the pass
        logger.warning("tag_counts_warm: %s failed", category, exc_info=True)
        return None

    if not isinstance(payload, dict):
        return None

    return split_rendered_items(payload.get("items"))


async def _candidate_categories() -> list[str]:
    """The categories to measure, biggest candidate total first.

    Enumerated from the route's OWN candidate pass rather than from a list
    kept here, so a category the classifier starts emitting is measured without
    anybody remembering to add it. Ordering is total-descending then by name:
    descending because the largest tiles are the largest lies, and by name so a
    tie cannot make the pass non-deterministic between runs.
    """
    from app.routes.feed import _candidate_tag_counts
    from app.tasks.base import get_task_session

    async with get_task_session() as db:
        counts = await _candidate_tag_counts(db)

    ranked = sorted(
        counts.items(),
        key=lambda kv: (-(kv[1].get("events", 0) + kv[1].get("futures", 0)), kv[0]),
    )
    return [cat for cat, _ in ranked[:MAX_CATEGORIES]]


async def _warm_tag_counts(rc=None) -> dict[str, Any]:
    """Measure every Browse category and publish the result. Never raises.

    The summary speaks the ``task_verdict`` vocabulary, and the unit is counts a
    reader is actually served — ``published`` — never a pass that returned.
    """
    from app.utils import tag_counts_cache

    started = time.monotonic()
    _before_counts, before = tag_counts_cache.read(rc)
    error: str | None = None
    measured: dict[str, dict[str, int]] = {}
    attempted = 0
    budget_exhausted = False

    try:
        categories = await _candidate_categories()
    except Exception as exc:  # noqa: BLE001 — no list means no pass, not a crash
        logger.warning("tag_counts_warm: candidate enumeration failed", exc_info=True)
        return {
            "terminal": "failed",
            "published": False,
            "error": f"enumerate: {str(exc)[:120]}",
            "measured": 0,
            "elapsed_ms": round((time.monotonic() - started) * 1000, 2),
        }

    for category in categories:
        if time.monotonic() - started > PASS_BUDGET_SECONDS:
            # Stop STARTING work, publish what is already measured. A partial
            # publish is correct here precisely because absence is not zero: the
            # categories that were not reached keep their candidate count.
            budget_exhausted = True
            logger.warning(
                "tag_counts_warm: pass budget %ss exhausted after %d categories",
                PASS_BUDGET_SECONDS,
                attempted,
            )
            break
        attempted += 1
        split = await _measure_one_category(category)
        if split is not None:
            measured[category] = split

    if not measured:
        # Publishing an empty map would be indistinguishable from "every
        # category renders nothing" on the next read, and the route would be
        # right to ignore it. Leave the previous publish in place.
        logger.warning("tag_counts_warm: measured 0 of %d categories", attempted)
        return {
            "terminal": "failed",
            "published": False,
            "error": error or "no_category_measured",
            "attempted": attempted,
            "measured": 0,
            "budget_exhausted": budget_exhausted,
            "created_at": before,
            "elapsed_ms": round((time.monotonic() - started) * 1000, 2),
        }

    try:
        tag_counts_cache.publish(measured, rc)
    except Exception as exc:  # noqa: BLE001 — a failed publish is a verdict
        error = f"publish: {str(exc)[:120]}"
        logger.warning("tag_counts_warm: publish failed", exc_info=True)

    # Read back: a republish is a NEW stamp, not merely a present one. A run
    # whose write was swallowed leaves the previous publish readable, and
    # "there are counts" would grade that green while they age out.
    _after_counts, after = tag_counts_cache.read(rc)
    published = after is not None and after != before

    return {
        "terminal": "complete" if published else "failed",
        "published": published,
        "attempted": attempted,
        "measured": len(measured),
        "budget_exhausted": budget_exhausted,
        "created_at": after,
        "previous_created_at": before,
        "error": error,
        "period_s": warm_period_seconds(),
        "elapsed_ms": round((time.monotonic() - started) * 1000, 2),
    }
