"""#12595 / #11286 review: a scheduled game's projected pair comes from RECENT line readings.

PILLAR: TRUTH. SHIP: a scheduled game's projected final, spread and total come
from sportsbook lines read within the last 90 minutes, dated by those readings,
or are absent with a reason. Never a day-old pair under this morning's time.

WHAT WAS WRONG (#12595, production, Nov 11 8:38 AM PT). Rams at Cardinals served
a projected 15.5 – 24.6 under `captured_at` 8:06 AM. The ten books behind it were
last confirmed ~36 h earlier, while the time and the book count beside it came
from eleven books' moneyline-only reads that morning. Two mechanisms:

* A moneyline-only fetch writes a new no-lines row (`_snapshots_are_equal` counts
  a missing spread as a change). That row becomes the book's latest, so the book
  leaves the pair. The Lakers at Hawks board went 20 → 9 books on each such pass.
* A book the moneyline-only fetch doesn't cover (the second region) keeps its old
  lines row as its latest, with no age limit (`pregame_projection.py` header).

THE RULE. For a game whose stored status is `scheduled`, in scope
(:data:`PROJECTION_RECENT_LINES_SPORTS`), the spread, total and projected pair
are aggregated (reversed books out, then `aggregate_bookmaker_odds`, the same
steps as today) over each book's newest row CARRYING both a spread and a total,
kept only if its effective time (`valid_until` or `captured_at`,
`odds_filtering._effective_time`) is within :data:`PROJECTION_LINES_BOUND`.
The probability, the moneyline, `captured_at` and `bookmaker_count` are NOT
touched. The installed iPhone dates its headline from `current_odds.captured_at`
(`EventAtlasLivePath11666.resolveHeadlineObservedAt`), so the pair gets its own:
`projection_captured_at` (the newest effective time behind it),
`projection_bookmaker_count`, and `projection_unavailable` ("no_recent_lines")
when nothing is recent enough, so an absent pair is never mistaken for a game
with no lines. Live and finished games are exactly as before.

THE BOUND. 90 minutes. The NFL and NBA get spreads and totals once an hour
(decision 138, #11286), so every book's lines are under an hour old plus
polling jitter. Every OTHER league is fetched with lines only inside the two
hours before the start (the poller's live and soon tiers). So outside that
window those leagues serve NO pair, with `projection_unavailable:
"no_recent_lines"`. That is what #12595 asks for: absent, not old. Whether
those leagues are in scope at all is decision 149 (Alex). One constant decides.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Optional

logger = logging.getLogger(__name__)

#: Decision 149 (Alex, pending): None means every league; a frozenset limits the
#: rule to those sport keys (e.g. {"americanfootball_nfl", "basketball_nba"}).
#: Either answer is this one line.
PROJECTION_RECENT_LINES_SPORTS: Optional[frozenset] = None

#: How old a book's newest line reading may be and still count toward the pair.
PROJECTION_LINES_BOUND = timedelta(minutes=90)

#: The scan floor for the recent-lines statement: no line reading older than this
#: is looked at, so a book that rarely quotes lines can't make the read walk its
#: whole history. Far outside the bound, so it never changes an answer.
_SCAN_FLOOR = timedelta(days=7)

NO_RECENT_LINES = "no_recent_lines"


def _utcnow() -> datetime:
    """The clock the bound is measured against; one seam for tests."""
    return datetime.now(timezone.utc)

#: The keys this adds to `current_odds` (scheduled, in scope only).
PROJECTION_KEYS = ("projection_captured_at", "projection_bookmaker_count", "projection_unavailable")

#: The `aggregate_bookmaker_odds` fields the recent line readings replace.
_PAIR_FIELDS = ("home_spread", "over_under", "projected_home_score", "projected_away_score")


def _loaded_sport_key(event: Any) -> Optional[str]:
    from app.utils.kalshi_occurrence_start import loaded_sport_key

    try:
        return loaded_sport_key(event)
    except Exception:  # noqa: BLE001 — an unknown sport is out of a limited scope
        return None


def in_scope(event: Any) -> bool:
    """Is this event's pair read from recent line readings? Never lazy-loads."""
    if event is None or getattr(event, "status", None) != "scheduled":
        return False
    if PROJECTION_RECENT_LINES_SPORTS is None:
        return True
    return _loaded_sport_key(event) in PROJECTION_RECENT_LINES_SPORTS


def card_in_scope(stored_status: Optional[str], sport_key: Optional[str]) -> bool:
    """`in_scope` for a list card, which carries its stored status and sport key."""
    if stored_status != "scheduled":
        return False
    return PROJECTION_RECENT_LINES_SPORTS is None or sport_key in PROJECTION_RECENT_LINES_SPORTS


def has_lines(snapshot: Any) -> bool:
    return (
        getattr(snapshot, "home_spread", None) is not None
        and getattr(snapshot, "over_under", None) is not None
    )


def recent_lines_per_bookmaker_query(event_ids: list[int], *, now: datetime):
    """The newest row WITH a spread and a total per (event, book), within the scan floor.

    The same recursive bookmaker walk as `latest_odds_per_bookmaker_query` and a
    `LIMIT 1` lateral, so it reads O(books), not O(depth). The bound itself is
    applied in Python on the effective time (`projection_from_rows`), the one
    definition `odds_filtering` uses, so a row kept current by dedup inside the
    two-hour window is never dropped for an old first capture.
    """
    from sqlalchemy import func, select, true
    from sqlalchemy.orm import aliased

    from app.models.models import Event, OddsSnapshot

    floor = now - _SCAN_FLOOR
    bookmakers = (
        select(
            Event.id.label("event_id"),
            select(func.min(OddsSnapshot.bookmaker))
            .where(OddsSnapshot.event_id == Event.id)
            .scalar_subquery()
            .label("bookmaker"),
        )
        .where(Event.id.in_(event_ids))
        .cte("lines_bookmakers", recursive=True)
    )
    _prev = bookmakers.alias("prev_lines_bookmaker")
    bookmakers = bookmakers.union_all(
        select(
            _prev.c.event_id,
            select(func.min(OddsSnapshot.bookmaker))
            .where(
                OddsSnapshot.event_id == _prev.c.event_id,
                OddsSnapshot.bookmaker > _prev.c.bookmaker,
            )
            .scalar_subquery(),
        ).where(_prev.c.bookmaker.isnot(None))
    )
    lines_snap = (
        select(OddsSnapshot)
        .where(
            OddsSnapshot.event_id == bookmakers.c.event_id,
            OddsSnapshot.bookmaker == bookmakers.c.bookmaker,
            OddsSnapshot.home_spread.isnot(None),
            OddsSnapshot.over_under.isnot(None),
            OddsSnapshot.captured_at >= floor,
        )
        .order_by(OddsSnapshot.captured_at.desc(), OddsSnapshot.id.desc())
        .limit(1)
        .lateral("lines_snap")
    )
    snap = aliased(OddsSnapshot, lines_snap)
    return (
        select(snap)
        .select_from(bookmakers)
        .join(lines_snap, true())
        .where(bookmakers.c.bookmaker.isnot(None))
    )


def projection_from_rows(rows: Iterable[Any], *, now: datetime) -> dict:
    """The pair fields and their stamps from one event's recent line readings. Pure."""
    from app.utils.odds_filtering import _effective_time
    from app.utils.odds_math import aggregate_bookmaker_odds, detect_reversed_bookmakers

    fresh = [r for r in rows if has_lines(r) and _effective_time(r) >= now - PROJECTION_LINES_BOUND]
    if not fresh:
        return {
            **{field: None for field in _PAIR_FIELDS},
            "projection_captured_at": None,
            "projection_bookmaker_count": 0,
            "projection_unavailable": NO_RECENT_LINES,
        }
    reversed_books = detect_reversed_bookmakers(fresh)
    agg = [r for r in fresh if r.bookmaker not in reversed_books] or fresh
    aggregated = aggregate_bookmaker_odds(agg)
    return {
        **{field: aggregated.get(field) for field in _PAIR_FIELDS},
        "projection_captured_at": max(_effective_time(r) for r in agg).isoformat(),
        "projection_bookmaker_count": len({r.bookmaker for r in agg}),
        "projection_unavailable": None,
    }


async def recent_line_projections(db: Any, events: Iterable[Any], *, now: Optional[datetime] = None) -> dict[int, dict]:
    """``{event_id: projection}`` for the in-scope scheduled events, in ONE statement."""
    now = now or _utcnow()
    ids = sorted({int(e.id) for e in events if in_scope(e)})
    if not ids:
        return {}
    by_event: dict[int, list] = {i: [] for i in ids}
    for row in (await db.execute(recent_lines_per_bookmaker_query(ids, now=now))).scalars().all():
        by_event.setdefault(row.event_id, []).append(row)
    return {eid: projection_from_rows(rows, now=now) for eid, rows in by_event.items()}


def apply_projection(aggregated: dict, projection: Optional[dict]) -> dict:
    """`aggregated` with the pair fields replaced by the recent readings' (a copy)."""
    if not projection:
        return aggregated
    out = dict(aggregated)
    for field in _PAIR_FIELDS:
        out[field] = projection.get(field)
    out["_projection"] = {key: projection.get(key) for key in PROJECTION_KEYS}
    return out


def projection_keys(aggregated: Optional[dict]) -> dict:
    """The keys to add to `current_odds`: nothing unless a projection was applied."""
    if not isinstance(aggregated, dict) or "_projection" not in aggregated:
        return {}
    return dict(aggregated["_projection"])


async def apply_recent_line_projections(db: Any, events: Iterable[Any], odds_map: dict, *, now: Optional[datetime] = None) -> None:
    """Replace each in-scope scheduled event's pair in an `{event_id: {"aggregated": …}}` map, in place.

    Never raises (gotcha #42): if the recent-lines read fails, every event keeps
    the pair it had, exactly as before this existed, and the failure is logged.
    """
    events = list(events)
    wanted = [e for e in events if int(e.id) in odds_map]
    try:
        projections = await recent_line_projections(db, wanted, now=now)
    except Exception:  # noqa: BLE001 — one stage, not the page
        logger.exception("recent line projections failed; serving today's pair")
        return
    for event_id, projection in projections.items():
        entry = odds_map.get(event_id)
        if isinstance(entry, dict) and "aggregated" in entry:
            entry["aggregated"] = apply_projection(entry["aggregated"], projection)
