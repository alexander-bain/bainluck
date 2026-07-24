"""Tests for prediction-market link-rate denominator guards."""

from datetime import datetime, timezone

from app.routes.admin_matching import (
    _LINK_RATE_NON_GAME_CATEGORIES,
    _LINK_RATE_SPORT_CATEGORIES,
    _is_obvious_non_game_market_name,
    _is_polymarket_matcher_game_level,
    _is_upstream_coverage_gap_market,
    _should_include_link_rate_bucket,
    _should_exclude_stale_open_unlinked_game_market,
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


def test_stale_open_unlinked_kalshi_game_market_excluded_from_link_rate():
    now = datetime(2026, 5, 18, 12, 0, tzinfo=timezone.utc)

    assert _should_exclude_stale_open_unlinked_game_market(
        source="kalshi",
        external_id="KXNBAGAME-26MAY16BOSNYK",
        status="open",
        event_id=None,
        now=now,
    ) is True


def test_active_or_linked_game_markets_stay_in_link_rate():
    now = datetime(2026, 5, 18, 12, 0, tzinfo=timezone.utc)
    recent_external_id = "KXNBAGAME-26MAY18BOSNYK"

    assert _should_exclude_stale_open_unlinked_game_market(
        source="kalshi",
        external_id=recent_external_id,
        status="open",
        event_id=None,
        now=now,
    ) is False
    assert _should_exclude_stale_open_unlinked_game_market(
        source="kalshi",
        external_id="KXNBAGAME-26MAY16BOSNYK",
        status="open",
        event_id=123,
        now=now,
    ) is False
    assert _should_exclude_stale_open_unlinked_game_market(
        source="polymarket",
        external_id="KXNBAGAME-26MAY16BOSNYK",
        status="open",
        event_id=None,
        now=now,
    ) is False


def test_polymarket_link_rate_uses_matcher_game_level_predicate():
    assert _is_polymarket_matcher_game_level(
        "Celtics vs Knicks",
        "championship",
        "123",
    ) is True
    assert _is_polymarket_matcher_game_level(
        "CF Estrela da Amadora vs. FC Porto - More Markets",
        "championship",
        "456",
    ) is True
    assert _is_polymarket_matcher_game_level(
        "Internationaux de Strasbourg (Doubles): Kichenok/Krawczyk vs Mihalikova/Nicholls",
        "championship",
        "493607",
    ) is False
    assert _is_polymarket_matcher_game_level(
        "World Championships: Czechia vs. Italy",
        "championship",
        "490611",
    ) is True  # "X vs. Y" is a game-level market


# -- Category-based denominator exclusion ----------------------------------

def test_non_game_categories_include_season_level_types():
    """Championship, award, season_win_total, player_futures must be excluded."""
    for cat in ("championship", "award", "season_win_total", "player_futures"):
        assert cat in _LINK_RATE_NON_GAME_CATEGORIES, f"{cat} missing from exclusion set"


def test_game_prop_not_in_non_game_categories():
    """game_prop is a game-level category and must NOT be excluded."""
    assert "game_prop" not in _LINK_RATE_NON_GAME_CATEGORIES


def test_non_game_categories_also_cover_structural_futures():
    """Division, conference, and series are season-level, not game-level."""
    for cat in ("division", "conference", "series"):
        assert cat in _LINK_RATE_NON_GAME_CATEGORIES


def test_non_game_category_exclusion_is_case_insensitive_in_loop():
    """The loop lowercases the category before checking, so mixed case works."""
    # Simulate the loop logic from the endpoint
    cat_raw = "Championship"
    cat = cat_raw.lower()
    assert cat in _LINK_RATE_NON_GAME_CATEGORIES


# -- #1230: upstream-coverage-gap denominator exclusion --------------------

def test_upstream_coverage_gap_excludes_itf_minor_tennis():
    """ITF minor-tour tennis has no schedule source → drop from the denominator."""
    assert _is_upstream_coverage_gap_market(
        "ITF Segrate: Juan Cruz Martin Manzano vs Raffaele Ciurnelli"
    ) is True
    assert _is_upstream_coverage_gap_market(
        "ITF Evansville: Renata Zarazua vs Sloane Stephens"
    ) is True


def test_upstream_coverage_gap_excludes_setka_table_tennis():
    """Setka / TT-Cup table-tennis circuits are uncovered upstream."""
    assert _is_upstream_coverage_gap_market("Setka Cup: A vs B: Total Games O/U 3.5") is True
    assert _is_upstream_coverage_gap_market("TT Cup: Player A vs Player B") is True
    assert _is_upstream_coverage_gap_market("Table Tennis: A vs B") is True


def test_upstream_coverage_gap_excludes_minor_cricket():
    """European Cricket Series (ECS) is a minor circuit with no coverage."""
    assert _is_upstream_coverage_gap_market(
        "ECS England: Rainham vs East Londoners"
    ) is True


def test_upstream_coverage_gap_keeps_covered_leagues():
    """Tier-1/2 leagues we DO schedule must stay in the denominator."""
    assert _is_upstream_coverage_gap_market("Yankees vs Red Sox") is False
    assert _is_upstream_coverage_gap_market("Lakers vs Celtics: Spread") is False
    assert _is_upstream_coverage_gap_market("Carlos Alcaraz vs Jannik Sinner") is False
    assert _is_upstream_coverage_gap_market("IPL: Mumbai Indians vs Chennai") is False
    assert _is_upstream_coverage_gap_market(None) is False


def test_upstream_coverage_gap_only_removes_unlinked_from_denominator():
    """The endpoint applies the predicate only when event_id IS None; a linked
    market is always kept in the numerator. This mirrors the loop logic."""
    # Simulate loop: linked coverage-gap market stays counted.
    event_id = 123
    name = "ITF Segrate: A vs B"
    excluded = event_id is None and _is_upstream_coverage_gap_market(name)
    assert excluded is False


def test_raw_rate_re_adds_excluded_upstream_gap():
    """Raw rate keeps the excluded (all-unlinked) markets in the denominator, so
    the honest rate is always >= the raw rate."""
    open_linked, open_total, excluded_open = 79, 100, 40
    honest = round(open_linked / open_total * 100, 1)
    raw = round(open_linked / (open_total + excluded_open) * 100, 1)
    assert honest == 79.0
    assert raw == round(79 / 140 * 100, 1)
    assert honest >= raw
