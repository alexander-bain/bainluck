"""Tests for Discover interaction signals used by feed personalization."""

import pytest

from app.routes.feed import (
    _build_discover_category_affinities,
    _build_discover_feature_affinities,
    _discover_feature_tokens,
    _discover_semantic_tokens,
)


def test_discover_category_affinity_requires_two_signals():
    rows = [("tech", "context_expand", 1)]

    assert _build_discover_category_affinities(rows) == {}


def test_discover_category_affinity_counts_context_expands_as_interest():
    rows = [
        ("tech", "context_expand", 1),
        ("tech", "share", 1),
        ("_pad", "open", 20),  # push above cold-start threshold
    ]

    result = _build_discover_category_affinities(rows)

    assert result["tech"] == pytest.approx((0.35 + 3.0) / 20.0)


def test_discover_category_affinity_caps_positive_interest():
    rows = [
        ("entertainment", "share", 10),
        ("entertainment", "context_expand", 10),
    ]

    result = _build_discover_category_affinities(rows)

    assert result["entertainment"] == 0.18


def test_discover_category_affinity_caps_dismiss_penalty():
    rows = [
        ("politics", "dismiss", 10),
        ("politics", "context_collapse", 5),
    ]

    result = _build_discover_category_affinities(rows)

    # 10 dismisses → n_negative=10 >= 8 and score=-20 < -12 → deepest tier floor -0.80
    assert result["politics"] == -0.80


def test_discover_category_affinity_ignores_unknown_actions_and_empty_categories():
    rows = [
        (None, "share", 10),
        ("weather", "impression", 50),
        ("weather", "context_expand", 1),
    ]

    assert _build_discover_category_affinities(rows) == {}


def test_discover_category_affinity_counts_unlike_as_soft_downrank():
    rows = [
        ("soccer", "unlike", 3),
        ("soccer", "context_expand", 1),
        ("_pad", "open", 20),  # push above cold-start threshold
    ]

    result = _build_discover_category_affinities(rows)

    assert result["soccer"] == pytest.approx((-3.0 + 0.35) / 20.0)


def test_discover_category_affinity_escalates_repeated_unlikes():
    rows = [
        ("baseball", "unlike", 10),
        ("baseball", "context_collapse", 1),
        ("_pad", "open", 20),  # push above cold-start threshold
    ]

    result = _build_discover_category_affinities(rows)

    # 10 unlikes → raw=-10, n_negative=10 >= 5, score < -8 → floor -0.60
    # affinity = max(-0.60, -10/20) = max(-0.60, -0.50) = -0.50
    assert result["baseball"] == -0.50


def test_discover_feature_tokens_include_archetype_and_entities():
    tokens = _discover_feature_tokens(
        item_name="Will Noah Kahan be #1 on Spotify this week?",
        category="entertainment",
        item_type="futures",
    )

    assert "archetype:culture_moment" in tokens
    assert "topic:entertainment_charts" in tokens
    assert "entity:noah_kahan" in tokens


def test_discover_semantic_tokens_bridge_league_champion_language():
    dismissed = _discover_semantic_tokens(
        item_name="Chilean Primera Division champion",
        category="soccer",
        item_type="futures",
    )
    candidate = _discover_semantic_tokens(
        item_name="Who wins the Chilean league?",
        category="soccer",
        item_type="futures",
    )

    assert dismissed & candidate >= {"term:chilean", "term:league", "term:win"}
    assert len(dismissed & candidate) / len(dismissed | candidate) > 0.60


def test_discover_feature_tokens_bridge_boston_teams_to_massachusetts():
    red_sox_tokens = _discover_feature_tokens(
        item_name="Tampa Bay Rays vs Boston Red Sox",
        category="baseball",
        item_type="event",
    )
    election_tokens = _discover_feature_tokens(
        item_name="Who will win the Massachusetts Governor election?",
        category="politics",
        item_type="futures",
    )

    assert "team:boston_red_sox" in red_sox_tokens
    assert "region:boston" in red_sox_tokens
    assert "region:massachusetts" in red_sox_tokens
    assert "region:new_england" in red_sox_tokens
    assert "region:massachusetts" in election_tokens
    assert "region:new_england" in election_tokens
    assert red_sox_tokens & election_tokens >= {
        "region:massachusetts",
        "region:new_england",
    }


def test_discover_feature_tokens_bridge_new_england_patriots_to_massachusetts():
    tokens = _discover_feature_tokens(
        item_name="Buffalo Bills vs New England Patriots",
        category="football",
        item_type="event",
    )

    assert "team:new_england_patriots" in tokens
    assert "region:massachusetts" in tokens
    assert "region:new_england" in tokens
    assert "region:boston" not in tokens


def test_discover_feature_affinity_reacts_to_single_like_quickly():
    rows = [
        ("futures", "Will Noah Kahan be #1 on Spotify this week?", "entertainment", "like", 1),
    ]

    result = _build_discover_feature_affinities(rows)

    assert result["archetype:culture_moment"] > 0
    assert result["entity:noah_kahan"] > 0


def test_discover_feature_affinity_liked_red_sox_boosts_regional_bridges():
    rows = [
        ("event", "Tampa Bay Rays vs Boston Red Sox", "baseball", "like", 1),
    ]

    result = _build_discover_feature_affinities(rows)

    assert result["team:boston_red_sox"] > 0
    assert result["region:boston"] > 0
    assert result["region:massachusetts"] > 0
    assert result["region:new_england"] > 0


def test_discover_feature_affinity_region_bridge_can_connect_team_and_local_market():
    rows = [
        ("event", "Tampa Bay Rays vs Boston Red Sox", "baseball", "like", 1),
        (
            "futures",
            "Who will win the Massachusetts Governor election?",
            "politics",
            "context_expand",
            2,
        ),
    ]

    result = _build_discover_feature_affinities(rows)

    assert result["region:massachusetts"] > result["team:boston_red_sox"]
    assert result["region:new_england"] > result["team:boston_red_sox"]
    assert result["topic:elections"] > 0


def test_discover_feature_affinity_uses_unlike_as_soft_downrank():
    rows = [
        ("event", "Red Sox vs Yankees", "baseball", "unlike", 2),
    ]

    result = _build_discover_feature_affinities(rows)

    assert result["format:matchup"] < 0


def test_discover_feature_affinity_unlike_downranks_team_and_regions_softly():
    rows = [
        ("event", "Tampa Bay Rays vs Boston Red Sox", "baseball", "unlike", 1),
    ]

    result = _build_discover_feature_affinities(rows)

    assert result["team:boston_red_sox"] == pytest.approx(-1.0 / 18.0)
    assert result["region:boston"] == pytest.approx(-1.0 / 18.0)
    assert result["region:massachusetts"] == pytest.approx(-1.0 / 18.0)
    assert result["region:new_england"] == pytest.approx(-1.0 / 18.0)


def test_discover_feature_affinity_repeated_unlikes_are_bounded_downranks():
    rows = [
        ("event", "Tampa Bay Rays vs Boston Red Sox", "baseball", "unlike", 10),
    ]

    result = _build_discover_feature_affinities(rows)

    assert result["team:boston_red_sox"] == -0.12
    assert result["region:massachusetts"] == -0.12


# =============================================================================
# Cold-start fast-lane (#850)
# =============================================================================


def test_cold_start_2x_weight_reaches_floor_with_2_dismisses():
    """With < 20 total interactions, 2 dismisses in one category should reach
    the -0.40 floor that previously required 3+ dismisses."""
    from app.routes.feed import _build_discover_category_affinities

    # 2 dismiss actions, total interactions = 2 (< 20 threshold)
    rows = [("politics", "dismiss", 2)]
    result = _build_discover_category_affinities(rows)
    assert result.get("politics", 0) <= -0.40, (
        f"Cold-start 2x weight should make 2 dismisses reach -0.40 floor, got {result.get('politics')}"
    )


def test_no_boost_above_20_interactions():
    """With >= 20 total interactions, normal weights apply — 2 dismisses
    should NOT reach -0.40."""
    from app.routes.feed import _build_discover_category_affinities

    # 2 dismiss + 18 other interactions = 20 total (no boost)
    rows = [("politics", "dismiss", 2), ("sports", "open", 18)]
    result = _build_discover_category_affinities(rows)
    assert result.get("politics", 0) > -0.40, (
        f"Above 20 interactions, 2 dismisses should NOT reach -0.40, got {result.get('politics')}"
    )


def test_cold_start_diversify_first_page_spread():
    """Cold-start mode should produce >= 5 distinct category groups in first 8 cards."""
    from app.utils.feed_market_quality import diversify_discover_first_page

    # Build 20 items across 6 categories, 3-4 each
    categories = ["politics", "economics", "tech", "sports", "entertainment", "weather"]
    items = []
    for i, cat in enumerate(categories * 4):
        items.append({
            "id": i,
            "type": "futures",
            "score": 100 - i,
            "llm_sport_category": cat,
            "_quality_story_key": f"story_{cat}_{i}",
        })

    result = diversify_discover_first_page(
        items[:24], first_page_size=20, cold_start=True
    )

    first_8_groups = set()
    for item in result[:8]:
        cat = item.get("llm_sport_category", "other")
        first_8_groups.add(cat)

    assert len(first_8_groups) >= 5, (
        f"Cold-start first 8 cards should have >= 5 category groups, got {len(first_8_groups)}: {first_8_groups}"
    )
