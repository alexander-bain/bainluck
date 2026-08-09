"""CAL-P018 (#1089) — the per-series cliff census.

The measurement Alex's band ruling stands on, built as a rail because it could
not be run as a query: the full scan, a single-series scan, and even a bare
``COUNT(*)`` over the resolved population all exceed the statement timeout,
measured twice twelve hours apart.

What these tests defend, in order of how badly each would hurt:
  1. the merge sums and derives rates ONCE at the end — averaging per-window
     means would weight a 12-row window like a 400,000-row one, and bias the
     cliff in the direction that makes a band look safer than it is;
  2. a PARTIAL walk never presents itself as a total;
  3. the census cannot hold its own opinion about what a prop-threshold row is,
     or about what the current bands exclude — both are imported.
"""

from __future__ import annotations

import inspect

import pytest

from app.tasks import census_prop_threshold_cliff as cen


def _window(*cohorts, exhausted=False):
    return {"cohorts": list(cohorts), "exhausted": exhausted}


def _c(series="KXNHLAST", category="hockey", band=7, n=10, sum_pred=7.0, wins=1,
       excluded_today=0):
    return {
        "series": series, "category": category, "band": band,
        "n": n, "sum_pred": sum_pred, "wins": wins,
        "excluded_today": excluded_today,
    }


class TestTheMergeArithmetic:
    def test_windows_sum_rather_than_average(self):
        """The load-bearing one.

        A cohort split across a tiny window and a huge one must come out as the
        POOLED rate. Average-of-averages would give (0.90 + 0.10) / 2 = 0.50
        here; the honest answer is 0.108.
        """
        merged = cen.merge_windows([
            _window(_c(n=10, sum_pred=7.0, wins=9)),
            _window(_c(n=990, sum_pred=693.0, wins=99)),
        ])
        rows = cen.with_rates(merged)
        assert len(rows) == 1
        row = rows[0]
        assert row["n"] == 1000
        assert row["wins"] == 108
        assert row["actual"] == pytest.approx(0.108)
        # ... and NOT the average of the two windows' rates.
        assert row["actual"] != pytest.approx(0.5)
        assert row["predicted"] == pytest.approx(0.70)
        assert row["gap"] == pytest.approx(0.108 - 0.70)

    def test_distinct_cohorts_do_not_bleed_into_each_other(self):
        merged = cen.merge_windows([
            _window(
                _c(series="KXNHLAST", band=7, n=5),
                _c(series="KXNHLAST", band=8, n=6),
                _c(series="KXMLBTB", band=7, n=7),
                _c(series="KXNHLAST", category="basketball", band=7, n=8),
            )
        ])
        assert len(merged) == 4
        assert merged[cen.cohort_key("KXNHLAST", "hockey", 7)]["n"] == 5
        assert merged[cen.cohort_key("KXMLBTB", "hockey", 7)]["n"] == 7
        assert merged[cen.cohort_key("KXNHLAST", "basketball", 7)]["n"] == 8

    def test_exclusion_counts_accumulate_too(self):
        """The ruling asks for published exclusion counts, so they must survive
        the walk exactly as the population counts do."""
        merged = cen.merge_windows([
            _window(_c(n=100, excluded_today=40)),
            _window(_c(n=100, excluded_today=60)),
        ])
        assert next(iter(merged.values()))["excluded_today"] == 100

    def test_an_empty_cohort_reports_no_rate_rather_than_zero(self):
        """Unmeasured and measured-zero are different claims, and a band gets
        decided from them."""
        merged = cen.merge_windows([_window(_c(n=0, sum_pred=0.0, wins=0))])
        row = cen.with_rates(merged)[0]
        assert row["n"] == 0
        assert row["predicted"] is None
        assert row["actual"] is None
        assert row["gap"] is None

    def test_merging_nothing_is_empty_not_an_error(self):
        assert cen.merge_windows([]) == {}
        assert cen.with_rates({}) == []


class TestAPartialWalkIsNeverATotal:
    def test_a_walk_that_never_exhausted_is_incomplete(self):
        assert not cen.is_complete_walk([_window(_c()), _window(_c())])

    def test_only_a_walk_ending_exhausted_is_complete(self):
        assert cen.is_complete_walk([_window(_c()), _window(_c(), exhausted=True)])

    def test_no_windows_at_all_is_not_complete(self):
        assert not cen.is_complete_walk([])

    def test_an_exhausted_window_earlier_in_the_list_does_not_count(self):
        """Completeness is a property of where the walk STOPPED."""
        assert not cen.is_complete_walk([_window(_c(), exhausted=True), _window(_c())])


class TestItCannotHoldItsOwnDefinitions:
    """CAL-P013's finding, applied pre-emptively: a second definition of what a
    prop-threshold row is would justify a band change against a population the
    curve does not plot."""

    def test_the_name_pattern_and_exclusion_come_from_the_curve(self):
        src = inspect.getsource(cen)
        assert "from app.tasks.precompute_calibration import (" in src
        assert "KALSHI_PROP_THRESHOLD_NAME_RE" in src
        assert "kalshi_prop_threshold_exclude_sql" in src
        # And no re-typed copy of either.
        assert "0.90" not in src, "a hand-typed band literal is a second opinion"
        assert "0.50" not in src, "a hand-typed band literal is a second opinion"

    def test_the_series_key_comes_from_the_sentinel(self):
        from app.tasks.calibration_sentinel import series_family

        assert cen.series_family is series_family
        # The fold it exists for: seasons collapse into one series.
        assert cen.series_family("KXNBA2026") == cen.series_family("KXNBA2025")

    def test_the_rendered_sql_carries_the_canonical_exclusion(self):
        from app.tasks.precompute_calibration import (
            KALSHI_PROP_THRESHOLD_DEGENERATE_BAND,
            KALSHI_HOCKEY_HONEST_BAND_MAX,
        )

        sql = cen._cohorts_sql()
        # Rendered, not retyped: the live constants appear because the imported
        # builder put them there.
        assert str(KALSHI_PROP_THRESHOLD_DEGENERATE_BAND) in sql
        assert str(KALSHI_HOCKEY_HONEST_BAND_MAX) in sql
        assert "excluded_today" in sql

    def test_it_walks_rows_not_an_id_span(self):
        """The bug census_reachability measured and this module inherited the
        fix for: outcome ids are not uniformly dense, so a fixed id width is
        fatal in the dense regions."""
        src = inspect.getsource(cen)
        assert "ORDER BY id ASC LIMIT :scan" in src
        assert cen.DEFAULT_SCAN <= cen.MAX_SCAN


class TestTheRailIsRegisteredAndReadOnly:
    def test_it_is_on_the_repairs_registry(self):
        from app.routes.admin_repairs import _REPAIRS

        assert _REPAIRS["prop-threshold-cliff-census"] == (
            "app.tasks.census_prop_threshold_cliff",
            "census",
        )

    def test_apply_is_accepted_and_ignored(self):
        """Same contract as winner-field-coherence and reachability-census: the
        rail's shape allows `apply`, and this census must never honour it."""
        sig = inspect.signature(cen.census)
        assert "apply" in sig.parameters
        src = inspect.getsource(cen.census)
        for writer in ("UPDATE ", "INSERT ", "DELETE ", "commit("):
            assert writer not in src, f"census must never write ({writer!r})"


class TestTheWalk:
    @pytest.mark.asyncio
    async def test_an_empty_tail_is_a_complete_walk_not_a_failure(self):
        class _Session:
            async def execute(self, statement, params=None):
                class _R:
                    def mappings(self_inner):
                        class _M:
                            def first(self_m):
                                return {"lo": None, "hi": None, "n": 0}

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
            {"ext_prefix": "KXNHLAST", "category": "hockey", "band": 7,
             "n": 3, "sum_pred": 2.1, "wins": 0, "excluded_today": 3},
        ]

        class _Session:
            def __init__(self):
                self.calls = 0

            async def execute(self, statement, params=None):
                self.calls += 1
                call = self.calls
                outer = self

                class _R:
                    def mappings(self_inner):
                        class _M:
                            def first(self_m):
                                return {"lo": 1, "hi": 900, "n": outer.scan}

                            def all(self_m):
                                return rows

                        return _M()

                # 1st = SET LOCAL, 2nd = bounds, 3rd = cohorts
                if call == 2 or call == 3:
                    return _R()
                return _R()

        session = _Session()
        session.scan = cen.DEFAULT_SCAN  # a FULL window => more work remains
        out = await cen.census(session, limit=cen.DEFAULT_SCAN)

        assert out["census"] == cen.CENSUS_NAME
        assert out["exhausted"] is False, "a full window means keep going"
        assert out["next_offset"] == 900
        assert out["prop_rows_in_window"] == 3
        assert out["cohorts"][0]["series"] == "KXNHLAST"
