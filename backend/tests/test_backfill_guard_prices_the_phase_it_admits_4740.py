"""#4740 — a budget guard must price the phase it admits, not just check a margin.

`backfill_winners`' admission test asked "is at least `_BUDGET_MARGIN_S` (300s)
left" before every guarded phase. That is a sound question only about a phase
costing LESS than the margin. Every guarded phase satisfies that except
`prob_and_datagolf`, measured 383.3s — so the guard could admit a phase it could
not afford, and the task then died at the 840s wall instead of returning.

The specimen these tests are built on is the 2026-09-10 09:45Z production cycle,
read from `bainluck:backfill_phase_timing` at the moment of death:

    cumulative_s 528.2, running_phase "prob_and_datagolf", completed
    {score_resolution 52.6, kalshi_api 97.8, kalshi_markets_api 11.4,
     polymarket_api 366.3}

840 - 528.1 = 311.8s left. The old test cleared 300 by 11.8 seconds, admitted a
~383s phase, and SoftTimeLimitExceeded'd at 09:59:01Z — losing the counters of
all four completed phases, which is exactly what #4658 had just shipped to
report.

The discriminating numbers are therefore REAL and are used verbatim: 311.8 must
be refused and 507.3 (the cycle that succeeded, 03:45Z) must be admitted. A test
that only proved "some large number is admitted and some small one is not" would
have passed against the buggy code too.
"""

import re
import inspect

import pytest
from unittest.mock import AsyncMock, patch

import app.tasks.backfill_winners as bw


#: The production soft limit the pipeline budgets against.
SOFT_LIMIT_S = 840

#: The plain margin every unpriced phase still uses.
MARGIN_S = 300

#: 2026-09-10 09:45Z — the cycle that died. cum 528.1 ⇒ 311.8s left.
BUDGET_LEFT_AT_THE_DEATH = 311.8

#: 2026-09-10 03:45Z — the cycle that completed. cum 332.7 ⇒ 507.3s left.
BUDGET_LEFT_ON_THE_GOOD_CYCLE = 507.3

#: The largest cost measured for `prob_and_datagolf` (03:45Z phase_times).
MEASURED_PROB_AND_DATAGOLF_S = 383.3


def _source_of_the_pipeline():
    return inspect.getsource(bw._backfill_all_winners)


class TestThePricingRule:
    """`_phase_admission_floor` is the whole rule, at module scope so it can be
    asserted directly rather than inferred from a 900-line closure."""

    def test_the_death_cycles_budget_is_refused_for_prob_and_datagolf(self):
        floor = bw._phase_admission_floor("prob_and_datagolf", MARGIN_S)
        assert BUDGET_LEFT_AT_THE_DEATH < floor, (
            f"311.8s left must NOT admit prob_and_datagolf: it is the measured "
            f"budget of the 09:45Z cycle that died, and the phase costs "
            f"{MEASURED_PROB_AND_DATAGOLF_S}s"
        )

    def test_the_good_cycles_budget_still_admits_prob_and_datagolf(self):
        """The fix must not starve the phase on the cycles that could afford it.

        Without this, 'refuse everything' would pass the test above.
        """
        floor = bw._phase_admission_floor("prob_and_datagolf", MARGIN_S)
        assert BUDGET_LEFT_ON_THE_GOOD_CYCLE >= floor, (
            "507.3s left is the 03:45Z cycle, which ran prob_and_datagolf to "
            "completion in 383.3s — refusing it would be a regression"
        )

    def test_the_priced_floor_exceeds_the_largest_measured_cost(self):
        """Shrinking the table's number below the measurement reds here.

        The bug was a floor BELOW the phase's cost; this is the invariant that
        was violated, stated directly.
        """
        floor = bw._phase_admission_floor("prob_and_datagolf", MARGIN_S)
        assert floor > MEASURED_PROB_AND_DATAGOLF_S, (
            f"the admission floor ({floor}s) must exceed the measured cost "
            f"({MEASURED_PROB_AND_DATAGOLF_S}s) or the guard can admit a phase "
            f"it cannot afford — that IS #4740"
        )

    @pytest.mark.parametrize("phase", [
        "kalshi_markets_api", "polymarket_api", "bookmaker_closing",
        "calibration_prices", "candlestick_trades", "trades",
        "polymarket_group_api", "datagolf_settlement", "datagolf_winners",
        "golf_matchups",
    ])
    def test_every_unpriced_phase_keeps_the_plain_margin(self, phase):
        """The ten sites this issue does not change are pinned as unchanged.

        `prob_and_datagolf` is deliberately absent from this list: it is the one
        phase whose behaviour moves.
        """
        assert bw._phase_admission_floor(phase, MARGIN_S) == MARGIN_S

    def test_an_unpriced_phase_is_admitted_at_the_death_cycles_budget(self):
        """311.8s left refuses prob_and_datagolf and admits everything else —
        the change is scoped to one phase, not a fleet-wide tightening."""
        for phase in ("candlestick_trades", "trades", "calibration_prices"):
            assert BUDGET_LEFT_AT_THE_DEATH >= bw._phase_admission_floor(
                phase, MARGIN_S
            )

    def test_pricing_never_lowers_the_plain_margin(self):
        """A table entry below the margin must not weaken the guard."""
        with patch.object(bw, "_PHASE_ADMISSION_COST_S", {"cheap_phase": 5.0}):
            assert bw._phase_admission_floor("cheap_phase", MARGIN_S) == MARGIN_S


class TestTheGuardSitesCannotDrift:
    """Structural guards: the pricing name and the reported name are one name,
    and no admission test bypasses the rule."""

    def test_every_guard_prices_the_phase_it_reports(self):
        src = _source_of_the_pipeline().split("\n")
        pairs = 0
        for i, line in enumerate(src):
            m = re.match(r'\s*if _cannot_afford\("([a-z0-9_]+)"\):\s*$', line)
            if not m:
                continue
            follower = re.match(
                r'\s*return _partial_result\("([a-z0-9_]+)"\)\s*$', src[i + 1]
            )
            assert follower, (
                f'guard for {m.group(1)!r} is not followed by its '
                f'_partial_result: {src[i + 1]!r}'
            )
            assert m.group(1) == follower.group(1), (
                f"guard PRICES {m.group(1)!r} but REPORTS {follower.group(1)!r} "
                f"— a phase priced under one name and reported under another is "
                f"how the cost table goes quietly wrong"
            )
            pairs += 1
        assert pairs == 11, f"expected 11 guard sites, found {pairs}"

    def test_no_admission_test_bypasses_the_pricing_rule(self):
        """A bare `_budget_left() < _BUDGET_MARGIN_S` admission test is the bug.

        `_BUDGET_MARGIN_S` still legitimately appears as the deadline handed to
        `_backfill_polymarket_winners_from_api` and inside `_cannot_afford`
        itself, so this pins the COMPARISON, not the constant.
        """
        src = _source_of_the_pipeline()
        assert "_budget_left() < _BUDGET_MARGIN_S" not in src, (
            "an admission test that compares the budget against the bare margin "
            "cannot price the phase it admits — route it through _cannot_afford"
        )

    def test_every_priced_phase_is_actually_a_guard_site(self):
        """A table entry for a phase no guard names would price nothing.

        Catches the rename half of the drift the previous test catches the
        other half of.
        """
        src = _source_of_the_pipeline()
        named = set(re.findall(r'_cannot_afford\("([a-z0-9_]+)"\)', src))
        for phase in bw._PHASE_ADMISSION_COST_S:
            assert phase in named, (
                f"{phase!r} is priced but no guard admits it — the entry is dead"
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


#: Distinctive payloads so the assertions prove the VALUE travelled, not merely
#: that a key exists. `no_result`/`ungradeable_result` are #4604's counters —
#: the ones the 09:45Z throw discarded.
KALSHI_API_STATS = {"resolved": 7, "no_result": 3, "ungradeable_result": 2}
POLY_API_STATS = {"resolved": 11, "errors": []}


async def _drive_to_the_prob_and_datagolf_guard(budget_left):
    """Drive the real pipeline with `budget_left` seconds remaining at the guard.

    `monotonic()` returns 0.0 once (that call is `_pipeline_start`) and the
    elapsed-time value thereafter, so `_budget_left()` is a constant
    `840 - elapsed`. Every phase before the guard is mocked to a no-op dict, so
    the guard, the closure scoping and both return paths are the shipped ones.
    """
    import app.tasks.kalshi as kalshi

    elapsed = SOFT_LIMIT_S - budget_left
    state = {"v": 0.0}

    def fake_monotonic():
        v = state["v"]
        state["v"] = elapsed
        return v

    mocked_no_ops = [
        "_resolve_kalshi_from_scores",
        "_resolve_kalshi_spread_total_from_scores",
        "_resolve_kalshi_player_props_from_boxscore",
        "_resolve_kalshi_total_bases_from_boxscore",
        "_resolve_kalshi_period_props",
        "_backfill_kalshi_winners_via_markets",
        "_backfill_datagolf_winners",
        "_backfill_from_current_probability",
    ]

    patches = []
    try:
        with patch("time.monotonic", side_effect=fake_monotonic), \
                patch.object(bw, "get_task_session", _FakeCM()), \
                patch.object(kalshi, "_link_sports_props_to_events",
                             AsyncMock(return_value={"total_linked": 0, "errors": []})), \
                patch.object(kalshi, "_backfill_candlestick_snapshots",
                             AsyncMock(return_value={"snapshots_created": 0, "errors": []})), \
                patch.object(kalshi, "_backfill_trade_history",
                             AsyncMock(return_value={"snapshots_created": 0, "errors": []})):
            for name in mocked_no_ops:
                p = patch.object(bw, name, AsyncMock(return_value={}))
                p.start()
                patches.append(p)
            for name, payload in (
                ("_backfill_kalshi_winners", KALSHI_API_STATS),
                ("_backfill_polymarket_winners_from_api", POLY_API_STATS),
            ):
                p = patch.object(bw, name, AsyncMock(return_value=dict(payload)))
                p.start()
                patches.append(p)
            return await bw._backfill_all_winners()
    finally:
        for p in patches:
            p.stop()


@pytest.mark.asyncio
class TestTheDeathCycleNowReturns:
    """The end-to-end conversion: the 09:45Z budget must produce a partial
    RESULT instead of running on into the wall."""

    async def test_the_guard_fires_at_the_death_cycles_budget(self):
        result = await _drive_to_the_prob_and_datagolf_guard(
            BUDGET_LEFT_AT_THE_DEATH
        )
        assert result["status"] == "partial_budget_guard"
        assert result["stopped_before"] == "prob_and_datagolf", (
            "at 311.8s left the pipeline must stop BEFORE prob_and_datagolf — "
            "admitting it here is what killed the 09:45Z cycle"
        )

    async def test_the_completed_phases_counters_travel_out(self):
        """#4658's ship, on the exit #4740 makes reachable.

        A throw returns nothing at all, so these counters were the concrete
        loss on all 16 deaths.
        """
        result = await _drive_to_the_prob_and_datagolf_guard(
            BUDGET_LEFT_AT_THE_DEATH
        )
        assert result["kalshi_api"] == KALSHI_API_STATS
        assert result["kalshi_api"]["no_result"] == 3
        assert result["kalshi_api"]["ungradeable_result"] == 2
        assert result["polymarket_api"] == POLY_API_STATS

    async def test_a_phase_that_never_ran_is_absent_not_empty(self):
        """gotcha #53 — an absence must not wear a value.

        `from_probability` and `datagolf_early` are produced INSIDE
        `prob_and_datagolf`, the phase this exit refuses, so they must not
        appear at all.
        """
        result = await _drive_to_the_prob_and_datagolf_guard(
            BUDGET_LEFT_AT_THE_DEATH
        )
        assert "from_probability" not in result
        assert "datagolf_early" not in result

    async def test_the_good_cycles_budget_runs_past_this_guard(self):
        """The control: same drive, the 03:45Z budget, and the pipeline does
        NOT stop here — so the test above is measuring the guard and not the
        harness."""
        result = await _drive_to_the_prob_and_datagolf_guard(
            BUDGET_LEFT_ON_THE_GOOD_CYCLE
        )
        assert result.get("stopped_before") != "prob_and_datagolf", (
            "507.3s left is the cycle that completed the phase — stopping here "
            "would starve it"
        )
