"""Card recycling for exhausted feeds (Queue #48 / SEQUENCE 000a2).

Heavy users hit a hard "all caught up" wall once they've impressioned the fresh
candidate pool. `_futures_recycle_eligible` decides whether a previously-seen
futures market may be re-shown (penalized below fresh) instead of walling.
"""

from datetime import datetime, timezone, timedelta
from types import SimpleNamespace

from app.routes.feed import (
    _futures_recycle_eligible,
    FEED_RECYCLE_AFTER_HOURS,
    FEED_RECYCLE_MATERIALITY,
)
from app.utils.personalization import PersonalizationContext


NOW = datetime(2026, 6, 15, 12, 0, 0, tzinfo=timezone.utc)


def _outcome(prob=None, change=None):
    return SimpleNamespace(current_probability=prob, probability_change_24h=change)


def _market(mid=1, outcomes=None):
    return SimpleNamespace(id=mid, outcomes=outcomes or [])


def _ctx(seen_at=None, mid=1):
    ctx = PersonalizationContext()
    ctx.recent_seen_futures_ids.add(mid)
    if seen_at is not None:
        ctx.recent_seen_futures_at[mid] = seen_at
    return ctx


class TestFuturesRecycleEligible:
    def test_stale_and_contested_is_eligible(self):
        # Seen 24h ago (> FEED_RECYCLE_AFTER_HOURS) and has a contested outcome.
        m = _market(outcomes=[_outcome(prob=0.55), _outcome(prob=0.45)])
        ctx = _ctx(seen_at=NOW - timedelta(hours=24))
        assert _futures_recycle_eligible(m, ctx, NOW) is True

    def test_stale_and_material_move_is_eligible(self):
        # Settled-looking probs but a big 24h move → still worth re-showing.
        big = FEED_RECYCLE_MATERIALITY + 0.05
        m = _market(outcomes=[_outcome(prob=0.97, change=big), _outcome(prob=0.03)])
        ctx = _ctx(seen_at=NOW - timedelta(hours=24))
        assert _futures_recycle_eligible(m, ctx, NOW) is True

    def test_seen_too_recently_not_eligible(self):
        # Seen only 2h ago → still within the no-repeat window.
        m = _market(outcomes=[_outcome(prob=0.55), _outcome(prob=0.45)])
        ctx = _ctx(seen_at=NOW - timedelta(hours=2))
        assert _futures_recycle_eligible(m, ctx, NOW) is False

    def test_stale_but_settled_and_static_not_eligible(self):
        # Old, no contested outcome, no material move → nothing to re-show.
        m = _market(outcomes=[_outcome(prob=0.99, change=0.001), _outcome(prob=0.01)])
        ctx = _ctx(seen_at=NOW - timedelta(hours=48))
        assert _futures_recycle_eligible(m, ctx, NOW) is False

    def test_missing_timestamp_skips_age_guard(self):
        # user_seen_markets supplement has no timestamp; eligibility falls back
        # to relevance only (contested here).
        m = _market(outcomes=[_outcome(prob=0.5), _outcome(prob=0.5)])
        ctx = _ctx(seen_at=None)
        assert _futures_recycle_eligible(m, ctx, NOW) is True

    def test_after_hours_threshold_is_tunable_constant(self):
        # The no-repeat window must be a real, positive constant (easy to tune).
        assert FEED_RECYCLE_AFTER_HOURS > 0
