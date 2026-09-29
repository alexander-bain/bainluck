"""#9427 — the scorer never offers a row #4965's fixture guard would refuse.

After ``f981cbacc2`` centred Pass 1's window on ``venue_game_start``, the Wild
Card Game 2 markets finally SAW their own row, and still did not link.
Production receipts, heavy v114, 2026-09-29 01:41:05Z::

    polymarket 63026424  mlb-phi-atl-2026-09-30  venue 09-30T18:00Z
      event 15320289  Game 1  09-29T18:00Z  Odds API id   score 30  (4+3+10+8+5)
      event 15320701  Game 2  09-30T18:00Z  no Odds API   score 28  (10+3+10+0+5)
      → Game 1 offered, guard refuses it (event_date_conflict · venue_fixture)

The +8 for an Odds API id is 32h of proximity, so it buys a whole day. #9117
closed that hole for a day-only stamp; a real first pitch was still scored
before the guard judged it. The scorer now asks the guard's own predicate
(``_venue_fixture_disagrees``) first, so the two can never disagree.

Every assertion comes in both directions (gotcha #43) and every instant is a
fixed literal (gotcha #44).
"""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.tasks.prediction_market_matching import (
    _REFUSAL_VENUE_FIXTURE,
    _check_polymarket_fixture_reason,
    _find_matching_event,
    _venue_fixture_disagrees,
)
from app.utils.prediction_market_matching import extract_matchup_with_ticker_fallback

UTC = timezone.utc
NOW = datetime(2026, 9, 29, 1, 41, 5, tzinfo=UTC)      # the refused attempt
LISTED = datetime(2026, 9, 28, 13, 0, 16, tzinfo=UTC)  # Gamma startDate

GAME_1 = (15320289, datetime(2026, 9, 29, 18, 0, tzinfo=UTC), "08d9219713246e3edff39b4f549085d8")
GAME_2 = (15320701, datetime(2026, 9, 30, 18, 0, tzinfo=UTC), None)
ROWS = (GAME_1, GAME_2)

G2_START = "2026-09-30T18:00:00+00:00"


def _event(event_id, commence, external_id):
    return SimpleNamespace(
        id=event_id,
        home_team_name="Atlanta Braves",
        away_team_name="Philadelphia Phillies",
        commence_time=commence,
        status="scheduled",
        external_id=external_id,
        sport=SimpleNamespace(key="baseball_mlb"),
        sport_id=3,
    )


def _market(venue=G2_START, *, slug="mlb-phi-atl-2026-09-30"):
    meta = {"polymarket_event_id": "1097831", "polymarket_event_slug": slug}
    if venue is not None:
        meta["venue_game_start"] = venue
    return SimpleNamespace(
        id=63026424,
        source="polymarket",
        external_id="1097831",
        name="Philadelphia Phillies vs. Atlanta Braves",
        commence_time=LISTED,
        llm_sport_category="baseball",
        market_metadata=meta,
    )


class _Session:
    """Every pass returns both Wild Card rows in commence order — Pass 1's
    window (centred on the venue stamp since ``f981cbacc2``) holds both."""

    def __init__(self, rows):
        self.rows = rows

    async def execute(self, statement):
        result = MagicMock()
        result.scalars.return_value.unique.return_value.all.return_value = self.rows
        return result


def _guard_session(commence):
    result = MagicMock()
    result.scalar_one_or_none.return_value = commence
    session = MagicMock()

    async def execute(_statement):
        return result

    session.execute = execute
    return session


async def _pick(market):
    matchup = extract_matchup_with_ticker_fallback(
        market.name, external_id=market.external_id,
    )
    assert matchup is not None and matchup.team_b, "specimen must parse as a matchup"
    rows = [_event(*r) for r in ROWS]
    return await _find_matching_event(_Session(rows), matchup, market, NOW)


class TestTheScorerOffersTheRowTheGuardAdmits:
    @pytest.mark.asyncio
    async def test_game_2_is_offered_game_2_not_the_odds_api_row(self):
        picked = await _pick(_market())
        assert picked is not None
        assert picked["event_id"] == GAME_2[0], (
            f"offered {picked['event_id']}; the venue names 09-30T18:00Z, which "
            f"is {GAME_2[0]}. Game 1's +8 Odds API bonus must not buy a day."
        )

    @pytest.mark.asyncio
    async def test_game_1_is_offered_game_1(self):
        picked = await _pick(_market("2026-09-29T18:00:00+00:00", slug="mlb-phi-atl-2026-09-29"))
        assert picked is not None and picked["event_id"] == GAME_1[0]

    @pytest.mark.asyncio
    async def test_a_market_no_row_fits_is_offered_nothing(self):
        # Game 3 (10-01), whose row does not exist yet: both rows are a day or
        # more away, so neither is offered rather than one being refused.
        assert await _pick(_market("2026-10-01T18:00:00+00:00", slug="mlb-phi-atl-2026-10-01")) is None

    @pytest.mark.asyncio
    async def test_no_stamp_scores_exactly_as_before(self):
        # Control: without a venue instant nothing is pre-filtered, so the Odds
        # API row still wins the score, as it always has.
        picked = await _pick(_market(venue=None))
        assert picked is not None and picked["event_id"] == GAME_1[0]


class TestTheScorerAndTheGuardAgree:
    """The scorer's pre-filter and the guard answer from one predicate: for
    every row, 'skipped by the scorer' == 'refused by the guard'."""

    @pytest.mark.parametrize("venue", [
        G2_START,
        "2026-09-30T20:59:00+00:00",   # 2h59m after Game 2 — admitted
        "2026-09-30T21:01:00+00:00",   # 3h01m — refused
        "2026-09-29T07:33:00+00:00",   # MLB TBD stamp (#9117): judged by day
        None,
    ])
    @pytest.mark.parametrize("row", ROWS)
    @pytest.mark.asyncio
    async def test_prefilter_matches_guard(self, venue, row):
        market = _market(venue)
        event_id, commence, _ = row
        refused = await _check_polymarket_fixture_reason(
            _guard_session(commence), event_id, market,
        ) == _REFUSAL_VENUE_FIXTURE
        assert _venue_fixture_disagrees(market, commence) is refused

    def test_the_three_hour_edge_both_ways(self):
        assert _venue_fixture_disagrees(_market("2026-09-30T20:59:00+00:00"), GAME_2[1]) is False
        assert _venue_fixture_disagrees(_market("2026-09-30T21:01:00+00:00"), GAME_2[1]) is True

    def test_a_day_only_stamp_is_judged_by_its_day_not_its_stand_in(self):
        # #9117: TBD on 09-29 (3:33 AM ET) and our row moved first to 8:08 PM
        # ET (00:08Z on the 30th) — 4.1h from the 4 PM stand-in, the same day.
        tbd = _market("2026-09-29T07:33:00+00:00", slug="mlb-phi-atl-2026-09-29")
        late_same_day = datetime(2026, 9, 30, 0, 8, tzinfo=UTC)
        assert _venue_fixture_disagrees(tbd, late_same_day) is False
        assert _venue_fixture_disagrees(tbd, GAME_2[1]) is True

    def test_only_polymarket_is_judged(self):
        # The guard judges Polymarket alone; a stamp on any other source's row
        # is no signal to the scorer either (#8373).
        kalshi = _market("2026-09-30T21:01:00+00:00")
        kalshi.source = "kalshi"
        assert _venue_fixture_disagrees(kalshi, GAME_2[1]) is False
        assert _venue_fixture_disagrees(_market("2026-09-30T21:01:00+00:00"), GAME_2[1]) is True

    def test_fails_open_without_either_side(self):
        assert _venue_fixture_disagrees(_market(venue=None), GAME_1[1]) is False
        assert _venue_fixture_disagrees(_market(), None) is False
