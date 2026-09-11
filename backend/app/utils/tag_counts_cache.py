"""The render-truthful per-category counts behind ``/api/feed/tag-counts`` (#4920).

WHAT A PERSON SEES TODAY. The Browse tile advertises ``Tennis — 368 events ·
4,627 markets``; tapping it renders **eleven** cards. Measured on production
2026-09-11 04:36-04:38Z, every one of the seventeen Browse categories
over-promises, and not one is correct::

    politics      6,757 promised ->  100 delivered   (68x)
    tennis        4,995           ->   11            (454x)
    table_tennis  3,102           ->    4            (776x)
    cricket         784           ->    1            (784x)
    football      2,556           ->   33            (77x)

``get_tag_counts`` counts rows admitted by the CANDIDATE predicate; the page
renders what survives the pipeline (`_filter_discover_event_noise`, the score
cut, market-quality gates, dedup). Candidate admission is necessary, not
sufficient, so the count can only ever over-promise.

WHY THIS MODULE EXISTS RATHER THAN A BETTER QUERY. The honest number is not
missing and does not need inventing: ``GET /api/feed?category=X`` already
returns a ``total``, and that total is what the page renders. There is no second
predicate to write — there is a number being computed and thrown away. This
module is the slot it gets kept in, so the tile and the page answer from one
place, which is what the promise in ``get_tag_counts`` has always claimed.

🔴 "NOT MEASURED" AND "MEASURED ZERO" ARE DIFFERENT ANSWERS, AND CONFLATING THEM
DELETES TILES. ``/categories`` removes a tile whose counts sum to zero —
deliberately, because a tile with no items is a door onto an empty page (#2627,
`app/categories/page.tsx`). Both states therefore have teeth:

* **Not measured** (cold cache, a category outside the pass, a run that errored
  on that one category) ⇒ the category is ABSENT from this payload and the
  caller keeps its candidate count. It must never be published as
  ``{"events": 0, "futures": 0}``: that would empty the Browse grid over a cold
  Redis, a worse defect than the one this ships against.
* **Measured zero** (the pipeline was asked and rendered nothing) ⇒ published as
  a real zero, and the tile correctly disappears. That is #2627's own rule
  working for the first time — until now the candidate count kept a door open
  onto a page that renders nothing.

The route's merge is written to that distinction and
`test_a_cold_category_keeps_its_candidate_count` pins the first half of it.

TTLs. ``FRESH_TTL_SECONDS`` is sized so a reader is covered across
``MISSED_DELIVERY_ALLOWANCE`` consecutive lost beats (the producer derives its
period from it — `app/tasks/tag_counts_warm.py`), and the ``:stale`` mirror
outlives it by a day so a wedged producer degrades to an old-but-real count
rather than back to the 784x lie.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

#: The published slot. One name, imported by both the route and the producer —
#: #2236 is the incident where a period lived as a literal in two files with
#: nothing comparing them, and a payload went uncovered for a full minute of
#: every two.
CACHE_KEY = "bainluck:feed:tag_counts_rendered"

#: Served when the primary has lapsed. An old real count beats a fresh false one.
STALE_CACHE_KEY = f"{CACHE_KEY}:stale"

#: How long a published set of counts is considered current.
#:
#: 🔴 4500 IS CHOSEN SO THE DERIVED PERIOD CLEARS THE SETTLEMENT SWEEP.
#: The producer's period is `FRESH_TTL_SECONDS // (MISSED_DELIVERY_ALLOWANCE +
#: 1)` = 900 s = 15 min, and `*/15` fires at :00 :15 :30 :45 — none of which
#: land in the settlement sweep's `:31`+13m window (:31–:44). That is not a
#: nicety: at the first-draft 3600 the period was 12 min, `*/12` fired at :36
#: INSIDE that window, and `test_the_run_window_does_not_sit_under_a_growing_pile`
#: went red at `19 <= 18`. The alternative on offer was to raise that sweep's
#: co-fire ceiling, which spends a sibling's headroom to buy this beat three
#: minutes of freshness it does not need.
#:
#: A 14-minute window cannot be dodged by ANY period of 14 minutes or less — a
#: p-periodic schedule always has a fire inside any window of length >= p — so
#: 15 is the fastest cadence that can clear it at all. `test_the_beat_never_fires_
#: inside_the_settlement_sweep_window` pins the result, so a later edit to this
#: TTL cannot silently walk back into the window.
FRESH_TTL_SECONDS = 4500

#: The mirror outlives the primary by a day.
STALE_TTL_SECONDS = 86400


def publish(counts: dict[str, dict[str, int]], rc=None) -> str:
    """Publish ``counts`` and return the ``created_at`` stamp written.

    Callers pass only the categories they actually measured. Absent is the
    signal for "not warmed"; see the module docstring on why a zero is not.
    """
    from app.tasks.redis_state import get_redis_client

    rc = rc or get_redis_client()
    created_at = datetime.now(timezone.utc).isoformat()
    payload = json.dumps({"created_at": created_at, "counts": counts})
    rc.set(CACHE_KEY, payload, ex=FRESH_TTL_SECONDS)
    rc.set(STALE_CACHE_KEY, payload, ex=STALE_TTL_SECONDS)
    return created_at


def read(rc=None) -> tuple[dict[str, dict[str, int]], str | None]:
    """Return ``(counts, created_at)``, falling back to the mirror, then to empty.

    Never raises. An unreadable cache means the caller serves candidate counts —
    today's behaviour — which is wrong but not destructive; raising here would
    take ``/categories`` down entirely, and the page has been through that
    already (the GROUP BY collision that returned a plain-text 500 for the whole
    life of the route).
    """
    from app.tasks.redis_state import get_redis_client

    try:
        rc = rc or get_redis_client()
        raw = rc.get(CACHE_KEY) or rc.get(STALE_CACHE_KEY)
    except Exception:  # noqa: BLE001 — an unreadable cache is a fallback, not a crash
        logger.warning("tag_counts_cache: read failed", exc_info=True)
        return {}, None

    if not raw:
        return {}, None

    try:
        body = json.loads(raw)
    except (TypeError, ValueError):
        logger.warning("tag_counts_cache: undecodable payload in %s", CACHE_KEY)
        return {}, None

    if not isinstance(body, dict):
        return {}, None

    counts = body.get("counts")
    if not isinstance(counts, dict):
        return {}, None

    created_at = body.get("created_at")
    return counts, created_at if isinstance(created_at, str) else None


def split_rendered_items(items: Any) -> dict[str, int] | None:
    """Count one category's rendered feed items into the tile's two numbers.

    ``event`` is the tile's "events"; ``futures`` and ``bundle`` are its
    "markets" — a bundle is one card standing for a group of markets, and it is
    counted as the ONE card a reader sees, because this number's whole job is to
    predict the page. That makes "markets" a card count, which is the tile's
    existing word for it and not a question this ship reopens.

    Returns ``None`` for an unusable payload, so the caller can leave the
    category absent rather than publish a zero it would have to defend.
    """
    if not isinstance(items, list):
        return None

    events = 0
    markets = 0
    for item in items:
        if not isinstance(item, dict):
            continue
        kind = item.get("type")
        if kind == "event":
            events += 1
        elif kind in ("futures", "bundle"):
            markets += 1

    return {"events": events, "futures": markets}
