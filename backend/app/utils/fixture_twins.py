"""One fixture, one row on the page — the display half of ruling 048's price.

#2623. Searching `Sabalenka` on 2026-09-01 returned "26 results · 16 games ·
10 markets", and those 16 games were **9 real matches, each listed twice**:

    15206893  Aryna Sabalenka vs Sara Bejlek   08-20 00:30  completed  0-2  odds_api
    15300722  Sabalenka vs Bejlek              08-20 04:14  closed     —    kalshi

Every pair is one rich row (tournament chip, full names, avatars, score) and one
ghost (bare `WTA` chip, surname only, no score, start time off by up to 23
hours). For the one upcoming match the ghost is worse than redundant: the same
first-round match is offered at two different times on two different days.

WHY THE GHOSTS EXIST, AND WHY THEY ARE NOT A BUG IN THE EVENT GRAPH. Ruling 048
/ gotcha #32: an id-less claim NEVER absorbs, it creates. A Kalshi tennis market
names its competitors by surname, parsed out of a market title, and its
`commence_time` is a close time (gotcha #14) — a label and a stand-in, not a
dereference. There is nothing to anchor an absorption to, so the registry
creates, deliberately, and `prediction_market_matching` says so at the call
site: *"Duplicates are the declared, bounded price; reconciliation drains them
once a real id arrives."*

THIS MODULE IS NOT THAT DRAIN, AND MUST NOT BE MISTAKEN FOR IT. It writes
nothing, merges nothing and asserts no identity in the database. It answers a
strictly smaller question that belongs to whoever renders a list: *given these
rows on this page, which of them are the same fixture told twice, and which one
should the reader see?* The event graph keeps both rows and keeps its bounded
price; the page stops charging the reader for it. When the anchor channel
(#1946) drains the duplicates for real, this collapses nothing, because there
will be nothing to collapse.

THE FOUR CONDITIONS, all required, all conservative:

1. **The hidden row is VENUE-authored and the survivor is SCHEDULE-authored**,
   both named explicitly (`VENUE_SOURCES` / `SCHEDULE_SOURCES`) rather than read
   off a `>` between ladder ranks. This is the condition a replay over live rows
   corrected: ranking alone let a `statpal` MLB row be hidden behind an `espn`
   one, and one of those pairs was **two different games of a Yankees–Red Sox
   series** (08-29 17:05 and 08-30 17:35, 24.5 hours apart) — the season-series
   mislink class, rebuilt by a rule that was supposed to remove duplicates. Only
   a venue's fabrication is ever hidden, and an UNKNOWN source is never a venue:
   most of the table predates the column, and treating unrecorded provenance as
   fabrication would hide real events by the thousand.
2. **Both competitor pairs match, in either orientation**, by
   `name_normalization.names_match`, whose suffix-containment stage is exactly
   what makes the ghost's `Sabalenka` meet the real row's `Aryna Sabalenka`.
3. **The two start times are within `TWIN_WINDOW`.** Measured on the live
   population 2026-09-01: the seven Sabalenka pairs skew −23h to +12h, because
   one side is a close time and the other is a start. 30 hours covers the
   measured spread.
4. **Exactly one candidate survivor.** A 30-hour window is wide enough to hold
   two legs of a series, and a ghost that matches two real fixtures does not
   name which one it duplicates. Ambiguity keeps every row: a twin is only a
   twin when it is the ONLY thing it could be.

AND ONE REFUSAL. A venue row that carries a SCORE the schedule row does not is
kept. Hiding it would delete the only result on the page, which is the opposite
of the complaint.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any, Iterable, Optional, Sequence

from app.utils.name_normalization import names_match

#: Measured spread between a venue's stand-in start and the schedule's real one
#: (2026-09-01, the nine Sabalenka fixtures): −23h to +12h.
TWIN_WINDOW = timedelta(hours=30)

#: The `events.commence_time_source` values written by a PREDICTION VENUE, i.e.
#: parsed out of a market title or a ticker rather than read off a schedule.
#: These are the only rows this module will ever hide. `kalshi_ticker` is the
#: ticker-derived variant `auto_create_commence_time` stamps (#2020); plain
#: `kalshi` / `polymarket` mean the venue's own close time (gotcha #14).
VENUE_SOURCES = frozenset({"kalshi", "kalshi_ticker", "polymarket"})

#: The values written by a SCHEDULE. Only these may be a survivor. `None` is
#: absent from BOTH sets on purpose: unrecorded provenance is not evidence of
#: anything, in either direction.
SCHEDULE_SOURCES = frozenset({"odds_api", "statpal", "espn", "mlb_schedule_repair"})


def _sport_family(sport_key: Optional[str]) -> str:
    """`tennis_wta_cincinnati_open` and `tennis_wta` are one family.

    The ghost lands in the venue's generic bucket (`tennis_wta`, 551 rows since
    2026-08-01) while the schedule's row lands in the per-tournament key
    (`tennis_wta_cincinnati_open`, 132 rows), so a same-`sport_key` test would
    never see a single pair. The family is the first segment.
    """
    return (sport_key or "").split("_", 1)[0]


def _has_score(row: Any) -> bool:
    return _get(row, "home_score") is not None or _get(row, "away_score") is not None


def _get(row: Any, attr: str) -> Any:
    if isinstance(row, dict):
        return row.get(attr)
    return getattr(row, attr, None)


def same_fixture(row_a: Any, row_b: Any) -> bool:
    """Do these two rows describe one fixture? Conditions 2 and 3 only."""
    if _sport_family(_get(row_a, "sport_key")) != _sport_family(_get(row_b, "sport_key")):
        return False

    t_a, t_b = _get(row_a, "commence_time"), _get(row_b, "commence_time")
    if t_a is None or t_b is None:
        return False
    if abs(t_a - t_b) > TWIN_WINDOW:
        return False

    a_home = _get(row_a, "home_team_name") or ""
    a_away = _get(row_a, "away_team_name") or ""
    b_home = _get(row_b, "home_team_name") or ""
    b_away = _get(row_b, "away_team_name") or ""
    if not (a_home and a_away and b_home and b_away):
        return False

    if names_match(a_home, b_home) and names_match(a_away, b_away):
        return True
    # A venue names the sides in whatever order its market title used; the
    # schedule names home first. Orientation is not identity.
    return names_match(a_home, b_away) and names_match(a_away, b_home)


@dataclass
class TwinCollapse:
    """What the page should show, and what it hid, named."""

    kept: list[Any] = field(default_factory=list)
    #: `(dropped_row, kept_row_id)` — the ghost and the fixture it duplicated.
    #: Ruling 054: a row this module removes leaves with a reason and a number,
    #: never as silent attrition.
    dropped: list[tuple[Any, Any]] = field(default_factory=list)

    @property
    def dropped_count(self) -> int:
        return len(self.dropped)


def collapse_fixture_twins(rows: Sequence[Any]) -> TwinCollapse:
    """Drop each venue-authored duplicate of a schedule-authored fixture.

    Input order is preserved for the survivors — this is a filter, never a
    re-rank. `rows` may be ORM `Event`s or plain dicts; the fields read are
    `id`, `sport_key`, `home_team_name`, `away_team_name`, `commence_time`,
    `commence_time_source`, `home_score`, `away_score`.
    """
    result = TwinCollapse()
    dropped_ids: set[Any] = set()

    for i, row in enumerate(rows):
        # Condition 1, first half: only a venue's fabrication is ever hidden.
        if _get(row, "commence_time_source") not in VENUE_SOURCES:
            continue
        candidates = []
        for j, other in enumerate(rows):
            if i == j or _get(other, "id") in dropped_ids:
                continue
            # Condition 1, second half: only a schedule may be the survivor.
            if _get(other, "commence_time_source") not in SCHEDULE_SOURCES:
                continue
            if not same_fixture(row, other):
                continue
            if _has_score(row) and not _has_score(other):
                # The refusal. The ghost holds the only result on the page.
                continue
            candidates.append(other)
        # Condition 4: a ghost matching two real fixtures does not say which one
        # it duplicates, and a 30-hour window is wide enough to hold two legs of
        # a series. Ambiguity keeps every row.
        if len(candidates) != 1:
            continue
        dropped_ids.add(_get(row, "id"))
        result.dropped.append((row, _get(candidates[0], "id")))

    result.kept = [r for r in rows if _get(r, "id") not in dropped_ids]
    return result


def event_rows_for_collapse(events: Iterable[Any]) -> list[dict[str, Any]]:
    """Project ORM ``Event``s onto the six fields this module reads.

    The projection exists so the caller loads `Event.sport` ONCE, in its own
    eager-loaded query, rather than letting `_sport_family` trip a lazy load per
    row inside the collapse (gotcha #6's neighbour: a pure function that touches
    a relationship is not pure, it is N+1 with a docstring).
    """
    out: list[dict[str, Any]] = []
    for event in events:
        sport = getattr(event, "sport", None)
        out.append({
            "id": event.id,
            "sport_key": getattr(sport, "key", None),
            "home_team_name": event.home_team_name,
            "away_team_name": event.away_team_name,
            "commence_time": event.commence_time,
            "commence_time_source": event.commence_time_source,
            "home_score": event.home_score,
            "away_score": event.away_score,
        })
    return out
