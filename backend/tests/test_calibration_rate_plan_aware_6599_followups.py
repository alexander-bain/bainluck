"""The two nonblocking follow-ups CERT-2987 named, both from CAL-P1301 (#6599).

CAL-P1302. #6599 taught the staged build to REFINE a slot that cancels twice
into m children of a finer partition, so from that deploy on a plan can hold
more units than the partition constant. Two places still assumed it could not.

**One — the remaining-work arithmetic.** ``_unit_costs_from`` was taught the
difference and ``_record_staged_rate`` was not, so it computed
``remaining = STAGED_FUTURES_BUCKETS - banked``. On a plan of 131 with 128
banked that is ``max(0, 0)`` — the producer publishing ``beats_to_publish: 0``,
which in this codebase means PUBLISHED, while three units are outstanding.
Nothing invalid escapes: ``is_complete`` is keyed on the exact unit set and
refuses. The damage is that the two then disagree inside one payload, and the
disagreement points the wrong way — the same "producer claims it is done while
it is not" reading that ``test_the_eta_never_reads_zero_while_units_remain``
(``test_staged_rate_projection_1680``) exists to forbid. This suite is that
invariant carried onto plans the 2026-08 partition could not express.

**Two — the cancellation-memory save.** #6599 added a ``save_staged_cursor``
call on the CANCELLATION path so a stuck slot is remembered between beats. That
call reaches the same two failing exits as a unit bank, and both of them tally
an unbanked COMPLETION — a count that is subtracted from
``staged:units_completed_this_beat``. So a beat that banked a unit and failed to
remember a cancellation would publish PROGRESS 0 while a unit really did land.
The direction is what makes it worth fixing rather than noting: that field's
whole job (CAL-P1048, gotcha #53) is to separate "nothing banked because every
unit was cancelled" from "nothing banked because the durable path is failing",
and the defect files a cancellation under the second.

Both are accounting, not publication — neither could publish partial data, which
is why the cert named them nonblocking. They are fixed together because they are
the same omission: CAL-P1301 changed what a plan can be, and two readers of the
old assumption were left behind.
"""

from __future__ import annotations

import asyncio
import inspect
from importlib import import_module

import pytest

cmb = import_module("app.tasks.calibration_main_build")
cpl = import_module("app.utils.calibration_phase_ledger")

UNIT = cmb.STAGED_UNIT_STAGE

#: The partition, pinned rather than read off the live dial — every scenario
#: here is arithmetic ABOUT the constant, so a suite that took its value from
#: the constant could not tell the two apart (the trap CAL-P1033 names, and the
#: one the third #6599 mutation caught in my own loop bound).
BASE = 128


def _ledger() -> cpl.PhaseLedger:
    return cpl.PhaseLedger(
        plan=cpl.derive_plan({}, floors={}),
        population_version="q269",
        owner="test",
        generation=1,
        input_fingerprint="fp",
    )


class _Runner:
    """The two things :func:`_record_staged_rate` reads off a PhaseRunner."""

    def __init__(self, ledger, elapsed_ms: int = 1_030_000):
        self.ledger = ledger
        self._elapsed_ms = elapsed_ms

    def elapsed_ms(self) -> int:
        return self._elapsed_ms


class _stage:
    """The frozen loop's ``runner.stage(...)`` contract, at a fixed cost.

    ``completed=True`` only if the body did not raise, which is exactly how a
    cancelled unit differs from a banked one in the ledger.
    """

    def __init__(self, ledger, name: str, cost_ms: int):
        self._ledger = ledger
        self._name = name
        self._cost = cost_ms

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self._ledger.record_stage_outcome(self._name, self._cost, completed=exc_type is None)
        return False


class _CursorStub:
    def as_payload(self) -> dict:
        return {"committed_units": [], "served_at": 0.0}


def _install_publish(monkeypatch, publish):
    """Point ``save_staged_cursor`` at a fake durable writer.

    ``publish=None`` makes the write RAISE; otherwise it returns
    ``publish(envelope)``. The subject is the boolean and the tally, not
    envelope construction, so the imported-inside-the-function collaborators are
    neutralised the way ``test_calibration_banked_after_checkpoint_3803`` does.
    """

    async def _publish(envelope):
        if publish is None:
            raise RuntimeError("durable write failed")
        return publish(envelope)

    monkeypatch.setattr("app.services.durable_snapshots.publish_snapshot_standalone", _publish)
    monkeypatch.setattr(
        "app.utils.calibration_staged_futures.stamp_served_at", lambda cursor, now: cursor
    )
    monkeypatch.setattr(
        "app.utils.durable_state.DurableEnvelope.build", staticmethod(lambda **kw: kw)
    )


@pytest.fixture(autouse=True)
def _partition_as_measured(monkeypatch):
    monkeypatch.setattr(cmb, "STAGED_FUTURES_BUCKETS", BASE)


@pytest.fixture(autouse=True)
def _clean_tally():
    """No test may inherit another's tally, and none may leak one."""
    cmb._reset_unbanked_completions()
    yield
    cmb._reset_unbanked_completions()


def _nine_healthy_units(led) -> None:
    """The 2026-08-17 production beat's shape: ~9 units at ~112s."""
    for _ in range(9):
        with _stage(led, UNIT, 112_000):
            pass


# --------------------------------------------------------------------------
# Follow-up one: the ETA counts the plan, not the partition
# --------------------------------------------------------------------------


class TestARefinedPlanIsNotFinishedAtOneHundredAndTwentyEight:
    """The reading the constant produced, on the plans #6599 made possible."""

    def test_the_eta_does_not_report_published_while_children_remain(self):
        """The defect, stated as the invariant it breaks.

        128 banked out of a 131-unit plan is three units of real work away from
        publishing. ``beats_to_publish: 0`` means PUBLISHED — the one value this
        field may not take while anything is outstanding.
        """
        led = _ledger()
        _nine_healthy_units(led)
        led.record_gauge("staged:units_planned_total", 131)
        runner = _Runner(led)

        cmb._record_staged_rate(runner, banked=BASE)

        assert led.stages["staged:beats_to_publish"] != 0, (
            "a 131-unit plan with 128 banked has three units left; reporting "
            "zero beats is the producer claiming it is done while it is not"
        )
        assert led.stages["staged:beats_to_publish"] > 0, (
            "and it is a converging build, so the answer is a finite count — "
            "-1 would say a whole beat cannot hold one unit, which is false here"
        )

    @pytest.mark.parametrize("banked", [BASE, BASE + 1, BASE + 2])
    def test_the_invariant_holds_past_the_partition(self, banked):
        """``test_the_eta_never_reads_zero_while_units_remain`` (#1680) stops at
        127 because 128 was the largest plan that could exist. Same property,
        carried onto the counts a refined plan can reach."""
        led = _ledger()
        _nine_healthy_units(led)
        led.record_gauge("staged:units_planned_total", BASE + 3)
        runner = _Runner(led)

        cmb._record_staged_rate(runner, banked=banked)

        assert led.stages["staged:beats_to_publish"] != 0

    def test_a_refined_plan_that_really_IS_complete_still_reports_zero(self):
        """The other direction, or the fix would be a one-way ratchet that can
        never say 'finished' again on a plan that was cut."""
        led = _ledger()
        _nine_healthy_units(led)
        led.record_gauge("staged:units_planned_total", 131)
        runner = _Runner(led)

        cmb._record_staged_rate(runner, banked=131)

        assert led.stages["staged:beats_to_publish"] == 0

    def test_the_eta_is_computed_from_the_children_it_still_owes(self):
        """Not merely non-zero — the right size.

        Three units left at ~9 per beat is one beat. A fix that read the plan
        but kept a wrong subtrahend could satisfy every assertion above.
        """
        led = _ledger()
        _nine_healthy_units(led)
        led.record_gauge("staged:units_planned_total", BASE + 3)
        runner = _Runner(led)

        cmb._record_staged_rate(runner, banked=BASE)

        assert led.stages["staged:beats_to_publish"] == 1


class TestTheUnrefinedBeatIsByteIdenticalToBefore:
    """The control. Every cursor before #6599, and every one whose slots all
    fit, must read EXACTLY as it always did — this is the overwhelming majority
    of beats, so a regression here would be the whole of production."""

    @pytest.mark.parametrize("banked", [0, 1, 73, 127, BASE])
    def test_an_absent_plan_gauge_falls_back_to_the_partition(self, banked):
        """A beat that died before the unit loop never records the gauge. The
        constant is the fallback, and the fallback is the old behaviour."""
        led = _ledger()
        _nine_healthy_units(led)
        runner = _Runner(led)

        cmb._record_staged_rate(runner, banked=banked)

        expected = 0 if banked >= BASE else led.stages["staged:beats_to_publish"]
        assert led.stages["staged:beats_to_publish"] == expected
        assert (led.stages["staged:beats_to_publish"] == 0) == (banked >= BASE), (
            "with no plan recorded, 'finished' must still mean 'banked the "
            "whole partition' — exactly the pre-CAL-P1302 reading"
        )

    def test_a_plan_of_exactly_the_partition_is_unchanged(self):
        """The common post-#6599 beat: the gauge is present and equals 128."""
        led = _ledger()
        _nine_healthy_units(led)
        led.record_gauge("staged:units_planned_total", BASE)
        runner = _Runner(led)
        cmb._record_staged_rate(runner, banked=BASE)

        bare = _ledger()
        _nine_healthy_units(bare)
        cmb._record_staged_rate(_Runner(bare), banked=BASE)

        assert led.stages["staged:beats_to_publish"] == bare.stages["staged:beats_to_publish"]

    def test_a_zero_plan_gauge_is_treated_as_absent_not_as_a_finished_build(self):
        """``0 or CONSTANT`` is the idiom, and it is load-bearing: a plan total
        of 0 arriving from a malformed payload must not read as 'nothing left
        to do, publish'."""
        led = _ledger()
        _nine_healthy_units(led)
        led.record_gauge("staged:units_planned_total", 0)
        runner = _Runner(led)

        cmb._record_staged_rate(runner, banked=73)

        assert led.stages["staged:beats_to_publish"] != 0


class TestTheTwoPublishersOfPlanSizeCannotDrift:
    """``_unit_costs_from`` publishes ``units_total``; ``_record_staged_rate``
    subtracts from it. CAL-P1301 fixed one and left the other — so the standing
    risk is not the constant, it is the two of them disagreeing again."""

    def test_both_read_the_same_helper(self):
        """A source scan, because the guarantee is 'one source', which no
        single behavioural assertion can express."""
        rate = inspect.getsource(cmb._record_staged_rate)
        costs = inspect.getsource(cmb._unit_costs_from)

        assert "_planned_unit_total(runner)" in rate
        assert "_planned_unit_total(runner)" in costs
        assert "STAGED_FUTURES_BUCKETS" not in rate, (
            "the remaining-work arithmetic must not reach for the partition "
            "constant again; the fallback belongs in the helper"
        )

    def test_the_published_total_and_the_subtrahend_agree_on_one_beat(self):
        """The behavioural half: one refined beat, both fields, same number."""
        led = _ledger()
        _nine_healthy_units(led)
        led.record_gauge("staged:units_planned_total", 131)
        led.record_gauge("staged:units_banked", BASE)
        runner = _Runner(led)

        costs = cmb._unit_costs_from(runner)
        cmb._record_staged_rate(runner, banked=BASE)

        assert costs["futures"]["units_total"] == 131
        assert led.stages["staged:beats_to_publish"] != 0, (
            "publishing units_total=131 beside beats_to_publish=0 is one payload "
            "holding both readings of the same build"
        )


# --------------------------------------------------------------------------
# Follow-up two: a cancellation is not a completion
# --------------------------------------------------------------------------

_BOTH_FAILING_EXITS = pytest.mark.parametrize(
    "publish, arm",
    [
        (lambda env: {"status": "rejected", "reason": "generation_regressed"},
         "the write was REJECTED"),
        (None, "the write RAISED"),
    ],
)


class TestAFailedCancellationMemorySaveIsNotAnUnbankedCompletion:
    """Both failing exits, because the caller sees one ``False`` and a repair
    that closed only the reachable branch would leave the defect on the other
    (the shape CAL-P1048 already established for the banking path)."""

    @_BOTH_FAILING_EXITS
    def test_the_tally_does_not_move(self, monkeypatch, publish, arm):
        led = _ledger()
        # The unit was CANCELLED: the stage did not complete.
        try:
            with _stage(led, UNIT, 950_329):
                raise RuntimeError("statement timeout")
        except RuntimeError:
            pass

        async def _drive():
            return await cmb.save_staged_cursor(
                _CursorStub(), terminal="partial", banks_a_unit=False
            )

        _install_publish(monkeypatch, publish)
        ok = asyncio.run(_drive())

        assert ok is False, f"{arm}: the failure is still reported to the caller"
        assert cmb.unbanked_unit_completions() == 0, (
            f"{arm}: no unit completed, so there is no completion to call "
            "unbanked — the caller records staged:unit_cancel_not_persisted"
        )

    @_BOTH_FAILING_EXITS
    def test_a_failed_UNIT_save_is_STILL_counted(self, monkeypatch, publish, arm):
        """The control that keeps this from being a deletion of CAL-P1048.

        The default is unchanged and the banking path must still tally, or the
        follow-up would have repaired an over-count by reintroducing the
        under-count #3803 was written against.
        """
        led = _ledger()
        with _stage(led, UNIT, 112_329):
            pass

        async def _drive():
            return await cmb.save_staged_cursor(_CursorStub(), terminal="partial")

        _install_publish(monkeypatch, publish)
        asyncio.run(_drive())

        assert cmb.unbanked_unit_completions() == 1, f"{arm}: still an unbanked completion"

    def test_the_published_progress_keeps_the_unit_that_really_landed(self, monkeypatch):
        """End to end on the mixed beat, which is the one that misreported.

        One unit banks; a second cancels and its cancellation memory fails to
        persist. Progress is 1. Under the defect the cancellation's tally was
        subtracted from the completion and the beat published 0 — a beat that
        did real work reporting none of it.
        """
        led = _ledger()
        runner = _Runner(led)

        async def _drive():
            with _stage(led, UNIT, 112_329):
                pass
            _install_publish(monkeypatch, lambda env: {"status": "ok"})
            banked = await cmb.save_staged_cursor(_CursorStub(), terminal="partial")

            try:
                with _stage(led, UNIT, 950_329):
                    raise RuntimeError("statement timeout")
            except RuntimeError:
                pass
            _install_publish(monkeypatch, lambda env: {"status": "rejected"})
            remembered = await cmb.save_staged_cursor(
                _CursorStub(), terminal="partial", banks_a_unit=False
            )
            return banked, remembered

        banked, remembered = asyncio.run(_drive())
        assert banked is True and remembered is False, "the beat under test is the mixed one"

        cmb._record_staged_rate(runner, banked=1)

        assert led.stages["staged:units_this_beat"] == 2
        assert led.stages["staged:units_completed_this_beat"] == 1, (
            "one unit read, committed and banked its cursor; the other was "
            "cancelled and only its MEMORY failed to save"
        )
        assert "staged:units_completion_not_banked" not in led.stages, (
            "and no durable-path failure is claimed, because none happened to a "
            "completed unit — that field is the diagnosis, not a counter"
        )


class TestTheCancellationCallSiteIsTheOneThatOptsOut:
    """The kwarg only pays if the cancellation save passes it and the banking
    saves do not. Asserted on the source because driving the frozen loop needs
    a database — but over the PARSE, not over the text.

    A ``src.count("banks_a_unit=False")`` reads 2 here and always will: the line
    above the call explains the kwarg and contains it verbatim. A needle that
    matches prose as well as code grades something nobody wrote deliberately, so
    the call sites are taken from the AST and the comments cannot vote.
    """

    @staticmethod
    def _saves() -> list:
        """Every ``save_staged_cursor(...)`` call in the frozen unit loop."""
        import ast
        import textwrap

        pcl = import_module("app.tasks.precompute_calibration")
        tree = ast.parse(textwrap.dedent(inspect.getsource(pcl._run_staged_futures)))
        return [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and getattr(node.func, "id", None) == "save_staged_cursor"
        ]

    @staticmethod
    def _opts_out(call) -> bool:
        return any(
            kw.arg == "banks_a_unit" and getattr(kw.value, "value", None) is False
            for kw in call.keywords
        )

    def test_exactly_one_save_in_the_unit_loop_opts_out(self):
        calls = self._saves()

        assert len(calls) >= 2, (
            "the loop saves on both the cancellation and the banking path; "
            "finding fewer means this scan stopped reaching its subject"
        )
        assert sum(self._opts_out(c) for c in calls) == 1, (
            "one cancellation save opts out. Two would mean the banking save "
            "has been silenced and a real durable failure would go untallied — "
            "the CAL-P1048 under-count, reintroduced by its own repair"
        )

    def test_the_save_that_banks_a_unit_still_takes_the_default(self):
        """Which call is which, by position: the opt-out is the EARLIER one.

        The cancellation save sits inside the ``continue`` branch, above the
        commit-and-advance that banks a unit. If a later edit moves the kwarg
        onto the banking call this reverses, and the behavioural control
        (``test_a_failed_UNIT_save_is_STILL_counted``) would still pass, because
        it calls the persister directly rather than through the loop.
        """
        calls = sorted(self._saves(), key=lambda c: c.lineno)

        assert self._opts_out(calls[0]), "the cancellation save is the first one"
        assert not any(self._opts_out(c) for c in calls[1:]), (
            "every save after it banks a unit and must keep tallying its own "
            "failures"
        )
