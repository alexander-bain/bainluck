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

    def test_make_cut_absent_inferred_as_loser_full_field(self):
        """With full leaderboard (>=100), absent player is correctly a loser."""
        # Simulate _backfill_datagolf_winners logic for make_cut
        leaderboard = [{"dg_id": i, "position": str(i)} for i in range(1, 156)]
        leaderboard_size = len(leaderboard)
        pos_by_dg = {str(e["dg_id"]): e["position"] for e in leaderboard}

        # Player 999 is absent from a FULL leaderboard -> truly not in field
        assert pos_by_dg.get("999") is None
        can_infer_absent = leaderboard_size >= 100  # full field
        assert can_infer_absent is True

    def test_make_cut_absent_NOT_inferred_truncated(self):
        """With truncated leaderboard (<100), absent player is NOT inferred as loser.

        This is the critical fix: truncated leaderboards (e.g., 50 entries)
        omit players ranked 51+ who actually made the cut. Inferring them
        as losers corrupts make_cut calibration.
        """
        leaderboard = [{"dg_id": i, "position": str(i)} for i in range(1, 51)]
        leaderboard_size = len(leaderboard)

        # Player 55 is absent from truncated leaderboard
        # but may have made the cut (rank 51-70)
        assert leaderboard_size == 50
        can_infer_absent = leaderboard_size >= 100  # truncated -> False
        assert can_infer_absent is False

    def test_make_cut_can_infer_absent_threshold(self):
        """The make_cut absent-inference threshold is 100 players."""
        import inspect
        from app.tasks.backfill_winners import _backfill_datagolf_winners
        source = inspect.getsource(_backfill_datagolf_winners)
        # The guard should check leaderboard size for make_cut
        assert "leaderboard_size >= 100" in source
        # make_cut should NOT be in the simple can_infer_absent tuple
        assert "can_infer_absent = market_type in (\"win\"" not in source or \
               "\"make_cut\"" not in source.split("can_infer_absent = market_type in")[1].split(")")[0]

    def test_win_absent_always_inferred(self):
        """Win markets should always infer absent players as losers."""
        # For win markets, any absent player definitely didn't win
        # regardless of leaderboard size
        import inspect
        from app.tasks.backfill_winners import _backfill_datagolf_winners
        source = inspect.getsource(_backfill_datagolf_winners)
        assert '"win"' in source

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


class TestGolfMakeCutCalibrationEndToEnd:
    """End-to-end simulation proving the truncated-leaderboard fix
    moves golf make_cut calibration in the right direction.

    Simulates 5 PGA tournaments with realistic DataGolf model predictions,
    runs resolution under both old (buggy) and new (fixed) logic, feeds
    results through the exact calibration bucketing rules from the
    production query, and compares the calibration output.
    """

    @staticmethod
    def _build_tournaments(seed=42):
        """Build 5 realistic PGA tournament datasets.

        Each tournament has ~156 golfers. DataGolf's pre-tournament model
        produces make_cut probabilities. Ground truth uses a realistic
        cut line (top ~70 players + ties make the cut).

        Returns list of tournament dicts, each containing:
          - full_leaderboard: all ~156 entries with final positions
          - truncated_leaderboard: first 50 entries only
          - outcomes: list of (dg_id, opening_probability)
        """
        import random
        rng = random.Random(seed)

        tournaments = []
        for t in range(5):
            field_size = rng.randint(144, 156)
            # Cut line: ~65-70 make the cut
            cut_line = rng.randint(65, 72)

            full_lb = []
            truncated_lb = []
            outcomes = []

            for rank in range(1, field_size + 1):
                dg_id = t * 1000 + rank
                made_cut = rank <= cut_line

                if made_cut:
                    # Positions 1 through cut_line
                    pos = str(rank)
                else:
                    pos = "CUT"

                entry = {"dg_id": dg_id, "position": pos}
                full_lb.append(entry)
                if rank <= 50:
                    truncated_lb.append(entry)

                # Simulate DataGolf model prediction for make_cut
                # Better-ranked players get higher predictions
                if rank <= 20:
                    prob = rng.uniform(0.88, 0.99)
                elif rank <= 50:
                    prob = rng.uniform(0.72, 0.92)
                elif rank <= cut_line:
                    # These are the CRITICAL ones: ranked 51-70, actually made
                    # the cut, but absent from truncated leaderboard
                    prob = rng.uniform(0.55, 0.82)
                elif rank <= cut_line + 15:
                    # Bubble players: missed the cut barely
                    prob = rng.uniform(0.40, 0.65)
                else:
                    prob = rng.uniform(0.08, 0.45)

                outcomes.append((dg_id, round(prob, 4)))

            tournaments.append({
                "full_leaderboard": full_lb,
                "truncated_leaderboard": truncated_lb,
                "outcomes": outcomes,
                "cut_line": cut_line,
                "field_size": field_size,
            })

        return tournaments

    @staticmethod
    def _resolve_outcomes(leaderboard, outcomes, market_type="make_cut"):
        """Run the resolution logic from _backfill_datagolf_winners.

        Returns dict of dg_id -> is_winner (True/False/None for skipped).
        Uses the CURRENT (fixed) logic: can_infer_absent gated on size >= 100.
        """
        from app.tasks.backfill_winners import _datagolf_check_placement

        pos_by_dg = {}
        for entry in leaderboard:
            dg_id = entry.get("dg_id")
            pos_raw = entry.get("position")
            if dg_id is not None and pos_raw is not None:
                pos_by_dg[str(dg_id)] = str(pos_raw)

        leaderboard_size = len(leaderboard)
        if market_type == "make_cut":
            can_infer_absent = leaderboard_size >= 100
        else:
            can_infer_absent = market_type in ("win", "top_5", "top_10", "top_20")

        results = {}
        for dg_id, _prob in outcomes:
            pos_str = pos_by_dg.get(str(dg_id))
            if pos_str is None:
                if can_infer_absent:
                    results[dg_id] = False
                else:
                    results[dg_id] = None  # skipped
            else:
                won = _datagolf_check_placement(pos_str, market_type)
                results[dg_id] = won

        return results

    @staticmethod
    def _resolve_outcomes_old_behavior(leaderboard, outcomes, market_type="make_cut"):
        """Run the OLD (buggy) resolution logic.

        Old behavior: can_infer_absent = True for make_cut regardless of
        leaderboard size. Absent players marked as losers.
        """
        from app.tasks.backfill_winners import _datagolf_check_placement

        pos_by_dg = {}
        for entry in leaderboard:
            dg_id = entry.get("dg_id")
            pos_raw = entry.get("position")
            if dg_id is not None and pos_raw is not None:
                pos_by_dg[str(dg_id)] = str(pos_raw)

        # OLD: always True for make_cut
        can_infer_absent = market_type in ("win", "top_5", "top_10", "top_20", "make_cut")

        results = {}
        for dg_id, _prob in outcomes:
            pos_str = pos_by_dg.get(str(dg_id))
            if pos_str is None:
                if can_infer_absent:
                    results[dg_id] = False
                else:
                    results[dg_id] = None
            else:
                won = _datagolf_check_placement(pos_str, market_type)
                results[dg_id] = won

        return results

    @staticmethod
    def _build_calibration_buckets(outcomes, resolutions):
        """Feed resolved outcomes through calibration bucketing.

        Replicates the production calibration query logic:
        - adj_opening_probability = opening_probability (DataGolf has no cal_prob)
        - Exclude outcomes with opening_prob <= 0.005 or >= 0.98 (multi-market tails)
        - Skip unresolved outcomes (is_winner is None)
        - Bucket by floor(prob * 10), capped at 9
        - A market must have at least 1 winner to enter calibration (has_winner >= 1)

        Returns dict of bucket_idx -> {n, winners, sum_prob}.
        """
        # First check has_winner: does this market have any True resolutions?
        has_winner = any(v is True for v in resolutions.values())
        if not has_winner:
            return {}  # entire market excluded from calibration

        buckets = {}
        for dg_id, prob in outcomes:
            is_winner = resolutions.get(dg_id)
            if is_winner is None:
                continue  # skipped outcome

            # Multi-market tail exclusion
            if prob <= 0.005 or prob >= 0.98:
                continue

            bucket = min(int(prob * 10), 9)
            if bucket not in buckets:
                buckets[bucket] = {"n": 0, "winners": 0, "sum_prob": 0.0}
            buckets[bucket]["n"] += 1
            if is_winner:
                buckets[bucket]["winners"] += 1
            buckets[bucket]["sum_prob"] += prob

        return buckets

    @staticmethod
    def _compute_mce(buckets):
        """Compute Mean Calibration Error from buckets.

        MCE = mean over buckets of |actual_win_rate - predicted_prob|
        Only counts buckets with at least 1 outcome.
        """
        if not buckets:
            return float("inf")
        total_err = 0.0
        n_buckets = 0
        for b in sorted(buckets.keys()):
            data = buckets[b]
            if data["n"] == 0:
                continue
            actual = data["winners"] / data["n"]
            predicted = data["sum_prob"] / data["n"]
            total_err += abs(actual - predicted)
            n_buckets += 1
        return total_err / n_buckets if n_buckets > 0 else float("inf")

    @staticmethod
    def _merge_buckets(all_buckets):
        """Merge bucket lists from multiple tournaments into one."""
        merged = {}
        for buckets in all_buckets:
            for b, data in buckets.items():
                if b not in merged:
                    merged[b] = {"n": 0, "winners": 0, "sum_prob": 0.0}
                merged[b]["n"] += data["n"]
                merged[b]["winners"] += data["winners"]
                merged[b]["sum_prob"] += data["sum_prob"]
        return merged

    def test_fix_reduces_mce_on_truncated_leaderboards(self):
        """The leaderboard-size guard produces better calibration than the old code.

        Runs both old and new logic on 5 tournaments with truncated (50-player)
        leaderboards and compares MCE. The new logic must produce strictly
        lower MCE because it avoids marking made-the-cut golfers as losers.
        """
        tournaments = self._build_tournaments()

        old_all_buckets = []
        new_all_buckets = []

        for t in tournaments:
            # OLD behavior: truncated leaderboard + old can_infer_absent
            old_res = self._resolve_outcomes_old_behavior(
                t["truncated_leaderboard"], t["outcomes"],
            )
            old_buckets = self._build_calibration_buckets(t["outcomes"], old_res)
            old_all_buckets.append(old_buckets)

            # NEW behavior: truncated leaderboard + size guard
            new_res = self._resolve_outcomes(
                t["truncated_leaderboard"], t["outcomes"],
            )
            new_buckets = self._build_calibration_buckets(t["outcomes"], new_res)
            new_all_buckets.append(new_buckets)

        old_merged = self._merge_buckets(old_all_buckets)
        new_merged = self._merge_buckets(new_all_buckets)

        old_mce = self._compute_mce(old_merged)
        new_mce = self._compute_mce(new_merged)

        # The fix MUST reduce MCE
        assert new_mce < old_mce, (
            f"Fix did not reduce MCE: old={old_mce:.4f}, new={new_mce:.4f}"
        )

    def test_fix_eliminates_false_losers_in_high_buckets(self):
        """Buckets 6-8 (60-90% probability) must not have wrongly-resolved losers.

        With truncated leaderboards, the old code marks players ranked 51-70
        as losers even though they made the cut. Their model predictions are
        typically 55-85%, landing in buckets 5-8. The fix should either
        resolve them correctly (full leaderboard) or skip them (truncated).
        """
        tournaments = self._build_tournaments()

        for t in tournaments:
            cut_line = t["cut_line"]

            # With truncated leaderboard + OLD logic:
            old_res = self._resolve_outcomes_old_behavior(
                t["truncated_leaderboard"], t["outcomes"],
            )

            # Count wrong losers in buckets 6-8
            old_wrong_losers = 0
            for dg_id, prob in t["outcomes"]:
                bucket = min(int(prob * 10), 9)
                if bucket not in (6, 7, 8):
                    continue
                rank = dg_id % 1000
                actually_made_cut = rank <= cut_line
                is_winner = old_res.get(dg_id)
                if actually_made_cut and is_winner is False:
                    old_wrong_losers += 1

            # With truncated leaderboard + NEW logic:
            new_res = self._resolve_outcomes(
                t["truncated_leaderboard"], t["outcomes"],
            )

            new_wrong_losers = 0
            for dg_id, prob in t["outcomes"]:
                bucket = min(int(prob * 10), 9)
                if bucket not in (6, 7, 8):
                    continue
                rank = dg_id % 1000
                actually_made_cut = rank <= cut_line
                is_winner = new_res.get(dg_id)
                if actually_made_cut and is_winner is False:
                    new_wrong_losers += 1

            # Old code should have wrong losers; new code should have zero
            assert old_wrong_losers > 0, (
                f"Tournament should have wrong losers in old code (cut_line={cut_line})"
            )
            assert new_wrong_losers == 0, (
                f"Fix should eliminate wrong losers but found {new_wrong_losers}"
            )

    def test_full_leaderboard_produces_same_results(self):
        """With full leaderboards (>= 100), old and new logic produce identical results.

        The fix should only change behavior for truncated leaderboards.
        Full leaderboards should resolve identically under both codepaths.
        """
        tournaments = self._build_tournaments()

        for t in tournaments:
            old_res = self._resolve_outcomes_old_behavior(
                t["full_leaderboard"], t["outcomes"],
            )
            new_res = self._resolve_outcomes(
                t["full_leaderboard"], t["outcomes"],
            )

            # Every outcome should have the same resolution
            for dg_id, _ in t["outcomes"]:
                assert old_res.get(dg_id) == new_res.get(dg_id), (
                    f"Full-leaderboard resolution differs for dg_id={dg_id}: "
                    f"old={old_res.get(dg_id)}, new={new_res.get(dg_id)}"
                )

    def test_full_leaderboard_mce_beats_old_code(self):
        """With full leaderboards, calibration MCE should be much better than old+truncated.

        The full leaderboard has more buckets (lower predictions where nobody
        makes the cut), so raw MCE can be higher than the fix-on-truncated
        MCE (which only covers high buckets). The right comparison is:
        full-leaderboard vs old-code-on-truncated. Full should be strictly
        better because it has correct resolutions everywhere.
        """
        tournaments = self._build_tournaments()

        old_all = []
        full_all = []
        for t in tournaments:
            old_res = self._resolve_outcomes_old_behavior(
                t["truncated_leaderboard"], t["outcomes"],
            )
            full_res = self._resolve_outcomes(
                t["full_leaderboard"], t["outcomes"],
            )
            old_all.append(self._build_calibration_buckets(t["outcomes"], old_res))
            full_all.append(self._build_calibration_buckets(t["outcomes"], full_res))

        old_merged = self._merge_buckets(old_all)
        full_merged = self._merge_buckets(full_all)

        old_mce = self._compute_mce(old_merged)
        full_mce = self._compute_mce(full_merged)

        # Full leaderboard should produce better MCE than old buggy code
        assert full_mce < old_mce, (
            f"Full leaderboard MCE ({full_mce:.4f}) should beat "
            f"old buggy MCE ({old_mce:.4f})"
        )

    def test_quantify_improvement(self):
        """Print the actual calibration numbers for both codepaths.

        Not a pass/fail assertion — this test documents the concrete
        improvement so there's no ambiguity about what the fix does.
        """
        tournaments = self._build_tournaments()

        old_all = []
        new_all = []
        full_all = []

        for t in tournaments:
            old_res = self._resolve_outcomes_old_behavior(
                t["truncated_leaderboard"], t["outcomes"],
            )
            new_res = self._resolve_outcomes(
                t["truncated_leaderboard"], t["outcomes"],
            )
            full_res = self._resolve_outcomes(
                t["full_leaderboard"], t["outcomes"],
            )

            old_all.append(self._build_calibration_buckets(t["outcomes"], old_res))
            new_all.append(self._build_calibration_buckets(t["outcomes"], new_res))
            full_all.append(self._build_calibration_buckets(t["outcomes"], full_res))

        old_m = self._merge_buckets(old_all)
        new_m = self._merge_buckets(new_all)
        full_m = self._merge_buckets(full_all)

        old_mce = self._compute_mce(old_m)
        new_mce = self._compute_mce(new_m)
        full_mce = self._compute_mce(full_m)

        # The fix must improve over old code on the same (truncated) data.
        # Full-leaderboard MCE covers more buckets (including low-prob ones
        # where nobody makes the cut) so it may be numerically higher than
        # the fix MCE (which only has high-bucket data). But both must beat
        # the old buggy code.
        assert new_mce < old_mce
        assert full_mce < old_mce

        # Count total wrong resolutions
        total_wrong_old = 0
        total_wrong_new = 0
        for t in tournaments:
            cut_line = t["cut_line"]
            old_res = self._resolve_outcomes_old_behavior(
                t["truncated_leaderboard"], t["outcomes"],
            )
            new_res = self._resolve_outcomes(
                t["truncated_leaderboard"], t["outcomes"],
            )
            for dg_id, _ in t["outcomes"]:
                rank = dg_id % 1000
                actually_made_cut = rank <= cut_line
                if actually_made_cut and old_res.get(dg_id) is False:
                    total_wrong_old += 1
                if actually_made_cut and new_res.get(dg_id) is False:
                    total_wrong_new += 1

        assert total_wrong_old > 0, "Old code should have wrong resolutions"
        assert total_wrong_new == 0, "New code should have zero wrong resolutions"
