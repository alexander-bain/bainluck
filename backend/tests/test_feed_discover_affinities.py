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


def test_discover_feature_affinity_reacts_to_single_like_quickly():
    rows = [
        ("futures", "Will Noah Kahan be #1 on Spotify this week?", "entertainment", "like", 1),
    ]

    result = _build_discover_feature_affinities(rows)

    assert result["archetype:culture_moment"] > 0
    assert result["entity:noah_kahan"] > 0


def test_discover_feature_affinity_uses_unlike_as_soft_downrank():
    rows = [
        ("event", "Red Sox vs Yankees", "baseball", "unlike", 2),
    ]

    result = _build_discover_feature_affinities(rows)

    assert result["format:matchup"] < 0
