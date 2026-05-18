"""Tests for prediction-market link-rate denominator guards."""

from app.routes.admin_matching import (
    _LINK_RATE_SPORT_CATEGORIES,
    _is_obvious_non_game_market_name,
    _should_include_link_rate_bucket,
)


def test_link_rate_bucket_excludes_unsupported_esports():
    assert "esports" not in _LINK_RATE_SPORT_CATEGORIES
    assert _should_include_link_rate_bucket("esports", "LOL") is False


def test_link_rate_bucket_rejects_impossible_sport_league_pairs():
    assert _should_include_link_rate_bucket("basketball", "NBA") is True
    assert _should_include_link_rate_bucket("basketball", "NHL") is False
    assert _should_include_link_rate_bucket("hockey", "NBA") is False


def test_obvious_non_game_market_name_detection():
    assert _is_obvious_non_game_market_name("Who will win the NBA Championship?") is True
    assert _is_obvious_non_game_market_name("Celtics vs Knicks") is False
    assert _is_obvious_non_game_market_name("Will Celtics win the game vs Knicks?") is False
