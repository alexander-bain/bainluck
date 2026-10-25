"""#10090 — a removal control is never malformed, and prices never wait for it.

THE SHIP, IN A READER'S WORDS: a live event page that opens or reconnects shows
the probabilities it can already show at once, even while the server is still
reading which source removals the page must cover; and a malformed removal
control is never treated as one.

WHAT IS PINNED (actual `_stream` route, the real hub `Subscription` mailbox and
the #837 in-process `Hub`; the coverage read is a controlled stand-in — its
real-PostgreSQL counterpart is
`integration/test_event_stream_reconcile_route_10090_pg.py`):

- attempt121 (`test_control_validation.py`, assertions verbatim):
  `_withdrawal_reconcile` refuses every malformed envelope (boolean ids or
  floors, a missing or extra floor row, an integer past 2**53, an empty or
  over-long custody id, a floor that disagrees with the frame's revision) and
  emits a valid one price-free, re-addressed to the page, with the underlying
  floor kept.
- attempt125 (`test_first_price.py`, assertions verbatim): a retained or live
  price reaches the page while the INITIAL coverage read is still blocked; that
  read is owned and joined on every exit (cancel, disconnect, terminal frame,
  failed read); a confirmation re-reads only its own origin row and emits that
  row's exact floor.

NOT DUPLICATED HERE. The attempt133 cases in
`test_event_stream_recovery_read_controls_10090.py` hold a LATER recovery read
(after the initial coverage); these hold the initial one. Its `until`/`data`
helpers are reused.

BOUNDED WAITS. The lab's unbounded `await entered.wait()` is bounded at 1 s and
every wait watches the stream task: a stream that ended first re-raises its own
error; one still running at the bound is cancelled and awaited.
"""

import asyncio
import json
from unittest.mock import AsyncMock

import pytest

from app.routes import event_stream as route
from app.utils import live_fanout
from tests.test_event_stream_recovery_read_controls_10090 import data, until
from tests.test_folded_event_stream_invalidation_837 import Hub, Request, frame


@pytest.fixture(autouse=True)
def reconcile_frames_reach_this_module():
    """These cases read `event: reconcile` frames off the real route.

    The legacy-listener view for older route tests (Live's
    `_event_stream_legacy_view`) drops those frames and answers coverage with
    a constant. It is installed per module or class; if anything ever installs
    it globally, this refuses before the case runs instead of letting it pass
    or fail on frames it never saw.
    """
    assert route._stream.__qualname__ == "_stream", route._stream
    # Absent on a route that predates reconcile (a bad-parent arm): the case
    # then fails on its own assertion, not here.
    coverage = getattr(route, "_current_reconcile", None)
    assert coverage is None or coverage.__qualname__ == "_current_reconcile", coverage


# --- attempt121 test_control_validation.py ---------------------------------


@pytest.mark.parametrize(
    "mutation",
    [
        "frame_bool",
        "control_bool",
        "floor_bool",
        "floor_missing",
        "extra_row",
        "over_safe_integer",
        "empty_id",
        "long_id",
        "mismatched_revision",
    ],
)
def test_invalid_control_never_creates_reconciliation(mutation):
    frame = {
        "event_id": 1,
        "rev": {"1": 4},
        "reconcile": {"event_id": 1, "custody_id": "owed:4", "removal_rev": {"1": 4}},
    }
    if mutation == "frame_bool":
        frame["event_id"] = True
    elif mutation == "control_bool":
        frame["reconcile"]["event_id"] = True
    elif mutation == "floor_bool":
        frame["reconcile"]["removal_rev"] = {"1": True}
    elif mutation == "floor_missing":
        frame["reconcile"]["removal_rev"] = {}
    elif mutation == "extra_row":
        frame["reconcile"]["removal_rev"]["2"] = 4
    elif mutation == "over_safe_integer":
        frame["reconcile"]["removal_rev"] = {"1": 2**53}
    elif mutation == "empty_id":
        frame["reconcile"]["custody_id"] = ""
    elif mutation == "long_id":
        frame["reconcile"]["custody_id"] = "x" * 97
    elif mutation == "mismatched_revision":
        frame["reconcile"]["removal_rev"] = {"1": 5}
    assert route._withdrawal_reconcile(frame, 1, 1) is None


def test_valid_control_is_price_free_and_keeps_underlying_floor():
    frame = {
        "event_id": 2,
        "rev": {"2": 4},
        "p": 0.5,
        "source": "kalshi",
        "reconcile": {
            "event_id": 2,
            "custody_id": "owed:4",
            "removal_rev": {"2": 4},
            "p": 0.9,
        },
    }
    assert route._withdrawal_reconcile(frame, 1, 2) == {
        "event_id": 1,
        "custody_id": "owed:4",
        "removal_rev": {"2": 4},
    }


# --- attempt125 test_first_price.py ----------------------------------------


def control(ids):
    return dict(
        event_id=1,
        custody_id="state:" + ",".join(map(str, ids)),
        removal_rev={str(i): i * 10 for i in ids},
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("retained", [True, False])
async def test_price_arrives_while_initial_coverage_still_blocked(
    monkeypatch, retained
):
    hub = Hub()
    entered = asyncio.Event()
    release = asyncio.Event()
    finished = asyncio.Event()
    chunks = []

    async def coverage(eid, ids):
        entered.set()
        try:
            await release.wait()
            return control(ids)
        finally:
            finished.set()

    monkeypatch.setattr(live_fanout, "fanout", lambda: hub)
    monkeypatch.setattr(route, "_current_reconcile", coverage)
    monkeypatch.setattr(
        route,
        "latest_frames",
        AsyncMock(return_value=[(1, json.dumps(frame(1)))] if retained else []),
    )
    monkeypatch.setattr(route, "FRAME_WAIT_S", 0.01)

    async def collect():
        async for c in route._stream(1, Request()):
            chunks.append(c)

    task = asyncio.create_task(collect())
    try:
        await until(entered.is_set, task, "initial read entered")
        if not retained:
            hub.subscriptions["live:event:1"].offer(json.dumps(frame(1)))
        await until(
            lambda: data(chunks, "probability"),
            task,
            "price while initial read blocked",
        )
        assert not release.is_set() and not data(chunks, "reconcile")
        release.set()
        await until(lambda: data(chunks, "reconcile"), task, "initial coverage")
        assert len(data(chunks, "probability")) == 1
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        assert finished.is_set() and hub.released == ["live:event:1"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "exit_kind", ["cancel", "disconnect", "terminal", "failed_read"]
)
async def test_initial_read_is_owned_and_joined_on_every_exit(monkeypatch, exit_kind):
    hub = Hub()
    entered = asyncio.Event()
    release = asyncio.Event()
    finished = asyncio.Event()
    chunks = []
    leaving = False

    class Reader:
        async def is_disconnected(self):
            return leaving

    async def coverage(eid, ids):
        entered.set()
        try:
            await release.wait()
            if exit_kind == "failed_read":
                raise ConnectionError("controlled")
            return control(ids)
        finally:
            finished.set()

    monkeypatch.setattr(live_fanout, "fanout", lambda: hub)
    monkeypatch.setattr(route, "_current_reconcile", coverage)
    monkeypatch.setattr(route, "latest_frames", AsyncMock(return_value=[]))
    monkeypatch.setattr(route, "FRAME_WAIT_S", 0.01)

    async def collect():
        async for c in route._stream(1, Reader()):
            chunks.append(c)

    task = asyncio.create_task(collect())
    try:
        await until(entered.is_set, task, "initial read entered")
        if exit_kind == "cancel":
            task.cancel()
        elif exit_kind == "disconnect":
            leaving = True
        elif exit_kind == "terminal":
            hub.subscriptions["live:event:1"].offer(
                json.dumps(frame(1, status="completed"))
            )
        else:
            release.set()
        await until(task.done, task, f"stream exit ({exit_kind})")
        assert finished.is_set() and not data(chunks, "reconcile")
        assert hub.released == ["live:event:1"] and route._open_connections == 0
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_confirmation_reads_only_its_origin_and_keeps_exact_floor(monkeypatch):
    hub = Hub()
    reads = []
    chunks = []

    async def coverage(eid, ids):
        reads.append(list(ids))
        return control(ids)

    monkeypatch.setattr(live_fanout, "fanout", lambda: hub)
    monkeypatch.setattr(route, "_current_reconcile", coverage)
    monkeypatch.setattr(route, "latest_frames", AsyncMock(return_value=[]))
    monkeypatch.setattr(route, "FRAME_WAIT_S", 0.01)

    async def collect():
        async for c in route._stream(1, Request(), [2, 3]):
            chunks.append(c)

    task = asyncio.create_task(collect())
    try:
        await until(lambda: data(chunks, "reconcile"), task, "initial coverage")
        for index, eid in enumerate([2, 3, 1], start=2):
            hub.subscriptions[f"live:event:{eid}"].offer(live_fanout.CONFIRMED)
            await until(
                lambda: len(data(chunks, "reconcile")) == index,
                task,
                f"confirmation coverage for {eid}",
            )
        await until(lambda: len(reads) == 4, task, "four coverage reads")
        assert reads == [[1, 2, 3], [2], [3], [1]]
        assert [x["removal_rev"] for x in data(chunks, "reconcile")] == [
            {"1": 10, "2": 20, "3": 30},
            {"2": 20},
            {"3": 30},
            {"1": 10},
        ]
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
