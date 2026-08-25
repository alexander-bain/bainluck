"""CAL-P093 — the calibration-truth eligibility twin on the cohort-cell census.

WHAT THIS DEFENDS, stated as the finding rather than as the code.

``artifacts/subcohort2/SUBCOHORT_DIAGNOSIS.md`` ranks the calibration hill-climb
queue by each cell's ``ece_all``. Measured 2026-08-24 against production, cell 1
(``basketball/quantity``) reads **24.27 pp over n=13,067** on that metric and
**5.73 pp over n=2,104** when restricted to legs whose ``resolution_source`` may
grade a published forecast. The 18.54 pp difference is not calibration: it is
rows the published curve **already excludes** at ``precompute_calibration``, the
largest single block being 1,690 ``pass2_loser`` markets that are priced
coherently (mean pair sum 0.9954) and carry **zero winning legs**.

So the queue was ranked on a number that includes rows no user's curve contains.
The fix is a second number, not a redefinition of the first — ``ece_all`` still
mirrors ``GET /api/admin/cohort-provenance-split`` exactly.

Every test here is about a way the twin could be quietly WRONG rather than
absent, because an eligibility twin that silently equals ``ece_all`` is worse
than no twin: it certifies the ranking it was built to correct.

No re-grade anywhere (gotcha #21): the poison cohort is reported OUT of the
eligible twin and left exactly where it sits.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from app.utils.cohort_cell_census import (
    CENSUS_SCHEMA,
    GRADE_COMPLETE,
    GRADE_INCOMPLETE,
    TRUTH_ELIGIBLE,
    TRUTH_INELIGIBLE,
    bin_key,
    build_report,
    fold_page,
    parse_bin_key,
)


def _row(*, grade, truth, b, n, sum_prob, winners, league="basketball",
         market_type="quantity"):
    return SimpleNamespace(
        league=league,
        market_type=market_type,
        grade=grade,
        truth=truth,
        bin=b,
        n=n,
        sum_prob=sum_prob,
        winners=winners,
    )


def _report(rows, *, cell="basketball/quantity", n_markets=10):
    acc: dict = {}
    fold_page(acc, rows)
    return build_report(
        accumulator=acc,
        roster_totals={cell: n_markets},
        paged_totals={cell: n_markets},
        complete=True,
        elapsed_s=1.0,
        pages_done=1,
    )["cells"][0]


class TestKeyShape:
    def test_truth_has_no_default_so_a_stale_caller_cannot_collapse_the_axis(self):
        """A default would let v1-shaped code fold every row into one class, and
        ``ece_eligible`` would then equal ``ece_all`` — the wrong number wearing
        the right name. It must be a TypeError, loudly, at the call."""
        with pytest.raises(TypeError):
            bin_key("basketball", "quantity", GRADE_COMPLETE, 3)  # type: ignore[call-arg]

    def test_v1_four_part_key_raises_rather_than_being_upgraded(self):
        """A short key reaching the parser means something bypassed the schema
        guard. Inventing the missing component is how ineligible rows get
        attributed to the eligible twin."""
        with pytest.raises(ValueError):
            parse_bin_key("basketball\x1fquantity\x1fcomplete\x1f3")

    def test_schema_bumped_so_a_persisted_v1_checkpoint_is_refused(self):
        """The worker reads with ``expected_version=CENSUS_SCHEMA``. If the
        version had not moved, a v1 checkpoint would be resumed and its 4-part
        keys would blow up mid-fold — after the run had reported progress."""
        assert CENSUS_SCHEMA == "cohort-cell-census/v2"

    def test_the_two_classes_do_not_merge_in_the_accumulator(self):
        acc: dict = {}
        fold_page(acc, [_row(grade=GRADE_COMPLETE, truth=TRUTH_ELIGIBLE,
                             b=5, n=4, sum_prob=2.0, winners=2)])
        fold_page(acc, [_row(grade=GRADE_COMPLETE, truth=TRUTH_INELIGIBLE,
                             b=5, n=6, sum_prob=3.0, winners=0)])
        assert len(acc) == 2
        assert acc[bin_key("basketball", "quantity", GRADE_COMPLETE, 5,
                           TRUTH_ELIGIBLE)]["n"] == 4
        assert acc[bin_key("basketball", "quantity", GRADE_COMPLETE, 5,
                           TRUTH_INELIGIBLE)]["n"] == 6

    def test_key_still_survives_a_json_round_trip(self):
        acc = {bin_key("basketball", "quantity", GRADE_COMPLETE, 5,
                       TRUTH_ELIGIBLE): {"n": 2.0}}
        assert json.loads(json.dumps(acc)) == acc

    def test_fold_raises_on_a_row_that_lost_the_column(self):
        """Plain attribute access, not ``getattr(..., default)``. A defaulted
        row lands the whole page in one class and the twin looks measured."""
        bad = SimpleNamespace(league="basketball", market_type="quantity",
                              grade=GRADE_COMPLETE, bin=5, n=1, sum_prob=0.5,
                              winners=0)
        with pytest.raises(AttributeError):
            fold_page({}, [bad])


class TestTwinSeparatesTheDefect:
    def test_the_pass2_loser_shape_moves_ece_all_but_not_ece_eligible(self):
        """The production shape, in miniature: a coherently-priced bin where the
        eligible legs resolve ~as priced, plus an ineligible block at the same
        price with ZERO winners. ``ece_all`` is dragged; ``ece_eligible`` is not.
        """
        cell = _report([
            _row(grade=GRADE_COMPLETE, truth=TRUTH_ELIGIBLE,
                 b=5, n=100, sum_prob=50.0, winners=50),
            _row(grade=GRADE_COMPLETE, truth=TRUTH_INELIGIBLE,
                 b=5, n=100, sum_prob=50.0, winners=0),
        ])
        assert cell["ece_eligible"] == pytest.approx(0.0, abs=0.01)
        assert cell["ece_all"] == pytest.approx(25.0, abs=0.01)
        assert cell["n_eligible"] == 100
        assert cell["n_all"] == 200
        assert cell["eligible_share"] == pytest.approx(0.5)

    def test_gap_eligible_is_reported_separately(self):
        cell = _report([
            _row(grade=GRADE_COMPLETE, truth=TRUTH_ELIGIBLE,
                 b=8, n=100, sum_prob=80.0, winners=60),
            _row(grade=GRADE_COMPLETE, truth=TRUTH_INELIGIBLE,
                 b=8, n=100, sum_prob=80.0, winners=0),
        ])
        assert cell["gap_eligible"] == pytest.approx(20.0, abs=0.01)
        assert cell["gap_all"] == pytest.approx(50.0, abs=0.01)

    def test_eligible_legs_in_a_partially_graded_market_are_kept(self):
        """Eligibility is a per-LEG property. Intersecting it with the
        market-level grade axis would drop eligible legs sitting inside
        ``incomplete`` markets — the exact cohort ``repair_pm_never_graded``
        deliberately leaves alone, so it is the one nobody else is measuring."""
        cell = _report([
            _row(grade=GRADE_INCOMPLETE, truth=TRUTH_ELIGIBLE,
                 b=5, n=40, sum_prob=20.0, winners=20),
        ])
        assert cell["n_eligible"] == 40
        assert cell["ece_eligible"] == pytest.approx(0.0, abs=0.01)

    def test_a_cell_with_no_eligible_legs_reports_absent_not_zero(self):
        """gotcha #53. "Nothing here can grade a forecast" and "everything here
        is perfectly calibrated" must not share a rendering — which is the same
        defect as the datagolf card rendering ``0 outcomes . 0.0pp ECE``."""
        cell = _report([
            _row(grade=GRADE_COMPLETE, truth=TRUTH_INELIGIBLE,
                 b=0, n=500, sum_prob=5.0, winners=400),
        ])
        assert cell["n_eligible"] == 0
        assert cell["ece_eligible"] is None
        assert cell["eligible_share"] == pytest.approx(0.0)
        assert cell["ece_all"] is not None


class TestParityWithV1:
    def test_ece_all_and_the_grade_twins_are_unchanged_by_the_new_axis(self):
        """The twin is ADDITIVE. Splitting one bin across both eligibility
        classes must reduce to exactly the same ``ece_all``/``ece_complete`` as
        folding it as a single row — otherwise this change silently restated
        every historical cell number."""
        split = _report([
            _row(grade=GRADE_COMPLETE, truth=TRUTH_ELIGIBLE,
                 b=6, n=30, sum_prob=18.0, winners=9),
            _row(grade=GRADE_COMPLETE, truth=TRUTH_INELIGIBLE,
                 b=6, n=70, sum_prob=42.0, winners=21),
        ])
        whole = _report([
            _row(grade=GRADE_COMPLETE, truth=TRUTH_ELIGIBLE,
                 b=6, n=100, sum_prob=60.0, winners=30),
        ])
        for field in ("ece_all", "ece_venue", "ece_complete", "gap_all", "n_all"):
            assert split[field] == pytest.approx(whole[field]), field


class TestWorkerSql:
    def test_eligibility_is_a_projected_column_never_a_where_clause(self):
        """Filtering in the WHERE would change ``ece_all`` and break parity with
        GET /api/admin/cohort-provenance-split, which this census reproduces."""
        from app.tasks.cohort_cell_census_worker import _BINS_SQL

        head, _, tail = _BINS_SQL.partition("WHERE")
        assert "resolution_source" in head
        assert "resolution_source" not in tail
        assert "GROUP BY 1, 2, 3" in _BINS_SQL

    def test_sql_renders_the_canonical_set_and_not_a_hand_typed_copy(self):
        """A second literal list of eligible sources is how the census and the
        published curve drift apart without either one erroring."""
        from app.tasks.cohort_cell_census_worker import _BINS_SQL
        from app.utils.resolution_authority import (
            CALIBRATION_TRUTH_ELIGIBLE_SOURCES_SQL,
        )

        assert CALIBRATION_TRUTH_ELIGIBLE_SOURCES_SQL in _BINS_SQL

    def test_null_resolution_source_falls_to_ineligible(self):
        """Fail-closed, matching ``is_calibration_truth_eligible``: a missing
        source can never grade a published forecast. In SQL the CASE's ELSE is
        what does it — ``NULL IN (...)`` is NULL, not false, so an implementation
        that tested for ``ineligible`` positively would drop the rows entirely.
        """
        from app.tasks.cohort_cell_census_worker import _BINS_SQL
        from app.utils.resolution_authority import is_calibration_truth_eligible

        assert is_calibration_truth_eligible(None) is False
        assert f"ELSE '{TRUTH_INELIGIBLE}'" in _BINS_SQL
