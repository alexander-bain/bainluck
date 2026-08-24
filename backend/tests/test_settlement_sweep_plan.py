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
    TIER_NEVER_PROBED,
    TIER_STABLE_NONANSWER,
    TIER_TRANSIENT_ONLY,
    Candidate,
    attempt_tier_from_dispositions,
    bucket_for,
    burn_down,
    order_candidates,
    plan_sweep,
    tier_counts,
)
from app.utils.settlement_sweep_query import (
    RETRYABLE_DISPOSITIONS,
    TERMINAL_DISPOSITIONS,
)
from app.utils.settlement_truth import (
    STABLE_NONANSWER_DISPOSITION_VALUES,
    TRANSIENT_DISPOSITION_VALUES,
    Disposition,
    is_stable_nonanswer,
)

#: A fixed instant. The suite never reads the wall clock, so it cannot go red in
#: the evening and green in the morning.
NOW = datetime(2026, 8, 21, 12, 0, tzinfo=timezone.utc)


def candidate(
    market_id: int,
    days_remaining: float | None,
    reason: str = "missing_winner",
    *,
    attempts: int = 0,
    stable_nonanswers: int = 0,
) -> Candidate:
    """Build a candidate with an exact days-remaining, derived from ``NOW``.

    ``days_remaining = CAPTURE_PLANNING_AGE_DAYS - age``, so
    ``age = CAPTURE_PLANNING_AGE_DAYS - days_remaining``.

    ``attempts`` / ``stable_nonanswers`` default to the never-probed shape, so every
    test written before #2175 keeps meaning what it meant.
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
        attempts=attempts,
        stable_nonanswers=stable_nonanswers,
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

    def test_the_tiling_holds_for_FRACTIONAL_days_too(self):
        """The test above checks the CONSTANT TABLE; this one checks the FUNCTION.

        They are not the same claim, and the difference shipped a defect. ``BUCKETS``
        tiled perfectly in whole days while ``bucket_for`` — comparing a float against
        inclusive integer ends — left ``(7, 8)``, ``(14, 15)``, ``(30, 31)`` and
        ``(60, 61)`` in no bucket at all. ``days_remaining`` is derived from two
        timestamps, so it is fractional essentially always: production carried 1,201
        such rows on 2026-08-24, named ``future`` and sorted last while up to eight
        days from expiry.
        """
        named = {label for label, _, _ in BUCKETS}
        step = 0.1
        value = 0.0
        while value <= max(high for _, _, high in BUCKETS):
            assert bucket_for(value) in named, f"{value} fell through every bucket"
            value = round(value + step, 6)

    def test_fractional_days_round_toward_urgency(self):
        """Ties go to the bucket that dies sooner: over-including costs a probe,
        under-including costs the row."""
        assert bucket_for(7.9) == "0-7"
        assert bucket_for(14.5) == "8-14"
        assert bucket_for(30.99) == "15-30"
        assert bucket_for(60.5) == "31-60"

    def test_a_row_in_the_old_gap_outranks_the_big_bucket(self):
        """The consequence, not just the label. A row eight days from expiry must not
        sort behind rows with two months of life left."""
        nearly_terminal = candidate(1, 7.6)  # in the old (7, 8) gap -> was `future`
        long_lived = candidate(2, 61)
        ordered = order_candidates([long_lived, nearly_terminal], NOW)
        assert [c.market_id for c in ordered] == [1, 2]

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


class TestProbeHistoryTiering:
    """#2175 — the terminal bucket livelocked on rows the source had already declined.

    The defect these guard is a COMPOSITION of two correct behaviours:
    ``ambiguous_empty`` is rightly non-terminal (so it is re-probed), and the
    planner is rightly oldest-first (so it is re-probed FIRST). Every test below
    fails against the pre-#2175 planner, which is the point — see the
    red-first receipt in the queue 405 report.
    """

    def test_a_never_probed_row_outranks_an_older_stale_one_in_the_same_bucket(self):
        """The defect itself, in one assertion.

        The stale row is OLDER, so the pre-fix key put it first and it stayed first
        on every subsequent pass. Both rows are in the terminal bucket.
        """
        stale = candidate(1, 1.0, attempts=3, stable_nonanswers=3)
        fresh = candidate(2, 6.0)

        ordered = order_candidates([stale, fresh], NOW)

        assert [c.market_id for c in ordered] == [2, 1]

    def test_a_binding_budget_spends_on_the_row_that_can_answer(self):
        """The consequence: with room for one probe, do not re-ask the unanswerable."""
        stale = candidate(1, 0.5, attempts=4, stable_nonanswers=4)
        transient = candidate(2, 3.0, attempts=1, stable_nonanswers=0)
        fresh = candidate(3, 6.0)

        selected, skipped = plan_sweep([stale, transient, fresh], budget=1, now=NOW)

        assert [c.market_id for c in selected] == [3]
        assert skipped[TERMINAL_BUCKET] == 2

    def test_transient_failures_outrank_stable_nonanswers(self):
        """A 429 is a channel failure; a 200-with-nothing is the source's answer.

        227 rows stuck on ``rate_limited`` (#2174) sat behind 341 unanswerable ones.
        """
        stale = candidate(1, 1.0, attempts=1, stable_nonanswers=1)
        transient = candidate(2, 1.0, attempts=1, stable_nonanswers=0)

        ordered = order_candidates([stale, transient], NOW)

        assert [c.market_id for c in ordered] == [2, 1]

    def test_stale_rows_are_still_probed_when_the_budget_allows(self):
        """The fix must be an ORDER, not an exclusion.

        If tier 2 became unreachable this would be ``AMBIGUOUS_EMPTY`` promoted to
        terminal by the back door — "we could not tell" recorded as "we are done
        asking", which is the one conversion the capture program exists to refuse.
        """
        stale = candidate(1, 1.0, attempts=9, stable_nonanswers=9)
        fresh = candidate(2, 6.0)

        selected, skipped = plan_sweep([stale, fresh], budget=2, now=NOW)

        assert {c.market_id for c in selected} == {1, 2}
        assert not skipped

    def test_the_deadline_bucket_still_outranks_probe_history(self):
        """Bucket rank stays the OUTERMOST key, and that is not negotiable.

        A stale row in the dying bucket must still beat a pristine row with sixty
        days of slack: the terminal bucket is the one that stops existing, and
        trading a permanent loss for a temporary one is not an improvement.
        """
        dying_but_stale = candidate(1, 2.0, attempts=5, stable_nonanswers=5)
        fresh_but_safe = candidate(2, 70.0)

        ordered = order_candidates([dying_but_stale, fresh_but_safe], NOW)

        assert [c.market_id for c in ordered] == [1, 2]

    def test_repeated_asks_yield_to_less_asked_rows_in_the_same_tier(self):
        """Within a tier, spread the retries instead of grinding one subset."""
        asked_often = candidate(1, 1.0, attempts=8, stable_nonanswers=8)
        asked_once = candidate(2, 1.0, attempts=1, stable_nonanswers=1)

        ordered = order_candidates([asked_often, asked_once], NOW)

        assert [c.market_id for c in ordered] == [2, 1]

    def test_ordering_is_still_deterministic_to_the_row(self):
        """Ties break on market_id, so a rehearsal and its run select the same rows."""
        cands = [candidate(i, 3.0, attempts=1, stable_nonanswers=1) for i in (7, 3, 9, 1)]
        assert [c.market_id for c in order_candidates(cands, NOW)] == [1, 3, 7, 9]
        assert [c.market_id for c in order_candidates(list(reversed(cands)), NOW)] == [
            1,
            3,
            7,
            9,
        ]


class TestAttemptTier:
    def test_a_never_probed_market_is_tier_zero(self):
        assert candidate(1, 5.0).attempt_tier() == TIER_NEVER_PROBED

    def test_channel_failures_alone_are_tier_one(self):
        assert candidate(1, 5.0, attempts=3).attempt_tier() == TIER_TRANSIENT_ONLY

    def test_any_stable_nonanswer_is_tier_two(self):
        c = candidate(1, 5.0, attempts=3, stable_nonanswers=1)
        assert c.attempt_tier() == TIER_STABLE_NONANSWER

    def test_tier_is_ever_not_last(self):
        """A later 429 does not un-tell us what the source already said.

        Reading only the most recent disposition would let one transient failure
        promote a known-unanswerable market back to the head of the queue — the
        livelock wearing a hat.
        """
        history = [
            Disposition.AMBIGUOUS_EMPTY.value,
            Disposition.RATE_LIMITED.value,
        ]
        assert attempt_tier_from_dispositions(history) == TIER_STABLE_NONANSWER

    def test_an_empty_history_is_never_probed(self):
        assert attempt_tier_from_dispositions([]) == TIER_NEVER_PROBED

    def test_an_unrecognised_disposition_defaults_to_urgent_not_stale(self):
        """Over-including into the urgent tier costs a probe; under-including costs
        the row. A value from a future protocol version must not silently sort to
        the back of the queue."""
        assert attempt_tier_from_dispositions(["some_future_disposition"]) == (
            TIER_TRANSIENT_ONLY
        )
        assert not is_stable_nonanswer("some_future_disposition")
        assert not is_stable_nonanswer(None)

    @pytest.mark.parametrize(
        "carrier", sorted(STABLE_NONANSWER_DISPOSITION_VALUES)
    )
    def test_every_stable_disposition_carries_the_demotion_not_just_one(self, carrier):
        """The tier is a property of the PARTITION, never of one string.

        ``ambiguous_empty`` is the disposition the 341 owed rows happen to carry, so
        a fix could special-case that one word, pass the regression test, and starve
        identically the first time the head refills with ``open_no_settlement``. Each
        member of the stable set is asserted separately so that shortcut cannot
        survive: demoting one word leaves the other three green here and red in
        production.
        """
        assert attempt_tier_from_dispositions([carrier]) == TIER_STABLE_NONANSWER
        assert is_stable_nonanswer(carrier)

    @pytest.mark.parametrize(
        "carrier", sorted(STABLE_NONANSWER_DISPOSITION_VALUES)
    )
    def test_a_binding_budget_prefers_the_unasked_row_whatever_the_carrier(
        self, carrier
    ):
        """G1 with the carrier varied — the selection, not the sort position.

        Both rows sit in the terminal bucket and the answered one is closer to its
        deadline, so under the pre-fix key it won every time. The budget binds at
        one, so this asserts who gets probed rather than who sorts where.
        """
        answered = candidate(
            1, 1.0, attempts=3,
            stable_nonanswers=3 if is_stable_nonanswer(carrier) else 0,
        )
        unasked = candidate(2, 6.0)
        selected, _ = plan_sweep([answered, unasked], budget=1, now=NOW)
        assert [c.market_id for c in selected] == [2]

    def test_tier_counts_names_every_tier_it_reports(self):
        cands = [
            candidate(1, 5.0),
            candidate(2, 5.0, attempts=1),
            candidate(3, 5.0, attempts=1, stable_nonanswers=1),
            candidate(4, 5.0, attempts=2, stable_nonanswers=2),
        ]
        assert tier_counts(cands) == {
            "never_probed": 1,
            "transient_only": 1,
            "stable_nonanswer": 2,
        }


class TestDispositionPartition:
    """The stable/transient split must be exhaustive and disjoint over the
    non-terminal set — the same guard ``TERMINAL | RETRYABLE`` already carries.

    Without this, a disposition added later defaults into a tier nobody chose.
    """

    def test_the_partition_covers_the_retryable_set_exactly(self):
        assert (
            TRANSIENT_DISPOSITION_VALUES | STABLE_NONANSWER_DISPOSITION_VALUES
        ) == RETRYABLE_DISPOSITIONS

    def test_the_partition_is_disjoint(self):
        assert not (TRANSIENT_DISPOSITION_VALUES & STABLE_NONANSWER_DISPOSITION_VALUES)

    def test_no_terminal_disposition_leaked_into_the_planning_partition(self):
        both = TRANSIENT_DISPOSITION_VALUES | STABLE_NONANSWER_DISPOSITION_VALUES
        assert not (both & TERMINAL_DISPOSITIONS)

    def test_the_livelock_disposition_is_stable_and_still_not_terminal(self):
        """Both halves matter. Stable is why it stops hogging the head of the queue;
        non-terminal is why it is still asked at all."""
        assert Disposition.AMBIGUOUS_EMPTY.value in STABLE_NONANSWER_DISPOSITION_VALUES
        assert Disposition.AMBIGUOUS_EMPTY.value not in TERMINAL_DISPOSITIONS

    def test_rate_limiting_is_transient_not_stable(self):
        """#2174's population must stay in the tier that gets retried first."""
        assert Disposition.RATE_LIMITED.value in TRANSIENT_DISPOSITION_VALUES
        assert Disposition.TRANSPORT_ERROR.value in TRANSIENT_DISPOSITION_VALUES
