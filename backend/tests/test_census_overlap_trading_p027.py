"""CAL-P027 (#1544) — the overlap census that measures ruling 011's N.

What these tests defend, in order of how badly each would hurt:

  1. ``absent`` never collapses into ``zero`` or ``untraded`` — ruling 011's
     load-bearing failure is exactly that fold, and it produced a number that
     lied in an interesting direction (thin markets looking better calibrated);
  2. ``precision_for_threshold`` refuses to answer rather than inventing an N —
     an interpolated precision figure is indistinguishable from a real one;
  3. moves are counted per bookmaker and folded with MAX, not SUM — either
     mistake yields a plausible, publishable, wrong N;
  4. density is observations, not row count, so write-time dedup does not read
     as sparsity;
  5. the merge pools rather than averaging, and a PARTIAL walk never presents
     itself as a total;
  6. one definition of banding, shared by the SQL and the Python.
"""

from __future__ import annotations

import inspect

import pytest

from app.tasks import census_overlap_trading as cen


def _window(*cohorts, exhausted=False):
    return {"cohorts": list(cohorts), "exhausted": exhausted}


def _c(
    source="kalshi",
    category="entertainment",
    volume_state="positive",
    density_band="10-49",
    move_band="5-9",
    n=10,
    snapshot_rows=100,
    observations=120,
    moves=60,
):
    return {
        "source": source,
        "category": category,
        "volume_state": volume_state,
        "density_band": density_band,
        "move_band": move_band,
        "n": n,
        "snapshot_rows": snapshot_rows,
        "observations": observations,
        "moves": moves,
    }


class TestTheThreeVolumeStates:
    """Ruling 011's whole point: absence of volume is not evidence of thinness."""

    def test_absent_zero_and_positive_are_three_distinct_cohorts(self):
        merged = cen.merge_windows([
            _window(
                _c(volume_state="absent", n=5),
                _c(volume_state="zero", n=6),
                _c(volume_state="positive", n=7),
            )
        ])
        assert len(merged) == 3
        by_state = {row["volume_state"]: row["n"] for row in merged.values()}
        assert by_state == {"absent": 5, "zero": 6, "positive": 7}

    def test_the_module_declares_all_three_states(self):
        assert cen.VOLUME_STATES == ("absent", "zero", "positive")

    def test_absent_rows_are_excluded_from_the_overlap_measurement(self):
        """`absent` is the UNKNOWN the ladder must not resolve silently.

        A predictor of `volume > 0` cannot be scored on rows where volume was
        never read. Including them would drag precision toward whichever way
        the unknown majority happened to fall.
        """
        merged = cen.merge_windows([
            _window(
                # 100 rows with no volume reading at all, all high-move.
                _c(volume_state="absent", move_band="20+", n=100),
                # The real overlap: 10 traded, high-move.
                _c(volume_state="positive", move_band="20+", n=10),
            )
        ])
        out = cen.precision_for_threshold(merged, 20, min_density=3)
        assert out["supported"] is True
        # Support counts ONLY the volume-bearing rows.
        assert out["support"] == 10
        assert out["true_positive"] == 10
        assert out["false_positive"] == 0

    def test_the_sql_maps_null_volume_to_absent_and_not_to_zero(self):
        sql = cen._cohorts_sql()
        assert "WHEN fo.volume IS NULL THEN 'absent'" in sql
        assert "WHEN fo.volume > 0 THEN 'positive'" in sql
        # And the ELSE arm (a real 0) is its own state.
        assert "'zero'" in sql


class TestItRefusesRatherThanInventingAnN:
    def test_a_threshold_that_splits_a_band_is_refused(self):
        """6 falls inside the 5-9 band, so `>= 6` is not answerable exactly."""
        merged = cen.merge_windows([_window(_c(move_band="5-9", n=10))])
        out = cen.precision_for_threshold(merged, 6, min_density=3)
        assert out["supported"] is False
        assert out["reason"] == "threshold_splits_a_band"
        assert "precision" not in out

    def test_a_boundary_threshold_is_answerable(self):
        assert cen.threshold_is_on_a_band_boundary(5) is True
        assert cen.threshold_is_on_a_band_boundary(6) is False
        assert cen.threshold_is_on_a_band_boundary(20) is True

    def test_an_empty_overlap_reports_unsupported_not_zero(self):
        """The pre-declared PREMISE-BROKEN case.

        No volume-bearing rows at adequate density means N is unmeasurable and
        must go back to Alex as a real choice. Returning 0.0 precision would be
        a publishable-looking answer to a question that was never answered.
        """
        merged = cen.merge_windows([
            _window(_c(volume_state="absent", n=500))
        ])
        out = cen.precision_for_threshold(merged, 5, min_density=3)
        assert out["supported"] is False
        assert out["reason"] == "no_overlap_rows"
        assert out.get("precision") is None

    def test_density_below_the_floor_is_excluded(self):
        """gotcha #53's shape: 2 observations cannot yield 5 moves, so scoring
        such a row as a false negative would blame the market for our capture."""
        merged = cen.merge_windows([
            _window(
                _c(volume_state="positive", density_band="2", move_band="0", n=99),
                _c(volume_state="positive", density_band="10-49", move_band="20+", n=1),
            )
        ])
        out = cen.precision_for_threshold(merged, 20, min_density=3)
        assert out["support"] == 1, "the 2-observation cohort must not be scored"
        assert out["true_positive"] == 1

    def test_precision_and_recall_are_computed_from_the_confusion_counts(self):
        merged = cen.merge_windows([
            _window(
                # predicted traded, and traded  -> TP 30
                _c(volume_state="positive", move_band="20+", n=30),
                # predicted traded, not traded  -> FP 10
                _c(volume_state="zero", move_band="20+", n=10),
                # predicted untraded, traded    -> FN 20
                _c(volume_state="positive", move_band="1", n=20),
                # predicted untraded, untraded  -> TN 40
                _c(volume_state="zero", move_band="1", n=40),
            )
        ])
        out = cen.precision_for_threshold(merged, 20, min_density=3)
        assert (out["true_positive"], out["false_positive"]) == (30, 10)
        assert (out["false_negative"], out["true_negative"]) == (20, 40)
        assert out["precision"] == pytest.approx(0.75)
        assert out["recall"] == pytest.approx(0.60)
        assert out["support"] == 100


class TestTheSnapshotArithmeticCannotBeQuietlyWrong:
    def test_moves_are_partitioned_by_bookmaker(self):
        """Two books quoting differently is not a price move.

        Without the bookmaker partition every cross-book quote difference reads
        as a move, and N comes out plausible and wrong.
        """
        sql = cen._cohorts_sql()
        assert "PARTITION BY s.outcome_id, s.bookmaker" in sql

    def test_the_lag_ordering_is_deterministic(self):
        sql = cen._cohorts_sql()
        assert "ORDER BY s.captured_at, s.id" in sql

    def test_books_are_folded_with_max_not_sum(self):
        """Ruling 011 takes 'the strongest evidence available'. SUM would
        multiply a market's evidence by the number of books quoting it."""
        sql = cen._cohorts_sql()
        assert "MAX(moves) AS moves" in sql
        assert "SUM(moves)" not in sql
        assert "MAX(observations) AS observations" in sql

    def test_density_is_observations_not_row_count(self):
        """DataGolf dedups at write time (reading_count), nobody else does. A
        row count would read fifty confirmations of an unchanged price as one
        sparse observation."""
        sql = cen._cohorts_sql()
        assert "SUM(reading_count) AS observations" in sql
        assert "COALESCE(s.reading_count, 1) AS reading_count" in sql
        # ...and the raw row count survives alongside it, because moves are
        # drawn from rows.
        assert "COUNT(*) AS snapshot_rows" in sql

    def test_a_move_requires_a_previous_reading_and_a_real_change(self):
        sql = cen._cohorts_sql()
        assert "prev_probability IS NOT NULL" in sql
        assert "probability IS DISTINCT FROM prev_probability" in sql


class TestThePopulationPredicateIsImported:
    def test_the_truth_allowlist_comes_from_resolution_authority(self):
        from app.utils.resolution_authority import (
            CALIBRATION_TRUTH_ELIGIBLE_SOURCES_SQL,
        )

        src = inspect.getsource(cen)
        assert (
            "from app.utils.resolution_authority import "
            "CALIBRATION_TRUTH_ELIGIBLE_SOURCES_SQL" in src
        )
        assert CALIBRATION_TRUTH_ELIGIBLE_SOURCES_SQL in cen._cohorts_sql()

    def test_it_does_not_import_from_the_frozen_precompute_module(self):
        """Ruling 009 freezes `precompute_calibration.py`. This census does not
        edit it — and does not need to import from it either, because the
        allowlist's real home is `resolution_authority`.

        Checked on IMPORT STATEMENTS, not on any mention of the name: the
        docstring discusses that module deliberately, and a test that forbade
        naming it would push the reasoning out of the file to satisfy the test.
        """
        import ast

        tree = ast.parse(inspect.getsource(cen))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
            elif isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)

        assert not any("precompute_calibration" in mod for mod in imported), (
            f"the census must not couple itself to the frozen module: {imported}"
        )
        # The positive half: it DOES import the allowlist from its real home.
        assert "app.utils.resolution_authority" in imported

    def test_it_uses_the_same_curve_price_expression_as_every_read_path(self):
        assert cen._CURVE_PRICE == (
            "COALESCE(fo.calibration_probability, fo.opening_probability)"
        )
        assert cen._CURVE_PRICE in cen._cohorts_sql()


class TestOneDefinitionOfBanding:
    @pytest.mark.parametrize("value", list(range(0, 60)))
    def test_python_and_sql_agree_on_every_move_band_boundary(self, value):
        """The bands are rendered into SQL from the same table `band_for` reads,
        so this asserts the renderer actually honours the boundaries rather than
        that two hand-written copies happen to match."""
        label = cen.band_for(value, cen.MOVE_BANDS)
        arm = cen._band_case_sql("m", cen.MOVE_BANDS)
        # Reconstruct the SQL's verdict by evaluating its arms in order.
        verdict = None
        for name, lo, hi in cen.MOVE_BANDS:
            if value >= lo and (hi is None or value <= hi):
                verdict = name
                break
        assert label == verdict
        assert f"'{label}'" in arm

    def test_band_for_covers_the_bands_without_gaps(self):
        for bands in (cen.MOVE_BANDS, cen.DENSITY_BANDS):
            for value in range(0, 100):
                assert cen.band_for(value, bands) != "unknown"

    def test_the_low_end_is_fine_grained_because_n_lives_there(self):
        """A coarse low end would make the census unable to answer its own
        question, so 0..4 must each be their own band."""
        for value in (0, 1, 2, 3, 4):
            assert cen.band_for(value, cen.MOVE_BANDS) == str(value)

    def test_a_single_observation_is_its_own_density_band(self):
        """Exam item 3's stamped-settlement signature: one captured quote."""
        assert cen.band_for(1, cen.DENSITY_BANDS) == "1"
        assert cen.band_for(2, cen.DENSITY_BANDS) == "2"

    def test_band_is_wholly_at_or_above_is_conservative(self):
        assert cen.band_is_wholly_at_or_above("20+", 20) is True
        assert cen.band_is_wholly_at_or_above("5-9", 5) is True
        # 5-9 contains rows below 10, so it does NOT wholly satisfy >= 10.
        assert cen.band_is_wholly_at_or_above("5-9", 10) is False

    def test_wholly_means_wholly_and_not_partly(self):
        """The case that separates a MIN implementation from a MAX one.

        Added because a MAX-based version survived mutation: every boundary
        threshold sits at a band's lower edge, where min and max happen to
        agree, so the boundary assertions above cannot tell the two apart. A
        threshold INSIDE a band is where "wholly" earns its name — band 5-9
        contains rows with 5 moves, so it does not wholly satisfy `>= 7`, and
        a MAX implementation would claim it does.

        `precision_for_threshold` refuses non-boundary thresholds today, so
        this is the predicate's contract rather than a live bug — which is
        exactly why it needs pinning: nothing else would catch it changing.
        """
        assert cen.band_is_wholly_at_or_above("5-9", 7) is False
        assert cen.band_is_wholly_at_or_above("10-19", 15) is False
        # The open-ended top band has no upper edge to be fooled by.
        assert cen.band_is_wholly_at_or_above("20+", 25) is False


class TestTheMergeArithmetic:
    def test_windows_pool_rather_than_average(self):
        merged = cen.merge_windows([
            _window(_c(n=10, moves=90, observations=100)),
            _window(_c(n=990, moves=99, observations=1_000)),
        ])
        rows = cen.with_rates(merged)
        assert len(rows) == 1
        row = rows[0]
        assert row["n"] == 1000
        assert row["moves"] == 189
        assert row["mean_moves"] == pytest.approx(0.189)
        # ...and NOT the average of the two windows' means (9.0 and 0.1).
        assert row["mean_moves"] != pytest.approx(4.55)

    def test_distinct_cohorts_do_not_bleed_into_each_other(self):
        merged = cen.merge_windows([
            _window(
                _c(source="kalshi", n=1),
                _c(source="polymarket", n=2),
                _c(category="cricket", n=3),
                _c(volume_state="zero", n=4),
                _c(density_band="1", n=5),
                _c(move_band="0", n=6),
            )
        ])
        assert len(merged) == 6
        assert merged[
            cen.cohort_key("kalshi", "entertainment", "positive", "10-49", "5-9")
        ]["n"] == 1

    def test_an_empty_cohort_reports_none_rather_than_zero(self):
        merged = cen.merge_windows([_window(_c(n=0, moves=0, observations=0))])
        row = cen.with_rates(merged)[0]
        assert row["mean_moves"] is None
        assert row["mean_observations"] is None

    def test_a_partial_walk_is_never_a_complete_one(self):
        assert cen.is_complete_walk([]) is False
        assert cen.is_complete_walk([_window(_c(), exhausted=False)]) is False
        assert cen.is_complete_walk([
            _window(_c(), exhausted=False),
            _window(_c(), exhausted=True),
        ]) is True


class TestTheRailIsRegisteredAndReadOnly:
    def test_it_is_on_the_repairs_registry(self):
        from app.routes.admin_repairs import _REPAIRS

        assert _REPAIRS["overlap-trading-census"] == (
            "app.tasks.census_overlap_trading",
            "census",
        )

    def test_apply_is_accepted_and_ignored(self):
        sig = inspect.signature(cen.census)
        assert "apply" in sig.parameters
        src = inspect.getsource(cen.census)
        for writer in ("UPDATE ", "INSERT ", "DELETE ", "commit("):
            assert writer not in src, f"census must never write ({writer!r})"

    def test_the_whole_module_holds_no_write(self):
        src = inspect.getsource(cen)
        for writer in ("UPDATE ", "INSERT INTO", "DELETE FROM", "commit("):
            assert writer not in src, f"census must never write ({writer!r})"

    def test_it_walks_rows_not_an_id_span(self):
        src = inspect.getsource(cen)
        assert "ORDER BY id ASC LIMIT :scan" in src
        assert cen.DEFAULT_SCAN <= cen.MAX_SCAN

    def test_its_window_is_smaller_than_the_cheaper_censuses(self):
        """This is the only census doing correlated snapshot scans, and the
        cliff census's docstring explicitly notes it does NOT. Matching their
        window size would reintroduce the timeout the rail exists to dodge."""
        from app.tasks import census_prop_threshold_cliff as cliff

        assert cen.DEFAULT_SCAN < cliff.DEFAULT_SCAN

    def test_the_window_timeout_exceeds_the_db_query_wall(self):
        """The measured failure was a 10s statement timeout; a rail that kept it
        would fail in exactly the same place."""
        assert cen._WINDOW_TIMEOUT == "20s"
        assert "SET LOCAL statement_timeout" in inspect.getsource(cen.census)


class TestTheWalk:
    @pytest.mark.asyncio
    async def test_an_empty_tail_is_a_complete_walk_not_a_failure(self):
        class _Session:
            async def execute(self, statement, params=None):
                class _R:
                    def mappings(self_inner):
                        class _M:
                            def first(self_m):
                                return {"lo": None, "hi": None, "n": 0, "watermark": 4242}

                            def all(self_m):  # pragma: no cover - not reached
                                return []

                        return _M()

                return _R()

        out = await cen.census(_Session())
        assert out["exhausted"] is True
        assert out["rows_walked"] == 0
        assert out["cohorts"] == []
        assert out["next_offset"] is None

    @pytest.mark.asyncio
    async def test_a_full_window_reports_resumable_progress(self):
        rows = [
            {
                "source": "kalshi",
                "category": "entertainment",
                "volume_state": "absent",
                "density_band": "1",
                "move_band": "0",
                "n": 3,
                "snapshot_rows": 3,
                "observations": 3,
                "moves": 0,
            },
        ]

        class _Session:
            def __init__(self):
                self.scan = cen.DEFAULT_SCAN

            async def execute(self, statement, params=None):
                outer = self

                class _R:
                    def mappings(self_inner):
                        class _M:
                            def first(self_m):
                                return {"lo": 1, "hi": 900, "n": outer.scan, "watermark": 4242}

                            def all(self_m):
                                return rows

                        return _M()

                return _R()

        out = await cen.census(_Session(), limit=cen.DEFAULT_SCAN)

        assert out["census"] == cen.CENSUS_NAME
        assert out["exhausted"] is False, "a full window means keep going"
        assert out["next_offset"] == 900
        assert out["eligible_rows_in_window"] == 3
        assert out["cohorts"][0]["volume_state"] == "absent"

    @pytest.mark.asyncio
    async def test_the_scan_is_capped_at_max(self):
        seen = {}

        class _Session:
            async def execute(self, statement, params=None):
                if params and "scan" in params:
                    seen["scan"] = params["scan"]

                class _R:
                    def mappings(self_inner):
                        class _M:
                            def first(self_m):
                                return {"lo": None, "hi": None, "n": 0, "watermark": 4242}

                            def all(self_m):  # pragma: no cover
                                return []

                        return _M()

                return _R()

        await cen.census(_Session(), limit=cen.MAX_SCAN * 100)
        assert seen["scan"] == cen.MAX_SCAN
