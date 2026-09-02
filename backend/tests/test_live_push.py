"""live/034 S1 — guards for the SSE live push.

The ship is "on a live match the number moves by itself, and the page says how
old it is". The failure classes that would silently un-ship it, each with a test
below:

* publisher and subscriber drift onto different channel strings — no test
  fails, no frame ever arrives, and the stream is simply dead forever;
* the aggregate falls back to `opening_home_probability`, arrives as a
  `Decimal`, `json.dumps` raises inside the publisher, and the push goes dark on
  exactly the events with no live source;
* a malformed message reaches the subscriber's loop and kills a connection —
  on the loop that also serves `/api/feed`;
* an `sse_encode` frame loses its terminating blank line, so everything looks
  right on the wire and no client handler ever fires;
* a stale buffered frame is forwarded after a stall and the number animates
  BACKWARDS to a price the market has already left;
* the push raises out of `LiveBlendRefresher` and takes down the price
  streaming that is the WS dyno's actual job (gotcha #42);
* the frame carries the single moved source's price instead of the aggregate,
  putting a second disagreeing number on screen ("the blend is the product").
"""

import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.utils.live_push import (
    MAX_FRAME_AGE_S,
    build_frame,
    event_channel,
    parse_frame,
    publish_frame,
    sse_encode,
)


def _frame(**over):
    base = dict(
        event_id=42,
        probability=0.61,
        source="kalshi",
        source_value=0.61,
        updated_at="2026-09-01T18:00:00+00:00",
        status="live",
    )
    base.update(over)
    return build_frame(**base)


class TestChannelAgreement:
    """The publisher and the subscriber are in different processes on
    different dynos. A drifted channel string cannot fail loudly — it delivers
    nothing, quietly. Both halves must resolve the name through this one
    function, and these pin its shape."""

    def test_channel_is_namespaced_per_event(self):
        assert event_channel(42) == "live:event:42"
        assert event_channel(7) != event_channel(8)

    def test_channel_accepts_a_numeric_string_id(self):
        """Route params arrive as strings often enough to be worth pinning."""
        assert event_channel("42") == event_channel(42)

    def test_the_route_and_the_refresher_use_this_function(self):
        """Not a style check — the actual drift guard.

        If either side ever inlines an f-string instead of importing this, the
        stream silently stops delivering. Assert the symbol is imported by both
        modules rather than that some string appears in them.
        """
        import app.routes.event_stream as route
        import app.tasks.live_blend_refresh as refresher
        import inspect

        assert route.event_channel is event_channel
        # The refresher imports it indirectly via `build_frame`/`publish_frame`,
        # which is the whole point — it never names a channel itself.
        source = inspect.getsource(refresher)
        assert "live:event:" not in source


class TestBuildFrame:
    def test_carries_the_aggregate_not_the_moved_source(self):
        """`p` is the number the hero renders. `source_value` is the feed that
        moved. Collapsing the two would put two disagreeing numbers on screen."""
        frame = _frame(probability=0.61, source_value=0.44)
        assert frame["p"] == 0.61
        assert frame["source_value"] == 0.44

    def test_a_decimal_aggregate_is_json_serialisable(self):
        """The real hazard: `compute_aggregate_probability` can fall back to
        `opening_home_probability`, a SQLAlchemy Numeric, which arrives as a
        Decimal the stdlib encoder refuses."""
        frame = _frame(probability=Decimal("0.6100"))
        assert isinstance(frame["p"], float)
        json.dumps(frame)  # would raise before the coercion

    def test_a_decimal_source_value_is_json_serialisable(self):
        frame = _frame(source_value=Decimal("0.4400"))
        assert isinstance(frame["source_value"], float)
        json.dumps(frame)

    def test_a_missing_aggregate_stays_null_rather_than_becoming_zero(self):
        """None means "no number". Coercing it to 0.0 would render a confident
        0% on a live hero."""
        assert _frame(probability=None)["p"] is None

    def test_updated_at_is_the_stamp_not_the_send_time(self):
        """The client counts "live · Ns ago" from this. It must be the write
        time, carried through verbatim."""
        assert _frame()["updated_at"] == "2026-09-01T18:00:00+00:00"


class TestParseFrame:
    """One bad message must never kill a connection on the shared loop."""

    def test_round_trips_a_published_frame(self):
        frame = _frame()
        assert parse_frame(json.dumps(frame)) == frame

    def test_accepts_bytes_as_redis_delivers_them(self):
        frame = _frame()
        assert parse_frame(json.dumps(frame).encode("utf-8")) == frame

    @pytest.mark.parametrize(
        "bad",
        [
            "not json at all",
            "",
            b"\xff\xfe not utf-8",
            json.dumps([1, 2, 3]),          # right JSON, wrong shape
            json.dumps({"no": "event_id"}),  # dict without the key we index
            None,
            12345,
        ],
    )
    def test_garbage_returns_none_and_never_raises(self, bad):
        assert parse_frame(bad) is None


class TestSseEncode:
    def test_a_message_terminates_with_a_blank_line(self):
        """The blank line is what dispatches the event. Without it the bytes
        look correct and no handler ever fires."""
        assert sse_encode("{}").endswith("\n\n")

    def test_a_named_event_precedes_its_data(self):
        out = sse_encode('{"a":1}', event="probability")
        assert out == 'event: probability\ndata: {"a":1}\n\n'

    def test_an_unnamed_message_has_no_event_line(self):
        assert sse_encode("{}") == "data: {}\n\n"

    def test_compact_json_stays_on_one_data_line(self):
        """A newline inside `data` would split one frame into two."""
        payload = json.dumps(_frame(), separators=(",", ":"))
        assert payload.count("\n") == 0
        assert sse_encode(payload).count("data:") == 1


class TestPublishFrame:
    """A stamp that already committed must not be reported as failed because a
    fanout nobody may be listening to did not go out."""

    @pytest.mark.asyncio
    async def test_publishes_on_the_events_channel(self):
        sent = []

        class FakeRedis:
            async def publish(self, channel, payload):
                sent.append((channel, payload))

        assert await publish_frame(FakeRedis(), _frame(event_id=99)) is True
        channel, payload = sent[0]
        assert channel == "live:event:99"
        assert json.loads(payload)["event_id"] == 99

    @pytest.mark.asyncio
    async def test_a_broken_client_returns_false_and_never_raises(self):
        class BrokenRedis:
            async def publish(self, channel, payload):
                raise ConnectionError("redis is gone")

        assert await publish_frame(BrokenRedis(), _frame()) is False


class TestFrameFreshness:
    """Forwarding a frame buffered through a stall animates the number
    BACKWARDS to a price the market has left — which reads as a real move."""

    def _fresh(self, age_s):
        from app.routes.event_stream import _frame_is_fresh

        now = datetime(2026, 9, 1, 18, 0, 0, tzinfo=timezone.utc)
        stamp = (now - timedelta(seconds=age_s)).isoformat()
        return _frame_is_fresh({"updated_at": stamp}, now)

    def test_a_just_stamped_frame_is_fresh(self):
        assert self._fresh(0) is True

    def test_a_frame_inside_the_window_is_fresh(self):
        assert self._fresh(MAX_FRAME_AGE_S - 1) is True

    def test_a_frame_past_the_window_is_dropped(self):
        assert self._fresh(MAX_FRAME_AGE_S + 1) is False

    def test_an_unparseable_stamp_is_forwarded_rather_than_dropped(self):
        """Fail OPEN. A stamp we cannot read is not evidence of staleness, and
        dropping on it would silently blank a working stream."""
        from app.routes.event_stream import _frame_is_fresh

        now = datetime(2026, 9, 1, 18, 0, 0, tzinfo=timezone.utc)
        assert _frame_is_fresh({"updated_at": "not-a-date"}, now) is True
        assert _frame_is_fresh({}, now) is True

    def test_a_naive_stamp_is_read_as_utc_not_as_local(self):
        """A naive stamp read as local time would be hours off and every frame
        would be judged stale — the stream would go dark while looking healthy."""
        from app.routes.event_stream import _frame_is_fresh

        now = datetime(2026, 9, 1, 18, 0, 0, tzinfo=timezone.utc)
        assert _frame_is_fresh({"updated_at": "2026-09-01T17:59:55"}, now) is True


class TestRefresherPublishContainment:
    """The push runs on the dyno whose actual job is streaming prices. Nothing
    here may interrupt that (gotcha #42)."""

    @pytest.mark.asyncio
    async def test_a_publish_failure_is_counted_not_raised(self, monkeypatch):
        from app.tasks import live_blend_refresh as mod

        class BrokenRedis:
            async def publish(self, channel, payload):
                raise ConnectionError("redis is gone")

        monkeypatch.setattr(
            "app.tasks.redis_state.get_async_redis_client", lambda: BrokenRedis()
        )
        r = mod.LiveBlendRefresher("kalshi")
        await r._publish([_frame(), _frame()])
        assert r.stats["publish_errors"] == 2
        assert r.stats["published"] == 0

    @pytest.mark.asyncio
    async def test_a_client_that_cannot_be_built_is_counted_not_raised(
        self, monkeypatch
    ):
        """No REDIS_URL, a refused TLS handshake — the client build itself can
        fail, which `publish_frame`'s own try/except never sees."""
        from app.tasks import live_blend_refresh as mod

        def explode():
            raise RuntimeError("no REDIS_URL")

        monkeypatch.setattr(
            "app.tasks.redis_state.get_async_redis_client", explode
        )
        r = mod.LiveBlendRefresher("kalshi")
        await r._publish([_frame()])
        assert r.stats["publish_errors"] == 1

    @pytest.mark.asyncio
    async def test_a_bad_client_is_dropped_so_the_next_batch_rebuilds_it(
        self, monkeypatch
    ):
        from app.tasks import live_blend_refresh as mod

        class BrokenRedis:
            async def publish(self, channel, payload):
                raise ConnectionError("gone")

        monkeypatch.setattr(
            "app.tasks.redis_state.get_async_redis_client", lambda: BrokenRedis()
        )
        r = mod.LiveBlendRefresher("kalshi")
        r._redis = object()  # a poisoned client from an earlier batch
        await r._publish([_frame()])
        assert r._redis is None

    @pytest.mark.asyncio
    async def test_an_empty_batch_opens_no_connection(self, monkeypatch):
        """A consumer run that never stamps anything must never build a client."""
        from app.tasks import live_blend_refresh as mod

        built = []

        def track():
            built.append(1)
            raise AssertionError("should not be reached")

        monkeypatch.setattr(
            "app.tasks.redis_state.get_async_redis_client", track
        )
        r = mod.LiveBlendRefresher("kalshi")
        await r._publish([])
        assert built == []

    @pytest.mark.asyncio
    async def test_successful_publishes_are_counted(self, monkeypatch):
        from app.tasks import live_blend_refresh as mod

        class FakeRedis:
            def __init__(self):
                self.sent = []

            async def publish(self, channel, payload):
                self.sent.append(channel)

        fake = FakeRedis()
        monkeypatch.setattr(
            "app.tasks.redis_state.get_async_redis_client", lambda: fake
        )
        r = mod.LiveBlendRefresher("kalshi")
        await r._publish([_frame(event_id=1), _frame(event_id=2)])
        assert r.stats["published"] == 2
        assert fake.sent == ["live:event:1", "live:event:2"]


class TestLiveGate:
    """Push is for LIVE events only; everything else polls (the ruling)."""

    def test_only_live_is_pushed(self):
        from app.routes.event_stream import LIVE_STATUSES

        assert "live" in LIVE_STATUSES
        for polled in ("scheduled", "completed", "closed", "postponed"):
            assert polled not in LIVE_STATUSES

    def test_heartbeat_fits_inside_the_heroku_router_idle_timeout(self):
        """~55s idle and the router closes the connection. Two heartbeats have
        to fit inside that so one can be lost without killing the stream."""
        from app.routes.event_stream import HEARTBEAT_INTERVAL_S

        assert HEARTBEAT_INTERVAL_S * 2 < 55
