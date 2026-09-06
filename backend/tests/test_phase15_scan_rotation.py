"""Phase 1.5 must eventually revalidate every linked market — #2325.

The wrong-game bind that motivated this file: Kalshi's
``KXNCAAFGAME-26AUG29MORGNCAT`` ("Morgan St. vs North Carolina A&T") carried
``event_id = 416565``, which is *North Carolina Tar Heels vs TCU Horned Frogs*.
A user on the UNC-TCU card was shown a Kalshi price for a different game, and
that price was eligible for the blend.

Phase 1.5 runs exactly the gate that should have torn the bind down, and it
never did. Not because the gate is wrong — measured on production, all four
team comparisons return ``False``, so the gate would unlink on sight — but
because **the scan never reached the row**. The scan read the 1,000
most-recently-updated eligible markets; the row ranked 4,796th of 8,207.

And it could never climb. A settled Kalshi market keeps ``status='open'`` in
our DB (gotcha #33), so it stays eligible forever, but polling stops touching
it, so its ``updated_at`` freezes and it sinks. Newest-first ordering
therefore starves precisely the population Phase 1.5 exists to check — links
on finished games. Measured the same day: 4,440 eligible rows untouched for
over 2 days, the oldest since 2026-07-02.

Every number quoted below was measured on production on 2026-08-30 via
``/api/admin/db-query``; they are fixed inputs to the arithmetic, not live
reads, so these tests never touch the network or the clock (gotcha #44).

Imports are deliberately *inside* each test. That keeps the source-shape guard
below runnable against unfixed code, where it fails by assertion — a result —
instead of by collection-time ImportError, which is only a story about the
harness (gotcha #124).
"""

import inspect
import re
from datetime import datetime, timedelta, timezone

import pytest

# --- The production measurement this file is built on ----------------------
# /api/admin/db-query, 2026-08-30, over
#   source IN ('kalshi','polymarket') AND event_id IS NOT NULL AND status='open'
ELIGIBLE_TOTAL = 8207          # total rows Phase 1.5 may revalidate
ELIGIBLE_FINISHED = 5904       # of those, on completed/closed events
OLD_SCAN_CAP = 1000            # what the scan read before this fix
MORGNCAT_RANK_IN_GROUP0 = 4796  # where the #2325 row sat in that ordering

BEAT = 900  # match_prediction_markets cadence, seconds
# A fixed anchor. Offset first, then use it — never branch on the clock.
ANCHOR = datetime(2026, 8, 30, 12, 0, 0, tzinfo=timezone.utc)


class TestWhyTheRowWasNeverReached:
    """Pins the defect itself, so a future re-cap cannot resurrect it."""

    def test_eligible_population_dwarfs_the_old_cap(self):
        assert ELIGIBLE_TOTAL > OLD_SCAN_CAP * 8

    def test_finished_group_alone_overflows_the_old_cap(self):
        # The priority ordering put finished events first, but there were ~6x
        # more of them than the cap, so the lower-priority groups were never
        # reached at all and most of group 0 wasn't either.
        assert ELIGIBLE_FINISHED > OLD_SCAN_CAP * 5

    def test_the_2325_row_sat_far_below_the_old_cap(self):
        assert MORGNCAT_RANK_IN_GROUP0 > OLD_SCAN_CAP
        # Not marginally below — 4.8x below. No time budget is needed to
        # explain the miss; the SQL cap alone guarantees it.
        assert MORGNCAT_RANK_IN_GROUP0 / OLD_SCAN_CAP > 4


class TestShardPlan:
    def test_small_population_keeps_a_single_shard(self):
        from app.tasks.prediction_market_matching import _phase15_shard_plan

        shards, index = _phase15_shard_plan(500, ANCHOR, limit=750)
        assert (shards, index) == (1, 0)

    def test_population_at_the_limit_keeps_a_single_shard(self):
        from app.tasks.prediction_market_matching import _phase15_shard_plan

        shards, _ = _phase15_shard_plan(750, ANCHOR, limit=750)
        assert shards == 1

    def test_one_over_the_limit_splits(self):
        from app.tasks.prediction_market_matching import _phase15_shard_plan

        shards, _ = _phase15_shard_plan(751, ANCHOR, limit=750)
        assert shards == 2

    def test_production_population_shard_count(self):
        from app.tasks.prediction_market_matching import _phase15_shard_plan

        shards, _ = _phase15_shard_plan(ELIGIBLE_TOTAL, ANCHOR, limit=750)
        assert shards == 11  # ceil(8207 / 750)

    def test_a_shard_always_fits_its_slice(self):
        from app.tasks.prediction_market_matching import _phase15_shard_plan

        for total in (0, 1, 749, 750, 751, 8207, 40_000):
            shards, _ = _phase15_shard_plan(total, ANCHOR, limit=750)
            largest = -(-total // shards) if shards else 0
            assert largest <= 750, (total, shards, largest)

    def test_empty_and_negative_populations_are_safe(self):
        from app.tasks.prediction_market_matching import _phase15_shard_plan

        assert _phase15_shard_plan(0, ANCHOR, limit=750) == (1, 0)
        assert _phase15_shard_plan(-5, ANCHOR, limit=750) == (1, 0)

    def test_a_nonpositive_slice_is_refused(self):
        from app.tasks.prediction_market_matching import _phase15_shard_plan

        with pytest.raises(ValueError):
            _phase15_shard_plan(100, ANCHOR, limit=0)

    def test_index_is_derived_from_the_passed_clock_not_a_live_read(self):
        from app.tasks.prediction_market_matching import _phase15_shard_plan

        # Same `now` must always give the same shard — the task is retried and
        # replayed, and a live clock read would make it nondeterministic.
        first = _phase15_shard_plan(ELIGIBLE_TOTAL, ANCHOR, limit=750)
        second = _phase15_shard_plan(ELIGIBLE_TOTAL, ANCHOR, limit=750)
        assert first == second

    def test_consecutive_beats_advance_the_shard(self):
        from app.tasks.prediction_market_matching import _phase15_shard_plan

        shards, first = _phase15_shard_plan(ELIGIBLE_TOTAL, ANCHOR, limit=750)
        _, second = _phase15_shard_plan(
            ELIGIBLE_TOTAL, ANCHOR + timedelta(seconds=BEAT), limit=750
        )
        assert second == (first + 1) % shards


class TestEveryRowIsReached:
    """The property the fix exists to buy."""

    def test_one_full_rotation_covers_every_eligible_id(self):
        from app.tasks.prediction_market_matching import _phase15_shard_plan

        shards, _ = _phase15_shard_plan(ELIGIBLE_TOTAL, ANCHOR, limit=750)
        ids = set(range(ELIGIBLE_TOTAL))
        reached: set[int] = set()
        for beat in range(shards):
            at = ANCHOR + timedelta(seconds=BEAT * beat)
            s, index = _phase15_shard_plan(ELIGIBLE_TOTAL, at, limit=750)
            assert s == shards, "shard count must be stable across a rotation"
            reached |= {i for i in ids if i % s == index}
        assert reached == ids

    def test_shards_are_disjoint_so_no_row_is_checked_twice_per_rotation(self):
        from app.tasks.prediction_market_matching import _phase15_shard_plan

        shards, _ = _phase15_shard_plan(ELIGIBLE_TOTAL, ANCHOR, limit=750)
        seen: set[int] = set()
        for index in range(shards):
            shard = {i for i in range(ELIGIBLE_TOTAL) if i % shards == index}
            assert not (shard & seen)
            seen |= shard

    def test_the_2325_row_is_reached_within_one_rotation(self):
        from app.tasks.prediction_market_matching import _phase15_shard_plan

        # Rank is irrelevant under rotation — membership is by id modulus, so
        # the row is reached on exactly one beat regardless of how stale it is.
        shards, _ = _phase15_shard_plan(ELIGIBLE_TOTAL, ANCHOR, limit=750)
        beats_that_reach_it = [
            beat
            for beat in range(shards)
            if MORGNCAT_RANK_IN_GROUP0
            % shards
            == _phase15_shard_plan(
                ELIGIBLE_TOTAL, ANCHOR + timedelta(seconds=BEAT * beat), limit=750
            )[1]
        ]
        assert len(beats_that_reach_it) == 1

    def test_full_rotation_completes_within_three_hours(self):
        from app.tasks.prediction_market_matching import _phase15_shard_plan

        shards, _ = _phase15_shard_plan(ELIGIBLE_TOTAL, ANCHOR, limit=750)
        assert shards * BEAT <= 3 * 3600


class TestScanQueryShapes:
    def test_rotation_orders_least_recently_updated_first(self):
        from app.tasks.prediction_market_matching import _phase15_rotation_query

        sql = str(_phase15_rotation_query(11, 3).compile())
        assert "futures_markets.updated_at ASC" in sql
        assert "futures_markets.updated_at DESC" not in sql

    def test_rotation_filters_to_its_shard(self):
        from app.tasks.prediction_market_matching import _phase15_rotation_query

        sql = str(_phase15_rotation_query(11, 3).compile())
        assert "futures_markets.id %" in sql

    def test_a_single_shard_adds_no_modulus_filter(self):
        from app.tasks.prediction_market_matching import _phase15_rotation_query

        sql = str(_phase15_rotation_query(1, 0).compile())
        assert "futures_markets.id %" not in sql

    def test_fresh_slice_still_reads_newest_first(self):
        from app.tasks.prediction_market_matching import _phase15_fresh_query

        # The rotation must not cost us the fast catch on brand-new mislinks.
        sql = str(_phase15_fresh_query().compile())
        assert "futures_markets.updated_at DESC" in sql

    def test_the_two_slices_fit_the_original_per_beat_cap(self):
        from app.tasks.prediction_market_matching import (
            _PHASE15_FRESH_SLICE,
            _PHASE15_ROTATION_SLICE,
            _PHASE15_SCAN_LIMIT,
        )

        # Rotation must not silently double the per-beat cost.
        assert _PHASE15_FRESH_SLICE + _PHASE15_ROTATION_SLICE == _PHASE15_SCAN_LIMIT
        assert _PHASE15_SCAN_LIMIT == OLD_SCAN_CAP

    def test_count_and_scans_share_one_population_definition(self):
        from app.tasks.prediction_market_matching import (
            _phase15_eligible_count_query,
            _phase15_fresh_query,
            _phase15_rotation_query,
        )

        # If the count ran over a different population than the scans, the
        # shard sizing would be wrong and the tail would starve again.
        def where_of(q):
            clause = str(q.compile()).split("WHERE", 1)[1].split("ORDER BY")[0]
            # Bind-parameter names are auto-numbered per compilation, so
            # :status_1 and :status_2 are the same predicate. Compare the
            # population, not the numbering.
            return re.sub(r"(:[a-z_]+?)_\d+", r"\1", clause).strip()

        count_where = where_of(_phase15_eligible_count_query())
        fresh_where = where_of(_phase15_fresh_query())
        assert count_where == fresh_where
        # The rotation adds only the shard predicate on top of that population.
        rotation_where = where_of(_phase15_rotation_query(11, 3))
        assert rotation_where.startswith(count_where)


class TestPhaseWiring:
    def test_phase_uses_both_slices(self):
        from app.tasks.prediction_market_matching import _phase15_revalidate

        src = inspect.getsource(_phase15_revalidate)
        assert "_phase15_fresh_query" in src
        assert "_phase15_rotation_query" in src

    def test_phase_no_longer_spends_its_whole_cap_newest_first(self):
        """RED-FIRST. Fails by assertion on unfixed code, not by ImportError.

        On the code that shipped the #2325 bind, ``_phase15_revalidate``
        contained a single ``.limit(1000)`` scan ordered ``updated_at.desc()``.
        That inline scan is the defect; it must be gone.
        """
        from app.tasks.prediction_market_matching import _phase15_revalidate

        src = inspect.getsource(_phase15_revalidate)
        assert "updated_at.desc()" not in src
        assert ".limit(1000)" not in src

    def test_phase_reports_what_it_left_for_later(self):
        from app.tasks.prediction_market_matching import _phase15_revalidate

        # No silent caps: the shard plan is observable in the funnel stats.
        src = inspect.getsource(_phase15_revalidate)
        assert "phase15_shards" in src
        assert "phase15_shard_index" in src
        assert "phase15_eligible_total" in src

    def test_dedup_keeps_an_overlapping_row_from_being_checked_twice(self):
        from app.tasks.prediction_market_matching import _phase15_revalidate

        src = inspect.getsource(_phase15_revalidate)
        assert "_seen_market_ids" in src
