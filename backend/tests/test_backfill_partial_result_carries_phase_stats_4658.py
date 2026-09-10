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

import ast
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

def _table_keys():
    """The return keys `_PHASE_STATS` names, read from the function's source."""
    src = inspect.getsource(bw._backfill_all_winners)
    table = src.split("_PHASE_STATS = (", 1)[1].split("\n    )", 1)[0]
    return re.findall(r'\("([a-z0-9_]+)", lambda:', table)


def _table_locals():
    """The LOCALS `_PHASE_STATS` reads, read from the function's source."""
    src = inspect.getsource(bw._backfill_all_winners)
    table = src.split("_PHASE_STATS = (", 1)[1].split("\n    )", 1)[0]
    return set(re.findall(r'\("[a-z0-9_]+", lambda: ([a-z0-9_]+)\)', table))


def _produced_stats_locals():
    """Every `*_stats` local the pipeline assigns, from the real AST.

    The completeness question is "did every phase that ran get reported", and
    only the function itself knows which locals those are. A hand-maintained
    list here would be a third copy of the same list that already drifted twice.
    """
    tree = ast.parse(inspect.getsource(bw).lstrip())
    fn = next(
        n for n in ast.walk(tree)
        if isinstance(n, (ast.AsyncFunctionDef, ast.FunctionDef))
        and n.name == "_backfill_all_winners"
    )
    found = set()
    for node in ast.walk(fn):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id.endswith("_stats"):
                    found.add(target.id)
    return found


#: Deliberate exclusions, each of which must carry a reason. Empty today: every
#: `*_stats` local the pipeline produces is reported. Kept as a named seam so a
#: future genuine exclusion is an explicit decision rather than a silent gap.
DELIBERATELY_UNREPORTED: set[str] = set()

_UNCOVERED_STATS_LOCALS = (
    _produced_stats_locals() - _table_locals() - DELIBERATELY_UNREPORTED
)


#: What the mocked `_backfill_kalshi_winners` hands back. Distinctive on
#: purpose: a bare `{}` would pass a "the key is present" assertion while
#: proving nothing about the VALUE travelling, and the value is the ship.
KALSHI_API_STATS = {
    "resolved": 7,
    "no_result": 3,            # #4604's counter, the reason this issue exists
    "ungradeable_result": 2,   # ditto
}


#: What the mocked total-bases resolver hands back. `total_bases_stats`
#: completes inside `score_resolution`, BEFORE the first guard, and was the
#: sharpest case CERT-2465 found: the exit production takes most often dropped a
#: phase that had already finished.
TOTAL_BASES_STATS = {"resolved": 4, "errors": []}

#: `dg_early_stats`, produced just after the `prob_and_datagolf` guard, so it is
#: carried by every LATER exit and by none before it.
DATAGOLF_EARLY_STATS = {"leaderboard_resolved": 5, "errors": []}


class _FakeSession:
    async def execute(self, *a, **k):
        raise AssertionError("no phase in this test should reach the database")

    async def commit(self):
        return None

    async def rollback(self):
        return None


class _PermissiveResult:
    rowcount = 0

    def fetchall(self):
        return []

    def all(self):
        return []

    def first(self):
        return None

    def scalar(self):
        return 0

    def scalars(self):
        return self

    def scalar_one_or_none(self):
        return None


class _PermissiveSession:
    """Answers every maintenance query with nothing.

    Used only by the later-guard drive, where the point is to get PAST several
    DB phases so their stats locals bind — not to exercise them. A raising
    session would also bind them (they catch and record), but through their
    error branch, which would make "the phase completed" mean something weaker
    than it should.
    """

    async def execute(self, *a, **k):
        return _PermissiveResult()

    async def commit(self):
        return None

    async def rollback(self):
        return None


class _FakeCM:
    def __init__(self, session_cls=_FakeSession):
        self._session_cls = session_cls

    def __call__(self, *a, **k):
        return self

    async def __aenter__(self):
        return self._session_cls()

    async def __aexit__(self, *a):
        return False


#: Both drives are deterministic and every test only READS the returned dict, so
#: they are run once each and shared. Without this the parametrised cases
#: re-drive the whole pipeline ~35 times and the file costs 3+ minutes of CI on
#: every push.
_DRIVE_CACHE: dict = {}


async def _run_to_the_first_guard():
    if "first" not in _DRIVE_CACHE:
        _DRIVE_CACHE["first"] = await _drive_to_the_first_guard()
    return dict(_DRIVE_CACHE["first"])


async def _drive_to_the_first_guard():
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
        patch.object(
            bw, "_resolve_kalshi_total_bases_from_boxscore",
            AsyncMock(return_value=dict(TOTAL_BASES_STATS)),
        ).start()
        try:
            return await bw._backfill_all_winners(dry_run=True, limit=5)
        finally:
            patch.stopall()


async def _run_until_the_clock_dies_during(phase_attr, payload):
    key = ("later", phase_attr)
    if key not in _DRIVE_CACHE:
        _DRIVE_CACHE[key] = await _drive_until_the_clock_dies_during(
            phase_attr, payload
        )
    return dict(_DRIVE_CACHE[key])


async def _drive_until_the_clock_dies_during(phase_attr, payload):
    """Drive PAST the first guard and let the budget expire inside a named phase.

    The clock does not advance on its own here: `monotonic` reports a virtual
    now that only the chosen phase's own mock moves. So the exit point is stated
    as "the budget ran out during X" rather than tuned by counting calls, which
    is what makes this readable and what keeps it from drifting when a phase is
    added upstream (gotcha #44 — an anchor with an `if` on the clock is not
    fixed).
    """
    import app.tasks.kalshi as kalshi

    state = {"v": 0.0}

    async def _die(*a, **k):
        state["v"] = 700.0          # 840 - 700 = 140 < the 300 margin
        return dict(payload)

    everything_else = [
        "_resolve_kalshi_from_scores",
        "_resolve_kalshi_spread_total_from_scores",
        "_resolve_kalshi_player_props_from_boxscore",
        "_resolve_kalshi_period_props",
        "_backfill_kalshi_winners_via_markets",
        "_backfill_polymarket_winners_from_api",
        "_backfill_from_current_probability",
    ]

    with patch("time.monotonic", side_effect=lambda: state["v"]), \
            patch.object(bw, "get_task_session", _FakeCM(_PermissiveSession)), \
            patch.object(kalshi, "_link_sports_props_to_events",
                         AsyncMock(return_value={"total_linked": 0, "errors": []})), \
            patch.object(kalshi, "_backfill_candlestick_snapshots",
                         AsyncMock(return_value={"snapshots_created": 0, "errors": []})), \
            patch.object(kalshi, "_backfill_trade_history",
                         AsyncMock(return_value={"snapshots_created": 0, "errors": []})):
        for name in everything_else:
            patch.object(bw, name, AsyncMock(return_value={})).start()
        patch.object(bw, "_backfill_kalshi_winners",
                     AsyncMock(return_value=dict(KALSHI_API_STATS))).start()
        patch.object(bw, "_resolve_kalshi_total_bases_from_boxscore",
                     AsyncMock(return_value=dict(TOTAL_BASES_STATS))).start()
        patch.object(bw, phase_attr, _die).start()
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

    async def test_total_bases_completed_before_the_first_guard_and_must_be_carried(self):
        """CERT-2465's exact finding, at the FIRST guard.

        `total_bases_stats` finishes inside `score_resolution`, upstream of every
        guard, so the exit production takes most often was dropping a phase that
        had already done its work. It was invisible because the full return never
        named it either — the pipeline computed it and no return in the file
        carried it.
        """
        result = await _run_to_the_first_guard()
        assert result["stopped_before"] == "kalshi_markets_api", result
        assert "kalshi_total_bases" in result, sorted(result)
        assert result["kalshi_total_bases"] == TOTAL_BASES_STATS

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


@pytest.mark.asyncio
class TestALaterGuardCarriesEverythingUpToIt:
    """The second half of CERT-2465's required repair.

    `bookmaker_closing` is not an arbitrary choice of "a later guard" — it is the
    exit the 2026-09-10 03:45Z production run actually took, so this drive
    reproduces the shape of the real cycle rather than a synthetic one.
    """

    async def test_it_stops_where_production_stops(self):
        result = await _run_until_the_clock_dies_during(
            "_backfill_datagolf_winners", DATAGOLF_EARLY_STATS,
        )
        assert result["status"] == "partial_budget_guard", result
        assert result["stopped_before"] == "bookmaker_closing", result

    @pytest.mark.parametrize("phase_key", [
        "kalshi_total_bases",     # before the first guard
        "kalshi_api",             # before the first guard
        "kalshi_markets_api",     # between guards
        "polymarket_api",         # between guards
        "from_probability",       # inside prob_and_datagolf
        "datagolf_early",         # the phase the clock died in
        "guess_upgrade",
        "link_sports_props",
    ])
    async def test_every_phase_upstream_of_the_exit_is_carried(self, phase_key):
        result = await _run_until_the_clock_dies_during(
            "_backfill_datagolf_winners", DATAGOLF_EARLY_STATS,
        )
        assert phase_key in result, sorted(result)

    async def test_the_phase_the_clock_died_in_carries_its_value(self):
        result = await _run_until_the_clock_dies_during(
            "_backfill_datagolf_winners", DATAGOLF_EARLY_STATS,
        )
        assert result["datagolf_early"] == DATAGOLF_EARLY_STATS

    @pytest.mark.parametrize("phase_key", [
        "bookmaker_calibration",   # the phase the guard is named for
        "calibration_prices",
        "candlestick_snapshots",
        "trade_history",
        "date_passed_binaries",
        "bywhen_ladder_collapse",
        "datagolf_makecut_fix",
        "golf_settlement_sync",
    ])
    async def test_everything_downstream_of_the_exit_is_still_absent(self, phase_key):
        """The other half. A later exit carrying MORE must not carry everything."""
        result = await _run_until_the_clock_dies_during(
            "_backfill_datagolf_winners", DATAGOLF_EARLY_STATS,
        )
        assert phase_key not in result, (
            f"{phase_key} runs after the exit but is being reported"
        )

    async def test_a_later_exit_carries_strictly_more_than_the_first(self):
        """The property that makes 'every completed phase' meaningful."""
        first = await _run_to_the_first_guard()
        later = await _run_until_the_clock_dies_during(
            "_backfill_datagolf_winners", DATAGOLF_EARLY_STATS,
        )
        table = set(_table_keys())
        first_phases = table & set(first)
        later_phases = table & set(later)
        assert first_phases < later_phases, {
            "first": sorted(first_phases), "later": sorted(later_phases),
        }


class TestTheTwoReturnPathsCannotDriftAgain:
    """The defect was two hand-maintained lists, one of which was empty."""

    def test_both_returns_read_the_same_table(self):
        src = inspect.getsource(bw._backfill_all_winners)
        assert src.count("**_phase_stats()") == 2, (
            "the partial return and the full return must BOTH spread the shared "
            "table; a hand-written key list is how #4658 happened"
        )

    def test_the_table_still_names_every_phase_the_full_return_carried(self):
        """The 33 the full return named by hand must not be lost."""
        named = set(_table_keys())
        missing = HISTORICAL_FULL_RETURN_KEYS - named
        assert not missing, sorted(missing)

    def test_the_table_names_EVERY_completed_phase_stat_not_just_the_returned_ones(self):
        """CERT-2465's required repair, and the guard that would have caught it.

        The first version of this table was "the keys the full return happened to
        name". That is a different set from #4658's actual acceptance — every
        phase stats dict that COMPLETED — and the difference was seven producers,
        one of them (`total_bases_stats`) finishing before the very first guard.

        Derived from the function's own source rather than pinned, so a phase
        added later cannot quietly go unreported: the new local reds this test
        the day it lands.
        """
        assert not _UNCOVERED_STATS_LOCALS, {
            "phase stats locals produced but never reported":
                sorted(_UNCOVERED_STATS_LOCALS),
            "fix": "add each to _PHASE_STATS in backfill_winners.py",
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
