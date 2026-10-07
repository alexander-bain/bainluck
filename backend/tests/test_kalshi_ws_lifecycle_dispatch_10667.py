"""#10667 — settling one Kalshi game must not hold unrelated games' quotes, and
must not lose its closing forecast while it waits.

WHY THIS FILE EXISTS. The socket reader awaited every lifecycle callback
inline, so one game's settlement write (a session, three UPDATEs, a publish)
held every other game's ticks in the socket. The first prototype deferred the
whole callback and was REJECTED: the callback's first act is to read the
settling leg's closing price out of `price_buffer`, and deferring it let the
periodic flush drain that entry first — `calibration_probability` became NULL.

The shipped split captures the closing price on the receive path
(`prepare_lifecycle`) and defers only the slow write. These tests drive the
REAL service reader (`app.services.kalshi_ws`) and, for the closing forecast,
the REAL `prepare_lifecycle` / `handle_lifecycle` closures lifted out of
`app/tasks/kalshi_ws.py`; only the socket, the session and the flush are faked.
"""

import ast
import asyncio
import json
from pathlib import Path

import pytest
import websockets
from sqlalchemy import update

import app.services.kalshi_ws as service
import app.tasks.kalshi_ws as kalshi_task
from app.models.models import FuturesMarket, FuturesOutcome


def frame(kind, ticker, **extra):
    return json.dumps({"type": kind, "msg": {"market_ticker": ticker, **extra}})


class Feed:
    def __init__(self, frames, *, disconnect=False):
        self.frames = frames
        self.read = 0
        self.disconnect = disconnect
        self.exhausted = asyncio.Event()
        self.forever = asyncio.Event()

    async def send(self, value):
        pass

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self.read < len(self.frames):
            value = self.frames[self.read]
            self.read += 1
            return value
        self.exhausted.set()
        if self.disconnect:
            raise ConnectionError("test disconnect")
        await self.forever.wait()
        raise StopAsyncIteration


@pytest.fixture
def connect(monkeypatch):
    calls = []

    def install(feed):
        class Context:
            async def __aenter__(self):
                calls.append(feed)
                return feed

            async def __aexit__(self, *args):
                pass

        monkeypatch.setattr(websockets, "connect", lambda *a, **kw: Context())
        monkeypatch.setattr(service, "_load_rsa_key", lambda: object())
        monkeypatch.setattr(service, "_sign_ws_request", lambda *args: {})
        return calls

    return install


def opted_in(ws):
    """Opt the socket into deferral with a preparation that captures nothing."""

    async def prepare(msg):
        return ws.on_lifecycle

    ws.on_lifecycle_prepare = prepare
    return ws


async def stop(task):
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


async def test_unrelated_quote_passes_settlement_and_its_queued_sibling(connect):
    feed = Feed(
        [
            frame("ticker", "GAME-A", n=0),
            frame("market_lifecycle_v2", "GAME-A"),
            frame("ticker", "GAME-B", n=1),
            frame("trade", "GAME-A", n=2),
            frame("ticker", "OTHER-C", n=3),
        ]
    )
    connect(feed)
    ws = opted_in(service.KalshiWebSocket())
    held, release, other, same = (asyncio.Event() for _ in range(4))
    seen = []

    async def lifecycle(msg):
        held.set()
        await release.wait()
        seen.append("settled")

    def quote(msg):
        seen.append(msg["n"])
        if msg["n"] == 3:
            other.set()
        if msg["n"] == 2:
            same.set()

    ws.on_lifecycle = lifecycle
    ws.on_ticker = ws.on_trade = quote
    task = asyncio.create_task(ws.run(["GAME-A", "GAME-B", "OTHER-C"]))
    try:
        await asyncio.wait_for(held.wait(), 1)
        await asyncio.wait_for(other.wait(), 0.2)
        assert seen == [0, 3]
        release.set()
        await asyncio.wait_for(same.wait(), 1)
        assert seen == [0, 3, "settled", 1, 2]
    finally:
        await stop(task)
    assert not ws.is_connected


async def test_backlog_is_bounded_and_applies_backpressure(connect, monkeypatch):
    # More independent slow markets than the bound must stop socket consumption.
    monkeypatch.setattr(service, "MAX_PENDING_CALLBACKS", 4)
    feed = Feed([frame("market_lifecycle_v2", f"GAME{i}-A") for i in range(50)])
    connect(feed)
    ws = opted_in(service.KalshiWebSocket())
    entered, release = asyncio.Event(), asyncio.Event()
    started, cleaned = [], []

    async def lifecycle(msg):
        started.append(msg["market_ticker"])
        if len(started) == 4:
            entered.set()
        try:
            await release.wait()
        finally:
            cleaned.append(msg["market_ticker"])

    ws.on_lifecycle = lifecycle
    task = asyncio.create_task(ws.run(["GAME0-A"]))
    try:
        await asyncio.wait_for(entered.wait(), 0.2)
        for _ in range(5):
            await asyncio.sleep(0)
        assert len(started) == 4
        assert feed.read <= 5  # at most one already-read frame waits for capacity
    finally:
        await stop(task)
    assert sorted(cleaned) == sorted(started)


async def test_callback_failure_is_reported_and_healthy_quotes_survive(connect, caplog):
    feed = Feed([frame("market_lifecycle_v2", "GAME-A"), frame("ticker", "GAME-B")])
    connect(feed)
    ws = opted_in(service.KalshiWebSocket())
    delivered = asyncio.Event()

    async def lifecycle(msg):
        raise ValueError("test failure")

    ws.on_lifecycle = lifecycle
    ws.on_ticker = lambda msg: delivered.set()
    task = asyncio.create_task(ws.run(["GAME-A"]))
    try:
        await asyncio.wait_for(delivered.wait(), 1)
        assert "Lifecycle handler error" in caplog.text
    finally:
        await stop(task)


@pytest.mark.parametrize("cancel_during_drain", [False, True])
async def test_disconnect_drains_before_reconnect_and_cancellation_joins_callbacks(
    connect, cancel_during_drain
):
    feed = Feed(
        [frame("market_lifecycle_v2", "GAME-A"), frame("ticker", "GAME-B")],
        disconnect=True,
    )
    calls = connect(feed)
    ws = opted_in(service.KalshiWebSocket())
    held, release, finished, quoted = (asyncio.Event() for _ in range(4))

    async def lifecycle(msg):
        held.set()
        try:
            await release.wait()
        finally:
            finished.set()

    ws.on_lifecycle = lifecycle
    ws.on_ticker = lambda msg: quoted.set()
    task = asyncio.create_task(ws.run(["GAME-A"]))
    try:
        await asyncio.wait_for(held.wait(), 1)
        await asyncio.wait_for(feed.exhausted.wait(), 0.2)
        assert len(calls) == 1
        assert not quoted.is_set()
        if not cancel_during_drain:
            release.set()
            await asyncio.wait_for(quoted.wait(), 1)
            assert finished.is_set()
    finally:
        await stop(task)
    assert finished.is_set()
    if cancel_during_drain:
        assert not quoted.is_set()


async def test_recycle_timeout_still_raises_and_joins_pending_settlement(connect):
    # Q460: the consumer bounds `run()` with `wait_for`; the recycle must still
    # surface as TimeoutError, and a deferred settlement must not outlive it.
    feed = Feed([frame("market_lifecycle_v2", "GAME-A")])
    connect(feed)
    ws = opted_in(service.KalshiWebSocket())
    held, finished = asyncio.Event(), asyncio.Event()

    async def lifecycle(msg):
        held.set()
        try:
            await asyncio.Event().wait()
        finally:
            finished.set()

    ws.on_lifecycle = lifecycle
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(ws.run(["GAME-A"]), 0.2)
    assert held.is_set() and finished.is_set()
    assert not ws.is_connected


async def test_unknown_identity_is_a_global_barrier(connect):
    feed = Feed(
        [
            frame("market_lifecycle_v2", "GAME-A"),
            frame("ticker", ""),
            frame("ticker", "OTHER-B"),
        ]
    )
    connect(feed)
    ws = opted_in(service.KalshiWebSocket())
    held, release, done = (asyncio.Event() for _ in range(3))
    seen = []

    async def lifecycle(msg):
        held.set()
        await release.wait()
        seen.append("settled")

    def quote(msg):
        seen.append(msg["market_ticker"])
        done.set()

    ws.on_lifecycle, ws.on_ticker = lifecycle, quote
    task = asyncio.create_task(ws.run(["GAME-A"]))
    try:
        await asyncio.wait_for(held.wait(), 1)
        for _ in range(5):
            await asyncio.sleep(0)
        assert seen == []
        release.set()
        await asyncio.wait_for(done.wait(), 1)
        assert seen == ["settled", "", "OTHER-B"]
    finally:
        await stop(task)


async def test_callback_cancellation_still_cancels_reader(connect):
    feed = Feed([frame("market_lifecycle_v2", "GAME-A"), frame("ticker", "GAME-B")])
    connect(feed)
    ws = opted_in(service.KalshiWebSocket())
    seen = []

    async def lifecycle(msg):
        raise asyncio.CancelledError

    ws.on_lifecycle = lifecycle
    ws.on_ticker = seen.append
    task = asyncio.create_task(ws.run(["GAME-A"]))
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, 1)
    assert seen == []
    assert not ws.is_connected


async def test_unprepared_callbacks_keep_original_inline_order(connect):
    # The shard and shadow sockets register `on_lifecycle` without a
    # preparation; they keep the reader's original synchronous ordering.
    feed = Feed([frame("market_lifecycle_v2", "GAME-A"), frame("ticker", "OTHER-B")])
    connect(feed)
    ws = service.KalshiWebSocket()
    assert ws.on_lifecycle_prepare is None
    held, release, quoted = (asyncio.Event() for _ in range(3))

    async def lifecycle(msg):
        held.set()
        await release.wait()

    ws.on_lifecycle, ws.on_ticker = lifecycle, lambda msg: quoted.set()
    task = asyncio.create_task(ws.run(["GAME-A"]))
    try:
        await asyncio.wait_for(held.wait(), 1)
        for _ in range(5):
            await asyncio.sleep(0)
        assert not quoted.is_set()
        release.set()
        await asyncio.wait_for(quoted.wait(), 1)
    finally:
        await stop(task)


async def test_preparation_captures_before_capacity_wait(monkeypatch):
    monkeypatch.setattr(service, "MAX_PENDING_CALLBACKS", 1)
    release, prepared = asyncio.Event(), asyncio.Event()
    buffer = {"closing": 0.42}
    observed = []

    async def slow(msg):
        await release.wait()

    async def prepare_slow(msg):
        return slow

    async def prepare_close(msg):
        captured = buffer.get("closing")
        prepared.set()

        async def close(payload):
            observed.append(captured)

        return close

    async with service._KalshiCallbackDispatch() as dispatcher:
        await dispatcher.submit(
            slow,
            {"market_ticker": "OTHER-A"},
            "lifecycle",
            lifecycle=True,
            prepare=prepare_slow,
        )
        closing = asyncio.create_task(
            dispatcher.submit(
                slow,
                {"market_ticker": "GAME-A"},
                "lifecycle",
                lifecycle=True,
                prepare=prepare_close,
            )
        )
        try:
            await asyncio.wait_for(prepared.wait(), 0.2)
            buffer.clear()
            release.set()
            await closing
        finally:
            release.set()
            if not closing.done():
                closing.cancel()
                await asyncio.gather(closing, return_exceptions=True)
    assert observed == [0.42]


async def test_queued_sibling_prepares_after_the_ticks_queued_ahead_of_it():
    # A second leg of the settling game prepares IN ORDER: it must see the tick
    # that arrived for it while the first leg's write was still running, as the
    # inline reader did. Capturing it at receive time would read a stale buffer.
    buffer = {}
    release = asyncio.Event()
    captured = []

    async def slow(msg):
        await release.wait()

    async def prepare_first(msg):
        return slow

    async def prepare_second(msg):
        captured.append(buffer.get("GAME-B"))

        async def write(payload):
            pass

        return write

    def tick(msg):
        buffer[msg["market_ticker"]] = msg["p"]

    async with service._KalshiCallbackDispatch() as dispatcher:
        await dispatcher.submit(
            slow,
            {"market_ticker": "GAME-A"},
            "Lifecycle",
            lifecycle=True,
            prepare=prepare_first,
        )
        await dispatcher.submit(tick, {"market_ticker": "GAME-B", "p": 0.61}, "Ticker")
        await dispatcher.submit(
            slow,
            {"market_ticker": "GAME-B"},
            "Lifecycle",
            lifecycle=True,
            prepare=prepare_second,
        )
        for _ in range(5):
            await asyncio.sleep(0)
        assert captured == []  # still queued behind GAME-A's write
        release.set()
    assert captured == [0.61]


# ------------------------------------------- the real task callbacks ----
# `prepare_lifecycle` / `handle_lifecycle` are closures inside the consumer, so
# they are lifted out of the real source and run against fakes for the state
# they close over. The assertion reads the bound parameter of the real UPDATE
# that writes `FuturesOutcome.calibration_probability`.

TASK_SOURCE = Path(kalshi_task.__file__).read_text()


def _lift(*names):
    tree = ast.parse(TASK_SOURCE)
    found = {
        node.name: node
        for node in ast.walk(tree)
        if isinstance(node, ast.AsyncFunctionDef) and node.name in names
    }
    assert set(found) == set(names), f"missing closures: {set(names) - set(found)}"
    return [found[name] for name in names]


class _Result:
    def first(self):
        return None


class _Session:
    def __init__(self, statements):
        self.statements = statements

    async def execute(self, statement):
        self.statements.append(statement)
        return _Result()


class _Refresher:
    async def publish_market_changes(self, session):
        pass


def _calibration(statements):
    """The `calibration_probability` each write binds, in write order."""
    values = []
    for statement in statements:
        params = statement.compile().params
        if "calibration_probability" in params:
            values.append(params["calibration_probability"])
    return values


async def _settle_through_reader(connect, closing, *, prepare_mode):
    """One quote then a terminal lifecycle for GAME-A; a flush drains the
    buffer the moment it is allowed to run. Returns the calibration writes."""
    buffer = {}
    statements = []
    ready, written = asyncio.Event(), asyncio.Event()

    class _Context:
        async def __aenter__(self):
            return _Session(statements)

        async def __aexit__(self, *args):
            written.set()

    namespace = {
        "asyncio": asyncio,
        "update": update,
        "FuturesMarket": FuturesMarket,
        "FuturesOutcome": FuturesOutcome,
        "settled_values": kalshi_task.settled_values,
        "queue_market_change": lambda *a, **kw: None,
        "is_terminal": kalshi_task.is_terminal,
        "open_contract_ids": {},
        "ticker_to_ids": {"GAME-A": (1, 2)},
        "market_id_by_ext": {"GAME": 1},
        "buffer_lock": asyncio.Lock(),
        "price_buffer": buffer,
        "get_task_session": lambda: _Context(),
        "blend_refresher": _Refresher(),
        "logger": kalshi_task.logger,
        "stats": {"errors": 0, "settlements": 0},
        "_UNCAPTURED": object(),
    }
    nodes = _lift("prepare_lifecycle", "handle_lifecycle")
    exec(
        compile(ast.Module(body=nodes, type_ignores=[]), "kalshi_task", "exec"),
        namespace,
    )

    feed = Feed(
        [
            frame("ticker", "GAME-A"),
            frame("market_lifecycle_v2", "GAME-A", status="determined", result="yes"),
        ]
    )
    connect(feed)
    ws = service.KalshiWebSocket()
    ws.on_ticker = lambda msg: (
        buffer.__setitem__(2, (closing, 0.4, 0.44)),
        ready.set(),
    )
    ws.on_lifecycle = namespace["handle_lifecycle"]
    if prepare_mode == "real":
        ws.on_lifecycle_prepare = namespace["prepare_lifecycle"]
    elif prepare_mode == "defer_without_capture":
        opted_in(ws)

    async def flusher():
        await ready.wait()
        buffer.pop(2, None)

    flush = asyncio.create_task(flusher())
    reader = asyncio.create_task(ws.run(["GAME-A"]))
    try:
        await asyncio.wait_for(written.wait(), 1)
    finally:
        reader.cancel()
        flush.cancel()
        await asyncio.gather(reader, flush, return_exceptions=True)
    return _calibration(statements)


def _expected(closing):
    # handle_lifecycle writes the settling leg, then the opposite leg.
    return [closing, (1.0 - closing) if closing else None]


@pytest.mark.parametrize("closing", [0.0, 0.42, 1.0, None])
async def test_real_prepared_callback_keeps_the_closing_forecast(connect, closing):
    assert await _settle_through_reader(connect, closing, prepare_mode="real") == (
        _expected(closing)
    )


@pytest.mark.parametrize("closing", [0.0, 0.42, 1.0, None])
async def test_inline_reader_matches_the_prepared_capture(connect, closing):
    # Baseline arm: no preparation registered ⇒ the original inline path.
    assert await _settle_through_reader(connect, closing, prepare_mode="inline") == (
        _expected(closing)
    )


async def test_control_deferring_without_capture_loses_the_closing_forecast(connect):
    # The rejected prototype's shape. If this ever stops losing the value the
    # race above no longer exercises the flush, and the tests above prove nothing.
    assert await _settle_through_reader(
        connect, 0.42, prepare_mode="defer_without_capture"
    ) == [None, None]


async def test_prepare_leaves_ineligible_frames_to_the_callback_unchanged():
    namespace = {
        "asyncio": asyncio,
        "is_terminal": kalshi_task.is_terminal,
        "open_contract_ids": {"OPEN-X": (7, 8)},
        "ticker_to_ids": {"GAME-A": (1, 2)},
        "market_id_by_ext": {"GAME": 1},
        "buffer_lock": asyncio.Lock(),
        "price_buffer": {2: (0.42, 0.4, 0.44)},
        "_UNCAPTURED": object(),
        "handle_lifecycle": lambda msg, **kw: None,
    }
    (node,) = _lift("prepare_lifecycle")
    exec(
        compile(ast.Module(body=[node], type_ignores=[]), "kalshi_task", "exec"),
        namespace,
    )
    prepare, uncaptured = namespace["prepare_lifecycle"], namespace["_UNCAPTURED"]

    async def captured(msg):
        return (await prepare(msg)).keywords["closing_price"]

    assert await captured({"market_ticker": "game-a", "status": "determined"}) == 0.42
    assert await captured({"market_ticker": "GAME-A", "status": "active"}) is uncaptured
    assert (
        await captured({"market_ticker": "OPEN-X", "status": "determined"})
        is uncaptured
    )
    assert (
        await captured({"market_ticker": "NOPE-A", "status": "determined"})
        is uncaptured
    )
    assert (
        await captured({"market_ticker": "GAME", "status": "determined"}) is uncaptured
    )


def test_consumer_registers_the_preparation_beside_the_callback():
    assert "ws.on_lifecycle = handle_lifecycle\n" in TASK_SOURCE
    assert "ws.on_lifecycle_prepare = prepare_lifecycle\n" in TASK_SOURCE
