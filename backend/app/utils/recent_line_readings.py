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
A book's reading is dated by `valid_until` ONLY when that row is still its
latest (re-read and confirmed). A lines row that a newer moneyline-only row has
replaced is dated by its own `captured_at`: the writer sets the replaced row's
`valid_until` to the moneyline pass's time, which is not a lines reading (Fable's
review of #12599). So, per book: its latest row if that row carries lines, else
its newest lines row captured inside the bound.

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
those leagues are in scope is decision 149: A (Alex, 9:42 AM PT Nov 11), every
league. One constant decides.

A FAILED READ withholds the pair (`projection_unavailable: "read_failed"`): an
unknown age is not a recent one. The read runs in a SAVEPOINT under a local
statement timeout and the savepoint is rolled back, so a failure can't abort the
request's transaction (the card path's pattern, `read_card_projected_pairs_bounded`).
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

NO_RECENT_LINES = "no_recent_lines"
READ_FAILED = "read_failed"

#: The recent-lines read's own statement bound, inside its savepoint.
PROJECTION_READ_CAP_MS = 1500

#: The columns the pair needs from a lines row (aggregation, reversal, dating).
_ROW_COLUMNS = (
    "id", "event_id", "bookmaker", "captured_at", "valid_until",
    "home_moneyline", "away_moneyline", "home_win_probability", "away_win_probability",
    "home_spread", "over_under", "projected_home_score", "projected_away_score",
)


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


def books_needing_lines(latest_by_event: dict) -> list[tuple[int, str]]:
    """``[(event_id, bookmaker)]`` whose LATEST row carries no lines: the only books read.

    A book whose latest row has lines is dated by that row (`pair_readings`), so
    it needs nothing more from the database.
    """
    return sorted(
        (int(eid), row.bookmaker)
        for eid, rows in latest_by_event.items()
        for row in rows
        if row is not None and not has_lines(row)
    )


def recent_lines_query(pairs: list[tuple[int, str]], *, since: datetime):
    """Each (event, book)'s newest row WITH a spread and a total captured since ``since``.

    ``pairs`` is a ``VALUES`` list; each pair gets a ``LIMIT 1`` lateral on
    ``ix_odds_snapshots_bookmaker_closing`` (event_id, bookmaker, captured_at
    DESC) that walks only that book's rows inside the bound. A plain ``SELECT``
    (no leading ``WITH``), so db-query can ``EXPLAIN ANALYZE`` it. Columns, not
    ORM rows, so the result survives the savepoint rollback (gotcha #6).
    """
    from sqlalchemy import Integer, String, column, select, true, values

    from app.models.models import OddsSnapshot

    want = values(
        column("event_id", Integer), column("bookmaker", String), name="want_lines"
    ).data(list(pairs))
    cols = [getattr(OddsSnapshot, c) for c in _ROW_COLUMNS]
    lines = (
        select(*cols)
        .where(
            OddsSnapshot.event_id == want.c.event_id,
            OddsSnapshot.bookmaker == want.c.bookmaker,
            OddsSnapshot.home_spread.isnot(None),
            OddsSnapshot.over_under.isnot(None),
            OddsSnapshot.captured_at >= since,
        )
        .order_by(OddsSnapshot.captured_at.desc(), OddsSnapshot.id.desc())
        .limit(1)
        .lateral("recent_lines")
    )
    return select(*[lines.c[c] for c in _ROW_COLUMNS]).select_from(want).join(lines, true())


def pair_readings(latest_rows: Iterable[Any], recent_rows: Iterable[Any], *, now: datetime) -> list[tuple[Any, datetime]]:
    """``[(row, read_at)]``: the lines reading each book contributes, if recent. Pure.

    Per book: its LATEST row, dated by its effective time (`valid_until`, it is
    still the confirmed reading), when that row carries lines. Otherwise its newest
    lines row captured inside the bound, dated by `captured_at`, never by the
    `valid_until` a later moneyline-only row stamped on it.
    """
    from app.utils.odds_filtering import _effective_time

    cutoff = now - PROJECTION_LINES_BOUND
    recent_by_book = {}
    for row in recent_rows:
        prior = recent_by_book.get(row.bookmaker)
        if prior is None or row.captured_at > prior.captured_at:
            recent_by_book[row.bookmaker] = row
    out = []
    latest_by_book = {r.bookmaker: r for r in latest_rows}
    for book in sorted(set(latest_by_book) | set(recent_by_book)):
        latest = latest_by_book.get(book)
        if latest is not None and has_lines(latest):
            row, read_at = latest, _effective_time(latest)
        else:
            row = recent_by_book.get(book)
            read_at = row.captured_at if row is not None else None
        if row is not None and read_at is not None and read_at >= cutoff:
            out.append((row, read_at))
    return out


def unavailable(reason: str) -> dict:
    return {
        **{field: None for field in _PAIR_FIELDS},
        "projection_captured_at": None,
        "projection_bookmaker_count": 0,
        "projection_unavailable": reason,
    }


def projection_from_rows(latest_rows: Iterable[Any], recent_rows: Iterable[Any], *, now: datetime) -> dict:
    """The pair fields and their stamps from one event's line readings. Pure."""
    from app.utils.odds_math import aggregate_bookmaker_odds, detect_reversed_bookmakers

    readings = pair_readings(latest_rows, recent_rows, now=now)
    if not readings:
        return unavailable(NO_RECENT_LINES)
    rows = [r for r, _ in readings]
    reversed_books = detect_reversed_bookmakers(rows)
    kept = [(r, t) for r, t in readings if r.bookmaker not in reversed_books] or readings
    aggregated = aggregate_bookmaker_odds([r for r, _ in kept])
    return {
        **{field: aggregated.get(field) for field in _PAIR_FIELDS},
        "projection_captured_at": max(t for _, t in kept).isoformat(),
        "projection_bookmaker_count": len({r.bookmaker for r, _ in kept}),
        "projection_unavailable": None,
    }


async def read_recent_lines(
    db: Any, pairs: list[tuple[int, str]], *, now: datetime, bounded: bool = True
) -> dict[int, list]:
    """``{event_id: [row, …]}``, under a SAVEPOINT and a local timeout. Raises on failure.

    ``bounded`` (the route call sites): SAVEPOINT → ``SET LOCAL
    statement_timeout`` → the read → ROLLBACK TO SAVEPOINT, always. The read
    writes nothing, and rolling back reverts the SET LOCAL, so neither the bound
    nor a failed statement leaks into the request's transaction. The card path
    passes ``bounded=False`` because it already runs inside its own savepoint and
    timeout (`read_card_projected_pairs_bounded`). Rows are copied to plain
    objects first, so nothing read here is expired by the rollback (gotcha #6).
    """
    from types import SimpleNamespace

    from sqlalchemy import text

    async def _read() -> dict[int, list]:
        by_event: dict[int, list] = {}
        if not pairs:
            return by_event
        stmt = recent_lines_query(pairs, since=now - PROJECTION_LINES_BOUND)
        for row in (await db.execute(stmt)).all():
            ns = SimpleNamespace(**{c: getattr(row, c, None) for c in _ROW_COLUMNS})
            by_event.setdefault(ns.event_id, []).append(ns)
        return by_event

    if not pairs:
        return {}
    if not bounded:
        return await _read()
    async with db.begin_nested() as savepoint:
        try:
            await db.execute(text(f"SET LOCAL statement_timeout = '{int(PROJECTION_READ_CAP_MS)}ms'"))
            return await _read()
        finally:
            await savepoint.rollback()


async def recent_line_projections(
    db: Any, events: Iterable[Any], latest_by_event: dict, *, now: Optional[datetime] = None
) -> dict[int, dict]:
    """``{event_id: projection}`` for the in-scope scheduled events, in ONE bounded read.

    A failed read withholds every in-scope pair with ``read_failed``.
    """
    now = now or _utcnow()
    ids = sorted({int(e.id) for e in events if in_scope(e)})
    if not ids:
        return {}
    pairs = books_needing_lines({eid: latest_by_event.get(eid) or [] for eid in ids})
    try:
        recent = await read_recent_lines(db, pairs, now=now)
    except Exception:  # noqa: BLE001 — one stage, not the page; withhold, don't guess
        logger.exception("recent line readings failed for %d events; withholding", len(ids))
        return {eid: unavailable(READ_FAILED) for eid in ids}
    return {
        eid: projection_from_rows(latest_by_event.get(eid) or [], recent.get(eid) or [], now=now)
        for eid in ids
    }


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
    """Replace each in-scope scheduled event's pair in an `{event_id: {"aggregated", "all_snapshots"}}` map, in place.

    ``all_snapshots`` is the latest row per book (unfiltered), which the clock rule
    needs. Never raises: a failed read withholds the pairs (`read_failed`).
    """
    events = [e for e in events if int(e.id) in odds_map]
    latest_by_event = {
        int(e.id): list((odds_map[int(e.id)] or {}).get("all_snapshots") or [])
        for e in events
    }
    projections = await recent_line_projections(db, events, latest_by_event, now=now)
    for event_id, projection in projections.items():
        entry = odds_map.get(event_id)
        if isinstance(entry, dict) and "aggregated" in entry:
            entry["aggregated"] = apply_projection(entry["aggregated"], projection)
