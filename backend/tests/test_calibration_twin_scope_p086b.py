"""CAL-P086B (#2076, #2007) — Gate 0 may not say ``agrees`` over a curve it cannot see.

The measurement behind this file, taken 2026-08-21 against production:

* ``GET /api/calibration`` publishes **285 cells / 1,934 buckets / 867,101 outcomes**
  across **seven** sources.
* The DB-direct twin folds ``_calibration_population_ctes()``, which is the **futures**
  population only. ``SELECT source, count(*) FROM futures_markets WHERE status='resolved'``
  returns exactly three values: polymarket 569,781, kalshi 225,274, datagolf 295. There is
  no ``odds_api*`` row in it, because those four sources are built by separate SQL at
  ``precompute_calibration.py:3677 / :3729 / :3778`` (plus the bookmaker path at :3838)
  over a different population.
* So **203 of 285 published cells (71.2%)** — 874 buckets, 135,102 outcomes — can never
  have a twin row. Not "did not today". Cannot, structurally.

``reconcile`` already counted those into ``published_only`` and reported them, which was
honest. But the **verdict** did not look at them, so Gate 0 could return ``agrees`` having
compared 28.8% of the curve's cells, and ``agrees`` is the word a certifier reads.

The fix is gotcha #53's distinction applied one level up: *"we could never see this"* and
*"we should have seen this and did not"* are different facts and must not share a bucket.
An out-of-scope cell is a declared, counted scope limit. An **in-scope** published cell with
no twin row is the twin and the producer disagreeing about the population — which is exactly
what Gate 0 exists to catch, and it was previously silent.
"""

from __future__ import annotations

import pytest

from app.utils.calibration_published_twin import (
    FOLD_POPULATION_SOURCES,
    VERDICT_AGREES,
    VERDICT_DISAGREES,
    VERDICT_UNMEASURABLE,
    reconcile,
)

# A disclosure earning a loose, definitely-not-None bound. The field names are
# ``tolerance_pp``'s, checked against it rather than guessed: ``measured: True``
# is required, and a staged block without it is UNMEASURABLE by design.
STAGED_WIDE = {
    "measured": True,
    "units_banked": 100,
    "units_drifted": 100,
    "units_drift_unknown": 0,
}
STAGED_TIGHT = {
    "measured": True,
    "units_banked": 100,
    "units_drifted": 0,
    "units_drift_unknown": 0,
}


def _cell(rate: float, n: int = 100) -> dict:
    return {"n": n, "winners": int(round(rate * n)), "sum_prob": rate * n}


def _pub(source: str, category: str, bucket: int, rate: float, n: int = 100) -> dict:
    return {
        "source": source,
        "category": category,
        "bucket_idx": bucket,
        "n": n,
        "winners": int(round(rate * n)),
    }


class TestScopeIsDeclaredAndSplit:
    def test_the_fold_population_is_the_three_futures_sources(self):
        assert FOLD_POPULATION_SOURCES == frozenset({"kalshi", "polymarket", "datagolf"})

    def test_an_out_of_scope_published_cell_does_not_make_the_verdict_disagree(self):
        """odds_api* cells are a declared scope limit, not a finding."""
        out = reconcile(
            db_cells={("kalshi", "nba"): {(5, None): _cell(0.55)}},
            published_buckets=[
                _pub("kalshi", "nba", 5, 0.55),
                _pub("odds_api", "nba", 5, 0.99),
                _pub("odds_api_totals", "nfl", 3, 0.01),
            ],
            staged=STAGED_WIDE,
        )
        assert out["verdict"] == VERDICT_AGREES
        assert len(out["published_only_out_of_scope"]) == 2
        assert out["published_only_in_scope"] == []

    def test_an_in_scope_published_cell_with_no_twin_row_is_a_DISAGREEMENT(self):
        """This is the case that was previously silent."""
        out = reconcile(
            db_cells={("kalshi", "nba"): {(5, None): _cell(0.55)}},
            published_buckets=[
                _pub("kalshi", "nba", 5, 0.55),
                _pub("polymarket", "politics", 2, 0.20),
            ],
            staged=STAGED_WIDE,
        )
        assert out["verdict"] == VERDICT_DISAGREES
        assert len(out["published_only_in_scope"]) == 1
        assert out["published_only_in_scope"][0]["source"] == "polymarket"

    def test_published_only_is_still_the_union_so_old_readers_do_not_lose_rows(self):
        out = reconcile(
            db_cells={("kalshi", "nba"): {(5, None): _cell(0.55)}},
            published_buckets=[
                _pub("kalshi", "nba", 5, 0.55),
                _pub("polymarket", "politics", 2, 0.20),
                _pub("odds_api", "nba", 5, 0.99),
            ],
            staged=STAGED_WIDE,
        )
        assert len(out["published_only"]) == 2
        assert len(out["published_only_in_scope"]) + len(
            out["published_only_out_of_scope"]
        ) == len(out["published_only"])


class TestTheVerdictCarriesItsOwnCoverage:
    def test_agrees_states_how_much_of_the_curve_it_compared(self):
        out = reconcile(
            db_cells={("kalshi", "nba"): {(5, None): _cell(0.55)}},
            published_buckets=[
                _pub("kalshi", "nba", 5, 0.55),
                _pub("odds_api", "nba", 5, 0.99, n=900),
            ],
            staged=STAGED_WIDE,
        )
        scope = out["scope"]
        assert scope["buckets_compared"] == 1
        assert scope["buckets_published"] == 2
        assert scope["buckets_out_of_scope"] == 1
        # 100 of 1,000 published outcomes were reachable.
        assert scope["outcomes_published"] == 1000
        assert scope["outcomes_out_of_scope"] == 900
        assert scope["pct_published_outcomes_in_scope"] == pytest.approx(10.0)

    def test_the_scope_block_is_present_even_when_the_verdict_is_unmeasurable(self):
        """A reader must never have to infer coverage from a missing key."""
        out = reconcile(
            db_cells={},
            published_buckets=[_pub("kalshi", "nba", 5, 0.55)],
            staged=None,
        )
        assert out["verdict"] == VERDICT_UNMEASURABLE
        assert "scope" in out
        assert out["scope"]["buckets_compared"] == 0

    def test_an_unmeasurable_bound_is_not_upgraded_by_an_in_scope_gap(self):
        """No bound means no verdict, full stop — a gap cannot manufacture one."""
        out = reconcile(
            db_cells={},
            published_buckets=[_pub("kalshi", "nba", 5, 0.55)],
            staged=None,
        )
        assert out["verdict"] == VERDICT_UNMEASURABLE
        assert len(out["published_only_in_scope"]) == 1


class TestTheOldBehaviourThatMustNotChange:
    def test_a_cell_outside_tolerance_still_disagrees(self):
        out = reconcile(
            db_cells={("kalshi", "nba"): {(5, None): _cell(0.90)}},
            published_buckets=[_pub("kalshi", "nba", 5, 0.10)],
            staged=STAGED_TIGHT,
        )
        assert out["verdict"] == VERDICT_DISAGREES
        assert len(out["outside"]) == 1

    def test_a_db_only_cell_is_still_reported_and_still_does_not_flip_the_verdict(self):
        """Unchanged on purpose: a db_only cell is the twin seeing MORE than the
        payload, which is a different and less alarming asymmetry — and turning it
        into a disagreement here would be a second behaviour change hiding inside
        the first."""
        out = reconcile(
            db_cells={
                ("kalshi", "nba"): {(5, None): _cell(0.55)},
                ("kalshi", "mlb"): {(1, None): _cell(0.15)},
            },
            published_buckets=[_pub("kalshi", "nba", 5, 0.55)],
            staged=STAGED_WIDE,
        )
        assert out["verdict"] == VERDICT_AGREES
        assert len(out["db_only"]) == 1


class TestTheProductionShapeItWasWrittenFor:
    """The measured 2026-08-21 split, in miniature: three in-scope sources present
    and four out-of-scope sources entirely absent from the fold."""

    def test_the_real_seven_source_shape_agrees_and_declares_71_percent_out_of_scope(self):
        db_cells = {
            ("kalshi", "nba"): {(5, None): _cell(0.55)},
            ("polymarket", "politics"): {(2, None): _cell(0.20)},
            ("datagolf", "golf"): {(7, None): _cell(0.75)},
        }
        published = [
            _pub("kalshi", "nba", 5, 0.55),
            _pub("polymarket", "politics", 2, 0.20),
            _pub("datagolf", "golf", 7, 0.75),
            _pub("odds_api", "nba", 5, 0.50),
            _pub("odds_api_bookmaker", "nba", 5, 0.50),
            _pub("odds_api_totals", "nfl", 3, 0.50),
            _pub("odds_api_spreads", "nfl", 3, 0.50),
        ]
        out = reconcile(
            db_cells=db_cells, published_buckets=published, staged=STAGED_WIDE
        )
        assert out["verdict"] == VERDICT_AGREES
        assert len(out["published_only_out_of_scope"]) == 4
        assert out["published_only_in_scope"] == []
        assert out["scope"]["sources_out_of_scope"] == [
            "odds_api",
            "odds_api_bookmaker",
            "odds_api_spreads",
            "odds_api_totals",
        ]

    def test_and_the_same_shape_DISAGREES_the_moment_an_in_scope_cell_goes_missing(self):
        """The mutation that proves the new guard is a sensor and not decoration
        (ruling 087): drop one in-scope cell from the fold and the verdict must
        flip. If it does not, the split is bookkeeping."""
        db_cells = {
            ("kalshi", "nba"): {(5, None): _cell(0.55)},
            ("datagolf", "golf"): {(7, None): _cell(0.75)},
        }
        published = [
            _pub("kalshi", "nba", 5, 0.55),
            _pub("polymarket", "politics", 2, 0.20),
            _pub("datagolf", "golf", 7, 0.75),
            _pub("odds_api", "nba", 5, 0.50),
        ]
        out = reconcile(
            db_cells=db_cells, published_buckets=published, staged=STAGED_WIDE
        )
        assert out["verdict"] == VERDICT_DISAGREES
        assert [r["source"] for r in out["published_only_in_scope"]] == ["polymarket"]
        assert len(out["published_only_out_of_scope"]) == 1
