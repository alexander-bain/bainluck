"""Tests for Discover interaction signals used by feed personalization."""

import pytest

from app.routes.feed import _build_discover_category_affinities


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

    assert result["politics"] == -0.15


def test_discover_category_affinity_ignores_unknown_actions_and_empty_categories():
    rows = [
        (None, "share", 10),
        ("weather", "impression", 50),
        ("weather", "context_expand", 1),
    ]

    assert _build_discover_category_affinities(rows) == {}
