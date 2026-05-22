"""Tests for Discover feed stale/completed/repetitive card suppression.

Covers issue #435: suppress settled markets, completed events, dead markets,
and duplicate group_id cards from the first page.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.routes.feed import (
    _dedupe_futures_by_group_id,
    _filter_discover_event_noise,
    _market_runtime_filter_trace,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_outcome(
    name: str,
    probability: float | None = None,
    probability_change_24h: float | None = None,
    opening_probability: float | None = None,
    rank: int | None = None,
    rank_change_24h: int | None = None,
) -> dict:
    return {
        "name": name,
        "probability": probability,
        "probability_change_24h": probability_change_24h,
        "opening_probability": opening_probability,
        "rank": rank,
        "rank_change_24h": rank_change_24h,
    }


def _make_market(
    *,
    status: str = "open",
    updated_at: datetime | None = None,
    resolution_date: datetime | None = None,
    commence_time: datetime | None = None,
    name: str = "Test Market",
    event_id: int | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        status=status,
        updated_at=updated_at,
        resolution_date=resolution_date,
        commence_time=commence_time,
        name=name,
        event_id=event_id,
    )


def _event_item(
    *,
    score: int = 50,
    status: str = "live",
    sport: str = "basketball_nba",
    home_team_data: dict | None = None,
    away_team_data: dict | None = None,
    ei_score: int | None = None,
) -> dict:
    data = {
        "sport": sport,
        "status": status,
        "event_tags": ["tier:1"],
    }
    if home_team_data:
        data["home_team_data"] = home_team_data
    if away_team_data:
        data["away_team_data"] = away_team_data
    if ei_score is not None:
        data["ei"] = {"score": ei_score}
    return {
        "type": "event",
        "score": score,
        "headline": "Test",
        "data": data,
    }


def _futures_item(
    *,
    score: int = 80,
    market_id: int = 1,
    group_id: str | None = None,
    name: str = "Test Future",
) -> dict:
    data = {
        "id": market_id,
        "name": name,
        "group_id": group_id,
    }
    return {
        "type": "futures",
        "score": score,
        "data": data,
        "_sort_time": 0,
    }


# ---------------------------------------------------------------------------
# Settled / locked market detection via runtime filter trace
# ---------------------------------------------------------------------------

NOW = datetime(2026, 5, 22, 12, 0, tzinfo=timezone.utc)


class TestSettledMarketDetection:
    """Verify that settled/locked/dead markets are blocked by runtime filters."""

    def test_leader_at_97pct_is_locked(self):
        """Markets with leader >= 97% should be blocked as locked_market."""
        outcomes = [
            _make_outcome("Yes", probability=0.97, probability_change_24h=0.0),
            _make_outcome("No", probability=0.03, probability_change_24h=0.0),
        ]
        market = _make_market(updated_at=NOW - timedelta(hours=1))
        trace = _market_runtime_filter_trace(
            market, outcomes, "Yes", 0.97, NOW
        )
        assert not trace["eligible"]
        assert "locked_market" in trace["blockers"]

    def test_leader_at_100pct_is_locked(self):
        """Markets at exactly 100% should be blocked."""
        outcomes = [
            _make_outcome("Yes", probability=1.0, probability_change_24h=0.0),
            _make_outcome("No", probability=0.0, probability_change_24h=0.0),
        ]
        market = _make_market(updated_at=NOW - timedelta(hours=1))
        trace = _market_runtime_filter_trace(
            market, outcomes, "Yes", 1.0, NOW
        )
        assert not trace["eligible"]
        assert "locked_market" in trace["blockers"]

    def test_leader_at_96pct_is_not_locked(self):
        """Markets at 96% should NOT be blocked (below 97% threshold)."""
        outcomes = [
            _make_outcome("Yes", probability=0.96, probability_change_24h=0.01),
            _make_outcome("No", probability=0.04, probability_change_24h=-0.01),
        ]
        market = _make_market(updated_at=NOW - timedelta(hours=1))
        trace = _market_runtime_filter_trace(
            market, outcomes, "Yes", 0.96, NOW
        )
        assert "locked_market" not in trace["blockers"]

    def test_near_zero_binary_at_3pct(self):
        """Binary markets with leader <= 3% should be blocked."""
        outcomes = [
            _make_outcome("Yes", probability=0.03, probability_change_24h=0.0),
            _make_outcome("No", probability=0.97, probability_change_24h=0.0),
        ]
        market = _make_market(updated_at=NOW - timedelta(hours=1))
        trace = _market_runtime_filter_trace(
            market, outcomes, "Yes", 0.03, NOW
        )
        assert not trace["eligible"]
        # Either near_zero_binary or locked_market (No at 97%) blocks it
        has_block = (
            "near_zero_binary" in trace["blockers"]
            or "locked_market" in trace["blockers"]
        )
        assert has_block

    def test_all_outcomes_zero_is_dead(self):
        """Markets where all outcomes have zero probability are dead."""
        outcomes = [
            _make_outcome("Yes", probability=0.0, probability_change_24h=0.0),
            _make_outcome("No", probability=0.0, probability_change_24h=0.0),
        ]
        market = _make_market(updated_at=NOW - timedelta(hours=1))
        trace = _market_runtime_filter_trace(
            market, outcomes, "Yes", 0.0, NOW
        )
        assert not trace["eligible"]
        assert "all_outcomes_zero" in trace["blockers"]

    def test_all_outcomes_settled_at_extremes(self):
        """Markets where every outcome is <5% or >95% should be blocked."""
        outcomes = [
            _make_outcome("A", probability=0.96, probability_change_24h=0.0),
            _make_outcome("B", probability=0.02, probability_change_24h=0.0),
            _make_outcome("C", probability=0.01, probability_change_24h=0.0),
        ]
        market = _make_market(updated_at=NOW - timedelta(hours=1))
        trace = _market_runtime_filter_trace(
            market, outcomes, "A", 0.96, NOW
        )
        assert not trace["eligible"]
        assert "all_outcomes_settled" in trace["blockers"]

    def test_stale_no_movement_is_blocked(self):
        """Markets with no updates for 2+ days and zero movement should be blocked."""
        outcomes = [
            _make_outcome("Yes", probability=0.65, probability_change_24h=0.0),
            _make_outcome("No", probability=0.35, probability_change_24h=0.0),
        ]
        market = _make_market(updated_at=NOW - timedelta(days=3))
        trace = _market_runtime_filter_trace(
            market, outcomes, "Yes", 0.65, NOW
        )
        assert not trace["eligible"]
        assert "stale_no_movement" in trace["blockers"]

    def test_active_market_with_movement_passes(self):
        """Active markets with recent movement should pass all filters."""
        outcomes = [
            _make_outcome("Yes", probability=0.65, probability_change_24h=0.05),
            _make_outcome("No", probability=0.35, probability_change_24h=-0.05),
        ]
        market = _make_market(updated_at=NOW - timedelta(hours=6))
        trace = _market_runtime_filter_trace(
            market, outcomes, "Yes", 0.65, NOW
        )
        assert trace["eligible"]
        assert trace["blockers"] == []


# ---------------------------------------------------------------------------
# Completed event filtering in Discover mode
# ---------------------------------------------------------------------------


class TestDiscoverEventNoiseFiltering:
    """Verify that completed/closed events are removed from Discover."""

    def test_completed_events_removed(self):
        items = [
            _event_item(score=90, status="completed"),
            _event_item(score=80, status="live"),
            _futures_item(score=70),
        ]
        filtered = _filter_discover_event_noise(items)
        event_statuses = [
            (i["data"].get("status") or "")
            for i in filtered
            if i["type"] == "event"
        ]
        assert "completed" not in event_statuses

    def test_closed_events_removed(self):
        items = [
            _event_item(score=90, status="closed"),
            _event_item(score=80, status="live"),
        ]
        filtered = _filter_discover_event_noise(items)
        event_statuses = [
            (i["data"].get("status") or "")
            for i in filtered
            if i["type"] == "event"
        ]
        assert "closed" not in event_statuses

    def test_live_events_kept(self):
        items = [
            _event_item(
                score=80,
                status="live",
                home_team_data={"name": "Lakers"},
                away_team_data={"name": "Celtics"},
            ),
        ]
        filtered = _filter_discover_event_noise(items)
        assert len([i for i in filtered if i["type"] == "event"]) == 1

    def test_futures_pass_through_unchanged(self):
        items = [
            _futures_item(score=90, market_id=1),
            _futures_item(score=80, market_id=2),
        ]
        filtered = _filter_discover_event_noise(items)
        assert len(filtered) == 2

    def test_low_score_events_without_exception_removed(self):
        """Events below score 45 without exceptional status should be removed."""
        items = [
            _event_item(
                score=30,
                status="scheduled",
                home_team_data={"name": "Lakers"},
                away_team_data={"name": "Celtics"},
            ),
        ]
        filtered = _filter_discover_event_noise(items)
        assert len([i for i in filtered if i["type"] == "event"]) == 0

    def test_events_without_team_media_removed(self):
        """Events without team logos/data should be removed from Discover."""
        items = [
            _event_item(score=60, status="live"),
        ]
        filtered = _filter_discover_event_noise(items)
        assert len([i for i in filtered if i["type"] == "event"]) == 0


# ---------------------------------------------------------------------------
# Group ID deduplication
# ---------------------------------------------------------------------------


class TestGroupIdDedup:
    """Verify that futures with the same group_id are deduplicated."""

    def test_same_group_id_keeps_highest_score(self):
        items = [
            _futures_item(score=90, market_id=1, group_id="poly:abc"),
            _futures_item(score=80, market_id=2, group_id="poly:abc"),
            _futures_item(score=70, market_id=3, group_id="poly:abc"),
        ]
        deduped = _dedupe_futures_by_group_id(items)
        assert len(deduped) == 1
        assert deduped[0]["data"]["id"] == 1  # highest score

    def test_different_group_ids_all_kept(self):
        items = [
            _futures_item(score=90, market_id=1, group_id="poly:abc"),
            _futures_item(score=80, market_id=2, group_id="poly:def"),
            _futures_item(score=70, market_id=3, group_id="poly:ghi"),
        ]
        deduped = _dedupe_futures_by_group_id(items)
        assert len(deduped) == 3

    def test_null_group_id_not_deduped(self):
        """Markets without group_id should all pass through."""
        items = [
            _futures_item(score=90, market_id=1, group_id=None),
            _futures_item(score=80, market_id=2, group_id=None),
            _futures_item(score=70, market_id=3, group_id=None),
        ]
        deduped = _dedupe_futures_by_group_id(items)
        assert len(deduped) == 3

    def test_mixed_group_and_no_group(self):
        """Mix of grouped and ungrouped markets."""
        items = [
            _futures_item(score=90, market_id=1, group_id="poly:abc"),
            _futures_item(score=85, market_id=2, group_id=None),
            _futures_item(score=80, market_id=3, group_id="poly:abc"),
            _futures_item(score=75, market_id=4, group_id=None),
            _futures_item(score=70, market_id=5, group_id="poly:def"),
        ]
        deduped = _dedupe_futures_by_group_id(items)
        ids = [item["data"]["id"] for item in deduped]
        assert 1 in ids  # highest from group poly:abc
        assert 3 not in ids  # lower from group poly:abc, deduped
        assert 2 in ids  # no group
        assert 4 in ids  # no group
        assert 5 in ids  # different group


# ---------------------------------------------------------------------------
# Edge cases for settled market probability thresholds
# ---------------------------------------------------------------------------


class TestSettledMarketEdgeCases:
    """Boundary tests for the tightened probability thresholds."""

    def test_trump_at_zero_percent_blocked(self):
        """A market at 0% (like 'Will Trump win at 0%') should be blocked."""
        outcomes = [
            _make_outcome("Yes", probability=0.0, probability_change_24h=0.0),
            _make_outcome("No", probability=1.0, probability_change_24h=0.0),
        ]
        market = _make_market(
            updated_at=NOW - timedelta(hours=1),
            name="Will Trump win the 2028 election?",
        )
        trace = _market_runtime_filter_trace(
            market, outcomes, "Yes", 0.0, NOW
        )
        assert not trace["eligible"]

    def test_stale_golf_tournament_blocked(self):
        """Golf markets that started 6+ days ago should be blocked."""
        outcomes = [
            _make_outcome("Tiger Woods", probability=0.15, probability_change_24h=0.0),
            _make_outcome("Scottie Scheffler", probability=0.25, probability_change_24h=0.0),
        ]
        market = _make_market(
            updated_at=NOW - timedelta(hours=6),
            commence_time=NOW - timedelta(days=7),
            name="PGA Tour Winner",
        )
        trace = _market_runtime_filter_trace(
            market, outcomes, "Scottie Scheffler", 0.25, NOW,
            sport_category="golf",
        )
        assert not trace["eligible"]
        assert "stale_golf_tournament" in trace["blockers"]

    def test_sports_soft_settled_binary_blocked(self):
        """Sports binary at 60%+ with no movement and high opening should be blocked."""
        outcomes = [
            _make_outcome(
                "No", probability=0.65,
                probability_change_24h=0.0,
                opening_probability=0.55,
            ),
            _make_outcome(
                "Yes", probability=0.35,
                probability_change_24h=0.0,
                opening_probability=0.45,
            ),
        ]
        market = _make_market(
            updated_at=NOW - timedelta(hours=6),
            name="Will Celtics advance to Finals?",
        )
        trace = _market_runtime_filter_trace(
            market, outcomes, "No", 0.65, NOW,
            sport_category="basketball",
        )
        assert not trace["eligible"]
        assert "soft_settled_binary" in trace["blockers"]
