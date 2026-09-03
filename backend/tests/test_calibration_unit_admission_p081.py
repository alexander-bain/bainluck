"""CAL-P081 (#2052): a unit may not spend the whole beat, and a cancelled unit
must not turn a working beat RED.

This file is the successor to ``test_calibration_unit_window_p038.py`` and it
exists because that file's guard — correct, and still correct — did not stop the
2026-08-20 18:37:31Z failure. The ledger for that beat is banked verbatim in
commit ``cde2c222``:

    read:futures_unit                 1,262,276 ms   (21.0 min)
    read:futures_generation              75,780 ms
    staged:units_this_beat                      6
    staged:units_completed_this_beat            5
    staged:unit_ms_mean                   210,379 ms
    staged:unit_ms_mean_completed          72,202 ms

Five completed units cost 361,010 ms between them. The sixth cost **901,266 ms**
— 12.5x the completed mean — and ended in ``QueryCanceledError`` mid-``market_info``.

**The admission check passed, and it was right to.** When the sixth unit started,
roughly 914,000 ms of window remained and the worst unit observed so far was at
most 361,010 ms; ``_unit_fits_in_window`` compared them and said yes. No rule
that admits on past cost can refuse an admission that past cost endorses. So the
directive's framing — "the loop starts units it cannot finish" — is half the
story, and the tests below pin both halves apart:

* **Admission** genuinely had a residual, named in CAL-P038's own docstring: on
  the FIRST unit of a beat ``worst_unit_ms`` is 0 and the fence opened
  unconditionally. The carried ``unit_ms`` on the plan closes it. That is
  ``TestAdmission``.
* **The unit's own bound** is what was actually missing. A unit's
  ``statement_timeout`` was the whole rest of the beat, so one pathological unit
  converted every remaining minute into a single cancellation instead of into
  the ~12 further units that fit. That is ``TestUnitBound``.
* **Containment.** The cancellation propagated out of the phase, so the beat
  terminated ``thrown``/``DBAPIError`` = ``failed`` — a RED verdict on a beat
  that had banked five units durably. That is ``TestContainment``, and it is the
  false-RED twin of the false-GREEN ``task_verdict.py`` exists to prevent.

The loop tests drive the REAL ``_run_staged_futures`` against a real
``PhaseLedger`` and a fake database that cancels at whatever ``statement_timeout``
the loop actually armed — not at a condition the test invented. That is what
makes them non-vacuous: widen the unit bound back to the phase bound and
``test_the_specimen_beat_banks_the_rest_of_its_units`` goes red with exactly the
production shape.
"""

from __future__ import annotations

import contextlib
import types

import pytest

from app.tasks import calibration_main_build as cmb
from app.tasks import precompute_calibration as pc
from app.utils import calibration_staged_futures as sf
from app.utils.calibration_phase_ledger import (
    PHASE_FUTURES,
    STAGED_UNIT_MAX_CANCELLATIONS,
    STAGED_UNIT_OVERRUN_FACTOR,
    PhaseBudget,
    PhaseLedger,
    PhasePlan,
)

# The specimen, in one place so no test re-types it.
SPECIMEN_UNIT_MS = 72_202       # staged:unit_ms_mean_completed, 5 completions
SPECIMEN_RUNAWAY_MS = 901_266   # the sixth unit: 1,262,276 - 5 * 72,202
SPECIMEN_WINDOW_MS = 1_351_697  # the phase window the beat was planned against


# =============================================================================
# 1. ADMISSION — the fence, and the residual CAL-P038 named
# =============================================================================


class TestAdmission:
    """``_unit_fits_in_window`` with the carried cost as a third input."""

    def test_the_first_unit_of_a_beat_is_now_fenced_by_the_carried_cost(self):
        """CAL-P038's named residual, closed.

        A beat that has completed nothing has ``worst_unit_ms == 0``, and the old
        predicate answered True on any positive remainder — so the first unit of
        a beat could always be started into a window far too small for it. The
        previous beat's measured ``unit_ms`` is evidence about exactly this unit
        and the loop simply never read it.
        """
        assert pc._unit_fits_in_window(50_000, 0.0, SPECIMEN_UNIT_MS) is False
        assert pc._unit_fits_in_window(50_000, 0.0) is True  # the old answer

    def test_a_carried_cost_that_fits_still_admits(self):
        assert pc._unit_fits_in_window(200_000, 0.0, SPECIMEN_UNIT_MS) is True

    def test_the_larger_of_the_two_observations_wins(self):
        """They are different evidence, not rival estimates.

        ``worst_unit_ms`` is this beat's own worst observation; ``prior_unit_ms``
        is last beat's mean. Taking the max is conservative in every combination,
        so the fence never loosens because a good beat followed a bad one.
        """
        # This beat is worse than last beat: this beat's number must govern.
        assert pc._unit_fits_in_window(200_000, 300_000.0, SPECIMEN_UNIT_MS) is False
        # Last beat was worse than this beat so far: last beat's must govern.
        assert pc._unit_fits_in_window(200_000, 10_000.0, 300_000.0) is False

    def test_with_no_measurement_at_all_a_beat_may_still_attempt_one_unit(self):
        """Or the build can never progress. Unchanged from CAL-P038, on purpose."""
        assert pc._unit_fits_in_window(1, 0.0, 0.0) is True
        assert pc._unit_fits_in_window(10_000, 0.0, None) is True

    def test_no_time_left_still_refuses_whatever_the_carried_cost_says(self):
        assert pc._unit_fits_in_window(0, 0.0, SPECIMEN_UNIT_MS) is False
        assert pc._unit_fits_in_window(-5, 0.0, 1.0) is False

    def test_the_specimen_admission_was_correct_and_this_fence_does_not_change_it(self):
        """The honest negative result, pinned so nobody re-litigates it.

        With ~914,000 ms left and 361,010 ms of worst-case evidence, admitting
        the sixth unit was the right call on the evidence available. A test suite
        that quietly "fixed" this by making admission stricter would be fitting a
        rule to one specimen.
        """
        assert pc._unit_fits_in_window(914_000, 361_010.0, SPECIMEN_UNIT_MS) is True


# =============================================================================
# 2. THE UNIT BOUND — what was actually missing
# =============================================================================


def _ledger(*, window_ms: int, unit_ms: int | None, units_done: int = 5) -> PhaseLedger:
    """A real ledger whose plan carries (or does not carry) a measured unit cost."""
    plan = PhasePlan(
        budgets=(
            PhaseBudget(
                name=PHASE_FUTURES,
                required=True,
                budget_ms=None,
                statement_timeout_ms=None,
                measured_input=True,
                unit_ms=unit_ms,
                units_total=128,
                units_done=units_done if unit_ms else 0,
            ),
        ),
        soft_limit_ms=window_ms + 120_000,
        cleanup_margin_ms=120_000,
    )
    return PhaseLedger(
        plan=plan,
        population_version="q268",
        owner="test:1",
        generation=1,
        input_fingerprint="fp",
        phases=(PHASE_FUTURES,),
    )


class TestUnitBound:
    """``PhaseLedger.statement_timeout_for_unit``."""

    def test_a_unit_is_bounded_by_a_multiple_of_its_own_measured_cost(self):
        led = _ledger(window_ms=SPECIMEN_WINDOW_MS, unit_ms=SPECIMEN_UNIT_MS)
        phase_bound = led.statement_timeout_for(PHASE_FUTURES, elapsed_ms=437_000)
        unit_bound = led.statement_timeout_for_unit(PHASE_FUTURES, elapsed_ms=437_000)
        assert unit_bound < phase_bound
        assert unit_bound <= SPECIMEN_UNIT_MS * STAGED_UNIT_OVERRUN_FACTOR

    def test_the_specimen_runaway_unit_is_cancelled_at_a_third_of_what_it_spent(self):
        """The number the fix is worth, computed rather than asserted vaguely."""
        led = _ledger(window_ms=SPECIMEN_WINDOW_MS, unit_ms=SPECIMEN_UNIT_MS)
        bound = led.statement_timeout_for_unit(PHASE_FUTURES, elapsed_ms=437_000)
        assert bound < SPECIMEN_RUNAWAY_MS / 3
        # ...and the window it hands back to the beat buys further units.
        reclaimed = SPECIMEN_RUNAWAY_MS - bound
        assert reclaimed // SPECIMEN_UNIT_MS >= 8

    def test_with_no_measured_unit_cost_the_phase_bound_stands_unchanged(self):
        """Never bounded by a number the build did not measure (ruling 075)."""
        led = _ledger(window_ms=SPECIMEN_WINDOW_MS, unit_ms=None)
        assert led.measured_unit_ms(PHASE_FUTURES) is None
        assert led.statement_timeout_for_unit(
            PHASE_FUTURES, elapsed_ms=10_000
        ) == led.statement_timeout_for(PHASE_FUTURES, elapsed_ms=10_000)

    def test_a_measured_cost_with_zero_completions_is_not_a_measurement(self):
        led = _ledger(window_ms=SPECIMEN_WINDOW_MS, unit_ms=SPECIMEN_UNIT_MS, units_done=0)
        assert led.measured_unit_ms(PHASE_FUTURES) is None

    def test_the_unit_bound_can_never_exceed_the_phase_bound(self):
        """A huge measured unit must not be able to WIDEN the window.

        The direction that matters: this bound only ever takes time away from a
        unit. If it could hand time back, a slow unit would be free to outlive
        the beat and the deadline discipline would be gone.
        """
        led = _ledger(window_ms=SPECIMEN_WINDOW_MS, unit_ms=10_000_000)
        for elapsed in (0, 500_000, 1_200_000, SPECIMEN_WINDOW_MS - 1):
            assert led.statement_timeout_for_unit(
                PHASE_FUTURES, elapsed_ms=elapsed
            ) <= led.statement_timeout_for(PHASE_FUTURES, elapsed_ms=elapsed)

    def test_this_beats_own_observation_overrides_the_carried_mean(self):
        """Stronger evidence wins the moment it exists."""
        led = _ledger(window_ms=SPECIMEN_WINDOW_MS, unit_ms=SPECIMEN_UNIT_MS)
        carried = led.statement_timeout_for_unit(PHASE_FUTURES, elapsed_ms=0)
        observed = led.statement_timeout_for_unit(
            PHASE_FUTURES, elapsed_ms=0, unit_ms=SPECIMEN_UNIT_MS * 3
        )
        assert observed > carried

    def test_the_overrun_factor_sits_above_the_measured_spread(self):
        """Derived from the ledger's own pair, not chosen (ruling 075).

        ``unit_ms_mean`` 210,379 over attempts vs ``unit_ms_mean_completed``
        72,202 over completions is a 2.9x spread the build genuinely exhibits.
        A factor at or below that would start cancelling units that are merely
        slow; one at or above the 12.5x specimen would not catch it.
        """
        assert 210_379 / 72_202 < STAGED_UNIT_OVERRUN_FACTOR
        assert STAGED_UNIT_OVERRUN_FACTOR < SPECIMEN_RUNAWAY_MS / SPECIMEN_UNIT_MS


# =============================================================================
# 3. CONTAINMENT — the loop, against a database that cancels for real
# =============================================================================


class _StatementCancelled(Exception):
    """Stands in for ``asyncpg.exceptions.QueryCanceledError``.

    The message is the one Postgres emits, because ``is_statement_timeout``
    matches on the message and a stand-in with a different message would test a
    predicate the production failure never meets.
    """


class _Runner:
    """The real ledger, a fake clock, and the surface the loop touches.

    The clock is advanced by the fake database, so a unit's cost is a property of
    the test rather than of the machine it runs on (gotcha #44).
    """

    def __init__(self, *, window_ms: int, prior_unit_ms: int | None):
        self.ledger = _ledger(window_ms=window_ms, unit_ms=prior_unit_ms)
        self._elapsed = 0
        self.population_version = "q268"
        self.fingerprint = "fp"
        self.owner = "test:1"
        self.generation = 1
        self.armed: list[int] = []

    def elapsed_ms(self) -> int:
        return self._elapsed

    def advance(self, ms: int) -> None:
        self._elapsed += ms

    def measured_unit_ms(self, phase: str):
        return self.ledger.measured_unit_ms(phase)

    @contextlib.contextmanager
    def stage(self, _name: str):
        yield

    async def commit(self, _db) -> None:
        return None

    async def apply_statement_timeout(self, _db, phase) -> int:
        return self.ledger.statement_timeout_for(phase, elapsed_ms=self._elapsed)

    async def apply_unit_statement_timeout(self, _db, phase, *, unit_ms=None, deferred_rebuild=False) -> int:
        armed = self.ledger.statement_timeout_for_unit(
            phase, elapsed_ms=self._elapsed, unit_ms=unit_ms
        )
        self.armed.append(armed)
        return armed


class _Db:
    """A database that cancels at whatever timeout the loop ARMED.

    This is the difference from the CAL-P038 harness, and the whole point of the
    file: that one cancelled on "the unit outran the window", which can only ever
    reproduce the last-unit failure. This one cancels on "the unit outran its own
    statement timeout", which is what Postgres does and what the sixth unit hit.
    """

    def __init__(self, runner: _Runner, roster, costs):
        self.runner = runner
        self.roster = roster
        self.costs = list(costs)
        self.completed = 0
        self.cancelled = 0
        self.rolled_back = 0
        self._generation_read_done = False

    async def execute(self, _sql, _params=None):
        if not self._generation_read_done:
            self._generation_read_done = True
            return types.SimpleNamespace(all=lambda: self.roster)
        cost = self.costs.pop(0) if self.costs else 1
        armed = self.runner.armed[-1] if self.runner.armed else 10**9
        window_left = self.runner.ledger.remaining_ms(elapsed_ms=self.runner.elapsed_ms())
        cap = min(armed, window_left)
        if cost > cap:
            self.runner.advance(cap)
            self.cancelled += 1
            raise _StatementCancelled("canceling statement due to statement timeout")
        self.runner.advance(cost)
        self.completed += 1
        return types.SimpleNamespace(all=lambda: [])

    async def rollback(self) -> None:
        self.rolled_back += 1


def _roster(n: int):
    return [
        types.SimpleNamespace(market_id=i, source="kalshi", vm_id=f"m:{i}", is_grouped=False)
        for i in range(1, n + 1)
    ]


@pytest.fixture
def loop_env(monkeypatch):
    """Wire the real planner/cursor to fake persistence and the cancelling db."""
    saved: list[int] = []

    async def _load(**kwargs):
        return (
            sf.new_staged_cursor(
                population_version=kwargs["population_version"],
                input_fingerprint=kwargs["input_fingerprint"],
                generation_fingerprint=kwargs["generation_fingerprint"],
                owner=kwargs["owner"],
                generation=kwargs["generation"],
            ),
            "resume",
            "resumable",
        )

    async def _save(cursor, terminal=None):
        saved.append(len(cursor.committed_units))
        return True

    monkeypatch.setattr(cmb, "load_staged_cursor", _load)
    monkeypatch.setattr(cmb, "save_staged_cursor", _save)
    monkeypatch.setattr(cmb, "staged_lease", lambda: 0.0)
    monkeypatch.setattr(pc, "_futures_generation_sql", lambda: "SELECT 1")

    def _build(*, window_ms, costs, prior_unit_ms, buckets, n_markets=None):
        monkeypatch.setattr(cmb, "STAGED_FUTURES_BUCKETS", buckets)
        runner = _Runner(window_ms=window_ms, prior_unit_ms=prior_unit_ms)
        db = _Db(runner, _roster(n_markets or buckets * 2), costs)
        monkeypatch.setattr(
            pc, "time", types.SimpleNamespace(monotonic=lambda: runner.elapsed_ms() / 1000.0)
        )
        return runner, db

    _build.saved = saved
    return _build


async def _run(runner, db):
    return await pc._run_staged_futures(db, runner, lambda frozen=False: "SELECT 1")


class TestContainment:
    @pytest.mark.asyncio
    async def test_the_specimen_beat_banks_the_rest_of_its_units(self, loop_env):
        """The 18:37:31Z beat, replayed: five ordinary units then a runaway.

        Under the defect the runaway consumed the whole remaining window and the
        beat banked five. Bounded, it is cancelled at its own backstop and the
        beat carries on with the ~610 s that leaves.
        """
        costs = [SPECIMEN_UNIT_MS] * 5 + [SPECIMEN_RUNAWAY_MS] + [SPECIMEN_UNIT_MS] * 12
        runner, db = loop_env(
            window_ms=SPECIMEN_WINDOW_MS,
            costs=costs,
            prior_unit_ms=SPECIMEN_UNIT_MS,
            buckets=18,
        )
        rows = await _run(runner, db)

        assert rows is None                      # the generation is not finished
        assert db.cancelled == 1                 # exactly the runaway
        assert db.completed > 5, (
            "the beat must bank units AFTER the runaway; banking exactly five is "
            "the production failure this file exists for"
        )
        # Under the defect the runaway alone spent 901,266 ms. Bounded, it spends
        # ~260,000 ms, and the difference is the units below.
        assert db.completed >= 12

    @pytest.mark.asyncio
    async def test_a_cancelled_unit_ends_the_beat_partial_and_never_propagates(
        self, loop_env
    ):
        """The false RED, gone.

        ``_run_staged_futures`` returning ``None`` is what the caller turns into
        ``StagedFuturesIncomplete`` -> ``cancelled``. A raised ``DBAPIError``
        instead is ``failed``, and that is what drove ``consecutive_failures``
        against a build that was banking units every beat.
        """
        runner, db = loop_env(
            window_ms=400_000,
            costs=[SPECIMEN_UNIT_MS, SPECIMEN_RUNAWAY_MS],
            prior_unit_ms=SPECIMEN_UNIT_MS,
            buckets=4,
        )
        rows = await _run(runner, db)

        assert rows is None
        assert db.cancelled == 1
        assert runner.ledger.stages.get("staged:units_cancelled") == 1
        assert runner.ledger.stages.get("staged:unit_cancelled_after_ms", 0) > 0

    @pytest.mark.asyncio
    async def test_a_cancelled_unit_is_SKIPPED_so_a_repeat_offender_cannot_stall_the_build(
        self, loop_env
    ):
        """The regression this design was one line away from shipping.

        The loop skips units the cursor already holds, so a unit that cancels
        reproducibly is the FIRST one every later beat attempts. Ending the beat
        on a cancellation would therefore bank ZERO units an hour, forever —
        strictly worse than the failure being fixed, which banked five.
        """
        # Unit 1 is the repeat offender; everything after it is ordinary.
        costs = [SPECIMEN_RUNAWAY_MS] + [SPECIMEN_UNIT_MS] * 6
        runner, db = loop_env(
            window_ms=900_000,
            costs=costs,
            prior_unit_ms=SPECIMEN_UNIT_MS,
            buckets=7,
        )
        await _run(runner, db)
        assert db.cancelled == 1
        assert db.completed >= 5, "the beat must get past the blocker, not stop on it"

    @pytest.mark.asyncio
    async def test_a_beat_stops_after_its_cancellation_budget_and_says_so_by_name(
        self, loop_env
    ):
        """A third cancellation means the BEAT is slow, not one unit.

        Recorded under ``window_stop:units_cancelling`` rather than folded into
        ``window_stop:deadline``: "stopped because units keep cancelling" and
        "stopped because the window ran out" are different diagnoses, and an
        absent distinction reads as the more comfortable one (gotcha #53).
        """
        costs = [SPECIMEN_RUNAWAY_MS] * 6
        runner, db = loop_env(
            window_ms=SPECIMEN_WINDOW_MS,
            costs=costs,
            prior_unit_ms=SPECIMEN_UNIT_MS,
            buckets=8,
        )
        await _run(runner, db)
        assert db.cancelled == STAGED_UNIT_MAX_CANCELLATIONS
        assert "staged:window_stop:units_cancelling" in runner.ledger.stages
        assert runner.ledger.stages["staged:units_cancelled"] == STAGED_UNIT_MAX_CANCELLATIONS

    @pytest.mark.asyncio
    async def test_the_cancellation_budget_is_a_fraction_of_the_beat_not_all_of_it(self):
        """Two cancellations cost at most eight units of an ~18-unit beat."""
        worst_case_ms = (
            STAGED_UNIT_MAX_CANCELLATIONS * STAGED_UNIT_OVERRUN_FACTOR * SPECIMEN_UNIT_MS
        )
        assert worst_case_ms < SPECIMEN_WINDOW_MS / 2

    @pytest.mark.asyncio
    async def test_the_poisoned_transaction_is_rolled_back_before_the_beat_continues(
        self, loop_env
    ):
        """Gotcha #6: the writes after this point must not run on a dead session."""
        runner, db = loop_env(
            window_ms=400_000,
            costs=[SPECIMEN_RUNAWAY_MS],
            prior_unit_ms=SPECIMEN_UNIT_MS,
            buckets=4,
        )
        await _run(runner, db)
        assert db.rolled_back == 1

    @pytest.mark.asyncio
    async def test_a_cancelled_unit_loses_only_itself(self, loop_env):
        """Everything banked before the cancellation is still banked."""
        runner, db = loop_env(
            window_ms=600_000,
            costs=[SPECIMEN_UNIT_MS] * 3 + [SPECIMEN_RUNAWAY_MS],
            prior_unit_ms=SPECIMEN_UNIT_MS,
            buckets=8,
        )
        await _run(runner, db)
        assert loop_env.saved[:3] == [1, 2, 3]

    @pytest.mark.asyncio
    async def test_a_genuine_error_is_still_raised_and_never_swallowed(self, loop_env):
        """The containment is scoped to OUR backstop and nothing else.

        A catch-all here would convert every database fault into a quiet partial,
        which is the exact shape of gotcha #45 — a scheduled read that dies
        silently for months.
        """
        runner, db = loop_env(
            window_ms=600_000,
            costs=[SPECIMEN_UNIT_MS],
            prior_unit_ms=SPECIMEN_UNIT_MS,
            buckets=4,
        )

        async def _boom(_sql, _params=None):
            raise RuntimeError("relation \"futures_markets\" does not exist")

        original = db.execute
        calls = {"n": 0}

        async def _execute(sql, params=None):
            calls["n"] += 1
            if calls["n"] == 1:
                return await original(sql, params)
            return await _boom(sql, params)

        db.execute = _execute
        with pytest.raises(RuntimeError, match="does not exist"):
            await _run(runner, db)

    @pytest.mark.asyncio
    async def test_the_convergence_projection_survives_the_cancellation(self, loop_env):
        """A throw skipped it. CAL-P038 fixed that for the window stop; this is
        the same fix for the cancellation stop, and it is why the ledger can now
        say ``beats_to_publish`` on a beat that hit one."""
        runner, db = loop_env(
            window_ms=600_000,
            costs=[SPECIMEN_UNIT_MS] * 2 + [SPECIMEN_RUNAWAY_MS],
            prior_unit_ms=SPECIMEN_UNIT_MS,
            buckets=8,
        )
        await _run(runner, db)
        assert "staged:beats_to_publish" in runner.ledger.stages
        # The cancelled unit is not counted as banked — it is counted as cancelled.
        assert runner.ledger.stages["staged:units_this_beat"] == db.completed
        assert runner.ledger.stages["staged:units_cancelled"] == 1


class TestCarriedCostIsRecorded:
    @pytest.mark.asyncio
    async def test_the_carried_cost_the_fence_used_is_on_the_ledger(self, loop_env):
        runner, db = loop_env(
            window_ms=600_000,
            costs=[SPECIMEN_UNIT_MS] * 4,
            prior_unit_ms=SPECIMEN_UNIT_MS,
            buckets=4,
        )
        await _run(runner, db)
        assert runner.ledger.stages.get("staged:prior_unit_ms") == SPECIMEN_UNIT_MS

    @pytest.mark.asyncio
    async def test_an_absent_carried_cost_is_declared_not_rendered_as_zero(self, loop_env):
        """Ruling 075, second clause, inside the instrument that enforces it."""
        runner, db = loop_env(
            window_ms=600_000,
            costs=[SPECIMEN_UNIT_MS] * 4,
            prior_unit_ms=None,
            buckets=4,
        )
        await _run(runner, db)
        assert runner.ledger.stages.get("staged:prior_unit_reason:unmeasured") == 1
        assert "staged:prior_unit_ms" not in runner.ledger.stages


class TestTheBankSurvivesThisChange:
    """The property that decides whether this fix helps or hurts.

    ``_main_input_fingerprint`` hashes the SOURCE of four functions, and any move
    invalidates the staged cursor — CAL-P024 watched a deploy cost a build all
    ten units it had banked, and the rebuild bank this change is meant to help is
    13/128 as of 2026-08-20T20:00Z. A fix for a slow build that resets the build
    is not a fix.

    Measured, not assumed: this window computed the digest on HEAD and on the
    changed tree and got ``b65faaacdc240b3b256934fcad528db1`` both times. The
    tests below are what keeps that true for the next edit.
    """

    @staticmethod
    def _hashed_source() -> str:
        import inspect

        return (
            inspect.getsource(pc.compute_calibration_payload)
            + inspect.getsource(pc._calibration_population_ctes)
            + inspect.getsource(pc._virtual_market_ctes)
            + inspect.getsource(pc._main_futures_sql)
        )

    def test_none_of_the_changed_functions_is_defined_inside_the_hashed_source(self):
        """``getsource`` returns a function's own text, never its callees'.

        That is the rule ``_main_input_fingerprint``'s own docstring states, and
        it is what makes this change cursor-safe: every line CAL-P081 moved lives
        in a function that is not on the hash list.
        """
        hashed = self._hashed_source()
        for name in (
            "_unit_fits_in_window",
            "_run_staged_futures",
            "apply_unit_statement_timeout",
            "statement_timeout_for_unit",
            "measured_unit_ms",
        ):
            assert f"def {name}" not in hashed

    def test_the_one_hashed_line_that_mentions_the_loop_is_its_unchanged_call_site(self):
        """``compute_calibration_payload`` CALLS the loop, so one line of the
        hash does name it. Pinned verbatim: change this call's shape and the
        digest moves and the bank is discarded, which must be a deliberate act
        rather than a side effect of editing the loop's internals."""
        hashed = self._hashed_source()
        mentions = [
            line.strip()
            for line in hashed.splitlines()
            if "_run_staged_futures" in line and not line.strip().startswith("#")
        ]
        assert mentions == ["rows = await _run_staged_futures(db, runner, _main_futures_sql)"]

    def test_the_fingerprint_is_stable_across_repeated_reads(self):
        assert pc._main_input_fingerprint() == pc._main_input_fingerprint()


class TestTimeoutPredicateIsShared:
    """One predicate, two callers — see ``is_statement_timeout``'s docstring."""

    def test_the_loop_and_the_terminal_classifier_agree(self):
        exc = _StatementCancelled("canceling statement due to statement timeout")
        assert cmb.is_statement_timeout(exc) is True

    def test_an_ordinary_error_is_not_a_timeout(self):
        assert cmb.is_statement_timeout(RuntimeError("connection reset")) is False

    def test_the_asyncpg_class_name_alone_is_enough(self):
        class QueryCanceledError(Exception):
            pass

        assert cmb.is_statement_timeout(QueryCanceledError("cancelled")) is True
