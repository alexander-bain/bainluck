"""CAL-P1048 — a unit is "banked" only after its cursor is DURABLE.

Repairs CERT-2196's named finding ``CALIBRATION-3803-BANKED-AFTER-CHECKPOINT``,
which is the second half of #3803. CAL-P1047 fixed the READER: the operator
window published ``rebuild_units_this_beat`` off ``staged:units_this_beat``, the
count of units that RAN, so a unit cancelled at its statement bound was reported
as a banked one. That is fixed and stays fixed (its guards are in
``test_calibration_beat_ring_counts_banked_not_attempted_3803.py``).

This file is about the PRODUCER of the number the reader now trusts. The frozen
unit loop in ``precompute_calibration._run_staged_futures`` reads (quoted at a
narrower indent than the source, so this docstring does not itself hold a literal
the mutation-residue scan reads as a stray mutant)::

  with runner.stage("read:futures_unit"):     # completed=True on exit
      result = await db.execute(chunk_sql, {...})
      unit_rows = result.all()
  await runner.commit(db)
  cursor = advance(cursor, chunk.key, unit_rows, ...)
  if not await save_staged_cursor(cursor, terminal=TERMINAL_PARTIAL):
      return None                              # counted, but NOT banked
  done += 1

The stage closes when the SQL returns. The commit and the durable cursor write
happen AFTER it. So on the cursor-write-failure path the unit is already inside
``stage_ok_counts`` — and ``staged:units_completed_this_beat`` is derived from
that tally — while ``done`` is correctly not incremented, the cursor is not
persisted, and the beat returns. The window would read *one banked this beat*
for a beat whose durable bank advanced by **zero**.

That is gotcha #53 in its exact shape (one number standing for two states), and
it is the same defect CAL-P1047 fixed one layer up, which is why it has to be
closed here rather than argued to be unreachable. It is rare — the durable write
has to fail — but "rare" is not "cannot", and the whole resume story rests on
``save_staged_cursor``'s boolean being honest, as that function's own docstring
says.

WHY THE FIX IS NOT IN THE LOOP: ``precompute_calibration.py`` is frozen under
D45, which licenses the publish-first reorder and nothing else. The count is
therefore corrected at both ends inside ``calibration_main_build.py`` —
``save_staged_cursor`` notes its own failure, ``load_staged_cursor`` resets the
tally at the start of the beat, ``_record_staged_rate`` subtracts it — and the
frozen loop is untouched. The tests below drive the REAL
``save_staged_cursor``, not a stand-in for it, so the wiring between those three
points is what is under test.
"""

from __future__ import annotations

import asyncio

import pytest

from app.tasks import calibration_main_build as cmb
from app.tasks.calibration_beat_gauge_sampler import (
    GAP_FIELD,
    row_rebuild_progress,
)
from app.utils import calibration_phase_ledger as cpl

UNIT = cmb.STAGED_UNIT_STAGE


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

    def __init__(self, ledger, elapsed_ms: int = 600_000):
        self.ledger = ledger
        self._elapsed_ms = elapsed_ms

    def elapsed_ms(self) -> int:
        return self._elapsed_ms


@pytest.fixture(autouse=True)
def _clean_tally():
    """No test may inherit another's tally, and none may leak one.

    The production reset lives in ``load_staged_cursor``; this fixture is the
    test-side equivalent so a failure here is never a false alarm from ordering.
    """
    cmb._reset_unbanked_completions()
    yield
    cmb._reset_unbanked_completions()


# --------------------------------------------------------------------------
# The failing path, driven through the real save_staged_cursor
# --------------------------------------------------------------------------


class TestACursorThatDidNotPersistIsNotABankedUnit:
    """Property 1 — query success + commit success + cursor-save false ⇒ 0."""

    @pytest.mark.parametrize(
        "publish, arm",
        [
            (lambda env: {"status": "rejected", "reason": "generation_regressed"},
             "the write was REJECTED"),
            (None, "the write RAISED"),
        ],
    )
    def test_the_beat_reports_zero_banked_not_one(self, monkeypatch, publish, arm):
        """Both failing exits of ``save_staged_cursor`` must be counted.

        The caller cannot tell a raise from a rejection — it sees one ``False``
        — and neither one banked anything, so a repair that closed only the
        branch that happens to be easier to reach would leave the defect live
        on the other.
        """
        led = _ledger()
        runner = _Runner(led)

        async def _drive():
            # The unit read: SQL returned, so the stage COMPLETES. This is the
            # exact ordering the frozen loop uses.
            with _stage(led, UNIT, 112_329):
                pass
            # ...and then the durable write fails.
            return await cmb.save_staged_cursor(_cursor_stub(), terminal="partial")

        _install_publish(monkeypatch, publish)
        ok = asyncio.run(_drive())

        assert ok is False, f"{arm}: save_staged_cursor must report failure"
        assert led.stage_completed_count(UNIT) == 1, (
            "the stage tally still counts it — that is the raw fact the repair "
            "corrects, not one it deletes"
        )

        cmb._record_staged_rate(runner, banked=29)

        assert led.stages["staged:units_completed_this_beat"] == 0, (
            f"{arm}: the durable bank advanced by zero, so the progress reading "
            "an operator sees must be zero"
        )
        assert led.stages["staged:units_completion_not_banked"] == 1, (
            "and the reason must be NAMED — 'nothing banked because every unit "
            "was cancelled' and 'nothing banked because the cursor write failed' "
            "are opposite diagnoses (gotcha #53)"
        )

    def test_the_endpoint_an_operator_reads_reports_zero(self, monkeypatch):
        """END TO END, which is what CERT-2196 asked for.

        The producer's gauges are fed through the ring reader that actually
        serves the operator window. A repair proved only at the ledger would
        leave open the possibility that the published field is derived from
        some other operand.
        """
        led = _ledger()
        runner = _Runner(led)

        async def _drive():
            with _stage(led, UNIT, 112_329):
                pass
            return await cmb.save_staged_cursor(_cursor_stub(), terminal="partial")

        _install_publish(monkeypatch, lambda env: {"status": "rejected"})
        asyncio.run(_drive())
        led.record_gauge("staged:units_banked", 29)
        led.record_gauge("staged:units_drifted", 19)
        led.record_gauge("staged:units_drift_checkable", 28)
        led.record_gauge("staged:units_drift_uncheckable", 1)
        cmb._record_staged_rate(runner, banked=29)

        progress = row_rebuild_progress(
            {
                "generation": 1_788_765_487_215,
                "generated_at": "2026-09-07T07:18:07.215080+00:00",
                "terminal": "cancelled",
                "gauge_capture_version": 2,
                "gauges_missing_required": [],
                "gauges": dict(led.stages),
            }
        )

        assert progress["rebuild_units_this_beat"] == 0, (
            "the served field, not the ledger gauge: this is the number on the "
            "operator window"
        )
        assert progress["rebuild_units_this_beat_measured"] is True, (
            "a measured zero, never an absence — the beat did record it"
        )
        assert progress["rebuild_units_ran_this_beat"] == 1, (
            "the unit RAN and that fact survives; the repair relabels it, it "
            "does not make 112 seconds of the beat invisible"
        )
        assert progress[GAP_FIELD] == 1, (
            "and the gap absorbs it, so the published triple still reconciles"
        )


class TestTheCostReadingIsDeliberatelyNotSubtracted:
    """Property 2 — progress and cost answer different questions."""

    def test_a_real_measured_unit_cost_survives_a_zero_progress_beat(self, monkeypatch):
        """A unit that read and committed really did take the time it took.

        Dropping it would throw away a valid sample AND feed a worse number to
        the unit bound, which is sized from measured cost (#3828). So
        ``units_completed_this_beat: 0`` beside a real ``unit_ms_mean_completed``
        is correct and intended, and this test pins it so a later reader does
        not "fix" the apparent inconsistency.
        """
        led = _ledger()
        runner = _Runner(led)

        async def _drive():
            with _stage(led, UNIT, 112_329):
                pass
            return await cmb.save_staged_cursor(_cursor_stub(), terminal="partial")

        _install_publish(monkeypatch, lambda env: {"status": "rejected"})
        asyncio.run(_drive())
        cmb._record_staged_rate(runner, banked=29)

        assert led.stages["staged:units_completed_this_beat"] == 0
        assert led.stages["staged:unit_ms_mean_completed"] == 112_329, (
            "the cost of a unit is measured, and this unit was measured"
        )
        assert "staged:unit_cost_reason:no_unit_completed" not in led.stages, (
            "a unit DID complete its read — the 'nothing completed' branch is a "
            "different state and must not fire here"
        )


class TestTheHappyPathIsUnmoved:
    """Property 3 — the repair costs a clean beat nothing."""

    def test_five_banked_units_still_report_five(self, monkeypatch):
        led = _ledger()
        runner = _Runner(led)

        async def _drive():
            for _ in range(5):
                with _stage(led, UNIT, 112_329):
                    pass
                assert await cmb.save_staged_cursor(_cursor_stub(), terminal="partial")

        _install_publish(monkeypatch, lambda env: {"status": "ok"})
        asyncio.run(_drive())
        cmb._record_staged_rate(runner, banked=29)

        assert led.stages["staged:units_completed_this_beat"] == 5
        assert "staged:units_completion_not_banked" not in led.stages, (
            "a clean beat writes no failure field — an unconditional 0 here "
            "would put a scary-looking key on every healthy ledger"
        )

    def test_a_superseded_write_is_a_success_not_a_failure(self, monkeypatch):
        """``superseded`` means a NEWER generation already landed — the durable
        state is ahead of us, not missing. ``save_staged_cursor`` has always
        treated it as ok and the repair must not silently re-classify it."""
        led = _ledger()
        runner = _Runner(led)

        async def _drive():
            with _stage(led, UNIT, 112_329):
                pass
            return await cmb.save_staged_cursor(_cursor_stub(), terminal="partial")

        _install_publish(monkeypatch, lambda env: {"status": "superseded"})
        assert asyncio.run(_drive()) is True
        cmb._record_staged_rate(runner, banked=29)

        assert led.stages["staged:units_completed_this_beat"] == 1
        assert "staged:units_completion_not_banked" not in led.stages

    def test_a_cancelled_unit_is_still_attributed_to_the_bound_not_the_cursor(self):
        """The CAL-P1047 case must keep its own diagnosis.

        Six ran, five completed, none failed at the cursor: the answer is 5 and
        no cursor-failure field. If this test ever fails, the two causes of "ran
        but not banked" have been merged back into one.
        """
        led = _ledger()
        runner = _Runner(led)
        for _ in range(5):
            with _stage(led, UNIT, 72_400):
                pass
        # The 6th unit is cancelled at its bound. Written as try/except rather
        # than ``pytest.raises`` because CodeQL does not model the latter as
        # swallowing the exception and reads the rest of the test as dead code.
        try:
            with _stage(led, UNIT, 950_329):
                raise RuntimeError("statement timeout")
        except RuntimeError:
            pass

        cmb._record_staged_rate(runner, banked=18)

        assert led.stages["staged:units_this_beat"] == 6
        assert led.stages["staged:units_completed_this_beat"] == 5
        assert "staged:units_completion_not_banked" not in led.stages


class TestTheTallyCannotLeakBetweenBeats:
    """Property 4 — a prefork worker reuses its process."""

    def test_load_staged_cursor_resets_the_tally(self, monkeypatch):
        """Without this, one beat's cursor failure would be subtracted from the
        NEXT beat's honest count — turning a fix for an over-count into an
        under-count, which is strictly worse because it hides real progress."""
        cmb._UNBANKED_UNIT_COMPLETIONS = 3

        async def _read(*a, **k):
            raise RuntimeError("unreadable")

        monkeypatch.setattr(
            "app.services.durable_snapshots.read_snapshot_standalone", _read
        )
        asyncio.run(
            cmb.load_staged_cursor(
                population_version="q269",
                input_fingerprint="fp",
                generation_fingerprint="gfp",
                owner="test",
                generation=2,
            )
        )

        assert cmb.unbanked_unit_completions() == 0, (
            "the beat's first cursor action must clear the previous beat's tally"
        )

    def test_the_published_count_is_never_negative(self):
        """A floor, because a wrong subtraction must degrade to 'no progress'
        rather than to a number no reader has a branch for."""
        led = _ledger()
        runner = _Runner(led)
        cmb._UNBANKED_UNIT_COMPLETIONS = 9
        with _stage(led, UNIT, 112_329):
            pass

        cmb._record_staged_rate(runner, banked=29)

        assert led.stages["staged:units_completed_this_beat"] == 0


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------


class _stage:
    """The frozen loop's ``runner.stage(...)`` contract, at a fixed cost.

    A real ``PhaseRunner.stage`` times the body with ``time.monotonic``; these
    tests need the duration to be the one the production beat measured, so the
    cost is passed in and the completion semantics — ``completed=True`` only if
    the body did not raise — are reproduced exactly.
    """

    def __init__(self, ledger, name: str, cost_ms: int):
        self._ledger = ledger
        self._name = name
        self._cost = cost_ms

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self._ledger.record_stage_outcome(
            self._name, self._cost, completed=exc_type is None
        )
        return False


class _CursorStub:
    def as_payload(self) -> dict:
        return {"committed_units": [], "served_at": 0.0}


def _cursor_stub():
    return _CursorStub()


def _install_publish(monkeypatch, publish):
    """Point ``save_staged_cursor`` at a fake durable writer.

    ``publish=None`` makes the write RAISE; otherwise it returns
    ``publish(envelope)``. Also neutralises ``stamp_served_at`` and
    ``DurableEnvelope.build``, which are imported inside the function and would
    otherwise need a real cursor dataclass — the subject under test is the
    boolean and the tally, not envelope construction.
    """

    async def _publish(envelope):
        if publish is None:
            raise RuntimeError("durable write failed")
        return publish(envelope)

    monkeypatch.setattr(
        "app.services.durable_snapshots.publish_snapshot_standalone", _publish
    )
    monkeypatch.setattr(
        "app.utils.calibration_staged_futures.stamp_served_at",
        lambda cursor, now: cursor,
    )
    monkeypatch.setattr(
        "app.utils.durable_state.DurableEnvelope.build",
        staticmethod(lambda **kw: kw),
    )
