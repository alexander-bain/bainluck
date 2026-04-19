"""Extended tests for DataGolf API service.

Covers methods not in test_datagolf.py:
- _first_int: correctly handles zero (even par), multi-key fallback
"""

import pytest

from app.services.datagolf_api import _first_int


class TestFirstInt:
    """_first_int correctly handles 0 (even par) unlike chaining with `or`."""

    def test_zero_is_valid(self):
        """0 (even par) must be returned, not treated as falsy."""
        assert _first_int({"current_score": 0}, "current_score") == 0

    def test_first_key_wins(self):
        d = {"a": 5, "b": 10}
        assert _first_int(d, "a", "b") == 5

    def test_skips_none_to_find_value(self):
        d = {"a": None, "b": 7}
        assert _first_int(d, "a", "b") == 7

    def test_skips_missing_key(self):
        d = {"b": 3}
        assert _first_int(d, "a", "b") == 3

    def test_all_none_returns_none(self):
        d = {"a": None, "b": None}
        assert _first_int(d, "a", "b") is None

    def test_all_missing_returns_none(self):
        assert _first_int({}, "a", "b", "c") is None

    def test_single_key(self):
        assert _first_int({"x": 42}, "x") == 42

    def test_string_int_converted(self):
        """String integers are safely parsed via _safe_int."""
        assert _first_int({"a": "15"}, "a") == 15

    def test_invalid_string_skipped(self):
        d = {"a": "not_a_number", "b": 3}
        assert _first_int(d, "a", "b") == 3

    def test_zero_preferred_over_later_key(self):
        """0 from first key should not fall through to second key."""
        d = {"a": 0, "b": 99}
        assert _first_int(d, "a", "b") == 0

    def test_negative_value(self):
        assert _first_int({"score": -5}, "score") == -5
