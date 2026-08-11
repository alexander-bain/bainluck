"""CAL-P024 — why the staged build could not converge, and how it now says so.

Three things shipped together, and they are one story.

**The measurement.** Two consecutive production beats of the staged futures
build, read 2026-08-09 19:11-19:18Z:

* 16:15:00Z, census OFF: ``read:futures_unit`` 626,242 ms / **10 units** = 62.6 s/unit
* 18:15:00Z, census ON:  ``read:futures_unit`` 632,103 ms / **1 unit**   = 632 s/unit

Same population, same 128-bucket partition, same statement but for the census.
A beat's usable window is ~687 s, so the build went from ~13 beats to ~128 — and
``_main_input_fingerprint`` resets the cursor on any deploy touching the build's
SQL, in a file that took 25 commits in 14 days. The build's convergence time had
come to exceed the lane's own edit interval.

**The two holes that let it happen unnoticed.**

1. Flipping ``COVERAGE_CENSUS_ENABLED`` changed the emitted statement without
   changing the fingerprint, because the switch is read in helpers that
   ``_main_futures_sql`` CALLS and ``inspect.getsource`` does not follow. Units
   built with the census on were resumable by code with it off.
2. Five distinct causes of cursor loss all recorded the same
   ``staged:cursor_invalidate``, and nothing anywhere divided units-done by
   time-per-unit — so "slow" and "never" looked identical in the ledger, and
   telling them apart took a source read plus ``git show`` across two merges.

The tests below pin the fixes to those, in that order.
"""

from __future__ import annotations

import math

import pytest

from app.tasks.calibration_main_build import STAGED_FUTURES_BUCKETS
from app.tasks.precompute_calibration import (
    _main_input_fingerprint,
    _record_convergence_projection,
)
from app.utils.calibration_phase_ledger import FRESH, INVALIDATE, REFUSE, RESUME
from app.utils.calibration_staged_futures import (
    MAIN_BUILD_TASK,
    REASON_ABSENT,
    REASON_INPUT_FINGERPRINT,
    REASON_LEASE_HELD,
    REASON_MALFORMED,
    REASON_MALFORMED_UNITS,
    REASON_NOTHING_BANKED,
    REASON_POPULATION_VERSION,
    REASON_RESUMABLE,
    REASON_SCHEMA,
    REASON_TASK,
    REASON_UNIT_KEY,
    STAGED_FUTURES_SCHEMA,
    UNIT_KEY_VM_ID,
    decode_staged_cursor,
    decode_staged_cursor_detailed,
    encode_unit_rows,
)

# --- The production beat, in numbers, so the tests are about a real event ----
#
# From ``calibration:main:phase_ledger`` generation 1786299300221 (18:15:00Z).
PROD_WINDOW_MS = 726_557       # the beat's deadline — where it was cancelled
PROD_GENERATION_MS = 38_748    # read:futures_generation, paid again every beat
PROD_UNIT_MS_CENSUS_ON = 632_103
PROD_UNIT_MS_CENSUS_OFF = 62_624  # 626,242 ms / 10 units, the 16:15Z beat
PROD_USABLE_MS = PROD_WINDOW_MS - PROD_GENERATION_MS  # ~687 s


class _FakeLedger:
    """Only what the projection touches. A deeper fake would assert on itself."""

    def __init__(self, window_ms: int) -> None:
        self.window_ms = window_ms
        self.stages: dict[str, int] = {}

    def record_stage(self, name: str, value: int) -> None:
        self.stages[name] = value

    def remaining_ms(self, *, elapsed_ms: int) -> int:
        return max(0, self.window_ms - elapsed_ms)


class _FakeRunner:
    def __init__(self, *, window_ms: int, elapsed_ms: int) -> None:
        self.ledger = _FakeLedger(window_ms)
        self._elapsed = elapsed_ms

    def elapsed_ms(self) -> int:
        return self._elapsed


def _project(*, done, planned, ran, unit_ms_total, window_ms=PROD_WINDOW_MS, overhead_ms=PROD_GENERATION_MS):
    runner = _FakeRunner(window_ms=window_ms, elapsed_ms=int(overhead_ms + unit_ms_total))
    _record_convergence_projection(
        runner, done=done, planned=planned, ran_this_beat=ran, unit_ms_this_beat=unit_ms_total
    )
    return runner.ledger.stages


# =============================================================================
# 1. The census switch belongs in the fingerprint
# =============================================================================
class TestTheCensusSwitchIsInTheFingerprint:
    """The hole: a switch that changes the SQL but not the digest.

    ``_main_input_fingerprint`` hashes the source of four functions.
    ``COVERAGE_CENSUS_ENABLED`` is read inside ``_coverage_bridge_ctes`` /
    ``_coverage_bridge_join`` / ``_coverage_bridge_select_columns``, which
    ``_main_futures_sql`` calls but which are not hashed — and
    ``inspect.getsource`` returns a function's own text, never its callees'.

    So the switch could move the statement while leaving the digest identical,
    and a cursor banked under one statement was resumable under the other. That
    is precisely the "half-built by the old code and half by the new" the digest
    exists to prevent, and it is the third instance of the same class of hole in
    this one function's history.
    """

    def test_flipping_the_switch_moves_the_fingerprint(self, monkeypatch):
        before = _main_input_fingerprint()
        monkeypatch.setattr(
            "app.tasks.precompute_calibration.COVERAGE_CENSUS_ENABLED", True
        )
        assert _main_input_fingerprint() != before

    def test_the_switch_is_hashed_by_name_not_as_an_incidental_substring(self):
        """Named, greppable, like ``REPRESENTATIVE_TIE_AUTHORITY`` beside it.

        A value folded anonymously into the digest is invisible to the next
        person deciding whether their new input is covered — which is how the
        previous two holes were opened.
        """
        import inspect

        from app.tasks.precompute_calibration import _main_input_fingerprint as fn

        assert "coverage_census=" in inspect.getsource(fn)

    def test_the_statement_really_does_differ_between_the_two_states(self, monkeypatch):
        """Non-vacuity for the test above: if the switch did NOT change the SQL,
        leaving it out of the fingerprint would have been harmless."""
        from app.tasks.precompute_calibration import _main_futures_sql

        off = _main_futures_sql()
        monkeypatch.setattr(
            "app.tasks.precompute_calibration.COVERAGE_CENSUS_ENABLED", True
        )
        assert _main_futures_sql() != off


# =============================================================================
# 2. A cursor that says why it reset
# =============================================================================
def _raw(**overrides):
    raw = {
        "schema": STAGED_FUTURES_SCHEMA,
        "task": MAIN_BUILD_TASK,
        "unit_key": UNIT_KEY_VM_ID,
        "population_version": "q267",
        "input_fingerprint": "fp-a",
        "generation_fingerprint": "gen-a",
        "owner": "me",
        "lease_expires_at": 0.0,
        "committed_units": ["u1"],
        "unit_results": {"u1": encode_unit_rows([{"bucket_idx": 1}])},
        "terminal": "partial",
    }
    raw.update(overrides)
    return raw


def _decode(raw, *, owner="me", version="q267", input_fp="fp-a", now=100.0):
    return decode_staged_cursor_detailed(
        raw,
        expected_population_version=version,
        expected_input_fingerprint=input_fp,
        expected_generation_fingerprint="gen-a",
        owner=owner,
        generation=9,
        now=now,
    )


class TestTheCursorSaysWhyItReset:
    """Five causes, one stage name. Gotcha #53's shape, in the build's own state.

    The 2026-08-09 18:15Z beat discarded ten banked units and recorded
    ``staged:cursor_invalidate``. Establishing that a deploy's fingerprint change
    was responsible — and not, say, roster drift, which CAL-P016 had just fixed
    and which would have meant CAL-P016 had failed — took reading the decode
    chain and diffing two merges. The cycle before it could not establish it at
    all and attributed the stall to the beat scheduler instead.
    """

    @pytest.mark.parametrize(
        "overrides,expected_action,expected_reason",
        [
            ({"schema": "other/v9"}, INVALIDATE, REASON_SCHEMA),
            ({"task": "some.other.task"}, INVALIDATE, REASON_TASK),
            ({"unit_key": "source"}, INVALIDATE, REASON_UNIT_KEY),
            ({"population_version": "q999"}, INVALIDATE, REASON_POPULATION_VERSION),
            ({"input_fingerprint": "fp-b"}, INVALIDATE, REASON_INPUT_FINGERPRINT),
            ({"committed_units": "not-a-list"}, INVALIDATE, REASON_MALFORMED_UNITS),
        ],
    )
    def test_each_cause_reports_itself(self, overrides, expected_action, expected_reason):
        _cursor, action, reason = _decode(_raw(**overrides))
        assert (action, reason) == (expected_action, expected_reason)

    def test_the_reasons_are_all_distinct(self):
        """A shared token would rebuild the exact ambiguity being removed."""
        causes = [
            {"schema": "other/v9"},
            {"task": "some.other.task"},
            {"unit_key": "source"},
            {"population_version": "q999"},
            {"input_fingerprint": "fp-b"},
            {"committed_units": "not-a-list"},
        ]
        reasons = [_decode(_raw(**c))[2] for c in causes]
        assert len(set(reasons)) == len(reasons)

    def test_the_deploy_case_is_the_one_that_fires_in_production(self):
        """Named separately because it is the finding, not just a branch."""
        _cursor, action, reason = _decode(_raw(input_fingerprint="deployed-new-sql"))
        assert action == INVALIDATE
        assert reason == REASON_INPUT_FINGERPRINT

    def test_a_healthy_resume_says_so_too(self):
        cursor, action, reason = _decode(_raw())
        assert (action, reason) == (RESUME, REASON_RESUMABLE)
        assert cursor.committed_units == ("u1",)

    def test_an_empty_but_valid_cursor_is_fresh_not_invalid(self):
        _cursor, action, reason = _decode(_raw(committed_units=[], unit_results={}))
        assert (action, reason) == (FRESH, REASON_NOTHING_BANKED)

    def test_absent_and_malformed_are_different_facts(self):
        assert _decode(None)[1:] == (FRESH, REASON_ABSENT)
        assert _decode("not a mapping")[1:] == (INVALIDATE, REASON_MALFORMED)

    def test_a_held_lease_reports_the_holder_not_a_defect(self):
        _cursor, action, reason = _decode(_raw(owner="someone-else", lease_expires_at=999.0))
        assert (action, reason) == (REFUSE, REASON_LEASE_HELD)


class TestTheTwoValueFormStillWorks:
    """Every existing caller unpacks two values; none of them should have to change.

    The predicate chain lives in the detailed function ONLY. A second copy of
    "why is this cursor unusable" would be the C14 drift this module refuses
    everywhere else.
    """

    def test_it_agrees_with_the_detailed_form(self):
        for overrides in ({}, {"input_fingerprint": "fp-b"}, {"schema": "x"}):
            two = decode_staged_cursor(
                _raw(**overrides),
                expected_population_version="q267",
                expected_input_fingerprint="fp-a",
                expected_generation_fingerprint="gen-a",
                owner="me",
                generation=9,
                now=100.0,
            )
            three = _decode(_raw(**overrides))
            assert two == three[:2]


# =============================================================================
# 3. The build projects its own convergence
# =============================================================================
class TestTheBuildProjectsItsOwnConvergence:
    """"Will this ever finish" must be readable from one beat's own ledger.

    It was computable before — ``read:futures_unit`` and ``committed_units``
    existed — but in two rows of two different snapshots, with nothing dividing
    one by the other. Both times someone did that division by hand it changed
    the plan, and both times it was a day late.
    """

    def test_the_real_census_on_beat_projects_over_a_hundred_more_beats(self):
        """The 18:15Z beat, exactly. It should have said ~117 on the spot."""
        stages = _project(
            done=1, planned=STAGED_FUTURES_BUCKETS, ran=1,
            unit_ms_total=PROD_UNIT_MS_CENSUS_ON,
        )
        units_per_beat = PROD_USABLE_MS / PROD_UNIT_MS_CENSUS_ON
        assert stages["staged:beats_to_publish"] == math.ceil(127 / units_per_beat)
        assert stages["staged:beats_to_publish"] > 100
        assert stages["staged:unit_ms_mean"] == PROD_UNIT_MS_CENSUS_ON

    def test_the_census_off_beat_projects_a_finishable_build(self):
        """The 16:15Z beat. Same code, same window, ~an order of magnitude fewer
        beats — which is the entire case for the switch being off."""
        stages = _project(
            done=10, planned=STAGED_FUTURES_BUCKETS, ran=10,
            unit_ms_total=PROD_UNIT_MS_CENSUS_OFF * 10,
        )
        assert stages["staged:beats_to_publish"] < 20

    def test_the_two_projections_differ_by_about_ten_times(self):
        on = _project(
            done=1, planned=STAGED_FUTURES_BUCKETS, ran=1,
            unit_ms_total=PROD_UNIT_MS_CENSUS_ON,
        )["staged:beats_to_publish"]
        off = _project(
            done=10, planned=STAGED_FUTURES_BUCKETS, ran=10,
            unit_ms_total=PROD_UNIT_MS_CENSUS_OFF * 10,
        )["staged:beats_to_publish"]
        assert on > off * 5

    def test_a_beat_that_banked_nothing_still_reports_its_counts(self):
        """The most important beat to be able to see is the one that did nothing.

        An absent stage reads as "fine" (gotcha #53), so the counts are recorded
        unconditionally — while the mean is OMITTED rather than guessed, because
        no unit ran to average.
        """
        stages = _project(done=4, planned=128, ran=0, unit_ms_total=0.0)
        assert stages["staged:units_done"] == 4
        assert stages["staged:units_planned"] == 128
        assert stages["staged:units_this_beat"] == 0
        assert "staged:unit_ms_mean" not in stages
        assert "staged:beats_to_publish" not in stages

    def test_a_unit_too_big_for_a_whole_window_reports_minus_one(self):
        """Not a huge number: a DIFFERENT and worse fact.

        If one unit cannot fit in one beat, the build makes no progress at all
        and no arithmetic over "beats" is meaningful. Rounding that to a large
        count would read as merely slow.
        """
        stages = _project(
            done=0, planned=128, ran=1, unit_ms_total=PROD_USABLE_MS * 2,
        )
        assert stages["staged:beats_to_publish"] == -1

    def test_a_complete_build_projects_zero_beats(self):
        stages = _project(done=128, planned=128, ran=1, unit_ms_total=50_000.0)
        assert stages["staged:beats_to_publish"] == 0

    def test_the_projection_is_recorded_by_the_staged_runner(self):
        """Wiring, source-level — driving the real loop needs a live session.

        Placed after the loop and before the completeness check, so a beat that
        ran out of window still reports where it got to.
        """
        import inspect

        from app.tasks.precompute_calibration import _run_staged_futures

        source = inspect.getsource(_run_staged_futures)
        assert "_record_convergence_projection(" in source
        assert source.index("_record_convergence_projection(") < source.index(
            "if not is_complete("
        )


# =============================================================================
# 4. Where the memory goes (CAL-P024c) — the P0's instrument
# =============================================================================
class TestTheBuildReportsItsOwnMemory:
    """The build is hard-killed on a 512MB dyno and a SIGKILL leaves no traceback.

    Alex's diagnosis (2026-08-09) is that the hourly beat fires on schedule and
    dies ~16 min in to a memory kill. What no artifact says is WHERE — and the
    payload build turns out to hold nothing that scales with the 652K-outcome
    population: every read in ``compute_calibration_payload`` is a ``GROUP BY``
    aggregate, the largest bounded by
    ``bucket_idx x source x category x price_moved x is_nonexclusive_bundle``
    at a few thousand rows. So the streaming rewrite has no obvious target in
    that function, and picking one by guess on a P0 is how the wrong thing gets
    rewritten.

    Hence: sample RSS at every stage boundary, so the next beat names the stage
    it died in and the level it reached.
    """

    def test_the_probe_returns_a_plausible_live_reading(self):
        from app.tasks.calibration_main_build import _process_rss_mb

        rss = _process_rss_mb()
        assert rss is not None
        # A pytest process is tens of MB; anything outside this is a units bug,
        # which is the specific failure mode worth guarding (ru_maxrss is bytes
        # on Darwin and kilobytes on Linux — off by 1024 in one direction).
        assert 5 < rss < 5000, f"implausible RSS {rss} MB — check the units"

    def test_an_unavailable_reading_is_none_never_zero(self, monkeypatch):
        """A missing measurement must not be recorded as a comfortable one."""
        import builtins

        import app.tasks.calibration_main_build as mb

        monkeypatch.setattr(
            builtins, "open", lambda *a, **k: (_ for _ in ()).throw(OSError())
        )
        monkeypatch.setitem(__import__("sys").modules, "resource", None)
        assert mb._process_rss_mb() is None

    def test_a_gauge_replaces_and_a_counter_accumulates(self):
        """The distinction the RSS reading depends on.

        ``record_stage`` is a counter — right for durations, and silently wrong
        for a level. An RSS of 400 recorded through it on 128 unit stages would
        publish 51,200.
        """
        from app.utils.calibration_phase_ledger import PhaseLedger

        ledger = PhaseLedger.__new__(PhaseLedger)
        ledger.stages = {}
        for _ in range(128):
            ledger.record_stage("read:futures_unit", 100)
            ledger.record_gauge("rss:at:read:futures_unit", 400)
        assert ledger.stages["read:futures_unit"] == 12_800
        assert ledger.stages["rss:at:read:futures_unit"] == 400

    def test_the_peak_only_ever_climbs(self, monkeypatch):
        import app.tasks.calibration_main_build as mb

        runner, ledger = _rss_runner()
        for reading in (120, 480, 300):
            monkeypatch.setattr(mb, "_process_rss_mb", lambda r=reading: r)
            runner._sample_rss("read:futures_unit")
        assert ledger.stages["rss:peak_mb"] == 480
        # …while the per-stage reading is the LAST one, not the peak: the two
        # answer different questions and collapsing them loses the trajectory.
        assert ledger.stages["rss:at:read:futures_unit"] == 300

    def test_sampling_never_raises_when_the_probe_fails(self, monkeypatch):
        import app.tasks.calibration_main_build as mb

        runner, ledger = _rss_runner()

        def _boom():
            raise RuntimeError("no /proc here")

        monkeypatch.setattr(mb, "_process_rss_mb", _boom)
        runner._sample_rss("read:futures_unit")  # must not raise
        assert "rss:peak_mb" not in ledger.stages

    def test_an_unobtainable_reading_records_nothing_rather_than_zero(self, monkeypatch):
        """None must not become a comfortable 0 MB in the ledger."""
        import app.tasks.calibration_main_build as mb

        runner, ledger = _rss_runner()
        monkeypatch.setattr(mb, "_process_rss_mb", lambda: None)
        runner._sample_rss("read:futures_unit")
        assert ledger.stages == {}

    def test_every_stage_boundary_samples(self):
        """Wiring: the sample must be in the ``finally``, so a stage that RAISES
        — the one most worth knowing the memory of — still reports."""
        import inspect

        from app.tasks.calibration_main_build import PhaseRunner

        source = inspect.getsource(PhaseRunner.stage)
        assert "_sample_rss" in source
        assert source.index("finally:") < source.index("_sample_rss")


class _RssRunner:
    """Just enough PhaseRunner to exercise ``_sample_rss`` in isolation.

    The real method is bound onto this object rather than reimplemented, so the
    tests exercise production code; the probe itself is monkeypatched at module
    level, which is where ``_sample_rss`` actually reads it from.
    """

    def __init__(self, ledger):
        from app.tasks.calibration_main_build import PhaseRunner

        self.ledger = ledger
        self._sample_rss = PhaseRunner._sample_rss.__get__(self)


def _rss_runner():
    from app.utils.calibration_phase_ledger import PhaseLedger

    ledger = PhaseLedger.__new__(PhaseLedger)
    ledger.stages = {}
    return _RssRunner(ledger), ledger
