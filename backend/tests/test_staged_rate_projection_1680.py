"""The producer says how fast it is going on the terminal it actually takes.

CAL-P066, #1680 phase two.

The diagnosis this suite pins is a positioning defect, not a logic one.
``_record_convergence_projection`` in ``app/tasks/precompute_calibration.py``
computes ``units_this_beat`` / ``unit_ms_mean`` / ``beats_to_publish`` correctly
and with the right caveats. It sits AFTER the unit loop. The loop's normal exit
for a build that has not finished is ``StagedFuturesIncomplete``, so the
projection is skipped on every beat that does not publish — which, since
2026-08-02, is every beat.

What production carried instead, measured 2026-08-17 22:00 UTC:

    "stages": {
        "read:futures_unit": 1077573,      <-- a SUM
        "staged:units_banked": 73,
        "staged:units_partition": 128,
        ...
    }

with no divisor anywhere in the payload. 1,077,573 ms is one pathological unit
or ten healthy ones, and those readings say OPPOSITE things: "this phase cannot
fit and never will" versus "this build is six beats from publishing". Settling
it required polling ``durable_state_snapshots`` from outside the application on
a 60-second loop, because the application would not say. That is ruling 075's
second clause — the ledger could not distinguish "I checked" from "I could not
check" — inside the instrument built to report convergence.

``precompute_calibration.py`` is frozen (ruling 009) so the fix cannot go where
the defect is. It does not need to: :meth:`PhaseLedger.record_stage` now counts
its own observations, so the divisor is in hand in ``calibration_main_build``,
on the path that runs whatever the terminal.
"""

from __future__ import annotations

from importlib import import_module

import pytest

cmb = import_module("app.tasks.calibration_main_build")
cpl = import_module("app.utils.calibration_phase_ledger")


def _ledger() -> cpl.PhaseLedger:
    return cpl.PhaseLedger(
        plan=cpl.derive_plan({}, floors={}),
        population_version="q267",
        owner="test",
        generation=1,
        input_fingerprint="fp",
    )


class _Runner:
    """The two things :func:`_record_staged_rate` reads off a PhaseRunner."""

    def __init__(self, ledger, elapsed_ms: int):
        self.ledger = ledger
        self._elapsed_ms = elapsed_ms

    def elapsed_ms(self) -> int:
        return self._elapsed_ms


class TestTheLedgerCountsItsOwnObservations:
    """The divisor, which is the whole fix."""

    def test_record_stage_still_accumulates(self):
        """The sum is what the budget reasons about — it must not change."""
        led = _ledger()
        led.record_stage("read:futures_unit", 100_000)
        led.record_stage("read:futures_unit", 120_000)

        assert led.stages["read:futures_unit"] == 220_000

    def test_and_now_also_counts(self):
        led = _ledger()
        for _ in range(9):
            led.record_stage("read:futures_unit", 112_000)

        assert led.stage_counts["read:futures_unit"] == 9
        assert led.stage_mean_ms("read:futures_unit") == 112_000

    def test_a_gauge_is_not_an_observation(self):
        """``record_gauge`` sets a LEVEL. Counting it would make the mean of a
        genuine stage wrong the moment the two shared a name."""
        led = _ledger()
        led.record_gauge("rss:peak_mb", 543)
        led.record_gauge("rss:peak_mb", 512)

        assert led.stages["rss:peak_mb"] == 512
        assert "rss:peak_mb" not in led.stage_counts

    def test_no_sample_is_none_and_not_zero(self):
        """Ruling 075, second clause, at the point of writing: "I ran no units"
        and "each unit took 0 ms" are opposite facts."""
        assert _ledger().stage_mean_ms("read:futures_unit") is None

    def test_the_count_is_serialized_beside_the_sum(self):
        """A divisor that never reaches the payload is not a divisor."""
        led = _ledger()
        led.record_stage("read:futures_unit", 112_000)

        payload = led.as_payload()
        assert payload["stage_counts"]["read:futures_unit"] == 1
        assert payload["stages"]["read:futures_unit"] == 112_000


class TestTheProjectionSurvivesTheThrowingTerminal:
    """The numbers that were absent from 181 consecutive ledgers.

    CAL-P1033 (#3536). Every scenario here is a RECONSTRUCTION of a named
    production beat taken under a 128-way partition — "79 of 128 banked", "73",
    "127" — so the partition is pinned rather than read off the live dial. When
    the dial moved to 4 these tests did not become more general, they became
    incoherent: "127 units banked" is not a state a 4-unit partition can be in,
    and the remaining-work arithmetic silently produced 0, which is this
    module's own definition of the producer lying about being finished.
    """

    @pytest.fixture(autouse=True)
    def _partition_as_measured(self, monkeypatch):
        monkeypatch.setattr(cmb, "STAGED_FUTURES_BUCKETS", 128)

    def test_a_working_beat_reports_its_rate_and_a_finite_eta(self):
        """The 2026-08-17 production beat, reconstructed: ~9.6 units at ~112s
        inside a 1,380s window, 79 of 128 banked."""
        led = _ledger()
        for _ in range(9):
            led.record_stage("read:futures_unit", 112_000)
        runner = _Runner(led, elapsed_ms=1_030_000)  # units + ~22s freeze

        cmb._record_staged_rate(runner, banked=79)

        assert led.stages["staged:units_this_beat"] == 9
        assert led.stages["staged:unit_ms_mean"] == 112_000
        eta = led.stages["staged:beats_to_publish"]
        assert eta > 0, "a converging build must publish a finite beat count"
        assert eta <= 8, f"49 units at ~9/beat is ~6 beats, got {eta}"

    def test_a_beat_that_ran_no_unit_says_so_rather_than_going_quiet(self):
        """The most important beat to be able to see. An absent stage reads as
        fine (gotcha #53), so this branch must WRITE something."""
        led = _ledger()
        runner = _Runner(led, elapsed_ms=95_000)

        cmb._record_staged_rate(runner, banked=79)

        assert led.stages["staged:units_this_beat"] == 0
        assert led.stages["staged:rate_reason:no_unit_ran"] == 1
        assert "staged:unit_ms_mean" not in led.stages, (
            "a mean over zero samples is a fabricated number"
        )

    def test_a_unit_larger_than_a_whole_beat_reports_minus_one_not_a_big_number(self):
        """-1 is not "unknown": it is "a whole beat cannot hold one unit", which
        is a different and worse fact. Same convention as the frozen module's
        projection, so the two can never disagree."""
        led = _ledger()
        led.record_stage("read:futures_unit", 3_000_000)  # 50 min for one unit
        runner = _Runner(led, elapsed_ms=3_020_000)

        cmb._record_staged_rate(runner, banked=79)

        assert led.stages["staged:beats_to_publish"] == -1

    def test_a_complete_generation_reports_zero_beats_left(self):
        led = _ledger()
        led.record_stage("read:futures_unit", 112_000)
        runner = _Runner(led, elapsed_ms=134_000)

        cmb._record_staged_rate(runner, banked=cmb.STAGED_FUTURES_BUCKETS)

        assert led.stages["staged:beats_to_publish"] == 0

    @pytest.mark.parametrize("banked", [0, 1, 73, 127])
    def test_the_eta_never_reads_zero_while_units_remain(self, banked):
        """Zero beats to publish means PUBLISHED. Anything else reporting zero
        is the producer claiming it is done while it is not — the exact reading
        four days of a stale ``generated_at`` were hiding behind."""
        led = _ledger()
        for _ in range(9):
            led.record_stage("read:futures_unit", 112_000)
        runner = _Runner(led, elapsed_ms=1_030_000)

        cmb._record_staged_rate(runner, banked=banked)

        assert led.stages["staged:beats_to_publish"] != 0


def test_the_rate_is_recorded_from_the_always_run_path():
    """The positioning IS the fix, so it is what this pins.

    ``_record_staged_convergence`` is called by ``save_phase_ledger``, which the
    module docstring commits to running on EVERY terminal. If the rate call
    migrates back inside a success branch, this build goes dark again in exactly
    the way it was dark for 181 beats and nothing else here would notice.
    """
    import inspect

    src = inspect.getsource(cmb._record_staged_convergence)
    assert "_record_staged_rate(runner" in src

    saver = inspect.getsource(cmb.save_phase_ledger)
    assert "await _record_staged_convergence(runner)" in saver
