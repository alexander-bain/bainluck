"""CAL-P1027 (#1597): the carried unit cost outlived the build it described.

THE SPECIMEN, read off production's own ledger at 2026-09-06 05:19:04Z
(``calibration:main:phase_ledger``)::

    unit_costs.futures   {'unit_ms': 928347, 'units_done': 6, 'units_total': 128}
    staged:units_banked                0      <- the DURABLE cursor, this beat
    staged:cursor_invalidate           fired  (population_version_changed)
    staged:units_this_beat             0
    staged:window_stop:unit_too_large  fired
    staged:window_left_ms              1,136,180
    staged:prior_unit_ms               928,347

Two facts on one row that cannot both be true. The level says six units are
banked at 928,347 ms each; the cursor it was measured against holds zero.

The level is the sole input to ``_unit_fits_in_window`` on the first unit of a
beat, and ``928,347 * 1.25 = 1,160,434`` against ``1,136,180`` of window is
short by 2.1%. So no unit starts. ``unit_ms`` refreshes only when a unit
COMPLETES, and the carry preserves the level exactly, so the next beat re-derives
the same arithmetic from the same numbers and refuses again — for every beat the
build has left. **The gate is fed by a measurement that only success refreshes,
so it can never reopen from the inside.** Its tell is in the specimen above: a
stop reason firing with 18.9 minutes of budget unused.

``precompute_calibration.py`` is frozen (ruling 009) and the fence lives there,
so nothing in this file touches it — and nothing needs to. The fence already
documents the right behaviour for having no measurement ("a beat must be allowed
to attempt one unit or the build can never progress"); it was simply being handed
a measurement that had stopped being one. The repair is in the carry, in
``calibration_main_build``, and it is two sentences:

* ``units_done`` is re-stamped from THIS beat's cursor, because that is what the
  field means where it is written (:func:`_unit_costs_from` takes it from
  ``staged:units_banked``). A level whose denominator is honestly zero is
  withdrawn by ``measured_unit_ms``'s own existing guard.
* ``unit_ms`` is withdrawn when the level refused every unit of the beat — the
  state in which it is blocking the only observation that could revise it.

Revert either half and the beats below reproduce production exactly: zero units
admitted, forever, on numbers that never move.
"""

from __future__ import annotations

import pytest

from app.tasks import calibration_main_build as cmb
from app.tasks import precompute_calibration as pc
from app.utils.calibration_phase_ledger import PHASE_FUTURES, PhaseBudget, PhaseLedger, PhasePlan

# -- The production numbers. Nothing below invents one. ------------------------
PROD_UNIT_MS = 928_347
PROD_WINDOW_LEFT_MS = 1_136_180
PROD_UNITS_DONE = 6
PROD_UNITS_TOTAL = 128


def _plan(*, unit_ms: int | None, units_done: int, unit_ms_worst: int | None = None) -> PhasePlan:
    return PhasePlan(
        budgets=(
            PhaseBudget(
                name=PHASE_FUTURES,
                required=True,
                budget_ms=1_267_625,
                statement_timeout_ms=1_237_625,
                measured_input=True,
                observations=10,
                unit_ms=unit_ms,
                unit_ms_worst=unit_ms_worst,
                units_total=PROD_UNITS_TOTAL,
                units_done=units_done,
            ),
        ),
        soft_limit_ms=1_500_000,
        cleanup_margin_ms=120_000,
    )


def _ledger_for(plan: PhasePlan) -> PhaseLedger:
    """A ledger over ``plan``, which is the only part of it these reads use."""
    return PhaseLedger(
        plan=plan,
        population_version="q269",
        owner="test:1",
        generation=1,
        input_fingerprint="fp",
    )


def _runner(
    *,
    completed: tuple[int, ...] = (),
    cancelled: tuple[int, ...] = (),
    unit_too_large: bool = False,
) -> cmb.PhaseRunner:
    """A runner in the state one beat leaves behind.

    ``staged:units_banked`` is deliberately NOT set here — the real
    ``_record_staged_convergence`` sets it from the faked cursor read, so the
    re-stamp under test is driven by production's own reader rather than by a
    number this file wrote.
    """
    runner = cmb.PhaseRunner(
        plan=_plan(unit_ms=PROD_UNIT_MS, units_done=PROD_UNITS_DONE),
        checkpoint=cmb.new_main_checkpoint(
            version="q269", fingerprint="fp", owner="test:1", generation=1
        ),
        checkpoint_action="fresh",
        owner="test:1",
        generation=1,
        fingerprint="fp",
        population_version="q269",
    )
    for ms in completed:
        runner.ledger.record_stage_outcome(cmb.STAGED_UNIT_STAGE, ms, completed=True)
    for ms in cancelled:
        runner.ledger.record_stage_outcome(cmb.STAGED_UNIT_STAGE, ms, completed=False)
    if unit_too_large:
        runner.ledger.record_stage("staged:window_stop:unit_too_large", 0)
    return runner


def _durable(monkeypatch, *, cursor_units: int | None):
    """Fake the two durable reads APART, which the shared-payload fakes cannot.

    ``save_phase_ledger`` reads two different artifacts and the re-stamp is
    exactly the disagreement between them, so a fake that serves one payload to
    both identities would make the two agree by construction and could never see
    the defect. ``cursor_units=None`` means the cursor read fails.
    """
    from app.services import durable_snapshots
    from app.utils.calibration_staged_futures import STAGED_FUTURES_SCHEMA
    from app.utils.durable_state import DurableEnvelope, EnvelopeRead

    written: dict = {}

    async def fake_publish(envelope):
        written["payload"] = envelope.payload
        return {"status": "ok"}

    def _envelope(identity, version, payload):
        return EnvelopeRead(
            status="ok",
            tier="durable",
            envelope=DurableEnvelope.build(
                identity=identity,
                schema_version=version,
                payload=payload,
                complete=True,
                source=cmb.MAIN_BUILD_TASK,
            ),
        )

    async def fake_read(identity, *, expected_version=None, max_age_s=None):
        if identity == cmb.STAGED_FUTURES_IDENTITY:
            if cursor_units is None:
                return EnvelopeRead(status="missing", tier="durable")
            return _envelope(
                identity,
                STAGED_FUTURES_SCHEMA,
                {"committed_units": [f"u{i}" for i in range(cursor_units)]},
            )
        if "payload" not in written:
            return EnvelopeRead(status="missing", tier="durable")
        return _envelope(identity, expected_version or "v1", written["payload"])

    monkeypatch.setattr(durable_snapshots, "publish_snapshot_standalone", fake_publish)
    monkeypatch.setattr(durable_snapshots, "read_snapshot_standalone", fake_read)
    return written


async def _bank_the_production_level(monkeypatch, written):
    """Put production's level on the durable row, the way production got it."""
    seed = _runner(completed=(PROD_UNIT_MS,))
    assert await cmb.save_phase_ledger(seed) == "ok"
    return written["payload"]["unit_costs"]


# =============================================================================
# 1. THE LATCH — reproduce it, then show the carry is what holds it shut
# =============================================================================


class TestTheLatch:
    def test_the_fence_refuses_production_numbers(self):
        """The premise. Not a claim about our repair — a claim about the state
        the repair exists to end, replayed through the real predicate."""
        assert (
            pc._unit_fits_in_window(PROD_WINDOW_LEFT_MS, 0.0, float(PROD_UNIT_MS)) is False
        )

    def test_and_it_reopens_the_moment_the_level_stops_being_quoted(self):
        """The control for the test above: same window, same beat, no carried
        quote. If this were False the repair would be pointless and the fence
        would need a change in a file ruling 009 forbids us to touch."""
        assert pc._unit_fits_in_window(PROD_WINDOW_LEFT_MS, 0.0, 0.0) is True

    def test_a_level_with_no_completed_units_behind_it_is_not_quoted(self):
        """``measured_unit_ms``'s own guard, which the re-stamp relies on and
        does not re-implement: a mean over zero completed units is not a
        measurement. This is why an honest ``units_done`` is sufficient."""
        quoted = _ledger_for(_plan(unit_ms=PROD_UNIT_MS, units_done=PROD_UNITS_DONE))
        withdrawn = _ledger_for(_plan(unit_ms=PROD_UNIT_MS, units_done=0))
        assert quoted.measured_unit_ms(PHASE_FUTURES) == PROD_UNIT_MS
        assert withdrawn.measured_unit_ms(PHASE_FUTURES) is None


# =============================================================================
# 2. THE RE-STAMP — units_done means the cursor, so it is read from the cursor
# =============================================================================


class TestTheReStamp:
    async def test_a_discarded_cursor_takes_the_level_down_with_it(self, monkeypatch):
        """Production's row, exactly: level says six banked, cursor holds zero.

        The beat here runs no unit and does NOT reach the fence (no
        ``unit_too_large``), so the withdrawal in section 3 cannot be what
        rescues it. Only the re-stamp can.
        """
        written = _durable(monkeypatch, cursor_units=1)
        banked = await _bank_the_production_level(monkeypatch, written)
        assert banked[PHASE_FUTURES]["unit_ms"] == PROD_UNIT_MS

        _durable(monkeypatch, cursor_units=0)
        # The seed row has to survive the re-fake or the carry has nothing to
        # carry; the fresh `written` is a different dict.
        monkeypatch.setattr(cmb, "_unit_costs_from", lambda runner: {})
        carried = cmb._carry_unit_costs(
            _runner_with_banked(0), {PHASE_FUTURES: dict(banked[PHASE_FUTURES])}
        )
        assert carried[PHASE_FUTURES]["units_done"] == 0
        assert carried[PHASE_FUTURES]["unit_ms"] == PROD_UNIT_MS

        ledger = _ledger_for(_plan(unit_ms=PROD_UNIT_MS, units_done=0))
        assert ledger.measured_unit_ms(PHASE_FUTURES) is None

    async def test_the_whole_beat_end_to_end_hands_the_next_plan_an_open_fence(
        self, monkeypatch
    ):
        """The round trip, driven by the real ``save_phase_ledger`` and the real
        ``derive_plan``. This is the test that would have caught it: everything
        below the payload was already correct and the payload was the liar."""
        written = _durable(monkeypatch, cursor_units=6)
        await _bank_the_production_level(monkeypatch, written)

        # The next beat: cursor invalidated to zero, no unit runs, fence fires.
        assert await cmb.save_phase_ledger(_runner(unit_too_large=True)) == "ok"

        _h, _f, unit_costs = await cmb.load_phase_measurements()
        plan = cmb.derive_plan({PHASE_FUTURES: [1_000]}, unit_costs=unit_costs)
        prior = _ledger_for(plan).measured_unit_ms(PHASE_FUTURES)
        assert prior is None
        assert pc._unit_fits_in_window(PROD_WINDOW_LEFT_MS, 0.0, float(prior or 0.0)) is True

    async def test_an_unreadable_cursor_carries_the_level_and_says_so(self, monkeypatch):
        """Ruling 075. Re-stamping from a number we do not have would be
        inventing one, and silence would read as freshly confirmed."""
        written = _durable(monkeypatch, cursor_units=6)
        banked = await _bank_the_production_level(monkeypatch, written)

        runner = _runner()
        carried = cmb._carry_unit_costs(runner, {PHASE_FUTURES: dict(banked[PHASE_FUTURES])})
        assert carried[PHASE_FUTURES]["units_done"] == PROD_UNITS_DONE
        assert runner.ledger.stages["staged:unit_cost_reason:units_done_unverified"] == 1


def _runner_with_banked(banked: int) -> cmb.PhaseRunner:
    runner = _runner()
    runner.ledger.record_gauge("staged:units_banked", banked)
    return runner


# =============================================================================
# 3. THE WITHDRAWAL — a level that blocks its own refresh has stopped measuring
# =============================================================================


class TestTheWithdrawal:
    def test_it_fires_on_the_production_beat(self):
        assert _self_blocked(_runner(unit_too_large=True)) is True

    def test_it_does_not_fire_on_a_productive_beat(self):
        """The control that keeps the fence a fence. Units ran, the window
        filled, the next one would not fit — the ordinary, correct end of a good
        beat, and the level that produced it is still evidence."""
        beat = _runner(completed=(72_000, 76_000), unit_too_large=True)
        assert _self_blocked(beat) is False
        carried = cmb._carry_unit_costs(
            beat, {PHASE_FUTURES: {"unit_ms": 74_000, "units_done": 8, "units_total": 128}}
        )
        assert carried[PHASE_FUTURES]["unit_ms"] == 74_000

    def test_it_does_not_fire_on_a_deferred_rebuild(self):
        """D45(A) hands the loop an empty iterable, so a publish-first beat runs
        zero units without ever consulting the fence. Withdrawing there would
        drop a good level for no reason, every time the reorder does its job."""
        assert _self_blocked(_runner()) is False

    def test_a_cancelled_unit_is_evidence_and_blocks_the_withdrawal(self):
        """A unit that started and was cancelled at its own bound reached the
        fence and got past it. The level admitted something; it is not blocking
        its own refresh, and the next beat's own worst observation will speak."""
        assert _self_blocked(_runner(cancelled=(900_000,), unit_too_large=True)) is False

    async def test_the_withdrawal_leaves_the_unit_bound_standing(self, monkeypatch):
        """The safety argument, tested rather than asserted. Withdrawing the
        mean must not leave the admitted unit unbounded: CAL-P163's worst-unit
        ring is untouched, so ``statement_timeout_for_unit`` still has a
        measured basis and the unit still cannot outlive the beat."""
        written = _durable(monkeypatch, cursor_units=6)
        await _bank_the_production_level(monkeypatch, written)
        assert await cmb.save_phase_ledger(_runner(unit_too_large=True)) == "ok"

        assert PHASE_FUTURES not in written["payload"].get("unit_costs", {})
        assert written["payload"][cmb.UNIT_WORST_HISTORY_KEY][PHASE_FUTURES] == [PROD_UNIT_MS]

        _h, _f, unit_costs = await cmb.load_phase_measurements()
        plan = cmb.derive_plan({PHASE_FUTURES: [1_000]}, unit_costs=unit_costs)
        ledger = _ledger_for(plan)
        assert ledger.measured_unit_ms(PHASE_FUTURES) is None
        assert ledger.measured_unit_worst_ms(PHASE_FUTURES) == PROD_UNIT_MS

    async def test_a_measured_beat_still_overwrites_the_carry(self, monkeypatch):
        """CAL-P067 unchanged: a beat that measured a cost writes it, and the
        carry never gets consulted. The repair may only touch the carried case."""
        written = _durable(monkeypatch, cursor_units=6)
        await _bank_the_production_level(monkeypatch, written)
        assert await cmb.save_phase_ledger(_runner(completed=(70_000,))) == "ok"
        assert written["payload"]["unit_costs"][PHASE_FUTURES]["unit_ms"] == 70_000


def _self_blocked(runner: cmb.PhaseRunner) -> bool:
    return cmb._level_self_blocked(runner)


# =============================================================================
# 4. THE LOOP HAS AN EXIT NOW — the property the whole queue is for
# =============================================================================


class TestTheLoopTerminates:
    async def test_twenty_four_beats_no_longer_all_refuse(self, monkeypatch):
        """The counterpart to the proof script: replay the same twenty-four
        identical beats through the real persistence layer. Before the repair
        every one of them carried 928,347 forward and admitted nothing; after
        it, the first refusal is the last one.
        """
        written = _durable(monkeypatch, cursor_units=6)
        await _bank_the_production_level(monkeypatch, written)

        admitted = 0
        for _ in range(24):
            _h, _f, unit_costs = await cmb.load_phase_measurements()
            plan = cmb.derive_plan({PHASE_FUTURES: [1_000]}, unit_costs=unit_costs)
            prior = float(_ledger_for(plan).measured_unit_ms(PHASE_FUTURES) or 0.0)
            if pc._unit_fits_in_window(PROD_WINDOW_LEFT_MS, 0.0, prior):
                admitted += 1
                # An admitted unit that completes re-measures the level, which
                # is the whole point; this beat is the one that never happened.
                break
            assert await cmb.save_phase_ledger(_runner(unit_too_large=True)) == "ok"

        assert admitted == 1
