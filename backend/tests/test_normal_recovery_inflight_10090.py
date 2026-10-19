"""#10090 attempt151 — recovery leaves a revision this process still owns to its
own publication, and no hold outlives the publication it waits for.

Authority's review of 0f6389ce65: recovery starts at the end of every
publication and swaps the acknowledged revisions before the next waiting group
of frames is acknowledged. Discovery then read that group's committed intents
(in flight, or acknowledged after the swap) and published a price-free control
for each, costing every open reader of a busy game a paired read. A revision is
now held from before COMMIT until its publication resolves; discovery skips
`rev <= max(held, acknowledged)` per event. A hold that leaked would hide a
quiet game's final from discovery for the process's life, so every path that
ends a publication releases, and an early release costs at most one control.
"""

import asyncio
from collections import namedtuple
from contextlib import asynccontextmanager

import pytest

from app.tasks.live_blend_refresh import LiveBlendRefresher
from tests.test_live_blend_refresh import _Result

pytestmark = pytest.mark.asyncio

Row = namedtuple("Row", "id event_id reading")


def frame(eid, rev):
    return {"event_id": eid, "p": .5, "rev": {str(eid): rev}, "source_value": .5}


def refresher(rows, on_read=None):
    r = LiveBlendRefresher("polymarket")
    published = []

    class Session:
        async def execute(self, statement, params=None):
            text = str(statement)
            if on_read is not None and text.startswith("SELECT"):
                on_read()
            if text.startswith("SELECT id FROM"):
                return _Result(scalar=max(row.id for row in rows))
            if text.startswith("SELECT id, event_id"):
                return _Result(rows=rows)
            return _Result()

    @asynccontextmanager
    async def factory():
        yield Session()

    async def publish(frames):
        published.append(frames)
        return {(f["event_id"], f["rev"][str(f["event_id"])]) for f in frames}

    r._session_factory = factory
    r._publish = publish
    return r, published


def reading(rev):
    return {"rev": rev, "updated_at": "2026-10-19T18:00:00Z"}


async def test_discovery_skips_owned_revisions_and_republishes_the_rest():
    rows = [
        Row(1, 1, reading(4)),  # A: failed, not held — owed a control
        Row(2, 2, reading(9)),  # B: committed, its publication in flight
        Row(3, 3, reading(6)),  # C: acknowledged after the swap
        Row(4, 4, reading(8)),  # D: held at an older revision than its row
    ]
    # C's publication resolves while discovery reads, after the swap at the
    # top of the run: its hold moves to the fresh `_normal_acked`.
    r, published = refresher(rows, on_read=lambda: (
        r._normal_acked.__setitem__(3, 6), r._normal_inflight.discard((3, 6)),
    ))
    r._normal_inflight = {(2, 9), (3, 6), (4, 7)}
    await asyncio.wait_for(r._recover_normal_prices(), 1)
    assert [[(f["event_id"], f["reconcile"]["custody_id"]) for f in fs] for fs in published] == [
        [(1, "normal-price:1:4"), (4, "normal-price:4:8")]
    ]
    assert r._normal_after == 0 and r._normal_horizon is None, "the sweep still completed"


async def test_a_failed_publication_releases_its_hold_for_the_next_discovery():
    r, published = refresher([Row(1, 2, reading(9))])
    r._normal_retry_at = float("inf")  # no opportunity until this test asks
    acknowledge = r._publish

    async def refuse(frames):
        raise ConnectionError("redis went away")

    r._publish = refuse
    r._normal_inflight.add((2, 9))
    assert await r._publish_prices([frame(2, 9)]) == set()
    assert not r._normal_inflight

    r._publish = acknowledge
    await asyncio.wait_for(r._recover_normal_prices(), 1)
    assert [f["event_id"] for fs in published for f in fs] == [2]


async def test_an_acknowledged_publication_moves_its_hold_to_acknowledged():
    r, _ = refresher([Row(1, 2, reading(9))])
    r._normal_retry_at = float("inf")
    r._normal_inflight.add((2, 9))
    assert await r._publish_prices([frame(2, 9)]) == {(2, 9)}
    assert not r._normal_inflight and r._normal_acked == {2: 9}


async def test_a_publication_task_cancelled_before_its_first_step_releases():
    r, published = refresher([])
    r._normal_retry_at = float("inf")
    r._normal_inflight.add((2, 9))
    task = r._publish_prices_task([frame(2, 9)])
    task.cancel()  # before the coroutine ever runs: its own release cannot
    with pytest.raises(asyncio.CancelledError):
        await task
    assert not published, "premise: the coroutine never ran"
    assert not r._normal_inflight


async def test_a_failed_stamp_transaction_releases_what_it_held():
    r, _ = refresher([])
    with pytest.raises(RuntimeError):
        async with r._normal_holds() as held:
            held |= {(2, 9)}
            r._normal_inflight |= held
            raise RuntimeError("before outer COMMIT")
    assert not r._normal_inflight


async def test_a_committed_stamp_transaction_keeps_its_hold_for_the_publication():
    r, _ = refresher([])
    async with r._normal_holds() as held:
        held |= {(2, 9)}
        r._normal_inflight |= held
    assert r._normal_inflight == {(2, 9)}
