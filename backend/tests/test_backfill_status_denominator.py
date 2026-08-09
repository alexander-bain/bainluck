"""CAL-P014 (#1544) — a coverage percentage must publish its own denominator.

Alex's 2026-08-08 ruling: publishing the count is the standing house rule for
every exclusion. `backfill-winners/status` violated the spirit of it by naming.

The field was `total_resolved_outcomes`, which reads as "every resolved outcome".
It is not. The query filters:

    AND fo.opening_probability IS NOT NULL
    AND fo.opening_probability > 0 AND fo.opening_probability < 1

— the same PRICED predicate `coverage_universe` uses. So it counts the priced
resolved population (~1.61M) against roughly 2.6M actually-resolved outcomes, and
`pct_covered: 92.2%` answers "of outcomes that HAVE a price, how many have a
calibration price" while reading as "we have graded 92% of everything".

Everything unpriced — the provably-purged and still-recoverable cohorts CAL-P011
named and CAL-P012 counted — sits outside that denominator entirely. That is the
exact failure the reachability tier exists to prevent, reappearing one surface
over: not a wrong number, a number whose name overstates its scope.
"""

import importlib

# ``app.tasks.precompute_backfill_winners_status`` resolves to the registered
# Celery task, not the module, so read the module object explicitly.
_MODULE = importlib.import_module("app.tasks.precompute_backfill_winners_status")


def _source() -> str:
    with open(_MODULE.__file__) as fh:
        return fh.read()


class TestTheQueryIsActuallyPriceFiltered:
    def test_coverage_query_filters_to_priced_outcomes(self):
        """If this filter is ever removed the denominator changes meaning, and
        the labels below become wrong rather than merely narrow."""
        src = _source()
        assert "fo.opening_probability IS NOT NULL" in src
        assert "fo.opening_probability > 0 AND fo.opening_probability < 1" in src


class TestTheDenominatorIsPublished:
    def test_self_describing_key_exists(self):
        assert '"priced_resolved_outcomes"' in _source()

    def test_percentage_names_its_denominator(self):
        src = _source()
        assert '"pct_covered_denominator"' in src
        assert '"priced_resolved_outcomes",' in src

    def test_denominator_rule_is_stated_in_the_payload(self):
        """A reader must not have to find the WHERE clause to know what the
        number means."""
        src = _source()
        assert '"denominator_rule"' in src
        assert "opening_probability strictly between 0 and 1" in src

    def test_rule_points_at_the_unpriced_split(self):
        """The honest complement: where to find what this denominator omits."""
        assert "reachability_bridge" in _source()


class TestBackwardCompatibility:
    def test_legacy_key_is_retained(self):
        """Renaming a published key without an alias breaks dashboards. The old
        name stays until nothing reads it."""
        assert '"total_resolved_outcomes"' in _source()

    def test_both_keys_carry_the_same_value(self):
        src = _source()
        # Both are assigned from the same row attribute — no second query, no
        # chance of the alias drifting away from the real count.
        assert '"priced_resolved_outcomes": cal_row.total_resolved' in src
        assert '"total_resolved_outcomes": cal_row.total_resolved' in src

    def test_pct_covered_still_divides_by_that_same_count(self):
        assert (
            "round(100 * cal_row.has_cal_prob / max(cal_row.total_resolved, 1), 1)"
            in _source()
        )
