"""CAL-P012 (#1544) — the bounded reachability census and its publish rules.

The rule these defend, in one line: **a partial walk must never be published as
a total.** Its counts are real but its denominator is not the population, and a
number that looks like a total while covering part of the rows is worse than no
number — the same "an empty 200 is not an absence" error (gotcha #51) wearing a
total's clothing.
"""

import json

from app.tasks.census_reachability import (
    DEFAULT_SCAN,
    MAX_SCAN,
    PUBLISHED_KEY,
    is_complete_walk,
    merge_windows,
    read_published_counts,
    tier_counts_for_bridge,
)
from app.utils.calibration_coverage_bridge import (
    PRICED_TIER,
    REACHABILITY_TIER_KEYS,
    build_coverage_census,
    EXCLUSION_RUNGS,
)
from app.utils.kalshi_retention import PROVABLY_PURGED_AGE_DAYS


def _w(priced=10, purged=5, recoverable=3, unknown=2, exhausted=False, ok=True):
    return {
        PRICED_TIER: priced,
        "unpriced_provably_purged": purged,
        "unpriced_recoverable": recoverable,
        "unpriced_unknown_age": unknown,
        "exhausted": exhausted,
        "partition_ok": ok,
    }


class TestOneDefinitionOfPurged:
    def test_horizon_comes_from_the_measured_constant(self):
        """Never a second hand-rolled interval — gotcha #35's whole lesson."""
        import app.tasks.census_reachability as m

        src = open(m.__file__).read()
        assert "PROVABLY_PURGED_AGE_DAYS" in src
        assert ":purge_days" in src, "the horizon must be bound, not inlined"
        # No literal day-count intervals smuggled into the SQL.
        assert "INTERVAL '86" not in src
        assert "86 days" not in src

    def test_purge_days_is_the_shipped_constant(self):
        assert PROVABLY_PURGED_AGE_DAYS == 86

    def test_priced_predicate_mirrors_coverage_universe(self):
        """If this drifts from precompute's coverage_universe the hinge breaks."""
        import app.tasks.census_reachability as m

        src = open(m.__file__).read()
        assert "opening_probability IS NOT NULL" in src
        assert "opening_probability > 0" in src
        assert "opening_probability < 1" in src


class TestBoundedByConstruction:
    def test_scan_is_bounded(self):
        assert 0 < DEFAULT_SCAN <= MAX_SCAN

    def test_scan_is_a_row_count_not_an_id_span(self):
        """The bug production caught: ids are not uniformly dense, so a fixed id
        WIDTH times out in dense regions. ``scan`` bounds ROWS via LIMIT. A scan
        sized like an id span (tens of millions) means someone reintroduced the
        conflation."""
        assert DEFAULT_SCAN <= 2_000_000, "scan looks like an id span, not a row count"

    def test_bounds_sql_limits_rows_and_derives_the_id_range(self):
        import app.tasks.census_reachability as m

        src = open(m.__file__).read()
        assert "ORDER BY id ASC LIMIT :scan" in src
        assert "MIN(id) AS lo, MAX(id) AS hi" in src

    def test_census_sql_is_windowed_not_unbounded(self):
        """An unbounded aggregate over futures_outcomes does not return in
        production. A future 'simplification' back to one aggregate must fail
        here rather than in a timeout."""
        import app.tasks.census_reachability as m

        src = open(m.__file__).read()
        assert "fo.id >= :lo AND fo.id <= :hi" in src
        assert "statement_timeout" in src


class TestMergeAndCompleteness:
    def test_merge_sums_every_tier(self):
        t = merge_windows([_w(), _w()])
        assert t[PRICED_TIER] == 20
        assert t["unpriced_provably_purged"] == 10
        assert set(t) == set(REACHABILITY_TIER_KEYS)

    def test_merge_of_nothing_is_checked_zeros_not_missing_keys(self):
        t = merge_windows([])
        assert t == {k: 0 for k in REACHABILITY_TIER_KEYS}

    def test_walk_is_complete_only_when_last_window_exhausted(self):
        assert is_complete_walk([_w(), _w(exhausted=True)]) is True
        assert is_complete_walk([_w(), _w()]) is False
        assert is_complete_walk([]) is False


class TestPartialNeverPublishes:
    def test_partial_walk_is_not_publishable(self):
        assert tier_counts_for_bridge([_w(), _w()]) is None

    def test_complete_walk_is_publishable(self):
        got = tier_counts_for_bridge([_w(), _w(exhausted=True)])
        assert got is not None and got[PRICED_TIER] == 20

    def test_a_window_whose_partition_broke_blocks_publication(self):
        """One non-reconciling window poisons the total; refuse the whole thing."""
        assert tier_counts_for_bridge([_w(ok=False), _w(exhausted=True)]) is None

    def test_empty_tail_still_counts_as_complete(self):
        """Exhausted-with-zero-rows is a complete walk of an empty tail."""
        tail = {**{k: 0 for k in REACHABILITY_TIER_KEYS}, "exhausted": True, "partition_ok": True}
        assert tier_counts_for_bridge([_w(), tail]) is not None


class _FakeRedis:
    def __init__(self, val=None, raise_on_get=False):
        self.val, self.raise_on_get = val, raise_on_get

    def get(self, key):
        if self.raise_on_get:
            raise RuntimeError("redis down")
        return self.val


class TestReadFailsOpen:
    def test_missing_cache_returns_none(self):
        assert read_published_counts(_FakeRedis(None)) is None

    def test_none_client_returns_none(self):
        assert read_published_counts(None) is None

    def test_redis_error_returns_none_not_raise(self):
        """precompute is on the critical path; a dead cache must not break it."""
        assert read_published_counts(_FakeRedis(raise_on_get=True)) is None

    def test_garbage_returns_none(self):
        assert read_published_counts(_FakeRedis(b"not json")) is None

    def test_missing_tier_returns_none_not_partial(self):
        counts = {k: 1 for k in REACHABILITY_TIER_KEYS}
        counts.pop("unpriced_provably_purged")
        payload = json.dumps({"counts": counts}).encode()
        assert read_published_counts(_FakeRedis(payload)) is None

    def test_bool_tier_value_rejected(self):
        counts = {k: 1 for k in REACHABILITY_TIER_KEYS}
        counts["unpriced_provably_purged"] = True
        payload = json.dumps({"counts": counts}).encode()
        assert read_published_counts(_FakeRedis(payload)) is None

    def test_good_cache_round_trips(self):
        counts = {k: 7 for k in REACHABILITY_TIER_KEYS}
        payload = json.dumps({"counts": counts}).encode()
        assert read_published_counts(_FakeRedis(payload)) == counts

    def test_published_key_is_namespaced(self):
        assert PUBLISHED_KEY.startswith("calibration:")


class TestEndToEndIntoThePayload:
    def _census(self, **kw):
        rungs = {"plotted_on_curve": 10, **{k: 0 for k in EXCLUSION_RUNGS}}
        return build_coverage_census(
            rung_counts=rungs,
            sportsbook_curve_legs=5,
            published_curve_observations=15,
            published_outcomes_crosscheck=10,
            population_version="v-test",
            **kw,
        )

    def test_published_counts_reach_the_payload(self):
        counts = tier_counts_for_bridge([_w(priced=10, exhausted=True)])
        c = self._census(reachability_tier_counts=counts)
        rb = c["reachability_bridge"]
        assert rb["status"] == "complete"
        assert rb["resolved_futures_outcomes"] == 20
        cell = next(t for t in rb["tiers"] if t["key"] == "unpriced_provably_purged")
        assert cell["outcomes"] == 5 and cell["checked"] is True

    def test_no_cache_yields_unavailable_and_keeps_census_complete(self):
        c = self._census(reachability_tier_counts=None, reachability_unavailable_reason="none yet")
        assert c["reachability_bridge"]["status"] == "unavailable"
        # The load-bearing separation from CAL-P011 still holds.
        assert c["status"] == "complete" and c["invariants"]["ok"] is True

    def test_hinge_divergence_is_reported_not_absorbed(self):
        """Census priced-count disagreeing with the coverage total means the two
        stand on different populations. It must SAY so."""
        counts = tier_counts_for_bridge([_w(priced=999, exhausted=True)])
        c = self._census(reachability_tier_counts=counts)
        assert "COVERAGE_HINGE_DIVERGES" in c["reachability_bridge"]["violations"]
        assert c["invariants"]["ok"] is True  # still not the coverage bridge's fault
