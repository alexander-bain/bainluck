from datetime import datetime, timezone

import pytest

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


@pytest.mark.parametrize(
    ("raw_period", "expected_period"),
    [
        ("Bot 10th inning", "Bottom 10th"),
        ("middle of the 7th", "Mid 7th"),
        ("End 11", "End 11th"),
    ],
)
def test_baseball_formats_common_inning_half_aliases(raw_period, expected_period):
    period, clock = normalize_live_game_state("baseball_mlb", raw_period, "12:00")

    assert period == expected_period
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


def test_feed_event_response_uses_baseball_period_when_scores_and_clock_missing():
    data = format_event_data(
        event_id=11,
        external_id="mlb-11",
        sport_key="baseball_mlb",
        sport_name="MLB",
        home_team="Dodgers",
        away_team="Giants",
        commence_time=datetime(2026, 5, 17, 20, 0, tzinfo=timezone.utc),
        status="live",
        home_score=None,
        away_score=None,
        current_home_prob=None,
        current_away_prob=None,
        opening_home_prob=None,
        opening_away_prob=None,
        opening_favorite=None,
        win_probability_sources=None,
        prob_source=None,
        game_clock=None,
        period="Top 10",
        broadcast_info=None,
        highlight_label=None,
        raw_ei=None,
        inline_tags=[],
        ended_at=None,
    )

    assert data["home_score"] is None
    assert data["away_score"] is None
    assert data["espn"] == {"period": "Top 10th"}


def test_feed_completed_event_does_not_emit_live_state():
    data = format_event_data(
        event_id=12,
        external_id="nba-12",
        sport_key="basketball_nba",
        sport_name="NBA",
        home_team="Lakers",
        away_team="Warriors",
        commence_time=datetime(2026, 5, 17, 20, 0, tzinfo=timezone.utc),
        status="completed",
        home_score=104,
        away_score=101,
        current_home_prob=None,
        current_away_prob=None,
        opening_home_prob=None,
        opening_away_prob=None,
        opening_favorite=None,
        win_probability_sources=None,
        prob_source=None,
        game_clock="0:00",
        period="4Q",
        broadcast_info="ESPN",
        highlight_label=None,
        raw_ei=None,
        inline_tags=[],
        ended_at=datetime(2026, 5, 17, 23, 0, tzinfo=timezone.utc),
    )

    assert "espn" not in data
    assert data["ended_at"] == "2026-05-17T23:00:00+00:00"


def test_event_response_preserves_live_period_when_score_and_clock_missing():
    sport = Sport(id=2, key="basketball_nba", name="NBA")
    event = Event(
        id=13,
        sport_id=2,
        sport=sport,
        home_team_name="Lakers",
        away_team_name="Warriors",
        commence_time=datetime(2026, 5, 17, 20, 0, tzinfo=timezone.utc),
        status="live",
        home_score=None,
        away_score=None,
        period="2Q",
        game_clock=None,
    )

    data = _format_event(event)

    assert data["home_score"] is None
    assert data["away_score"] is None
    assert data["espn"] == {"period": "2Q"}
