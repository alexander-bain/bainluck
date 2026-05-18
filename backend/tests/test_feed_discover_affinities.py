"""Tests for Discover interaction signals used by feed personalization."""

import pytest

from app.routes.feed import (
    _build_discover_category_affinities,
    _build_discover_feature_affinities,
    _discover_feature_tokens,
)


def test_discover_category_affinity_requires_two_signals():
    rows = [("tech", "context_expand", 1)]

    assert _build_discover_category_affinities(rows) == {}


def test_discover_category_affinity_counts_context_expands_as_interest():
    rows = [
        ("tech", "context_expand", 1),
        ("tech", "share", 1),
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

    assert result["politics"] == -0.40


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
    ]

    result = _build_discover_category_affinities(rows)

    assert result["soccer"] == pytest.approx((-3.0 + 0.35) / 20.0)


def test_discover_category_affinity_escalates_repeated_unlikes():
    rows = [
        ("baseball", "unlike", 10),
        ("baseball", "context_collapse", 1),
    ]

    result = _build_discover_category_affinities(rows)

    assert result["baseball"] == -0.40


def test_discover_feature_tokens_include_archetype_and_entities():
    tokens = _discover_feature_tokens(
        item_name="Will Noah Kahan be #1 on Spotify this week?",
        category="entertainment",
        item_type="futures",
    )

    assert "archetype:culture_moment" in tokens
    assert "topic:entertainment_charts" in tokens
    assert "entity:noah_kahan" in tokens


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
