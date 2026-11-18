from datetime import datetime, timedelta, timezone

from app.routes.league_futures import _format_game_brief
from app.utils.aggregation import compute_aggregate_probability, stamp_source_reading
from tests.test_league_games_rail_probability import FakeEvent


def test_league_rail_explains_the_same_pair_with_bound_observations():
    now = datetime.now(timezone.utc)
    read_at = now - timedelta(seconds=7)
    readings = stamp_source_reading({}, "kalshi", 0.62, now=now, price_read_at=read_at)
    readings = stamp_source_reading(readings, "polymarket", 0.60, now=now)
    event = FakeEvent(sources=readings, status="live")
    event.commence_time = now - timedelta(minutes=10)

    brief = _format_game_brief(event, "basketball_nba")

    home = compute_aggregate_probability(event)
    assert brief["home_win_probability"] == home
    assert brief["current_odds"] == {
        "home_probability": home,
        "away_probability": round(1 - home, 6),
    }
    home_mark = brief["source_mark"]
    away_mark = brief["away_source_mark"]
    assert home_mark["state"] == away_mark["state"] == "blend"
    assert [mark["key"] for mark in home_mark["sources"]] == ["kalshi", "polymarket"]
    assert [mark["probability"] for mark in home_mark["sources"]] == [0.62, 0.60]
    assert [mark["probability"] for mark in away_mark["sources"]] == [0.38, 0.40]
    observed = read_at.isoformat().replace("+00:00", "Z")
    for mark in (home_mark, away_mark):
        assert [source["observed_at"] for source in mark["sources"]] == [observed, None]


def test_legacy_espn_quote_keeps_its_source_and_an_unknown_clock():
    brief = _format_game_brief(FakeEvent(espn=0.68), "basketball_nba")

    assert brief["source_mark"] == {
        "state": "single",
        "sources": [
            {
                "key": "espn",
                "name": "ESPN",
                "probability": 0.68,
                "observed_at": None,
                "reason": "observation_unknown",
            }
        ],
    }


def test_draw_priced_game_does_not_attribute_a_fabricated_away_quote():
    brief = _format_game_brief(FakeEvent(espn=0.68), "soccer_epl")

    assert brief["source_mark"]["state"] == "single"
    assert brief["current_odds"]["away_probability"] == 0.32
    assert brief["away_source_mark"] == {
        "state": "none",
        "sources": [],
        "reason": "away_unavailable",
    }


def test_historical_opening_pair_does_not_gain_current_source_marks():
    brief = _format_game_brief(
        FakeEvent(opening=0.71, opening_away=0.29), "basketball_nba"
    )

    assert brief["home_win_probability"] is None
    assert "current_odds" not in brief
    assert "source_mark" not in brief
    assert "away_source_mark" not in brief
    assert brief["opening_odds"] == {"home_probability": 0.71, "away_probability": 0.29}
