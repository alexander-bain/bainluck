"""``classify()``/``grade()`` — CAL-P083's carry-withhold specimen grader.

Fable's item 2: *"prove it fires on the NEXT partial beat ... so the insurance
is verified before it's ever needed in anger."* It turned out to have fired in
anger already, at 2026-08-21 07:39:45Z, and the whole risk in reporting that is
credulity — the guard writes a string, and a grader that looks for the string
finds the string.

So the suite is arranged around the ways a firing can be claimed wrongly:

* **crediting the guard for a beat it never ran on.** ``build_checkpoint`` is
  reachable only when the terminal is NOT ``complete``, and a beat whose futures
  phase never completed has no carry to withhold. That beat is a NEGATIVE
  CONTROL, and if it were counted as a firing the token would be indistinguishable
  from a label applied to every unhappy beat. CAL-P082's honest finding — the
  guard has never fired — is only meaningful because that distinction holds.
* **missing the guard being BROKEN.** Reachable, futures completed, rebuild in
  flight, and no withhold: that is the defect, and it has to outrank any firing
  elsewhere in the same window rather than be averaged with it.
* **claiming an effect that was not observed.** A firing whose following beat was
  never captured must not render as a working guard; unobserved is not success.

The predicate operands are asserted too, not just the verdict. The guard's
condition is ``units_done < units_planned``, and an instrument that reports "the
guard fired" purely from the token it wrote can only ever agree with the guard —
including when the guard is wrong.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "grade_carry_withhold",
    Path(__file__).resolve().parent.parent / "scripts" / "grade_carry_withhold.py",
)
_MOD = importlib.util.module_from_spec(_SPEC)
sys.modules["grade_carry_withhold"] = _MOD
_SPEC.loader.exec_module(_MOD)

classify = _MOD.classify
grade = _MOD.grade
WITHHELD = _MOD.WITHHELD

_ALL_PHASES = ["futures", "sports", "diagnostics", "aggregate", "serialize_gate_publish"]


def _beat(gen, stamp, *, terminal, banked, completed, done=95, planned=128,
          carried=(), this_beat=7, units_banked=95, done_gauge=True):
    stages = {
        "staged:units_planned": planned,
        "staged:units_this_beat": this_beat,
        "staged:units_banked": units_banked,
    }
    if done_gauge and done is not None:
        stages["staged:units_done"] = done
    row = {
        "generation": gen,
        "generated_at": stamp,
        "terminal": terminal,
        "banked": banked,
        "completed_required": list(completed),
        "carried": list(carried),
        "stages": stages,
    }
    if not done_gauge and done is not None:
        row["unit_costs"] = {"futures": {"units_done": done, "units_total": planned}}
    return row


# The production specimen, verbatim in shape.
FIRING = _beat(
    1_787_297_985_432, "2026-08-21T07:39:45+00:00",
    terminal="failed", banked={"futures": WITHHELD}, completed=["futures"],
    done=95, units_banked=95, done_gauge=False,
)
# The production negative control, verbatim in shape: cancelled before futures
# finished, so there was nothing to withhold.
CONTROL = _beat(
    1_787_264_491_343, "2026-08-20T22:21:31+00:00",
    terminal="cancelled", banked=None, completed=[], done=None, planned=None,
    units_banked=24,
)
# The beat after the firing: futures NOT carried, unit loop ran.
AFTER = _beat(
    1_787_304_789_916, "2026-08-21T09:33:09+00:00",
    terminal="complete", banked={}, completed=_ALL_PHASES,
    done=106, carried=["sports"], this_beat=6, units_banked=106,
)


class TestClassification:
    def test_the_production_specimen_is_a_firing(self):
        out = classify(FIRING)
        assert out["state"] == "withheld"
        assert out["banked"]["futures"] == WITHHELD

    def test_the_firing_carries_its_predicate_operands_not_just_the_token(self):
        out = classify(FIRING)
        assert out["units_done"] == 95
        assert out["units_planned"] == 128
        assert out["rebuild_in_flight"] is True
        assert out["futures_completed"] is True

    def test_a_complete_beat_is_unreachable_not_a_silent_failure(self):
        """The guard cannot run here, so this beat is evidence of nothing.

        Fifteen of the seventeen production beats are this state. Folding them
        into a denominator would make the guard look 1-for-16 when it is 1-for-1
        on the beats it can reach.
        """
        assert classify(AFTER)["state"] == "guard_unreachable_complete"

    def test_nothing_to_bank_is_the_negative_control_not_a_firing(self):
        out = classify(CONTROL)
        assert out["state"] == "nothing_to_bank"
        assert out["futures_completed"] is False

    def test_a_reachable_beat_that_should_have_fired_and_did_not_is_a_defect(self):
        broken = _beat(
            5, "2026-08-21T07:39:45+00:00",
            terminal="failed", banked={"futures": "stored"}, completed=["futures"],
            done=95,
        )
        assert classify(broken)["state"] == "expected_firing_absent"

    def test_banking_futures_with_no_units_outstanding_is_legitimate(self):
        """The guard is scoped to the in-flight case; a finished rebuild carries.

        ``done == planned`` means there is nothing left to re-stage, so banking
        the carry costs nothing. This must not read as the guard failing.
        """
        done_rebuild = _beat(
            6, "2026-08-21T07:39:45+00:00",
            terminal="failed", banked={"futures": "stored"}, completed=["futures"],
            done=128, planned=128,
        )
        out = classify(done_rebuild)
        assert out["rebuild_in_flight"] is False
        assert out["state"] == "banked_rebuild_not_in_flight"


class TestOperandProvenance:
    def test_the_gauge_is_preferred_when_present(self):
        with_gauge = _beat(
            7, "2026-08-21T07:39:45+00:00",
            terminal="failed", banked={"futures": WITHHELD}, completed=["futures"],
            done=95, done_gauge=True,
        )
        assert classify(with_gauge)["units_done_source"] == "gauge"

    def test_a_pre_p083_capture_falls_back_to_unit_costs_and_says_so(self):
        """The overnight capture predates the ``staged:units_done`` gauge.

        The number is recoverable from ``unit_costs``, and the fallback is
        LABELLED rather than silent — a derived operand and a recorded one are
        not the same evidence, and the report has to be able to say which it had.
        """
        out = classify(FIRING)
        assert out["units_done"] == 95
        assert out["units_done_source"] == "unit_costs"

    def test_an_unrecoverable_operand_leaves_in_flight_unknown_not_false(self):
        """Gotcha #53: the emptier reading must not become the fact.

        ``False`` here would assert the rebuild had finished, which would then
        classify a real firing as illegitimate.
        """
        blind = _beat(
            8, "2026-08-21T07:39:45+00:00",
            terminal="failed", banked=None, completed=[], done=None, planned=None,
        )
        assert classify(blind)["rebuild_in_flight"] is None


class TestGrade:
    def test_the_production_window_grades_as_fired(self):
        result = grade([CONTROL, FIRING, AFTER])
        assert result["verdict"] == "fired"
        assert len(result["firings"]) == 1
        assert result["firings"][0]["generation"] == FIRING["generation"]

    def test_the_negative_control_is_required_reporting(self):
        result = grade([CONTROL, FIRING, AFTER])
        assert result["negative_control_present"] is True
        assert result["counts"]["nothing_to_bank"] == 1

    def test_the_effect_on_the_following_beat_is_measured(self):
        result = grade([CONTROL, FIRING, AFTER])
        effect = result["firings"][0]["effect"]
        assert effect["observed"] is True
        assert effect["futures_not_carried"] is True
        assert effect["unit_loop_ran"] is True
        assert (effect["bank_before"], effect["bank_after"]) == (95, 106)

    def test_the_pre_fix_defect_shape_is_not_scored_as_a_working_effect(self):
        """The 2026-08-20 20:15Z beat this guard was written for.

        ``carried: ['futures','sports']`` with ``units_this_beat: 0`` — a whole
        beat of re-stage bought for one generation read. If a firing were ever
        followed by THAT, the guard did not work, and the grade must show it.
        """
        # Generation ids are epoch-millis and the grader orders by them, so a
        # "following" beat must genuinely follow. A small synthetic id here
        # sorted BEFORE the real specimen and silently made this an
        # effect-unobserved case instead of the regression it is testing.
        regressed = _beat(
            FIRING["generation"] + 7_000_000, "2026-08-21T09:33:09+00:00",
            terminal="complete", banked={}, completed=_ALL_PHASES,
            done=95, carried=["futures", "sports"], this_beat=0, units_banked=95,
        )
        result = grade([FIRING, regressed])
        effect = result["firings"][0]["effect"]
        assert effect["futures_not_carried"] is False
        assert effect["unit_loop_ran"] is False

    def test_an_unobserved_effect_is_not_a_success(self):
        result = grade([CONTROL, FIRING])
        assert result["firings"][0]["effect"]["observed"] is False

    def test_no_firing_is_the_cal_p082_state_and_a_real_answer(self):
        result = grade([AFTER, CONTROL])
        assert result["verdict"] == "no_firing"
        assert "CAL-P082" in result["reason"] or "CAL-P082" in result["reason"].upper()

    def test_a_guard_defect_outranks_a_firing_in_the_same_window(self):
        broken = _beat(
            FIRING["generation"] + 10_000_000, "2026-08-21T10:32:16+00:00",
            terminal="failed", banked={"futures": "stored"}, completed=["futures"],
            done=100,
        )
        result = grade([FIRING, AFTER, broken])
        assert result["verdict"] == "guard_defect"

    def test_beats_are_ordered_by_generation_not_file_order(self):
        result = grade([AFTER, FIRING, CONTROL])
        assert [b["generation"] for b in result["beats"]] == sorted(
            b["generation"] for b in result["beats"]
        )
        assert result["firings"][0]["effect"]["next_generation"] == AFTER["generation"]
