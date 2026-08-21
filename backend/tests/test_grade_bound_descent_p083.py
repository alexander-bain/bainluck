"""``grade()`` — CAL-P083's bound-descent grader, over the production pair.

Fable's item 1 is a quotation request: *"the bound's first descent gets quoted
with the beat's own generation id."* Everything sharp about that sentence is in
the words around "descent", and each one is a way to quote a true number that
means the wrong thing:

* **first** — the bound is a SAWTOOTH, not a ramp. It drops to the tight floor
  on the beat that promotes a freshly-built census and climbs again as the
  roster moves under it. The production observation this suite is built from is
  ``100.0 -> 0.5 -> 85.9375 -> 100.0`` across four adjacent beats. A grader that
  reported the minimum, or the latest, would quote the program's best number and
  its worst number respectively, and neither is the descent.
* **descent** — a bound can fall because a new census is being SERVED
  (a promotion: ``served_at`` moves) or because the same bank was re-measured
  against a quieter roster. Only the first is what #2007 has waited for, so an
  unattributed dip must not be reported as one.
* **the beat's own** — the id has to be the id of the beat that DID it, which is
  the later of the pair, not the one whose bound is being left behind.

And the finding that governs how the number can be used at all is not the
descent but its lifetime: a trough one beat wide bounds the window in which
Gate 0 can be run against a tight bound. So ``held`` is asserted in both
directions, because "it descended" and "it is down" are different claims and
the report has to be able to tell them apart.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "grade_bound_descent",
    Path(__file__).resolve().parent.parent / "scripts" / "grade_bound_descent.py",
)
_MOD = importlib.util.module_from_spec(_SPEC)
sys.modules["grade_bound_descent"] = _MOD
_SPEC.loader.exec_module(_MOD)

grade = _MOD.grade
grade_beat = _MOD.grade_beat

# The real production sequence of 2026-08-21, kept as the fixture spine so the
# suite fails if the disclosure/tolerance pair ever stops reproducing a beat
# this program has already quoted in a report.
_PROMOTION_EPOCH = 1_787_315_330
_PRIOR_EPOCH = 1_787_250_149


def _beat(gen, stamp, *, served_at, drifted, units=128, uncheckable=0,
          terminal="complete", rebuild_banked=8):
    return {
        "generation": gen,
        "generated_at": stamp,
        "terminal": terminal,
        "carried": [],
        "stages": {
            "staged:served_units": units,
            "staged:served_drifted": drifted,
            "staged:served_drift_uncheckable": uncheckable,
            "staged:served_at": served_at,
            "staged:units_banked": rebuild_banked,
            "staged:units_this_beat": 8,
        },
    }


def _saturated(gen, stamp):
    return _beat(gen, stamp, served_at=_PRIOR_EPOCH, drifted=128)


PROMOTION = _beat(
    1_787_315_424_367, "2026-08-21T12:30:24+00:00",
    served_at=_PROMOTION_EPOCH, drifted=0, rebuild_banked=0,
)
RECLIMB = _beat(
    1_787_319_343_481, "2026-08-21T13:35:43+00:00",
    served_at=_PROMOTION_EPOCH, drifted=110,
)
RESATURATED = _beat(
    1_787_323_095_513, "2026-08-21T14:38:15+00:00",
    served_at=_PROMOTION_EPOCH, drifted=128, rebuild_banked=16,
)


class TestBoundArithmetic:
    """The bound comes from production, so these pin what production says."""

    def test_fully_drifted_bank_saturates_at_the_scale(self):
        out = grade_beat(_saturated(1, "2026-08-21T11:36:17+00:00"))
        assert out["tolerance_pp"] == pytest.approx(100.0)

    def test_undrifted_bank_lands_on_the_tight_floor_not_zero(self):
        # 0.0 would be the arithmetic answer and the wrong one: agreement is
        # never claimed tighter than the floor, because a census can be
        # undrifted and still not bit-identical to a fresh fold.
        out = grade_beat(PROMOTION)
        assert out["tolerance_pp"] == pytest.approx(0.5)

    def test_partial_drift_scales_linearly(self):
        out = grade_beat(RECLIMB)
        assert out["tolerance_pp"] == pytest.approx(85.9375)

    def test_uncheckable_units_widen_the_bound_they_do_not_shrink_it(self):
        """CAL-P069's failure, as an assertion.

        Six units published as ``drifted: 0`` because nothing could check them.
        An unmeasurable remainder has to push the bound UP — the direction that
        cannot manufacture a pass — so an otherwise-clean bank with unreadable
        units must NOT read as the tight floor.
        """
        blind = _beat(
            9, "2026-08-21T12:30:24+00:00",
            served_at=_PROMOTION_EPOCH, drifted=0, uncheckable=6,
        )
        assert grade_beat(blind)["tolerance_pp"] == pytest.approx(100.0 * 6 / 128)
        assert grade_beat(blind)["tolerance_pp"] > grade_beat(PROMOTION)["tolerance_pp"]


class TestDescent:
    def test_finds_the_descent_and_names_the_later_beat(self):
        result = grade([_saturated(1, "2026-08-21T11:36:17+00:00"), PROMOTION])
        assert result["verdict"] == "descent"
        d = result["descent"]
        # The id quoted is the beat that DID it, not the one it left behind.
        assert d["to_generation"] == 1_787_315_424_367
        assert d["from_tolerance_pp"] == pytest.approx(100.0)
        assert d["to_tolerance_pp"] == pytest.approx(0.5)
        assert d["at_tight_floor"] is True

    def test_attributes_a_served_at_move_to_a_promotion(self):
        result = grade([_saturated(1, "2026-08-21T11:36:17+00:00"), PROMOTION])
        assert result["descent"]["attribution"] == "promotion"

    def test_refuses_to_call_a_same_bank_dip_a_promotion(self):
        """A quieter roster is not a new census.

        Same ``served_at``, less drift. The bound genuinely fell and the grader
        genuinely reports a descent — but calling it a promotion would tell a
        reader the rebuild had published, which is the claim #2007 tracks.
        """
        quieter = _beat(
            2, "2026-08-21T13:35:43+00:00", served_at=_PRIOR_EPOCH, drifted=64,
        )
        result = grade([_saturated(1, "2026-08-21T11:36:17+00:00"), quieter])
        assert result["verdict"] == "descent"
        assert result["descent"]["attribution"] == "drift_remeasurement"

    def test_first_descent_wins_over_a_later_deeper_one(self):
        deeper = _beat(
            1_787_326_000_000, "2026-08-21T15:40:00+00:00",
            served_at=1_787_326_000, drifted=0,
        )
        result = grade([
            _saturated(1, "2026-08-21T11:36:17+00:00"),
            PROMOTION, RECLIMB, RESATURATED, deeper,
        ])
        assert result["descent"]["to_generation"] == PROMOTION["generation"]


class TestHeld:
    """"It descended" and "it is down" are different claims."""

    def test_a_one_beat_trough_does_not_count_as_held(self):
        result = grade([
            _saturated(1, "2026-08-21T11:36:17+00:00"),
            PROMOTION, RECLIMB, RESATURATED,
        ])
        d = result["descent"]
        assert d["held"] is False
        assert d["beats_observed_after"] == 2
        assert [a["tolerance_pp"] for a in d["tolerance_pp_after"]] == [
            pytest.approx(85.9375), pytest.approx(100.0)
        ]

    def test_a_descent_with_nothing_after_it_is_not_held_either(self):
        """Unobserved is not stable.

        One beat at the floor and no later beat says nothing about whether it
        stays there, and the report must not be able to render that silence as
        a hold.
        """
        result = grade([_saturated(1, "2026-08-21T11:36:17+00:00"), PROMOTION])
        assert result["descent"]["held"] is False
        assert result["descent"]["beats_observed_after"] == 0

    def test_a_descent_that_stays_down_is_held(self):
        stays = _beat(
            1_787_319_343_481, "2026-08-21T13:35:43+00:00",
            served_at=_PROMOTION_EPOCH, drifted=0,
        )
        result = grade([
            _saturated(1, "2026-08-21T11:36:17+00:00"), PROMOTION, stays,
        ])
        assert result["descent"]["held"] is True


class TestRefusals:
    def test_no_descent_is_a_result_not_an_error(self):
        result = grade([
            _saturated(1, "2026-08-21T10:32:16+00:00"),
            _saturated(2, "2026-08-21T11:36:17+00:00"),
        ])
        assert result["verdict"] == "no_descent"

    def test_a_single_beat_cannot_be_a_descent(self):
        result = grade([PROMOTION])
        assert result["verdict"] == "unmeasurable"
        assert "fewer_than_two" in result["reason"]

    def test_an_unreadable_bank_is_unmeasurable_not_a_clean_bound(self):
        """Gotcha #53: the emptier reading must never become the fact.

        A ledger row with no served bank at all has no bound. Grading it as one
        end of a descent would invent the very number the gate is checking.
        """
        broken = {
            "generation": 3, "generated_at": "2026-08-21T13:35:43+00:00",
            "stages": {},
        }
        assert grade_beat(broken)["tolerance_pp"] is None
        result = grade([broken, PROMOTION])
        assert result["verdict"] == "unmeasurable"

    def test_rows_are_graded_in_generation_order_not_file_order(self):
        result = grade([RECLIMB, PROMOTION, _saturated(1, "2026-08-21T11:36:17+00:00")])
        assert result["verdict"] == "descent"
        assert result["descent"]["to_generation"] == PROMOTION["generation"]


class TestDeterminism:
    def test_the_grade_does_not_move_with_the_wall_clock(self):
        """Gotcha #44, this program's most-repeated self-inflicted wound.

        ``build_disclosure`` takes a ``now`` and derives ``staged_age_s`` from
        it. The grader pins it to the beat's own stamp, so a report quoted today
        re-derives identically tomorrow.
        """
        rows = [_saturated(1, "2026-08-21T11:36:17+00:00"), PROMOTION, RECLIMB]
        first = grade(rows)
        second = grade(rows)
        assert first["bound_series_pp"] == second["bound_series_pp"]
        assert first["descent"] == second["descent"]
