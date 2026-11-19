"""Source marks follow the exact current and pregame numbers on the team page."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.routes.teams import _format_event_brief
from app.utils.aggregation import stamp_source_reading
from tests.test_team_card_probability_5382 import AWAY_TEAM, HOME_TEAM, FakeEvent


def test_team_rows_keep_the_admitted_prices_on_the_viewed_teams_side():
    now = datetime.now(timezone.utc)
    observed = now - timedelta(seconds=7)
    sources = stamp_source_reading({}, "kalshi", 0.62, now=now, price_read_at=observed)
    sources = stamp_source_reading(sources, "polymarket", 0.60, now=now)
    event = FakeEvent(sources=sources, status="live")
    event.commence_time = now - timedelta(minutes=10)

    home = _format_event_brief(event, HOME_TEAM)
    away = _format_event_brief(event, AWAY_TEAM)
    assert home["win_probability"] + away["win_probability"] == pytest.approx(1)
    home_sources = home["source_mark"]["sources"]
    away_sources = away["source_mark"]["sources"]
    assert [source["key"] for source in home_sources] == ["kalshi", "polymarket"]
    assert [source["probability"] for source in home_sources] == [0.62, 0.60]
    assert [source["probability"] for source in away_sources] == [0.38, 0.40]
    stamp = observed.isoformat().replace("+00:00", "Z")
    assert [source["observed_at"] for source in home_sources] == [stamp, None]
    assert [source["observed_at"] for source in away_sources] == [stamp, None]


def test_espn_fallback_is_attributed_without_an_unbound_clock():
    event = FakeEvent(espn=0.78)
    brief = _format_event_brief(event, HOME_TEAM)
    assert brief["win_probability"] == 0.78
    assert brief["source_mark"] == {
        "state": "single",
        "sources": [
            {
                "key": "espn",
                "name": "ESPN",
                "probability": 0.78,
                "observed_at": None,
                "reason": "observation_unknown",
            }
        ],
    }


def test_draw_priced_away_current_chance_is_withheld_but_pregame_remains():
    event = FakeEvent(espn=0.68, opening=0.48, opening_away=0.31)
    event.sport = SimpleNamespace(key="soccer_epl")
    brief = _format_event_brief(event, AWAY_TEAM)
    assert brief["win_probability"] is None
    assert brief["source_mark"] == {
        "state": "none",
        "sources": [],
        "reason": "away_unavailable",
    }
    assert brief["pregame_win_probability"] == 0.31
    assert brief["pregame_source_mark"]["sources"][0] == {
        "key": "betting",
        "name": "Sportsbooks",
        "probability": 0.31,
        "observed_at": None,
        "reason": "observation_unknown",
    }


def test_pregame_mark_uses_selected_venue_input_before_pair_rounding():
    event = FakeEvent(status="completed", opening=0.75, opening_away=0.25)
    brief = _format_event_brief(
        event,
        AWAY_TEAM,
        prematch={
            "source": "kalshi",
            "home_probability": 0.555,
            "away_probability": 0.445,
            "home_rendered_percent": 56,
            "away_rendered_percent": 44,
        },
    )
    assert brief["pregame_win_probability"] == 0.44
    assert brief["pregame_source_mark"]["sources"][0] == {
        "key": "kalshi",
        "name": "Kalshi",
        "probability": 0.445,
        "observed_at": None,
        "reason": "observation_unknown",
    }
