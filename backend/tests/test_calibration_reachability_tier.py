"""CAL-P011 (#1544, Alex ruling 2026-08-08) — the reachability tier.

The ruling: *provably-purged outcomes become a NAMED TIER in the coverage census
— visible with its own count, never invisible in the ungraded remainder.*

What these tests defend, in order of how badly each failure would hurt:

1. The purged count is never folded into any other tier. That fold IS the defect
   — it is what let #683 sit open as a P0 for ten weeks, because "not done yet"
   and "gone forever" were one number.
2. Unknown never becomes zero, and checked-zero is distinguishable from
   unmeasured — inherited verbatim from the coverage bridge.
3. An unwired reachability tier never marks a SOUND coverage bridge broken.
4. The section is explicitly unavailable, never silently absent.
"""

import pytest

from app.utils.calibration_coverage_bridge import (
    PRICED_TIER,
    REACHABILITY_TIER_KEYS,
    REACHABILITY_TIERS,
    STATUS_COMPLETE,
    STATUS_INCOMPLETE,
    STATUS_UNAVAILABLE,
    UNPRICED_TIERS,
    build_coverage_census,
    build_reachability_bridge,
    census_is_complete,
    unavailable_census,
)


def _counts(priced=100, purged=70, recoverable=20, unknown=10):
    return {
        PRICED_TIER: priced,
        "unpriced_provably_purged": purged,
        "unpriced_recoverable": recoverable,
        "unpriced_unknown_age": unknown,
    }


class TestTierContract:
    def test_purged_is_its_own_named_tier(self):
        """The ruling in one assertion: the purged cohort has its own key."""
        assert "unpriced_provably_purged" in REACHABILITY_TIER_KEYS

    def test_purged_recoverable_and_unknown_are_three_distinct_tiers(self):
        """Never two. Collapsing any pair re-creates the defect."""
        for key in (
            "unpriced_provably_purged",
            "unpriced_recoverable",
            "unpriced_unknown_age",
        ):
            assert key in UNPRICED_TIERS
        assert len(set(UNPRICED_TIERS)) == 3

    def test_priced_tier_is_terminal_and_not_an_absence(self):
        assert REACHABILITY_TIERS[0][0] == PRICED_TIER
        assert PRICED_TIER not in UNPRICED_TIERS

    def test_every_tier_carries_a_user_facing_rule(self):
        for key, rule in REACHABILITY_TIERS:
            assert rule.strip(), f"{key} has no rule sentence"

    def test_tier_keys_are_unique(self):
        assert len(REACHABILITY_TIER_KEYS) == len(set(REACHABILITY_TIER_KEYS))


class TestPartition:
    def test_tiers_sum_to_the_resolved_total(self):
        b = build_reachability_bridge(_counts(), coverage_total=100)
        assert b["resolved_futures_outcomes"] == 200
        assert b["reconciles"] is True
        assert b["residual"] == 0
        assert b["status"] == STATUS_COMPLETE
        assert b["violations"] == []

    def test_purged_count_is_published_verbatim(self):
        """Visible with its OWN count — not netted into anything."""
        b = build_reachability_bridge(_counts(purged=70088), coverage_total=100)
        cell = next(c for c in b["tiers"] if c["key"] == "unpriced_provably_purged")
        assert cell["outcomes"] == 70088
        assert cell["checked"] is True

    def test_resolved_total_is_strictly_larger_than_coverage(self):
        b = build_reachability_bridge(_counts(), coverage_total=100)
        assert b["resolved_futures_outcomes"] > 100

    @pytest.mark.parametrize("missing", list(REACHABILITY_TIER_KEYS))
    def test_any_unmeasured_tier_blocks_the_total(self, missing):
        """NON-VACUITY BY MUTATION: drop one tier at a time; the sum must refuse
        to reconcile every time. A total that survives a missing member is a
        residual pretending to be a measurement."""
        counts = _counts()
        counts[missing] = None
        b = build_reachability_bridge(counts, coverage_total=100)
        assert b["resolved_futures_outcomes"] is None
        assert b["reconciles"] is False
        assert "REACHABILITY_TIER_UNKNOWN" in b["violations"]
        assert b["status"] == STATUS_INCOMPLETE


class TestUnknownNeverBecomesZero:
    def test_unmeasured_tier_is_none_not_zero(self):
        counts = _counts()
        counts["unpriced_provably_purged"] = None
        b = build_reachability_bridge(counts, coverage_total=100)
        cell = next(c for c in b["tiers"] if c["key"] == "unpriced_provably_purged")
        assert cell["outcomes"] is None
        assert cell["checked"] is False

    def test_checked_zero_is_distinguishable_from_unmeasured(self):
        """0-with-checked and None are two DIFFERENT claims."""
        zero = build_reachability_bridge(_counts(purged=0), coverage_total=100)
        zero_cell = next(
            c for c in zero["tiers"] if c["key"] == "unpriced_provably_purged"
        )
        assert zero_cell["outcomes"] == 0 and zero_cell["checked"] is True
        assert zero["reconciles"] is True

        counts = _counts()
        counts["unpriced_provably_purged"] = None
        unk = build_reachability_bridge(counts, coverage_total=100)
        unk_cell = next(
            c for c in unk["tiers"] if c["key"] == "unpriced_provably_purged"
        )
        assert unk_cell["outcomes"] is None and unk_cell["checked"] is False
        assert zero_cell != unk_cell

    def test_bool_is_not_accepted_as_a_count(self):
        """``True`` is an int in Python; it is not a measurement."""
        counts = _counts()
        counts["unpriced_provably_purged"] = True
        b = build_reachability_bridge(counts, coverage_total=100)
        cell = next(c for c in b["tiers"] if c["key"] == "unpriced_provably_purged")
        assert cell["outcomes"] is None
        assert cell["checked"] is False


class TestHinge:
    def test_priced_tier_must_agree_with_the_coverage_total(self):
        b = build_reachability_bridge(_counts(priced=100), coverage_total=100)
        assert "COVERAGE_HINGE_DIVERGES" not in b["violations"]

    def test_divergent_hinge_is_a_violation(self):
        """Two reconciliations standing on different populations must SAY so."""
        b = build_reachability_bridge(_counts(priced=100), coverage_total=999)
        assert "COVERAGE_HINGE_DIVERGES" in b["violations"]
        assert b["status"] == STATUS_INCOMPLETE

    def test_unknown_coverage_total_leaves_the_hinge_unchecked(self):
        b = build_reachability_bridge(_counts(), coverage_total=None)
        assert "COVERAGE_HINGE_UNCHECKED" in b["violations"]


class TestUnavailableRatherThanAbsent:
    def test_none_counts_produce_an_explicit_unavailable_section(self):
        b = build_reachability_bridge(None, coverage_total=100)
        assert b["status"] == STATUS_UNAVAILABLE
        assert b["violations"] == ["REACHABILITY_UNAVAILABLE"]
        assert b["resolved_futures_outcomes"] is None

    def test_unavailable_still_names_every_tier(self):
        """Absent keys would read as 'nothing was purged'. Name them, count None."""
        b = build_reachability_bridge(None, coverage_total=100)
        assert [c["key"] for c in b["tiers"]] == list(REACHABILITY_TIER_KEYS)
        assert all(c["outcomes"] is None and c["checked"] is False for c in b["tiers"])

    def test_unavailable_carries_the_reason(self):
        b = build_reachability_bridge(None, coverage_total=None, unavailable_reason="nope")
        assert b["reason"] == "nope"

    def test_empty_dict_is_treated_as_unavailable_not_as_zeros(self):
        b = build_reachability_bridge({}, coverage_total=100)
        assert b["status"] == STATUS_UNAVAILABLE


class TestCensusIntegration:
    def _census(self, **kw):
        rungs = {"plotted_on_curve": 10}
        from app.utils.calibration_coverage_bridge import EXCLUSION_RUNGS

        for key in EXCLUSION_RUNGS:
            rungs[key] = 0
        params = dict(
            rung_counts=rungs,
            sportsbook_curve_legs=5,
            published_curve_observations=15,
            published_outcomes_crosscheck=10,
            population_version="v-test",
        )
        params.update(kw)
        return build_coverage_census(**params)

    def test_census_always_carries_a_reachability_section(self):
        assert "reachability_bridge" in self._census()

    def test_unwired_tier_does_not_break_a_sound_coverage_bridge(self):
        """The load-bearing separation: an unwired tier ABOVE the bridge must not
        make the bridge below it report as broken."""
        c = self._census()
        assert c["status"] == STATUS_COMPLETE
        assert c["invariants"]["ok"] is True
        assert census_is_complete(c) is True
        assert c["reachability_bridge"]["status"] == STATUS_UNAVAILABLE

    def test_reachability_violations_stay_out_of_census_invariants(self):
        c = self._census(reachability_tier_counts=_counts(priced=999))
        assert "COVERAGE_HINGE_DIVERGES" in c["reachability_bridge"]["violations"]
        assert c["invariants"]["ok"] is True

    def test_wired_tier_reconciles_against_the_real_coverage_total(self):
        c = self._census(reachability_tier_counts=_counts(priced=10))
        rb = c["reachability_bridge"]
        assert rb["status"] == STATUS_COMPLETE
        assert rb["resolved_futures_outcomes"] == 110
        assert "COVERAGE_HINGE_DIVERGES" not in rb["violations"]

    def test_unavailable_census_also_names_the_tier(self):
        c = unavailable_census("build disabled")
        assert c["reachability_bridge"]["status"] == STATUS_UNAVAILABLE
        assert [t["key"] for t in c["reachability_bridge"]["tiers"]] == list(
            REACHABILITY_TIER_KEYS
        )


class TestRetentionAlignment:
    def test_purged_rule_stands_on_the_measured_horizon(self):
        """The tier's meaning must track the CAL-P008 constant, not prose."""
        from app.utils import kalshi_retention

        assert kalshi_retention.PROVABLY_PURGED_AGE_DAYS == 86
        rule = dict(REACHABILITY_TIERS)["unpriced_provably_purged"]
        assert "MEASURED" in rule
