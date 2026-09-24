"""#8373 — a Polymarket series game is scored from the venue's own instant.

Polymarket lists one market per game, and every game of a series carries the
same ``name`` ("Chicago Cubs vs. Boston Red Sox"). A Polymarket market has no
ticker date, so ``_find_matching_event`` scored candidate proximity from
``now`` — and the NEAREST game of the series always won. Every later game of a
weekend set was offered game 1, #4965's fixture guard (rightly) refused it, and
the market never linked.

Measured on production 2026-09-24 20:07Z (heavy log, matcher pass 3df1f5d5)::

    Broad fallback matched polymarket 'Chicago Cubs vs. Boston Red Sox'
        → event 15316415 (time window bypass)
    Venue-fixture linkage blocked (#4965): polymarket 1053345
        (fixture=2026-09-26T23:15:00+00:00) would link to event 15316415
        (commence=2026-09-25T17:05:00+00:00) — 30.2h apart

Saturday's own row, 15316408 (09-26 23:15Z), sat in the same candidate list.
The fix scores Polymarket candidates from ``market_metadata.venue_game_start`` —
the same stamp the guard judges the link by. Scoring only: the search windows
are unchanged, and a market without the stamp scores exactly as before.
"""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.tasks.prediction_market_matching import (
    _check_polymarket_fixture_reason,
    _find_matching_event,
)
from app.utils.prediction_market_matching import extract_matchup_with_ticker_fallback

UTC = timezone.utc
NOW = datetime(2026, 9, 24, 20, 7, tzinfo=UTC)  # the refused pass
LISTED = datetime(2026, 9, 20, 19, 15, tzinfo=UTC)  # Gamma listing stamp

# The series as production holds it (events.id, commence).
GAME_1 = (15316415, datetime(2026, 9, 25, 17, 5, tzinfo=UTC))
GAME_2 = (15316330, datetime(2026, 9, 25, 22, 5, tzinfo=UTC))
SATURDAY = (15316408, datetime(2026, 9, 26, 23, 15, tzinfo=UTC))
SERIES = [GAME_1, GAME_2, SATURDAY]


def _event(event_id, commence):
    return SimpleNamespace(
        id=event_id,
        home_team_name="Boston Red Sox",
        away_team_name="Chicago Cubs",
        commence_time=commence,
        status="scheduled",
        external_id=f"mlb-{event_id}",
        sport=SimpleNamespace(key="baseball_mlb"),
        sport_id=3,
    )


def _market(external_id="1053345", venue_start=SATURDAY[1], source="polymarket"):
    meta = {"polymarket_event_id": external_id}
    if venue_start is not None:
        meta["venue_game_start"] = venue_start.isoformat()
    return SimpleNamespace(
        id=61665050,
        source=source,
        external_id=external_id,
        name="Chicago Cubs vs. Boston Red Sox",
        commence_time=LISTED,
        llm_sport_category="baseball",
        market_metadata=meta,
    )


class _Session:
    """Pass 1 (windowed on the listing stamp) finds nothing; the broad pass
    returns the whole series in commence order — production's shape."""

    def __init__(self, rows):
        self.rows = rows
        self.calls = 0

    async def execute(self, statement):
        self.calls += 1
        result = MagicMock()
        rows = [] if self.calls == 1 else self.rows
        result.scalars.return_value.unique.return_value.all.return_value = rows
        return result


async def _pick(market, rows=None):
    rows = rows if rows is not None else [_event(i, c) for i, c in SERIES]
    matchup = extract_matchup_with_ticker_fallback(
        market.name, external_id=market.external_id,
    )
    assert matchup is not None and matchup.team_b, "specimen must parse as a matchup"
    return await _find_matching_event(_Session(rows), matchup, market, NOW)


@pytest.mark.asyncio
async def test_saturdays_market_is_offered_saturdays_game_not_game_1():
    picked = await _pick(_market(venue_start=SATURDAY[1]))
    assert picked is not None
    assert picked["event_id"] == SATURDAY[0], (
        f"offered {picked['event_id']}; the venue says the game is "
        f"{SATURDAY[1].isoformat()}, which is event {SATURDAY[0]}. Scoring from "
        "`now` offers the nearest game of the series, which #4965 then refuses."
    )


@pytest.mark.asyncio
async def test_a_doubleheader_half_is_offered_its_own_half():
    picked = await _pick(_market(external_id="1047827", venue_start=GAME_2[1]))
    assert picked["event_id"] == GAME_2[0]
    picked = await _pick(_market(external_id="1058697", venue_start=GAME_1[1]))
    assert picked["event_id"] == GAME_1[0]


@pytest.mark.asyncio
async def test_the_offered_event_is_one_the_fixture_guard_admits():
    # The point of the fix: the finder and #4965 now judge by ONE instant, so
    # the offer is not refused on arrival.
    market = _market(venue_start=SATURDAY[1])
    picked = await _pick(market)

    class _CommenceSession:
        async def execute(self, statement):
            result = MagicMock()
            commence = dict(SERIES)[picked["event_id"]]
            result.scalar_one_or_none.return_value = commence
            result.scalar.return_value = commence
            return result

    reason = await _check_polymarket_fixture_reason(
        _CommenceSession(), picked["event_id"], market,
    )
    assert reason is None


@pytest.mark.asyncio
async def test_a_market_without_the_stamp_scores_exactly_as_before():
    # Control: no venue instant ⇒ proximity from `now`, the nearest game wins.
    picked = await _pick(_market(venue_start=None))
    assert picked["event_id"] == GAME_1[0]


@pytest.mark.asyncio
async def test_a_non_polymarket_row_does_not_read_the_polymarket_stamp():
    # `tasks.polymarket` is the only writer of `venue_game_start`; the gate is
    # the source, as in `_venue_confirmed_covered_fixture` and #6073.
    picked = await _pick(_market(venue_start=SATURDAY[1], source="kalshi"))
    assert picked["event_id"] == GAME_1[0]
