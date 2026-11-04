"""#10090 — a Discover futures card in view shows the venue's move at arrival.

THE SHIP. A Kalshi or Polymarket market a reader holds (its ``live:market:<id>``
channel is subscribed by a web dyno's SSE hub) gets a PROVISIONAL
``market_preview`` frame the moment the venue socket buffers its price, instead
of waiting for the flush, its committed invalidation and the card's price-card
re-read. `app.utils.market_preview` is the publisher; `routes/market_stream`
forwards the frame under its own SSE event name.

THE HARD ACCEPTANCE pinned here:

* no database session, engine or row is touched on the publish path;
* only held markets publish; change-only; at most one frame per market per
  window, with the newest price per leg (leading AND trailing edge);
* a settled market or graded leg, or a terminal 0/1, never publishes;
* the frame's shape, and an invalidation-only reader (`parse_market_frame`)
  refuses it, so an older web dyno drops it;
* the stream forwards it as ``event: market_preview`` within its ttl;
* through the REAL Kalshi and Polymarket consumers: the preview goes out before
  the flush, and the flush writes exactly the batch it writes with previews off.
"""

import asyncio
import json
import math
from datetime import datetime, timedelta, timezone

import pytest

import app.services.database as database
import app.tasks.base as task_base
from app.routes import market_stream as route
from app.utils import live_fanout
from app.utils import market_preview as mp
from app.utils.market_quote_push import parse_market_frame
from app.utils.reader_presence import HeldEventCache, ReaderPresence

MARKET = 7
YES, NO = 70, 71


class FakeRedis:
    """The pooled-connection surface `publish_market_changes` drives."""

    def __init__(self, on_publish=None):
        self.published: list[tuple[str, dict]] = []
        outer = self

        class Connection:
            def pack_commands(self, commands):
                return list(commands)

            async def send_packed_command(self, packed):
                for command in packed:
                    assert command[0] == "PUBLISH"
                    outer.published.append((command[1], json.loads(command[2])))
                    if on_publish is not None:
                        on_publish(command[1], json.loads(command[2]))

            async def read_response(self):
                return 0  # zero listeners is a successful publication

            async def disconnect(self):
                return None

        connection = Connection()

        class Pool:
            async def get_connection(self, *_a):
                return connection

            async def release(self, _connection):
                return None

        self.connection_pool = Pool()

    def frames(self):
        return [payload for _channel, payload in self.published]


def publisher(redis, *, held=(MARKET,), window_s=0.05, **kwargs):
    return mp.MarketPreviewPublisher(
        "kalshi", lambda: redis, held=lambda: frozenset(held),
        enabled=True, window_s=window_s, **kwargs,
    )


async def settle(publisher_=None):
    for _ in range(5):
        await asyncio.sleep(0)
    if publisher_ is not None and publisher_._task is not None:
        await asyncio.wait_for(publisher_._task, 1)


# ── the publisher ───────────────────────────────────────────────────────────


async def test_a_held_markets_first_move_goes_at_once_in_the_frame_shape():
    redis = FakeRedis()
    pub = publisher(redis)
    pub.note(MARKET, YES, 0.4123456)
    await settle()
    assert len(redis.published) == 1
    channel, frame = redis.published[0]
    assert channel == "live:market:7"
    assert set(frame) == {
        "type", "preview", "market_id", "source", "outcomes", "seq", "ttl_ms", "published_at",
    }
    assert frame["type"] == "market_preview" and frame["preview"] is True
    assert "invalidation" not in frame
    assert (frame["market_id"], frame["source"], frame["ttl_ms"]) == (MARKET, "kalshi", mp.PREVIEW_TTL_MS)
    [leg] = frame["outcomes"]
    assert leg["outcome_id"] == YES and leg["p"] == 0.412346
    observed = datetime.fromisoformat(leg["observed_at"])
    assert abs((datetime.now(timezone.utc) - observed).total_seconds()) < 5
    # An invalidation-only reader (every web dyno before this change) drops it.
    assert parse_market_frame(json.dumps(frame)) is None
    assert mp.parse_market_preview(json.dumps(frame))["outcomes"] == [
        {"outcome_id": YES, "p": 0.412346, "observed_at": observed.isoformat()}
    ]
    await settle(pub)


async def test_a_burst_coalesces_to_one_trailing_frame_with_the_newest_price_per_leg():
    redis = FakeRedis()
    pub = publisher(redis, window_s=0.05)
    pub.note(MARKET, YES, 0.40)
    await settle()
    pub.note(MARKET, YES, 0.41)
    pub.note(MARKET, NO, 0.58)
    pub.note(MARKET, YES, 0.42)
    await settle()
    assert len(redis.published) == 1, "inside the window nothing more goes out"
    await asyncio.sleep(0.08)
    await settle(pub)
    frames = redis.frames()
    assert len(frames) == 2
    assert frames[1]["outcomes"] == [
        {"outcome_id": YES, "p": 0.42, "observed_at": frames[1]["outcomes"][0]["observed_at"]},
        {"outcome_id": NO, "p": 0.58, "observed_at": frames[1]["outcomes"][1]["observed_at"]},
    ]
    assert frames[1]["seq"] > frames[0]["seq"]


async def test_a_sustained_stream_is_bounded_by_the_window():
    redis = FakeRedis()
    pub = publisher(redis, window_s=0.05)
    started = asyncio.get_running_loop().time()
    for i in range(200):
        pub.note(MARKET, YES, 0.30 + (i % 50) / 1000 + 0.0001 * (i // 50))
        await asyncio.sleep(0.001)
    elapsed = asyncio.get_running_loop().time() - started
    await asyncio.sleep(0.08)
    await settle(pub)
    frames = redis.frames()
    assert 2 <= len(frames) <= math.ceil(elapsed / 0.05) + 2, (len(frames), elapsed)
    # The last price of the burst is never lost.
    assert frames[-1]["outcomes"][0]["p"] == round(0.30 + 49 / 1000 + 0.0003, 6)
    seqs = [frame["seq"] for frame in frames]
    assert seqs == sorted(seqs) and len(set(seqs)) == len(seqs)


async def test_change_only():
    redis = FakeRedis()
    pub = publisher(redis, window_s=0.02)
    pub.note(MARKET, YES, 0.40)
    await settle(pub)
    pub.note(MARKET, YES, 0.40)  # the same price again
    await settle(pub)
    pub.note(MARKET, YES, 0.41)  # a move and back inside one window
    pub.note(MARKET, YES, 0.40)
    await asyncio.sleep(0.05)
    await settle(pub)
    assert [frame["outcomes"][0]["p"] for frame in redis.frames()] == [0.40]


async def test_only_held_markets_publish():
    import time

    redis = FakeRedis()
    held = {MARKET}
    skew = [0.0]
    pub = mp.MarketPreviewPublisher(
        "polymarket", lambda: redis, held=lambda: frozenset(held), enabled=True,
        clock=lambda: time.monotonic() + skew[0],
    )
    pub.note(8, 80, 0.5)
    await settle()
    assert redis.published == [] and pub._task is None and pub._pending == {}
    pub.note(MARKET, YES, 0.5)
    await settle(pub)
    assert [payload["market_id"] for payload in redis.frames()] == [MARKET]
    held.clear()
    skew[0] += mp.HELD_RECHECK_S  # the next tick re-asks the held set
    pub.note(MARKET, YES, 0.6)
    await settle(pub)
    assert len(redis.published) == 1


async def test_a_tick_asks_the_held_set_at_most_once_per_recheck():
    asks = []
    now = [0.0]

    def held():
        asks.append(now[0])
        return frozenset()

    pub = mp.MarketPreviewPublisher(
        "kalshi", lambda: None, held=held, enabled=True, clock=lambda: now[0],
    )
    for i in range(1000):
        now[0] = i * 0.001  # 1,000 ticks over one second, none held
        pub.note(8, 80, 0.5)
    assert len(asks) == 4, asks  # 0, 0.25, 0.5, 0.75
    assert pub._pending == {} and pub._task is None


async def test_the_default_held_set_is_the_process_presence_cache(monkeypatch):
    import app.utils.reader_presence as presence

    class Cache:
        def market_ids(self):
            return frozenset({MARKET})

    monkeypatch.setattr(presence, "_HELD_EVENTS", Cache())
    redis = FakeRedis()
    pub = mp.MarketPreviewPublisher("kalshi", lambda: redis, enabled=True)
    pub.note(MARKET, YES, 0.5)
    pub.note(9, 90, 0.5)
    await settle(pub)
    assert [payload["market_id"] for payload in redis.frames()] == [MARKET]


async def test_settled_markets_graded_legs_and_terminal_prices_never_publish():
    redis = FakeRedis()
    settled = set()
    pub = publisher(redis, held=(MARKET, 8, 9), refused=lambda mid: mid in settled)
    pub.note(MARKET, YES, 1.0)
    pub.note(MARKET, YES, 0.0)
    pub.note(MARKET, YES, "nan")
    settled.add(MARKET)
    pub.note(MARKET, YES, 0.5)  # the consumer saw it settle
    pub.refuse_market(8)
    pub.note(8, 80, 0.5)  # resolved
    pub.refuse_outcome(91)
    pub.note(9, 91, 0.5)  # this leg graded
    pub.note(9, 92, 0.5)  # its sibling still trades
    await settle(pub)
    assert [(f["market_id"], [o["outcome_id"] for o in f["outcomes"]]) for f in redis.frames()] == [
        (9, [92])
    ]


async def test_a_market_that_settles_inside_its_window_drops_its_pending_price():
    redis = FakeRedis()
    settled = set()
    pub = publisher(redis, window_s=0.05, refused=lambda mid: mid in settled)
    pub.note(MARKET, YES, 0.4)
    await settle()
    pub.note(MARKET, YES, 0.5)
    settled.add(MARKET)
    await asyncio.sleep(0.08)
    await settle(pub)
    assert [f["outcomes"][0]["p"] for f in redis.frames()] == [0.4]


async def test_a_withdrawn_book_drops_the_unsent_price():
    redis = FakeRedis()
    pub = publisher(redis, window_s=0.05)
    pub.note(MARKET, YES, 0.4)
    await settle()
    pub.note(MARKET, YES, 0.5)
    pub.forget([YES])
    await asyncio.sleep(0.08)
    await settle(pub)
    assert [f["outcomes"][0]["p"] for f in redis.frames()] == [0.4]


async def test_the_kill_switch(monkeypatch):
    monkeypatch.setenv(mp.MARKET_PREVIEW_ENV, "0")
    redis = FakeRedis()
    pub = mp.MarketPreviewPublisher("kalshi", lambda: redis, held=lambda: {MARKET})
    assert pub.enabled is False
    pub.note(MARKET, YES, 0.5)
    await settle()
    assert redis.published == []
    monkeypatch.delenv(mp.MARKET_PREVIEW_ENV)
    assert mp.MarketPreviewPublisher("kalshi", lambda: redis).enabled is True


async def test_seq_keeps_rising_across_a_restarted_publisher():
    redis = FakeRedis()
    first = publisher(redis)
    first.note(MARKET, YES, 0.4)
    await settle(first)
    second = publisher(redis)  # a recycled / restarted consumer
    second.note(MARKET, YES, 0.5)
    await settle(second)
    a, b = redis.frames()
    assert b["seq"] > a["seq"]


async def test_a_redis_failure_never_raises_into_the_socket():
    def broken():
        raise ConnectionError("no redis")

    pub = mp.MarketPreviewPublisher("kalshi", broken, held=lambda: {MARKET}, enabled=True)
    pub.note(MARKET, YES, 0.5)
    await settle(pub)
    assert pub.failures == 1 and pub.frames == 0


class _Forbidden:
    """Any use of a database handle on the publish path fails the test."""

    def __init__(self, name):
        self._name = name

    def __call__(self, *_a, **_kw):
        raise AssertionError(f"the preview path touched {self._name}")

    def __getattr__(self, attr):
        raise AssertionError(f"the preview path touched {self._name}.{attr}")


async def test_the_publish_path_touches_no_database(monkeypatch):
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

    monkeypatch.setattr(database, "engine", _Forbidden("engine"))
    monkeypatch.setattr(database, "async_session_maker", _Forbidden("async_session_maker"))
    monkeypatch.setattr(task_base, "get_task_session", _Forbidden("get_task_session"))
    for name in ("execute", "scalar", "scalars", "get", "commit", "flush"):
        monkeypatch.setattr(AsyncSession, name, _Forbidden(f"AsyncSession.{name}"))
    for name in ("connect", "begin"):
        monkeypatch.setattr(AsyncEngine, name, _Forbidden(f"AsyncEngine.{name}"))
    redis = FakeRedis()
    pub = publisher(redis, window_s=0.02)
    for price in (0.40, 0.41, 0.42):
        pub.note(MARKET, YES, price)
        pub.note(MARKET, NO, 1 - price)
        await asyncio.sleep(0.03)
    await settle(pub)
    assert len(redis.published) == 3


# ── the reader ──────────────────────────────────────────────────────────────


def _wire(**overrides):
    frame = {
        "type": "market_preview", "preview": True, "market_id": MARKET, "source": "kalshi",
        "outcomes": [{"outcome_id": YES, "p": 0.4, "observed_at": "2026-11-03T17:00:01.123456+00:00"}],
        "seq": 5, "ttl_ms": 10_000, "published_at": datetime.now(timezone.utc).isoformat(),
    }
    frame.update(overrides)
    return json.dumps(frame)


@pytest.mark.parametrize("overrides", [
    {"type": "market"}, {"preview": False}, {"invalidation": True}, {"market_id": 0},
    {"source": "espn"}, {"seq": 0}, {"ttl_ms": 0}, {"ttl_ms": 600_000}, {"outcomes": []},
    {"outcomes": [{"outcome_id": YES, "p": 1.0, "observed_at": "2026-11-03T17:00:01+00:00"}]},
    {"outcomes": [{"outcome_id": YES, "p": True, "observed_at": "2026-11-03T17:00:01+00:00"}]},
    {"outcomes": [{"outcome_id": YES, "p": 0.4, "observed_at": "2026-11-03T17:00:01"}]},
    {"outcomes": [{"outcome_id": YES, "p": 0.4, "observed_at": "2026-11-03T17:00:01+00:00"}] * 2},
    {"published_at": "yesterday"},
])
def test_malformed_previews_are_refused(overrides):
    assert mp.parse_market_preview(_wire(**overrides)) is None


@pytest.mark.parametrize("raw", [None, {}, "[]", "{}", "not json", b"\xff", "market_preview"])
def test_unparseable_messages_are_ignored(raw):
    assert mp.parse_market_preview(raw) is None


# ── the held set ────────────────────────────────────────────────────────────


def test_one_presence_read_serves_held_events_and_markets():
    reads = []

    def read():
        reads.append(1)
        return ReaderPresence(market_ids=frozenset({MARKET}), event_ids=frozenset({3}))

    starts = []
    cache = HeldEventCache(read, clock=lambda: 0.0, start=starts.append)
    assert cache.market_ids() == frozenset()  # never blocks: the read starts
    starts.pop(0)()
    assert cache.market_ids() == frozenset({MARKET})
    assert cache.event_ids() == frozenset({3})
    assert reads == [1] and starts == []


# ── the stream ──────────────────────────────────────────────────────────────


class _Request:
    async def is_disconnected(self):
        return False


class _Hub:
    def __init__(self):
        self.subscriptions = {}

    async def subscribe(self, channel):
        sub = live_fanout.Subscription(channel)
        self.subscriptions[channel] = sub
        return sub

    def release(self, sub):
        return None


async def _opened(monkeypatch):
    hub = _Hub()
    monkeypatch.setattr(live_fanout, "fanout", lambda: hub)
    stream = route._stream([MARKET], [], _Request())
    assert (await anext(stream)).startswith("retry: ")
    assert (await anext(stream)).startswith("event: open")
    return hub, stream


async def test_the_stream_forwards_a_preview_under_its_own_event(monkeypatch):
    hub, stream = await _opened(monkeypatch)
    try:
        raw = _wire()
        hub.subscriptions["live:market:7"].offer(raw)
        message = await asyncio.wait_for(anext(stream), 1)
        assert message.startswith("event: market_preview\n")
        assert json.loads(message.split("data: ")[1]) == mp.parse_market_preview(raw)
    finally:
        await stream.aclose()


@pytest.mark.parametrize("market_id, age_s, kind", [
    (8, 0, "market_preview"),  # another market's frame on this channel
    (MARKET, 11, "market_preview"),  # past its 10 s ttl
    (MARKET, -60, "market_preview"),  # from the future
    (MARKET, 0, "nope"),  # malformed
], ids=["foreign", "expired", "future", "malformed"])
async def test_the_stream_drops_a_foreign_expired_or_malformed_preview(
    monkeypatch, market_id, age_s, kind,
):
    bad = _wire(
        market_id=market_id, type=kind,
        published_at=(datetime.now(timezone.utc) - timedelta(seconds=age_s)).isoformat(),
    )
    hub, stream = await _opened(monkeypatch)
    try:
        hub.subscriptions["live:market:7"].offer(bad)
        good = _wire(seq=6)
        hub.subscriptions["live:market:7"].offer(good)
        message = await asyncio.wait_for(anext(stream), 1)
        assert json.loads(message.split("data: ")[1])["seq"] == 6
    finally:
        await stream.aclose()


# ── through the real consumers ──────────────────────────────────────────────


async def test_kalshi_previews_before_the_flush_and_writes_the_same_batch(monkeypatch):
    import tests.test_kalshi_socket_prices_by_the_rest_rule_8753 as rig
    from tests.test_a_settled_leg_takes_no_live_price_5411 import _NoopRefresher

    async def run(held):
        captured_at_publish = []
        holder = {}
        redis = FakeRedis(on_publish=lambda *_: captured_at_publish.append(len(holder["captured"])))

        class Refresher(_NoopRefresher):
            def _client(self):
                return redis

        class Session(rig._CapturingSession):
            def __init__(self, batches, captured, rowcount):
                holder["captured"] = captured
                super().__init__(batches, captured, rowcount)

        monkeypatch.setattr(rig, "_NoopRefresher", Refresher)
        monkeypatch.setattr(rig, "_CapturingSession", Session)
        monkeypatch.setattr(mp, "_held_market_ids", lambda: frozenset(held))
        written = await rig._price_updates(
            monkeypatch, rig._tick(yes_bid_dollars="0.40", yes_ask_dollars="0.44"),
        )
        return written, redis.frames(), captured_at_publish

    control, no_frames, _ = await run(held=())
    written, frames, at_publish = await run(held=(rig.MARKET_ID,))
    assert no_frames == []
    assert [(f["market_id"], f["source"], [(o["outcome_id"], o["p"]) for o in f["outcomes"]])
            for f in frames] == [(rig.MARKET_ID, "kalshi", [(rig.OUTCOME_ID, 0.42)])]
    assert at_publish == [0], "the preview went out before the flush wrote the row"
    assert len(written) == len(control) == 1
    assert written[0][1] == control[0][1], "the flush batch is the one it writes with no preview"
    assert str(written[0][0]) == str(control[0][0])


async def test_polymarket_previews_before_the_flush_and_writes_the_same_batch(monkeypatch):
    import tests.test_poly_ws_side1_leg_pairing_8403 as rig

    async def run(held):
        writes_at_publish = []
        holder = {}
        redis = FakeRedis(on_publish=lambda *_: writes_at_publish.append(list(holder["writes"])))

        class Refresher(rig._NoopRefresher):
            def _client(self):
                return redis

        monkeypatch.setattr(rig, "_NoopRefresher", Refresher)
        monkeypatch.setattr(mp, "_held_market_ids", lambda: frozenset(held))
        real_session = rig._Session

        class Session(real_session):
            def __init__(self, batches, writes, *rest):
                holder["writes"] = writes
                super().__init__(batches, writes, *rest)

        monkeypatch.setattr(rig, "_Session", Session)
        writes, _stats = await rig._run(
            monkeypatch, rig.SPECIMEN_LEGS, [rig._book(rig.LUKKO_TOKEN, "0.42", "0.50")],
        )
        return writes, redis.frames(), writes_at_publish

    control, no_frames, _ = await run(held=())
    writes, frames, at_publish = await run(held=(rig.MARKET_ID,))
    assert no_frames == []
    assert len(frames) == 1 and frames[0]["market_id"] == rig.MARKET_ID
    assert frames[0]["source"] == "polymarket"
    assert {o["outcome_id"]: o["p"] for o in frames[0]["outcomes"]} == {
        rig.LUKKO_LEG: pytest.approx(0.46),
    }
    assert at_publish == [[]], "the preview went out before the flush wrote the row"
    assert writes == control
