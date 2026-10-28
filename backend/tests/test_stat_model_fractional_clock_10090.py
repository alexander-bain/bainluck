"""#10090: ESPN's fractional clock must not suppress an eligible model update."""

import pytest
from sqlalchemy import select

from app.models.models import Event, WinProbSnapshot
from app.utils.espn_helpers import compute_and_write_stat_model
from app.utils.win_probability import compute_statistical_win_prob, parse_game_clock
from tests.test_priorless_stat_model_defers_to_market_8522 import (
    _portable_probability_writer as _writer_fixture,
)
from tests.test_espn_orientation_by_identity_7338 import (
    UVA,
    WVU,
    _AsyncShim,
    _espn_board_row,
    _live_row_on_disk,
)

# Reuse the existing writer seam; these tests exercise the real ESPN/model
# decision and snapshot writer, but SQLite is not a PostgreSQL/fanout proof.
_portable_probability_writer = _writer_fixture


@pytest.mark.parametrize("clock", ["20.5", "0:20.5", " 20.5 "])
@pytest.mark.parametrize("period,expected", [("Q1", 2180.5), ("Q4", 20.5), ("OT", 20.5)])
def test_fractional_seconds_keep_the_real_game_position(clock, period, expected):
    assert parse_game_clock(clock, period, "basketball_nba") == expected


@pytest.mark.parametrize("clock", ["NaN", "Infinity", "-0.5", "1e1", "60.5", "0:60.5", "0:20.", ".5", "0:NaN", "0:20.5:0"])
def test_malformed_fractional_clocks_still_refuse(clock):
    assert parse_game_clock(clock, "Q4", "basketball_nba") is None


@pytest.mark.parametrize("clock", ["20.5", "0:20.5"])
@pytest.mark.asyncio
async def test_espn_fractional_clock_updates_model_and_chart_snapshot(clock):
    session, event = _live_row_on_disk()
    try:
        event.opening_home_probability = 0.6
        event.win_probability_sources = {"kalshi": 0.55, "stat_model": 0.51}
        session.commit()
        reading = _espn_board_row(
            home_team=WVU, away_team=UVA, home_score=100, away_score=98,
            clock=clock, status_detail="4th Quarter",
        )
        reading.period = 4
        stats = {}
        wrote = await compute_and_write_stat_model(
            _AsyncShim(session), event, reading, "basketball_nba", stats,
        )
        assert wrote, "a valid last-minute clock must reach the model writer"
        session.commit()
        session.expire_all()
        row = session.execute(select(Event)).scalar_one()
        expected = compute_statistical_win_prob(
            home_score=100, away_score=98, clock="0:20.5", period="4",
            sport_key="basketball_nba", opening_home_probability=0.6,
        )
        assert row.win_probability_sources["stat_model"]["value"] == round(expected, 4)
        assert row.win_probability_sources["kalshi"] == 0.55
        point = session.execute(select(WinProbSnapshot)).scalar_one()
        assert point.source == "stat_model"
        assert float(point.home_win_probability) == round(expected, 4)
        assert point.game_state["clock"] == clock
        assert stats.get("stat_model_errors", 0) == 0
    finally:
        session.close()
        session.bind.dispose()
