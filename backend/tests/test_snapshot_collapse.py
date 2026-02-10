"""Tests for snapshot collapse (data retention) logic.

Tests the core algorithm: given an ordered list of snapshots for one partition
(event+bookmaker), identify consecutive runs of identical values and mark
which rows should be absorbed vs kept.
"""

import pytest
from datetime import datetime, timezone, timedelta


class FakeSnapshot:
    """Minimal snapshot stand-in for testing collapse logic."""

    def __init__(self, id, captured_at, value, reading_count=1, valid_until=None):
        self.id = id
        self.captured_at = captured_at
        self.home_win_probability = value
        self.reading_count = reading_count
        self.valid_until = valid_until


def collapse_rows(rows):
    """Pure-function version of the collapse logic from tasks.py.

    Returns (keepers, ids_to_delete) where keepers have updated
    reading_count and valid_until.
    """
    if len(rows) <= 1:
        return rows, []

    ids_to_delete = []
    keeper = rows[0]

    for row in rows[1:]:
        keeper_val = keeper.home_win_probability
        row_val = row.home_win_probability

        vals_equal = False
        if keeper_val is None and row_val is None:
            vals_equal = True
        elif keeper_val is not None and row_val is not None:
            vals_equal = float(keeper_val) == float(row_val)

        if vals_equal:
            last_time = row.valid_until or row.captured_at
            keeper.valid_until = last_time
            keeper.reading_count = (keeper.reading_count or 1) + (row.reading_count or 1)
            ids_to_delete.append(row.id)
        else:
            if keeper.valid_until is None:
                keeper.valid_until = row.captured_at
            keeper = row

    return [r for r in rows if r.id not in ids_to_delete], ids_to_delete


def _ts(minutes):
    """Helper: return a UTC datetime offset by N minutes from a base time."""
    base = datetime(2026, 2, 1, 12, 0, 0, tzinfo=timezone.utc)
    return base + timedelta(minutes=minutes)


class TestCollapseAlgorithm:
    def test_single_row_unchanged(self):
        rows = [FakeSnapshot(1, _ts(0), 0.55)]
        keepers, deleted = collapse_rows(rows)
        assert len(keepers) == 1
        assert len(deleted) == 0

    def test_empty_list(self):
        keepers, deleted = collapse_rows([])
        assert len(keepers) == 0
        assert len(deleted) == 0

    def test_two_identical_rows_collapsed(self):
        rows = [
            FakeSnapshot(1, _ts(0), 0.55),
            FakeSnapshot(2, _ts(1), 0.55),
        ]
        keepers, deleted = collapse_rows(rows)
        assert len(keepers) == 1
        assert deleted == [2]
        assert keepers[0].id == 1
        assert keepers[0].reading_count == 2
        assert keepers[0].valid_until == _ts(1)

    def test_two_different_rows_kept(self):
        rows = [
            FakeSnapshot(1, _ts(0), 0.55),
            FakeSnapshot(2, _ts(1), 0.60),
        ]
        keepers, deleted = collapse_rows(rows)
        assert len(keepers) == 2
        assert len(deleted) == 0
        # First row's valid_until set to second row's captured_at
        assert keepers[0].valid_until == _ts(1)

    def test_long_run_of_identical_values(self):
        """10 identical rows collapse to 1."""
        rows = [FakeSnapshot(i, _ts(i), 0.50) for i in range(10)]
        keepers, deleted = collapse_rows(rows)
        assert len(keepers) == 1
        assert len(deleted) == 9
        assert keepers[0].reading_count == 10
        assert keepers[0].valid_until == _ts(9)

    def test_alternating_values_no_collapse(self):
        """No two consecutive rows are the same."""
        rows = [
            FakeSnapshot(1, _ts(0), 0.50),
            FakeSnapshot(2, _ts(1), 0.55),
            FakeSnapshot(3, _ts(2), 0.50),
            FakeSnapshot(4, _ts(3), 0.55),
        ]
        keepers, deleted = collapse_rows(rows)
        assert len(keepers) == 4
        assert len(deleted) == 0

    def test_runs_of_different_values(self):
        """Two distinct runs: 3×0.50 then 3×0.60."""
        rows = [
            FakeSnapshot(1, _ts(0), 0.50),
            FakeSnapshot(2, _ts(1), 0.50),
            FakeSnapshot(3, _ts(2), 0.50),
            FakeSnapshot(4, _ts(3), 0.60),
            FakeSnapshot(5, _ts(4), 0.60),
            FakeSnapshot(6, _ts(5), 0.60),
        ]
        keepers, deleted = collapse_rows(rows)
        assert len(keepers) == 2
        assert len(deleted) == 4
        # First keeper: id=1, covers 0.50 run
        assert keepers[0].id == 1
        assert keepers[0].reading_count == 3
        assert keepers[0].valid_until == _ts(2)
        # Second keeper: id=4, covers 0.60 run
        assert keepers[1].id == 4
        assert keepers[1].reading_count == 3
        assert keepers[1].valid_until == _ts(5)

    def test_reading_count_summed_correctly(self):
        """Pre-existing reading_counts are summed, not overwritten."""
        rows = [
            FakeSnapshot(1, _ts(0), 0.50, reading_count=5),
            FakeSnapshot(2, _ts(1), 0.50, reading_count=3),
            FakeSnapshot(3, _ts(2), 0.50, reading_count=10),
        ]
        keepers, deleted = collapse_rows(rows)
        assert len(keepers) == 1
        assert keepers[0].reading_count == 18  # 5 + 3 + 10

    def test_valid_until_from_last_row_preserved(self):
        """If last row has valid_until set, keeper inherits it."""
        rows = [
            FakeSnapshot(1, _ts(0), 0.50),
            FakeSnapshot(2, _ts(1), 0.50, valid_until=_ts(5)),
        ]
        keepers, deleted = collapse_rows(rows)
        assert keepers[0].valid_until == _ts(5)

    def test_none_values_treated_as_equal(self):
        """Two None probabilities are considered identical."""
        rows = [
            FakeSnapshot(1, _ts(0), None),
            FakeSnapshot(2, _ts(1), None),
        ]
        keepers, deleted = collapse_rows(rows)
        assert len(keepers) == 1
        assert deleted == [2]

    def test_none_vs_value_not_equal(self):
        """None and a real value are different."""
        rows = [
            FakeSnapshot(1, _ts(0), None),
            FakeSnapshot(2, _ts(1), 0.50),
        ]
        keepers, deleted = collapse_rows(rows)
        assert len(keepers) == 2
        assert len(deleted) == 0

    def test_realistic_game_pattern(self):
        """Simulate a realistic pattern: pre-game stability, live movement, post-game stability.

        Pre-game: 5 identical readings at 0.55
        Live: 0.55, 0.52, 0.48, 0.45, 0.50, 0.55
        Post-game: 3 identical readings at 0.55
        Expected: pre-game collapses to 1, live stays as 6, post-game collapses to 1
        But the last live 0.55 and the 3 post-game 0.55 also collapse together.
        """
        rows = [
            # Pre-game (all 0.55)
            FakeSnapshot(1, _ts(0), 0.55),
            FakeSnapshot(2, _ts(1), 0.55),
            FakeSnapshot(3, _ts(2), 0.55),
            FakeSnapshot(4, _ts(3), 0.55),
            FakeSnapshot(5, _ts(4), 0.55),
            # Live movement
            FakeSnapshot(6, _ts(5), 0.55),  # same as pre-game, will collapse with above
            FakeSnapshot(7, _ts(6), 0.52),
            FakeSnapshot(8, _ts(7), 0.48),
            FakeSnapshot(9, _ts(8), 0.45),
            FakeSnapshot(10, _ts(9), 0.50),
            FakeSnapshot(11, _ts(10), 0.55),
            # Post-game (all 0.55, same as last live)
            FakeSnapshot(12, _ts(11), 0.55),
            FakeSnapshot(13, _ts(12), 0.55),
            FakeSnapshot(14, _ts(13), 0.55),
        ]
        keepers, deleted = collapse_rows(rows)
        # Kept: id=1 (0.55 run), 7 (0.52), 8 (0.48), 9 (0.45), 10 (0.50), 11 (0.55 run)
        assert len(keepers) == 6
        assert len(deleted) == 8
        keeper_ids = [k.id for k in keepers]
        assert keeper_ids == [1, 7, 8, 9, 10, 11]

    def test_exact_match_not_fuzzy(self):
        """0.5000 and 0.5001 are NOT collapsed (exact match only)."""
        rows = [
            FakeSnapshot(1, _ts(0), 0.5000),
            FakeSnapshot(2, _ts(1), 0.5001),
        ]
        keepers, deleted = collapse_rows(rows)
        assert len(keepers) == 2
        assert len(deleted) == 0
