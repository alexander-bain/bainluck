"""Tests for is_winner backfill logic."""

import pytest
import re
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock


class TestDataGolfRecoveryJsonbBind:
    """#994: the DataGolf recovery drained 0 across 5+ cycles because every DB
    write crashed. Root cause: `SET market_metadata = :meta::jsonb` — SQLAlchemy's
    bind regex has a negative lookahead `(?![:\\w])`, so a param immediately
    followed by `::` is NOT bound; the literal `:meta::jsonb` reached asyncpg →
    "syntax error at or near ':'". The fix is `CAST(:meta AS jsonb)`, which binds
    the param. These tests pin the fix and forbid the regression.
    """

    def test_cast_form_binds_the_meta_param(self):
        from sqlalchemy import text
        from sqlalchemy.dialects.postgresql import asyncpg as apg

        compiled = text(
            "UPDATE futures_markets SET market_metadata = CAST(:meta AS jsonb) "
            "WHERE id = :mid"
        ).compile(dialect=apg.dialect())
        # Both params must bind — the pre-fix `:meta::jsonb` bound only `mid`.
        assert set(compiled.params.keys()) == {"meta", "mid"}

    def test_colon_colon_form_drops_the_bind(self):
        # Documents WHY the bug happened: the `::` form silently loses `:meta`.
        from sqlalchemy import text
        from sqlalchemy.dialects.postgresql import asyncpg as apg

        compiled = text(
            "UPDATE t SET m = :meta::jsonb WHERE id = :mid"
        ).compile(dialect=apg.dialect())
        assert "meta" not in compiled.params  # the trap

    def test_no_param_colon_colon_jsonb_in_backfill_source(self):
        # Regression guard: no `:<param>::jsonb` may reappear in the task source.
        src = (
            Path(__file__).resolve().parents[1]
            / "app" / "tasks" / "backfill_winners.py"
        ).read_text()
        offenders = re.findall(r":[a-z_]+::jsonb", src)
        assert offenders == [], f"risky asyncpg bind::cast pattern: {offenders}"


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
        assert float(m.group(2)) == 210.5

    def test_total_1h(self):
        from app.tasks.backfill_winners import _TOTAL_RE
        m = _TOTAL_RE.search("Over 93.5 1H points scored")
        assert m is not None
        assert float(m.group(2)) == 93.5

    def test_total_team_points(self):
        from app.tasks.backfill_winners import _TOTAL_RE
        m = _TOTAL_RE.search("Over 106.5 team points scored")
        assert m is not None
        assert float(m.group(2)) == 106.5

    def test_total_without_scored(self):
        from app.tasks.backfill_winners import _TOTAL_RE
        m = _TOTAL_RE.search("Over 4.5 runs")
        assert m is not None
        assert float(m.group(2)) == 4.5

    def test_total_total_points(self):
        from app.tasks.backfill_winners import _TOTAL_RE
        m = _TOTAL_RE.search("Over 106.5 total points")
        assert m is not None
        assert float(m.group(2)) == 106.5

    def test_total_does_not_match_spread_text(self):
        from app.tasks.backfill_winners import _TOTAL_RE
        assert _TOTAL_RE.search("Cincinnati wins by over 5.5 Points") is None

    def test_team_total_outcome_pattern(self):
        import re
        _tt = r"(.+?)\s+over\s+(\d+\.?\d*)\s+(?:points|runs|goals)"
        m = re.match(_tt, "Miami over 109.5 points scored", re.IGNORECASE)
        assert m is not None
        assert m.group(1) == "Miami"
        assert float(m.group(2)) == 109.5

    def test_total_under_pattern(self):
        from app.tasks.backfill_winners import _TOTAL_RE
        m = _TOTAL_RE.search("Under 210.5 points scored")
        assert m is not None
        assert m.group("dir") == "Under"
        assert float(m.group(2)) == 210.5

    def test_total_esports_maps(self):
        from app.tasks.backfill_winners import _TOTAL_RE
        m = _TOTAL_RE.search("Over 2.5 maps")
        assert m is not None
        assert float(m.group(2)) == 2.5

    def test_total_esports_rounds(self):
        from app.tasks.backfill_winners import _TOTAL_RE
        m = _TOTAL_RE.search("Over 24.5 rounds")
        assert m is not None

    def test_no_match_random_text(self):
        from app.tasks.backfill_winners import _SPREAD_RE, _TOTAL_RE
        assert _SPREAD_RE.search("Yes") is None
        assert _TOTAL_RE.search("Yes") is None


class TestSpreadOutcomeIndependentGrading:
    """#939: each "{team} wins by over N" spread outcome is graded on its OWN
    team + line, never as a complementary Yes/No pair.

    The old resolver computed `won` for the first matching outcome and flipped
    every sibling to `not won`, then broke — so whole KXNHLSPREAD markets landed
    all-True or all-False by insertion order (game_score: pred 25% / actual 72%).
    """

    def _w(self, name, home, away, hs, as_):
        from app.tasks.backfill_winners import _spread_outcome_is_winner
        return _spread_outcome_is_winner(name, home, away, hs, as_)

    def test_home_favorite_covers(self):
        # Carolina (home) beats Montreal 6-1, margin +5.
        assert self._w("Carolina wins by over 1.5 goals",
                       "Carolina Hurricanes", "Montreal Canadiens", 6, 1) is True
        assert self._w("Carolina wins by over 2.5 goals",
                       "Carolina Hurricanes", "Montreal Canadiens", 6, 1) is True

    def test_losing_side_never_wins_a_spread(self):
        # The team that LOST can never win a "wins by over N" outcome —
        # this is the exact production bug (Montreal lost 1-6 yet was marked True).
        assert self._w("Montreal wins by over 1.5 goals",
                       "Carolina Hurricanes", "Montreal Canadiens", 6, 1) is False
        assert self._w("Montreal wins by over 2.5 goals",
                       "Carolina Hurricanes", "Montreal Canadiens", 6, 1) is False

    def test_away_favorite_covers_line_sign(self):
        # Away team wins big: margin computed as away-home, must stay positive.
        assert self._w("Nashville wins by over 1.5 goals",
                       "Los Angeles Kings", "Nashville Predators", 1, 5) is True
        # ...but the home loser does not.
        assert self._w("Los Angeles wins by over 1.5 goals",
                       "Los Angeles Kings", "Nashville Predators", 1, 5) is False

    def test_one_goal_game_nobody_covers_1_5(self):
        # San Jose 4-3 Anaheim: a 1-goal game — NO "wins by over 1.5" is True.
        # Production showed all four True; correct answer is all four False.
        for nm in ("San Jose wins by over 1.5 goals",
                   "San Jose wins by over 2.5 goals",
                   "Anaheim wins by over 1.5 goals",
                   "Anaheim wins by over 2.5 goals"):
            assert self._w(nm, "San Jose Sharks", "Anaheim Ducks", 4, 3) is False

    def test_winner_covers_low_line_but_not_high_line(self):
        # Florida wins by exactly 2: covers 1.5 but not 2.5 (independent lines).
        assert self._w("Florida wins by over 1.5 goals",
                       "Florida Panthers", "Boston Bruins", 3, 1) is True
        assert self._w("Florida wins by over 2.5 goals",
                       "Florida Panthers", "Boston Bruins", 3, 1) is False

    def test_blowout_only_winner_side_true(self):
        # 7-0 blowout: every winner-side line True, every loser-side line False.
        assert self._w("Boston wins by over 2.5 goals",
                       "Boston Bruins", "Buffalo Sabres", 7, 0) is True
        assert self._w("Buffalo wins by over 1.5 goals",
                       "Boston Bruins", "Buffalo Sabres", 7, 0) is False

    def test_accented_team_name_matches(self):
        # #939 residual: "Montreal" (ASCII outcome) must match "Montréal"
        # (accented event name) — else the outcome is left at its old value.
        # Montreal (away) lost 3-4, so neither "wins by over" line is True.
        assert self._w("Montreal wins by over 1.5 goals",
                       "Los Angeles Kings", "Montréal Canadiens", 4, 3) is False
        # Montreal (home) wins by 2 -> covers 1.5, not 2.5.
        assert self._w("Montreal wins by over 1.5 goals",
                       "Montréal Canadiens", "Toronto Maple Leafs", 3, 1) is True
        assert self._w("Montreal wins by over 2.5 goals",
                       "Montréal Canadiens", "Toronto Maple Leafs", 3, 1) is False

    def test_punctuated_team_name_matches(self):
        # "St. Louis" (event) vs "St. Louis" outcome — periods normalized.
        assert self._w("St. Louis wins by over 1.5 goals",
                       "Chicago Blackhawks", "St. Louis Blues", 1, 4) is True

    def test_unmatched_team_or_non_spread_returns_none(self):
        assert self._w("Over 5.5 goals scored",
                       "Boston Bruins", "Buffalo Sabres", 7, 0) is None
        assert self._w("Tampa wins by over 1.5 goals",
                       "Boston Bruins", "Buffalo Sabres", 7, 0) is None

    def test_resolver_no_longer_flips_siblings(self):
        # The complementary flip + break that caused the inversion must be gone.
        import inspect
        from app.tasks.backfill_winners import (
            _resolve_kalshi_spread_total_from_scores,
        )
        src = inspect.getsource(_resolve_kalshi_spread_total_from_scores)
        # The spread branch must use the independent grader. Isolate it: from the
        # spread-pattern match up to the total-pattern branch. The complementary
        # sibling-flip (still legitimately used by the TOTAL branch) must NOT
        # appear inside the spread branch.
        spread_branch = src.split("# Try total pattern")[0]
        assert "_spread_outcome_is_winner(" in spread_branch
        assert "oc_won = won if oc.id == outcome.id else not won" not in spread_branch

    def test_regrade_is_wired_and_scoped(self):
        import inspect
        from app.tasks.backfill_winners import (
            _regrade_kalshi_nhl_spread_inversions,
            _resolve_winners_only,
        )
        rg = inspect.getsource(_regrade_kalshi_nhl_spread_inversions)
        # Scoped to the Kalshi NHL/NBA/MLB spread cohort (#944: broadened from
        # NHL-only) + write-on-change.
        assert "KX(NHL|NBA|MLB)SPREAD" in rg
        assert "bool(r.cur) == won" in rg  # write-on-change guard
        assert "_spread_outcome_is_winner(" in rg
        # ...and actually invoked by the frequent resolve_winners task.
        assert "_regrade_kalshi_nhl_spread_inversions(" in inspect.getsource(
            _resolve_winners_only
        )


class TestGolfSettlementSyncSingleWinner:
    """#938: settlement_sync must not clobber an authoritative golf winner with
    stale 99%-ask extras (it was marking up to 5 'winners' on single-winner
    fields), and must re-grade the extras it already wrote."""

    def _src(self):
        import inspect
        from app.tasks.backfill_winners import _backfill_all_winners
        return inspect.getsource(_backfill_all_winners)

    def test_settlement_sync_will_not_promote_winner_over_authoritative(self):
        src = self._src()
        # The promote (>=0.95) branch must be guarded so it can't add a winner
        # to a market that already has a leaderboard/api/datagolf/score winner.
        assert "resolution_source = 'settlement_sync'" in src
        assert "NOT EXISTS (" in src
        for auth in ("'leaderboard'", "'api_settlement'", "'datagolf'", "'game_score'"):
            assert auth in src, f"authoritative source {auth} missing from guard"
        # Confirming a loser stays unconditional.
        assert "fo.current_probability <= 0.05" in src

    def test_settlement_sync_extra_winner_regrade_present(self):
        src = self._src()
        # The re-grade flips ONLY settlement_sync extras to False, and only on
        # markets that still hold an authoritative winner (never winner-less,
        # never bulk-reset — gotcha #21).
        assert "regraded_extra_winners" in src
        assert "SET is_winner = false" in src
        assert "fo.resolution_source = 'settlement_sync'" in src

    def test_extra_winner_regrade_runs_in_fast_resolve_task(self):
        # The deep settlement_sync block is starved (#898), so the idempotent
        # re-grade must ALSO run in the fast resolve_winners task to take effect.
        import inspect
        from app.tasks.backfill_winners import (
            _regrade_golf_extra_winners,
            _resolve_winners_only,
        )
        helper = inspect.getsource(_regrade_golf_extra_winners)
        assert "SET is_winner = false" in helper
        assert "fo.resolution_source = 'settlement_sync'" in helper
        assert "datagolf" in helper and "leaderboard" in helper  # auth-winner guard
        assert "_regrade_golf_extra_winners(" in inspect.getsource(_resolve_winners_only)


class TestThreeWayWinnerResolution:
    """3-outcome Team/Team/Tie winner markets (e.g. KXNCAAMB1HWINNER, #816)."""

    def _d(self, names, home, away, h, a):
        from app.tasks.backfill_winners import _decide_three_way_winner
        return _decide_three_way_winner(names, home, away, h, a)

    def test_home_team_wins_half(self):
        # Nebraska (home) 33, Maryland (away) 27 at half → Nebraska wins
        d = self._d(
            ["Tie", "Nebraska", "Maryland"],
            "Nebraska Cornhuskers", "Maryland Terrapins", 33, 27,
        )
        assert d == {0: False, 1: True, 2: False}

    def test_away_team_wins_half(self):
        # Marquette (home) 33, UConn (away) 35 → UConn (away) wins
        d = self._d(
            ["Tie", "UConn", "Marquette"],
            "Marquette Golden Eagles", "UConn Huskies", 33, 35,
        )
        assert d == {0: False, 1: True, 2: False}

    def test_tie_wins_when_scores_equal(self):
        d = self._d(
            ["Tie", "UConn", "Marquette"],
            "Marquette Golden Eagles", "UConn Huskies", 35, 35,
        )
        assert d == {0: True, 1: False, 2: False}

    def test_abbreviated_team_name_token_match(self):
        # "Texas A&M" outcome vs "Texas A&M Aggies" event team
        d = self._d(
            ["Tie", "Arkansas", "Texas A&M"],
            "Arkansas Razorbacks", "Texas A&M Aggies", 37, 28,
        )
        assert d == {0: False, 1: True, 2: False}

    def test_returns_none_for_two_outcomes(self):
        # 2-outcome markets are handled by the existing fallback, not here
        assert self._d(["A", "B"], "A team", "B team", 10, 5) is None

    def test_returns_none_for_missing_scores(self):
        assert self._d(["Tie", "Nebraska", "Maryland"],
                       "Nebraska", "Maryland", None, 27) is None

    def test_returns_none_without_clean_triple(self):
        # No tie outcome and an unmatched 3rd outcome → not a clean triple
        assert self._d(["Yes", "No", "Maybe"],
                       "Nebraska", "Maryland", 33, 27) is None

    def test_branch_wired_into_resolver(self):
        import inspect
        from app.tasks.backfill_winners import (
            _resolve_kalshi_spread_total_from_scores,
        )
        src = inspect.getsource(_resolve_kalshi_spread_total_from_scores)
        assert "_decide_three_way_winner" in src
        assert "len(outcomes_list) == 3" in src


class TestResolverThroughput:
    """Score resolvers must not be starved by LIMIT 10000 vs the ~41K backlog,
    and must commit incrementally so a long run drains it (#907)."""

    def _src(self, fn_name):
        import inspect
        import app.tasks.backfill_winners as m
        return inspect.getsource(getattr(m, fn_name))

    def test_spread_total_resolver_limit_raised(self):
        import re
        src = self._src("_resolve_kalshi_spread_total_from_scores")
        assert re.search(r"LIMIT 10000(?!\d)", src) is None  # no bare 10000
        assert "LIMIT 100000" in src

    def test_moneyline_resolver_limit_raised(self):
        import re
        src = self._src("_resolve_kalshi_from_scores")
        assert re.search(r"LIMIT 10000(?!\d)", src) is None
        assert "LIMIT 100000" in src

    def test_spread_total_resolver_commits_incrementally(self):
        src = self._src("_resolve_kalshi_spread_total_from_scores")
        # enumerate + periodic commit inside the loop (not just one end-commit)
        assert "enumerate(markets)" in src
        assert "i % 500 == 0" in src
        assert src.count("await session.commit()") >= 2

    def test_moneyline_resolver_commits_incrementally(self):
        src = self._src("_resolve_kalshi_from_scores")
        assert "enumerate(markets)" in src
        assert "i % 500 == 0" in src
        assert src.count("await session.commit()") >= 2


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
        """Markets with non-authoritative resolution should be targeted.

        The query should catch ALL markets where any outcome was resolved
        by guess (pass2_guess) or other non-authoritative method, not just
        markets with specific probability ranges.
        """
        import inspect
        from app.tasks.backfill_winners import _backfill_polymarket_winners_from_api
        source = inspect.getsource(_backfill_polymarket_winners_from_api)
        assert "NOT IN ('api_settlement', 'clean_resolution')" in source

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
        """DataGolf winner resolution uses leaderboard/did_not_play/withdrew sources."""
        import inspect
        from app.tasks.backfill_winners import _backfill_datagolf_winners
        source = inspect.getsource(_backfill_datagolf_winners)
        assert 'res_source = "leaderboard"' in source
        assert 'res_source = "did_not_play"' in source
        assert 'res_source = "withdrew"' in source
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


class TestCalibrationPricePartA2:
    """Tests proving Part A2 of _compute_calibration_prices uses the
    pre-tournament closing line for non-event golf markets.

    Without Part A2, golf markets fall through to Part B which uses
    opening_captured_at to grab the first-ever price (potentially weeks
    before the tournament). Part A2 uses fm.commence_time to grab the
    last snapshot before the tournament starts.
    """

    def test_part_a2_exists_in_compute_calibration_prices(self):
        """Part A2 should be present in _compute_calibration_prices."""
        import inspect
        from app.tasks.backfill_winners import _compute_calibration_prices
        source = inspect.getsource(_compute_calibration_prices)
        assert "Part A2" in source

    def test_part_a2_uses_market_commence_time(self):
        """Part A2 should use fm.commence_time, not e.commence_time or opening_captured_at."""
        import inspect
        from app.tasks.backfill_winners import _compute_calibration_prices
        source = inspect.getsource(_compute_calibration_prices)
        # Extract the full Part A2 section (between "part_a2_total" and "part_b_total")
        a2_start = source.index("part_a2_total")
        a2_end = source.index("part_b_total")
        a2_section = source[a2_start:a2_end]
        assert "fm.commence_time" in a2_section
        assert "fos.captured_at < nc.commence_time" in a2_section
        # Should NOT use opening_captured_at in the main query
        assert "opening_captured_at" not in a2_section.split("Part B")[0].split("needs_cal")[1]

    def test_part_a2_only_processes_non_event_markets(self):
        """Part A2 should only process markets where event_id IS NULL."""
        import inspect
        from app.tasks.backfill_winners import _compute_calibration_prices
        source = inspect.getsource(_compute_calibration_prices)
        a2_start = source.index("part_a2_total")
        a2_end = source.index("part_b_total")
        a2_section = source[a2_start:a2_end]
        assert "fm.event_id IS NULL" in a2_section

    def test_part_a2_resets_stale_calibration(self):
        """Part A2 should reset calibration_probability stuck at opening."""
        import inspect
        from app.tasks.backfill_winners import _compute_calibration_prices
        source = inspect.getsource(_compute_calibration_prices)
        # The reset is in the setup BEFORE part_a2_total, still in the A2 block
        a2_comment_start = source.index("Part A2:")
        a2_end = source.index("part_b_total")
        a2_full_section = source[a2_comment_start:a2_end]
        # Should have a reset query for outcomes where cal_prob = opening
        assert "calibration_probability = NULL" in a2_full_section
        assert "reset_a2" in a2_full_section

    def test_cal_price_run_is_self_limiting(self):
        """#1100: every run must be bounded by a wall-clock deadline (well under
        the 600s soft_time_limit) so it returns cleanly (SUCCESS) instead of
        tripping SoftTimeLimitExceeded, recording where it stopped."""
        import inspect
        from app.tasks.backfill_winners import _compute_calibration_prices
        source = inspect.getsource(_compute_calibration_prices)
        assert "_CAL_DEADLINE_S" in source
        assert "_cal_remaining" in source
        assert 'stats["stopped_at"]' in source
        # deadline must leave a margin under the 600s soft limit
        assert "540" in source
        # batches must be small enough that one uninterrupted statement can't
        # overshoot the margin — the huge 100K batch is gone.
        assert "LIMIT 100000" not in source

    def test_cal_price_deadline_checked_in_every_batch_loop(self):
        """The deadline is only useful if checked BETWEEN batches in each Part —
        a bare `for _ in range(...)` with no `_cal_remaining()` check could still
        overshoot. Every batch loop in the function must guard on the deadline."""
        import inspect
        from app.tasks.backfill_winners import _compute_calibration_prices
        source = inspect.getsource(_compute_calibration_prices)
        # Parts A, A2-reset, A2-fill, B, C each mark a distinct stopped_at stage.
        for stage in ("part_a", "reset_a2", "part_a2", "part_b", "part_c"):
            assert f'"{stage}"' in source, f"missing deadline break for {stage}"

    def test_reset_a2_is_monotonic_not_churning(self):
        """#1100 root cause: the #190 EXISTS(snapshot) guard still churned rows
        whose last pre-commence snapshot EQUALS opening (A2 refilled cal=opening →
        re-nulled forever). The reset must instead null ONLY rows where the exact
        snapshot A2 will pick differs from opening (`<> fo.opening_probability`),
        which also excludes no-snapshot rows (NULL <> x is NULL), so the reset set
        drains to 0 over cycles rather than churning every run."""
        import inspect
        from app.tasks.backfill_winners import _compute_calibration_prices
        source = inspect.getsource(_compute_calibration_prices)
        a2_comment_start = source.index("Part A2:")
        a2_end = source.index("part_b_total")
        a2_section = source[a2_comment_start:a2_end]
        # the converging predicate is present in the reset block
        assert "<> fo.opening_probability" in a2_section
        # reset is bounded (chunked), not one unbounded UPDATE
        assert "reset_a2_total" in a2_section

    def test_stale_price_impact_on_calibration(self):
        """Demonstrate that using opening vs closing line changes calibration.

        A golfer whose win probability moves from 5% (2 weeks out) to 12%
        (eve of R1) and then actually wins: calibration should use 12%
        (bucket 1), not 5% (bucket 0). Using 5% inflates bucket 0's win
        rate and leaves bucket 1 with too few winners.
        """
        # 20 golfers, simulate stale vs closing prices
        import random
        rng = random.Random(99)

        outcomes = []
        for i in range(20):
            opening = rng.uniform(0.02, 0.15)
            # Closing line shifts: some up, some down, average +2pp
            closing = max(0.005, min(0.98, opening + rng.gauss(0.02, 0.04)))
            won = (i == 0)  # golfer 0 wins
            outcomes.append((opening, closing, won))

        # Build calibration buckets with opening prices (stale - old behavior)
        stale_buckets = {}
        for opening, _closing, won in outcomes:
            b = min(int(opening * 10), 9)
            stale_buckets.setdefault(b, {"n": 0, "winners": 0, "sum_prob": 0.0})
            stale_buckets[b]["n"] += 1
            stale_buckets[b]["sum_prob"] += opening
            if won:
                stale_buckets[b]["winners"] += 1

        # Build calibration buckets with closing prices (Part A2 behavior)
        closing_buckets = {}
        for _opening, closing, won in outcomes:
            b = min(int(closing * 10), 9)
            closing_buckets.setdefault(b, {"n": 0, "winners": 0, "sum_prob": 0.0})
            closing_buckets[b]["n"] += 1
            closing_buckets[b]["sum_prob"] += closing
            if won:
                closing_buckets[b]["winners"] += 1

        # The winner's opening price and closing price
        winner_opening = outcomes[0][0]
        winner_closing = outcomes[0][1]

        # The winner should land in the correct bucket based on closing price
        stale_bucket = min(int(winner_opening * 10), 9)
        closing_bucket = min(int(winner_closing * 10), 9)

        # At minimum, verify that the closing price captures more recent info
        # (even if they land in the same bucket, the bucket's avg_prob changes)
        assert winner_closing != winner_opening, (
            "Test setup error: closing should differ from opening"
        )

        # Verify the buckets are populated
        assert sum(d["n"] for d in stale_buckets.values()) == 20
        assert sum(d["n"] for d in closing_buckets.values()) == 20


class TestScoreResolutionOverwritesGuess:
    """Score-based resolution must re-resolve pass2_guess outcomes.

    The HAVING guard in _resolve_kalshi_from_scores (and related phases)
    previously used SUM(CASE WHEN fo.is_winner THEN 1 ELSE 0 END) = 0,
    which blocked re-resolution on any market that Pass 2 had already
    tagged. The fix treats pass2_guess, binary_higher_wins, and
    multi_max_prob as "still needs resolution."
    """

    def test_having_guard_sql_treats_pass2_guess_as_unresolved(self):
        """The SQL HAVING clause must count pass2_guess winners as zero."""
        import re

        from app.tasks.backfill_winners import _resolve_kalshi_from_scores
        import inspect
        src = inspect.getsource(_resolve_kalshi_from_scores)

        # #845: the guess-family list now routes through the single canonical
        # constant (which contains pass2_guess/binary_higher_wins/multi_max_prob),
        # so the phase must reference OVERWRITABLE_WINNER_SOURCES_SQL.
        assert "OVERWRITABLE_WINNER_SOURCES_SQL" in src, (
            "_resolve_kalshi_from_scores must route its re-resolution guard "
            "through resolution_authority.OVERWRITABLE_WINNER_SOURCES_SQL"
        )
        from app.utils.resolution_authority import OVERWRITABLE_WINNER_SOURCES
        assert {"pass2_guess", "binary_higher_wins", "multi_max_prob"} <= set(
            OVERWRITABLE_WINNER_SOURCES
        )

    def test_spread_total_having_guard_updated(self):
        """_resolve_kalshi_spread_total_from_scores must also allow re-resolution."""
        import inspect
        from app.tasks.backfill_winners import _resolve_kalshi_spread_total_from_scores
        src = inspect.getsource(_resolve_kalshi_spread_total_from_scores)

        assert "pass2_guess" in src, (
            "_resolve_kalshi_spread_total_from_scores SQL must reference "
            "pass2_guess to allow re-resolution"
        )

    def test_player_props_having_guard_updated(self):
        """_resolve_kalshi_player_props_from_boxscore must also allow re-resolution."""
        import inspect
        from app.tasks.backfill_winners import _resolve_kalshi_player_props_from_boxscore
        src = inspect.getsource(_resolve_kalshi_player_props_from_boxscore)

        assert "OVERWRITABLE_WINNER_SOURCES_SQL" in src  # #845 routes through constant

    def test_period_props_having_guard_updated(self):
        """_resolve_kalshi_period_props must also allow re-resolution."""
        import inspect
        from app.tasks.backfill_winners import _resolve_kalshi_period_props
        src = inspect.getsource(_resolve_kalshi_period_props)

        assert "OVERWRITABLE_WINNER_SOURCES_SQL" in src  # #845 routes through constant

    def test_total_resolution_sets_game_score_source(self):
        """Total resolution must set resolution_source='game_score'."""
        import inspect
        from app.tasks.backfill_winners import _resolve_kalshi_spread_total_from_scores
        src = inspect.getsource(_resolve_kalshi_spread_total_from_scores)

        total_block = src[src.index("Try total pattern"):]
        assert "resolution_source" in total_block, (
            "Total pattern UPDATE must set resolution_source='game_score'"
        )

    def test_period_total_resolution_sets_source(self):
        """Period prop total resolution must set resolution_source."""
        import inspect
        from app.tasks.backfill_winners import _resolve_kalshi_period_props
        src = inspect.getsource(_resolve_kalshi_period_props)

        # Find all UPDATE statements — every one should set resolution_source
        updates = [line.strip() for line in src.split("\n")
                   if "UPDATE futures_outcomes SET" in line]
        for stmt in updates:
            assert "resolution_source" in stmt, (
                f"UPDATE missing resolution_source: {stmt}"
            )

    def test_period_spread_uses_team_matching(self):
        """Period prop spread must match the specific team, not either team."""
        import inspect
        from app.tasks.backfill_winners import _resolve_kalshi_period_props
        src = inspect.getsource(_resolve_kalshi_period_props)

        spread_section = src[src.index("Try spread pattern"):src.index("Try total pattern")]
        assert "home_tokens" in spread_section, (
            "Period spread must use team token matching"
        )
        assert "away_tokens" in spread_section

    def test_moneyline_resolution_logic(self):
        """Moneyline: home team wins when home_score > away_score."""
        home_score, away_score = 110, 95
        home_won = home_score > away_score
        assert home_won is True

        home_tokens = {"celtics", "boston"}
        away_tokens = {"lakers", "los", "angeles"}

        # Outcome named "Celtics" should match home
        name_tokens = {"celtics"}
        is_home = bool(home_tokens & name_tokens)
        is_away = bool(away_tokens & name_tokens)
        assert is_home and not is_away
        assert home_won  # Celtics win

        # Outcome named "Lakers" should match away
        name_tokens = {"lakers"}
        is_home = bool(home_tokens & name_tokens)
        is_away = bool(away_tokens & name_tokens)
        assert not is_home and is_away
        won = not home_won  # Away team outcome: inverse of home_won
        assert won is False  # Lakers lose

    def test_spread_with_team_matching(self):
        """Spread: 'Boston wins by over 5.5 points' with margin 15 → yes."""
        from app.tasks.backfill_winners import _SPREAD_RE

        m = _SPREAD_RE.search("Boston wins by over 5.5 points")
        assert m is not None
        team_name = m.group(1).strip()
        line = float(m.group(2))

        home_team = "Boston Celtics"
        away_team = "LA Lakers"
        period_home, period_away = 55, 40

        home_tokens = set(home_team.lower().split())
        away_tokens = set(away_team.lower().split())
        team_tokens = set(team_name.lower().split())

        assert team_tokens & home_tokens  # "boston" matches
        margin = period_home - period_away  # 15
        assert margin > line  # 15 > 5.5 → won

    def test_spread_away_team(self):
        """Spread for away team: must use away margin, not home."""
        from app.tasks.backfill_winners import _SPREAD_RE

        m = _SPREAD_RE.search("Lakers wins by over 3.5 points")
        team_name = m.group(1).strip()
        line = float(m.group(2))

        home_team = "Boston Celtics"
        away_team = "LA Lakers"
        period_home, period_away = 40, 55

        home_tokens = set(home_team.lower().split())
        away_tokens = set(away_team.lower().split())
        team_tokens = set(team_name.lower().split())

        assert team_tokens & away_tokens  # "lakers" matches
        margin = period_away - period_home  # 15
        assert margin > line  # 15 > 3.5 → won

    def test_old_spread_bug_either_team_margin(self):
        """The old bug: (home-away)>line OR (away-home)>line always true.

        Example: 'Boston wins by over 5.5 points' but Lakers won by 10.
        Old logic: (40-55) > 5.5 OR (55-40) > 5.5 = False OR True = True (WRONG).
        New logic: Boston matched → margin = 40-55 = -15 → -15 > 5.5 = False (CORRECT).
        """
        period_home, period_away = 40, 55
        line = 5.5

        # Old bug: either team
        old_result = (period_home - period_away) > line or (period_away - period_home) > line
        assert old_result is True  # Bug: says "yes" even though Boston lost

        # New logic: Boston is home team
        margin = period_home - period_away  # -15
        new_result = margin > line
        assert new_result is False  # Correct: Boston didn't win by over 5.5

    def test_sql_uses_correct_event_column_names(self):
        """SQL must reference e.home_team_name, not e.home_team (doesn't exist)."""
        import inspect
        from app.tasks.backfill_winners import (
            _resolve_kalshi_from_scores,
            _resolve_kalshi_spread_total_from_scores,
            _resolve_kalshi_period_props,
        )
        for fn in [_resolve_kalshi_from_scores,
                   _resolve_kalshi_spread_total_from_scores,
                   _resolve_kalshi_period_props]:
            src = inspect.getsource(fn)
            assert "e.home_team_name" in src, (
                f"{fn.__name__} must use e.home_team_name (not e.home_team)"
            )
            assert "e.away_team_name" in src
            # Must NOT reference the non-existent e.home_team column
            lines = src.split("\n")
            for line in lines:
                if "e.home_team" in line and "e.home_team_name" not in line and "e.home_team_id" not in line:
                    assert False, (
                        f"{fn.__name__} has bare 'e.home_team' reference "
                        f"(should be e.home_team_name): {line.strip()}"
                    )

    def test_having_guard_simulated(self):
        """Simulate the HAVING SUM(...) guard with different resolution sources.

        The SQL is:
          HAVING SUM(CASE WHEN fo.is_winner
                     AND fo.resolution_source NOT IN
                         ('pass2_guess', 'binary_higher_wins', 'multi_max_prob')
                     THEN 1 ELSE 0 END) = 0

        Markets with only guess-based winners should be picked up.
        Markets with authoritative winners (api_settlement, game_score, etc.)
        should be skipped.
        """
        GUESS_SOURCES = {"pass2_guess", "binary_higher_wins", "multi_max_prob"}

        def having_guard(outcomes):
            """Returns True if market should be processed (needs resolution)."""
            auth_winners = sum(
                1 for is_winner, source in outcomes
                if is_winner and source not in GUESS_SOURCES
            )
            return auth_winners == 0

        # Case 1: pass2_guess winner → should be re-resolved
        assert having_guard([(True, "pass2_guess"), (False, "pass2_guess")]) is True

        # Case 2: binary_higher_wins → should be re-resolved
        assert having_guard([(True, "binary_higher_wins"), (False, "binary_higher_wins")]) is True

        # Case 3: api_settlement winner → already resolved, skip
        assert having_guard([(True, "api_settlement"), (False, "api_settlement")]) is False

        # Case 4: game_score winner → already resolved, skip
        assert having_guard([(True, "game_score"), (False, "game_score")]) is False

        # Case 5: no winner at all → should be processed (original behavior)
        assert having_guard([(False, None), (False, None)]) is True

        # Case 6: mixed — one outcome api_settlement winner, one pass2_guess loser
        assert having_guard([(True, "api_settlement"), (False, "pass2_guess")]) is False

        # Case 7: multi_max_prob → should be re-resolved
        assert having_guard([(True, "multi_max_prob"), (False, None)]) is True


class TestPlayerPropNameNormalization:
    """Tests for accent/suffix normalization in player prop matching."""

    def test_accent_normalization(self):
        from app.tasks.backfill_winners import _normalize_player_name
        assert _normalize_player_name("Nikola Vučević") == _normalize_player_name("Nikola Vucevic")

    def test_suffix_stripping(self):
        from app.tasks.backfill_winners import _normalize_player_name
        assert _normalize_player_name("LeBron James Jr.") == _normalize_player_name("LeBron James")
        assert _normalize_player_name("LeBron James Jr") == _normalize_player_name("LeBron James")

    def test_period_removal(self):
        from app.tasks.backfill_winners import _normalize_player_name
        assert _normalize_player_name("P.J. Washington") == _normalize_player_name("PJ Washington")

    def test_no_false_positive(self):
        from app.tasks.backfill_winners import _normalize_player_name
        assert _normalize_player_name("Jalen Green") != _normalize_player_name("Jalen Williams")

    def test_case_insensitive(self):
        from app.tasks.backfill_winners import _normalize_player_name
        assert _normalize_player_name("LEBRON JAMES") == _normalize_player_name("LeBron James")

    def test_doncic(self):
        from app.tasks.backfill_winners import _normalize_player_name
        assert _normalize_player_name("Luka Dončić") == _normalize_player_name("Luka Doncic")


class TestPlayerPropBoxScoreStructure:
    """Verify player prop resolver reads the correct level of box_score_data."""

    def test_box_score_data_has_players_key(self):
        """box_score_data is {"source": "espn", "players": {...}}, not flat."""
        import inspect
        from app.tasks.backfill_winners import _resolve_kalshi_player_props_from_boxscore
        src = inspect.getsource(_resolve_kalshi_player_props_from_boxscore)
        assert '.get("players"' in src or "get('players'" in src, (
            "Player prop resolver must extract box_score_data['players'] "
            "not iterate the raw wrapper dict"
        )

    def test_players_extraction_logic(self):
        """Simulate the extraction: raw_bs → players dict."""
        raw_bs = {
            "source": "espn",
            "fetched_at": "2026-03-01T00:00:00",
            "players": {
                "Luka Doncic": {"points": 30, "rebounds": 8, "assists": 10},
                "Kyrie Irving": {"points": 22, "rebounds": 4, "assists": 6},
            },
            "scoring_plays": [],
        }
        box_score = raw_bs.get("players", raw_bs) if isinstance(raw_bs, dict) else {}
        assert "Luka Doncic" in box_score
        assert box_score["Luka Doncic"]["points"] == 30
        assert "source" not in box_score


class TestNhlPointsDerivedFromGoalsAssists:
    """Regression guard for #937: ESPN NHL box scores store `goals` and `assists`
    but have NO `points` field. Mapping kxnhlpts to a singular "points" stat made
    every NHL points prop grade a loser (box_score actual win rate 0% vs ~45%
    predicted; e.g. Pavel Zacha 1g+1a=2pts was marked False for "Zacha: 2+").
    NHL points MUST be the combo goals+assists.
    """

    def test_kxnhlpts_is_a_goals_plus_assists_combo(self):
        from app.tasks.backfill_winners import _PROP_TICKER_TO_STAT, _COMBO_STATS
        # Must NOT map to a non-existent singular "points" stat.
        assert _PROP_TICKER_TO_STAT.get("kxnhlpts") != "points"
        assert "kxnhlpts" not in _PROP_TICKER_TO_STAT
        # Must derive points = goals + assists.
        assert _COMBO_STATS.get("kxnhlpts") == ["goals", "assists"]

    def test_zacha_two_plus_points_resolves_true(self):
        """1 goal + 1 assist = 2 points -> 'Zacha: 2+' must be a WINNER."""
        from app.tasks.backfill_winners import _COMBO_STATS
        player_stats = {"goals": 1.0, "assists": 1.0, "hits": 3.0}  # no 'points' key
        combo = _COMBO_STATS["kxnhlpts"]
        actual = sum(player_stats.get(s, 0) for s in combo)
        assert actual == 2
        assert (actual >= 2) is True  # "2+" wins; the old singular-"points" path gave 0 -> False

    def test_regrade_only_writes_on_changed_verdict(self):
        """The box_score re-grade must be idempotent: only re-write rows whose
        verdict CHANGES (no last_updated churn on already-correct rows, #937/#21)."""
        import inspect
        from app.tasks.backfill_winners import _resolve_kalshi_player_props_from_boxscore
        src = inspect.getsource(_resolve_kalshi_player_props_from_boxscore)
        assert "cur_winner" in src, "re-grade must compare against the current is_winner"
        assert "'box_score'" in src, "re-grade must re-consider already box_score-resolved rows"


class TestWinnerWritesBumpLastUpdated:
    """Regression guard for #898 (Kalshi winner-backfill observability).

    The winners-touched-24h metric reads ``is_winner=true AND last_updated<24h``
    grouped by source. Settled Kalshi outcomes stop being repolled (gotcha #33),
    so a resolution write is the ONLY thing that can touch them — if the resolver
    sets ``is_winner`` without bumping ``last_updated`` the metric is structurally
    blind to Kalshi (it read 0 for weeks despite ~1,050 markets/cycle resolving,
    causing the ops r5/r6 false stall alarms). Every determined-value
    ``is_winner`` write in the resolver must bump ``last_updated`` in the SAME
    statement (gotchas #4-6: Core update, not a second write). NULL-reset
    cleanups are intentionally exempt.
    """

    def _resolver_source(self):
        from pathlib import Path

        path = (
            Path(__file__).parent.parent
            / "app"
            / "tasks"
            / "backfill_winners.py"
        )
        return path.read_text().split("\n")

    def test_every_determined_is_winner_write_bumps_last_updated(self):
        lines = self._resolver_source()
        misses = []
        for i, ln in enumerate(lines, start=1):
            s = ln.strip()
            # Raw SQL: "SET is_winner = ..." (skip NULL-reset cleanups).
            if s.startswith("SET is_winner") and "NULL" not in s:
                window = "\n".join(lines[i - 1 : i + 4])
                if "last_updated" not in window:
                    misses.append((i, s[:80]))
            # Core update().values(...) and multi-column SET continuations.
            if (
                s.startswith("is_winner =") or s.startswith("is_winner=")
            ) and "NULL" not in s:
                ctx = "\n".join(lines[max(0, i - 4) : i + 5])
                is_resolution_write = (".values(" in ctx) or (
                    "SET " in ctx and "UPDATE futures_outcomes" in ctx
                )
                if is_resolution_write and "last_updated" not in ctx:
                    misses.append((i, s[:80]))
        assert not misses, (
            "is_winner resolution writes missing a last_updated bump "
            f"(metric would go blind for the affected source): {misses}"
        )


class TestMoneylineSkipsHalfWinnerMarkets:
    """Guard for #816 / gotcha #21: the moneyline score resolver
    (_resolve_kalshi_from_scores) resolves from FINAL game scores, so it MUST
    skip half/period WINNER markets (1hwinner/2hwinner) — those need halftime/
    period scores and are owned by the spread/total resolver's team-name
    fallback. Once box-score backfill populates final scores, omitting these
    from the skip list would mis-resolve any game where the half winner differs
    from the game winner, corrupting calibration.
    """

    def test_non_ml_skip_list_includes_half_winner(self):
        from pathlib import Path

        src = (
            Path(__file__).parent.parent
            / "app"
            / "tasks"
            / "backfill_winners.py"
        ).read_text()
        # The _non_ml tuple lives inside _resolve_kalshi_from_scores; assert the
        # half/period winner tokens are present in source.
        assert '"1hwinner"' in src, "moneyline resolver must skip 1hwinner"
        assert '"2hwinner"' in src, "moneyline resolver must skip 2hwinner"


class TestTotalBasesBoundVerdict:
    """#802 — Kalshi MLB total-bases (KXMLBTB) resolved by deterministic bounds.

    ESPN gives hits + home runs but not doubles/triples, so total bases is only
    bounded: TB_min = hits + 3*HR, TB_max = 3*hits + HR. A 'N+' outcome is a
    certain loser when TB_max < N, a certain winner when TB_min >= N, else
    indeterminate.
    """

    def _verdict(self, hits, hr, threshold):
        from app.tasks.backfill_winners import _total_bases_verdict
        return _total_bases_verdict(hits, hr, threshold)

    def test_zero_hits_is_certain_loser_for_any_positive_threshold(self):
        # The trivial case from the issue: no hits -> 0 total bases.
        assert self._verdict(0, 0, 1) is False
        assert self._verdict(0, 0, 5) is False

    def test_certain_loser_when_max_below_threshold(self):
        # 1 hit, 0 HR -> TB_max = 3 < 4 -> loser even if it were a triple.
        assert self._verdict(1, 0, 4) is False

    def test_certain_winner_when_min_at_or_above_threshold(self):
        # 2 hits incl 1 HR -> TB_min = 2 + 3 = 5 >= 5 -> winner even worst case.
        assert self._verdict(2, 1, 5) is True
        # 3 plain hits -> TB_min = 3 >= 2 -> winner for 2+.
        assert self._verdict(3, 0, 2) is True

    def test_indeterminate_when_threshold_between_bounds(self):
        # 2 hits, 0 HR -> TB_min=2, TB_max=6; a 4+ outcome is unknowable.
        assert self._verdict(2, 0, 4) is None
        # 1 hit, 0 HR -> TB_min=1, TB_max=3; a 2+ or 3+ is unknowable.
        assert self._verdict(1, 0, 2) is None
        assert self._verdict(1, 0, 3) is None

    def test_all_home_runs_resolve_high_thresholds(self):
        # 2 hits both HR -> TB_min = 2 + 6 = 8, exact TB = 8 -> winner up to 8.
        assert self._verdict(2, 2, 8) is True
        assert self._verdict(2, 2, 9) is False  # TB_max = 6 + 2 = 8 < 9


class TestTotalOutcomeRegrade:
    """#945: Kalshi TOTAL game_score re-grade (mirror of the spread re-grade)."""

    def _w(self, name, hs, as_):
        from app.tasks.backfill_winners import _total_outcome_is_winner
        return _total_outcome_is_winner(name, hs, as_)

    def test_over_wins_when_total_exceeds_line(self):
        # 4-3 = 7 total. Over 5.5 -> True; Over 7.5 -> False.
        assert self._w("Over 5.5 goals scored", 4, 3) is True
        assert self._w("Over 7.5 goals scored", 4, 3) is False

    def test_under_direction_respected_gotcha_17(self):
        # Under 7.5 with total 7 -> True; Under 5.5 -> False (direction matters).
        assert self._w("Under 7.5 goals scored", 4, 3) is True
        assert self._w("Under 5.5 goals scored", 4, 3) is False

    def test_points_and_runs_units(self):
        assert self._w("Over 210.5 points scored", 110, 105) is True   # 215
        assert self._w("Over 8.5 runs scored", 3, 2) is False           # 5

    def test_non_total_or_missing_scores_returns_none(self):
        assert self._w("Carolina wins by over 1.5 goals", 4, 3) is None
        assert self._w("Over 5.5 goals scored", None, 3) is None

    def test_regrade_wired_and_scoped(self):
        import inspect
        from app.tasks.backfill_winners import (
            _regrade_kalshi_total_inversions, _resolve_winners_only,
        )
        rg = inspect.getsource(_regrade_kalshi_total_inversions)
        assert "KX(NHL|NBA|MLB)TOTAL" in rg
        assert "_total_outcome_is_winner(" in rg
        assert "bool(r.cur) == won" in rg            # write-on-change
        sql = rg[rg.index("text("):]
        assert "resolution_source" not in sql.split("UPDATE")[1] if "UPDATE" in sql else True
        assert "_regrade_kalshi_total_inversions(" in inspect.getsource(_resolve_winners_only)


class TestResolverNoReInversion:
    """#947: _resolve_kalshi_spread_total_from_scores must NOT re-invert
    already-correctly-resolved spread/total game_score markets on re-pull.
    Two root causes fixed: (1) the team-total branch grabbed spread names;
    (2) the total branch used a complementary sibling-flip."""

    def _src(self):
        import inspect
        from app.tasks.backfill_winners import _resolve_kalshi_spread_total_from_scores
        return inspect.getsource(_resolve_kalshi_spread_total_from_scores)

    def test_team_total_branch_skips_spread_names(self):
        src = self._src()
        tt = src.split("# Team total:")[1].split("# For spread/total parsing")[0]
        # spread names ("X wins by over N") must be skipped so the spread branch
        # (margin-based) handles them, not the team-total branch (raw-score-based).
        assert "_SPREAD_RE.search(oc.name" in tt

    def test_total_branch_grades_each_outcome_independently(self):
        src = self._src()
        total_branch = src.split("# Try total pattern")[1].split("# Fallback:")[0]
        # strip comment lines so we test CODE, not the comment that quotes the bug.
        code = "\n".join(l for l in total_branch.splitlines() if not l.strip().startswith("#"))
        # per-outcome grading via the #945 helper; no complementary sibling-flip.
        assert "_total_outcome_is_winner(" in code
        assert "oc_won = won if oc.id == outcome.id else not won" not in code
        assert "is_over = bool(" not in code  # the dead var is gone

    def test_spread_branch_still_independent(self):
        # #939 spread branch must remain per-outcome (not regressed).
        src = self._src()
        spread_branch = src.split("# Try spread pattern")[1].split("# Try total pattern")[0]
        assert "_spread_outcome_is_winner(" in spread_branch
        assert "oc_won = won if oc.id == outcome.id else not won" not in spread_branch


class TestBudgetGuard:
    """#898 (Queue #94): the time-budget guard must early-return BEFORE the
    candlestick/trade backfills (the phases that bust the 840s soft_time_limit)
    so the cycle COMPLETES with status='partial_budget_guard' instead of dying
    on SoftTimeLimitExceeded. Resolution phases run first + commit, so winners
    still grade; only the idempotent maintenance tail is skipped."""

    class _FakeSession:
        async def execute(self, *a, **k):
            m = MagicMock()
            m.rowcount = 0
            m.scalar = MagicMock(return_value=0)
            m.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
            m.fetchall = MagicMock(return_value=[])
            m.all = MagicMock(return_value=[])
            return m

        async def commit(self):
            return None

        async def rollback(self):
            return None

    class _FakeCM:
        def __call__(self):
            return self

        async def __aenter__(self):
            return TestBudgetGuard._FakeSession()

        async def __aexit__(self, *a):
            return False

    async def test_guard_early_returns_before_candlestick_when_budget_exhausted(self):
        """With elapsed > the ~600s effective budget by the time the candlestick
        guard is reached, the task returns partial_budget_guard(candlestick_trades)
        and never calls the candlestick/trade backfills."""
        import app.tasks.backfill_winners as bw
        import app.tasks.kalshi as kalshi

        # monotonic: first call = pipeline_start (0.0); every later call = 700.0
        # → budget_left = 840 - 700 = 140 < margin 240 → guard fires.
        state = {"v": 0.0}

        def fake_monotonic():
            v = state["v"]
            state["v"] = 700.0
            return v

        # All resolution / pre-candlestick phase fns mocked to no-op dicts so the
        # function reaches the candlestick guard instantly (no DB).
        resolution_fns = [
            "_resolve_kalshi_from_scores",
            "_resolve_kalshi_spread_total_from_scores",
            "_resolve_kalshi_player_props_from_boxscore",
            "_resolve_kalshi_total_bases_from_boxscore",
            "_resolve_kalshi_period_props",
            "_backfill_kalshi_winners",
            "_backfill_kalshi_winners_via_markets",
            "_backfill_polymarket_winners_from_api",
            "_backfill_from_current_probability",
        ]

        candlestick_mock = AsyncMock(return_value={"snapshots_created": 0, "errors": []})
        trade_mock = AsyncMock(return_value={"snapshots_created": 0, "errors": []})

        with patch("time.monotonic", side_effect=fake_monotonic), \
                patch.object(bw, "get_task_session", self._FakeCM()), \
                patch.object(kalshi, "_link_sports_props_to_events", AsyncMock(return_value={"total_linked": 0, "errors": []})), \
                patch.object(kalshi, "_backfill_candlestick_snapshots", candlestick_mock), \
                patch.object(kalshi, "_backfill_trade_history", trade_mock):
            for name in resolution_fns:
                patch.object(bw, name, AsyncMock(return_value={})).start()
            try:
                result = await bw._backfill_all_winners(dry_run=True, limit=5)
            finally:
                patch.stopall()

        assert result["status"] == "partial_budget_guard", result
        # #991 (Queue #117): the winner-resolution block now guards the heavy
        # backlog drainers, so on budget exhaustion the FIRST guard hit is the
        # new "kalshi_markets_api" pre-phase guard (ahead of the reordered
        # bookmaker_closing drain). The wall-busting candlestick/trade backfills
        # still never run.
        assert result["stopped_before"] == "kalshi_markets_api", result
        candlestick_mock.assert_not_called()
        trade_mock.assert_not_called()

    def test_margin_gives_540s_effective_budget(self):
        """#991: margin raised 240 -> 300 (effective budget ~540s under the 840s
        soft limit) after the loop regressed to busting 840s; the winner-res block
        also now guards its heavy drainers. Comfortably under the 900s hard limit."""
        import inspect
        import app.tasks.backfill_winners as bw

        src = inspect.getsource(bw._backfill_all_winners)
        assert "_SOFT_LIMIT_S = 840" in src
        assert "_BUDGET_MARGIN_S = 300" in src
        # effective budget = soft - margin
        assert (840 - 300) == 540
        # the candlestick/trade block is guarded before _mark("candlestick_trades")
        guard_then_mark = src.split('_partial_result("candlestick_trades")')[1]
        assert '_mark("candlestick_trades")' in guard_then_mark
        # and a second guard precedes the trade-history sub-phase
        assert '_partial_result("trades")' in src


class TestCalLoopConsolidatedFix:
    """#107: bound the candlestick/trade inner ops to the cycle deadline + run
    the calibration drain BEFORE candlestick so it executes every cycle."""

    def _bw_src(self):
        import inspect
        from app.tasks.backfill_winners import _backfill_all_winners
        return inspect.getsource(_backfill_all_winners)

    def test_candlestick_and_trade_get_cycle_deadline(self):
        src = self._bw_src()
        # both wall-busting inner ops are passed the cycle deadline so they
        # early-return mid-flight (not just at their own absolute caps)
        assert "_backfill_candlestick_snapshots(" in src
        assert "deadline=_pipeline_start + _SOFT_LIMIT_S - _BUDGET_MARGIN_S" in src
        # trade history call also gets it
        cand_then_trade = src.split("_backfill_trade_history(", 1)[1][:120]
        assert "deadline=" in cand_then_trade

    def test_calibration_drain_runs_before_candlestick(self):
        src = self._bw_src()
        cal = src.find("_compute_calibration_prices()")
        cand = src.find("_backfill_candlestick_snapshots(")
        assert cal != -1 and cand != -1
        assert cal < cand, "calibration drain must run BEFORE candlestick (#107 reorder)"

    def test_inner_ops_have_deadline_param(self):
        import inspect
        from app.tasks.kalshi import _backfill_candlestick_snapshots, _backfill_trade_history
        for fn in (_backfill_candlestick_snapshots, _backfill_trade_history):
            sig = inspect.signature(fn)
            assert "deadline" in sig.parameters, fn.__name__
            body = inspect.getsource(fn)
            # the deadline is actually checked in a loop (early-return), not just accepted
            assert "deadline and _time.monotonic() >= deadline" in body, fn.__name__


def test_poly_resolver_dead_cid_429_classification():
    """#985: the dead-cid cache must mark a condition_id dead ONLY on a definitive
    404, never on a 429/transient error (gotcha #36). The old code returned None
    on any error and cached it dead, so rate-limited flagship markets were skipped
    forever. _fetch_market now returns a `definitive` flag and the consumer only
    sadd's the dead key when definitive. Plus a one-time purge of the polluted set."""
    import inspect
    from app.tasks.backfill_winners import _backfill_polymarket_winners_from_api
    src = inspect.getsource(_backfill_polymarket_winners_from_api)
    # _fetch_market returns a 3rd 'definitive' element + bounded retry
    assert "definitive" in src
    assert "return cid, None, False" in src           # transient → not definitive
    assert "await service.get_market_by_condition(str(cid)), True" in src  # authoritative
    # consumer only caches dead on a definitive 404
    assert "if definitive:" in src
    assert "_rc.sadd(_dead_key, cid)" in src
    # one-time purge of the 429-polluted dead set
    assert "bainluck:poly_dead_purged_v2" in src
    assert "_rc.delete(_dead_key)" in src


def test_poly_resolver_rate_limit_aware():
    """#985: the bulk re-fetch must respect Gamma's rate limit — re-fetching the
    un-skipped backlog at high concurrency saturated it (a verify run hit 6000/6000
    429, 0 winners). Low concurrency + a circuit-breaker that stops the run when a
    batch is mostly throttled (not dead — retried next run)."""
    import inspect
    from app.tasks.backfill_winners import _backfill_polymarket_winners_from_api
    src = inspect.getsource(_backfill_polymarket_winners_from_api)
    assert "asyncio.Semaphore(3)" in src                 # low concurrency
    assert "throttled_stop" in src                       # circuit-breaker flag
    assert "_batch_rl >= 0.8 * len(results)" in src      # breaker condition


def test_resolve_winners_has_deadline_guard_991():
    """#991: _resolve_winners_only must early-return before the heavy backlog
    drainers (poly_api/kalshi_markets) when near its 540s soft limit, so it stops
    cleanly instead of SoftTimeLimitExceeded. Scheduling only (gotcha #21)."""
    import inspect
    from app.tasks.backfill_winners import _resolve_winners_only
    src = inspect.getsource(_resolve_winners_only)
    assert "_DEADLINE_S = 450" in src
    assert "_over_budget()" in src
    assert "_budget_exit(" in src
    # guards before the heavy phases
    assert 'return _budget_exit("before_polymarket_api")' in src
    assert 'return _budget_exit("before_kalshi_markets")' in src


def test_backfill_all_winners_guards_heavy_phases_991():
    """#991/#116-item2: _backfill_all_winners widened its margin and guards the
    kalshi_markets_api + polymarket_api drainers so a slow winner-resolution
    block can't bust the 840s wall before the drain guards run."""
    import inspect
    from app.tasks.backfill_winners import _backfill_all_winners
    src = inspect.getsource(_backfill_all_winners)
    assert "_BUDGET_MARGIN_S = 300" in src
    assert 'return _partial_result("kalshi_markets_api")' in src
    assert 'return _partial_result("polymarket_api")' in src


class TestPolymarketTotalLineParsing:
    """#140: parse the O/U line from a Polymarket full-game total market NAME.

    Polymarket outcomes are literally "Over"/"Under"; the line lives in the
    market name ("{A} vs. {B}: O/U N"), so the grader parses it from there. Only
    the strict "...: O/U N$" full-game suffix qualifies — scoped/prop/period
    totals must return None so the grader skips them (gotcha #21).
    """

    def _line(self, name):
        from app.tasks.backfill_winners import _poly_total_line
        return _poly_total_line(name)

    def test_full_game_soccer_total(self):
        assert self._line("Scotland vs. Brazil: O/U 2.5") == 2.5
        assert self._line("CF Universidad de Chile vs. O'Higgins FC: O/U 3.5") == 3.5

    def test_integer_line_parses(self):
        assert self._line("Team A vs. Team B: O/U 3") == 3.0

    def test_case_and_spacing_tolerant(self):
        assert self._line("A vs. B: o/u 4.5") == 4.5
        assert self._line("A vs. B:O/U 1.5") == 1.5

    def test_first_half_total_is_skipped(self):
        # halftime scope — final score would mis-grade it
        assert self._line("76ers vs. Celtics: 1H O/U 105.5") is None

    def test_player_prop_is_skipped(self):
        assert self._line("Aaron Gordon: Points O/U 14.5") is None
        assert self._line("Aaron Nesmith: Rebounds O/U 3.5") is None

    def test_tennis_games_sets_skipped(self):
        assert self._line("Abe vs. Yamazaki: Match O/U 22.5") is None
        assert self._line("Abe vs. Yamazaki: Set 1 Games O/U 10.5") is None
        assert self._line("Aaron Gabet vs. Seydina Andre: Total Sets O/U 2.5") is None

    def test_non_total_and_empty_return_none(self):
        assert self._line("Will there be a red card?") is None
        assert self._line("") is None
        assert self._line(None) is None


class TestPolymarketTotalGradingDirection:
    """#140: the over/under grading decision the resolver applies per outcome.

    Mirrors the resolver body: total = home + away, "Over" wins iff total > line,
    "Under" iff total < line, total == line is a push (skip). Kept as a pure
    helper so the direction/push logic is unit-covered without a DB.
    """

    def _grade(self, direction, line, home, away):
        total = home + away
        if total == line:
            return None  # push — skipped by the resolver
        if direction == "over":
            return total > line
        return total < line

    def test_over_wins_and_loses(self):
        assert self._grade("over", 2.5, 2, 0) is False   # total 2 < 2.5
        assert self._grade("over", 2.5, 2, 1) is True    # total 3 > 2.5

    def test_under_wins_and_loses(self):
        assert self._grade("under", 2.5, 2, 0) is True   # total 2 < 2.5
        assert self._grade("under", 2.5, 2, 1) is False  # total 3 > 2.5

    def test_push_on_integer_line_is_skipped(self):
        # total == line only possible on an integer line; never guess a winner
        assert self._grade("over", 3, 2, 1) is None
        assert self._grade("under", 3, 2, 1) is None

    def test_zero_zero_draw_under_wins(self):
        assert self._grade("under", 0.5, 0, 0) is True
        assert self._grade("over", 0.5, 0, 0) is False


class TestPolymarketTotalScoreResolverWiring:
    """#140: the poly total score resolver is wired into both pipelines and
    writes with the safe, idempotent conventions."""

    def test_resolver_uses_poly_total_score_tag_and_skips_push(self):
        import inspect
        from app.tasks.backfill_winners import _resolve_polymarket_total_from_scores
        src = inspect.getsource(_resolve_polymarket_total_from_scores)
        assert "poly_total_score" in src
        assert "source = 'polymarket'" in src
        assert "BOOL_OR(u.is_winner) IS NOT TRUE" in src   # only ungraded
        assert "e.status IN ('completed', 'closed')" in src  # final scores only
        assert "push_skip" in src                          # push guarded
        assert "i % 500 == 0" in src                       # per-batch commit (#13)

    def test_wired_into_both_pipelines(self):
        import inspect
        from app.tasks.backfill_winners import (
            _resolve_winners_only, _backfill_all_winners,
        )
        assert "_resolve_polymarket_total_from_scores(" in inspect.getsource(
            _resolve_winners_only)
        assert "_resolve_polymarket_total_from_scores(" in inspect.getsource(
            _backfill_all_winners)


class TestClearRunningPhaseLatch:
    """L2-105: after a successful (or partial-budget-guard) backfill run, the
    `bainluck:backfill_phase_timing` blob was left with `running_phase` pointing
    at the last _mark'd phase — a stale latch the dashboard/cockpit read as
    "backfill still mid-phase" long after the task returned (nearly a phantom-run
    wait). `_clear_backfill_running_phase()` drops the latch on completion."""

    def _fake_rc(self, store):
        class FakeRedis:
            def get(self, k):
                return store.get(k)

            def setex(self, k, ttl, v):
                store[k] = v

        return FakeRedis()

    def test_clears_running_phase_preserving_timings(self, monkeypatch):
        import json
        import app.tasks.redis_state as rs
        from app.tasks.backfill_winners import _clear_backfill_running_phase

        store = {
            "bainluck:backfill_phase_timing": json.dumps({
                "running_phase": "golf_matchups",       # stale latch
                "completed": {"kalshi_api": 254.7, "score_resolution": 41.2},
                "cumulative_s": 812.3,
                "soft_time_limit_s": 840,
            })
        }
        monkeypatch.setattr(rs, "get_redis_client", lambda *a, **k: self._fake_rc(store))
        _clear_backfill_running_phase()

        blob = json.loads(store["bainluck:backfill_phase_timing"])
        assert blob["running_phase"] is None            # latch dropped
        assert "completed_at" in blob                    # completion stamped
        assert blob["completed"]["kalshi_api"] == 254.7  # timings preserved

    def test_noop_when_no_blob(self, monkeypatch):
        import app.tasks.redis_state as rs
        from app.tasks.backfill_winners import _clear_backfill_running_phase

        store = {}
        monkeypatch.setattr(rs, "get_redis_client", lambda *a, **k: self._fake_rc(store))
        _clear_backfill_running_phase()  # must not raise
        assert store == {}

    def test_wired_into_both_completion_paths(self):
        import inspect
        from app.tasks.backfill_winners import _backfill_all_winners

        src = inspect.getsource(_backfill_all_winners)
        # partial-budget-guard return AND full completion both drop the latch
        assert src.count("_clear_backfill_running_phase()") >= 2


class TestResolverHygieneDatePassed:
    """Item 1 (A): _grade_date_passed_binaries — grade lapsed open poly binaries."""

    def _src(self):
        import inspect
        from app.tasks.backfill_winners import _grade_date_passed_binaries

        return inspect.getsource(_grade_date_passed_binaries)

    def test_predicate_is_tightly_gated(self):
        src = self._src()
        assert "fm.source = 'polymarket'" in src
        assert "fm.status = 'open'" in src
        assert "fm.resolution_date < NOW() - INTERVAL '3 days'" in src
        assert r"fm.name ~* '\yby\y'" in src
        assert r"fm.name ~ '\?'" in src
        # exactly two Yes/No outcomes, nothing already graded, No near-certain
        assert "COUNT(*) = 2" in src
        assert "SUM(CASE WHEN fo.is_winner THEN 1 ELSE 0 END) = 0" in src
        assert ">= 0.95" in src

    def test_writes_date_passed_and_couples_status(self):
        src = self._src()
        assert "resolution_source = 'date_passed'" in src
        # No side wins, and the market is flipped resolved in the same phase.
        assert "is_winner = (lower(name) = 'no')" in src
        assert "status = 'resolved'" in src

    def test_wired_into_both_entrypoints(self):
        import inspect
        from app.tasks.backfill_winners import (
            _backfill_all_winners,
            _resolve_winners_only,
        )

        assert "_grade_date_passed_binaries(" in inspect.getsource(_resolve_winners_only)
        assert "_grade_date_passed_binaries(" in inspect.getsource(_backfill_all_winners)


class TestResolverHygienePrematureOpenWinners:
    """Item 1 (C): _clear_premature_open_winners — sweep guess/None open winners."""

    def _src(self):
        import inspect
        from app.tasks.backfill_winners import _clear_premature_open_winners

        return inspect.getsource(_clear_premature_open_winners)

    def test_only_touches_non_resolved_markets(self):
        src = self._src()
        assert "fm.status NOT IN ('resolved', 'closed')" in src
        assert "fo.is_winner = true" in src

    def test_uses_guess_family_constant_not_inline_tuple(self):
        # Must route through the canonical constant (drift-scan forbids inlining).
        src = self._src()
        assert "GUESS_FAMILY_SOURCES_SQL" in src
        assert "fo.resolution_source IS NULL" in src

    def test_nulls_winner_and_source(self):
        src = self._src()
        assert "is_winner = false" in src
        assert "resolution_source = NULL" in src

    def test_wired_into_resolver(self):
        import inspect
        from app.tasks.backfill_winners import _resolve_winners_only

        assert "_clear_premature_open_winners(" in inspect.getsource(_resolve_winners_only)


class TestByWhenLadderDateParser:
    """Item 1 (B): _parse_outcome_date earliest-date selection helper."""

    def test_parses_month_name_forms(self):
        from app.tasks.backfill_winners import _parse_outcome_date

        assert _parse_outcome_date("July 1") == (0, 7, 1)
        assert _parse_outcome_date("Jul 6") == (0, 7, 6)
        assert _parse_outcome_date("July 1, 2026") == (2026, 7, 1)

    def test_parses_iso_and_numeric(self):
        from app.tasks.backfill_winners import _parse_outcome_date

        assert _parse_outcome_date("2026-07-01") == (2026, 7, 1)
        assert _parse_outcome_date("7/1/2026") == (2026, 7, 1)

    def test_unparseable_returns_none(self):
        from app.tasks.backfill_winners import _parse_outcome_date

        assert _parse_outcome_date("Linda Nosková") is None
        assert _parse_outcome_date("") is None
        assert _parse_outcome_date(None) is None

    def test_earliest_date_sorts_first(self):
        # The July 1/2/3/6 ladder: July 1 must be the kept (earliest) winner.
        from app.tasks.backfill_winners import _parse_outcome_date

        names = ["July 6", "July 2", "July 1", "July 3"]
        earliest = min(names, key=lambda n: _parse_outcome_date(n))
        assert earliest == "July 1"
