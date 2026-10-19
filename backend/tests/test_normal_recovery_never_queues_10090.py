"""#10090 attempt151 — publication recovery never queues behind a stamp for a slot.

Authority's review of be6d5958e1: only the first of recovery's three slot
acquisitions checked `locked()`. Discovery and the final settle could still
wait as first-in-line waiters ahead of a later stamp (up to 0.25 s each). Each
acquisition now checks with no await between the check and the acquisition,
and passes when all three slots are taken; the next opportunity retries.
"""

import asyncio
from collections import namedtuple
from contextlib import asynccontextmanager

import pytest

from app.tasks.live_blend_refresh import FRESH_STAMP_WORKERS, LiveBlendRefresher
from tests.test_live_blend_refresh import _Result

pytestmark = pytest.mark.asyncio

Row = namedtuple("Row", "id event_id reading")


class Slots(asyncio.Semaphore):
    """The refresher's three slots, recording each task that waited in line."""

    def __init__(self, value):
        super().__init__(value)
        self.queued = []

    async def acquire(self):
        if self.locked():
            self.queued.append(asyncio.current_task())
        return await super().acquire()


def refresher(execute):
    r = LiveBlendRefresher("polymarket")
    r._session_slots = Slots(FRESH_STAMP_WORKERS)
    statements = []

    class Session:
        async def execute(self, statement, params=None):
            statements.append(" ".join(str(statement).split()[:3]))
            return await execute(statement)

    @asynccontextmanager
    async def factory():
        yield Session()

    r._session_factory = factory
    return r, statements


async def release_all(r, held):
    for _ in range(held):
        r._session_slots.release()


async def test_discovery_passes_when_stamps_took_every_slot_during_settlement():
    taken = []

    async def execute(statement):
        if str(statement).startswith("DELETE") and not taken:
            # Two stamps take the free slots; a third queues for this one.
            for _ in range(FRESH_STAMP_WORKERS - 1):
                await r._session_slots.acquire()
                taken.append(True)
            taken.append(asyncio.create_task(r._session_slots.acquire()))
            await asyncio.sleep(0)
        return _Result()

    r, statements = refresher(execute)
    r._normal_acked = {1: 5}
    try:
        await asyncio.wait_for(r._recover_normal_prices(), 1)
        assert statements == ["DELETE FROM owed_chart_points"]
        assert asyncio.current_task() not in r._session_slots.queued, (
            "discovery waited in line for a slot behind the stamps"
        )
    finally:
        if taken and isinstance(taken[-1], asyncio.Task):
            await asyncio.wait_for(taken[-1], 1)
        await release_all(r, len(taken))


async def test_final_settle_keeps_the_ack_instead_of_queueing_for_a_slot():
    async def execute(statement):
        text = str(statement)
        if text.startswith("SELECT id FROM"):
            return _Result(scalar=10)
        if text.startswith("SELECT id, event_id"):
            return _Result(rows=[Row(3, 1, {"rev": 7, "updated_at": "2026-10-19T17:00:00Z"})])
        return _Result()

    r, statements = refresher(execute)
    held = 0

    async def publish(frames):
        nonlocal held
        assert [f["event_id"] for f in frames] == [1]
        # Stamps take every slot while the control's ACK is outstanding.
        for _ in range(FRESH_STAMP_WORKERS):
            await r._session_slots.acquire()
            held += 1
        return {(1, 7)}

    r._publish = publish
    try:
        await asyncio.wait_for(r._recover_normal_prices(), 1)
        assert not any(s.startswith("DELETE") for s in statements)
        assert asyncio.current_task() not in r._session_slots.queued, (
            "the final settle waited in line for a slot behind the stamps"
        )
        # The next opportunity settles it.
        assert r._normal_acked == {1: 7}
    finally:
        await release_all(r, held)
