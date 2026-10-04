"""How a published collection's members are presented to a reader. #9636 (v3, #9217).

**SHIP: an NFL week or the MLB postseason opens as the same game and question
cards a reader already knows, each one tapping through to a page that exists —
never an id, never a dead link, never a card we made up.** (Pillar: MATCHING /
FORMATTING / TRUTH.)

This is the pure half of ``GET /api/containers/{slug}``. The route reads the
published membership (``container_corrections.read_published`` — one statement,
so one revision), batch-loads the card for every member through the SAME
serializers the events list and search already serve, and hands the cards here.
No database, no network, no clock: every rule below is gradeable from a fixture.

WHAT IT DECIDES, EXHAUSTIVELY.

1. **Edition identity** — which NFL week, NFL season or MLB postseason a slug
   names, or (#9935) which theme collection. Read by round-tripping the slug
   through the adapters' OWN slug builders (the theme registry's for a theme),
   so the identity can never disagree with the slug assembly wrote. Any other
   slug has no edition (``None``), never a nearest guess.
2. **Destinations** — the web page and API path a member card (or a nested
   collection) taps through to.
   Only for a member whose row we actually hold; a member without a card has no
   destination, so it cannot become a broken link.
3. **Sections** — members grouped by the class assembly stored on their edge
   (the route's ``order_classes`` orders them), games in kickoff order, and
   every member we could not present WITHHELD WITH A REASON rather than dropped
   (gotcha #53: an absent card and a missing member are different facts).
4. **Related questions** — each game card lists the member questions whose
   market is linked to that game. Read off membership and ``event_id``; never a
   name match.

WHAT IT DELIBERATELY DOES NOT DO. It does not decide membership (assembly did),
does not classify (the edge carries the class), and does not re-derive a game's
state (the event card already carries ``served_event_status``).
"""

from __future__ import annotations

import re
from typing import Callable, Iterable, Mapping, Optional

from app.utils.container_mlb_playoffs import MlbPostseason
from app.utils.container_nfl import (
    STAGE_POSTSEASON,
    STAGE_PRESEASON,
    STAGE_REGULAR,
    NflWeek,
)
from app.utils.theme_definitions import parse_theme_slug

EDITION_NFL_WEEK = "nfl_week"
EDITION_NFL_SEASON = "nfl_season"
EDITION_MLB_POSTSEASON = "mlb_postseason"

#: Why a member of a published collection is not shown as a card.
WITHHELD_ROW_MISSING = "row_missing"  # the edge names a row we no longer hold
WITHHELD_UNSERIALIZABLE = "unserializable"  # the card serializer raised
WITHHELD_UNKNOWN_TYPE = "unknown_member_type"  # a node type this reader cannot draw

MEMBER_EVENT = "event"
MEMBER_MARKET = "market"

_NFL_WEEK_RE = re.compile(r"^nfl-(\d{4})-(?:preseason-|postseason-)?week-(\d{1,2})$")
_NFL_SEASON_RE = re.compile(r"^nfl-(\d{4})$")
_MLB_POSTSEASON_RE = re.compile(r"^mlb-(\d{4})-postseason$")


def edition_for_slug(slug: str) -> Optional[dict]:
    """The edition a collection slug names, or None. Exact, never fuzzy.

    The regex only proposes numbers; the adapter's own slug builder has to
    reproduce the slug byte for byte before an identity is returned, so a slug
    the adapters would never write (``nfl-2026-week-04``, an unknown stage) has
    no edition.
    """
    if not isinstance(slug, str):
        return None

    match = _NFL_WEEK_RE.match(slug)
    if match:
        season, week = int(match.group(1)), int(match.group(2))
        for stage in (STAGE_REGULAR, STAGE_PRESEASON, STAGE_POSTSEASON):
            try:
                if NflWeek(season=season, week=week, stage=stage).slug == slug:
                    return {
                        "kind": EDITION_NFL_WEEK,
                        "league": "nfl",
                        "season": season,
                        "stage": stage,
                        "week": week,
                    }
            except ValueError:
                return None
        return None

    match = _NFL_SEASON_RE.match(slug)
    if match:
        return {"kind": EDITION_NFL_SEASON, "league": "nfl", "season": int(match.group(1))}

    match = _MLB_POSTSEASON_RE.match(slug)
    if match:
        season = int(match.group(1))
        try:
            if MlbPostseason(season=season).slug == slug:
                return {"kind": EDITION_MLB_POSTSEASON, "league": "mlb", "season": season}
        except ValueError:
            return None
        return None

    # #9935: a theme collection, AFTER the sports branches so no NFL/MLB slug's
    # answer can change. ``{"kind": "theme_edition", "subject", "edition"}`` or
    # ``{"kind": "theme_continuing", "subject"}``; the registry's own builder
    # has to reproduce the slug, so ``oscars-27`` and ``ai-2026`` are None.
    return parse_theme_slug(slug)


def event_destination(event_id: int) -> dict:
    """The game page. The web route is ``frontend/app/events/[id]``."""
    return {"kind": MEMBER_EVENT, "id": int(event_id), "web": f"/events/{int(event_id)}",
            "api": f"/api/events/{int(event_id)}"}


def market_destination(market_id: int) -> dict:
    """The question page. The web route is ``frontend/app/futures/[id]``."""
    return {"kind": MEMBER_MARKET, "id": int(market_id), "web": f"/futures/{int(market_id)}",
            "api": f"/api/futures/{int(market_id)}"}


def container_destination(slug: str) -> dict:
    """A collection hub. The web route is ``frontend/app/collections/[slug]``
    (#9886). Search's collection card and a hub's nested children both read
    this, so every entry to one collection lands on the same page."""
    return {"kind": "container", "slug": slug, "web": f"/collections/{slug}",
            "api": f"/api/containers/{slug}"}


def _kickoff_key(entry: dict) -> tuple:
    """Games by kickoff, then id; anything without a kickoff after, by id.

    ISO-8601 strings from one serializer sort as their instants do; a card
    without ``commence_time`` sorts last rather than raising.
    """
    card = entry.get("card") or {}
    kickoff = card.get("commence_time")
    return (0, kickoff, entry["id"]) if isinstance(kickoff, str) else (1, "", entry["id"])


def present_sections(
    members: Iterable[dict],
    *,
    event_cards: Mapping[int, dict],
    market_cards: Mapping[int, dict],
    market_event_ids: Mapping[int, Optional[int]],
    failed: Mapping[tuple, str],
    order_classes: Callable[[set], list],
    unclassified: str,
) -> tuple[list, list]:
    """``(sections, withheld)`` for one published read.

    ``members`` is ``PublishedRead.members`` verbatim. ``event_cards`` /
    ``market_cards`` hold the serialized card for every row that loaded;
    ``failed`` names the ``(type, id)`` whose serializer raised. A member with
    no card is withheld with its reason and never reaches a section, so the
    counts a reader sees are the cards a reader can open.
    """
    # Questions per game, from membership only. A market that is a member AND
    # is linked to a member game is that game's related question.
    member_markets = [m for m in members if m.get("type") == MEMBER_MARKET]
    related: dict[int, list] = {}
    for m in member_markets:
        market_id = int(m["id"])
        if market_id not in market_cards:
            continue
        event_id = market_event_ids.get(market_id)
        if event_id is not None:
            related.setdefault(int(event_id), []).append(market_id)

    by_class: dict[str, list] = {}
    withheld: list = []
    seen: set = set()
    for m in members:
        member_type, member_id = m.get("type"), int(m["id"])
        key = (member_type, member_id)
        # A draw and its parent can both hold one member; the reader sees it once
        # (the first, i.e. lowest class/child order the read returned).
        if key in seen:
            continue
        seen.add(key)

        if member_type == MEMBER_EVENT:
            card = event_cards.get(member_id)
            destination = event_destination(member_id) if card is not None else None
        elif member_type == MEMBER_MARKET:
            card = market_cards.get(member_id)
            destination = market_destination(member_id) if card is not None else None
        else:
            withheld.append({"type": member_type, "id": member_id, "reason": WITHHELD_UNKNOWN_TYPE})
            continue

        if card is None:
            reason = failed.get(key, WITHHELD_ROW_MISSING)
            withheld.append({"type": member_type, "id": member_id, "reason": reason})
            continue

        entry = {
            "type": member_type,
            "id": member_id,
            "container_id": m.get("container_id"),
            "source": m.get("source"),
            "confidence": m.get("confidence"),
            "destination": destination,
            "card": card,
        }
        if member_type == MEMBER_EVENT:
            entry["question_ids"] = sorted(related.get(member_id, []))
        else:
            event_id = market_event_ids.get(member_id)
            entry["event_id"] = int(event_id) if event_id is not None else None
        by_class.setdefault(m.get("class") or unclassified, []).append(entry)

    sections = []
    for member_class in order_classes(set(by_class)):
        entries = by_class[member_class]
        games = sorted((e for e in entries if e["type"] == MEMBER_EVENT), key=_kickoff_key)
        questions = [e for e in entries if e["type"] != MEMBER_EVENT]
        ordered = games + questions
        sections.append({"class": member_class, "count": len(ordered), "members": ordered})
    return sections, withheld
