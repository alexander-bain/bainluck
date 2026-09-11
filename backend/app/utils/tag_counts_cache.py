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


#: The frontend's own recursion backstop, mirrored (`lib/feedSections.ts`).
#:
#: A bundle at or past this depth contributes NOTHING to the page — the
#: renderer `continue`s past it rather than falling back to counting the
#: wrapper as one card — so a count that stopped at the cap and added 1 would
#: over-promise by exactly the cards the reader never gets.
_MAX_BUNDLE_DEPTH = 3


def _flatten_bundles(items: list, depth: int = 0) -> list[dict]:
    """The Python mirror of ``flattenFeedBundles`` in ``lib/feedSections.ts``.

    Every clause here exists because the renderer has it, not because it is the
    obvious way to count:

    * a non-bundle passes through;
    * a bundle at ``depth >= _MAX_BUNDLE_DEPTH`` is DROPPED, contributing zero;
    * members come from ``data.items`` with ``?? []`` semantics, so a malformed
      or member-less bundle contributes zero rather than one.

    Kept as a mirror rather than shared because the two live on opposite sides
    of the wire; the guard test pins them to the same production-shaped payload
    so they cannot drift silently — and the FRONTEND half is pinned too, by
    `__tests__/tagCountMirrorsFlattenBundles4920.test.ts`, which runs the real
    `flattenFeedBundles` over that payload and gets the same 11.

    ONE DELIBERATE DIVERGENCE, verified by running the renderer rather than
    reading it: on a bundle whose ``data`` is absent or ``null`` the frontend
    THROWS — ``(item.data as FeedBundleData).items`` casts a lie and the read
    dies — whereas this contributes zero. Not reachable from our own backend
    (all four emitters in ``discover_bundles.py`` set ``data``), so it is latent
    fragility filed on its own rather than fixed inside this repair. Copying the
    throw here would be strictly worse: a warmer that raised would abandon the
    category, and leaving it unmeasured is already the correct fallback.
    """
    out: list[dict] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        if item.get("type") != "bundle":
            out.append(item)
            continue
        if depth >= _MAX_BUNDLE_DEPTH:
            continue
        data = item.get("data")
        members = (data or {}).get("items") if isinstance(data, dict) else None
        if not isinstance(members, list):
            members = []
        out.extend(_flatten_bundles(members, depth + 1))
    return out


def split_rendered_items(items: Any) -> dict[str, int] | None:
    """Count one category's rendered feed items into the tile's two numbers.

    COUNTS WHAT THE PAGE COUNTS, WHICH MEANS UNFOLDING BUNDLES (CERT-2589).
    The first version of this counted a bundle as the ONE card it appears to be
    and argued that "markets" was a card count. That was wrong about the page:
    `categories/[slug]/page.tsx` builds its header from
    ``flattenFeedBundles(allItems)`` and counts ``type === "futures"`` over the
    FLATTENED list, because #2597 had already found the folded count promising
    "18 markets" over a page showing 22.

    So a bundle contributes its members, recursively. Measured on a tagged
    production Tennis payload — 8 futures plus one 3-member bundle — the folded
    count published 9 while the page rendered and labelled 11. Counting the
    wrapper was the same defect this whole ship exists to remove, pointed the
    other way: a number that does not survive being checked against its page.

    ``event`` is the tile's "events" and ``futures`` its "markets", both read
    AFTER flattening, exactly as the header does.

    Returns ``None`` for an unusable payload, so the caller can leave the
    category absent rather than publish a zero it would have to defend.
    """
    if not isinstance(items, list):
        return None

    events = 0
    markets = 0
    for item in _flatten_bundles(items):
        kind = item.get("type")
        if kind == "event":
            events += 1
        elif kind == "futures":
            markets += 1

    return {"events": events, "futures": markets}
