"""#9653: published hubs compete with cards on Discover's canonical first page.

The ordinary composed deck supplies relevance and scores. The fixed first-page
window keeps collection membership independent of pagination size and offset.
No reserved slot, score bonus, assembly, or publication decision lives here.
"""

import asyncio
import logging

from app.services import container_discovery

logger = logging.getLogger(__name__)
COLLECTION_READ_BUDGET_SECONDS = 0.25


def feed_collections_enabled(*, mode, include_events, my_teams_only, debug=False):
    from app.routes.containers import containers_read_enabled

    return (
        (mode or "discover").lower() == "discover"
        and include_events
        and not my_teams_only
        and not debug
        and container_discovery.container_discovery_enabled()
        and containers_read_enabled()
    )


async def add_feed_collections(
    db,
    items,
    *,
    rank_key,
    page_window=20,
    budget_seconds=COLLECTION_READ_BUDGET_SECONDS
):
    """Insert eligible cards by the existing key, preserving ordinary deck order.

    Read publication on every serve; callers must not cache the resulting deck.
    A hub inherits its strongest visible member's score and recency, so it
    cannot purchase a slot with a new ranking bonus. The producer card remains
    intact under ``data``, the normal feed envelope.
    """
    games = {
        item["data"]["id"]: item
        for item in items[:page_window]
        if item.get("type") == "event" and item.get("data", {}).get("id") is not None
    }
    if not games or budget_seconds <= 0:
        return items
    try:
        read = await asyncio.wait_for(
            container_discovery.discover_collections(db, event_ids=games),
            timeout=min(budget_seconds, COLLECTION_READ_BUDGET_SECONDS),
        )
    except Exception:
        # A cancelled/failed statement can leave the session aborted. Ordinary
        # cards are already serialized; restore it for subsequent feed reads.
        await db.rollback()
        logger.warning(
            "Discover collection read failed; keeping ordinary cards", exc_info=True
        )
        return items

    additions = []
    for card in read.collections:
        members = [games[i] for i in card["matched_event_ids"] if i in games]
        if not members:
            continue
        strongest = max(members, key=rank_key)
        additions.append(
            {
                "type": "collection",
                "score": strongest.get("score", 0),
                "_rank_score": strongest.get("_rank_score", strongest.get("score", 0)),
                "_sort_time": strongest.get("_sort_time", 0),
                "reason": card["name"],
                "headline": None,
                "data": card,
            }
        )
    if not additions:
        return items
    result = list(items)
    for card in sorted(additions, key=rank_key, reverse=True):
        position = next(
            (i for i, item in enumerate(result) if rank_key(card) > rank_key(item)),
            len(result),
        )
        result.insert(position, card)
    return result
