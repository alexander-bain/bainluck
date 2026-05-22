"""Tests for auto-extending sparse futures history windows (issue #558).

When a market has too few snapshots in the requested window, the history
endpoint should automatically widen to 30d then 90d to surface more data.
"""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from httpx import AsyncClient


# --------------------------------------------------------------------------
# Helpers: build mock market + snapshot objects
# --------------------------------------------------------------------------

def _make_outcome(oid: int, name: str, prob: float = 0.5):
    o = MagicMock()
    o.id = oid
    o.name = name
    o.current_probability = prob
    o.probability_change_24h = None
    o.team_id = None
    o.team = None
    o.opening_probability = None
    o.opening_american_odds = None
    o.rank = 1
    o.rank_change_24h = None
    o.is_winner = None
    o.last_updated = None
    return o


def _make_snapshot(outcome_id: int, captured_at: datetime, prob: float):
    s = MagicMock()
    s.outcome_id = outcome_id
    s.captured_at = captured_at
    s.probability = prob
    s.bookmaker = "test"
    return s


def _make_market(market_id: int = 1, outcomes=None, metadata=None):
    m = MagicMock()
    m.id = market_id
    m.name = "Test Market"
    m.market_metadata = metadata
    m.outcomes = outcomes or [_make_outcome(100, "Outcome A", 0.6)]
    return m


# --------------------------------------------------------------------------
# Unit tests for the auto-extend logic
# --------------------------------------------------------------------------

class TestHistoryAutoExtend:
    """Tests for /{market_id}/history auto-extend behavior."""

    @pytest.mark.asyncio
    async def test_sparse_data_triggers_extension(self):
        """When <20 snapshots in 7d window, should auto-extend to 30d."""
        from app.routes.futures import get_futures_history

        now = datetime.now(timezone.utc)
        market = _make_market(outcomes=[_make_outcome(100, "Outcome A")])

        # 5 snapshots in the last 7 days
        recent_snaps = [
            _make_snapshot(100, now - timedelta(hours=i * 24), 0.5 + i * 0.01)
            for i in range(5)
        ]
        # 25 more snapshots in the 8-30 day range
        older_snaps = [
            _make_snapshot(100, now - timedelta(days=8 + i), 0.4 + i * 0.005)
            for i in range(25)
        ]

        call_count = 0
        async def mock_execute(query):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                # First call: return market
                result.scalar_one_or_none.return_value = market
                return result
            elif call_count == 2:
                # Second call: initial 7-day window (5 snapshots)
                scalars_mock = MagicMock()
                scalars_mock.all.return_value = recent_snaps
                result.scalars.return_value = scalars_mock
                return result
            elif call_count == 3:
                # Third call: extended 30-day window (30 snapshots)
                scalars_mock = MagicMock()
                scalars_mock.all.return_value = recent_snaps + older_snaps
                result.scalars.return_value = scalars_mock
                return result
            else:
                scalars_mock = MagicMock()
                scalars_mock.all.return_value = recent_snaps + older_snaps
                result.scalars.return_value = scalars_mock
                return result

        db = AsyncMock()
        db.execute = mock_execute

        result = await get_futures_history(market_id=1, hours=168, db=db)

        assert result["hours"] == 168  # requested hours unchanged
        assert result["actual_hours"] == 720  # auto-extended to 30 days
        assert result.get("auto_extended") is True

    @pytest.mark.asyncio
    async def test_very_sparse_extends_to_90d(self):
        """When <10 snapshots in 30d, should extend to 90d."""
        from app.routes.futures import get_futures_history

        now = datetime.now(timezone.utc)
        market = _make_market(outcomes=[_make_outcome(100, "Outcome A")])

        # Only 3 snapshots total in the last 7 days
        recent_snaps = [
            _make_snapshot(100, now - timedelta(hours=i * 48), 0.5)
            for i in range(3)
        ]
        # 5 more in 30-day window (still under 10)
        month_snaps = [
            _make_snapshot(100, now - timedelta(days=10 + i * 5), 0.45)
            for i in range(5)
        ]
        # 15 more in 90-day window
        quarter_snaps = [
            _make_snapshot(100, now - timedelta(days=35 + i * 3), 0.4)
            for i in range(15)
        ]

        call_count = 0
        async def mock_execute(query):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                result.scalar_one_or_none.return_value = market
                return result
            elif call_count == 2:
                # 7-day: 3 snapshots
                scalars_mock = MagicMock()
                scalars_mock.all.return_value = recent_snaps
                result.scalars.return_value = scalars_mock
                return result
            elif call_count == 3:
                # 30-day: 8 snapshots (still <10)
                scalars_mock = MagicMock()
                scalars_mock.all.return_value = recent_snaps + month_snaps
                result.scalars.return_value = scalars_mock
                return result
            elif call_count == 4:
                # 90-day: 23 snapshots
                scalars_mock = MagicMock()
                scalars_mock.all.return_value = recent_snaps + month_snaps + quarter_snaps
                result.scalars.return_value = scalars_mock
                return result
            else:
                scalars_mock = MagicMock()
                scalars_mock.all.return_value = recent_snaps + month_snaps + quarter_snaps
                result.scalars.return_value = scalars_mock
                return result

        db = AsyncMock()
        db.execute = mock_execute

        result = await get_futures_history(market_id=1, hours=168, db=db)

        assert result["hours"] == 168
        assert result["actual_hours"] == 2160  # 90 days
        assert result.get("auto_extended") is True
        # sparse flag reflects the FINAL data count (23 points after extending),
        # not the original window's count; 23 >= 10 so not sparse
        assert result["total_data_points"] == 23

    @pytest.mark.asyncio
    async def test_dense_data_no_extension(self):
        """When >=20 snapshots in 7d, no extension needed."""
        from app.routes.futures import get_futures_history

        now = datetime.now(timezone.utc)
        market = _make_market(outcomes=[_make_outcome(100, "Outcome A")])

        # 50 snapshots in the last 7 days
        snaps = [
            _make_snapshot(100, now - timedelta(hours=i * 3), 0.5 + (i % 10) * 0.01)
            for i in range(50)
        ]

        call_count = 0
        async def mock_execute(query):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                result.scalar_one_or_none.return_value = market
                return result
            else:
                scalars_mock = MagicMock()
                scalars_mock.all.return_value = snaps
                result.scalars.return_value = scalars_mock
                return result

        db = AsyncMock()
        db.execute = mock_execute

        result = await get_futures_history(market_id=1, hours=168, db=db)

        assert result["hours"] == 168
        assert result["actual_hours"] == 168  # no extension
        assert result.get("auto_extended") is None  # not set
        assert result.get("sparse") is None  # not sparse

    @pytest.mark.asyncio
    async def test_total_data_points_in_response(self):
        """Response should include total_data_points count."""
        from app.routes.futures import get_futures_history

        now = datetime.now(timezone.utc)
        market = _make_market(outcomes=[_make_outcome(100, "Outcome A")])
        snaps = [
            _make_snapshot(100, now - timedelta(hours=i), 0.5)
            for i in range(30)
        ]

        call_count = 0
        async def mock_execute(query):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                result.scalar_one_or_none.return_value = market
                return result
            else:
                scalars_mock = MagicMock()
                scalars_mock.all.return_value = snaps
                result.scalars.return_value = scalars_mock
                return result

        db = AsyncMock()
        db.execute = mock_execute

        result = await get_futures_history(market_id=1, hours=168, db=db)

        assert "total_data_points" in result
        assert result["total_data_points"] == 30
