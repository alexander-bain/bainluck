"""LAT-P131 (P128-2): the grid warm covers every buildable league, under a bound.

Nine of the thirteen leagues with a grid config were never warmed. Their pages
worked only for as long as some earlier visitor's own rebuild survived in Redis
— 3900 s fresh, then 24 h in the ``:stale`` mirror — and the first visitor after
that paid the build on a route whose wall is 25 s. Measured on production
2026-08-29: ncaa-football **12.45 s**, wnba **6.83 s**, ncaa-women-basketball
**7.83 s** cold on the ordinary path, and NFL straddling the wall at
25.30 s/**503**, 8.65 s/200, 14.02 s/200 across three consecutive rebuilds.

🔴 **Why these tests assert SHAPE and BOUNDS rather than results.** Widening a
list is a one-line change that cannot fail visibly: every league still returns
the right grid, so a results test passes against every regression here. What can
break is invisible from the payload —

* the pass overrunning the task's ``soft_time_limit`` (a SIGKILL, not a slow run),
* the tail starving behind an early hog (gotcha #34), whose symptom is a league
  that silently stops being warmed,
* an empty build overwriting a good grid in the 24 h ``:stale`` mirror, whose
  symptom is a healthy page becoming a live rebuild — and for NFL a live rebuild
  is the 503,
* and the **second door**: computing the budget, recording it in the report, and
  then handing ``asyncio.wait_for`` the old 120 s ceiling anyway. That version
  looks correct in the report and is bounded by nothing.

Each of those gets a test that fails on it.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import app.tasks.precompute_category_pages as pcp
from app.config.league_configs import get_all_league_slugs


# The one league deliberately left out of the warm list, and the reason it is
# out. Measured 2026-08-29: `/api/playoffs/ncaa-basketball?top=11` returned
# **25.36 s to `unfinished=1`**, of which **17.87 s was `app` and not `db`**, and
# Sentry carried 7 of its "timed out and no last-good payload is available" 503s
# in the preceding 24 h. It is the one league that cannot be built at all, so
# warming it would spend up to the whole per-league ceiling every hour to publish
# nothing. Its 503 is a real user-visible defect with its own ship (P131-1).
KNOWN_UNBUILDABLE = {"ncaa-basketball"}

GOOD_GRID = {"teams": [{"name": "Team A"}], "columns": [{"key": "championship"}]}
EMPTY_GRID = {"teams": [], "columns": []}


class _FakeCM:
    async def __aenter__(self):
        return MagicMock()

    async def __aexit__(self, *a):
        return False


def _run(grid_side_effect, *, budget=None, redis_mock=None):
    """Drive `_precompute_grids` with a stubbed builder and capture the report."""
    redis_mock = redis_mock if redis_mock is not None else MagicMock()
    report: dict = {}
    grid_mock = AsyncMock(side_effect=grid_side_effect)

    stack = [
        patch("app.tasks.redis_state.get_redis_client", return_value=redis_mock),
        patch("app.tasks.base.get_task_session", return_value=_FakeCM()),
        patch("app.routes.playoffs.get_playoff_grid", grid_mock),
    ]
    if budget is not None:
        stack.append(patch.object(pcp, "GRID_WARM_PASS_BUDGET_S", budget))

    for cm in stack:
        cm.start()
    try:
        warmed = asyncio.run(pcp._precompute_grids(report))
    finally:
        for cm in reversed(stack):
            cm.stop()
    return warmed, report, redis_mock, grid_mock


# --------------------------------------------------------------------------
# 1. The ship: every buildable league is actually in the warm list.
# --------------------------------------------------------------------------

def test_every_league_with_a_grid_config_is_warmed():
    """The landmine. Shrink the list back and this FAILS — it does not get slower.

    Asserted against `get_all_league_slugs()` rather than a hard-coded set on
    purpose: a NEW league config that nobody triaged into the warm list fails
    here, which forces the decision to be made rather than defaulted. The only
    permitted absence is a league that provably cannot be built.
    """
    configured = set(get_all_league_slugs())
    warm = set(pcp.GRID_WARM_LEAGUES)

    assert warm <= configured, f"warm list names leagues with no config: {warm - configured}"
    missing = configured - warm - KNOWN_UNBUILDABLE
    assert not missing, (
        "these leagues have a grid config and are not warmed, so their first "
        f"visitor of the day pays the whole build: {sorted(missing)}"
    )


def test_the_four_original_leagues_are_still_warmed():
    """#901 and #1484 must survive the widening — this is a superset change."""
    assert {"mlb", "nba", "nhl", "golf"}.issubset(set(pcp.GRID_WARM_LEAGUES))


def test_the_unbuildable_league_stays_out_until_it_builds():
    """ncaa-basketball is excluded deliberately; re-adding it needs its own ship.

    Not a style preference: it 503s at the route wall and burns the budget of
    every league behind it. If someone fixes the build and adds it back, this
    test is the place that records what had to be true first.
    """
    assert not (KNOWN_UNBUILDABLE & set(pcp.GRID_WARM_LEAGUES))


# --------------------------------------------------------------------------
# 2. The pass is bounded, and the bound fits inside the task that hosts it.
# --------------------------------------------------------------------------

def test_pass_budget_fits_under_the_task_soft_time_limit():
    """The arithmetic that makes the widening safe, pinned so it cannot drift.

    `precompute_category_pages` is declared `soft_time_limit=300, time_limit=360`.
    The five non-grid sections measured **49.5 s** on the production run at
    2026-08-29T17:26:25Z (politics 17.3, entertainment 10.6, economics 11.3,
    weather 8.8, golf 1.5). Raising the grid budget without raising the limit —
    or lowering the limit without lowering the budget — fails here rather than
    in a SIGKILL nobody attributes to this change.
    """
    import app.tasks as tasks_mod

    # Read the real declaration rather than restating it: a test that hard-codes
    # 300 keeps passing after someone lowers the limit.
    task = tasks_mod.celery_app.tasks["app.tasks.precompute_category_pages"]
    soft_limit = task.soft_time_limit
    assert soft_limit, "the task lost its soft_time_limit; the budget is unbounded"

    measured_non_grid_s = 49.5
    worst_case = measured_non_grid_s + pcp.GRID_WARM_PASS_BUDGET_S
    assert worst_case < soft_limit, (
        f"grid pass budget {pcp.GRID_WARM_PASS_BUDGET_S}s + measured non-grid "
        f"{measured_non_grid_s}s = {worst_case}s, which does not fit the task's "
        f"{soft_limit}s soft limit"
    )


def test_unbounded_leagues_cannot_overrun_the_pass_budget():
    """Every league hangs. The pass must still stop at its budget.

    Before LAT-P131 this loop's worst case was `GRID_WARM_TIMEOUT_S x N` with no
    pass bound at all — 1,560 s for thirteen leagues inside a 300 s task.
    """
    budget = 0.30

    async def _hang(*a, **kw):
        await asyncio.sleep(10)

    import time as _time

    started = _time.monotonic()
    warmed, report, _, _ = _run(_hang, budget=budget)
    elapsed = _time.monotonic() - started

    assert warmed == []
    # Generous slack for scheduler jitter; the point is that it is bounded by the
    # BUDGET and not by 13 x 120 s.
    assert elapsed < budget + 2.0, f"pass took {elapsed:.2f}s against a {budget}s budget"
    assert report["grid_pass_budget_s"] == budget
    assert report["grid_budget_left_s"] == 0.0


def test_the_ceiling_still_binds_when_the_budget_is_large():
    """The pass budget may only ever make a deadline SMALLER, never larger.

    With a budget far above the ceiling, the first league must still be offered
    `GRID_WARM_TIMEOUT_S` and not its (much larger) fair share.
    """
    seen = {}

    async def _record(slug, **kw):
        return GOOD_GRID

    with patch.object(pcp, "GRID_WARM_PASS_BUDGET_S", 100000.0):
        real_wait_for = asyncio.wait_for

        async def _spy(aw, timeout):
            seen.setdefault("first", timeout)
            return await real_wait_for(aw, timeout)

        with patch("asyncio.wait_for", _spy):
            _run(_record)

    assert seen["first"] == pytest.approx(float(pcp.GRID_WARM_TIMEOUT_S))


def test_the_budget_actually_reaches_wait_for():
    """🔴 THE SECOND DOOR. Compute the budget, report it, then ignore it.

    A version that derives `deadline_s`, writes it into the report, and still
    passes `GRID_WARM_TIMEOUT_S` to `asyncio.wait_for` is bounded by nothing and
    looks entirely correct from the outside. Assert the value that was actually
    handed to the timeout, not the value that was written down.
    """
    timeouts = []
    budget = 13.0  # < GRID_WARM_TIMEOUT_S, so the budget must be what binds

    async def _instant(slug, **kw):
        return GOOD_GRID

    real_wait_for = asyncio.wait_for

    async def _spy(aw, timeout):
        timeouts.append(timeout)
        return await real_wait_for(aw, timeout)

    with patch("asyncio.wait_for", _spy):
        _run(_instant, budget=budget)

    assert timeouts, "wait_for was never called"
    assert all(t < pcp.GRID_WARM_TIMEOUT_S for t in timeouts), (
        f"a league was given the raw {pcp.GRID_WARM_TIMEOUT_S}s ceiling under a "
        f"{budget}s pass budget — the budget was computed and then ignored: {timeouts}"
    )
    assert timeouts[0] == pytest.approx(budget / len(pcp.GRID_WARM_LEAGUES))


# --------------------------------------------------------------------------
# 3. Gotcha #34: the tail cannot starve behind an early hog.
# --------------------------------------------------------------------------

def test_every_league_is_guaranteed_its_floor_in_every_order():
    """Executed, not argued: deadline_i >= BUDGET / N for every i.

    `_prewarm_target_deadline` divides what is LEFT by what is LEFT TO DO. This
    replays the allocation against the pathological profile — each league
    consuming its entire share, which is the case that starves a fixed-slice
    loop — and asserts the floor holds at every position.
    """
    budget = pcp.GRID_WARM_PASS_BUDGET_S
    n = len(pcp.GRID_WARM_LEAGUES)
    floor = budget / n

    left = float(budget)
    for index in range(n):
        share = pcp._prewarm_target_deadline(left, n - index)
        assert share >= floor - 1e-9, (
            f"league {index} of {n} was offered {share:.3f}s, below the "
            f"{floor:.3f}s floor the budget guarantees"
        )
        left = max(0.0, left - share)  # the hog: it spends the lot


def test_an_early_hog_does_not_stop_the_tail_being_reached():
    """One slow league must not consume the pass. The tail still gets built."""
    budget = 4.0
    hog = pcp.GRID_WARM_LEAGUES[0]

    async def _one_hog(slug, **kw):
        if slug == hog:
            await asyncio.sleep(10)
        return GOOD_GRID

    warmed, report, _, _ = _run(_one_hog, budget=budget)

    assert report["grid_leagues"][hog]["outcome"] == "timeout"
    # Everyone behind the hog still ran and published.
    assert set(warmed) == set(pcp.GRID_WARM_LEAGUES) - {hog}


def test_a_league_the_budget_never_reached_says_so():
    """#1484's contract: 'never reached' and 'tried and failed' must differ.

    Three outcomes, three names. `budget_exhausted` is not `timeout` (which
    means the league ran and overran) and not `not_attempted` (the pre-seeded
    value, which reads as 'the task died before grids ran at all').

    🔴 **The budget is driven to zero directly, and that is the honest way to
    test this branch.** The first draft starved the pass with one hog and
    expected the tail to be skipped — it never was, because
    `_prewarm_target_deadline` hands each league only its share of what is LEFT,
    so a single hog *cannot* consume the pass. That is the anti-starvation
    property working, proven by `test_an_early_hog_does_not_stop_the_tail_being_reached`,
    and it makes the exhausted branch reachable only when the budget is
    genuinely gone. Setting it gone is deterministic; racing thirteen sleeps
    into an accumulated overshoot is not.
    """
    async def _good(slug, **kw):
        return GOOD_GRID

    warmed, report, redis_mock, grid_mock = _run(_good, budget=0.0)
    outcomes = {s: v["outcome"] for s, v in report["grid_leagues"].items()}

    assert warmed == []
    assert grid_mock.call_args_list == [], "a skipped league was still built"
    assert set(outcomes.values()) == {"budget_exhausted"}, outcomes
    assert "not_attempted" not in outcomes.values(), (
        "a league the pass consciously skipped is reported as if grids never ran"
    )
    assert all(
        v["pass_budget_s"] == 0.0 for v in report["grid_leagues"].values()
    ), "the skip does not record the budget that caused it"


def test_a_failing_league_still_charges_the_budget():
    """The `finally`, not four call sites. The expensive failure is the one debt
    the budget must never miss — a league that raises after 30 s has spent 30 s.
    """
    # The share must exceed the raiser's own runtime, or it times out before it
    # can raise and this tests the wrong branch (it did, in the first draft).
    budget = 13.0
    raiser = pcp.GRID_WARM_LEAGUES[0]

    async def _raise_slowly(slug, **kw):
        if slug == raiser:
            await asyncio.sleep(0.4)
            raise RuntimeError("boom")
        return GOOD_GRID

    _, report, _, _ = _run(_raise_slowly, budget=budget)

    assert report["grid_leagues"][raiser]["outcome"] == "error"
    assert report["grid_budget_left_s"] < budget, (
        "the failing league's wall time was never charged to the pass"
    )


# --------------------------------------------------------------------------
# 4. An empty build never overwrites a good grid.
# --------------------------------------------------------------------------

def test_an_empty_build_is_not_published():
    """The writer must refuse what the reader refuses.

    This publish owns the 24 h `:stale` mirror as well as the fresh key, so
    storing an empty payload does not merely fail to help — it removes the
    fallback `get_playoff_grid_cached` falls back to, turning a healthy page
    into a live rebuild. Three leagues build empty out of season today.
    """
    redis_mock = MagicMock()

    async def _all_empty(slug, **kw):
        return EMPTY_GRID

    warmed, report, redis_mock, _ = _run(_all_empty, redis_mock=redis_mock)

    assert warmed == []
    assert redis_mock.setex.call_args_list == [], (
        "an empty grid was written to Redis, clobbering last-good"
    )
    assert all(v["outcome"] == "empty" for v in report["grid_leagues"].values())


def test_an_empty_build_does_not_stop_the_other_leagues():
    """Out-of-season emptiness is the ordinary case, not a failure of the pass."""
    empty_one = pcp.GRID_WARM_LEAGUES[0]

    async def _one_empty(slug, **kw):
        return EMPTY_GRID if slug == empty_one else GOOD_GRID

    warmed, report, _, _ = _run(_one_empty)

    assert report["grid_leagues"][empty_one]["outcome"] == "empty"
    assert set(warmed) == set(pcp.GRID_WARM_LEAGUES) - {empty_one}


def test_the_empty_check_is_the_routes_own_predicate():
    """Reuse, not a second opinion.

    A private copy of "is this grid usable" in the writer would drift from the
    reader's, and the two disagreeing is precisely the bug: the writer stores
    something the reader then refuses. An error envelope is the case a naive
    `len(teams) > 0` check would publish.
    """
    from app.routes.playoffs import _grid_payload_usable

    assert not _grid_payload_usable({"teams": [], "columns": []})
    assert not _grid_payload_usable({"teams": [{"name": "A"}], "error": "timeout"})
    assert _grid_payload_usable(GOOD_GRID)

    redis_mock = MagicMock()

    async def _error_envelope(slug, **kw):
        return {"teams": [{"name": "A"}], "columns": [], "error": "timeout"}

    warmed, _, redis_mock, _ = _run(_error_envelope, redis_mock=redis_mock)
    assert warmed == []
    assert redis_mock.setex.call_args_list == []


def test_a_good_build_still_writes_both_keys_with_their_ttls():
    """The guard must not cost the thing it protects."""
    redis_mock = MagicMock()

    async def _good(slug, **kw):
        return GOOD_GRID

    warmed, _, redis_mock, _ = _run(_good, redis_mock=redis_mock)

    assert set(warmed) == set(pcp.GRID_WARM_LEAGUES)
    written = {c.args[0]: c.args[1] for c in redis_mock.setex.call_args_list}
    for slug in pcp.GRID_WARM_LEAGUES:
        assert written[f"bainluck:category:playoffs:{slug}"] == 3600
        assert written[f"bainluck:category:playoffs:{slug}:stale"] == 86400


# --------------------------------------------------------------------------
# 5. The warm build asks for the same grid the cache-eligible request asks for.
# --------------------------------------------------------------------------

def test_the_warm_build_matches_the_cache_eligible_request():
    """`cache_eligible = not debug and hours is None and top == 10`.

    Warm with any other arguments and the beat populates a key that no request
    ever reads — the grid stays cold and the report says `ok`, which is the
    quietest possible failure. This is the same class LAT-P128 found one layer
    up, where `hours=24` bypassed the cache with the import still correct.
    """
    async def _good(slug, **kw):
        return GOOD_GRID

    _, _, _, grid_mock = _run(_good)

    for call in grid_mock.call_args_list:
        assert call.kwargs["hours"] is None, call
        assert call.kwargs["top"] == 10, call
        assert call.kwargs["debug"] is False, call
