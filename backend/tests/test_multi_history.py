"""Tests for the /api/futures/multi-history endpoint.

Covers:
- _progression_merge_key: cross-source outcome matching
- Merge key grouping: same team, same name, different teams
"""

import pytest

from app.routes.futures import _progression_merge_key
from types import SimpleNamespace


# ============================================================================
# Helpers
# ============================================================================


def _outcome(oid, name, *, team_id=None, probability=0.5):
    return SimpleNamespace(
        id=oid,
        name=name,
        team_id=team_id,
        current_probability=probability,
        probability_change_24h=None,
    )


# ============================================================================
# _progression_merge_key unit tests
# ============================================================================


class TestProgressionMergeKey:
    """Outcome merge key generation for cross-source matching."""

    def test_team_id_takes_priority(self):
        o = _outcome(1, "Boston Celtics", team_id=42)
        assert _progression_merge_key(o) == "team:42"

    def test_name_fallback(self):
        o = _outcome(1, "Scottie Scheffler")
        assert _progression_merge_key(o) == "name:scottie scheffler"

    def test_kalshi_prefix_stripped(self):
        o = _outcome(1, "Yes: Oklahoma City Thunder")
        key = _progression_merge_key(o)
        assert "yes" not in key
        assert "oklahoma city thunder" in key

    def test_datagolf_comma_format(self):
        o = _outcome(1, "Scheffler, Scottie")
        key = _progression_merge_key(o)
        assert key == "name:scottie scheffler"

    def test_diacritics_stripped(self):
        o = _outcome(1, "Skarsgård, Viktor")
        key = _progression_merge_key(o)
        assert "skarsgard" in key

    def test_polymarket_quotes_stripped(self):
        o = _outcome(1, '"Boston Celtics"')
        key = _progression_merge_key(o)
        assert key == "name:boston celtics"


# ============================================================================
# Aggregation logic (unit-level)
# ============================================================================


class TestMultiHistoryAggregation:
    """Core aggregation: merging outcomes by name/team_id across sources."""

    def test_merge_key_groups_same_team(self):
        """Outcomes with the same team_id from different sources share a merge key."""
        o1 = _outcome(1, "Boston Celtics", team_id=10, probability=0.25)
        o2 = _outcome(2, "Celtics", team_id=10, probability=0.30)
        assert _progression_merge_key(o1) == _progression_merge_key(o2)

    def test_merge_key_groups_same_name(self):
        """Outcomes with the same name (after normalization) share a merge key."""
        o1 = _outcome(1, "Yes: Scottie Scheffler", probability=0.15)
        o2 = _outcome(2, "Scottie Scheffler", probability=0.18)
        assert _progression_merge_key(o1) == _progression_merge_key(o2)

    def test_merge_key_different_teams(self):
        """Outcomes for different teams have different merge keys."""
        o1 = _outcome(1, "Boston Celtics", team_id=10)
        o2 = _outcome(2, "Lakers", team_id=20)
        assert _progression_merge_key(o1) != _progression_merge_key(o2)

    def test_merge_key_case_insensitive(self):
        """Name matching is case-insensitive."""
        o1 = _outcome(1, "OKLAHOMA CITY THUNDER")
        o2 = _outcome(2, "oklahoma city thunder")
        assert _progression_merge_key(o1) == _progression_merge_key(o2)

    def test_merge_key_jr_suffix_stripped(self):
        """Jr./Sr. suffixes are stripped for matching."""
        o1 = _outcome(1, "Shai Gilgeous-Alexander Jr.")
        o2 = _outcome(2, "Shai Gilgeous-Alexander")
        assert _progression_merge_key(o1) == _progression_merge_key(o2)
