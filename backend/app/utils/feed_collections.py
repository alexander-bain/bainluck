"""#9653: published hubs compete with cards on Discover's canonical first page.

The ordinary composed deck supplies relevance and scores. The fixed first-page
window keeps collection membership independent of pagination size and offset.
No reserved slot, score bonus, assembly, or publication decision lives here.
"""

import asyncio
import hashlib
import logging
import time

from sqlalchemy import text

from app.services import container_discovery
from app.utils.container_corrections import PUBLICATION_COLUMN, REVISION_COLUMN

logger = logging.getLogger(__name__)
COLLECTION_READ_BUDGET_SECONDS = 0.25
_fingerprint_cache: tuple[float, str] | None = None

#: #10003: what a cached collection-bearing page is keyed on. One row per
#: discoverable published root hub, as ``id:membership_revision``. The revision
#: moves on the hub and every ancestor whenever anything its reader would see
#: changes — publish, withdraw, member correction, assembly — and never moves
#: back, so two different publication states can never share a fingerprint.
_FINGERPRINT_SQL = (
    "SELECT COALESCE(string_agg("
    f"id::text || ':' || {REVISION_COLUMN}::text, ',' ORDER BY id), '') "
    "FROM containers "
    f"WHERE {PUBLICATION_COLUMN} = 'published' "
    "AND parent_container_id IS NULL "
    "AND slug ~ :slug_pattern"
)


def feed_collections_enabled(
    *, mode, include_events, my_teams_only, debug=False, include_futures=True
):
    from app.routes.containers import containers_read_enabled

    # ``include_futures``: collections are a Discover ship, and every Discover
    # request carries futures. An events-only request (the native Sports tab's
    # Live Now / Upcoming backfill, the web Sports finished lookup) renders no
    # collection card on any client, so admitting it only cost it its cache
    # (#10003: 33 ms shared hit → 0.6–3.3 s cold build).
    return (
        (mode or "discover").lower() == "discover"
        and include_events
        and include_futures
        and not my_teams_only
        and not debug
        and container_discovery.container_discovery_enabled()
        and containers_read_enabled()
    )


async def feed_collections_cache_fingerprint(db, *, max_age_seconds=0.0):
    """The publication state a collection-bearing page may be cached under, or None.

    #10003. ``add_feed_collections`` reads publication on every BUILD; this
    lets a built page be reused only while that publication state still holds,
    so revocation stays live without disabling the cache. One statement over
    the few published root hubs.

    ``None`` means "could not tell" and the caller must not cache — which is
    the pre-#10003 behaviour, so a failure here costs speed, never truth. The
    read runs in a SAVEPOINT so a failed statement (an un-migrated database
    has no ``membership_revision``) rolls back alone instead of aborting the
    request's transaction or expiring its loaded rows.
    """
    # Discover opens reuse this public publication hash for at most five seconds.
    # This removes three DB round trips from a warm feed request. Prices and
    # personalized payloads keep their existing independent cache lifetimes.
    global _fingerprint_cache
    now = time.monotonic()
    max_age_seconds = min(max(0.0, max_age_seconds), 5.0)
    if (
        max_age_seconds > 0
        and _fingerprint_cache is not None
        and now - _fingerprint_cache[0] < max_age_seconds
    ):
        return _fingerprint_cache[1]
    try:
        async with db.begin_nested():
            raw = (
                await db.execute(
                    text(_FINGERPRINT_SQL),
                    {"slug_pattern": container_discovery.DISCOVERABLE_SLUG_PATTERN},
                )
            ).scalar()
    except Exception:
        logger.warning(
            "Discover collection fingerprint read failed; serving uncached",
            exc_info=True,
        )
        return None
    if not isinstance(raw, str):
        return None
    fingerprint = hashlib.sha256(f"v1|{raw}".encode()).hexdigest()[:16]
    if max_age_seconds > 0:
        _fingerprint_cache = (now, fingerprint)
    return fingerprint


#: #10290: which branch ``add_feed_collections`` took, for an ``observe`` hook.
COLLECTIONS_NO_PAGE_GAMES = "no_page_games"
COLLECTIONS_NO_BUDGET = "no_budget"
COLLECTIONS_READ_FAILED = "read_failed"
COLLECTIONS_READ = "read"


async def add_feed_collections(
    db,
    items,
    *,
    rank_key,
    page_window=20,
    budget_seconds=COLLECTION_READ_BUDGET_SECONDS,
    observe=None,
):
    """Insert eligible cards before their strongest member in the composed deck.

    Read publication on every serve; callers must not cache the resulting deck.
    The existing key selects the strongest visible member; its actual position
    determines placement. Composition has already moved cards out of key order,
    so a key scan cannot determine that position. A hub inherits the member's
    score and recency without a bonus. The producer card remains intact under
    ``data``, the normal feed envelope.

    ``observe`` (#10290), when given, is called once as ``observe(branch,
    collections)`` with one of the ``COLLECTIONS_*`` branches and, for
    ``COLLECTIONS_READ``, the cards the read returned (``None`` otherwise). It
    is how a display capture freezes this stage's only input; it changes
    nothing here.
    """
    games = _page_games(items, page_window)
    if not games or budget_seconds <= 0:
        if observe is not None:
            observe(
                COLLECTIONS_NO_PAGE_GAMES if not games else COLLECTIONS_NO_BUDGET,
                None,
            )
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
        if observe is not None:
            observe(COLLECTIONS_READ_FAILED, None)
        return items

    if observe is not None:
        observe(COLLECTIONS_READ, read.collections)
    return insert_feed_collections(
        items, read.collections, rank_key=rank_key, page_window=page_window
    )


def _page_games(items, page_window):
    return {
        item["data"]["id"]: item
        for item in items[:page_window]
        if item.get("type") == "event" and item.get("data", {}).get("id") is not None
    }


def insert_feed_collections(items, collections, *, rank_key, page_window=20):
    """The pure half of ``add_feed_collections``: place already-read cards.

    Split out for #10290 so the offline display replay places frozen cards by
    running this, not a copy. No I/O and no clock; ``items`` is not mutated.
    """
    games = _page_games(items, page_window)
    additions = []
    for card in collections:
        members = [games[i] for i in card["matched_event_ids"] if i in games]
        if not members:
            continue
        strongest = max(members, key=rank_key)
        additions.append(
            (
                strongest,
                {
                    "type": "collection",
                    "score": strongest.get("score", 0),
                    "_rank_score": strongest.get(
                        "_rank_score", strongest.get("score", 0)
                    ),
                    "_sort_time": strongest.get("_sort_time", 0),
                    "reason": card["name"],
                    "headline": None,
                    "data": card,
                },
            )
        )
    if not additions:
        return items
    result = list(items)
    for strongest, card in sorted(
        additions, key=lambda addition: rank_key(addition[1]), reverse=True
    ):
        result.insert(result.index(strongest), card)
    return result
