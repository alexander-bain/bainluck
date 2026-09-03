"""live/035 item 2: a LIVE event's chart gains a point even when the price is flat.

`_create_or_update_win_prob_snapshot` appends only on a value CHANGE. That is
correct for a scheduled market — and it is why a live game with a settled price
draws one straight segment between two distant points instead of a line that
breathes. Alex's bar is at least one snapshot per minute per live event, so the
helper takes a cadence floor: unchanged + older than the floor is still a new
observation and gets its own row.

Both arms are asserted throughout. A heartbeat test that only proves "a row
appeared" would pass against a helper that had simply stopped deduping, which
would grow `win_prob_snapshots` ~60x — the exact cost the Q501 throttle exists
to avoid. So every case below has its control: same call, floor absent or not
yet breached, must still dedup.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

from app.models.models import WinProbSnapshot
from app.tasks.live_blend_refresh import (
    DEFAULT_SNAPSHOT_INTERVAL_S,
    DEFAULT_SNAPSHOT_MAX_GAP_S,
    heartbeat_deadline,
)
from app.tasks.snapshots import _create_or_update_win_prob_snapshot


def _session_returning(existing):
    sess = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none = MagicMock(return_value=existing)
    sess.execute = AsyncMock(return_value=result)
    return sess


def _existing(age_seconds: float, probability: float = 0.60) -> WinProbSnapshot:
    return WinProbSnapshot(
        event_id=1,
        source="kalshi",
        home_win_probability=probability,
        away_win_probability=round(1.0 - probability, 4),
        captured_at=datetime.now(timezone.utc) - timedelta(seconds=age_seconds),
        game_state={"market_name": "Vallejo vs Monfils"},
        reading_count=4,
    )


async def _write(existing, **kwargs):
    sess = _session_returning(existing)
    return await _create_or_update_win_prob_snapshot(
        sess,
        event_id=1,
        source="kalshi",
        home_win_probability=0.60,
        away_win_probability=0.40,
        game_state={"market_name": "Vallejo vs Monfils"},
        **kwargs,
    )


async def test_flat_price_past_the_floor_appends_a_point():
    snap, is_new = await _write(_existing(age_seconds=90), max_gap_seconds=60.0)

    assert is_new is True, "a live chart must keep gaining points on a flat market"
    assert float(snap.home_win_probability) == 0.60


async def test_flat_price_inside_the_floor_still_dedups():
    """The control. Without this the 'fix' is just 'stop deduplicating'."""
    existing = _existing(age_seconds=10)
    snap, is_new = await _write(existing, max_gap_seconds=60.0)

    assert is_new is False
    assert snap is existing
    assert snap.reading_count == 5


async def test_no_floor_passed_preserves_the_old_behaviour_exactly():
    """Every caller that does NOT own a live event must be unaffected."""
    existing = _existing(age_seconds=86_400)  # a day of silence
    snap, is_new = await _write(existing)

    assert is_new is False, "an absent floor must never append"
    assert snap is existing


async def test_completed_event_never_heartbeats():
    """#922's stale tail must not come back through the cadence floor.

    A completed event refreshes its terminal point in place. A heartbeat there
    would append post-final points on every re-process cycle, rebuilding exactly
    the tail #922 removed.
    """
    existing = _existing(age_seconds=3_600)
    snap, is_new = await _write(existing, max_gap_seconds=60.0, is_completed=True)

    assert is_new is False
    assert snap is existing


async def test_naive_captured_at_is_treated_as_utc_not_crashed_on():
    """Rows written before tz-awareness must not raise inside a live poll."""
    existing = _existing(age_seconds=600)
    existing.captured_at = existing.captured_at.replace(tzinfo=None)

    snap, is_new = await _write(existing, max_gap_seconds=60.0)

    assert is_new is True


async def test_value_change_still_appends_regardless_of_the_floor():
    existing = _existing(age_seconds=1, probability=0.42)
    sess = _session_returning(existing)

    snap, is_new = await _create_or_update_win_prob_snapshot(
        sess,
        event_id=1,
        source="kalshi",
        home_win_probability=0.60,
        away_win_probability=0.40,
        max_gap_seconds=60.0,
    )

    assert is_new is True
    assert float(snap.home_win_probability) == 0.60


# ---------------------------------------------------------------------------
# The deadline arithmetic — the part that decides whether the bar is actually met
# ---------------------------------------------------------------------------


def test_deadline_is_the_target_minus_the_sampling_period():
    """A deadline equal to the sampling period is observed one period LATE.

    This is the whole reason `heartbeat_deadline` exists rather than passing the
    target straight through. With a 25s sample and a 60s target, a naive
    deadline of 60 is first seen breached at t=75 — over the bar. 35 is seen at
    t=50 and again at t=75, so no gap exceeds 60.
    """
    deadline = heartbeat_deadline(60.0, 25.0)
    assert deadline == 35.0

    # Simulate the sampler: it only looks every `interval` seconds.
    interval, last_write, worst_gap = 25.0, 0.0, 0.0
    for tick in range(1, 40):
        t = tick * interval
        if t - last_write >= deadline:
            worst_gap = max(worst_gap, t - last_write)
            last_write = t
    assert worst_gap <= 60.0, f"worst observed gap {worst_gap}s exceeds the 60s bar"


def test_naive_deadline_would_miss_the_bar():
    """The control for the test above: prove the naive choice actually fails.

    Without this, `heartbeat_deadline` could return the target unchanged and the
    simulation above would still pass on some interval pairings.
    """
    interval, deadline, last_write, worst_gap = 25.0, 60.0, 0.0, 0.0
    for tick in range(1, 40):
        t = tick * interval
        if t - last_write >= deadline:
            worst_gap = max(worst_gap, t - last_write)
            last_write = t
    assert worst_gap > 60.0


def test_configured_defaults_meet_alexs_one_per_minute_bar():
    """The SHIPPED constants, not a hypothetical pair, clear 60 seconds.

    On a flat market the WS lane reaches `_maybe_snapshot` on the unchanged
    re-stamp beat, not the 5s blend beat, so the real sampling period is
    `UNCHANGED_RESTAMP_INTERVAL_S`. Simulated end to end against both throttles
    so a future tweak to either constant fails here rather than silently on a
    chart.
    """
    from app.tasks.live_blend_refresh import UNCHANGED_RESTAMP_INTERVAL_S

    deadline = heartbeat_deadline(
        DEFAULT_SNAPSHOT_MAX_GAP_S, DEFAULT_SNAPSHOT_INTERVAL_S
    )
    sample = max(DEFAULT_SNAPSHOT_INTERVAL_S, UNCHANGED_RESTAMP_INTERVAL_S)

    last_write, worst_gap = 0.0, 0.0
    for tick in range(1, 60):
        t = tick * sample
        if t - last_write >= deadline:
            worst_gap = max(worst_gap, t - last_write)
            last_write = t

    assert worst_gap <= 60.0, (
        f"a flat live market can go {worst_gap}s without a chart point — "
        "over Alex's one-per-minute bar"
    )


# ---------------------------------------------------------------------------
# The fast lane itself — the writer that has to honour the floor in production
# ---------------------------------------------------------------------------


def _refresher_session(existing):
    sess = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none = MagicMock(return_value=existing)
    sess.execute = AsyncMock(return_value=result)
    sess.add = MagicMock()
    return sess


def _reading():
    return MagicMock(
        market=MagicMock(name="m", id=7),
        outcome=MagicMock(id=9),
        yes_probability=0.60,
    )


async def test_ws_fast_lane_writes_a_point_on_a_silent_market():
    from app.tasks.live_blend_refresh import LiveBlendRefresher

    refresher = LiveBlendRefresher("kalshi")
    sess = _refresher_session(_existing(age_seconds=90))

    await refresher._maybe_snapshot(sess, 1, 0.60, _reading(), now=1_000.0)

    assert refresher.stats["snapshots_written"] == 1
    assert refresher.stats["snapshots_deduped"] == 0


async def test_ws_fast_lane_still_dedups_a_fresh_point():
    """Control: the floor must not turn the fast lane into a per-tick writer."""
    from app.tasks.live_blend_refresh import LiveBlendRefresher

    refresher = LiveBlendRefresher("kalshi")
    sess = _refresher_session(_existing(age_seconds=5))

    await refresher._maybe_snapshot(sess, 1, 0.60, _reading(), now=1_000.0)

    assert refresher.stats["snapshots_written"] == 0
    assert refresher.stats["snapshots_deduped"] == 1
