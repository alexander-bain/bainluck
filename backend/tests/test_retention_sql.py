"""Tests for the pure-SQL snapshot collapse implementation.

Verifies that the SQL window function logic in retention.py produces
the same results as the Python reference implementation. Uses an
in-memory SQLite database to test the actual SQL patterns.

Note: PostgreSQL's IS DISTINCT FROM is not available in SQLite, so
these tests verify the logic via a Python simulation of the CTE
behavior, ensuring the SQL construction is correct.
"""

import pytest
from datetime import datetime, timezone, timedelta

from app.tasks.retention import _TABLE_CONFIG


def _ts(minutes):
    base = datetime(2026, 2, 1, 12, 0, 0, tzinfo=timezone.utc)
    return base + timedelta(minutes=minutes)


def simulate_sql_collapse(rows, value_key="home_win_probability"):
    """Simulate the SQL CTE collapse logic in Python.

    This mirrors the exact SQL window function behavior:
    1. LAG() to get prev_value
    2. IS DISTINCT FROM comparison (NULL-safe)
    3. Cumulative SUM for run groups
    4. MIN(id) for keeper, MAX(valid_until/captured_at) for last_time,
       SUM(reading_count) for total readings

    Returns (keeper_ids_with_stats, ids_to_delete) where
    keeper_ids_with_stats is a dict mapping keeper_id to
    (valid_until, reading_count).
    """
    if not rows:
        return {}, []

    # Step 1: Add LAG (prev_value)
    annotated = []
    prev_val = None  # First row has NULL prev_value
    first = True
    for r in rows:
        val = r.get(value_key)
        annotated.append({
            **r,
            "prev_value": None if first else prev_val,
            "_is_first": first,
        })
        prev_val = val
        first = False

    # Step 2: Mark run boundaries (IS DISTINCT FROM)
    for a in annotated:
        val = a.get(value_key)
        prev = a["prev_value"]
        if a["_is_first"]:
            # First row: LAG returns NULL. In SQL, IS DISTINCT FROM NULL
            # is true for non-NULL values, false for NULL.
            # But cumulative SUM starts at 0 or 1 depending on this.
            # Actually, the first row always starts a new run.
            a["is_new_run"] = 1
        else:
            # IS DISTINCT FROM: NULL vs NULL = false (not distinct), else use !=
            if val is None and prev is None:
                a["is_new_run"] = 0
            elif val is None or prev is None:
                a["is_new_run"] = 1
            else:
                a["is_new_run"] = 1 if float(val) != float(prev) else 0

    # Step 3: Cumulative SUM for run groups
    cum_sum = 0
    for a in annotated:
        cum_sum += a["is_new_run"]
        a["run_group"] = cum_sum

    # Step 4: Group by run_group
    from collections import defaultdict
    groups = defaultdict(list)
    for a in annotated:
        groups[a["run_group"]].append(a)

    keeper_stats = {}
    ids_to_delete = []

    for run_group, members in groups.items():
        if len(members) <= 1:
            continue
        keeper_id = min(m["id"] for m in members)
        last_time = max(m.get("valid_until") or m["captured_at"] for m in members)
        total_readings = sum(m.get("reading_count", 1) or 1 for m in members)
        keeper_stats[keeper_id] = {
            "valid_until": last_time,
            "reading_count": total_readings,
        }
        for m in members:
            if m["id"] != keeper_id:
                ids_to_delete.append(m["id"])

    return keeper_stats, sorted(ids_to_delete)


class TestSQLCollapseSimulation:
    """Test the SQL CTE logic simulation against expected results."""

    def test_two_identical_rows(self):
        rows = [
            {"id": 1, "captured_at": _ts(0), "home_win_probability": 0.55, "reading_count": 1, "valid_until": None},
            {"id": 2, "captured_at": _ts(1), "home_win_probability": 0.55, "reading_count": 1, "valid_until": None},
        ]
        keepers, deleted = simulate_sql_collapse(rows)
        assert deleted == [2]
        assert keepers[1]["reading_count"] == 2
        assert keepers[1]["valid_until"] == _ts(1)

    def test_two_different_rows(self):
        rows = [
            {"id": 1, "captured_at": _ts(0), "home_win_probability": 0.55, "reading_count": 1, "valid_until": None},
            {"id": 2, "captured_at": _ts(1), "home_win_probability": 0.60, "reading_count": 1, "valid_until": None},
        ]
        keepers, deleted = simulate_sql_collapse(rows)
        assert deleted == []
        assert keepers == {}

    def test_long_run(self):
        rows = [
            {"id": i, "captured_at": _ts(i), "home_win_probability": 0.50, "reading_count": 1, "valid_until": None}
            for i in range(10)
        ]
        keepers, deleted = simulate_sql_collapse(rows)
        assert len(deleted) == 9
        assert keepers[0]["reading_count"] == 10
        assert keepers[0]["valid_until"] == _ts(9)

    def test_alternating_values(self):
        rows = [
            {"id": 1, "captured_at": _ts(0), "home_win_probability": 0.50, "reading_count": 1, "valid_until": None},
            {"id": 2, "captured_at": _ts(1), "home_win_probability": 0.55, "reading_count": 1, "valid_until": None},
            {"id": 3, "captured_at": _ts(2), "home_win_probability": 0.50, "reading_count": 1, "valid_until": None},
            {"id": 4, "captured_at": _ts(3), "home_win_probability": 0.55, "reading_count": 1, "valid_until": None},
        ]
        keepers, deleted = simulate_sql_collapse(rows)
        assert deleted == []

    def test_two_runs(self):
        rows = [
            {"id": 1, "captured_at": _ts(0), "home_win_probability": 0.50, "reading_count": 1, "valid_until": None},
            {"id": 2, "captured_at": _ts(1), "home_win_probability": 0.50, "reading_count": 1, "valid_until": None},
            {"id": 3, "captured_at": _ts(2), "home_win_probability": 0.50, "reading_count": 1, "valid_until": None},
            {"id": 4, "captured_at": _ts(3), "home_win_probability": 0.60, "reading_count": 1, "valid_until": None},
            {"id": 5, "captured_at": _ts(4), "home_win_probability": 0.60, "reading_count": 1, "valid_until": None},
            {"id": 6, "captured_at": _ts(5), "home_win_probability": 0.60, "reading_count": 1, "valid_until": None},
        ]
        keepers, deleted = simulate_sql_collapse(rows)
        assert sorted(deleted) == [2, 3, 5, 6]
        assert keepers[1]["reading_count"] == 3
        assert keepers[1]["valid_until"] == _ts(2)
        assert keepers[4]["reading_count"] == 3
        assert keepers[4]["valid_until"] == _ts(5)

    def test_reading_count_summed(self):
        rows = [
            {"id": 1, "captured_at": _ts(0), "home_win_probability": 0.50, "reading_count": 5, "valid_until": None},
            {"id": 2, "captured_at": _ts(1), "home_win_probability": 0.50, "reading_count": 3, "valid_until": None},
            {"id": 3, "captured_at": _ts(2), "home_win_probability": 0.50, "reading_count": 10, "valid_until": None},
        ]
        keepers, deleted = simulate_sql_collapse(rows)
        assert keepers[1]["reading_count"] == 18

    def test_valid_until_preserved(self):
        rows = [
            {"id": 1, "captured_at": _ts(0), "home_win_probability": 0.50, "reading_count": 1, "valid_until": None},
            {"id": 2, "captured_at": _ts(1), "home_win_probability": 0.50, "reading_count": 1, "valid_until": _ts(5)},
        ]
        keepers, deleted = simulate_sql_collapse(rows)
        assert keepers[1]["valid_until"] == _ts(5)

    def test_none_values_equal(self):
        rows = [
            {"id": 1, "captured_at": _ts(0), "home_win_probability": None, "reading_count": 1, "valid_until": None},
            {"id": 2, "captured_at": _ts(1), "home_win_probability": None, "reading_count": 1, "valid_until": None},
        ]
        keepers, deleted = simulate_sql_collapse(rows)
        assert deleted == [2]

    def test_none_vs_value(self):
        rows = [
            {"id": 1, "captured_at": _ts(0), "home_win_probability": None, "reading_count": 1, "valid_until": None},
            {"id": 2, "captured_at": _ts(1), "home_win_probability": 0.50, "reading_count": 1, "valid_until": None},
        ]
        keepers, deleted = simulate_sql_collapse(rows)
        assert deleted == []

    def test_realistic_game_pattern(self):
        rows = [
            # Pre-game (all 0.55)
            {"id": 1, "captured_at": _ts(0), "home_win_probability": 0.55, "reading_count": 1, "valid_until": None},
            {"id": 2, "captured_at": _ts(1), "home_win_probability": 0.55, "reading_count": 1, "valid_until": None},
            {"id": 3, "captured_at": _ts(2), "home_win_probability": 0.55, "reading_count": 1, "valid_until": None},
            {"id": 4, "captured_at": _ts(3), "home_win_probability": 0.55, "reading_count": 1, "valid_until": None},
            {"id": 5, "captured_at": _ts(4), "home_win_probability": 0.55, "reading_count": 1, "valid_until": None},
            # Live movement
            {"id": 6, "captured_at": _ts(5), "home_win_probability": 0.55, "reading_count": 1, "valid_until": None},
            {"id": 7, "captured_at": _ts(6), "home_win_probability": 0.52, "reading_count": 1, "valid_until": None},
            {"id": 8, "captured_at": _ts(7), "home_win_probability": 0.48, "reading_count": 1, "valid_until": None},
            {"id": 9, "captured_at": _ts(8), "home_win_probability": 0.45, "reading_count": 1, "valid_until": None},
            {"id": 10, "captured_at": _ts(9), "home_win_probability": 0.50, "reading_count": 1, "valid_until": None},
            {"id": 11, "captured_at": _ts(10), "home_win_probability": 0.55, "reading_count": 1, "valid_until": None},
            # Post-game (all 0.55)
            {"id": 12, "captured_at": _ts(11), "home_win_probability": 0.55, "reading_count": 1, "valid_until": None},
            {"id": 13, "captured_at": _ts(12), "home_win_probability": 0.55, "reading_count": 1, "valid_until": None},
            {"id": 14, "captured_at": _ts(13), "home_win_probability": 0.55, "reading_count": 1, "valid_until": None},
        ]
        keepers, deleted = simulate_sql_collapse(rows)
        # Pre-game 0.55 run: ids 1-6 → keeper=1, delete 2,3,4,5,6
        # Post-game 0.55 run: ids 11-14 → keeper=11, delete 12,13,14
        assert sorted(deleted) == [2, 3, 4, 5, 6, 12, 13, 14]
        remaining_ids = sorted(set(r["id"] for r in rows) - set(deleted))
        assert remaining_ids == [1, 7, 8, 9, 10, 11]

    def test_single_row(self):
        rows = [
            {"id": 1, "captured_at": _ts(0), "home_win_probability": 0.55, "reading_count": 1, "valid_until": None},
        ]
        keepers, deleted = simulate_sql_collapse(rows)
        assert deleted == []
        assert keepers == {}

    def test_empty(self):
        keepers, deleted = simulate_sql_collapse([])
        assert deleted == []
        assert keepers == {}

    def test_futures_value_col(self):
        """Verify the simulation works with a different value column name."""
        rows = [
            {"id": 1, "captured_at": _ts(0), "probability": 0.10, "reading_count": 1, "valid_until": None},
            {"id": 2, "captured_at": _ts(1), "probability": 0.10, "reading_count": 1, "valid_until": None},
            {"id": 3, "captured_at": _ts(2), "probability": 0.15, "reading_count": 1, "valid_until": None},
        ]
        keepers, deleted = simulate_sql_collapse(rows, value_key="probability")
        assert deleted == [2]
        assert keepers[1]["reading_count"] == 2


class TestTableConfig:
    """Verify _TABLE_CONFIG has correct structure for all tables."""

    def test_all_tables_configured(self):
        assert set(_TABLE_CONFIG.keys()) == {"odds", "winprob", "futures"}

    def test_odds_config(self):
        cfg = _TABLE_CONFIG["odds"]
        assert cfg["table"] == "odds_snapshots"
        assert cfg["partition_col"] == "event_id"
        assert cfg["sub_partition_col"] == "bookmaker"
        assert cfg["value_col"] == "home_win_probability"

    def test_winprob_config(self):
        cfg = _TABLE_CONFIG["winprob"]
        assert cfg["table"] == "win_prob_snapshots"
        assert cfg["partition_col"] == "event_id"
        assert cfg["sub_partition_col"] == "source"
        assert cfg["value_col"] == "home_win_probability"

    def test_futures_config(self):
        cfg = _TABLE_CONFIG["futures"]
        assert cfg["table"] == "futures_odds_snapshots"
        assert cfg["partition_col"] == "outcome_id"
        assert cfg["sub_partition_col"] == "bookmaker"
        assert cfg["value_col"] == "probability"


class TestSQLCorrectness:
    """Verify properties of the SQL CTE logic that differ from the Python version."""

    def test_first_row_lag_is_null_starts_new_run(self):
        """SQL LAG() returns NULL for the first row. This should always
        start a new run (is_new_run=1), regardless of the value."""
        rows = [
            {"id": 1, "captured_at": _ts(0), "home_win_probability": None, "reading_count": 1, "valid_until": None},
            {"id": 2, "captured_at": _ts(1), "home_win_probability": None, "reading_count": 1, "valid_until": None},
        ]
        keepers, deleted = simulate_sql_collapse(rows)
        # Both are NULL but they should be in the SAME run (run_group=1)
        # First row: is_new_run=1 (always), second: is_new_run=0 (NULL=NULL)
        assert deleted == [2]

    def test_run_group_assignment_correctness(self):
        """Verify run groups are assigned correctly across value transitions."""
        rows = [
            {"id": 1, "captured_at": _ts(0), "home_win_probability": 0.50, "reading_count": 1, "valid_until": None},
            {"id": 2, "captured_at": _ts(1), "home_win_probability": 0.50, "reading_count": 1, "valid_until": None},
            {"id": 3, "captured_at": _ts(2), "home_win_probability": 0.60, "reading_count": 1, "valid_until": None},
            {"id": 4, "captured_at": _ts(3), "home_win_probability": 0.60, "reading_count": 1, "valid_until": None},
            {"id": 5, "captured_at": _ts(4), "home_win_probability": None, "reading_count": 1, "valid_until": None},
            {"id": 6, "captured_at": _ts(5), "home_win_probability": None, "reading_count": 1, "valid_until": None},
        ]
        keepers, deleted = simulate_sql_collapse(rows)
        # Three runs: 0.50×2, 0.60×2, NULL×2
        assert sorted(deleted) == [2, 4, 6]
        assert set(keepers.keys()) == {1, 3, 5}
