"""#9482 — a game ESPN has matched prints ESPN's spelling of the club.

THE SHIP: the NHL page spells the Canadiens and the Blues one way. On
production 2026-09-28 Tuesday's Maple Leafs game read ``Montreal Canadiens``
while the Oct 3 Penguins and Oct 6 Hurricanes games read ``Montréal Canadiens``;
``St. Louis Blues`` and ``St Louis Blues`` sat on different cards the same way.
Every card prints its own row's ``home_team_name`` / ``away_team_name``.

WHY THE WRONG SPELLING NEVER LEAVES
-----------------------------------

The Odds API minted those games in July with its own spellings. Every later
claim asks ``_update_fields_by_priority`` whether it may rewrite the names, and
that test reads the row's ``commence_time_source`` as the names' provenance. The
ESPN passes stamp ``commence_time_source = 'espn'`` when they correct or confirm
a start — and write no names. From then on ESPN and StatPal both read as parity
or lower, so the Odds API spelling is permanent (15169778: ``espn`` time source,
ESPN id 401891822, StatPal fixture 652890, still ``Montréal Canadiens``).
``upsert_team`` then resolves the side BY that name, so the game also stays bound
to the spelling's own team row (3706 / 3705) rather than ESPN's (568 / 571).

WHAT THIS DOES
--------------

When an ESPN pass has matched a row, each side whose stored name differs from
ESPN's ``displayName`` ONLY by accents and punctuation (``team_name_fold_key``,
the fold the search card and team page already read these rows as one club by)
takes ESPN's spelling — provided a team row in the event's sport ALREADY carries
exactly that name AND ESPN's team id. Three consequences:

* It never names a different club: fold-equal names are the same letters.
* It never mints: ``upsert_team`` resolves ESPN's spelling by exact name to that
  id-anchored row, and the existing #1918 binding guard moves the side onto it.
* It never touches a side whose fold differs (``LA Clippers`` vs ``Los Angeles
  Clippers``) or a reversed pairing (the home fold would name the other club).

AND IT NEVER MOVES A SIDE ONTO A STALER ROW. The card serves slug, record and
standings from the BOUND team row, and StatPal's standings writer keeps whichever
row carries ITS spelling: 568 ``Montreal Canadiens`` (written 2026-09-29) but
3705 ``St Louis Blues`` (written 2026-09-29) — while ESPN's ``St. Louis Blues``
row 571 was last written in May. So ESPN's row must also be at least as fresh as
the row the side is bound to (#9229's tie-break, ``standings_updated_at``). The
Canadiens move; the Blues hold, rather than trade a spelling for a May record.
The check only ever blocks a move toward ESPN's spelling, so it cannot flap.

Measured 2026-09-29: four spelling-only same-ESPN-id team pairs site-wide
(Blues, Canadiens, AFL Gold Coast Suns, NCAA baseball UT Arlington); only the
two NHL clubs have scheduled games (6 rows).
"""

from __future__ import annotations

import logging
from typing import Mapping, Optional

from app.utils.event_twin_fold import team_name_fold_key

logger = logging.getLogger(__name__)


def _standings_stamp(team) -> float:
    stamp = getattr(team, "standings_updated_at", None) if team is not None else None
    return stamp.timestamp() if stamp is not None else float("-inf")


def espn_respelling(
    stored_name: Optional[str],
    espn_team,
    sport_id,
    team_cache: Mapping,
    bound_team_id=None,
) -> Optional[str]:
    """ESPN's spelling of this side, or ``None`` when the row keeps its own.

    ``team_cache`` is the pass's full-sport ``{(name, sport_id): Team}`` map;
    ``bound_team_id`` is the side's current ``<side>_team_id``.
    Pure: reads the cache, writes nothing.
    """
    if not stored_name or espn_team is None:
        return None
    espn_name = getattr(espn_team, "display_name", None)
    espn_id = getattr(espn_team, "espn_id", None)
    if not espn_name or not espn_id or espn_name == stored_name:
        return None
    fold = team_name_fold_key(stored_name)
    if not fold or fold != team_name_fold_key(espn_name):
        return None
    canonical = team_cache.get((espn_name, sport_id))
    if canonical is None or str(getattr(canonical, "espn_id", None) or "") != str(espn_id):
        return None
    if bound_team_id is not None and bound_team_id != getattr(canonical, "id", None):
        bound = next(
            (t for t in team_cache.values() if getattr(t, "id", None) == bound_team_id),
            None,
        )
        if _standings_stamp(canonical) < _standings_stamp(bound):
            return None
    return espn_name


def apply_espn_respelling(event, ee, team_cache: Mapping, stats: dict, *, source: str) -> int:
    """Write ESPN's spelling onto each side :func:`espn_respelling` allows.

    Call BEFORE ``upsert_team`` so the side resolves to the id-anchored row.
    Returns the number of sides rewritten.
    """
    written = 0
    for side, espn_team in (("home", getattr(ee, "home_team", None)),
                            ("away", getattr(ee, "away_team", None))):
        column = f"{side}_team_name"
        stored = getattr(event, column, None)
        respelled = espn_respelling(
            stored, espn_team, event.sport_id, team_cache,
            bound_team_id=getattr(event, f"{side}_team_id", None),
        )
        if respelled is None:
            continue
        setattr(event, column, respelled)
        written += 1
        logger.info(
            "ESPN (%s): event %s %s side %r -> ESPN's spelling %r (#9482)",
            source, getattr(event, "id", None), side, stored, respelled,
        )
    if written:
        key = f"{source}_team_name_respelled"
        stats[key] = stats.get(key, 0) + written
    return written
