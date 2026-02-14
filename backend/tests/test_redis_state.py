"""Tests for redis_state.py helper functions.

Covers:
- compute_odds_hash: deterministic hashing of odds data for change detection
"""

import pytest

from app.tasks.redis_state import compute_odds_hash


def _make_event(event_id="evt1", bookmaker="fanduel", price=-150, point=None):
    """Create a minimal Odds API event structure."""
    outcome = {"name": "Home", "price": price}
    if point is not None:
        outcome["point"] = point
    return {
        "id": event_id,
        "bookmakers": [{
            "key": bookmaker,
            "markets": [{
                "key": "h2h",
                "outcomes": [outcome],
            }],
        }],
    }


class TestComputeOddsHash:
    """Tests for deterministic odds data hashing."""

    def test_deterministic_same_input(self):
        """Same input should always produce the same hash."""
        events = [_make_event()]
        assert compute_odds_hash(events) == compute_odds_hash(events)

    def test_different_price_different_hash(self):
        h1 = compute_odds_hash([_make_event(price=-150)])
        h2 = compute_odds_hash([_make_event(price=-160)])
        assert h1 != h2

    def test_different_bookmaker_different_hash(self):
        h1 = compute_odds_hash([_make_event(bookmaker="fanduel")])
        h2 = compute_odds_hash([_make_event(bookmaker="draftkings")])
        assert h1 != h2

    def test_different_event_id_different_hash(self):
        h1 = compute_odds_hash([_make_event(event_id="evt1")])
        h2 = compute_odds_hash([_make_event(event_id="evt2")])
        assert h1 != h2

    def test_empty_list(self):
        """Empty events list should still produce a valid hash."""
        h = compute_odds_hash([])
        assert isinstance(h, str)
        assert len(h) == 32  # MD5 hex digest length

    def test_event_order_independent(self):
        """Hash should be the same regardless of event order in the list."""
        e1 = _make_event(event_id="a", price=-100)
        e2 = _make_event(event_id="b", price=-200)
        h_forward = compute_odds_hash([e1, e2])
        h_reverse = compute_odds_hash([e2, e1])
        assert h_forward == h_reverse

    def test_returns_md5_hex_string(self):
        h = compute_odds_hash([_make_event()])
        assert isinstance(h, str)
        assert len(h) == 32
        assert all(c in "0123456789abcdef" for c in h)

    def test_with_point_spread(self):
        """Events with point spreads should hash differently from those without."""
        h_no_point = compute_odds_hash([_make_event(point=None)])
        h_with_point = compute_odds_hash([_make_event(point=-3.5)])
        assert h_no_point != h_with_point

    def test_no_bookmakers_key(self):
        """Events without bookmakers should produce a valid hash."""
        h = compute_odds_hash([{"id": "evt1"}])
        assert isinstance(h, str)
        assert len(h) == 32
