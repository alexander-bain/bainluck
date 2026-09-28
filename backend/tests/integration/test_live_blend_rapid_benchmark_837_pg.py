"""#837 — every real price on a liquid market reaches the number, not every fifth second's.

## the ship

Real changing probabilities arrive promptly and visibly follow the action. Alex's
required benchmark (Angelini v Johns, ATP Challenger Bari, 2026-09-28, Kalshi)
reads Johns 77 -> 80 -> 85 -> 84 about two seconds apart, then 73. The WS lane
flushes every 2s; with the blend's floor at 5s the 85 was written to
`futures_outcomes` and never stamped, framed or shown.

## what runs for real

The REAL `LiveBlendRefresher.refresh` at its DEFAULT floor, on disposable
Postgres, reading rows the socket's own UPDATE wrote (#8910's fixture: the
real poll primes Kalshi at 0.77). Only the refresher's monotonic clock is
driven, so each flush lands on the 2s grid, and the SSE publish is captured
instead of sent. The stored bag, the published frames and the refresher's
own stats are what is asserted.

The control arm runs the same schedule at the old 5s floor and must drop the
85 — the proof that this case can tell the two floors apart. It is a control on
the rig, not a statement about arbitrary loaded runtime: this names no latency
bound, and real delivery is still accepted on a release capture.

Runs where `SEARCH_TEST_DATABASE_URL` is set (CI `search-recall`).
"""

from __future__ import annotations

import pytest

import app.tasks.live_blend_refresh as blend_mod
from app.tasks.live_blend_refresh import LiveBlendRefresher
from tests.integration.test_live_writers_observation_order_8910_pg import (
    DB_URL,
    PRE_GOAL,
    _run_ws_refresh,
    _socket_flush,
    _stored,
    pg as _shared_pg_fixture,
)

pg = _shared_pg_fixture

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not DB_URL, reason="requires disposable SEARCH_TEST_DATABASE_URL"
    ),
]

#: flush time (s) -> the Kalshi home price the socket wrote just before it;
#: None = a flush with no new price for this event (the socket's quiet flush).
BENCHMARK = [
    (2.0, 0.80),
    (4.0, 0.85),
    (6.0, 0.84),
    (8.0, None),
    (10.0, None),
    (12.0, 0.73),
    (14.0, None),
]


async def _replay(Session, event_id, refresher, monkeypatch):
    clock = {"t": 0.0}
    monkeypatch.setattr(blend_mod, "_mono", lambda: 1000.0 + clock["t"])
    frames: list = []
    stamped_at: list = []
    for t, price in BENCHMARK:
        clock["t"] = t
        if price is not None:
            await _socket_flush(Session, price)
        before = len(frames)
        # A quiet flush hands the event in too (the shared helper always does).
        # Due with an unchanged price it stamps nothing, so this can only make
        # a dropped price harder to see, never invent one.
        refresher, _ = await _run_ws_refresh(
            Session, event_id, refresher=refresher, frames=frames,
        )
        if len(frames) > before:
            stamped_at.append(t)
    return refresher, frames, stamped_at


class TestTheBenchmarkReachesTheNumber:
    async def test_every_benchmark_price_is_stamped_and_framed_at_its_flush(
        self, pg, monkeypatch,
    ):
        Session, event_id = pg
        assert (await _stored(Session, event_id))["kalshi"]["value"] == PRE_GOAL

        refresher = LiveBlendRefresher("kalshi")  # the DEFAULT floor, on purpose
        refresher, frames, stamped_at = await _replay(
            Session, event_id, refresher, monkeypatch,
        )

        assert [f["source_value"] for f in frames] == pytest.approx(
            [0.80, 0.85, 0.84, 0.73]
        ), frames
        assert stamped_at == [2.0, 4.0, 6.0, 12.0], stamped_at
        assert all(f["source"] == "kalshi" and f["event_id"] == event_id
                   for f in frames), frames
        assert refresher.stats["throttled"] == 0, refresher.stats
        assert refresher.stats["stamped"] == 4, refresher.stats
        stored = await _stored(Session, event_id)
        assert stored["kalshi"]["value"] == pytest.approx(0.73), stored


class TestTheOldFloorControl:
    async def test_the_5s_floor_drops_the_85_on_the_same_schedule(
        self, pg, monkeypatch,
    ):
        """CONTROL: same rig, same rows, the pre-change floor. The 85 is
        stored by the socket and never reaches a stamp or a frame."""
        Session, event_id = pg
        refresher = LiveBlendRefresher("kalshi", min_refresh_interval_s=5.0)
        refresher, frames, stamped_at = await _replay(
            Session, event_id, refresher, monkeypatch,
        )

        values = [f["source_value"] for f in frames]
        assert values == pytest.approx([0.80, 0.84, 0.73]), frames
        assert 0.85 not in values
        assert stamped_at == [2.0, 8.0, 14.0], stamped_at
        assert refresher.stats["throttled"] >= 2, refresher.stats
