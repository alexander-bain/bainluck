"""A visible market set shares fanout, keeps market truth, and releases resources."""

import asyncio
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.routes import market_stream as route
from app.utils import live_fanout, market_quote_push as push


class Request:
    async def is_disconnected(self):
        return False


class Hub:
    def __init__(self):
        self.subscriptions = {}
        self.released = []

    async def subscribe(self, channel):
        sub = live_fanout.Subscription(channel)
        self.subscriptions[channel] = sub
        return sub

    def release(self, sub):
        self.released.append(sub.channel)


def frame(mid=1, terminal=False, age=0):
    stamp = datetime.now(timezone.utc) - timedelta(seconds=age)
    return json.dumps(
        dict(
            push._change(
                market_id=mid,
                source="kalshi",
                outcome_observed_at={mid * 10: stamp},
                terminal=terminal,
                updated_at=None,
            ),
            published_at=stamp.isoformat(),
        )
    )


async def opened(monkeypatch, ids=(1, 2)):
    hub = Hub()
    monkeypatch.setattr(live_fanout, "fanout", lambda: hub)
    stream = route._stream(list(ids), [9], Request())
    assert (await anext(stream)).startswith("retry: ")
    message = await anext(stream)
    assert message.startswith("event: open")
    assert json.loads(message.split("data: ")[1]) == {
        "market_ids": list(ids),
        "unavailable_market_ids": [9],
    }
    return hub, stream


async def test_many_markets_use_the_same_hub_and_final_invalidates_before_unsubscribe(
    monkeypatch,
):
    hub, stream = await opened(monkeypatch)
    try:
        hub.subscriptions["live:market:1"].offer(frame(1, terminal=True))
        message = await asyncio.wait_for(anext(stream), 1)
        assert message.startswith("event: market")
        assert json.loads(message.split("data: ")[1])["terminal"] is True
        hub.subscriptions["live:market:2"].offer(frame(2))
        second = await asyncio.wait_for(anext(stream), 1)
        assert json.loads(second.split("data: ")[1])["market_id"] == 2
        assert hub.released == ["live:market:1"]
        hub.subscriptions["live:market:2"].offer(frame(2, terminal=True))
        assert (await asyncio.wait_for(anext(stream), 1)).startswith("event: market")
        closed = await asyncio.wait_for(anext(stream), 1)
        assert json.loads(closed.split("data: ")[1]) == {
            "reason": "settled",
            "market_ids": [1, 2],
        }
    finally:
        await stream.aclose()
    assert hub.released == ["live:market:1", "live:market:2"]
    assert route._open_connections == 0


@pytest.mark.parametrize(
    "bad", ["not json", frame(2), frame(1, age=60), frame(1, age=-60)]
)
async def test_wrong_identity_stale_and_malformed_frames_cannot_reach_reader(
    monkeypatch, bad
):
    hub, stream = await opened(monkeypatch, ids=(1,))
    try:
        hub.subscriptions["live:market:1"].offer(bad)
        valid = frame(1)
        hub.subscriptions["live:market:1"].offer(valid)
        message = await asyncio.wait_for(anext(stream), 1)
        assert json.loads(message.split("data: ")[1]) == json.loads(valid)
    finally:
        await stream.aclose()


async def test_dead_hub_announces_reconnect_and_releases_all(monkeypatch):
    hub, stream = await opened(monkeypatch)
    hub.subscriptions["live:market:1"].offer(live_fanout.CLOSED)
    assert '"reason": "upstream"' in await anext(stream)
    await stream.aclose()
    assert set(hub.released) == {"live:market:1", "live:market:2"}


async def test_cancellation_during_wait_releases_every_subscription(monkeypatch):
    hub, stream = await opened(monkeypatch)
    pending = asyncio.create_task(anext(stream))
    await asyncio.sleep(0)
    pending.cancel()
    with pytest.raises(asyncio.CancelledError):
        await pending
    assert set(hub.released) == {"live:market:1", "live:market:2"}
    assert route._open_connections == 0


async def test_partial_subscription_failure_cleans_up_and_announces_reconnect(
    monkeypatch,
):
    hub = Hub()
    original = hub.subscribe

    async def subscribe(channel):
        if channel == "live:market:2":
            raise RuntimeError("connection failed")
        return await original(channel)

    hub.subscribe = subscribe
    monkeypatch.setattr(live_fanout, "fanout", lambda: hub)
    stream = route._stream([1, 2], [], Request())
    assert '"reason": "upstream"' in await anext(stream)
    await stream.aclose()
    assert hub.released == ["live:market:1"]


async def test_silent_stream_heartbeats_and_rolls_over(monkeypatch):
    monkeypatch.setattr(route, "HEARTBEAT_INTERVAL_S", 0)
    monkeypatch.setattr(route, "FRAME_WAIT_S", 0.001)
    hub, stream = await opened(monkeypatch)
    try:
        assert (await asyncio.wait_for(anext(stream), 1)).startswith("event: heartbeat")
        monkeypatch.setattr(route, "MAX_CONNECTION_S", 0)
        assert '"reason": "max_age"' in await anext(stream)
    finally:
        await stream.aclose()


@pytest.mark.parametrize(
    "ids",
    [
        "",
        "0",
        "-1",
        "1,,2",
        "1.2",
        "true",
        "١",
        "2147483648",
        ",".join(map(str, range(1, 52))),
    ],
)
def test_invalid_ids_are_bounded_before_database_access(ids):
    with pytest.raises(HTTPException) as error:
        route._market_ids(ids)
    assert error.value.status_code == 400


def test_ids_are_deduplicated_without_changing_order():
    assert route._market_ids("3,1,3,2") == [3, 1, 2]


async def test_connect_eligibility_uses_market_truth_without_an_event_table():
    engine = create_engine("sqlite://")
    with Session(engine) as sync:
        sync.execute(
            text(
                "CREATE TABLE futures_markets (id INTEGER PRIMARY KEY, source TEXT, status TEXT)"
            )
        )
        sync.execute(
            text(
                "CREATE TABLE futures_outcomes (id INTEGER PRIMARY KEY, market_id INTEGER, is_winner BOOLEAN)"
            )
        )
        sync.execute(
            text(
                "INSERT INTO futures_markets VALUES (1,'kalshi','open'), (2,'polymarket','suspended'), (3,'kalshi','resolved'), (4,'betting','open'), (5,'kalshi','open'), (6,'polymarket',NULL), (7,'polymarket','FINAL')"
            )
        )
        sync.execute(text("INSERT INTO futures_outcomes VALUES (51,5,1), (11,1,0)"))
        db = SimpleNamespace(execute=AsyncMock(side_effect=sync.execute))
        admitted, existing = await route._eligible_markets(db, list(range(1, 9)))
        assert admitted == [1, 2, 6]
        assert existing == list(range(1, 8))
        assert db.execute.await_count == 1
    engine.dispose()


@pytest.mark.parametrize(
    "admitted,existing,status", [([1], [1, 2], 200), ([], [], 404), ([], [1], 409)]
)
async def test_database_session_ends_before_stream_and_refusals_are_explicit(
    monkeypatch, admitted, existing, status
):
    class Maker:
        closed = False

        def __call__(self):
            return self

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            self.closed = True

    maker = Maker()
    monkeypatch.setattr(route, "async_session_maker", maker)
    monkeypatch.setattr(
        route, "_eligible_markets", AsyncMock(return_value=(admitted, existing))
    )
    if status == 200:
        response = await route.stream_markets(Request(), "1,2")
        assert response.status_code == 200
        assert maker.closed
        with pytest.raises(RuntimeError, match="gone before body"):
            await response(
                {"type": "http", "asgi": {"spec_version": "2.4"}},
                AsyncMock(),
                AsyncMock(side_effect=RuntimeError("gone before body")),
            )
        assert route._open_connections == 0
    else:
        with pytest.raises(HTTPException) as error:
            await route.stream_markets(Request(), "1,2")
        assert error.value.status_code == status
        assert error.value.detail["poll"] is True
    assert maker.closed


async def test_capacity_refuses_before_a_database_connection(monkeypatch):
    monkeypatch.setattr(route, "_open_connections", route.MAX_CONNECTIONS)
    lookup = AsyncMock()
    monkeypatch.setattr(route, "_eligible_markets", lookup)
    with pytest.raises(HTTPException) as error:
        await route.stream_markets(Request(), "1")
    assert error.value.status_code == 503
    assert error.value.detail["poll"] is True
    lookup.assert_not_awaited()


async def test_concurrent_admission_reserves_capacity_before_any_generator_starts(
    monkeypatch,
):
    monkeypatch.setattr(route, "MAX_CONNECTIONS", 1)

    class Maker:
        def __call__(self):
            return self

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

    monkeypatch.setattr(route, "async_session_maker", Maker())
    arrived = 0
    both_in_database = asyncio.Event()

    async def lookup(_db, _ids):
        nonlocal arrived
        arrived += 1
        if arrived == 2:
            both_in_database.set()
        await both_in_database.wait()
        return [1], [1]

    monkeypatch.setattr(route, "_eligible_markets", lookup)
    results = await asyncio.gather(
        route.stream_markets(Request(), "1"),
        route.stream_markets(Request(), "1"),
        return_exceptions=True,
    )
    accepted = [r for r in results if isinstance(r, StreamingResponse)]
    refused = [r for r in results if isinstance(r, HTTPException)]
    assert len(accepted) == len(refused) == 1
    assert refused[0].status_code == 503
    assert route._open_connections == 1
    with pytest.raises(asyncio.CancelledError):
        await accepted[0](
            {"type": "http", "asgi": {"spec_version": "2.4"}},
            AsyncMock(),
            AsyncMock(side_effect=asyncio.CancelledError()),
        )
    assert route._open_connections == 0


async def test_response_completion_releases_reservation_and_hub(monkeypatch):
    hub = Hub()
    monkeypatch.setattr(live_fanout, "fanout", lambda: hub)
    monkeypatch.setattr(route, "MAX_CONNECTION_S", 0)
    response = route._MarketStreamResponse(route._stream([1], [], Request()))
    response.reserve()
    assert route._open_connections == 1
    await response(
        {"type": "http", "asgi": {"spec_version": "2.4"}}, AsyncMock(), AsyncMock()
    )
    assert route._open_connections == 0
    assert hub.released == ["live:market:1"]


def test_route_is_mounted_on_the_public_api():
    from app.main import app

    assert any(
        getattr(item, "path", None) == "/api/markets/stream" for item in app.routes
    )


@pytest.mark.parametrize("protocol", [2, 3])
async def test_market_and_event_streams_share_one_real_pubsub_socket(
    monkeypatch, protocol
):
    from app.routes import event_stream
    from app.tasks import redis_state
    from tests.test_sse_shares_one_pubsub_connection_6515 import (
        _TinyPubSubServer,
        _live_frame,
        _until,
    )

    server = _TinyPubSubServer()
    monkeypatch.setattr(
        redis_state,
        "REDIS_URL",
        f"redis://127.0.0.1:{server.port}/0?protocol={protocol}",
    )
    monkeypatch.setattr(live_fanout, "READ_TIMEOUT_S", 0.01)
    await live_fanout.reset_fanout()
    markets = route._stream([1, 2], [], Request())
    event = event_stream._stream(3, Request())
    try:
        for stream in (markets, event):
            await anext(stream)
            assert (await anext(stream)).startswith("event: open")
        assert await _until(
            lambda: server.subscriber_count("live:market:2") == 1
            and server.subscriber_count("live:event:3") == 1
        )
        assert server.accepted == server.peak_concurrent == 1
        assert live_fanout.fanout().subscriber_count == 3
        server.publish("live:market:2", frame(2))
        server.publish("live:event:3", _live_frame(3))
        assert (await asyncio.wait_for(anext(markets), 2)).startswith("event: market")
        assert (await asyncio.wait_for(anext(event), 2)).startswith(
            "event: probability"
        )
    finally:
        await markets.aclose()
        await event.aclose()
        await live_fanout.reset_fanout()
        server.close()
    assert route._open_connections == 0
