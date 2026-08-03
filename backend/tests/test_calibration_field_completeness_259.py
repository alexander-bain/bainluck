"""Queue #259 Item 1 — the published-normalized-field sum-to-1 INVARIANT (C14 P1).

Queue #257 added the field-completeness gate but computed completeness/divisor
BEFORE the ``deduped`` mode-price + extreme-tail filters, so a complete normalized
field could lose a member after normalization and publish < 1.0. Queue #259 fixes
``deduped`` to EXEMPT complete normalized fields (``is_mex_normalized``) from those
placeholder heuristics, so the partition still sums to ~1.0.

The heavy CTE is Postgres-only (no test Postgres — CI has no PG service, and the
sandbox blocks shared memory), so — as with every other calibration exclusion —
the tested contract is the canonical Python mirror
(``published_normalized_field_probabilities``) executed against the counter-class
data, plus source-inspection that the shipped SQL carries the exemption + the
candidate-vs-published transparency split. A Postgres-backed contract test that
runs the real CTE lives in ``test_calibration_canonical_pg.py`` (skipped unless a
database is reachable).
"""

import inspect

import pytest

from app.tasks import precompute_calibration
from app.tasks.precompute_calibration import (
    field_is_complete_for_normalization,
    market_needs_mex_normalization,
    published_normalized_field_probabilities,
)

TOL = 1e-9


def _sum(cps, **kw):
    return sum(published_normalized_field_probabilities(cps, **kw))


# ---------------------------------------------------------------------------
# The invariant: a COMPLETE normalized field publishes every member and the
# published partition sums to ~1.0 (the fixed path), where the OLD path did not.
# ---------------------------------------------------------------------------
class TestSumToOneInvariant:
    def test_extreme_tail_counterexample_0_99_0_20_0_001(self):
        # C14's headline: cp_sum = 1.191 (> 1.15 -> a normalization candidate),
        # every member eligible & surviving -> COMPLETE. Normalized members are
        # 0.831 / 0.168 / 0.00084 — the last is < 0.005.
        cps = [0.99, 0.20, 0.001]
        assert market_needs_mex_normalization(
            n_eligible=3, n_winners=1, cp_sum=sum(cps)
        )
        assert field_is_complete_for_normalization(
            eligible_n=3, survivor_n=3, survivor_win_n=1
        )
        # Fixed (shipped) path: all 3 published, sums to 1.0.
        published = published_normalized_field_probabilities(cps)
        assert len(published) == 3
        assert abs(sum(published) - 1.0) < TOL
        # OLD path: the 0.00084 tail is dropped -> partition broken (< 1.0).
        old = published_normalized_field_probabilities(cps, apply_tail_mode_filters=True)
        assert len(old) == 2
        assert sum(old) < 1.0 - 1e-4

    def test_modal_price_counterexample_uniform_field(self):
        # A uniform field: 10 members each raw 0.15 -> cp_sum 1.5 (> 1.15). Each
        # normalizes to 0.10; that price is shared by all 10 (> max(10*0.5, 2) = 5),
        # so the OLD mode-price filter wipes the ENTIRE field. The fix publishes all.
        cps = [0.15] * 10
        assert market_needs_mex_normalization(
            n_eligible=10, n_winners=1, cp_sum=sum(cps)
        )
        published = published_normalized_field_probabilities(cps)
        assert len(published) == 10
        assert abs(sum(published) - 1.0) < TOL
        old = published_normalized_field_probabilities(cps, apply_tail_mode_filters=True)
        assert old == []  # every member removed as a modal price

    def test_ordinary_complete_field_unaffected(self):
        # A normal over-confident field with no extreme tail / mode: both paths
        # publish all members and sum to 1.0 (the fix changes nothing here).
        cps = [0.60, 0.40, 0.20]  # cp_sum 1.20 > 1.15
        published = published_normalized_field_probabilities(cps)
        old = published_normalized_field_probabilities(cps, apply_tail_mode_filters=True)
        assert len(published) == 3 and len(old) == 3
        assert abs(sum(published) - 1.0) < TOL
        assert abs(sum(old) - 1.0) < TOL

    def test_winner_above_0_98_cap_survives_after_fix(self):
        # A field whose WINNER normalizes above the old 0.98 cap: the OLD path drops
        # both the >0.98 winner and the <0.005 tails (partition destroyed); the fix
        # publishes the whole partition so it still sums to 1.0.
        cps = [1.20, 0.005, 0.005]  # cp_sum 1.21; winner 0.9917 (> 0.98)
        published = published_normalized_field_probabilities(cps)
        assert len(published) == 3
        assert abs(sum(published) - 1.0) < TOL
        old = published_normalized_field_probabilities(cps, apply_tail_mode_filters=True)
        assert sum(old) < 1.0 - 1e-4  # winner (>0.98) AND tails (<0.005) dropped


# ---------------------------------------------------------------------------
# Incomplete / winner-removed candidate fields are EXCLUDED (never normalized),
# so the invariant is vacuous for them — they contribute no published partition.
# ---------------------------------------------------------------------------
class TestIncompleteFieldsExcluded:
    def test_member_excluded_field_is_incomplete(self):
        # A member was removed by a per-outcome exclusion (survivor_n < eligible_n)
        # -> incomplete -> dropped from the curve, never normalized over survivors.
        assert not field_is_complete_for_normalization(
            eligible_n=5, survivor_n=4, survivor_win_n=1
        )

    def test_winner_removed_field_is_incomplete(self):
        # The winner itself was excluded -> normalizing losers to 1.0 would be
        # fiction -> incomplete -> excluded.
        assert not field_is_complete_for_normalization(
            eligible_n=5, survivor_n=4, survivor_win_n=0
        )


# ---------------------------------------------------------------------------
# Source-inspection: the shipped SQL carries the invariant fix + transparency.
# ---------------------------------------------------------------------------
class TestShippedSQLCarriesTheFix:
    def test_shared_population_builder_exempts_complete_fields(self):
        src = precompute_calibration._calibration_population_ctes()
        # deduped exempts complete normalized fields from the tail/mode cuts.
        assert "WHEN ro.is_mex_normalized THEN true" in src
        # mode_prices no longer lets normalized/incomplete rows vote/be removed.
        assert "AND NOT is_mex_normalized AND NOT is_field_incomplete" in src
        # the legacy tail cut still guards the NON-partition multi pool.
        assert "ro.adj_opening_probability > 0.005" in src
        assert "ELSE ro.rn = 1" in src

    def test_payload_reports_candidate_vs_published_split(self):
        # Queue 300D hoisted the bucket SELECT out of ``compute_calibration_payload``
        # into ``_main_futures_sql`` so both of its scopes could be parsed and
        # tested. Assert against the RENDERED statement rather than the enclosing
        # function's source text: it is the same guarantee, checked one step
        # closer to what the database actually receives, and it no longer breaks
        # the next time this SQL moves between functions.
        src = precompute_calibration._main_futures_sql()
        # published_summary computes post-dedup counts distinct from candidates.
        assert "published_summary" in src
        assert "mex_published_markets" in src
        assert "CROSS JOIN published_summary ps" in src

    def test_one_builder_feeds_both_consumers(self):
        # The cohort sweep builds on the SAME shared population producer, so serve
        # and audit are row-identical by construction (Queue #259 Item 2).
        from scripts.evals.cohort_sweep import load_from_session

        sweep_src = inspect.getsource(load_from_session)
        assert "_calibration_population_ctes()" in sweep_src
        assert "FROM deduped" in sweep_src


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
