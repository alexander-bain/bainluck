"""#9653: the published hubs a ``/search`` page's own games belong to.

SHIP: a reader who searches a club and sees this week's NFL game, or a
postseason MLB game, can open the same NFL-week / MLB-postseason hub they would
reach from Discover or Browse. (Pillar: DISCOVER / MATCHING.)

The Search consumer of ``app.services.container_discovery``. It adds ONE
optional top-level key to the ``GET /api/events/search`` payload, and nothing
else in that payload moves:

* ``collections`` — at most ``SEARCH_COLLECTIONS_CAP`` producer cards, exactly
  as ``discover_collections`` emits them, most-matched first. It is present only
  when there is at least one card, so with the flags off, with no matching hub,
  or when the read fails or overruns, the payload is byte-identical to the one
  released clients already decode ("missing field = no collections").

RELEVANCE, NOT A SLOT. The only evidence is the games this page already
shows (``results[].id``): a hub is offered only if it contains one of them.
There is no new ranking, no score and no reserved position. What the reader
typed decided the games, and the games decide the hub.

LIVE AUTHORITY, NOT CACHED. Publication can be withdrawn at any moment, so the
cards are read on EVERY serve and attached AFTER the response cache is read or
written. The cache never holds a card, and a withdrawn hub is gone from the next
response rather than surviving for the cache TTL. Flag-off cost is zero: the
switches are read before anything else, and the producer itself reads them again
before its first statement.

BOUNDED. One producer call (two statements), capped at
``SEARCH_COLLECTION_READ_BUDGET_SECONDS`` (sized from production, #10274). A failure or overrun keeps the ordinary
answer, and it can never turn a served search into an error.
"""

from __future__ import annotations

import asyncio
import logging

from app.services import container_discovery

logger = logging.getLogger(__name__)

#: Most cards one search page can carry (the coordinator's cap, #9653).
SEARCH_COLLECTIONS_CAP = 2

#: The producer read's ceiling on a search page (#10274). It started as
#: Discover's 0.25 s, and that is a coin flip. The aggregate statement alone
#: measured 70-275 ms on production (EXPLAIN ANALYZE, 10/3 03:3xZ, eagles and
#: bills page ids, plus 7-12 ms of planning). The schema probe and two round
#: trips add to that, so about half of searches cut the read and dropped the
#: Collections row (eagles 0/4 cache hits at 323-344 ms; bills and chiefs
#: carried it at 69-243 ms). 0.6 s is about twice the slowest whole read
#: observed. A read is only charged its real duration, so a 300 ms read costs
#: ~50 ms more than the old give-up at 250 ms, and the reader gets the row.
SEARCH_COLLECTION_READ_BUDGET_SECONDS = 0.6

#: The slowest producer statement measured on production when the budget was
#: set (ms, execution + planning). The guard test keeps the budget >= 2x this.
MEASURED_COLLECTION_READ_MAX_MS = 287


def search_collections_enabled() -> bool:
    """Both switches the producer honours, read through their own functions."""
    if not container_discovery.container_discovery_enabled():
        return False
    from app.routes.containers import containers_read_enabled

    return containers_read_enabled()


def _page_event_ids(payload: dict) -> list[int]:
    ids: list[int] = []
    for row in payload.get("results") or ():
        if not isinstance(row, dict):
            continue
        try:
            ids.append(int(row["id"]))
        except (KeyError, TypeError, ValueError):
            continue
    return ids


async def attach_search_collections(
    db,
    payload: dict,
    *,
    budget_seconds: float = SEARCH_COLLECTION_READ_BUDGET_SECONDS,
) -> dict:
    """``payload`` plus ``collections`` when this page's games are in a published hub.

    Returns the SAME object, untouched, whenever there is nothing to add: flags
    off, no games on the page, no eligible hub, or a failed/overrun read. A
    returned card list is a new dict, so a caller that has already written
    ``payload`` to the cache cannot have the cached body altered after the fact.
    """
    try:
        if not search_collections_enabled():
            return payload
        event_ids = _page_event_ids(payload)
        if not event_ids:
            return payload
        read = await asyncio.wait_for(
            container_discovery.discover_collections(
                db, event_ids=event_ids, limit=SEARCH_COLLECTIONS_CAP
            ),
            timeout=min(budget_seconds, SEARCH_COLLECTION_READ_BUDGET_SECONDS),
        )
    except Exception:  # noqa: BLE001 — never fail a served search on a bonus read
        # A cancelled or failed statement can leave the session aborted. The
        # answer is already assembled; restore the session for the dependency's
        # own close.
        try:
            await db.rollback()
        except Exception:  # noqa: BLE001
            pass
        logger.warning(
            "search collection read failed; serving the ordinary answer", exc_info=True
        )
        return payload

    cards = list(read.collections[:SEARCH_COLLECTIONS_CAP])
    if not cards:
        return payload
    return {**payload, "collections": cards}
