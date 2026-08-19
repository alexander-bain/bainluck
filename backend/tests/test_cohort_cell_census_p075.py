"""CAL-P075 / #1978 — the all-cells census core, tested without a database.

There is no local Postgres in this sandbox, so every decision that could be
wrong is made in :mod:`app.utils.cohort_cell_census` and asserted here. The
worker module is asserted only for the properties a string can carry (that its
SQL is built from the shared population constants, and that it orders its
roster), because those are the two things whose absence produced a wrong answer
that looked right.
"""

from __future__ import annotations

import json

import pytest

from app.utils.cohort_cell_census import (
    BISECT_FLOOR_IDS,
    GRADE_COMPLETE,
    GRADE_INCOMPLETE,
    GRADE_NEVER,
    MIN_CELL_N,
    bin_key,
    bisect_range,
    build_report,
    cell_id,
    classify_market_grade,
    ece_from_bins,
    fold_page,
    gap_from_bins,
    parse_bin_key,
    reconcile_markets,
)


def _row(league, market_type, grade, b, n, sum_prob, winners):
    from types import SimpleNamespace

    return SimpleNamespace(
        league=league,
        market_type=market_type,
        grade=grade,
        bin=b,
        n=n,
        sum_prob=sum_prob,
        winners=winners,
    )


class TestGradeClassification:
    """The twins' discriminator. A two-way split collapses ``incomplete`` into
    whichever side the implementer picked, and the two sides mean opposite
    things."""

    def test_all_legs_graded_is_complete(self):
        assert classify_market_grade(5, 5) == GRADE_COMPLETE

    def test_no_legs_graded_is_never(self):
        assert classify_market_grade(5, 0) == GRADE_NEVER

    def test_some_legs_graded_is_incomplete(self):
        assert classify_market_grade(5, 2) == GRADE_INCOMPLETE

    def test_single_leg_market_is_binary_not_incomplete(self):
        assert classify_market_grade(1, 1) == GRADE_COMPLETE
        assert classify_market_grade(1, 0) == GRADE_NEVER

    def test_no_legs_is_never_not_complete(self):
        # 0 >= 0 would classify as complete under a naive comparison, which
        # would silently promote a market with nothing in the population into
        # the cohort we trust most.
        assert classify_market_grade(0, 0) == GRADE_NEVER

    def test_impossible_overcount_is_not_silently_clamped_into_incomplete(self):
        # graded > total cannot come from the SQL. If it ever does, it must not
        # land in ``incomplete`` — that would hide a counting bug inside the one
        # cohort nobody is otherwise measuring.
        assert classify_market_grade(3, 4) == GRADE_COMPLETE


class TestBinKeyJsonRoundTrip:
    def test_round_trip(self):
        k = bin_key("tennis", "quantity", GRADE_COMPLETE, 7)
        assert parse_bin_key(k) == ("tennis", "quantity", GRADE_COMPLETE, 7)

    def test_survives_json_which_a_tuple_key_would_not(self):
        """The checkpoint is JSONB. A tuple key comes back as a list, which is
        unhashable, so the resumed run would rebuild an EMPTY accumulator while
        reporting the banked page count — a failure that looks like a working
        resume."""
        acc = {bin_key("soccer", "quantity", GRADE_NEVER, 0): {"n": 3.0}}
        revived = json.loads(json.dumps(acc))
        assert revived == acc
        assert parse_bin_key(next(iter(revived)))[0] == "soccer"

    def test_malformed_key_raises_rather_than_defaulting(self):
        with pytest.raises(ValueError):
            parse_bin_key("not-a-key")


class TestFold:
    def test_two_pages_accumulate(self):
        acc: dict = {}
        fold_page(acc, [_row("tennis", "quantity", GRADE_COMPLETE, 3, 10, 3.5, 4)])
        fold_page(acc, [_row("tennis", "quantity", GRADE_COMPLETE, 3, 5, 1.75, 2)])
        slot = acc[bin_key("tennis", "quantity", GRADE_COMPLETE, 3)]
        assert slot["n"] == 15
        assert slot["sum_prob"] == pytest.approx(5.25)
        assert slot["winners"] == 6

    def test_distinct_grades_do_not_merge(self):
        acc: dict = {}
        fold_page(
            acc,
            [
                _row("tennis", "quantity", GRADE_COMPLETE, 3, 10, 3.5, 4),
                _row("tennis", "quantity", GRADE_NEVER, 3, 99, 34.65, 0),
            ],
        )
        assert len(acc) == 2


class TestEce:
    def test_below_floor_is_absent_not_zero(self):
        """A zero would rank an unmeasurable cell as the best-calibrated cell in
        the table."""
        value, fallback = ece_from_bins([{"n": MIN_CELL_N - 1, "sum_prob": 5.0, "winners": 5}])
        assert value is None
        assert fallback is False

    def test_perfectly_calibrated_is_zero(self):
        bins = [{"n": 100, "sum_prob": 30.0, "winners": 30}]
        value, fallback = ece_from_bins(bins)
        assert value == pytest.approx(0.0, abs=0.01)
        assert fallback is False

    def test_matches_the_canonical_definition(self):
        from app.tasks.precompute_calibration import _compute_horizon_mce

        bins = [
            {"n": 100, "sum_prob": 10.0, "winners": 25},
            {"n": 200, "sum_prob": 150.0, "winners": 120},
        ]
        assert ece_from_bins(bins)[0] == _compute_horizon_mce(
            [dict(b) for b in bins], weighted=True
        )

    def test_gap_is_signed(self):
        """ECE is unsigned; #1145's whole open question is a SIGN."""
        over = gap_from_bins([{"n": 100, "sum_prob": 80.0, "winners": 20}])
        under = gap_from_bins([{"n": 100, "sum_prob": 20.0, "winners": 80}])
        assert over > 0 and under < 0

    def test_gap_of_empty_is_none(self):
        assert gap_from_bins([]) is None


class TestBisect:
    def test_halves_a_wide_range(self):
        halves = bisect_range(0, 1000)
        assert halves == ((0, 500), (501, 1000))

    def test_irreducible_below_floor(self):
        assert bisect_range(0, BISECT_FLOOR_IDS - 1) is None

    def test_inverted_range_is_irreducible_not_an_exception(self):
        assert bisect_range(50, 10) is None


class TestReconciliation:
    def test_the_silent_short_read_is_caught(self):
        """The exact shape of the only silent wrong answer so far: paging
        without ORDER BY id read 1,317 of basketball/quantity's 13,121 markets
        and reported them as the cell."""
        recon = reconcile_markets(
            {"basketball/quantity": 13121}, {"basketball/quantity": 1317}
        )
        assert recon["ok"] is False
        assert recon["mismatches"][0]["delta"] == 1317 - 13121

    def test_agreement_is_ok(self):
        assert reconcile_markets({"a/b": 10}, {"a/b": 10})["ok"] is True

    def test_a_cell_paging_saw_but_the_roster_did_not_is_a_mismatch(self):
        recon = reconcile_markets({}, {"ghost/quantity": 4})
        assert recon["ok"] is False


class TestReport:
    def _acc(self):
        acc: dict = {}
        # complete cohort: well calibrated
        fold_page(acc, [_row("tennis", "quantity", GRADE_COMPLETE, 3, 400, 140.0, 140)])
        # incomplete cohort: badly calibrated, and small enough to matter
        fold_page(acc, [_row("tennis", "quantity", GRADE_INCOMPLETE, 3, 100, 35.0, 90)])
        # never-graded: is_winner=false is the column default, so 0 winners
        fold_page(acc, [_row("tennis", "quantity", GRADE_NEVER, 3, 500, 175.0, 0)])
        return acc

    def test_zero_cells_are_reported(self):
        """#1978's argument rests on a zero-fallback control. A census that
        lists only cells with a positive share deletes the comparison."""
        report = build_report(
            accumulator={},
            roster_totals={"politics/quantity": 417, "rodeo/container_member": 132},
            paged_totals={"politics/quantity": 417, "rodeo/container_member": 132},
            complete=True,
            elapsed_s=1.0,
            pages_done=1,
        )
        assert report["cells_total"] == 2
        assert {c["cell"] for c in report["cells"]} == {
            "politics/quantity",
            "rodeo/container_member",
        }
        for cell in report["cells"]:
            assert cell["n_all"] == 0
            assert cell["ece_all"] is None  # absent, never a comfortable zero

    def test_twins_are_separated_and_all_sits_between_them(self):
        report = build_report(
            accumulator=self._acc(),
            roster_totals={"tennis/quantity": 200},
            paged_totals={"tennis/quantity": 200},
            complete=True,
            elapsed_s=1.0,
            pages_done=1,
        )
        cell = report["cells"][0]
        assert cell["ece_complete"] == pytest.approx(0.0, abs=0.01)
        assert cell["ece_incomplete"] > 50
        # The blend hides which population moves it — that is the whole point of
        # reporting both.
        assert cell["ece_complete"] < cell["ece_all"] < cell["ece_incomplete"]
        assert cell["n_complete"] == 400
        assert cell["n_incomplete"] == 100
        assert cell["n_never"] == 500
        assert cell["incomplete_share"] == pytest.approx(0.1, abs=0.001)

    def test_ece_venue_keeps_parity_with_the_endpoint(self):
        """venue = complete + incomplete, so the existing contract is preserved
        and the twins are purely additive."""
        report = build_report(
            accumulator=self._acc(),
            roster_totals={"tennis/quantity": 200},
            paged_totals={"tennis/quantity": 200},
            complete=True,
            elapsed_s=1.0,
            pages_done=1,
        )
        cell = report["cells"][0]
        assert cell["n_venue"] == cell["n_complete"] + cell["n_incomplete"]
        assert cell["n_default"] == cell["n_never"]
        assert cell["graded_share"] == pytest.approx(500 / 1000, abs=0.001)

    def test_measured_is_per_cell_not_per_run(self):
        """CAL-P074's directive: a run that gets 44 of 49 cells reports 44
        measurements and 5 absences, not one absence."""
        report = build_report(
            accumulator=self._acc(),
            roster_totals={"tennis/quantity": 200, "soccer/quantity": 98036},
            paged_totals={"tennis/quantity": 200, "soccer/quantity": 12},
            complete=True,
            elapsed_s=1.0,
            pages_done=1,
        )
        by_cell = {c["cell"]: c for c in report["cells"]}
        assert by_cell["tennis/quantity"]["measured"] is True
        assert by_cell["soccer/quantity"]["measured"] is False
        assert by_cell["soccer/quantity"]["measured_reason"] == "roster_vs_paged_mismatch"
        assert report["cells_measured"] == 1
        assert report["cells_absent"] == 1

    def test_an_incomplete_run_marks_every_cell_unmeasured(self):
        report = build_report(
            accumulator=self._acc(),
            roster_totals={"tennis/quantity": 200},
            paged_totals={"tennis/quantity": 200},
            complete=False,
            elapsed_s=1.0,
            pages_done=1,
        )
        assert report["complete"] is False
        assert report["cells"][0]["measured"] is False
        assert report["cells"][0]["measured_reason"] == "run_incomplete"

    def test_irreducible_ranges_are_carried_not_dropped(self):
        report = build_report(
            accumulator={},
            roster_totals={"a/quantity": 1},
            paged_totals={"a/quantity": 1},
            failed_ranges=[{"lo": 10, "hi": 20, "ids": 11, "reason": "statement_timeout"}],
            complete=False,
            elapsed_s=1.0,
            pages_done=1,
        )
        assert report["irreducible_ranges"][0]["lo"] == 10
        assert (
            report["cells"][0]["measured_reason"] == "run_incomplete_with_irreducible_range"
        )

    def test_sampled_is_false_because_this_is_the_full_population(self):
        report = build_report(
            accumulator={},
            roster_totals={},
            paged_totals={},
            complete=True,
            elapsed_s=1.0,
            pages_done=0,
        )
        assert report["sampled"] is False
        assert report["population"] == "full"


class TestWorkerSqlInvariants:
    """Two properties whose absence already produced a wrong answer."""

    def _sql(self):
        import inspect

        from app.tasks import cohort_cell_census_worker as w

        return inspect.getsource(w)

    def test_roster_page_is_ordered_by_id(self):
        """Paging without ORDER BY id read 1,317 of 13,121 markets and errored
        on nothing."""
        from app.tasks.cohort_cell_census_worker import _ROSTER_PAGE_SQL

        assert "ORDER BY fm.id" in _ROSTER_PAGE_SQL
        assert "fm.id > :cursor" in _ROSTER_PAGE_SQL

    def test_roster_page_has_no_category_predicate(self):
        """Category is a GROUPING key, never a filter — that is what deletes the
        id-space density trap AND avoids the group/event closure unsoundness
        CAL-P075 measured."""
        from app.tasks.cohort_cell_census_worker import _ROSTER_PAGE_SQL

        assert "llm_sport_category" in _ROSTER_PAGE_SQL  # selected...
        assert "llm_sport_category =" not in _ROSTER_PAGE_SQL  # ...never filtered
        assert "llm_sport_category IN" not in _ROSTER_PAGE_SQL

    def test_population_predicate_comes_from_the_shared_constants(self):
        from app.tasks.cohort_cell_census_worker import (
            _ROSTER_PAGE_SQL,
            _ROSTER_TOTALS_SQL,
        )
        from app.utils.cohort_cell_census import (
            POPULATION_MARKET_TYPES,
            POPULATION_SOURCE,
            POPULATION_STATUS,
        )

        for sql in (_ROSTER_PAGE_SQL, _ROSTER_TOTALS_SQL):
            assert f"'{POPULATION_SOURCE}'" in sql
            assert f"'{POPULATION_STATUS}'" in sql
            for market_type in POPULATION_MARKET_TYPES:
                assert f"'{market_type}'" in sql

    def test_grade_leg_is_unfiltered_by_price(self):
        """Classification is over ALL of a market's outcomes. Classifying on the
        eligibility-filtered subset would call a market fully-graded because its
        ungraded legs were priced out of the curve."""
        from app.tasks.cohort_cell_census_worker import _BINS_SQL, _GRADE_SQL

        assert "calibration_probability" not in _GRADE_SQL
        assert "opening_probability" not in _GRADE_SQL
        # ...while the BIN leg does carry the endpoint's price filters.
        assert "opening_probability IS NOT NULL" in _BINS_SQL

    def test_both_aggregation_legs_are_bounded_by_the_id_array(self):
        """``fo.market_id = ANY(ARRAY[...])`` is the only thing measured to bound
        this plan; a join or a range predicate does not."""
        from app.tasks.cohort_cell_census_worker import _BINS_SQL, _GRADE_SQL

        for sql in (_GRADE_SQL, _BINS_SQL):
            assert "fo.market_id = ANY(CAST(:ids AS bigint[]))" in sql

    def test_worker_is_not_on_the_beat_schedule(self):
        """It reads the population the deadline-critical producer reads hourly
        from :15 to ~:35. The quiet window is a human's choice, not a cron
        guess."""
        from app.tasks import celery_app

        names = {
            entry.get("task") for entry in celery_app.conf.beat_schedule.values()
        }
        assert "app.tasks.cohort_cell_census" not in names

    def test_worker_task_is_registered(self):
        from app.tasks import celery_app

        assert "app.tasks.cohort_cell_census" in celery_app.tasks


def test_cell_id_is_stable():
    assert cell_id("tennis", "quantity") == "tennis/quantity"
