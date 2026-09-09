"""Serve-time fold for twin event rows — one game, one card (#4100).

WHAT THIS IS FOR. Alex, on `/sports` at phone width 2026-09-08: page one carried
two adjacent MLB cards for the SAME game — "St. Louis Cardinals 24% / San
Francisco Giants 76%, 0-2, Top 6th" and, five cards later, "St.Louis Cardinals
38% / San Francisco Giants 62%" with no score at all. Two cards, one game, two
different numbers, and the team's own name spelled two ways.

WHY THE ROWS EXIST, AND WHY THIS IS NOT THE MATCHER'S REPAIR. They are two
`events` rows, each minted by a different authority and each anchored to that
authority's own game id — measured on production 2026-09-09 01:xxZ:

    15307210  odds_api:c8513bd1…   espn_id set   betting, espn, mlb, stat_model
    15300848  statpal:baseball_mlb:364…          kalshi, mlb

Ruling 048 (gotcha #32) is why they never merged and why they MUST not be merged
by name and time in the registry: an id-less claim never absorbs, and absorption
needs a SHARED provider id. Neither row shares one — each carries a `game` anchor
from a provider the other has never heard of — so `event_provider_anchors` has
nothing to join on and both rows are, structurally, correct. Loosening absorption
was put to Alex on 2026-08-20 and REJECTED.

So this module does not touch the registry, the matcher, or a single row. It is a
SERVE-TIME fold: the reader's page shows the fixture once, and the surviving card
carries the union of both rows' venues so the number on it is the blend Alex's
standing ruling asks for. The duplicate rows stay in the database exactly as they
are — visible to the Grid and Flow sentinels, to `audit_event_matching.py`, and
to whatever eventually lands #2693 / #4100. Hiding a card is not fixing a bug and
this file does not claim to; it stops the bug reaching a reader while the durable
repair is built.

THE KEY IS DELIBERATELY STRICTER THAN A MATCHER'S. `(sport_id, normalised away,
normalised home, commence MINUTE)`. Two distinct fixtures cannot share it: an MLB
doubleheader is the same teams on the same DAY but never the same minute, and two
different matches between one pair of players at one instant do not exist. A
matcher's helper is permissive on purpose — wrong here — so the key is built from
`strip_diacritics` and an alphanumeric squash rather than from
`normalize_team_name_for_matching`.

WHY NEITHER EXISTING NORMALISER WOULD HAVE FOLDED THE CARD ALEX SAW.
`normalize_team_name` strips a period only when a space follows it
(`re.sub(r"\\.(?=\\s)", …)`), so "St.Louis Cardinals" keeps its period and does
not equal "st louis cardinals". `match_key` keeps spaces, so it yields
"stlouis cardinals" against "st louis cardinals". Both leave the twin unfolded.
The squash below removes every non-alphanumeric character, spaces included, and
both spellings land on `stlouiscardinals`.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional

from app.utils.name_normalization import strip_diacritics

logger = logging.getLogger(__name__)

__all__ = [
    "FoldResult",
    "fold_twin_events",
    "twin_fold_key",
    "twin_identity_rank",
]

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def _squash(name: Optional[str]) -> str:
    """Alphanumeric-only, lowercase, diacritic-free form of a team name.

    "St. Louis Cardinals" and "St.Louis Cardinals" both become
    "stlouiscardinals"; "Atlético Madrid" becomes "atleticomadrid".
    """
    if not name:
        return ""
    return _NON_ALNUM.sub("", strip_diacritics(name).lower())


def twin_fold_key(event: Any) -> Optional[tuple]:
    """The key two rows must share to be the same fixture, or ``None``.

    ``None`` means "never fold this row" — a row missing a team name or a
    commence time cannot be proven to be anybody's twin, and the fold's whole
    licence is that the key admits no false positives.
    """
    home = _squash(getattr(event, "home_team_name", None))
    away = _squash(getattr(event, "away_team_name", None))
    commence = getattr(event, "commence_time", None)
    sport_id = getattr(event, "sport_id", None)
    if not home or not away or commence is None or sport_id is None:
        return None
    return (sport_id, away, home, commence.replace(second=0, microsecond=0))


def _source_count(event: Any) -> int:
    sources = getattr(event, "win_probability_sources", None)
    return len(sources) if sources else 0


def twin_identity_rank(event: Any) -> tuple:
    """Sort key for electing the survivor among twins — biggest wins.

    Ordered by what a reader loses if the other row is the one served, NOT by
    row richness. lane1/197 measured that richness points the wrong way in 2 of
    5 pairs, and gotcha "the emptier row heuristic is backwards for Kalshi
    ghosts" is the same lesson from the other side. What does not flip:

    1. **A visible score.** The card Alex saw twice differed in exactly this —
       one said "0-2, Top 6th", the other showed a live game with no score at
       all. Serving the scoreless row would be a worse page than serving two.
    2. **An ESPN id**, then **any provider id**. An anchored row is the one the
       event page, the chart and the settlement path can all reach.
    3. Only then source count, and finally the lower row id, so the election is
       deterministic across requests and the served `id` does not flicker
       between two polls.
    """
    home_score = getattr(event, "home_score", None)
    away_score = getattr(event, "away_score", None)
    has_score = home_score is not None or away_score is not None
    return (
        1 if has_score else 0,
        1 if getattr(event, "espn_id", None) else 0,
        1 if getattr(event, "external_id", None) else 0,
        _source_count(event),
        -(getattr(event, "id", 0) or 0),
    )


@dataclass
class FoldResult:
    """What the fold decided, in a shape a caller can act on and log."""

    events: list = field(default_factory=list)
    """The surviving rows, in the order they arrived."""

    merged_sources: dict = field(default_factory=dict)
    """``{survivor_id: unioned win_probability_sources}`` — survivors only, and
    only where a fold actually added a venue."""

    dropped_ids: list = field(default_factory=list)
    """Row ids the fold removed, for the log line and the guard tests."""

    @property
    def folded_count(self) -> int:
        return len(self.dropped_ids)


def fold_twin_events(events: Iterable[Any]) -> FoldResult:
    """Collapse same-fixture rows to one, unioning their venues.

    The union is ADDITIVE ONLY: a source the survivor already reports is never
    overwritten by a twin's reading of it. The survivor's own numbers are the
    ones the rest of the pipeline already trusts; the fold adds the venues that
    were stranded on the other row and nothing else. Draining the other
    direction — electing a winner and discarding the loser's sources — deletes a
    whole venue's price for that game, which is what the "blend is the product"
    ruling forbids.
    """
    ordered = list(events)
    groups: dict[tuple, list] = {}
    unkeyed: list = []

    # Gotcha #42 — one bad item must never wipe a scoring pass. This runs on the
    # `/api/feed` hot path above every other stage, so a single row with a
    # surprising `commence_time` type must cost that row its fold, not the whole
    # page. A row that cannot be keyed is a row that cannot be proven a twin,
    # which is already the "leave it alone" branch.
    for event in ordered:
        try:
            key = twin_fold_key(event)
        except Exception:  # noqa: BLE001 — see above; the fallback is inaction
            logger.warning(
                "twin fold: could not key event %s; left unfolded",
                getattr(event, "id", "?"),
                exc_info=True,
            )
            key = None
        if key is None:
            unkeyed.append(event)
            continue
        groups.setdefault(key, []).append(event)

    # Keyed on the PYTHON object, not on `.id`: the fold must survive a caller
    # that hands it two hydrated rows carrying the same primary key, and must
    # never keep a row merely because a sibling elected the same id.
    keep: set[int] = {id(e) for e in unkeyed}
    result = FoldResult()

    for members in groups.values():
        if len(members) == 1:
            keep.add(id(members[0]))
            continue

        try:
            _elect(members, keep, result)
        except Exception:  # noqa: BLE001 — one group's failure keeps its rows
            logger.warning(
                "twin fold: election failed for %s; all rows kept",
                [getattr(m, "id", "?") for m in members],
                exc_info=True,
            )
            for member in members:
                keep.add(id(member))

    result.events = [e for e in ordered if id(e) in keep]
    return result


def _elect(members: list, keep: set, result: "FoldResult") -> None:
    """Pick the survivor for one group and union the losers' venues onto it."""
    ranked = sorted(members, key=twin_identity_rank, reverse=True)
    survivor, losers = ranked[0], ranked[1:]
    keep.add(id(survivor))
    result.dropped_ids.extend(loser.id for loser in losers)

    merged = dict(getattr(survivor, "win_probability_sources", None) or {})
    added = False
    for loser in losers:
        for name, reading in (
            getattr(loser, "win_probability_sources", None) or {}
        ).items():
            if name not in merged:
                merged[name] = reading
                added = True
    if added:
        result.merged_sources[survivor.id] = merged
