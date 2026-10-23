"""An NHL puck-line handicap must not become an expected scoring margin."""

import pytest

from app.utils.win_probability import (
    compute_statistical_win_prob,
    model_pregame_spread,
)


@pytest.mark.parametrize("sport", ["hockey_nhl", "icehockey_nhl"])
@pytest.mark.parametrize("handicap", [-1.5, 1.5])
@pytest.mark.parametrize("opening", [.5756, .4244])
def test_puck_drop_uses_opening_price_not_handicap(sport, handicap, opening):
    result = compute_statistical_win_prob(
        0, 0, "20:00", "1st Period", sport,
        pregame_spread=handicap, opening_home_probability=opening,
    )
    # The model's approximate inverse CDF has a small numerical error.
    assert result == pytest.approx(opening, abs=.0002)


@pytest.mark.parametrize("score,clock,expected", [
    (0, "18:41", .574634720),
    (1, "5:27", .734080836),
])
def test_retained_bruins_states_use_the_opening_moneyline(score, clock, expected):
    result = compute_statistical_win_prob(
        score, 0, clock, "1st Period", "icehockey_nhl",
        pregame_spread=-1.5, opening_home_probability=.5756,
    )
    assert result == pytest.approx(expected, abs=1e-8)


@pytest.mark.parametrize("sport,spread,expected", [
    ("baseball_mlb", -1.5, None),
    ("baseball_ncaa", 1.5, None),
    ("football_nfl", -7., -7.),
    ("americanfootball_nfl", 3., 3.),
    ("basketball_nba", -5., -5.),
    ("basketball_ncaab", 4., 4.),
])
def test_other_sport_prior_selection_is_preserved(sport, spread, expected):
    assert model_pregame_spread(sport, spread) == expected


@pytest.mark.parametrize("opening", [None, .5756])
async def test_existing_model_writer_applies_prior_and_priorless_deferral(opening, monkeypatch):
    from tests.test_priorless_stat_model_defers_to_market_8522 import (
        _live_row_on_disk, _run_writer, _stored, STAMP,
    )
    from tests.nonvenue_writer_seam import portable_nonvenue_write

    # Reuse the existing SQLite writer seam; PostgreSQL publication is not
    # changed here. Exercise the real writer's prior and deferral decisions.
    monkeypatch.setattr(
        "app.utils.nonvenue_live_push.write_nonvenue_probability",
        portable_nonvenue_write,
    )

    session, event = _live_row_on_disk(
        sources={"kalshi": {"value": .5756, "updated_at": STAMP}},
        opening_home_probability=opening,
    )
    engine = session.get_bind()
    try:
        event.opening_home_spread = -1.5
        session.commit()
        wrote, stats = await _run_writer(session, event)
        stored, snapshots = _stored(session)
        if opening is None:
            assert wrote is False
            assert stats["stat_model_priorless_deferred"] == 1
            assert "stat_model" not in stored.win_probability_sources
            assert snapshots == []
        else:
            assert wrote is True
            assert "stat_model_priorless_deferred" not in stats
            assert stored.win_probability_sources["stat_model"]["value"] == pytest.approx(opening, abs=.002)
            assert len(snapshots) == 1
    finally:
        session.close()
        engine.dispose()
