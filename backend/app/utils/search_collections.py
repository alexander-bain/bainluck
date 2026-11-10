"""#9653: the published hubs a ``/search`` page's own games belong to.

SHIP: a reader who searches a club and sees this week's NFL game, or a
postseason MLB game, can open the same NFL-week / MLB-postseason hub they would
reach from Discover or Browse. (Pillar: DISCOVER / MATCHING.)

The Search consumer of ``app.services.container_discovery``. It adds ONE
optional top-level key to the ``GET /api/events/search`` payload, and nothing
else in that payload moves:

* ``collections`` — at most ``SEARCH_COLLECTIONS_CAP`` producer cards. It is
  present only when there is at least one card. With the flags off or with no
  matching hub, the ordinary payload is unchanged. Failed or unfinished query
  reads add ``degraded=["collections"]`` and retain completed matches.

Relevance comes from title matches and the ordinary answer's matched games
and markets, including its family members. Computed sets are read only when
their producer is named, using the same licensed producers as their cards
and pages. Collection destinations are read after
both response-cache exits, so a withdrawn page cannot survive in the cache.

LIVE AUTHORITY, NOT CACHED. Publication can be withdrawn at any moment, so the
cards are read on EVERY serve and attached AFTER the response cache is read or
written. The cache never holds a card, and a withdrawn hub is gone from the next
response rather than surviving for the cache TTL. Flag-off cost is zero: the
switches are read before anything else, and the producer itself reads them again
before its first statement.

BOUNDED. Stored-set and computed-set reads share
``SEARCH_COLLECTION_READ_BUDGET_SECONDS``. Title matches finish before
unrelated member reads. A failure retains completed matches and declares the
unfinished collection lookup through ``degraded``.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Iterable

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


def _page_market_ids(payload: dict) -> list[int]:
    rows = list(payload.get("futures") or [])
    for family in payload.get("futures_families") or []:
        if not isinstance(family, dict):
            continue
        rows.extend(family.get("markets") or [])
        rows.extend(family.get("members") or [])
        rows.append(family.get("headline"))
    ids = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            ids.append(int(row["id"]))
        except (KeyError, TypeError, ValueError):
            continue
    return sorted(set(ids))


async def _attach_theme_family_refs(payload: dict) -> dict:
    """Attach ``collection_ref`` onto Search ``futures_families`` when Search
    collections and theme collections are enabled (#11040). Uses
    ``theme_collection_ref``'s own bounded side session and never touches the
    caller's ``db`` session."""
    try:
        if not search_collections_enabled():
            return payload
        families = payload.get("futures_families")
        if not isinstance(families, list) or not families:
            return payload
        from app.utils.theme_collection_ref import (
            attach_search_family_collection_refs,
            read_published_themes,
            theme_collections_enabled,
        )

        if not theme_collections_enabled():
            return payload
        published = await read_published_themes(max_age_seconds=5.0)
        if published is None or not published.themes:
            return payload
        updated = await attach_search_family_collection_refs(
            families, published=published
        )
        if updated is families:
            return payload
        return {**payload, "futures_families": updated}
    except Exception:  # noqa: BLE001
        logger.warning(
            "search family theme collection ref read failed; serving without ref",
            exc_info=True,
        )
        return payload


async def attach_search_collections(
    db,
    payload: dict,
    *,
    budget_seconds: float = SEARCH_COLLECTION_READ_BUDGET_SECONDS,
    titles_only: bool = False,
) -> dict:
    """Attach published collections matching the query or this page's member games.

    Returns the SAME object, untouched, whenever there is nothing to add: flags
    off or no eligible hub. A query read that fails names ``collections`` in
    ``degraded``, retaining any matches already read. A
    returned card list is a new dict, so a caller that has already written
    ``payload`` to the cache cannot have the cached body altered after the fact.
    """
    try:
        if not search_collections_enabled():
            return payload
    except Exception:  # noqa: BLE001
        return payload
    payload = await _attach_theme_family_refs(payload)
    event_ids = _page_event_ids(payload)
    query = payload.get("query")
    tokens = (
        container_discovery.collection_query_tokens(query)
        if isinstance(query, str)
        else ()
    )
    if not event_ids and not tokens:
        return payload
    cards = []
    degraded = False
    sport_key = (payload.get("filters") or {}).get("sport") or None

    async def read_cards():
        nonlocal degraded
        from app.utils.roundup_containers import ROUNDUP_PRODUCERS

        named_roundup = bool(tokens) and any(
            _matches(tokens, _producer_search_terms(producer))
            for producer in ROUNDUP_PRODUCERS.values()
        )
        if named_roundup:
            degraded = await _append_roundup_matches(
                db, cards, tokens, sport_key=sport_key
            )
            if cards:
                return
        kwargs = {"event_ids": event_ids, "limit": SEARCH_COLLECTIONS_CAP}
        if tokens:
            kwargs["query"] = query
            if not titles_only:
                kwargs["market_ids"] = _page_market_ids(payload)
        if sport_key:
            kwargs["sport_key"] = sport_key
        if titles_only:
            kwargs["titles_only"] = True
        read = await container_discovery.discover_collections(db, **kwargs)
        cards.extend(read.collections[:SEARCH_COLLECTIONS_CAP])
        for index, card in enumerate(tuple(cards)):
            if card.get("slug") == "midterms-2026" and not titles_only:
                from app.routes.containers import get_container

                # The page folds venue contributors and withholds unavailable
                # members. Its admitted presentation owns the advertised count.
                # Other completed matches survive a failed or timed-out page read.
                cards.remove(card)
                page = await get_container(
                    "midterms-2026", include_children=True, revision=None,
                    cursor=None, limit=None, compact=False, db=db,
                )
                if page.get("state") != "published" or not page["member_count"]:
                    continue
                cards.insert(index, {
                    **card,
                    "question_count": page["member_count"],
                    "game_count": 0,
                    "revision": page["revision"],
                })
        degraded = degraded or bool(tokens and read.truncated)
        if tokens and read.reason == container_discovery.REASON_SCHEMA_ABSENT:
            raise RuntimeError("collection publication schema is unavailable")

    try:
        await asyncio.wait_for(
            read_cards(),
            timeout=min(budget_seconds, SEARCH_COLLECTION_READ_BUDGET_SECONDS),
        )
    except Exception:  # noqa: BLE001 — never fail a served search on a bonus read
        # A cancelled or failed statement can leave the session aborted. The
        # answer is already assembled; restore the session for the dependency's
        # own close.
        try:
            await db.rollback()
        except Exception:  # noqa: BLE001
            logger.warning("search collection rollback failed", exc_info=True)
        logger.warning(
            "search collection read failed; serving the ordinary answer", exc_info=True
        )
        degraded = bool(tokens)

    if not cards and not degraded:
        return payload
    result = {**payload}
    if cards:
        result["collections"] = cards
    if degraded:
        result["degraded"] = list(
            dict.fromkeys([*(payload.get("degraded") or []), "collections"])
        )
    return result


def _producer_search_terms(producer: Any) -> tuple[str, ...]:
    """Return the title, slug, kicker, and keyword strings a roundup producer is named by (#12376, Decide 31-A)."""
    terms: list[str] = []
    for attr in ("name", "slug", "kicker", "tag"):
        val = getattr(producer, attr, None)
        if isinstance(val, str) and val.strip():
            terms.append(val.strip())

    rule = getattr(producer, "rule", None)
    if isinstance(rule, dict):
        for key in (
            "title",
            "card_title",
            "headline",
            "kicker",
            "tag",
            "title_pattern",
            "question_prefix",
            "question_suffix",
            "team_name",
        ):
            val = rule.get(key)
            if isinstance(val, str) and val.strip():
                terms.append(val.strip())
        for list_key in ("keywords", "search_words", "team_aliases"):
            seq = rule.get(list_key)
            if isinstance(seq, (list, tuple)):
                for item in seq:
                    if isinstance(item, str) and item.strip():
                        terms.append(item.strip())
    return tuple(dict.fromkeys(terms))


def _matches(tokens: tuple[str, ...], values: Iterable[object]) -> bool:
    for value in values:
        words = container_discovery.collection_query_tokens(str(value or ""))
        if all(any(word.startswith(token) for word in words) for token in tokens):
            return True
    return False


async def _append_roundup_matches(
    db: Any, cards: list[dict], tokens: tuple[str, ...], *, sport_key: str | None = None
) -> bool:
    """Search the same licensed, cached sets their cards and pages already read."""
    from app.utils.container_presentation import container_destination
    from app.utils.roundup_containers import (
        ROUNDUP_PRODUCERS,
        evaluate_roundup_producer,
    )

    named = [
        producer
        for producer in ROUNDUP_PRODUCERS.values()
        if _matches(tokens, _producer_search_terms(producer))
    ]
    failed = False
    for producer in named:
        if len(cards) >= SEARCH_COLLECTIONS_CAP:
            return failed
        try:
            _feed_item, page = await evaluate_roundup_producer(producer, db)
        except Exception:  # noqa: BLE001 — one refused read cannot erase healthy sets
            failed = True
            logger.warning(
                "search roundup read failed for %s", producer.slug, exc_info=True
            )
            try:
                await db.rollback()
            except Exception:  # noqa: BLE001
                logger.warning("search roundup rollback failed", exc_info=True)
                return True
            continue
        if page is None or page.get("state") != "published":
            continue
        header = page.get("container") or {}
        values = [header.get("name"), *_producer_search_terms(producer)]
        member_ids = {"event": set(), "market": set()}
        for section in page.get("sections") or []:
            for member in section.get("members") or []:
                card = member.get("card") or {}
                member_type = member.get("type")
                if member_type in member_ids:
                    member_ids[member_type].add(member["id"])
                values.extend(
                    (
                        card.get("name"),
                        card.get("home_team_name"),
                        card.get("away_team_name"),
                    )
                )
                for side in ("home_team", "away_team"):
                    team = card.get(side)
                    if isinstance(team, dict):
                        values.append(team.get("name"))
                values.extend(
                    outcome.get("name") for outcome in card.get("outcomes") or []
                )
        if not _matches(tokens, values):
            continue
        if sport_key:
            sport_matches = await _roundup_matches_sport(db, page, sport_key)
            failed = failed or sport_matches is None
            if not sport_matches:
                continue
        games = len(member_ids["event"])
        markets = len(member_ids["market"])
        if games + markets == 0:
            continue
        cards.append(
            {
                "type": "collection",
                "id": header["id"],
                "slug": producer.slug,
                "name": header["name"],
                "text": header["name"],
                "state": "published",
                "revision": page["revision"],
                "game_count": games,
                "question_count": markets,
                "destination": container_destination(producer.slug),
            }
        )
    return failed


async def _roundup_matches_sport(db: Any, page: dict, sport_key: str) -> bool | None:
    """Apply the search's sport key to the set's canonical member rows."""
    from sqlalchemy import text

    ids = {"event": set(), "market": set()}
    for section in page.get("sections") or []:
        for member in section.get("members") or []:
            if member.get("type") in ids:
                ids[member["type"]].add(member["id"])
    try:
        scope_result = await db.execute(
            text(
                "SELECT EXISTS (SELECT 1 FROM events e JOIN sports s ON s.id = e.sport_id "
                "WHERE e.id = ANY(:event_ids) AND s.key = :sport_key) "
                "OR EXISTS (SELECT 1 FROM futures_markets f JOIN sports s ON s.id = f.sport_id "
                "WHERE f.id = ANY(:market_ids) AND s.key = :sport_key)"
            ),
            {
                "event_ids": sorted(ids["event"]),
                "market_ids": sorted(ids["market"]),
                "sport_key": sport_key,
            },
        )
    except Exception:  # noqa: BLE001 — an unavailable scope is explicitly degraded
        logger.warning(
            "search roundup sport read failed for %s", page.get("slug"), exc_info=True
        )
        await db.rollback()
        return None
    return bool(scope_result.scalar())


async def attach_typeahead_collections(db: Any, payload: dict) -> dict:
    """Attach live collection destinations after either typeahead cache exit."""
    suggestions = payload.get("suggestions") or []
    lookup = await attach_search_collections(
        db,
        {
            "query": payload.get("query"),
            "results": [
                {"id": row["event_id"]} for row in suggestions if row.get("event_id")
            ],
        },
        titles_only=True,
    )
    cards = lookup.get("collections") or []
    if not cards and not lookup.get("degraded"):
        return payload
    result = {**payload}
    if cards:
        result["collections"] = cards
    if lookup.get("degraded"):
        result["degraded"] = list(
            dict.fromkeys([*(payload.get("degraded") or []), *lookup["degraded"]])
        )
    return result
