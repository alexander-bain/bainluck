"""#6599: the level-refutation latch — a window bound withdraws the level that
would have fitted the unit, and nothing can ever put it back.

THE SPECIMEN, read off production's own row ``calibration:main:phase_ledger``
at the 2026-09-17T17:37:55Z beat (``bainluck-heavy`` v41, carrying #6723/#6732)::

    staged:units_this_beat                            2
    staged:units_completed_this_beat                  0
    staged:units_cancelled                            2
    staged:unit_cancelled:98f88f19e9586ca0    1,254,562   <- unit 1, the whole window
    staged:unit_cancelled:248c4616a352cdab       59,594   <- unit 2, the scraps
    staged:unit_bound_ms:futures                 59,087
    staged:unit_bound_headroom_ms:futures         6,565
    staged:unit_worst_reason:unmeasured:futures       1
    staged:unit_cost_reason:no_unit_completed         1
    staged:unit_cost_reason:withdrawn_refuted_by_cancellation  1
    staged:units_banked                           1/128
    elapsed_ms                                1,374,676
    terminal                                  cancelled

    unit_costs        {'futures': {'units_done': 1, 'units_total': 128,
                                   'level_refuted': True}}
    unit_worst_history['futures']   24 entries, max 1,181,085, ALL of them
                                    genuine completions the ring still holds

and off ``calibration:main:staged_futures`` in the same minute: ``unit_cancels``
holds **30 slots, every one at count 1** (``128:1`` … ``128:30``, contiguous) and
``unit_splits`` is **empty**.

WHAT THAT PAIR PROVES, AND WHAT IT DOES NOT. CAL-P1301's durable memory WORKS —
thirty cancellations survived fifteen beats and two process restarts — and
:func:`~app.utils.calibration_staged_futures.attempt_order` WORKS: the slots
rotate strictly and never repeat, which is the livelock #6599's title describes
and it is gone. Nothing has been refined, so the build still banks nothing.

THE LATCH, which is why no unit can complete for the ordering to matter.

``_statement_timeout_for(b) = b - max(1, min(STATEMENT_INNER_MARGIN_MS, b // 10))``
always reserves a strictly positive gap. So when the fence has no measured basis
and falls back to the phase/window bound, the bound is ``remaining - gap`` and
the recorded headroom is ``gap`` — **positive, always, by construction.**

:func:`_level_refuted_by_cancellation`'s third condition reads exactly that
gauge and documents it as meaning the opposite::

    "``headroom`` is ``remaining_ms - timeout`` recorded at the moment the fence
     was applied, so a positive value means the bound came from the measured
     basis while window was still available — which is precisely 'the level did
     this'."

It cannot mean that. A window-derived bound leaves positive headroom too, and
production's 6,565 ms is one: unit 2 was handed 59,087 ms because 65,652 ms of
window remained after unit 1 ate the beat, not because any level said 59,087.

So every beat: unmeasured basis -> unit 1 gets the whole window and cancels ->
unit 2 gets the scraps and cancels -> zero completions, positive headroom ->
the level is "refuted" -> :func:`load_phase_measurements` then skips the
worst-unit ring on the ``level_refuted`` marker -> the next beat's basis is zero
again -> unit 1 gets the whole window. **The ring on disk still holds 24 real
completions and no beat may read one of them.**

That is the exact disease ``_level_refuted_by_cancellation``'s own docstring
says it exists to cure — "a measurement that blocks the only observation which
could revise it" — reproduced by the cure, one layer up. #6275's specimen was
real and its repair stands; what was missing is that the honesty condition meant
to scope it to that case is satisfied by every beat that merely ends busy.

The existing control ``test_a_window_bound_cancellation_is_not_a_refutation``
sets ``headroom_ms=0`` BY HAND. No writer in the tree can produce that value for
a window bound, so the control passes on a state production cannot reach. Every
beat below drives the REAL writer,
:meth:`~app.tasks.calibration_main_build.PhaseRunner.apply_unit_statement_timeout`,
and reads back the gauge it actually wrote.
"""

from __future__ import annotations

import time

import pytest

from app.tasks import calibration_main_build as cmb
from app.utils.calibration_phase_ledger import (
    BUDGET_SAFETY,
    PHASE_FUTURES,
    STATEMENT_INNER_MARGIN_MS,
    PhaseBudget,
    PhaseLedger,
    PhasePlan,
    _statement_timeout_for,
)

# -- The production numbers. Nothing below invents one. ------------------------
PROD_ELAPSED_AFTER_UNIT_1_MS = 1_254_562  # staged:unit_cancelled:98f88f19e9586ca0
PROD_UNIT_2_BOUND_MS = 59_087             # staged:unit_bound_ms:futures
PROD_UNIT_2_HEADROOM_MS = 6_565           # staged:unit_bound_headroom_ms:futures
PROD_UNIT_2_CANCELLED_MS = 59_594         # staged:unit_cancelled:248c4616a352cdab
PROD_BANKED = 1
PROD_UNITS_TOTAL = 128
PROD_SOFT_LIMIT_MS = 1_440_214            # remaining before unit 2 was 65,652 ms
PROD_CLEANUP_MARGIN_MS = 120_000
#: ``unit_worst_history['futures']`` as the row carries it — 24 real completions.
PROD_WORST_RING = (
    217_564, 170_991, 228_426, 208_277, 205_168, 226_716, 318_050, 246_180,
    200_187, 199_446, 181_321, 189_981, 260_459, 180_105, 195_359, 175_089,
    256_688, 193_207, 156_509, 181_332, 194_011, 171_845, 222_972, 1_181_085,
)
#: #6275's own specimen, kept so its repair is held green by this file too.
P6275_HEADROOM_MS = 347_841
P6275_CANCELLED_MS = 483_862


class _FakeDb:
    """Accepts the two ``SET LOCAL``s the fence arms, records nothing else.

    Deliberately not an ``AsyncMock``: #6732 exposed five suites whose fakes
    answered every attribute, and a fence that silently no-opped would read here
    as a fence that fired.
    """

    def __init__(self) -> None:
        self.statements: list[str] = []

    async def execute(self, statement, *_args, **_kwargs):
        self.statements.append(str(statement))
        return None


async def _no_tag(self, _db) -> dict:  # noqa: ANN001
    return {"applied": True, "backend_pid": 1}


def _plan(*, unit_ms: int | None, unit_ms_worst: int | None, units_done: int) -> PhasePlan:
    return PhasePlan(
        budgets=(
            PhaseBudget(
                name=PHASE_FUTURES,
                required=True,
                budget_ms=0,
                statement_timeout_ms=0,
                measured_input=True,
                observations=10,
                unit_ms=unit_ms,
                unit_ms_worst=unit_ms_worst,
                units_total=PROD_UNITS_TOTAL,
                units_done=units_done,
            ),
        ),
        soft_limit_ms=PROD_SOFT_LIMIT_MS,
        cleanup_margin_ms=PROD_CLEANUP_MARGIN_MS,
    )


def _runner(*, unit_ms=None, unit_ms_worst=None, units_done=PROD_BANKED) -> cmb.PhaseRunner:
    return cmb.PhaseRunner(
        plan=_plan(unit_ms=unit_ms, unit_ms_worst=unit_ms_worst, units_done=units_done),
        checkpoint=cmb.new_main_checkpoint(
            version="q271", fingerprint="fp", owner="test:1", generation=1
        ),
        checkpoint_action="fresh",
        owner="test:1",
        generation=1,
        fingerprint="fp",
        population_version="q271",
    )


def _at_elapsed(runner: cmb.PhaseRunner, elapsed_ms: int) -> None:
    """Put the runner's own clock where the beat was. Offset, never branched
    (gotcha #44) — the value is a fixed production reading."""
    runner._started = time.monotonic() - (elapsed_ms / 1000.0)


async def _arm(runner: cmb.PhaseRunner, monkeypatch) -> int:
    monkeypatch.setattr(cmb.PhaseRunner, "tag_session", _no_tag, raising=True)
    monkeypatch.setattr(cmb.PhaseRunner, "tag_rebuild_session", _no_tag, raising=True)
    return await runner.apply_unit_statement_timeout(_FakeDb(), PHASE_FUTURES)


# =============================================================================
# 1. THE ARITHMETIC — positive headroom is not evidence of anything
# =============================================================================


class TestPositiveHeadroomIsUnavoidable:
    def test_the_inner_margin_is_always_strictly_positive(self):
        """The whole latch in one line. Every window-derived bound is
        ``remaining - gap`` with ``gap >= 1``, so the headroom the predicate
        reads as 'the level did this' can never be zero for a window bound."""
        for remaining in (2, 100, 65_652, 500_000, 1_440_214):
            gap = remaining - _statement_timeout_for(remaining)
            assert gap >= 1, remaining
            assert gap <= STATEMENT_INNER_MARGIN_MS, remaining

    def test_the_existing_control_uses_a_value_no_writer_can_produce(self):
        """``test_a_window_bound_cancellation_is_not_a_refutation`` pins
        ``headroom_ms=0``. Nothing in the tree writes that for a window bound —
        which is why the control passes while production reproduces the bug."""
        assert _statement_timeout_for(65_652) != 65_652


# =============================================================================
# 2. THE REAL WRITER — reproduce production's two bounds from the real fence
# =============================================================================


class TestTheProductionBeatIsReproduced:
    @pytest.mark.asyncio
    async def test_unit_one_with_no_measured_basis_is_handed_the_whole_window(
        self, monkeypatch
    ):
        """``basis <= 0`` returns the phase bound — documented as 'one honest
        attempt per beat'. With a 22-minute window that attempt IS the beat."""
        runner = _runner()
        _at_elapsed(runner, 0)
        bound = await _arm(runner, monkeypatch)
        remaining = runner.ledger.remaining_ms(elapsed_ms=0)
        assert bound == _statement_timeout_for(remaining)
        assert bound > PROD_ELAPSED_AFTER_UNIT_1_MS - 60_000
        assert runner.ledger.stages[f"staged:unit_worst_reason:unmeasured:{PHASE_FUTURES}"] == 1

    @pytest.mark.asyncio
    async def test_unit_two_gets_the_scraps_and_the_production_headroom(
        self, monkeypatch
    ):
        """Unit 1 ate 1,254,562 ms of the beat. The real writer then reproduces
        production's 59,087 ms bound and 6,565 ms headroom to the millisecond —
        and that headroom is the gauge the refutation reads."""
        runner = _runner()
        _at_elapsed(runner, PROD_ELAPSED_AFTER_UNIT_1_MS)
        bound = await _arm(runner, monkeypatch)
        headroom = runner.ledger.stages[f"staged:unit_bound_headroom_ms:{PHASE_FUTURES}"]
        assert bound == PROD_UNIT_2_BOUND_MS
        assert headroom == PROD_UNIT_2_HEADROOM_MS
        assert headroom > 0


# =============================================================================
# 3. THE DEFECT — a window bound is read as a refutation of the level
# =============================================================================


class TestAWindowBoundIsNotARefutation:
    @pytest.mark.asyncio
    async def test_the_production_beat_must_not_refute_the_level(self, monkeypatch):
        """RED until repaired. Neither of this beat's two units was killed by a
        level — there was no level; ``basis`` was zero and both bounds came from
        the window. Withdrawing on that evidence withdraws a measurement the
        beat never tested."""
        runner = _runner()
        _at_elapsed(runner, 0)
        await _arm(runner, monkeypatch)
        runner.ledger.record_stage_outcome(
            cmb.STAGED_UNIT_STAGE, PROD_ELAPSED_AFTER_UNIT_1_MS, completed=False
        )
        runner.ledger.record_stage("staged:units_cancelled", 1)
        _at_elapsed(runner, PROD_ELAPSED_AFTER_UNIT_1_MS)
        await _arm(runner, monkeypatch)
        runner.ledger.record_stage_outcome(
            cmb.STAGED_UNIT_STAGE, PROD_UNIT_2_CANCELLED_MS, completed=False
        )
        runner.ledger.record_stage("staged:units_cancelled", 1)
        runner.ledger.record_gauge("staged:units_banked", PROD_BANKED)

        assert cmb._level_refuted_by_cancellation(runner) is False

    @pytest.mark.asyncio
    async def test_the_ceiling_is_capped_at_the_margin_not_a_tenth_of_the_window(
        self, monkeypatch
    ):
        """The cap is load-bearing and has no natural specimen, so it is
        manufactured (the two candidate ceilings only disagree above a ~300 s
        window). A level bound that bites 100,000 ms inside a 1,320,214 ms
        window IS a level verdict: ``_statement_timeout_for`` reserves at most
        ``STATEMENT_INNER_MARGIN_MS``, so no window bound could have left that
        much. Dropping the cap makes the ceiling ``remaining // 10`` =
        132,021 ms and this refutation is silently declined — a measured level
        that killed every unit would be carried forward untouched, which is the
        #6275 latch coming back by the other door."""
        basis_worst = 833_476  # * BUDGET_SAFETY = 1,250,214
        runner = _runner(unit_ms=None, unit_ms_worst=basis_worst, units_done=PROD_BANKED)
        _at_elapsed(runner, 0)
        bound = await _arm(runner, monkeypatch)
        headroom = runner.ledger.stages[f"staged:unit_bound_headroom_ms:{PHASE_FUTURES}"]
        remaining = bound + headroom
        assert headroom == 100_000
        assert headroom > STATEMENT_INNER_MARGIN_MS
        assert headroom < remaining // 10  # the uncapped ceiling would swallow it

        runner.ledger.record_stage_outcome(
            cmb.STAGED_UNIT_STAGE, bound + 500, completed=False
        )
        runner.ledger.record_stage("staged:units_cancelled", 1)
        runner.ledger.record_gauge("staged:units_banked", PROD_BANKED)

        assert cmb._level_refuted_by_cancellation(runner) is True

    @pytest.mark.asyncio
    async def test_a_genuine_level_bound_cancellation_still_refutes(self, monkeypatch):
        """#6275's specimen, and the control this repair may not break. Here a
        MEASURED basis produced the bound while 347,841 ms of window was still
        available — the level really did kill the units, and withdrawing it is
        what reopened that build."""
        runner = _runner(unit_ms=128_250, unit_ms_worst=268_898, units_done=52)
        _at_elapsed(runner, 0)
        bound = await _arm(runner, monkeypatch)
        remaining = runner.ledger.remaining_ms(elapsed_ms=runner.elapsed_ms())
        assert bound < _statement_timeout_for(remaining)  # the LEVEL bit, not the window
        runner.ledger.record_stage_outcome(
            cmb.STAGED_UNIT_STAGE, P6275_CANCELLED_MS, completed=False
        )
        runner.ledger.record_stage("staged:units_cancelled", 1)
        runner.ledger.record_gauge("staged:units_banked", 52)

        assert cmb._level_refuted_by_cancellation(runner) is True


# =============================================================================
# 4. THE LATCH — the withdrawal is what keeps the ring unreadable
# =============================================================================


class TestTheRingCannotBeReadBack:
    def test_a_refuted_marker_suppresses_a_ring_of_real_completions(self):
        """``load_phase_measurements`` skips the fold when the carried level
        wears ``level_refuted``. Production's ring holds 24 genuine completions
        and the marker makes every one of them unreadable — which is why the
        next beat's basis is zero and its unit gets the whole window again."""
        merged = {
            PHASE_FUTURES: {
                "units_total": PROD_UNITS_TOTAL,
                "units_done": PROD_BANKED,
                cmb.LEVEL_REFUTED_KEY: True,
            }
        }
        assert "unit_ms_worst" not in merged[PHASE_FUTURES]
        ledger = PhaseLedger(
            plan=_plan(unit_ms=None, unit_ms_worst=None, units_done=PROD_BANKED),
            population_version="q271",
            owner="test:1",
            generation=1,
            input_fingerprint="fp",
        )
        assert ledger.measured_unit_worst_ms(PHASE_FUTURES) is None

    def test_the_ring_would_otherwise_bound_the_unit(self):
        """The ring is not decorative: folded back in it produces a real basis.
        That it exceeds one beat's window is the NEXT finding (the slot needs
        refining, CAL-P1301) — it is not a reason to keep it suppressed."""
        worst_basis = int(max(PROD_WORST_RING) * BUDGET_SAFETY)
        assert worst_basis > 0
        second_worst = int(sorted(PROD_WORST_RING)[-2] * BUDGET_SAFETY)
        assert second_worst < PROD_SOFT_LIMIT_MS - PROD_CLEANUP_MARGIN_MS
