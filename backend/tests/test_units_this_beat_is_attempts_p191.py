"""CAL-P191 (#2052) — ``staged:units_this_beat`` publishes ATTEMPTS, not banked.

Report: ``artifacts/cal-p191/UNITS-THIS-BEAT-IS-ATTEMPTS-AND-GENERATION-IS-A-CLOCK.md``.

Two writers set the same ledger key, from two modules, meaning two different
things, and the later one wins:

* ``precompute_calibration._record_convergence_projection`` (frozen under
  ruling 009) does ``record_stage("staged:units_this_beat", ran_this_beat)``,
  and ``ran_this_beat`` is incremented only after a unit COMMITS and its cursor
  persists. That is the BANKED count.
* ``calibration_main_build._record_staged_rate`` does
  ``record_gauge("staged:units_this_beat", stage_counts["read:futures_unit"])``.
  ``read:futures_unit`` is recorded on every exit of the unit stage, exceptional
  ones included, so that is the ATTEMPTED count.

``record_gauge`` writes ``self.stages[name] = value`` — the SAME dict
``record_stage`` accumulates into, but with overwrite semantics. So the gauge
write lands last and the published number is attempts.

The overwrite is deliberate and load-bearing (CAL-P066/#1680 put the divisor on
the path that runs whatever the terminal, because the frozen writer could not be
moved). What was not deliberate is the change of DEFINITION that rode along, and
nothing in the suite noticed: ``test_staged_rate_projection_1680.py`` exercises
each writer alone, never both, so the disagreement has never been observed by a
test. On a beat with no cancellations the two readings coincide, which is why it
survived — and since the fence work every beat cancels.

Measured on the live 2026-09-01T16:32:11Z ledger, reproduced verbatim below:
``read:futures_unit`` 7 attempts / ``staged:units_completed_this_beat`` 5 banked
/ ``staged:units_cancelled`` 2, and ``staged:units_this_beat`` published **7**.

These tests CHARACTERIZE current behaviour. They do not assert it is right. The
honest reading is already published beside it (``units_completed_this_beat``),
so the defect is the NAME, and choosing which writer should win changes the
meaning of a gauge five graders read — a fold's call under ruling 134, not a
build lane's.

TEST-ONLY. Nothing under ``app/`` is touched, so ``_main_input_fingerprint()``
cannot move and this file is inert under the D-G deploy freeze
(``.claude/handoff/runner-inbox/calibration/960-calibration-deploy-freeze``).
"""

from __future__ import annotations

from datetime import datetime, timezone
from importlib import import_module

cmb = import_module("app.tasks.calibration_main_build")
cpl = import_module("app.utils.calibration_phase_ledger")
pc = import_module("app.tasks.precompute_calibration")
ds = import_module("app.utils.durable_state")


# The 2026-09-01T16:32:11Z production beat, to the millisecond.
LIVE_ATTEMPTS = 7
LIVE_BANKED = 5
LIVE_CANCELLED = 2
LIVE_COMPLETED_MS = 56_431          # staged:unit_ms_mean_completed
LIVE_CANCELLED_MS = (353_845, 353_838)   # staged:unit_cancelled:<chunk>
LIVE_MIXED_MEAN_MS = 141_403        # staged:unit_ms_mean


def _ledger() -> cpl.PhaseLedger:
    return cpl.PhaseLedger(
        plan=cpl.derive_plan({}, floors={}),
        population_version="q268",
        owner="test",
        generation=1,
        input_fingerprint="fp",
    )


class _Runner:
    """The two things the writers read off a PhaseRunner."""

    def __init__(self, ledger, elapsed_ms: int):
        self.ledger = ledger
        self._elapsed_ms = elapsed_ms

    def elapsed_ms(self) -> int:
        return self._elapsed_ms


def _live_beat_ledger() -> cpl.PhaseLedger:
    """Five units that banked and two that died at their own bound."""
    led = _ledger()
    for _ in range(LIVE_BANKED):
        led.record_stage_outcome("read:futures_unit", LIVE_COMPLETED_MS, completed=True)
    for ms in LIVE_CANCELLED_MS:
        led.record_stage_outcome("read:futures_unit", ms, completed=False)
        led.record_stage("staged:units_cancelled", 1)
    return led


# ---------------------------------------------------------------------------
# 1. The mechanism: one store, two write rules
# ---------------------------------------------------------------------------


class TestOneStoreTwoWriteRules:
    def test_record_gauge_overwrites_what_record_stage_accumulated(self):
        """The collision is invisible because both land in ``stages``."""
        led = _ledger()
        led.record_stage("staged:units_this_beat", 5)
        assert led.stages["staged:units_this_beat"] == 5

        led.record_gauge("staged:units_this_beat", 7)

        assert led.stages["staged:units_this_beat"] == 7, (
            "record_gauge must replace, not add — if this becomes 12 the gauge "
            "contract (CAL-P024c) has been lost"
        )

    def test_the_loser_leaves_no_trace_of_having_written(self):
        """There is no way to tell, from the payload, that 5 was ever there.

        This is why the disagreement is unobservable in production: a grader
        reading the ledger sees one key with one value and no sign that two
        modules disagreed about what it counts.
        """
        led = _ledger()
        led.record_stage("staged:units_this_beat", 5)
        led.record_gauge("staged:units_this_beat", 7)

        payload = led.as_payload()
        assert payload["stages"]["staged:units_this_beat"] == 7
        assert payload["stage_counts"]["staged:units_this_beat"] == 1, (
            "the emission COUNT is all that survives of the first write, and 1 "
            "is not the banked count it stood for"
        )


# ---------------------------------------------------------------------------
# 2. The consequence: the published number is attempts
# ---------------------------------------------------------------------------


class TestTheLiveBeatDisagreesWithItself:
    def test_the_frozen_writer_alone_reports_banked(self):
        led = _live_beat_ledger()
        runner = _Runner(led, elapsed_ms=1_031_102)

        pc._record_convergence_projection(
            runner,
            done=45,
            planned=128,
            ran_this_beat=LIVE_BANKED,
            unit_ms_this_beat=float(LIVE_COMPLETED_MS * LIVE_BANKED),
            worst_unit_ms=68_314.0,
        )

        assert led.stages["staged:units_this_beat"] == LIVE_BANKED

    def test_the_later_writer_replaces_it_with_attempts(self):
        """Both writers ran on the live beat. 7 is what production published."""
        led = _live_beat_ledger()
        runner = _Runner(led, elapsed_ms=1_031_102)

        pc._record_convergence_projection(
            runner,
            done=45,
            planned=128,
            ran_this_beat=LIVE_BANKED,
            unit_ms_this_beat=float(LIVE_COMPLETED_MS * LIVE_BANKED),
            worst_unit_ms=68_314.0,
        )
        cmb._record_staged_rate(runner, banked=45)

        assert led.stages["staged:units_this_beat"] == LIVE_ATTEMPTS, (
            "the gauge writer wins; 'units this beat' is the count of units the "
            "beat STARTED, two of which died at their own bound"
        )
        assert LIVE_ATTEMPTS != LIVE_BANKED, "the guard is vacuous if they agree"

    def test_a_beat_with_no_cancellation_hides_the_disagreement(self):
        """Why this survived: the readings coincide until a unit dies.

        The regression arm of this guard must show the defect is INVISIBLE in
        the healthy case, or the healthy case would have caught it years ago.
        """
        led = _ledger()
        for _ in range(LIVE_BANKED):
            led.record_stage_outcome("read:futures_unit", LIVE_COMPLETED_MS, completed=True)
        runner = _Runner(led, elapsed_ms=1_031_102)

        pc._record_convergence_projection(
            runner,
            done=45,
            planned=128,
            ran_this_beat=LIVE_BANKED,
            unit_ms_this_beat=float(LIVE_COMPLETED_MS * LIVE_BANKED),
            worst_unit_ms=68_314.0,
        )
        cmb._record_staged_rate(runner, banked=45)

        assert led.stages["staged:units_this_beat"] == LIVE_BANKED

    def test_the_honest_pair_is_the_mixed_mean_and_it_shares_the_denominator(self):
        """``unit_ms_mean`` divides by the same 7 (P189 §5c), by construction.

        The numerator defect and the denominator defect are ONE defect:
        ``read:futures_unit``'s observation count is both 'units this beat' and
        the mean's divisor.
        """
        led = _live_beat_ledger()
        runner = _Runner(led, elapsed_ms=1_031_102)
        cmb._record_staged_rate(runner, banked=45)

        total = led.stages["read:futures_unit"]
        assert led.stages["staged:units_this_beat"] == LIVE_ATTEMPTS
        assert led.stages["staged:unit_ms_mean"] == total // LIVE_ATTEMPTS
        assert led.stage_completed_mean_ms("read:futures_unit") == LIVE_COMPLETED_MS, (
            "the completed-only mean is the cost of a unit; the mixed mean is not"
        )


# ---------------------------------------------------------------------------
# 3. ``generation`` is a clock reading
# ---------------------------------------------------------------------------


class TestGenerationIsAClockNotACounter:
    """The last untested quotable gauge on the CAL-P190 list."""

    def test_generation_is_epoch_milliseconds_of_the_builds_own_stamp(self):
        stamp = datetime(2026, 9, 1, 16, 15, 0, 162_000, tzinfo=timezone.utc)

        assert ds.generation_for(stamp) == 1_788_279_300_162, (
            "the value carried by the live 2026-09-01T16:32:11Z ledger — a wall "
            "clock reading, not a rebuild sequence number"
        )

    def test_it_is_not_a_counter_so_it_cannot_detect_a_rebuild_restart(self):
        """Every beat mints a new one. A changed generation means TIME PASSED.

        The gauge that detects a restart is ``input_fingerprint``; ``generation``
        is incapable of it in either direction, and reads exactly like a counter
        that would be.
        """
        first = ds.generation_for(datetime(2026, 9, 1, 15, 33, 41, tzinfo=timezone.utc))
        second = ds.generation_for(datetime(2026, 9, 1, 16, 15, 0, tzinfo=timezone.utc))

        assert second > first
        assert second - first == (16 * 3600 + 15 * 60) * 1000 - (
            15 * 3600 + 33 * 60 + 41
        ) * 1000, "the delta is elapsed milliseconds, not a number of builds"
