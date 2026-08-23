"""The ordering policy's suite — the part that decides what survives.

Queue 389 Item 1 (#2077). Every test here fixes the clock explicitly and derives
its dates by OFFSET from that clock, never by pinning an hour (gotcha #44: offset
first, then truncate; an anchor containing an ``if`` has not been fixed).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.utils.kalshi_retention import CAPTURE_PLANNING_AGE_DAYS
from app.utils.settlement_sweep_plan import (
    BUCKETS,
    NON_TERMINAL_RESERVE,
    TERMINAL_BUCKET,
    Candidate,
    bucket_for,
    burn_down,
    order_candidates,
    plan_sweep,
)

#: A fixed instant. The suite never reads the wall clock, so it cannot go red in
#: the evening and green in the morning.
NOW = datetime(2026, 8, 21, 12, 0, tzinfo=timezone.utc)


def candidate(market_id: int, days_remaining: float | None, reason: str = "missing_winner") -> Candidate:
    """Build a candidate with an exact days-remaining, derived from ``NOW``.

    ``days_remaining = CAPTURE_PLANNING_AGE_DAYS - age``, so
    ``age = CAPTURE_PLANNING_AGE_DAYS - days_remaining``.
    """
    if days_remaining is None:
        resolution = None
    else:
        age = CAPTURE_PLANNING_AGE_DAYS - days_remaining
        resolution = NOW - timedelta(days=age)
    return Candidate(
        market_id=market_id,
        source="kalshi",
        external_id=f"KXTEST-{market_id}",
        resolution_date=resolution,
        candidate_reason=reason,
    )


class TestBucketing:
    @pytest.mark.parametrize("label,low,high", BUCKETS)
    def test_each_bucket_claims_its_own_edges(self, label, low, high):
        assert bucket_for(low) == label
        assert bucket_for(high) == label

    def test_buckets_tile_with_no_gap(self):
        """A gap swallows rows silently — they would sort as `future` and never run."""
        edges = [(low, high) for _, low, high in BUCKETS]
        for (_, prev_high), (next_low, _) in zip(edges, edges[1:]):
            assert next_low == prev_high + 1

    def test_negative_is_expired_not_bucket_zero(self):
        assert bucket_for(-0.5) == "expired"
        assert bucket_for(-40) == "expired"

    def test_unknown_and_future_are_NAMED_not_dropped(self):
        """Silently filtering them reports a clean run over an undefined population."""
        assert bucket_for(None) == "unknown"
        assert bucket_for(500) == "future"


class TestOrdering:
    def test_terminal_bucket_sorts_ahead_of_everything(self):
        cands = [candidate(1, 70), candidate(2, 40), candidate(3, 3), candidate(4, 20)]
        ordered = order_candidates(cands, NOW)
        assert ordered[0].market_id == 3

    def test_within_a_bucket_the_nearest_deadline_goes_first(self):
        cands = [candidate(1, 7), candidate(2, 1), candidate(3, 4)]
        assert [c.market_id for c in order_candidates(cands, NOW)] == [2, 3, 1]

    def test_expired_and_unknown_never_displace_a_saveable_row(self):
        """gotcha #41's inverse: grinding the already-dead before the dying."""
        cands = [candidate(1, -10), candidate(2, None), candidate(3, 70)]
        ordered = order_candidates(cands, NOW)
        assert ordered[0].market_id == 3

    def test_ordering_is_deterministic_to_the_row(self):
        """Rehearsal and run must select the SAME rows, not the same count."""
        cands = [candidate(i, 30) for i in range(20)]
        first = [c.market_id for c in order_candidates(list(reversed(cands)), NOW)]
        second = [c.market_id for c in order_candidates(cands, NOW)]
        assert first == second == sorted(c.market_id for c in cands)


class TestPlanSweep:
    def test_the_terminal_bucket_is_taken_before_the_big_one(self):
        cands = [candidate(i, 3) for i in range(5)] + [candidate(100 + i, 70) for i in range(50)]
        selected, _ = plan_sweep(cands, budget=10, now=NOW)
        terminal_ids = {c.market_id for c in selected if c.market_id < 5}
        assert terminal_ids == {0, 1, 2, 3, 4}

    def test_a_huge_terminal_bucket_cannot_starve_the_rest(self):
        """The reserve exists because starvation runs in both directions."""
        cands = [candidate(i, 3) for i in range(100)] + [candidate(1000 + i, 70) for i in range(100)]
        budget = 20
        selected, _ = plan_sweep(cands, budget=budget, now=NOW)
        non_terminal = [c for c in selected if c.market_id >= 1000]
        assert len(selected) == budget
        assert len(non_terminal) >= budget * NON_TERMINAL_RESERVE

    def test_with_nothing_else_to_do_the_terminal_bucket_may_use_the_whole_budget(self):
        cands = [candidate(i, 3) for i in range(50)]
        selected, _ = plan_sweep(cands, budget=20, now=NOW)
        assert len(selected) == 20

    def test_what_was_dropped_is_REPORTED_per_bucket(self):
        """A silent cap reads as 'covered everything'. In a burn-down that is fatal."""
        cands = [candidate(i, 3) for i in range(5)] + [candidate(100 + i, 70) for i in range(30)]
        selected, skipped = plan_sweep(cands, budget=10, now=NOW)
        assert len(selected) == 10
        assert sum(skipped.values()) == len(cands) - 10
        assert skipped["61-74"] > 0

    def test_a_budget_larger_than_the_work_selects_everything_and_skips_nothing(self):
        cands = [candidate(i, 30) for i in range(5)]
        selected, skipped = plan_sweep(cands, budget=100, now=NOW)
        assert len(selected) == 5
        assert skipped == {}

    def test_selection_never_exceeds_its_budget(self):
        cands = [candidate(i, i % 70) for i in range(200)]
        for budget in (0, 1, 7, 50, 199, 200, 500):
            selected, _ = plan_sweep(cands, budget=budget, now=NOW)
            assert len(selected) <= budget

    def test_every_candidate_is_either_selected_or_counted_as_skipped(self):
        """No row may fall out of the plan unaccounted for."""
        cands = [candidate(i, i % 80 - 5) for i in range(120)]
        selected, skipped = plan_sweep(cands, budget=33, now=NOW)
        assert len(selected) + sum(skipped.values()) == len(cands)


class TestBurnDown:
    def test_counts_every_bucket_including_the_unsaveable(self):
        cands = [candidate(1, 3), candidate(2, 3), candidate(3, 70), candidate(4, -1), candidate(5, None)]
        counts = burn_down(cands, NOW)
        assert counts[TERMINAL_BUCKET] == 2
        assert counts["61-74"] == 1
        assert counts["expired"] == 1
        assert counts["unknown"] == 1

    def test_the_total_is_conserved(self):
        cands = [candidate(i, i % 90 - 8) for i in range(150)]
        assert sum(burn_down(cands, NOW).values()) == 150


class TestClockDiscipline:
    def test_the_plan_does_not_read_the_wall_clock_when_given_a_time(self):
        """gotcha #44: a test anchor that branches on the clock is not fixed.

        Running the same plan against two very different 'now' values must move the
        buckets, which proves ``now`` is genuinely threaded through rather than
        quietly replaced by ``datetime.now()`` somewhere inside.
        """
        cands = [candidate(1, 70)]
        near = order_candidates(cands, NOW)[0].days_remaining(NOW)
        far = order_candidates(cands, NOW + timedelta(days=400))[0].days_remaining(
            NOW + timedelta(days=400)
        )
        assert near == pytest.approx(70, abs=0.01)
        assert far == pytest.approx(-330, abs=0.01)
        assert bucket_for(far) == "expired"
