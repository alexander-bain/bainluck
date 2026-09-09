"""Guard tests for the density + success-cohort census bounds (#4444, ship #4456).

## what these hold

Both tiles ran an uncorrelated-per-row `COUNT(*)` against `futures_odds_snapshots`
(205M rows / 53 GB), once per sampled outcome, with **no cap**. Measured on
`pg_stat_statements` over 2026-08-31 18:50Z -> 2026-09-09 21:18Z (9.1 d):

    statement                     calls   GB read   GB/call
    density   (WITH ro AS ...)      227     566.0     2.493
    cohort    (WITH ro AS ...)      226     448.9     1.986
    chart_density (WITH uv AS ...)  225      91.9     0.409   <- already capped

1,015 GB of the window's 7,940 GB database-wide -- the two largest disk readers
in the database, and 8x the accuracy rebuild they share the 2-slot `heavy` queue
with. The module's own #202 comment asserted they were "self-bounded by a small,
fixed window"; the resolved window is ~948,000 markets and that premise expired.

## why the text assertions here are not the whole gate

These run with no DB, so they can only assert the bounds are still IN the SQL --
the same thing `test_backfill_progress_chart_density.py` does for the capped
sibling. What they CANNOT grade is whether the caps produce the right numbers,
which is the actual claim. That is
`tests/integration/test_census_cap_real_postgres.py`, which executes both
statements against a real server.

## gotcha #43 discipline: both directions

Every bound below is paired with an assertion that the tile is STILL A REAL
MEASUREMENT -- a query that returned nothing would satisfy "bounded" perfectly.
"""

import importlib
import re

# NB: `from app.tasks import precompute_backfill_progress` resolves to the
# registered Celery task proxy (same name), not the module. Load the module file
# explicitly to reach its constants.
pbp = importlib.import_module("app.tasks.precompute_backfill_progress")

_TILES = (("DENSITY_SQL", "density"), ("SUCCESS_COHORT_SQL", "success_cohort"))


class TestSnapCapIsDerivedNotChosen:
    """CENSUS_SNAP_CAP's correctness is its DERIVATION, so that is what is held.

    At `DENSE_POINTS + 1` both surviving predicates are exact for every row:
    `snaps >= DENSE_POINTS` and `snaps >= 1` read the same as they did uncapped.
    A cap of, say, 10 would still be "a positive int" and would silently zero the
    dense rate on every source -- which is why `> 0` is not the assertion.
    """

    def test_snap_cap_strictly_exceeds_the_dense_threshold(self):
        assert pbp.CENSUS_SNAP_CAP > pbp.DENSE_POINTS, (
            "a cap at or below DENSE_POINTS makes `snaps >= DENSE_POINTS` "
            "unsatisfiable -- the dense rate would read 0.0 on every source and "
            "nothing else in the tile would look wrong"
        )

    def test_snap_cap_is_derived_from_dense_points(self):
        # ⚠️ A VALUE comparison cannot grade this. `CENSUS_SNAP_CAP = 16` passes
        # `== DENSE_POINTS + 1` today and drifts silently the moment DENSE_POINTS
        # moves -- that mutation survived the first red arm of this file, which
        # is why the assertion is on the ASSIGNMENT rather than on the number.
        # Parsed, not grepped: a comment mentioning DENSE_POINTS beside a literal
        # would satisfy a substring search.
        import ast
        import inspect

        tree = ast.parse(inspect.getsource(pbp))
        rhs = [
            node.value
            for node in ast.walk(tree)
            if isinstance(node, ast.Assign)
            and any(
                isinstance(t, ast.Name) and t.id == "CENSUS_SNAP_CAP"
                for t in node.targets
            )
        ]
        assert len(rhs) == 1, "CENSUS_SNAP_CAP must be assigned exactly once"
        names = {n.id for n in ast.walk(rhs[0]) if isinstance(n, ast.Name)}
        assert "DENSE_POINTS" in names, (
            "CENSUS_SNAP_CAP must be COMPUTED from DENSE_POINTS, not written as "
            "a literal that happens to equal it today"
        )
        assert pbp.CENSUS_SNAP_CAP == pbp.DENSE_POINTS + 1

    def test_group_sample_cap_is_a_positive_int(self):
        assert isinstance(pbp.CENSUS_GROUP_SAMPLE_CAP, int)
        assert pbp.CENSUS_GROUP_SAMPLE_CAP > 0


class TestBothTilesAreBounded:
    def test_snapshot_probe_is_capped(self):
        for name, _ in _TILES:
            sql = getattr(pbp, name)
            assert "LIMIT :snapcap" in sql, (
                f"{name}: the per-outcome COUNT(*) probe must be capped -- an "
                "uncapped one reads the outcome's whole history, and #3716 "
                "(autovacuum_count = 0 on futures_odds_snapshots) means every "
                "counted row costs a heap fetch"
            )

    def test_the_uncapped_probe_shape_is_gone(self):
        # The exact shape that cost 1,015 GB. A cap added ALONGSIDE a surviving
        # raw probe would pass every other test in this file.
        raw = re.compile(
            r"SELECT\s+COUNT\(\*\)\s+FROM\s+futures_odds_snapshots\s+s\s+"
            r"WHERE\s+s\.outcome_id\s*=\s*ro\.oid\s*\)",
            re.I,
        )
        for name, _ in _TILES:
            assert not raw.search(getattr(pbp, name)), (
                f"{name}: the uncapped per-outcome COUNT(*) is back"
            )

    def test_probe_count_is_capped_per_group(self):
        for name, _ in _TILES:
            sql = getattr(pbp, name)
            assert "ROW_NUMBER() OVER" in sql and "rn <= :percap" in sql, (
                f"{name}: the number of per-outcome probes must be bounded"
            )

    def test_the_per_group_cap_is_not_a_flat_limit(self):
        # THE trap this fix exists to avoid. `LIMIT :percap` with no ORDER BY
        # takes SCAN order, which correlates with id, which correlates with
        # resolution month -- on the density tile (28 groups running 3 -> 36,909
        # rows, measured 2026-09-09) it would truncate to the oldest months and
        # drop the newest entirely, gutting the per-month trend the tile is for.
        for name, _ in _TILES:
            sql = getattr(pbp, name)
            assert "LIMIT :percap" not in sql, (
                f"{name}: a flat LIMIT would starve the small groups; the cap "
                "must be PARTITIONed by the tile's own GROUP BY"
            )

    def test_the_partition_matches_the_tiles_own_group_by(self):
        # A cap partitioned by anything other than what the tile GROUPs BY can
        # still starve a reported group.
        assert "PARTITION BY fm.source, to_char(fm.resolution_date, 'YYYY-MM')" in pbp.DENSITY_SQL
        assert "GROUP BY source, mon" in pbp.DENSITY_SQL
        assert "PARTITION BY fm.source" in pbp.SUCCESS_COHORT_SQL
        assert "GROUP BY source" in pbp.SUCCESS_COHORT_SQL

    def test_the_probe_runs_once_per_row_not_once_per_reference(self):
        # A CTE referenced once is INLINED (PG12+), which duplicates its
        # target-list subquery once per reference to the column it computes.
        # `snaps` is read three times in the density SELECT, so the probe ran
        # three times per outcome; the production planner confirmed 3 SubPlan
        # nodes as-written and 1 with MATERIALIZED (cohort 2 -> 1,
        # chart_density 3 -> 1). Dropping the keyword restores a 2-3x cost with
        # nothing else looking wrong.
        for name, _ in _TILES:
            assert "os AS MATERIALIZED (" in getattr(pbp, name), (
                f"{name}: the probe CTE must be MATERIALIZED or it is re-run "
                "once per reference to `snaps`"
            )
        assert "d AS MATERIALIZED (" in pbp.CHART_DENSITY_SQL, (
            "chart_density carries the same defect and the same one-word fix"
        )

    def test_the_within_group_pick_is_random_not_physical(self):
        # Without `ORDER BY random()` the window re-introduces exactly the
        # scan-order bias the PARTITION was added to avoid, one level down.
        for name, _ in _TILES:
            assert "ORDER BY random()" in getattr(pbp, name), (
                f"{name}: the per-group pick must be a random sample"
            )


class TestBothTilesAreStillRealMeasurements:
    """The other direction (gotcha #43): a bounded query that measures nothing
    would satisfy every assertion above."""

    def test_both_still_sample_the_population(self):
        for name, _ in _TILES:
            assert "random() < :frac" in getattr(pbp, name)

    def test_density_still_returns_its_consumer_columns(self):
        for col in ("source", "mon", "sampled", "ge_dense", "any_snap",
                    "has_cal", "avg_snaps"):
            assert col in pbp.DENSITY_SQL

    def test_cohort_still_returns_its_consumer_columns(self):
        for col in ("source", "sampled", "has_cal", "ge_dense",
                    "cal_and_dense", "authoritative"):
            assert col in pbp.SUCCESS_COHORT_SQL

    def test_the_dense_predicate_still_reads_the_real_threshold(self):
        # `snaps >= :dense`, bound to DENSE_POINTS -- not a literal frozen into
        # the SQL, which would drift the moment DENSE_POINTS moved.
        for name, _ in _TILES:
            assert "snaps >= :dense" in getattr(pbp, name)

    def test_density_still_reads_the_any_snapshot_rate(self):
        assert "snaps >= 1" in pbp.DENSITY_SQL


class TestBindsMatchWhatIsExecuted:
    """A missing bind is an asyncpg runtime error the tile's own try/except
    would swallow into a degraded tile (gotcha #45 class) -- the census would
    quietly serve its prior cached value forever."""

    #: What each call site passes, read from the source below rather than
    #: trusted: the assertion is that the two agree.
    _SUPPLIED = {"since", "frac", "dense", "snapcap", "percap"}

    def _binds(self, sql):
        # Match :name binds but NOT ::type casts (negative lookbehind on ':').
        return set(re.findall(r"(?<!:):(\w+)", sql))

    def test_density_binds_match(self):
        assert self._binds(pbp.DENSITY_SQL) == self._SUPPLIED

    def test_cohort_binds_match(self):
        assert self._binds(pbp.SUCCESS_COHORT_SQL) == self._SUPPLIED

    def test_the_call_sites_really_pass_those_keys(self):
        # Reads the executing source, so this cannot pass on a stale copy of the
        # parameter dict living only in this test.
        import inspect

        src = inspect.getsource(pbp._precompute_backfill_progress)
        assert 'text(DENSITY_SQL)' in src
        assert 'text(SUCCESS_COHORT_SQL)' in src
        for key in self._SUPPLIED:
            assert f'"{key}":' in src, f"call sites never bind :{key}"


class TestTheCappedMeanIsNamedHonestly:
    """`avg_snapshots` cannot survive a cap of 16 -- datagolf's honest 270.8
    would print as ~15. The rates are exact; the mean is not, and the payload
    key has to say which is which."""

    def test_the_payload_does_not_publish_a_bare_avg_snapshots(self):
        import inspect

        src = inspect.getsource(pbp._precompute_backfill_progress)
        assert '"avg_snapshots":' not in src, (
            "a capped mean published under the uncapped name is a wrong number "
            "with no way for its reader to know"
        )
        assert '"avg_snapshots_capped":' in src

    def test_the_cap_travels_with_the_tile(self):
        # A reader who sees a capped mean must be able to read the cap that
        # produced it out of the same payload.
        import inspect

        src = inspect.getsource(pbp._precompute_backfill_progress)
        assert '"snap_cap": CENSUS_SNAP_CAP' in src
        assert '"group_sample_cap": CENSUS_GROUP_SAMPLE_CAP' in src
