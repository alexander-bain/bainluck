"""WNBA's placeholder stamp names a game DAY, not a 17:00Z tip-off (#9117's class).

Polymarket lists a conditional playoff game before the league sets its
tip-off, with ``startTime`` = its ``eventDate`` at exactly 17:00:00Z. Measured
2026-09-30 ~11:40Z on Gamma, all four conditional games listed on 09-25::

    1081046  wnba-nyl-min-2026-10-01  startTime 10-01T17:00Z  (not needed: 2-0)
    1081047  wnba-ind-las-2026-10-01  startTime 10-01T17:00Z  (Game 3, 1-1)
    1081048  wnba-wsh-atl-2026-10-02  startTime 10-02T17:00Z
    1081049  wnba-dal-gsv-2026-10-02  startTime 10-02T17:00Z

Production held (``market_match_receipts``, 79 attempts since 09-25 18:20Z)::

    polymarket 62363365 / 63087132  "Indiana Fever vs. Las Vegas Aces"
      candidate 15321848 (ESPN 401918022, 10-02T01:00Z, both sides matched)
      verdict outside_time_window — #4965's ±3h guard, 8h from the stamp

So the Fever @ Aces elimination game showed no Polymarket price while Gamma
traded it at 37/40. 17:00Z is also a real 1 PM Eastern tip-off (Minnesota @
Connecticut 2026-09-20), so the stamp is read as the Eastern DAY, which costs a
real 17:00Z game nothing.

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
    _venue_fixture_disagrees,
    auto_create_commence_time,
    venue_game_day,
    venue_game_start,
)
from app.utils.prediction_market_matching import extract_matchup_with_ticker_fallback

UTC = timezone.utc
NOW = datetime(2026, 9, 30, 9, 30, tzinfo=UTC)          # the last refused attempt
LISTED = datetime(2026, 9, 25, 17, 48, 22, tzinfo=UTC)   # Gamma startDate

GAME_2 = (15320302, datetime(2026, 9, 29, 22, 30, tzinfo=UTC), "completed")
GAME_3 = (15321848, datetime(2026, 10, 2, 1, 0, tzinfo=UTC), "scheduled")
#: A row one Eastern day later than the venue's — what a relisted Game 3 on the
#: wrong day, or Game 4 of a longer series, would look like.
NEXT_DAY = (15399999, datetime(2026, 10, 3, 1, 0, tzinfo=UTC), "scheduled")

PLACEHOLDER = ("1081047", "wnba-ind-las-2026-10-01", "2026-10-01T17:00:00+00:00")


def _event(event_id, commence, status):
    return SimpleNamespace(
        id=event_id,
        home_team_name="Las Vegas Aces",
        away_team_name="Indiana Fever",
        commence_time=commence,
        status=status,
        external_id=None,
        sport=SimpleNamespace(key="basketball_wnba"),
        sport_id=18,
    )


def _market(spec, *, slug=None):
    pm_id, default_slug, venue = spec
    return SimpleNamespace(
        id=63087132,
        source="polymarket",
        external_id="0x651eebc68d945ed247cdc03919bdbdfdb2e5cf0b74fbc5a7fa684b93dc2f564a",
        name="Indiana Fever vs. Las Vegas Aces",
        commence_time=LISTED,
        llm_sport_category="basketball",
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
    """Every pass returns the given rows in commence order."""

    def __init__(self, rows):
        self.rows = rows

    async def execute(self, statement):
        result = MagicMock()
        result.scalars.return_value.unique.return_value.all.return_value = self.rows
        return result


async def _pick(market, rows):
    matchup = extract_matchup_with_ticker_fallback(
        market.name, external_id=market.external_id,
    )
    assert matchup is not None and matchup.team_b, "specimen must parse as a matchup"
    return await _find_matching_event(
        _Session([_event(*r) for r in rows]), matchup, market, NOW,
    )


# ── Reading the stamp ────────────────────────────────────────────────────────
class TestThePlaceholderNamesADay:
    def test_game_3s_placeholder_is_the_eastern_game_day(self):
        day, offset = venue_game_day(_market(PLACEHOLDER))
        assert str(day) == "2026-10-01"
        assert offset.total_seconds() == -4 * 3600

    def test_the_instant_is_left_as_the_venue_gave_it(self):
        # 17:00Z is 1 PM EDT: already the stand-in, so the scorer's reference
        # does not move.
        assert venue_game_start(_market(PLACEHOLDER)) == datetime(2026, 10, 1, 17, 0, tzinfo=UTC)

    def test_a_real_wnba_tip_off_is_untouched(self):
        # Game 2 GS @ DAL after Gamma re-timed it (1081045).
        m = _market(("1081045", "wnba-gsv-dal-2026-09-30", "2026-10-01T01:00:00+00:00"))
        assert venue_game_day(m) is None

    def test_a_stamp_one_minute_off_the_placeholder_is_untouched(self):
        m = _market(("1081047", "wnba-ind-las-2026-10-01", "2026-10-01T17:01:00+00:00"))
        assert venue_game_day(m) is None

    def test_17z_on_another_date_than_the_slug_is_untouched(self):
        m = _market(("1081047", "wnba-ind-las-2026-10-01", "2026-10-02T17:00:00+00:00"))
        assert venue_game_day(m) is None

    def test_another_league_at_the_same_instant_is_untouched(self):
        m = _market(PLACEHOLDER, slug="nba-ind-lv-2026-10-01")
        assert venue_game_day(m) is None
        assert venue_game_start(m) == datetime(2026, 10, 1, 17, 0, tzinfo=UTC)

    def test_a_late_tip_off_on_the_game_day_is_the_same_day(self):
        # 9 PM ET on the 1st is 01:00Z on the 2nd; 9 PM ET on the 2nd is not.
        m = _market(PLACEHOLDER)
        assert not _venue_fixture_disagrees(m, GAME_3[1])
        assert _venue_fixture_disagrees(m, NEXT_DAY[1])


# ── The guard ────────────────────────────────────────────────────────────────
class TestTheFixtureGuardComparesTheDay:
    @pytest.mark.asyncio
    async def test_game_3_admits_its_own_row(self):
        assert await _check_polymarket_fixture_reason(
            _guard_session(GAME_3[1]), GAME_3[0], _market(PLACEHOLDER),
        ) is None

    @pytest.mark.asyncio
    async def test_game_3_is_refused_game_2s_row(self):
        assert await _check_polymarket_fixture_reason(
            _guard_session(GAME_2[1]), GAME_2[0], _market(PLACEHOLDER),
        ) == _REFUSAL_VENUE_FIXTURE

    @pytest.mark.asyncio
    async def test_game_3_is_refused_a_row_a_day_later(self):
        assert await _check_polymarket_fixture_reason(
            _guard_session(NEXT_DAY[1]), NEXT_DAY[0], _market(PLACEHOLDER),
        ) == _REFUSAL_VENUE_FIXTURE

    @pytest.mark.asyncio
    async def test_a_real_17z_tip_off_still_admits_its_own_row(self):
        # Minnesota @ Connecticut 2026-09-20 was a real 17:00Z game.
        m = _market(("981019", "wnba-min-conn-2026-09-20", "2026-09-20T17:00:00+00:00"))
        assert await _check_polymarket_fixture_reason(
            _guard_session(datetime(2026, 9, 20, 17, 0, tzinfo=UTC)), 1, m,
        ) is None
        assert await _check_polymarket_fixture_reason(
            _guard_session(datetime(2026, 9, 21, 17, 0, tzinfo=UTC)), 1, m,
        ) == _REFUSAL_VENUE_FIXTURE

    @pytest.mark.asyncio
    async def test_a_real_instant_keeps_the_three_hour_rule(self):
        # Control: the same 17:00Z on a non-WNBA slug is a tip-off, 8h from the
        # row, and still refused exactly as before.
        m = _market(PLACEHOLDER, slug="nba-ind-lv-2026-10-01")
        assert await _check_polymarket_fixture_reason(
            _guard_session(GAME_3[1]), GAME_3[0], m,
        ) == _REFUSAL_VENUE_FIXTURE


# ── The scorer ───────────────────────────────────────────────────────────────
class TestTheScorerOffersTheRowOnTheVenuesDay:
    @pytest.mark.asyncio
    async def test_game_3_is_offered_game_3(self):
        picked = await _pick(_market(PLACEHOLDER), [GAME_3])
        assert picked is not None and picked["event_id"] == GAME_3[0]

    @pytest.mark.asyncio
    async def test_game_3_is_offered_nothing_on_another_day(self):
        assert await _pick(_market(PLACEHOLDER), [NEXT_DAY]) is None

    @pytest.mark.asyncio
    async def test_another_league_at_17z_is_offered_nothing(self):
        # Control: the pre-fix behaviour, which is what every WNBA placeholder
        # got for 79 passes.
        m = _market(PLACEHOLDER, slug="nba-ind-lv-2026-10-01")
        assert await _pick(m, [GAME_3]) is None


# ── Minting ──────────────────────────────────────────────────────────────────
def test_a_placeholder_never_becomes_a_minted_rows_start():
    commence, source = auto_create_commence_time(_market(PLACEHOLDER), LISTED)
    assert commence != venue_game_start(_market(PLACEHOLDER))
    assert source is None or "polymarket" not in str(source).lower()


def test_a_real_wnba_tip_off_still_mints_at_the_venues_instant():
    m = _market(("1081045", "wnba-gsv-dal-2026-09-30", "2026-10-01T01:00:00+00:00"))
    commence, _ = auto_create_commence_time(m, LISTED)
    assert commence == datetime(2026, 10, 1, 1, 0, tzinfo=UTC)
