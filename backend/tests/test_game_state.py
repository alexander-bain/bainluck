from datetime import datetime, timezone

from app.models import Event, Sport
from app.routes.events import _format_event
from app.utils.feed_scoring import format_event_data
from app.utils.game_state import normalize_live_game_state


def test_baseball_uses_inning_from_period_and_omits_clock():
    period, clock = normalize_live_game_state("baseball_mlb", "Top 1st", "Top 1")

    assert period == "Top 1st"
    assert clock is None


def test_baseball_uses_inning_from_clock_when_period_is_wrong_half_label():
    period, clock = normalize_live_game_state("baseball_mlb", "HT", "Bottom 2")

    assert period == "Bottom 2nd"
    assert clock is None


def test_baseball_suppresses_half_label_when_no_inning_is_available():
    period, clock = normalize_live_game_state("baseball_mlb", "2H", None)

    assert period is None
    assert clock is None


def test_non_baseball_state_is_unchanged():
    period, clock = normalize_live_game_state("basketball_nba", "2H", "12:00")

    assert period == "2H"
    assert clock == "12:00"


def test_event_response_formats_baseball_inning_indicator():
    sport = Sport(id=1, key="baseball_mlb", name="MLB")
    event = Event(
        id=10,
        sport_id=1,
        sport=sport,
        home_team_name="Dodgers",
        away_team_name="Giants",
        commence_time=datetime(2026, 5, 17, 20, 0, tzinfo=timezone.utc),
        status="live",
        home_score=1,
        away_score=0,
        period="HT",
        game_clock="Top 1",
    )

    data = _format_event(event)

    assert data["espn"]["period"] == "Top 1st"
    assert "game_clock" not in data["espn"]


def test_feed_event_response_formats_baseball_inning_indicator():
    data = format_event_data(
        event_id=10,
        external_id="mlb-10",
        sport_key="baseball_mlb",
        sport_name="MLB",
        home_team="Dodgers",
        away_team="Giants",
        commence_time=datetime(2026, 5, 17, 20, 0, tzinfo=timezone.utc),
        status="live",
        home_score=1,
        away_score=0,
        current_home_prob=None,
        current_away_prob=None,
        opening_home_prob=None,
        opening_away_prob=None,
        opening_favorite=None,
        win_probability_sources=None,
        prob_source=None,
        game_clock="Bottom 2",
        period="2H",
        broadcast_info=None,
        highlight_label=None,
        raw_ei=None,
        inline_tags=[],
        ended_at=None,
    )

    assert data["espn"]["period"] == "Bottom 2nd"
    assert "game_clock" not in data["espn"]
