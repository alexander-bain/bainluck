"""``grade_consecutive()`` — the pure half of CAL-P082's per-beat grader.

The bar this instrument exists to answer is Fable's, verbatim: *">= 1 unit
banked per unit-loop beat, verified across >= 3 consecutive beats from the
ledger -- not one."* Three words in that sentence are load-bearing and each one
is a way the previous instrument got the wrong answer:

* **beat** — ``verify_rolling_restage`` samples on a wall clock, so two reads
  eight minutes apart inside one inter-beat gap graded as two samples. That is
  how CAL-P081 reported ``rebuild_advancing`` FAIL at ``[13, 13]``: the finding
  was real, the sample count was one.
* **consecutive** — a beat that was never sampled leaves no hole in a file. Two
  rows an hour apart in the FILE can be two beats or two of five, and gotcha #53
  is precisely that the emptier reading must not be assumed.
* **>= 1** — ``len(set(banked)) > 1`` is satisfied by 13 -> 14 over four hours.

So the suite is arranged around the states that must NOT grade PASS, and the
sharpest of them is the third: a genuinely unmeasurable window has to be
distinguishable from a stalled one, in both directions. An unmeasured beat
graded FAIL sends someone to revert a working fix; a stalled beat graded
"unmeasurable" is #2007 all over again.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "sample_calibration_beats",
    Path(__file__).resolve().parent.parent / "scripts" / "sample_calibration_beats.py",
)
_MOD = importlib.util.module_from_spec(_SPEC)
sys.modules["sample_calibration_beats"] = _MOD
_SPEC.loader.exec_module(_MOD)

grade_consecutive = _MOD.grade_consecutive
beat_row = _MOD.beat_row
BEAT_PERIOD_S = _MOD.BEAT_PERIOD_S


# The real cadence, so nothing here depends on a clock. Beats land hourly at
# :15 and the ledger is written when the build FINISHES, ~18 min later.
_HOURS = {
    18: "2026-08-20T18:22:29+00:00",
    19: "2026-08-20T19:33:11+00:00",
    20: "2026-08-20T20:34:02+00:00",
    21: "2026-08-20T21:33:07+00:00",
    22: "2026-08-20T22:33:40+00:00",
}


def _beat(hour, *, units, banked, carried=(), generation=None, terminal="complete",
          stamp=None):
    return {
        "generation": generation if generation is not None else 1_787_000_000 + hour,
        "generated_at": stamp or _HOURS[hour],
        "complete": True,
        "terminal": terminal,
        "carried": list(carried),
        "stages": {
            "staged:units_this_beat": units,
            "staged:units_banked": banked,
            "staged:units_planned": 128,
        },
    }


# ---------------------------------------------------------------------------
# the bar, met
# ---------------------------------------------------------------------------

def test_three_adjacent_beats_each_banking_a_unit_is_the_pass():
    rows = [
        _beat(19, units=8, banked=13),
        _beat(20, units=6, banked=19),
        _beat(21, units=7, banked=26),
    ]
    verdict = grade_consecutive(rows)
    assert verdict["pass"] is True
    assert verdict["reason"] == "advancing"
    assert verdict["beats_observed"] == 3
    assert "[8, 6, 7]" in verdict["detail"]


def test_one_unit_a_beat_is_enough_because_the_bar_says_at_least_one():
    """The bar is ">= 1", not "healthy". A slow build is still an advancing one,
    and a grader that quietly required more would report a false RED against a
    build that is converging — which is the exact defect CAL-P081 removed from
    ``drift_falling``."""
    rows = [_beat(19, units=1, banked=14), _beat(20, units=1, banked=15),
            _beat(21, units=1, banked=16)]
    assert grade_consecutive(rows)["pass"] is True


def test_a_finish_time_that_jitters_inside_the_slack_is_still_adjacent():
    """The ledger is stamped at FINISH, and finish time moves with the work
    done: the measured spread on 2026-08-20 was ~18 to ~22 minutes. Adjacency
    must survive that or every real window reads as a gap."""
    rows = [
        _beat(19, units=8, banked=13, stamp="2026-08-20T19:20:00+00:00"),
        _beat(20, units=6, banked=19, stamp="2026-08-20T20:41:00+00:00"),
        _beat(21, units=7, banked=26, stamp="2026-08-20T21:19:00+00:00"),
    ]
    assert grade_consecutive(rows)["pass"] is True


# ---------------------------------------------------------------------------
# the bar, missed — the real FAIL
# ---------------------------------------------------------------------------

def test_the_carried_beat_is_a_stall_not_a_gap():
    """CAL-P081's specimen: the 20:15Z beat published successfully, banked ZERO
    units, and carried the futures phase — so ``_run_staged_futures`` never ran.
    A published beat that banked nothing is a FAILURE of the bar, and it must not
    be excused as unmeasurable just because the beat had a reason."""
    rows = [
        _beat(19, units=8, banked=13),
        _beat(20, units=0, banked=13, carried=("futures", "sports")),
        _beat(21, units=7, banked=20),
    ]
    verdict = grade_consecutive(rows)
    assert verdict["pass"] is False
    assert verdict["reason"] == "stalled"
    assert "[8, 0, 7]" in verdict["detail"]
    assert ["futures", "sports"] in verdict["carried_in_window"]


def test_a_stall_after_a_healthy_stretch_is_not_rescued_by_its_own_history():
    """The graded window is the LAST `minimum` beats. Averaging over everything
    ever seen is how a rail that has stopped keeps reporting the day it worked."""
    rows = [
        _beat(18, units=6, banked=5),
        _beat(19, units=8, banked=13),
        _beat(20, units=5, banked=18),
        _beat(21, units=0, banked=18, carried=("futures",)),
        _beat(22, units=0, banked=18, carried=("futures",)),
    ]
    # The first three beats would grade PASS on their own — [6, 8, 5]. Only the
    # LAST three, [5, 0, 0], describe the rail as it is now.
    assert grade_consecutive(rows[:3])["pass"] is True
    verdict = grade_consecutive(rows)
    assert verdict["pass"] is False
    assert verdict["reason"] == "stalled"
    assert verdict["beats_observed"] == 5
    assert "[5, 0, 0]" in verdict["detail"]


# ---------------------------------------------------------------------------
# UNMEASURABLE — and it must be its own answer, in both directions
# ---------------------------------------------------------------------------

def test_two_beats_cannot_answer_a_three_beat_question():
    rows = [_beat(20, units=6, banked=19), _beat(21, units=7, banked=26)]
    verdict = grade_consecutive(rows)
    assert verdict["pass"] is None
    assert verdict["reason"] == "insufficient"


def test_cal_p081s_actual_reading_is_ONE_beat_and_grades_unmeasurable():
    """The frozen negative control, in its true shape. CAL-P081 took two samples
    of ``/api/calibration`` 8 minutes apart and graded ``rebuild_advancing``
    FAIL on ``[13, 13]``. Both samples were the SAME beat. The stall was real —
    it is `test_the_carried_beat_is_a_stall_not_a_gap` above, proved from the
    ledger — but two reads of one generation are one observation, and this
    grader must say so rather than inherit a verdict it cannot support."""
    same_beat = _beat(20, units=0, banked=13, carried=("futures", "sports"))
    verdict = grade_consecutive([dict(same_beat), dict(same_beat)])
    assert verdict["pass"] is None
    assert verdict["reason"] == "insufficient"
    assert verdict["beats_observed"] == 1, "one generation seen twice is one beat"


def test_a_missing_beat_is_a_GAP_and_never_a_pass():
    """An unsampled beat leaves no hole in the file. If 20:15Z is absent, 19 and
    21 sit adjacent in the rows and an hour apart is not a period apart. Grading
    that PASS would certify a window containing a beat nobody looked at."""
    rows = [
        _beat(18, units=6, banked=5),
        _beat(19, units=8, banked=13),
        _beat(21, units=7, banked=20),
    ]
    verdict = grade_consecutive(rows)
    assert verdict["pass"] is None
    assert verdict["reason"] == "gap"
    assert verdict["gaps"], "the offending pair must be named, not just counted"
    assert verdict["gaps"][0]["expected_s"] == BEAT_PERIOD_S


def test_a_gap_does_not_get_reported_as_a_stall():
    """The inverse of the case above, and the more expensive one. A window that
    could not be measured must never send someone to revert a working fix — so
    ``gap`` grades ``None``, not ``False``."""
    rows = [
        _beat(18, units=6, banked=5),
        _beat(19, units=8, banked=13),
        _beat(21, units=7, banked=20),
    ]
    assert grade_consecutive(rows)["pass"] is not False


def test_an_unreadable_gauge_is_unmeasurable_rather_than_zero():
    """``staged:units_this_beat`` absent is "we did not record it", which is a
    different fact from "it banked nothing" — gotcha #53, applied to a gauge."""
    rows = [_beat(19, units=8, banked=13), _beat(20, units=6, banked=19),
            _beat(21, units=None, banked=26)]
    verdict = grade_consecutive(rows)
    assert verdict["pass"] is None
    assert verdict["reason"] == "gauge_missing"


def test_no_beats_at_all_is_unmeasurable():
    verdict = grade_consecutive([])
    assert verdict["pass"] is None
    assert verdict["reason"] == "insufficient"
    assert verdict["beats_observed"] == 0


# ---------------------------------------------------------------------------
# knobs and shaping
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("minimum", [2, 3, 4])
def test_the_minimum_is_honoured_exactly(minimum):
    rows = [_beat(h, units=5, banked=5 * i) for i, h in enumerate(_HOURS, start=1)]
    assert grade_consecutive(rows[:minimum - 1], minimum=minimum)["pass"] is None
    assert grade_consecutive(rows[:minimum], minimum=minimum)["pass"] is True


def test_beat_row_keeps_the_carry_and_the_gauges_the_grader_reads():
    """A reducer that dropped ``carried`` would make every stall look causeless,
    and CAL-P081's whole diagnosis was the carry."""
    record = {
        "generation": 1787261587576,
        "generated_at": "2026-08-20T21:33:07.576173+00:00",
        "complete": True,
        "payload": {
            "terminal": "complete",
            "carried": ["futures", "sports"],
            "elapsed_ms": 1087069,
            "input_fingerprint": "b65faaacdc240b3b256934fcad528db1",
            "stages": {"staged:units_this_beat": 7, "staged:units_banked": 20,
                       "rss:peak_mb": 562},
            "stage_counts": {"read:futures_unit": 7, "publish_gate": 1},
        },
    }
    row = beat_row(record, served={"rebuild_units_banked": 20})
    assert row["carried"] == ["futures", "sports"]
    assert row["stages"]["staged:units_this_beat"] == 7
    assert row["input_fingerprint"] == "b65faaacdc240b3b256934fcad528db1"
    assert "rss:peak_mb" not in row["stages"], "only the graded gauges are lifted"
    assert row["staged_stage_counts"] == {}, "stage_counts is filtered to staged:*"
    assert row["served"]["rebuild_units_banked"] == 20


def test_rows_are_ordered_by_generation_not_by_file_position():
    """A sampler restart can append an older read after a newer one. Ordering by
    file position would then invent a gap, or worse, a fake adjacency."""
    rows = [_beat(21, units=7, banked=26), _beat(19, units=8, banked=13),
            _beat(20, units=6, banked=19)]
    verdict = grade_consecutive(rows)
    assert verdict["pass"] is True
    assert verdict["graded_window"] == [1_787_000_019, 1_787_000_020, 1_787_000_021]


def test_the_sample_clock_is_derived_and_never_lands_in_the_past():
    """gotcha #44 — an anchor that branches on the clock is the defect. The next
    sample is always strictly ahead, at every hour of the day."""
    import datetime

    for hour in range(24):
        for minute in (0, 14, 39, 40, 41, 59):
            now = datetime.datetime(2026, 8, 20, hour, minute, 30,
                                    tzinfo=datetime.timezone.utc)
            delay = _MOD._seconds_to_next_sample(now, 40)
            assert delay >= 30
            assert (now + datetime.timedelta(seconds=delay)) > now
            assert delay <= 3600
