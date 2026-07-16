"""Guard test for #210 Item 2's dominant-plurality safe-subset predicate.

The one-shot cleanup only unlinks foreign strays from events where ONE game
clearly dominates. Ties and flat esports dumps must be deferred (never
false-drop a real game on the durable data path).
"""
from scripts.fix_210_dominant_plurality import _dominant_code


class TestDominantCode:
    def test_supermajority_is_dominant(self):
        assert _dominant_code({"A": 8, "B": 2}) == "A"

    def test_exactly_60pct_is_dominant(self):
        assert _dominant_code({"A": 6, "B": 4}) == "A"

    def test_double_the_runner_up_is_dominant(self):
        assert _dominant_code({"A": 4, "B": 2}) == "A"

    def test_three_way_clear_dominant(self):
        assert _dominant_code({"A": 10, "B": 2, "C": 1}) == "A"

    def test_slim_plurality_deferred(self):
        # 55% and < 2x runner-up — not safe.
        assert _dominant_code({"A": 11, "B": 9}) is None

    def test_tie_deferred(self):
        assert _dominant_code({"A": 3, "B": 3}) is None

    def test_singleton_spread_deferred(self):
        assert _dominant_code({"A": 1, "B": 1, "C": 1}) is None

    def test_flat_esports_dump_deferred(self):
        assert _dominant_code({"A": 2, "B": 2, "C": 2, "D": 2}) is None

    def test_single_code_not_dominant(self):
        # Only one code means no foreign strays to resolve.
        assert _dominant_code({"A": 5}) is None

    def test_top_must_have_min_markets(self):
        # A unique max of 1 market is too thin to trust as "the game".
        assert _dominant_code({"A": 1, "B": 0}) is None
