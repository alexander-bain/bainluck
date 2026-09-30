"""Which published collections a reader can be offered, and the card each one is. #9653 (v3, #9217).

**SHIP: a reader finds the right NFL week or MLB postseason hub from Search,
Browse and Discover, and every entry opens the same hub.** (Pillar: MATCHING /
DISCOVER.)

This is the bounded PRODUCER those three entry points share. It answers one
question — "of these collections, which may a reader be offered, and what is
the card?" — and nothing else. It does not rank, does not reserve a slot, and
does not decide membership. Where a card goes, and whether it goes anywhere, is
the consuming route's existing ranking (the Discover placement is
relevance-based, never a mandatory slot: #9653's acceptance).

ONE IDENTITY, ONE DESTINATION. The card reuses #9636's edition identity
(``edition_for_slug`` — the adapters' own slug builders, round-tripped) and its
destination (``container_destination``), so an entry from Search and an entry
from Discover cannot name two different hubs, and the hub they open
(``GET /api/containers/{slug}``) describes the same revision the card was cut
from.

ELIGIBLE MEANS ALL OF THESE, AND FAILS CLOSED ON EACH:

* both switches are on — this producer's own ``CONTAINER_DISCOVERY_ENABLED``
  and the hub's ``CONTAINERS_READ_ENABLED``; a card whose hub serves 404 is a
  dead link, so the hub switch gates discovery too;
* #9651's publication schema is present (an un-migrated database offers
  nothing, and says why);
* ``publication_state = 'published'`` exactly — ``unpublished``, ``withdrawn``
  and any state this code has never heard of are not permission;
* a ROOT collection (no parent): an entry lands on the hub, never inside it;
* an edition the adapters would write byte for byte, of a kind this ship
  offers (``nfl_week``, ``mlb_postseason``), and inside the caller's
  league/season filter when one is given — anything else is ``wrong_edition``;
* at least one member whose row we still hold — an empty hub is not a
  destination (#2215: an empty page reads, from outside, as "nothing on").

The SQL applies these so ineligible rows cannot consume the bound, AND the pure
half (``collection_card``) re-applies every one to every returned row, so a
query that drifted can only ever offer fewer collections, never a wrong one.

BOUNDED. Two statements whatever the inputs: the schema probe and one
aggregate read. Inputs are capped (``MAX_EVENT_IDS``, ``MAX_SLUGS``,
``MAX_COLLECTIONS``) and truncation is reported, never silent.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Iterable, Optional

from sqlalchemy import text

from app.utils.container_corrections import (
    PUBLICATION_COLUMN,
    READ_PUBLISHED,
    REVISION_COLUMN,
    correction_schema_present,
)
from app.utils.container_presentation import (
    EDITION_MLB_POSTSEASON,
    EDITION_NFL_WEEK,
    container_destination,
    edition_for_slug,
)

logger = logging.getLogger(__name__)

#: The card's ``type``. Search results and feed items both key on ``type``, so
#: a consumer that does not know this value skips it exactly as it skips any
#: other type it does not render — released clients are untouched.
CARD_TYPE = "collection"

#: The editions this ship offers. ``nfl_season`` has an identity but no hub a
#: reader was promised; it is ``wrong_edition`` here until a ship names it.
DISCOVERABLE_EDITIONS = frozenset({EDITION_NFL_WEEK, EDITION_MLB_POSTSEASON})

#: League filter → the slug prefix both SQL and the pure check agree on.
LEAGUE_SLUG_PREFIXES = {"nfl": "nfl-", "mlb": "mlb-"}

#: The only slug shapes the two discoverable adapters write — the week is an
#: int >= 1 formatted bare, so no leading zero (``week-09`` is not ours and, on
#: real Postgres, took the only LIMIT slot before this said so). A pre-filter so
#: a wrong-shaped slug cannot consume the LIMIT; ``edition_for_slug`` remains
#: the authority and re-checks every row.
DISCOVERABLE_SLUG_PATTERN = (
    r"^(nfl-[0-9]{4}-(preseason-|postseason-)?week-[1-9][0-9]?|mlb-[0-9]{4}-postseason)$"
)

MAX_COLLECTIONS = 20
MAX_EVENT_IDS = 500
MAX_SLUGS = 50

#: Why a row the read returned is not offered. Diagnostic only — never rendered.
EXCLUDED_NOT_PUBLISHED = "not_published"
EXCLUDED_NESTED = "nested_collection"
EXCLUDED_WRONG_EDITION = "wrong_edition"
EXCLUDED_EMPTY = "empty"
EXCLUDED_NOT_MATCHED = "no_matching_member"

REASON_DISABLED = "discovery_disabled"
REASON_HUB_DISABLED = "hub_read_disabled"
REASON_SCHEMA_ABSENT = "publication_schema_absent"


def container_discovery_enabled() -> bool:
    """Read at call time, like the hub's own switch, so it flips without a restart."""
    return os.getenv("CONTAINER_DISCOVERY_ENABLED", "false").lower() == "true"


def _hub_read_enabled() -> bool:
    # The hub's switch, read through the hub's own function so the two can
    # never name different env vars. Imported late: services must not pull a
    # router in at import time.
    from app.routes.containers import containers_read_enabled

    return containers_read_enabled()


@dataclass
class DiscoveryRead:
    """What one call produced. ``collections`` is the only field a reader sees."""

    collections: list = field(default_factory=list)
    #: Set when nothing could be offered for a reason other than "none matched".
    reason: Optional[str] = None
    excluded: dict = field(default_factory=dict)
    truncated: dict = field(default_factory=dict)


def _capped(values: Optional[Iterable], cap: int, name: str, truncated: dict, cast) -> Optional[list]:
    if values is None:
        return None
    cleaned = sorted({cast(v) for v in values if v is not None})
    if len(cleaned) > cap:
        truncated[name] = len(cleaned)
        cleaned = cleaned[:cap]
    return cleaned


def collection_card(
    row: dict,
    *,
    league: Optional[str] = None,
    season: Optional[int] = None,
    matched_required: bool = False,
) -> tuple[Optional[dict], Optional[str]]:
    """``(card, None)`` for an eligible row, ``(None, excluded_reason)`` otherwise.

    Pure. ``row`` is one row of the aggregate read as a dict (the keys the SQL
    selects). Every eligibility rule is re-applied here; see the module
    docstring for why the SQL applying them too is not enough.
    """
    if row.get("publication_state") != READ_PUBLISHED:
        return None, EXCLUDED_NOT_PUBLISHED
    if row.get("parent_container_id") is not None:
        return None, EXCLUDED_NESTED

    slug = row.get("slug")
    edition = edition_for_slug(slug)
    if edition is None or edition.get("kind") not in DISCOVERABLE_EDITIONS:
        return None, EXCLUDED_WRONG_EDITION
    if league is not None and edition.get("league") != league:
        return None, EXCLUDED_WRONG_EDITION
    if season is not None and edition.get("season") != season:
        return None, EXCLUDED_WRONG_EDITION

    game_count = int(row.get("game_count") or 0)
    question_count = int(row.get("question_count") or 0)
    if game_count + question_count == 0:
        return None, EXCLUDED_EMPTY

    matched = sorted(int(i) for i in (row.get("matched_event_ids") or ()))
    if matched_required and not matched:
        return None, EXCLUDED_NOT_MATCHED

    window_start, window_end = row.get("window_start"), row.get("window_end")
    card = {
        "type": CARD_TYPE,
        # ``text`` is the field every search result is labelled by.
        "text": row.get("name"),
        "id": int(row["id"]),
        "slug": slug,
        "name": row.get("name"),
        "state": READ_PUBLISHED,
        "revision": int(row["revision"]) if row.get("revision") is not None else None,
        "edition": edition,
        "status": row.get("status"),
        "window_start": window_start.isoformat() if window_start is not None else None,
        "window_end": window_end.isoformat() if window_end is not None else None,
        # Members whose row we still hold. The hub can show fewer only by
        # withholding one it could not draw, and it then says so with a reason.
        "game_count": game_count,
        "question_count": question_count,
        # The caller's games this hub contains — the relevance evidence, read
        # off membership by id. Empty when the caller passed no games.
        "matched_event_ids": matched,
        "destination": container_destination(slug),
    }
    return card, None


def _discovery_sql(*, by_slug: bool, by_prefix: bool, by_season: bool, by_events: bool) -> str:
    """One aggregate statement. Filters are composed from fixed fragments only;
    every value is a bind parameter (gotcha #45)."""
    hub_filters = [
        f"c.{PUBLICATION_COLUMN} = 'published'",
        "c.parent_container_id IS NULL",
        "c.slug ~ :slug_pattern",
    ]
    if by_slug:
        hub_filters.append("c.slug = ANY(:slugs)")
    if by_prefix:
        hub_filters.append("starts_with(c.slug, :slug_prefix)")
    if by_season:
        # Both discoverable slug shapes carry the season as their second token.
        hub_filters.append("split_part(c.slug, '-', 2) = :season_token")
    matched = (
        "COALESCE(array_agg(DISTINCT m.child_id) FILTER ("
        "  WHERE m.child_type = 'event' AND ev.id IS NOT NULL "
        "    AND m.child_id = ANY(:event_ids)), '{}')"
        if by_events
        else "'{}'::bigint[]"
    )
    having = [
        "COUNT(DISTINCT ev.id) + COUNT(DISTINCT fm.id) > 0",
    ]
    if by_events:
        having.append(
            "bool_or(m.child_type = 'event' AND ev.id IS NOT NULL "
            "AND m.child_id = ANY(:event_ids))"
        )
    return (
        "WITH hub AS ("
        "  SELECT c.id, c.name, c.slug, c.status, c.window_start, c.window_end, "
        f"         c.parent_container_id, c.{PUBLICATION_COLUMN} AS publication_state, "
        f"         c.{REVISION_COLUMN} AS revision "
        "  FROM containers c "
        f"  WHERE {' AND '.join(hub_filters)}"
        "), parts AS ("
        "  SELECT hub.id AS part_id, hub.id AS hub_id FROM hub "
        "  UNION ALL "
        "  SELECT c.id, hub.id FROM containers c JOIN hub ON c.parent_container_id = hub.id "
        f"  WHERE c.{PUBLICATION_COLUMN} <> 'withdrawn'"
        "), m AS ("
        "  SELECT DISTINCT parts.hub_id, e.child_type, e.child_id "
        "  FROM parts JOIN event_edges e "
        "    ON e.kind = 'contains' AND e.parent_type = 'container' "
        "   AND e.parent_id = parts.part_id "
        "  WHERE e.child_type IN ('event', 'market')"
        ") "
        "SELECT hub.id, hub.name, hub.slug, hub.status, hub.window_start, hub.window_end, "
        "       hub.parent_container_id, hub.publication_state, hub.revision, "
        "       COUNT(DISTINCT ev.id) AS game_count, "
        "       COUNT(DISTINCT fm.id) AS question_count, "
        f"      {matched} AS matched_event_ids "
        "FROM hub "
        "LEFT JOIN m ON m.hub_id = hub.id "
        "LEFT JOIN events ev ON m.child_type = 'event' AND ev.id = m.child_id "
        "LEFT JOIN futures_markets fm ON m.child_type = 'market' AND fm.id = m.child_id "
        "GROUP BY hub.id, hub.name, hub.slug, hub.status, hub.window_start, hub.window_end, "
        "         hub.parent_container_id, hub.publication_state, hub.revision "
        f"HAVING {' AND '.join(having)} "
        "ORDER BY cardinality("
        f"{matched}) DESC, hub.window_start DESC NULLS LAST, hub.id "
        "LIMIT :limit"
    )


_COLUMNS = (
    "id", "name", "slug", "status", "window_start", "window_end",
    "parent_container_id", "publication_state", "revision",
    "game_count", "question_count", "matched_event_ids",
)


async def discover_collections(
    session,
    *,
    event_ids: Optional[Iterable[int]] = None,
    slugs: Optional[Iterable[str]] = None,
    league: Optional[str] = None,
    season: Optional[int] = None,
    limit: int = MAX_COLLECTIONS,
) -> DiscoveryRead:
    """The collections a reader may be offered, as cards. Two statements, always.

    * ``event_ids`` — the games a consumer is already showing (a search
      page, a feed page). Only collections containing at least one of them are
      returned, most-matched first; ``matched_event_ids`` names which. This is
      how Search and Discover stay relevance-based: no games, no card.
    * ``slugs`` — exact collections (a Browse list, a deep link).
    * ``league`` (``"nfl"``/``"mlb"``) / ``season`` — Browse's filter.

    With none of them, the most recent eligible collections are returned
    (Browse's "all collections" list), still bounded by ``limit``.
    """
    read = DiscoveryRead()
    if not container_discovery_enabled():
        read.reason = REASON_DISABLED
        return read
    if not _hub_read_enabled():
        read.reason = REASON_HUB_DISABLED
        return read
    if league is not None and league not in LEAGUE_SLUG_PREFIXES:
        read.excluded[EXCLUDED_WRONG_EDITION] = 1
        return read

    limit = max(1, min(int(limit), MAX_COLLECTIONS))
    events = _capped(event_ids, MAX_EVENT_IDS, "event_ids", read.truncated, int)
    slug_list = _capped(slugs, MAX_SLUGS, "slugs", read.truncated, str)
    # An explicit empty list is "nothing to look for", not "no filter".
    if (events is not None and not events) or (slug_list is not None and not slug_list):
        return read

    schema = await correction_schema_present(session)
    if not schema.columns:
        read.reason = REASON_SCHEMA_ABSENT
        return read

    params: dict = {"slug_pattern": DISCOVERABLE_SLUG_PATTERN, "limit": limit}
    if slug_list is not None:
        params["slugs"] = slug_list
    if league is not None:
        params["slug_prefix"] = LEAGUE_SLUG_PREFIXES[league]
    if season is not None:
        params["season_token"] = str(int(season))
    if events is not None:
        params["event_ids"] = events
    sql = _discovery_sql(
        by_slug=slug_list is not None,
        by_prefix=league is not None,
        by_season=season is not None,
        by_events=events is not None,
    )
    rows = (await session.execute(text(sql), params)).fetchall()

    for raw in rows:
        row = dict(zip(_COLUMNS, raw))
        card, excluded = collection_card(
            row, league=league, season=season, matched_required=events is not None
        )
        if card is None:
            read.excluded[excluded] = read.excluded.get(excluded, 0) + 1
            logger.warning(
                "container discovery: SQL returned %s, which the pure check refused (%s)",
                row.get("slug"), excluded,
            )
            continue
        read.collections.append(card)
    return read
