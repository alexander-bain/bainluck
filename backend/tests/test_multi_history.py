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


class TestMultiHistoryTopOutcomeScoping:
    """#13573: `/api/futures/multi-history` has no Field line and only renders
    `top_entries[:capped_n]`, so snapshot and archive reads must not ask for
    unserved tail outcome IDs."""

    @pytest.mark.asyncio
    async def test_only_top_entries_outcomes_reach_snapshot_and_archive_reads(
        self, monkeypatch
    ):
        from datetime import datetime, timedelta, timezone

        import app.routes.futures as futures_route

        def _full_outcome(oid: int, name: str, prob: float):
            return SimpleNamespace(
                id=oid,
                external_id=f"ext-{oid}",
                name=name,
                team_id=None,
                current_probability=prob,
                probability_change_24h=None,
                resolution_source=None,
                is_winner=None,
            )

        def _market(mid: int, source: str, outcomes: list):
            return SimpleNamespace(
                id=mid,
                name=f"Market {mid}",
                source=source,
                market_type="binary",
                mutually_exclusive=True,
                market_metadata=None,
                status="open",
                outcomes=outcomes,
            )

        # Two Kalshi + Polymarket markets with 5 shared outcomes; top_n=2 should query only IDs {1,101, 2,102}.
        kalshi_outcomes = [
            _full_outcome(1, "Leader A", 0.45),
            _full_outcome(2, "Leader B", 0.30),
            _full_outcome(3, "Tail C", 0.10),
            _full_outcome(4, "Tail D", 0.08),
            _full_outcome(5, "Tail E", 0.07),
        ]
        poly_outcomes = [
            _full_outcome(101, "Leader A", 0.44),
            _full_outcome(102, "Leader B", 0.31),
            _full_outcome(103, "Tail C", 0.11),
            _full_outcome(104, "Tail D", 0.07),
            _full_outcome(105, "Tail E", 0.07),
        ]
        markets = [_market(10, "kalshi", kalshi_outcomes), _market(11, "polymarket", poly_outcomes)]

        now = datetime.now(timezone.utc)
        snaps = [
            SimpleNamespace(
                id=idx,
                outcome_id=oid,
                bookmaker="kalshi" if oid < 100 else "polymarket",
                probability=0.45 if oid in (1, 101) else 0.30,
                yes_bid=0.44,
                yes_ask=0.46,
                last_price=0.45,
                captured_at=now - timedelta(hours=2),
            )
            for idx, oid in enumerate((1, 101, 2, 102), start=1)
        ]

        seen_snapshot_oids: list[set[int]] = []
        seen_archive_ids: list[list[int]] = []

        async def _fake_archive(db, market, ids, *, since, full_range):
            seen_archive_ids.append(list(ids))
            return SimpleNamespace(
                state="empty",
                rows={},
                served=lambda *a, **k: {},
                describe=lambda *a, **k: {},
            )

        monkeypatch.setattr(futures_route, "load_archive_history", _fake_archive)

        class _Result:
            def __init__(self, rows):
                self._rows = rows

            def scalars(self):
                return self

            def unique(self):
                return self

            def all(self):
                return self._rows

        class _DB:
            def __init__(self):
                self.calls = 0

            async def execute(self, statement):
                self.calls += 1
                if self.calls == 1:
                    return _Result(markets)
                compiled = str(statement.compile(compile_kwargs={"literal_binds": True}))
                # Verify tail outcomes 3, 4, 5, 103, 104, 105 never appear in snapshot IN (...) filter
                present = {oid for oid in (1, 2, 3, 4, 5, 101, 102, 103, 104, 105) if f" {oid}" in compiled or f"({oid}" in compiled or f", {oid}" in compiled}
                seen_snapshot_oids.append(present)
                return _Result(snaps)

        payload = await futures_route.get_multi_market_history(
            market_ids="10,11", hours=168, top_n=2, db=_DB()
        )
        assert [o["name"] for o in payload["outcomes"]] == ["Leader A", "Leader B"]
        assert seen_snapshot_oids, "expected at least one snapshot query"
        for queried in seen_snapshot_oids:
            assert queried <= {1, 2, 101, 102}
            assert queried == {1, 2, 101, 102}
        assert seen_archive_ids == [[1, 2]]
