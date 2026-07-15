"""Guard test for the chart_density census SQL bound (#202).

The chart_density tile scans OPEN markets too (an unbounded, growing population
whose outcomes carry huge live-polled snapshot counts). Left bounded only by
`random() < :frac`, its per-outcome COUNT(*) probe against futures_odds_snapshots
grew with the population until it blew past the worker's 150s statement_timeout,
erroring the tile and blinding the Flow Sentinel's chart_density check.

The fix adds two ABSOLUTE bounds (SAMPLE_CAP outcomes, SNAP_CAP per-outcome
snapshots). These tests assert BOTH directions (gotcha #43 discipline):
  * BOUNDED — the query can never regress to a raw full-population scan, AND
  * STILL A REAL MEASUREMENT — it still samples and still returns the columns the
    consumer (chart_density_verdict / the cockpit tile) reads.

No DB is needed: the SQL is a module constant, so we assert on its text + binds.
"""

import importlib

# NB: `from app.tasks import precompute_backfill_progress` resolves to the
# registered Celery task proxy (same name), not the module. Load the module file
# explicitly to reach its constants.
pbp = importlib.import_module("app.tasks.precompute_backfill_progress")


class TestChartDensityBounds:
    def test_caps_are_positive_ints(self):
        assert isinstance(pbp.CHART_DENSITY_SAMPLE_CAP, int)
        assert isinstance(pbp.CHART_DENSITY_SNAP_CAP, int)
        assert pbp.CHART_DENSITY_SAMPLE_CAP > 0
        assert pbp.CHART_DENSITY_SNAP_CAP > 0

    def test_query_is_outcome_bounded(self):
        # An absolute LIMIT on the sampled-outcome CTE bounds the number of
        # per-outcome probes regardless of population growth — the fix's core.
        sql = pbp.CHART_DENSITY_SQL
        assert "LIMIT :cap" in sql, "sampled-outcome set must be hard-capped"

    def test_query_snapshot_probe_is_bounded(self):
        # Each per-outcome snapshot count is capped so one hyper-liquid outcome
        # can't dominate the runtime.
        sql = pbp.CHART_DENSITY_SQL
        assert "LIMIT :snapcap" in sql, "per-outcome snapshot probe must be capped"

    def test_query_still_samples(self):
        # BOTH directions: bounded, but still a random SAMPLE (not the first N rows
        # in physical order) — the cap thins on top of random() selection.
        assert "random() < :frac" in pbp.CHART_DENSITY_SQL

    def test_query_still_returns_consumer_columns(self):
        # The chart_density_verdict consumer + cockpit tile read these; the bound
        # must not have dropped the real measurement.
        sql = pbp.CHART_DENSITY_SQL
        for col in ("sampled", "below_bar", "avg_pts_per_hr", "median_pts_per_hr", "source"):
            assert col in sql

    def test_all_binds_are_supplied(self):
        # Every :param in the SQL must have a matching key passed at execute time
        # (a missing bind is an asyncpg runtime error — gotcha #45 class).
        import re

        # Match :name binds but NOT ::type casts (negative lookbehind on ':').
        binds = set(re.findall(r"(?<!:):(\w+)", pbp.CHART_DENSITY_SQL))
        supplied = {"since", "frac", "bar", "cap", "snapcap"}
        assert binds == supplied, f"bind mismatch: sql has {binds}, execute passes {supplied}"
