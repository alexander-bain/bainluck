"""#4658 — the budget-guard exit must carry the counters of the phases that ran.

`backfill_winners` has two return paths. The full return at the bottom named 33
phase stats dicts by hand; `_partial_result` named none of them. That would be a
cosmetic asymmetry if the full return were the normal path, and it is not: the
effective budget is `_SOFT_LIMIT_S - _BUDGET_MARGIN_S` = 540s and the measured
core phases alone are 757.5s (2026-09-10 03:45Z), so **every** production cycle
returns `partial_budget_guard`. `kalshi_api` runs before that exit, so its
counters were incremented every run and discarded every run — which is why
#4604's `no_result` / `ungradeable_result` were unobservable on
`task-metrics?task=backfill_winners`.

The discriminating assertion is not "stats are present". It is that a phase that
ran is present AND a phase that did not run is ABSENT — an empty dict for a
phase that never executed is the same lie the old return told by omission
(gotcha #53: an absence must not wear a value).

The pipeline is driven for real, with the same faked-monotonic harness
`TestBudgetGuard` uses: phase functions are mocked, but the guard, the closure
scoping and both return paths are the shipped ones.
"""

import inspect
import re
from unittest.mock import AsyncMock, patch

import pytest

import app.tasks.backfill_winners as bw


# The 33 keys the full return carried before #4658. Pinned so that dropping a
# phase from the shared table reds here rather than going quiet on a dashboard.
HISTORICAL_FULL_RETURN_KEYS = {
    "link_sports_props", "ml_misresolution_repair", "guess_upgrade",
    "retro_tagging", "retro_guess_tagging", "commence_time_fixes",
    "polymarket_group_id", "kalshi_group_id", "null_untradeable",
    "opening_repair", "closing_lines", "calibration_prices",
    "poly_under_signflip", "datagolf_premature_unresolve",
    "impossible_both_ones", "both_winner_guess_flip", "polymarket_api_group_id",
    "datagolf_settlement", "datagolf_leaderboard_backfill", "datagolf",
    "golf_cross_reference", "golf_matchup_resolution", "golf_settlement_sync",
    "kalshi_score_resolution", "kalshi_spread_total_resolution",
    "polymarket_total_score_resolution", "kalshi_player_props",
    "kalshi_period_props", "from_probability", "kalshi_api",
    "kalshi_markets_api", "polymarket_api", "bookmaker_calibration",
}

#: What the mocked `_backfill_kalshi_winners` hands back. Distinctive on
#: purpose: a bare `{}` would pass a "the key is present" assertion while
#: proving nothing about the VALUE travelling, and the value is the ship.
KALSHI_API_STATS = {
    "resolved": 7,
    "no_result": 3,            # #4604's counter, the reason this issue exists
    "ungradeable_result": 2,   # ditto
}


class _FakeSession:
    async def execute(self, *a, **k):
        raise AssertionError("no phase in this test should reach the database")

    async def commit(self):
        return None

    async def rollback(self):
        return None


class _FakeCM:
    def __call__(self):
        return self

    async def __aenter__(self):
        return _FakeSession()

    async def __aexit__(self, *a):
        return False


async def _run_to_the_first_guard():
    """Drive the real pipeline until the budget guard fires.

    First `monotonic()` call is `_pipeline_start` (0.0); every later call
    returns 700.0, so `_budget_left()` is 140 against a 300 margin and the first
    guard reached — `kalshi_markets_api` — returns. That guard sits AFTER
    `kalshi_api` and BEFORE `polymarket_api`, which is exactly the boundary this
    issue is about.
    """
    import app.tasks.kalshi as kalshi

    state = {"v": 0.0}

    def fake_monotonic():
        v = state["v"]
        state["v"] = 700.0
        return v

    # Every phase up to the guard, mocked to a no-op dict so nothing touches a
    # database. `_backfill_kalshi_winners` alone returns a distinctive payload.
    ran_before_the_guard = [
        "_resolve_kalshi_from_scores",
        "_resolve_kalshi_spread_total_from_scores",
        "_resolve_kalshi_player_props_from_boxscore",
        "_resolve_kalshi_total_bases_from_boxscore",
        "_resolve_kalshi_period_props",
        "_backfill_kalshi_winners_via_markets",
        "_backfill_polymarket_winners_from_api",
        "_backfill_from_current_probability",
    ]

    with patch("time.monotonic", side_effect=fake_monotonic), \
            patch.object(bw, "get_task_session", _FakeCM()), \
            patch.object(kalshi, "_link_sports_props_to_events",
                         AsyncMock(return_value={"total_linked": 0, "errors": []})), \
            patch.object(kalshi, "_backfill_candlestick_snapshots",
                         AsyncMock(return_value={"snapshots_created": 0, "errors": []})), \
            patch.object(kalshi, "_backfill_trade_history",
                         AsyncMock(return_value={"snapshots_created": 0, "errors": []})):
        for name in ran_before_the_guard:
            patch.object(bw, name, AsyncMock(return_value={})).start()
        patch.object(
            bw, "_backfill_kalshi_winners",
            AsyncMock(return_value=dict(KALSHI_API_STATS)),
        ).start()
        try:
            return await bw._backfill_all_winners(dry_run=True, limit=5)
        finally:
            patch.stopall()


@pytest.mark.asyncio
class TestTheGuardExitCarriesWhatRan:

    async def test_the_harness_still_stops_where_this_test_believes_it_does(self):
        """The premise, asserted rather than assumed.

        Every assertion below is about which side of the guard a phase sits on,
        so a reordering that moved the first guard would silently turn the real
        assertions into vacuous ones.
        """
        result = await _run_to_the_first_guard()
        assert result["status"] == "partial_budget_guard", result
        assert result["stopped_before"] == "kalshi_markets_api", result

    async def test_kalshi_apis_counters_survive_the_guard_exit(self):
        """The ship. Before #4658 this key did not exist on this path."""
        result = await _run_to_the_first_guard()
        assert "kalshi_api" in result, sorted(result)
        assert result["kalshi_api"] == KALSHI_API_STATS, result["kalshi_api"]

    async def test_4604s_two_counters_are_readable_on_the_path_that_actually_runs(self):
        result = await _run_to_the_first_guard()
        assert result["kalshi_api"]["no_result"] == 3
        assert result["kalshi_api"]["ungradeable_result"] == 2

    async def test_an_earlier_phase_that_ran_is_carried_too(self):
        """`score_resolution` completes before `kalshi_api`; it must not be
        dropped just because it is not the phase the guard was named for."""
        result = await _run_to_the_first_guard()
        assert "kalshi_score_resolution" in result, sorted(result)

    @pytest.mark.parametrize("phase_key", [
        "polymarket_api",          # the phase immediately after the guard
        "from_probability",        # prob_and_datagolf, further down
        "bookmaker_calibration",   # the bookmaker_closing drain
        "calibration_prices",
        "datagolf_settlement",
        "link_sports_props",
    ])
    async def test_a_phase_that_never_ran_is_absent_not_empty(self, phase_key):
        """Absence, not an empty dict.

        `{}` for a phase that never executed reads on a dashboard as "it ran and
        found nothing" — the same class of lie as the counters going missing,
        pointed the other way.
        """
        result = await _run_to_the_first_guard()
        assert phase_key not in result, (
            f"{phase_key} did not run before the guard but is being reported"
        )

    async def test_the_guards_own_fields_are_not_shadowed(self):
        result = await _run_to_the_first_guard()
        for field in ("status", "stopped_before", "pipeline_elapsed_s",
                      "phase_times", "score_resolution_sub_s"):
            assert field in result, field
        # the spread must not have replaced the guard's own status
        assert result["status"] == "partial_budget_guard"


class TestTheTwoReturnPathsCannotDriftAgain:
    """The defect was two hand-maintained lists, one of which was empty."""

    def test_both_returns_read_the_same_table(self):
        src = inspect.getsource(bw._backfill_all_winners)
        assert src.count("**_phase_stats()") == 2, (
            "the partial return and the full return must BOTH spread the shared "
            "table; a hand-written key list is how #4658 happened"
        )

    def test_the_table_still_names_every_phase_the_full_return_carried(self):
        src = inspect.getsource(bw._backfill_all_winners)
        table = src.split("_PHASE_STATS = (", 1)[1].split("\n    )", 1)[0]
        named = set(re.findall(r'\("([a-z0-9_]+)", lambda:', table))
        assert named == HISTORICAL_FULL_RETURN_KEYS, {
            "missing": sorted(HISTORICAL_FULL_RETURN_KEYS - named),
            "unexpected": sorted(named - HISTORICAL_FULL_RETURN_KEYS),
        }

    def test_only_a_missing_name_is_swallowed(self):
        """`except NameError` and nothing wider.

        A bare `except Exception` here would convert a genuine fault inside a
        stats dict into a silently missing key — the exact failure this issue
        is about, reintroduced by the fix for it.
        """
        src = inspect.getsource(bw._backfill_all_winners)
        body = src.split("def _phase_stats():", 1)[1].split("\n    def ", 1)[0]
        assert "except NameError:" in body, body
        assert "except Exception" not in body, body
        assert "except:" not in body, body
