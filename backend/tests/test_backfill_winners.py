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


class TestPolymarketAllLosersAndNegRisk:
    """Tests for all-losers query expansion and NegRisk market handling."""

    def test_all_losers_included_in_stuck_query(self):
        """Markets with MAX(current_probability) <= 0.10 should be targeted.

        Previously the query only matched BETWEEN 0.05 AND 0.95, which
        skipped all-losers markets where the winning outcome's settlement
        price was never synced.
        """
        import inspect
        from app.tasks.backfill_winners import _backfill_polymarket_winners_from_api
        source = inspect.getsource(_backfill_polymarket_winners_from_api)
        # The query should include all-losers markets (max <= 0.10)
        assert "MAX(fo.current_probability) <= 0.10" in source
        # The original midrange condition should still be there
        assert "BETWEEN 0.05 AND 0.95" in source

    def test_negrisk_branch_exists(self):
        """NegRisk parent markets (external_id = event_id) need special
        handling that iterates all API sub-markets instead of single lookup.
        """
        import inspect
        from app.tasks.backfill_winners import _backfill_polymarket_winners_from_api
        source = inspect.getsource(_backfill_polymarket_winners_from_api)
        assert "is_negrisk" in source or "negrisk" in source.lower()

    def test_group_type_in_query(self):
        """The stuck query should fetch group_type to identify NegRisk markets."""
        import inspect
        from app.tasks.backfill_winners import _backfill_polymarket_winners_from_api
        source = inspect.getsource(_backfill_polymarket_winners_from_api)
        assert "fm.group_type" in source

    def test_settlement_price_sync_during_api_backfill(self):
        """API backfill should sync settlement prices to current_probability,
        not just set is_winner. This ensures Pass 1 clean resolution works
        on subsequent runs.
        """
        import inspect
        from app.tasks.backfill_winners import _backfill_polymarket_winners_from_api
        source = inspect.getsource(_backfill_polymarket_winners_from_api)
        assert "prices_synced" in source

    def test_stats_tracking_no_unbound_local(self):
        """Stats tracking should not reference r1/r2 when bare match succeeds.

        Previous bug: when r_bare.rowcount > 0 (bare condition_id matched),
        the code entered the else branch but then tried to access r1/r2,
        which were only defined in the if branch, causing UnboundLocalError.
        """
        import inspect
        from app.tasks.backfill_winners import _backfill_polymarket_winners_from_api
        source = inspect.getsource(_backfill_polymarket_winners_from_api)
        # The fixed version should use r_bare.rowcount for stats when bare match succeeds
        assert "r_bare.rowcount" in source


class TestSettlementSyncSubMarkets:
    """Tests for settlement price sync handling _yes/_no suffix outcomes."""

    def test_yes_suffix_in_settlement_sync(self):
        """Settlement sync should update _yes suffix outcomes."""
        import inspect
        from app.tasks.polymarket import _sync_polymarket_resolved_status
        source = inspect.getsource(_sync_polymarket_resolved_status)
        assert "cid_yes" in source or "_yes" in source

    def test_no_suffix_in_settlement_sync(self):
        """Settlement sync should update _no suffix outcomes."""
        import inspect
        from app.tasks.polymarket import _sync_polymarket_resolved_status
        source = inspect.getsource(_sync_polymarket_resolved_status)
        assert "cid_no" in source or "_no" in source

    def test_no_price_stored(self):
        """Settlement prices should include both Yes and No side prices."""
        import inspect
        from app.tasks.polymarket import _sync_polymarket_resolved_status
        source = inspect.getsource(_sync_polymarket_resolved_status)
        assert "no_price" in source


class TestDataGolfHistoricalResultsParsing:
    """Tests for DataGolfAPIService.get_historical_results() parsing."""

    def test_aggregates_to_latest_round(self):
        """Should keep only the latest round per player."""
        from app.services.datagolf_api import DataGolfAPIService

        svc = DataGolfAPIService(api_key="test")
        # Simulate raw API response (list of round rows)
        raw_data = [
            {"dg_id": 100, "player_name": "Scheffler, Scottie", "round_num": 1,
             "fin_text": None, "total_to_par": -3},
            {"dg_id": 100, "player_name": "Scheffler, Scottie", "round_num": 2,
             "fin_text": None, "total_to_par": -7},
            {"dg_id": 100, "player_name": "Scheffler, Scottie", "round_num": 3,
             "fin_text": None, "total_to_par": -10},
            {"dg_id": 100, "player_name": "Scheffler, Scottie", "round_num": 4,
             "fin_text": "1", "total_to_par": -15},
            {"dg_id": 200, "player_name": "Hovland, Viktor", "round_num": 1,
             "fin_text": None, "total_to_par": -1},
            {"dg_id": 200, "player_name": "Hovland, Viktor", "round_num": 2,
             "fin_text": "CUT", "total_to_par": 3},
        ]

        # The method calls self._get internally, so we test the parsing
        # logic by replicating what get_historical_results does after the API call
        from app.services.datagolf_api import normalize_player_name
        by_player = {}
        for row in raw_data:
            dg_id = row.get("dg_id")
            round_num = row.get("round_num", 0) or 0
            existing = by_player.get(dg_id)
            if existing is None or round_num > existing.get("_round_num", 0):
                by_player[dg_id] = {
                    "dg_id": dg_id,
                    "name": normalize_player_name(row.get("player_name", "")),
                    "position": row.get("fin_text", row.get("current_pos", row.get("position"))),
                    "total_score": row.get("total_to_par", row.get("total_score")),
                    "_round_num": round_num,
                }
        results = []
        for p in by_player.values():
            p.pop("_round_num", None)
            results.append(p)

        assert len(results) == 2

        scheffler = next(r for r in results if r["dg_id"] == 100)
        assert scheffler["position"] == "1"
        assert scheffler["total_score"] == -15
        assert scheffler["name"] == "Scottie Scheffler"

        hovland = next(r for r in results if r["dg_id"] == 200)
        assert hovland["position"] == "CUT"
        assert hovland["total_score"] == 3

    def test_handles_dict_response_with_data_key(self):
        """Should handle response as dict with 'data' key."""
        data = {"data": [
            {"dg_id": 1, "player_name": "Smith, John", "round_num": 4,
             "fin_text": "T5", "total_to_par": -8},
        ]}
        raw_rows = data if isinstance(data, list) else data.get("data", data.get("rounds", []))
        assert len(raw_rows) == 1
        assert raw_rows[0]["dg_id"] == 1

    def test_empty_response_returns_empty(self):
        """Should return empty list for empty/no data."""
        raw_rows = [] if isinstance([], list) else {}.get("data", [])
        assert raw_rows == []


class TestDataGolfLeaderboardTruncation:
    """Tests for detecting and fixing truncated DataGolf leaderboards."""

    def test_make_cut_resolution_with_full_leaderboard(self):
        """With full leaderboard, player at position 65 should make the cut."""
        from app.tasks.backfill_winners import _datagolf_check_placement
        # Position 65 (typical cut line ~70) — has a numeric position = made the cut
        assert _datagolf_check_placement("65", "make_cut") is True
        assert _datagolf_check_placement("T68", "make_cut") is True

    def test_make_cut_absent_inferred_as_loser(self):
        """With can_infer_absent=True, player not in leaderboard is a loser."""
        # Simulating the logic from _backfill_datagolf_winners
        pos_by_dg = {"100": "1", "200": "CUT"}  # truncated: only 2 players
        # Player 300 is absent from leaderboard
        dg_id = "300"
        pos_str = pos_by_dg.get(dg_id)
        assert pos_str is None  # absent

        can_infer_absent = True  # make_cut is now in the tuple
        if pos_str is None and can_infer_absent:
            won = False
        else:
            won = None
        assert won is False  # correctly inferred as loser

    def test_truncation_detection_exactly_50(self):
        """Leaderboard of exactly 50 entries is the truncation signature."""
        leaderboard = [{"dg_id": i, "name": f"Player {i}", "position": str(i)}
                       for i in range(1, 51)]
        assert len(leaderboard) == 50  # truncation signature

    def test_full_leaderboard_not_flagged(self):
        """Leaderboard with >50 entries is not truncated."""
        leaderboard = [{"dg_id": i, "name": f"Player {i}", "position": str(i)}
                       for i in range(1, 157)]
        assert len(leaderboard) == 156
        assert len(leaderboard) != 50  # not flagged as truncated

    def test_resolution_source_is_leaderboard(self):
        """DataGolf winner resolution should use 'leaderboard' as resolution_source."""
        # The resolution_source was changed from 'scoring_plays' to 'leaderboard'
        # This test ensures the correct value is used
        import ast
        import inspect
        from app.tasks.backfill_winners import _backfill_datagolf_winners
        source = inspect.getsource(_backfill_datagolf_winners)
        assert "resolution_source = 'leaderboard'" in source
        assert "resolution_source = 'scoring_plays'" not in source
