"""#9427 — a Polymarket game market's Pass 1 WINDOW is centred on the venue's instant.

#8373 made ``_find_matching_event`` SCORE Polymarket candidates from
``market_metadata.venue_game_start`` but left the window on ``commence_time`` —
Gamma's LISTING stamp. A market listed two days before its game then searched a
window that ended before the game started.

Measured on production 2026-09-28 17:55Z (``market_match_receipts``, 8 attempts
each)::

    63045821  Philadelphia Phillies vs. Atlanta Braves   (Gamma 1097831)
      listed 09-28T13:00Z · venue_game_start 09-30T18:00Z
      window 09-26T13:00Z .. 09-30T13:00Z · windowed_candidates 1
      chosen 15320289 (Game 1, 09-29T18:00Z) → event_date_conflict / venue_fixture

Game 2's own row, 15320701 (09-30T18:00Z), sat five hours past the window end.
Because Pass 1 returned a candidate, the broad pass never ran. 22 markets carried
the same receipt that afternoon (Wild Card G2/G3, WNBA, NHL October games).

The fake session here APPLIES the statement's own ``BETWEEN`` bounds, so these
tests read the window the query really asked for — not a canned candidate list.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sqlalchemy.sql import operators, visitors

from app.tasks.prediction_market_matching import (
    _check_polymarket_fixture_reason,
    _find_matching_event,
)
from app.utils.prediction_market_matching import extract_matchup_with_ticker_fallback

UTC = timezone.utc
NOW = datetime(2026, 9, 28, 17, 20, tzinfo=UTC)  # the refused pass
LISTED = datetime(2026, 9, 28, 13, 0, 16, tzinfo=UTC)  # Gamma startDate

# The Wild Card series as production holds it (events.id, commence).
GAME_1 = (15320289, datetime(2026, 9, 29, 18, 0, tzinfo=UTC))
GAME_2 = (15320701, datetime(2026, 9, 30, 18, 0, tzinfo=UTC))
SERIES = [GAME_1, GAME_2]
GAME_3_VENUE = datetime(2026, 10, 1, 18, 0, tzinfo=UTC)  # no ESPN row yet


def _event(event_id, commence):
    return SimpleNamespace(
        id=event_id,
        home_team_name="Atlanta Braves",
        away_team_name="Philadelphia Phillies",
        commence_time=commence,
        status="scheduled",
        external_id=None,
        sport=SimpleNamespace(key="baseball_mlb"),
        sport_id=53232,
    )


def _market(venue_start=GAME_2[1], source="polymarket"):
    meta = {"polymarket_event_id": "1097831"}
    if venue_start is not None:
        meta["venue_game_start"] = venue_start.isoformat()
    return SimpleNamespace(
        id=63045821,
        source=source,
        external_id="0x3c80445e6248383d45606d5c8cde91ffc86f8312fa366b68e62d18d8b5019322",
        name="Philadelphia Phillies vs. Atlanta Braves",
        commence_time=LISTED,
        llm_sport_category="baseball",
        market_metadata=meta,
    )


def _between_bounds(statement):
    """The ``(low, high)`` of the statement's ``commence_time BETWEEN``."""
    for el in visitors.iterate(statement.whereclause):
        if getattr(el, "operator", None) is operators.between_op:
            low, high = (b.value for b in el.right.clauses)
            return low, high
    raise AssertionError("statement carries no BETWEEN — not the windowed query")


class _WindowedSession:
    """Answers each query with the series rows its BETWEEN admits."""

    def __init__(self, rows):
        self.rows = rows
        self.windows = []

    async def execute(self, statement):
        low, high = _between_bounds(statement)
        self.windows.append((low, high))
        admitted = [r for r in self.rows if low <= r.commence_time <= high]
        result = MagicMock()
        result.scalars.return_value.unique.return_value.all.return_value = admitted
        return result


async def _pick(market, rows=None):
    rows = rows if rows is not None else [_event(i, c) for i, c in SERIES]
    matchup = extract_matchup_with_ticker_fallback(
        market.name, external_id=market.external_id,
    )
    assert matchup is not None and matchup.team_b, "specimen must parse as a matchup"
    session = _WindowedSession(rows)
    picked = await _find_matching_event(session, matchup, market, NOW)
    return picked, session.windows[0]


@pytest.mark.asyncio
async def test_game_2_listed_two_days_early_is_offered_game_2():
    picked, (low, high) = await _pick(_market(venue_start=GAME_2[1]))
    assert high >= GAME_2[1], (
        f"Pass 1 searched up to {high.isoformat()}; Game 2 starts "
        f"{GAME_2[1].isoformat()}. A window centred on the listing stamp "
        f"({LISTED.isoformat()}) ends before the game it lists."
    )
    assert picked is not None
    assert picked["event_id"] == GAME_2[0], (
        f"offered {picked['event_id']}; the venue says {GAME_2[1].isoformat()}, "
        f"which is event {GAME_2[0]}"
    )


@pytest.mark.asyncio
async def test_the_window_is_centred_on_the_venue_instant():
    _, (low, high) = await _pick(_market(venue_start=GAME_2[1]))
    assert (low, high) == (GAME_2[1] - timedelta(hours=48), GAME_2[1] + timedelta(hours=48))


@pytest.mark.asyncio
async def test_the_offer_is_one_the_fixture_guard_admits():
    market = _market(venue_start=GAME_2[1])
    picked, _ = await _pick(market)

    class _CommenceSession:
        async def execute(self, statement):
            result = MagicMock()
            commence = dict(SERIES)[picked["event_id"]]
            result.scalar_one_or_none.return_value = commence
            result.scalar.return_value = commence
            return result

    assert await _check_polymarket_fixture_reason(
        _CommenceSession(), picked["event_id"], market,
    ) is None


@pytest.mark.asyncio
async def test_a_game_with_no_row_yet_is_still_refused_by_the_guard():
    # Game 3 has no ESPN row. The wider reach offers the nearest game (Game 2),
    # and #4965 refuses it — the same outcome as before, never a wrong link.
    market = _market(venue_start=GAME_3_VENUE)
    picked, _ = await _pick(market)
    assert picked is not None and picked["event_id"] == GAME_2[0]

    class _CommenceSession:
        async def execute(self, statement):
            result = MagicMock()
            result.scalar_one_or_none.return_value = GAME_2[1]
            result.scalar.return_value = GAME_2[1]
            return result

    assert await _check_polymarket_fixture_reason(
        _CommenceSession(), GAME_2[0], market,
    ) is not None


@pytest.mark.asyncio
async def test_a_market_without_the_stamp_keeps_the_listing_window():
    # Control: no venue instant ⇒ the window is the listing stamp ±48h, as before.
    picked, (low, high) = await _pick(_market(venue_start=None))
    assert (low, high) == (LISTED - timedelta(hours=48), LISTED + timedelta(hours=48))
    assert picked["event_id"] == GAME_1[0]


@pytest.mark.asyncio
async def test_a_kalshi_row_does_not_read_the_polymarket_stamp():
    # Kalshi's window is ±7d of commence_time; the Polymarket stamp never moves it.
    _, (low, high) = await _pick(_market(venue_start=GAME_2[1], source="kalshi"))
    assert (low, high) == (LISTED - timedelta(days=7), LISTED + timedelta(days=7))
