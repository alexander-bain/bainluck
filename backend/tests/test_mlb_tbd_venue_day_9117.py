"""#9117 — MLB's "time TBD" stamp names a game DAY, not a 3:33 AM first pitch.

A game whose first pitch is not yet set is published at 3:33:00 AM in the
park's own zone. Measured 2026-09-27 ~10:50Z: the MLB Stats API gives the Red
Sox @ Yankees AL Wild Card opener as ``2026-09-29T07:33:00Z`` (and Cubs @
Padres at Petco as ``10:33:00Z``), both ``status.startTimeTBD=true``, and Gamma
copies the instant into ``startTime`` with ``eventDate`` 2026-09-29.

Production held (``market_match_receipts``, 24 attempts since 09-26 13:20Z)::

    polymarket 1085445  mlb-bos-nyy-2026-09-29  venue 09-29T07:33Z  rejected · venue_fixture
    polymarket 1085449  mlb-bos-nyy-2026-09-30  venue 09-30T07:33Z  rejected · venue_fixture
    polymarket 1085450  mlb-bos-nyy-2026-10-01  venue 10-01T07:33Z  rejected · venue_fixture

    event 15319563  Game 1  09-29T20:00Z  StatPal 369024 + Odds API id
    event 15319236  Game 2  09-30T20:00Z  StatPal 369023, no Odds API id

Two defects, and both have to go for Game 2 to link:

1. #4965's ±3h guard read 07:33Z as a first pitch, 12.5h from each row.
2. The scorer picked Game 1's row for ALL THREE markets: its Odds API id is
   worth +8, i.e. 32h of proximity, which outweighs a day. So widening the
   window alone would have put Game 2's price on Game 1.

Every assertion comes in both directions (gotcha #43), and every instant is a
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
    _venue_game_day_disagrees,
    auto_create_commence_time,
    venue_game_day,
    venue_game_start,
)
from app.utils.prediction_market_matching import extract_matchup_with_ticker_fallback

UTC = timezone.utc
NOW = datetime(2026, 9, 27, 8, 50, tzinfo=UTC)      # the last refused attempt
LISTED = datetime(2026, 9, 26, 13, 0, 24, tzinfo=UTC)  # Gamma startDate

GAME_1 = (15319563, datetime(2026, 9, 29, 20, 0, tzinfo=UTC), "4cb76cceb16eb603c683038d132f4642")
GAME_2 = (15319236, datetime(2026, 9, 30, 20, 0, tzinfo=UTC), None)
ROWS = (GAME_1, GAME_2)

TBD_G1 = ("1085445", "mlb-bos-nyy-2026-09-29", "2026-09-29T07:33:00+00:00")
TBD_G2 = ("1085449", "mlb-bos-nyy-2026-09-30", "2026-09-30T07:33:00+00:00")
TBD_G3 = ("1085450", "mlb-bos-nyy-2026-10-01", "2026-10-01T07:33:00+00:00")


def _event(event_id, commence, external_id):
    return SimpleNamespace(
        id=event_id,
        home_team_name="New York Yankees",
        away_team_name="Boston Red Sox",
        commence_time=commence,
        status="scheduled",
        external_id=external_id,
        sport=SimpleNamespace(key="baseball_mlb"),
        sport_id=3,
    )


def _market(spec, *, slug=None):
    pm_id, default_slug, venue = spec
    return SimpleNamespace(
        id=int(pm_id),
        source="polymarket",
        external_id=pm_id,
        name="Boston Red Sox vs. New York Yankees",
        commence_time=LISTED,
        llm_sport_category="baseball",
        market_metadata={
            "polymarket_event_id": pm_id,
            "polymarket_event_slug": default_slug if slug is None else slug,
            "venue_game_start": venue,
        },
    )


def _guard_session(commence):
    result = MagicMock()
    result.scalar_one_or_none.return_value = commence
    session = MagicMock()

    async def execute(_statement):
        return result

    session.execute = execute
    return session


class _Session:
    """Pass 1 (windowed on the listing stamp) finds nothing; later passes
    return both Wild Card rows in commence order."""

    def __init__(self, rows):
        self.rows = rows
        self.calls = 0

    async def execute(self, statement):
        self.calls += 1
        result = MagicMock()
        rows = [] if self.calls == 1 else self.rows
        result.scalars.return_value.unique.return_value.all.return_value = rows
        return result


async def _pick(market):
    matchup = extract_matchup_with_ticker_fallback(
        market.name, external_id=market.external_id,
    )
    assert matchup is not None and matchup.team_b, "specimen must parse as a matchup"
    rows = [_event(*r) for r in ROWS]
    return await _find_matching_event(_Session(rows), matchup, market, NOW)


# ── Reading the stamp ────────────────────────────────────────────────────────
class TestTheStampNamesADay:
    def test_yankee_stadium_tbd_is_the_ny_game_day(self):
        day, offset = venue_game_day(_market(TBD_G1))
        assert str(day) == "2026-09-29"
        assert offset.total_seconds() == -4 * 3600

    def test_petco_tbd_is_the_pacific_game_day(self):
        m = _market(("1", "mlb-chc-sd-2026-09-29", "2026-09-29T10:33:00Z"))
        day, offset = venue_game_day(m)
        assert str(day) == "2026-09-29"
        assert offset.total_seconds() == -7 * 3600

    def test_the_instant_is_the_stand_in_not_three_thirty_three(self):
        assert venue_game_start(_market(TBD_G1)) == datetime(2026, 9, 29, 20, 0, tzinfo=UTC)

    def test_a_real_mlb_first_pitch_is_untouched(self):
        m = _market(("1058711", "mlb-bal-nyy-2026-09-27", "2026-09-27T17:05:00+00:00"))
        assert venue_game_day(m) is None
        assert venue_game_start(m) == datetime(2026, 9, 27, 17, 5, tzinfo=UTC)

    def test_another_league_at_the_same_instant_is_untouched(self):
        m = _market(TBD_G1, slug="nba-bos-nyk-2026-09-29")
        assert venue_game_day(m) is None
        assert venue_game_start(m) == datetime(2026, 9, 29, 7, 33, tzinfo=UTC)

    def test_a_stamp_one_minute_off_the_sentinel_is_untouched(self):
        m = _market(("1", "mlb-bos-nyy-2026-09-29", "2026-09-29T07:34:00+00:00"))
        assert venue_game_day(m) is None

    def test_a_late_start_on_the_game_day_is_the_same_day(self):
        # 10:10 PM ET on the 29th is 02:10Z on the 30th.
        m = _market(TBD_G1)
        assert not _venue_game_day_disagrees(m, datetime(2026, 9, 30, 2, 10, tzinfo=UTC))
        assert _venue_game_day_disagrees(m, datetime(2026, 9, 30, 20, 0, tzinfo=UTC))


# ── The guard ────────────────────────────────────────────────────────────────
class TestTheFixtureGuardComparesTheDay:
    @pytest.mark.asyncio
    async def test_game_1_admits_its_own_row(self):
        assert await _check_polymarket_fixture_reason(
            _guard_session(GAME_1[1]), GAME_1[0], _market(TBD_G1),
        ) is None

    @pytest.mark.asyncio
    async def test_game_2_admits_its_own_row(self):
        assert await _check_polymarket_fixture_reason(
            _guard_session(GAME_2[1]), GAME_2[0], _market(TBD_G2),
        ) is None

    @pytest.mark.asyncio
    async def test_game_2_is_refused_game_1s_row(self):
        assert await _check_polymarket_fixture_reason(
            _guard_session(GAME_1[1]), GAME_1[0], _market(TBD_G2),
        ) == _REFUSAL_VENUE_FIXTURE

    @pytest.mark.asyncio
    async def test_game_3_is_refused_game_2s_row(self):
        assert await _check_polymarket_fixture_reason(
            _guard_session(GAME_2[1]), GAME_2[0], _market(TBD_G3),
        ) == _REFUSAL_VENUE_FIXTURE

    @pytest.mark.asyncio
    async def test_our_row_timed_before_the_venue_still_admits_its_day(self):
        # MLB sets Game 1 at 8:08 PM ET (00:08Z on the 30th) and our row moves
        # first while Gamma still says TBD. That is 4.1h from the 4 PM stand-in,
        # so an instant rule would refuse a correct link; the day rule admits it.
        late = datetime(2026, 9, 30, 0, 8, tzinfo=UTC)
        assert await _check_polymarket_fixture_reason(
            _guard_session(late), GAME_1[0], _market(TBD_G1),
        ) is None
        assert await _check_polymarket_fixture_reason(
            _guard_session(late), GAME_1[0], _market(TBD_G2),
        ) == _REFUSAL_VENUE_FIXTURE

    @pytest.mark.asyncio
    async def test_a_real_instant_keeps_the_three_hour_rule(self):
        # Control: the same 07:33Z on a non-MLB slug is still a first pitch,
        # 12.5h from the row, and still refused exactly as before.
        m = _market(TBD_G1, slug="nba-bos-nyk-2026-09-29")
        assert await _check_polymarket_fixture_reason(
            _guard_session(GAME_1[1]), GAME_1[0], m,
        ) == _REFUSAL_VENUE_FIXTURE


# ── The scorer ───────────────────────────────────────────────────────────────
class TestTheScorerOffersTheRowOnTheVenuesDay:
    @pytest.mark.asyncio
    async def test_game_1_is_offered_game_1(self):
        picked = await _pick(_market(TBD_G1))
        assert picked is not None and picked["event_id"] == GAME_1[0]

    @pytest.mark.asyncio
    async def test_game_2_is_offered_game_2_not_the_odds_api_row(self):
        picked = await _pick(_market(TBD_G2))
        assert picked is not None
        assert picked["event_id"] == GAME_2[0], (
            f"offered {picked['event_id']}; the venue names Sep 30, which is "
            f"{GAME_2[0]}. Game 1's +8 Odds API bonus must not buy a day."
        )

    @pytest.mark.asyncio
    async def test_game_3_if_necessary_is_offered_nothing(self):
        assert await _pick(_market(TBD_G3)) is None

    @pytest.mark.asyncio
    async def test_a_real_instant_scores_exactly_as_before(self):
        # Control for the narrow scope: with a real first pitch the pre-filter
        # does not fire, so the Odds API row still wins the score and #4965's
        # guard is what refuses it, unchanged.
        m = _market(("1085449", "nba-bos-nyk-2026-09-30", "2026-09-30T07:33:00+00:00"))
        picked = await _pick(m)
        assert picked is not None and picked["event_id"] == GAME_1[0]


# ── Minting ──────────────────────────────────────────────────────────────────
def test_a_tbd_stamp_never_becomes_a_minted_rows_start():
    commence, source = auto_create_commence_time(_market(TBD_G1), LISTED)
    assert commence != venue_game_start(_market(TBD_G1))
    assert source is None or "polymarket" not in str(source).lower()


def test_a_real_first_pitch_still_mints_at_the_venues_instant():
    m = _market(("1058711", "mlb-bal-nyy-2026-09-27", "2026-09-27T17:05:00+00:00"))
    commence, _ = auto_create_commence_time(m, LISTED)
    assert commence == datetime(2026, 9, 27, 17, 5, tzinfo=UTC)
