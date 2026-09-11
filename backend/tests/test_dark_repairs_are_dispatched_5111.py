"""#5111 — the four repairs that only `_resolve_winners_only` called must run.

`_regrade_kalshi_total_inversions`, `_regrade_kalshi_nhl_spread_inversions`,
`_regrade_golf_extra_winners` and `_clear_premature_open_winners` had exactly one
caller between them: `_resolve_winners_only`. That function reaches production
through exactly one task, `app.tasks.resolve_winners`, whose beat entry was
retired 2026-07-06 (#991). So all four stopped executing that day and nobody
noticed for nine weeks — long enough for #5055 to widen the TOTAL re-grade's
scope, be certified GREEN, merged and deployed with no effect whatsoever.

WHY THE OBVIOUS TEST WOULD NOT HAVE CAUGHT IT. Every one of these functions was
covered by unit tests, and every one of those tests passed for all nine weeks:
they call the repair directly and assert it grades correctly. A repair can be
perfectly correct and never run. What was missing is an assertion about
DISPATCH, so that is what this file asserts, and it asserts it the only way that
means anything — by driving the real `_backfill_all_winners` and observing that
the four are awaited. `hasattr(bw, "_regrade_kalshi_total_inversions")` would
pass today, passed throughout the outage, and is worth nothing.

The harness is the one `test_backfill_partial_result_carries_phase_stats_4658`
established: phase functions are mocked so nothing touches a database or a
venue, but the pipeline, its closure scoping, its budget guards and its return
paths are the shipped ones.
"""

import inspect
import re
from unittest.mock import AsyncMock, patch

import pytest

import app.tasks.backfill_winners as bw


#: The four. Named here rather than discovered, because the whole point is to
#: pin a set that shrank silently once already.
DARK_REPAIRS_5111 = (
    "_regrade_kalshi_nhl_spread_inversions",
    "_regrade_kalshi_total_inversions",
    "_regrade_golf_extra_winners",
    "_clear_premature_open_winners",
)

#: The `_PHASE_STATS` keys those four report under.
DARK_REPAIR_KEYS_5111 = (
    "nhl_spread_regrade",
    "total_regrade",
    "golf_extra_winner_regrade",
    "premature_open_cleared",
)

#: Everything awaited between the top of `_backfill_all_winners` and the block
#: under test. Mocked to inert dicts: this file is about whether the four are
#: reached, not about what any of these do.
PHASES_BEFORE_THE_BLOCK = (
    "_resolve_kalshi_from_scores",
    "_resolve_kalshi_spread_total_from_scores",
    "_resolve_polymarket_total_from_scores",
    "_resolve_kalshi_player_props_from_boxscore",
    "_resolve_kalshi_total_bases_from_boxscore",
    "_resolve_kalshi_period_props",
    "_backfill_kalshi_winners",
    "_backfill_kalshi_winners_via_markets",
    "_backfill_polymarket_winners_from_api",
    "_backfill_datagolf_winners",
    "_backfill_from_current_probability",
    "_precompute_bookmaker_calibration",
    "_backfill_closing_lines",
    "_compute_calibration_prices",
    "_regrade_polymarket_under_signflip",
    "_unresolve_datagolf_premature",
    "_null_impossible_both_sides_openings",
    "_correct_both_winner_guess_side",
    "_grade_date_passed_binaries",
    "_collapse_bywhen_ladder_winners",
)


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
    async def execute(self, *a, **k):
        return _PermissiveResult()

    async def commit(self):
        return None

    async def rollback(self):
        return None


class _FakeCM:
    def __call__(self, *a, **k):
        return self

    async def __aenter__(self):
        return _PermissiveSession()

    async def __aexit__(self, *a):
        return False


_DRIVE_CACHE: dict = {}


async def _run_the_pipeline():
    """Drive once; every test only reads the result. (CI cost, per #4658.)"""
    if "result" not in _DRIVE_CACHE:
        _DRIVE_CACHE["result"] = await _drive_through_the_hygiene_block()
    result, mocks = _DRIVE_CACHE["result"]
    return dict(result), mocks


async def _drive_through_the_hygiene_block():
    """Run the real pipeline until just past the resolver-hygiene block.

    The clock is virtual and does not advance on its own. The LAST of the four
    repairs moves it to 700.0, so the very next budget gate —
    `_cannot_afford("candlestick_trades")`, which sits immediately below the
    block — returns `_partial_result`. That gives a deterministic stop right
    after the code under test instead of one tuned by counting calls (gotcha
    #44: an anchor that branches on the clock is not an anchor).

    If the four calls were deleted, the clock would never advance here, the
    pipeline would sail past that gate, and the await-count assertions below go
    red — which is exactly the regression this file exists to catch.
    """
    import app.tasks.kalshi as kalshi

    state = {"v": 0.0}
    mocks = {}

    with patch("time.monotonic", side_effect=lambda: state["v"]), \
            patch.object(bw, "get_task_session", _FakeCM()), \
            patch.object(kalshi, "_link_sports_props_to_events",
                         AsyncMock(return_value={"total_linked": 0, "errors": []})), \
            patch.object(kalshi, "_backfill_candlestick_snapshots",
                         AsyncMock(return_value={"snapshots_created": 0, "errors": []})), \
            patch.object(kalshi, "_backfill_trade_history",
                         AsyncMock(return_value={"snapshots_created": 0, "errors": []})):
        for name in PHASES_BEFORE_THE_BLOCK:
            patch.object(bw, name, AsyncMock(return_value={})).start()

        for name in DARK_REPAIRS_5111:
            m = AsyncMock(return_value={"checked": 1, "flipped": 1,
                                        "cleared": 1, "errors": []})
            mocks[name] = m
            patch.object(bw, name, m).start()

        async def _stop_the_clock(*a, **k):
            # 840 - 700 = 140, under the 300s margin: the next gate returns.
            state["v"] = 700.0
            return {"cleared": 1, "errors": []}

        mocks["_clear_premature_open_winners"].side_effect = _stop_the_clock

        try:
            result = await bw._backfill_all_winners(dry_run=True, limit=5)
        finally:
            patch.stopall()
    return result, mocks


@pytest.mark.asyncio
@pytest.mark.parametrize("repair", DARK_REPAIRS_5111)
async def test_dark_repair_is_awaited_on_a_backfill_all_winners_run(repair):
    """The assertion #5111 turns on: the scheduled task actually calls it.

    Not "the function exists", not "the function grades correctly" — both were
    true every day of the nine-week outage.
    """
    _, mocks = await _run_the_pipeline()
    assert mocks[repair].await_count == 1, (
        f"{repair} was not awaited by _backfill_all_winners. It has no other "
        "live caller: _resolve_winners_only is only reachable through the "
        "app.tasks.resolve_winners beat, retired 2026-07-06 (#991). If you "
        "removed the call, this repair is now dark exactly as it was before "
        "#5111."
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("key", DARK_REPAIR_KEYS_5111)
async def test_dark_repair_counters_reach_the_verdict(key):
    """A rail whose counters nobody can see is how this went unnoticed.

    #4658/CERT-2465's rule, applied to the four: a phase that runs and reports
    nothing is indistinguishable on `task-metrics` from a phase that never ran.
    These counters are the standing evidence that the rails are dispatched.
    """
    result, _ = await _run_the_pipeline()
    assert key in result, (
        f"{key} is missing from the backfill_winners result. Add it to the "
        "_PHASE_STATS table; without it the only signal that this repair runs "
        "is a log line nobody greps."
    )


def test_the_four_run_before_the_755_re_null():
    """Placement, which is the decision #5111 had to make and get right.

    Measured 2026-09-11: the #755 re-null's regex is unanchored and
    case-insensitive over the whole `external_id`, so it reaches 611 of the
    TOTAL re-grade's 14,337 production rungs through accidental team-
    abbreviation substrings (`DE-TB-OS`, `TOR-TB`, `SD-STL`, `B-REB-RI`) — the
    re-null's own defect, filed as #5116, and one it inflicts on those rows
    today with or without these calls.

    The four therefore sit in the un-budget-guarded resolver-hygiene block,
    ABOVE the re-null and above the first `_cannot_afford` gate below it.
    Moving them under that gate would drop them into the budget-guarded tail —
    the #898 starvation `_regrade_golf_extra_winners` was explicitly written to
    escape, and the one edit that would silently reproduce this bug.
    """
    src = inspect.getsource(bw._backfill_all_winners)

    renull = src.index("ml_repair_stats = {")
    for repair in DARK_REPAIRS_5111:
        call = src.index(f"await {repair}()")
        assert call < renull, (
            f"{repair} is called after the #755 re-null. Read #5116 before "
            "moving it: below the re-null it also lands in the budget-guarded "
            "tail, which is where these repairs starve."
        )


def test_resolve_winners_only_is_still_the_documented_dead_path():
    """Pin the reachability fact itself, so the next reader cannot be misled.

    The retirement note used to call the standalone task "redundant —
    backfill_winners runs the same shared `_resolve_winners_only` path". It
    does not, and that one false sentence is the entire nine-week outage. If a
    beat entry for resolve-winners is ever re-added, this test reds and the
    duplicate-dispatch question gets asked deliberately rather than by
    accident.
    """
    import app.tasks as tasks

    beat = inspect.getsource(tasks)
    schedule_block = beat.split("beat_schedule", 1)[1]
    assert not re.search(r'"resolve-winners"\s*:', schedule_block), (
        "A resolve-winners beat entry exists again. That is not forbidden, but "
        "it now double-dispatches the four repairs #5111 mirrored into "
        "_backfill_all_winners. Decide which path owns them and update this "
        "test with the reasoning."
    )
