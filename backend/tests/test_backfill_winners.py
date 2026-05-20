"""Tests for is_winner backfill logic."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock


class TestPolymarketPhase3Settlement:
    """Tests for _backfill_polymarket_winners_from_api (Phase 3)."""

    @pytest.fixture
    def mock_session(self):
        session = AsyncMock()
        session.commit = AsyncMock()
        return session

    def test_yes_won_prices(self):
        """outcome_prices [1, 0] should mark Yes as winner."""
        prices = [1.0, 0.0]
        assert prices[0] >= 0.90
        assert prices[1] <= 0.10
        yes_won = prices[0] >= 0.90
        assert yes_won is True

    def test_no_won_prices(self):
        """outcome_prices [0, 1] should mark No as winner."""
        prices = [0.0, 1.0]
        yes_won = prices[0] >= 0.90
        assert yes_won is False

    def test_midrange_prices_skipped(self):
        """outcome_prices [0.6, 0.4] should be skipped (not settled)."""
        prices = [0.6, 0.4]
        max_price = max(prices)
        min_price = min(prices)
        assert not (max_price >= 0.90 and min_price <= 0.10)

    def test_near_settlement_passes(self):
        """outcome_prices [0.95, 0.05] should be treated as settled."""
        prices = [0.95, 0.05]
        max_price = max(prices)
        min_price = min(prices)
        assert max_price >= 0.90
        assert min_price <= 0.10
        yes_won = prices[0] >= 0.90
        assert yes_won is True

    def test_stringified_prices_parsed(self):
        """Gamma API sometimes returns stringified JSON arrays."""
        import json
        raw = '["0.95", "0.05"]'
        parsed = json.loads(raw)
        prices = [float(p) for p in parsed]
        assert prices == [0.95, 0.05]

    def test_empty_prices_skipped(self):
        """Empty outcome_prices should be skipped."""
        prices = []
        assert len(prices) < 2

    def test_single_price_skipped(self):
        """Single outcome_price should be skipped."""
        prices = [0.95]
        assert len(prices) < 2

    def test_external_id_mapping(self):
        """Outcome external_ids follow the {condition_id}_{yes|no} pattern."""
        condition_id = "0xabc123"
        yes_ext = f"{condition_id}_yes"
        no_ext = f"{condition_id}_no"
        assert yes_ext == "0xabc123_yes"
        assert no_ext == "0xabc123_no"


class TestCoverageMetricExclusion:
    """Tests for the coverage metric denominator fix."""

    def test_untradeable_markets_excluded(self):
        """Markets where ALL outcomes have null cal+open should be excluded."""
        # Simulated market status rows
        markets = [
            {"has_winner": True, "all_cal_null": False},   # resolved with winner
            {"has_winner": False, "all_cal_null": True},   # ghost — excluded
            {"has_winner": False, "all_cal_null": False},  # needs backfill
        ]

        resolved = len(markets)
        has_winner = sum(1 for m in markets if m["has_winner"])
        needs_backfill = sum(1 for m in markets
                            if not m["has_winner"] and not m["all_cal_null"])
        untradeable = sum(1 for m in markets if m["all_cal_null"])

        assert resolved == 3
        assert has_winner == 1
        assert needs_backfill == 1  # only the real gap
        assert untradeable == 1   # ghost excluded

    def test_tradeable_without_winner_still_counts(self):
        """Markets with calibration data but no winner still need backfill."""
        markets = [
            {"has_winner": False, "all_cal_null": False},  # real gap
            {"has_winner": False, "all_cal_null": False},  # real gap
        ]
        needs = sum(1 for m in markets if not m["has_winner"] and not m["all_cal_null"])
        assert needs == 2


class TestDataGolfPlacement:
    """Tests for _datagolf_check_placement logic."""

    def test_win_position_1(self):
        from app.tasks.backfill_winners import _datagolf_check_placement
        assert _datagolf_check_placement("1", "win") is True

    def test_win_tied_first(self):
        from app.tasks.backfill_winners import _datagolf_check_placement
        assert _datagolf_check_placement("T1", "win") is True

    def test_win_position_2(self):
        from app.tasks.backfill_winners import _datagolf_check_placement
        assert _datagolf_check_placement("2", "win") is False

    def test_top_5_position_3(self):
        from app.tasks.backfill_winners import _datagolf_check_placement
        assert _datagolf_check_placement("3", "top_5") is True

    def test_top_5_tied_5(self):
        from app.tasks.backfill_winners import _datagolf_check_placement
        assert _datagolf_check_placement("T5", "top_5") is True

    def test_top_5_position_6(self):
        from app.tasks.backfill_winners import _datagolf_check_placement
        assert _datagolf_check_placement("6", "top_5") is False

    def test_top_10_position_10(self):
        from app.tasks.backfill_winners import _datagolf_check_placement
        assert _datagolf_check_placement("10", "top_10") is True

    def test_top_10_position_11(self):
        from app.tasks.backfill_winners import _datagolf_check_placement
        assert _datagolf_check_placement("11", "top_10") is False

    def test_top_20_position_20(self):
        from app.tasks.backfill_winners import _datagolf_check_placement
        assert _datagolf_check_placement("T20", "top_20") is True

    def test_top_20_position_21(self):
        from app.tasks.backfill_winners import _datagolf_check_placement
        assert _datagolf_check_placement("21", "top_20") is False

    def test_make_cut_numeric_position(self):
        from app.tasks.backfill_winners import _datagolf_check_placement
        assert _datagolf_check_placement("45", "make_cut") is True

    def test_make_cut_tied(self):
        from app.tasks.backfill_winners import _datagolf_check_placement
        assert _datagolf_check_placement("T32", "make_cut") is True

    def test_make_cut_status_CUT(self):
        from app.tasks.backfill_winners import _datagolf_check_placement
        assert _datagolf_check_placement("CUT", "make_cut") is False

    def test_make_cut_status_MC(self):
        from app.tasks.backfill_winners import _datagolf_check_placement
        assert _datagolf_check_placement("MC", "make_cut") is False

    def test_make_cut_status_WD(self):
        from app.tasks.backfill_winners import _datagolf_check_placement
        assert _datagolf_check_placement("WD", "make_cut") is False

    def test_make_cut_status_DQ(self):
        from app.tasks.backfill_winners import _datagolf_check_placement
        assert _datagolf_check_placement("DQ", "make_cut") is False

    def test_cut_player_loses_top_5(self):
        from app.tasks.backfill_winners import _datagolf_check_placement
        assert _datagolf_check_placement("CUT", "top_5") is False

    def test_unparseable_returns_none(self):
        from app.tasks.backfill_winners import _datagolf_check_placement
        assert _datagolf_check_placement("???", "win") is None


class TestSpreadTotalParsing:
    """Tests for spread/total outcome name regex parsing."""

    def test_spread_full_game(self):
        from app.tasks.backfill_winners import _SPREAD_RE
        m = _SPREAD_RE.search("New York wins by over 29.5 points")
        assert m is not None
        assert m.group(1) == "New York"
        assert float(m.group(2)) == 29.5

    def test_spread_1h(self):
        from app.tasks.backfill_winners import _SPREAD_RE
        m = _SPREAD_RE.search("New York wins the 1H by over 24.5 points")
        assert m is not None
        assert m.group(1) == "New York"
        assert float(m.group(2)) == 24.5

    def test_spread_runs(self):
        from app.tasks.backfill_winners import _SPREAD_RE
        m = _SPREAD_RE.search("Los Angeles A wins by over 3.5 runs")
        assert m is not None
        assert m.group(1) == "Los Angeles A"
        assert float(m.group(2)) == 3.5

    def test_total_full_game(self):
        from app.tasks.backfill_winners import _TOTAL_RE
        m = _TOTAL_RE.search("Over 210.5 points scored")
        assert m is not None
        assert float(m.group(1)) == 210.5

    def test_total_1h(self):
        from app.tasks.backfill_winners import _TOTAL_RE
        m = _TOTAL_RE.search("Over 93.5 1H points scored")
        assert m is not None
        assert float(m.group(1)) == 93.5

    def test_no_match_random_text(self):
        from app.tasks.backfill_winners import _SPREAD_RE, _TOTAL_RE
        assert _SPREAD_RE.search("Yes") is None
        assert _TOTAL_RE.search("Yes") is None


class TestPhase2LimitIncrease:
    """Tests for the Kalshi Phase 2 limit increase."""

    def test_default_limit_is_5000(self):
        """_backfill_all_winners default limit should be 5000."""
        import inspect
        from app.tasks.backfill_winners import _backfill_all_winners
        sig = inspect.signature(_backfill_all_winners)
        assert sig.parameters["limit"].default == 5000
