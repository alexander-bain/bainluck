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

CERT-2585 BLOCKED THE FIRST VERSION OF THIS FIX, AND THIS FILE IS WHY IT COULD.
That version mirrored the four into the hygiene block ~200 lines below the first
`_cannot_afford` gate and called it "the un-budget-guarded core section". The
tests here passed anyway, because the harness only ever advanced its virtual
clock AT the four repairs — so no gate above them could fire and the drive could
not tell a reachable line from a starved one. Production's own numbers say it is
starved: `task-metrics` 2026-09-11 shows both successful cycles in 24h running
782.1s and 611.6s against an effective budget of 540s, so the cycle returns at a
gate well above that site.

The clock is therefore now blown BEFORE the guarded region is entered, which is
the production condition, and the four are asserted to run anyway. A test whose
clock cannot reach the failing state is not a weaker test, it is a test of a
different program.
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

#: The guard the pipeline hits first, and the phase name it reports stopping
#: before. The four must be dispatched ABOVE this line — that is the whole of
#: CERT-2585's required repair.
FIRST_BUDGET_EXIT_PHASE = "kalshi_markets_api"

#: Everything awaited between the top of `_backfill_all_winners` and the
#: resolver-hygiene block. Mocked to inert dicts: this file is about whether the
#: four are reached, not about what any of these do.
PHASES_BEFORE_THE_BLOCK = (
    "_resolve_kalshi_from_scores",
    "_resolve_kalshi_spread_total_from_scores",
    "_resolve_polymarket_total_from_scores",
    "_resolve_kalshi_player_props_from_boxscore",
    "_resolve_kalshi_total_bases_from_boxscore",
    "_resolve_kalshi_period_props",
    "_backfill_kalshi_winners",
)

#: Phases BELOW the first gate. They are mocked too, so that a regression which
#: moves the four back under the gate fails on the await assertions rather than
#: dying in an unmocked callee — a red for the right reason.
PHASES_AFTER_THE_FIRST_GATE = (
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
    """Run the real pipeline with the budget ALREADY blown at the first gate.

    The clock is virtual and does not advance on its own. `kalshi_api` — the
    last phase above the resolver-hygiene block — moves it to 700.0, so
    `_budget_left()` is 840 - 700 = 140, under the 300s `_BUDGET_MARGIN_S`, and
    the very first `_cannot_afford` gate returns `_partial_result`. Nothing
    below that gate runs.

    That is the production condition, not a contrived one: measured on
    `task-metrics` 2026-09-11, both successful cycles in the trailing 24h ran
    782.1s and 611.6s against an effective budget of 540s. A drive that lets the
    pipeline sail through every gate is testing a cycle production does not have.

    The clock jump is unconditional and lives in a phase ABOVE the code under
    test, so the stop point is fixed by the pipeline's own structure rather than
    by anything the four repairs do (gotcha #44: an anchor that branches on the
    clock is not an anchor). The previous version advanced the clock inside the
    LAST of the four, which made the stop point depend on the code under test —
    it could not fail while the four sat below a gate, which is exactly the
    defect CERT-2585 caught.
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
        for name in PHASES_BEFORE_THE_BLOCK + PHASES_AFTER_THE_FIRST_GATE:
            patch.object(bw, name, AsyncMock(return_value={})).start()

        for name in DARK_REPAIRS_5111:
            m = AsyncMock(return_value={"checked": 1, "flipped": 1,
                                        "cleared": 1, "errors": []})
            mocks[name] = m
            patch.object(bw, name, m).start()

        async def _blow_the_budget(*a, **k):
            # 840 - 700 = 140, under the 300s margin: the first gate returns.
            state["v"] = 700.0
            return {}

        # `kalshi_api`, the phase immediately above the hygiene block.
        bw._backfill_kalshi_winners.side_effect = _blow_the_budget

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


@pytest.mark.asyncio
async def test_dark_repairs_run_before_first_budget_exit():
    """CERT-2585's required repair, asserted end to end on the shipped pipeline.

    The exact condition production runs in: the budget is gone by the time the
    first `_cannot_afford` gate is reached, so the cycle returns
    `partial_budget_guard` there and NOTHING below that gate executes. The four
    repairs must still have run, and their counters must still reach the
    verdict — otherwise #5111's fix only relocates the darkness.

    All three claims are asserted together on one drive on purpose. "The guard
    fired" alone would pass if the four never ran; "the four ran" alone would
    pass on a drive whose guard never fired, which is precisely how the first
    version of this file went green over a starved call site.
    """
    result, mocks = await _run_the_pipeline()

    assert result.get("status") == "partial_budget_guard", (
        "the drive did not stop at a budget guard, so it cannot say anything "
        f"about what runs above one. Got status={result.get('status')!r}."
    )
    assert result.get("stopped_before") == FIRST_BUDGET_EXIT_PHASE, (
        "the drive stopped at a LATER gate than the first one. Everything "
        "between the two is then untested, which is the hole CERT-2585 found. "
        f"Got stopped_before={result.get('stopped_before')!r}."
    )

    not_run = [r for r in DARK_REPAIRS_5111 if mocks[r].await_count != 1]
    assert not not_run, (
        f"{not_run} did not run before the first budget exit. They are below a "
        "`_cannot_afford` gate, and production reaches that gate on every "
        "cycle it completes (782.1s / 611.6s vs a 540s effective budget, "
        "measured 2026-09-11). A repair below the gate is dark, exactly as it "
        "was for the nine weeks #5111 is about."
    )

    missing = [k for k in DARK_REPAIR_KEYS_5111 if k not in result]
    assert not missing, (
        f"{missing} are absent from the partial-budget return. The four ran but "
        "report nothing, so `task-metrics` cannot distinguish that from their "
        "never having run — #4658's rule, and the reason nobody noticed for "
        "nine weeks. Add them to the `_PHASE_STATS` table."
    )


def test_the_four_are_dispatched_above_every_budget_gate():
    """The structural guard: source position, so the next mover is stopped cold.

    Two orderings have to hold, and they came from different places.

    ABOVE THE FIRST `_cannot_afford` — CERT-2585. Below it the calls are
    starved rather than dark, which looks fixed and is not. This is asserted
    against the FIRST gate in the source rather than a named one, so inserting a
    new gate above the block also reds.

    ABOVE THE #755 RE-NULL — measured 2026-09-11. That re-null's regex is
    unanchored and case-insensitive over the whole `external_id`, so it reaches
    611 of the TOTAL re-grade's 14,337 production rungs through accidental
    team-abbreviation substrings (`DE-TB-OS`, `TOR-TB`, `SD-STL`, `B-REB-RI`) —
    the re-null's own defect, filed as #5116, inflicted on those rows with or
    without these calls.
    """
    src = inspect.getsource(bw._backfill_all_winners)

    first_gate = src.index("if _cannot_afford(")
    renull = src.index("ml_repair_stats = {")

    for repair in DARK_REPAIRS_5111:
        call = src.index(f"await {repair}()")
        assert call < first_gate, (
            f"{repair} is called below the first `_cannot_afford` gate. That is "
            "the CERT-2585 defect: production returns at a budget guard on "
            "every long cycle, so the call never executes. Move it back into "
            "the resolver-hygiene block above the first gate."
        )
        assert call < renull, (
            f"{repair} is called after the #755 re-null. Read #5116 before "
            "moving it."
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
