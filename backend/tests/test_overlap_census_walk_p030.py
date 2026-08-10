"""CAL-P030 — the adaptive walk policy that lets the overlap census reach the end.

The rail is bounded per window and hands back a ``next_offset``; nothing shipped
with it walked that cursor. The first real walk (2026-08-10) found a fixed row
budget cannot work — 5,000 rows returned in 2.3 s at the head of the id space
and timed out repeatedly in the middle, where density is two orders of magnitude
higher.

The rule these tests exist to protect is the one that is cheap to get wrong:
**a hot window is retried smaller, never skipped.** Skipping would produce a
walk that completes, reports ``exhausted``, and silently omits the dense regions
holding most of the population — an N biased in an invisible direction. That is
the failure this whole census was written to avoid, so it must fail loudly here.
"""

from __future__ import annotations

import pytest

from app.tasks.census_overlap_trading import (
    WALK_FAST_S,
    WALK_SCAN_MAX,
    WALK_SCAN_MIN,
    WALK_SCAN_START,
    WALK_SLOW_S,
    is_complete_walk,
    next_scan,
)


class TestTimeoutShrinks:
    def test_a_hot_window_halves_the_budget(self):
        assert next_scan(5_000, seconds=20.4, timed_out=True) == 2_500

    def test_shrinking_stops_at_the_floor_rather_than_reaching_zero(self):
        """A budget that decays without limit makes no progress while looking busy."""
        scan = WALK_SCAN_MIN
        for _ in range(10):
            scan = next_scan(scan, seconds=20.0, timed_out=True)
        assert scan == WALK_SCAN_MIN

    def test_the_floor_is_never_breached_from_just_above_it(self):
        assert next_scan(WALK_SCAN_MIN + 1, seconds=20.0, timed_out=True) == WALK_SCAN_MIN

    def test_a_timeout_shrinks_even_when_it_returned_quickly(self):
        """``timed_out`` outranks the clock.

        A transport error or an HTTP 500 can come back fast; treating that as a
        FAST window would grow the budget straight back into the wall.
        """
        assert next_scan(5_000, seconds=0.2, timed_out=True) == 2_500


class TestHealthyWindowsSteer:
    def test_a_fast_window_grows_the_budget(self):
        assert next_scan(4_000, seconds=WALK_FAST_S - 0.5, timed_out=False) == 6_000

    def test_growth_is_capped(self):
        assert next_scan(WALK_SCAN_MAX, seconds=0.1, timed_out=False) == WALK_SCAN_MAX

    def test_a_slow_window_shrinks_before_it_ever_times_out(self):
        """Steering happens below the rail's 20 s window timeout, not after it."""
        got = next_scan(10_000, seconds=WALK_SLOW_S + 1, timed_out=False)
        assert got == 6_000
        assert got < 10_000

    def test_a_comfortable_window_is_left_alone(self):
        mid = (WALK_FAST_S + WALK_SLOW_S) / 2
        assert next_scan(7_777, seconds=mid, timed_out=False) == 7_777

    @pytest.mark.parametrize("seconds", [WALK_FAST_S, WALK_SLOW_S])
    def test_the_band_edges_are_inclusive_of_no_change(self, seconds):
        """Exactly-at-threshold is the steady band; only strictly past it steers."""
        assert next_scan(5_000, seconds=seconds, timed_out=False) == 5_000

    def test_the_start_budget_is_inside_its_own_bounds(self):
        assert WALK_SCAN_MIN <= WALK_SCAN_START <= WALK_SCAN_MAX


class TestPartialWalksAreNeverPublishable:
    """``is_complete_walk`` is what stops a prefix being reported as a population."""

    def test_an_unexhausted_tail_is_incomplete(self):
        assert is_complete_walk([{"exhausted": True}, {"exhausted": False}]) is False

    def test_only_the_LAST_window_decides(self):
        """An earlier short window is normal; it does not certify the walk.

        ``exhausted`` means ``walked < scan``, which also happens whenever a hot
        window is retried smaller. Reading it anywhere but the tail would certify
        almost every real walk as complete.
        """
        assert is_complete_walk([{"exhausted": True}, {"exhausted": True}]) is True
        assert is_complete_walk([{"exhausted": False}, {"exhausted": True}]) is True

    def test_no_windows_is_not_a_complete_walk(self):
        assert is_complete_walk([]) is False
