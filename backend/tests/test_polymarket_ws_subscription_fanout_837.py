"""#837 — the Polymarket subscribe is fanned over sized connections.

WHY THIS FILE EXISTS. The venue accepts an oversized subscribe frame and then
serves a FRACTION of it, silently: no error, no close, the connection holds and
streams a few hundred assets. live/512 measured it against the public CLOB
socket with a 119-asset probe set pinned at the FRONT of every list, only the
filler behind it changing:

    719 assets (56.9 KiB) -> 119/119 of the probe served
    778 assets (61.6 KiB) ->  12/119
  2,000 assets           ->   6/119

Monotone, reproduced twice, and not a prefix — at 1,019 subscribed it served 180
assets, 8 of them from the front-placed probe. Production was sending >=3,274
ids in one ~255 KiB frame and re-dealing it six times an hour, which is how a
176-minute MNF game produced a single 15.5-minute band of prices.

THE FAILURE IS SILENT AT EVERY LAYER WE OWN, which is the whole reason these
are guard tests rather than a comment: the socket is connected, the message
count rises, no handler errors, and the only visible symptom is a chart that
does not move. So the properties pinned here are the ones whose breakage is
invisible in production:

  * no asset is ever dropped by the sharding (a dropped id IS the defect);
  * every shard's REAL serialized frame fits the bound (the sizing arithmetic
    is an estimate, and an estimate that drifts under-count re-creates the bug);
  * the bound is in BYTES, so it cannot be defeated by longer ids;
  * cancellation tears every connection down (the caller recycles on a timer,
    so a leak here is one socket per shard every 10 minutes);
  * coverage is counted on the WIRE, before handler filtering.

These numbers are NOT a claim about a documented venue limit. Nothing published
says 60 KiB; the cliff was measured, not announced.
"""

import asyncio
import json
import logging

import pytest

from app.services.polymarket_ws import (
    COVERAGE_GRACE_SECONDS,
    MAX_ASSETS_PER_CONNECTION,
    MAX_SUBSCRIBE_BYTES,
    PolymarketWebSocket,
    _shard_asset_ids,
    _subscribe_frame,
)


def _ids(n, length=76):
    """Asset ids the shape of real ones — live/512 measured them at 74-78."""
    return [str(i).zfill(length) for i in range(n)]


class TestShardingLosesNothing:
    def test_every_asset_survives_the_split_in_order(self):
        assets = _ids(3274)  # the production population that broke
        shards = _shard_asset_ids(assets)

        flattened = [a for shard in shards for a in shard]
        assert flattened == assets, "sharding must not drop or reorder an asset"

    def test_an_empty_population_produces_no_shards(self):
        assert _shard_asset_ids([]) == []

    def test_one_asset_produces_one_shard(self):
        assert _shard_asset_ids(["a"]) == [["a"]]

    def test_a_single_oversized_id_still_gets_a_shard_rather_than_vanishing(self):
        # It cannot fit the bound on its own. Dropping it would be the exact
        # defect this function exists to fix, so it rides alone instead.
        huge = "x" * (MAX_SUBSCRIBE_BYTES * 2)
        shards = _shard_asset_ids(["small", huge, "also-small"])
        assert [a for s in shards for a in s] == ["small", huge, "also-small"]
        assert [huge] in shards


class TestEveryShardFitsTheBound:
    def test_the_real_serialized_frame_fits_not_just_the_estimate(self):
        # The sizing is computed incrementally rather than by serializing every
        # candidate, so this asserts against the ACTUAL frame `run` will send.
        # An arithmetic drift that under-counts would silently re-create #837.
        for shard in _shard_asset_ids(_ids(3274)):
            frame = len(_subscribe_frame(shard).encode("utf-8"))
            assert frame <= MAX_SUBSCRIBE_BYTES, (
                f"a shard serializes to {frame} bytes, over the {MAX_SUBSCRIBE_BYTES} bound"
            )

    def test_no_shard_exceeds_the_asset_cap(self):
        for shard in _shard_asset_ids(_ids(3274)):
            assert len(shard) <= MAX_ASSETS_PER_CONNECTION

    def test_the_production_population_is_fanned_not_sent_whole(self):
        assets = _ids(3274)
        one_frame = len(_subscribe_frame(assets).encode("utf-8"))
        assert one_frame > 200_000, "sanity: this is the ~255 KiB frame that broke"
        assert len(_shard_asset_ids(assets)) > 1

    def test_the_bound_is_bytes_so_longer_ids_make_smaller_shards(self):
        # A count-only cap would let id length quietly push a shard back over
        # the cliff. Ids are 74-78 chars today and nothing promises they stay.
        short = _shard_asset_ids(_ids(2000, length=20))
        long = _shard_asset_ids(_ids(2000, length=400))
        assert len(long[0]) < len(short[0])
        for shard in long:
            assert len(_subscribe_frame(shard).encode("utf-8")) <= MAX_SUBSCRIBE_BYTES

    def test_every_shard_sits_below_the_lowest_size_observed_to_degrade(self):
        # 56.9 KiB was served in full; 61.6 KiB was not. The bound is chosen so
        # the fix does not depend on the boundary being exactly where we found
        # it — if this fails, somebody raised MAX_SUBSCRIBE_BYTES into the
        # measured degradation band.
        assert MAX_SUBSCRIBE_BYTES < 56.9 * 1024


class _FakeSocket:
    """A connection that accepts a subscribe and replays canned frames."""

    def __init__(self, frames, record):
        self._frames = list(frames)
        self._record = record
        self.closed = False

    async def send(self, payload):
        if payload != "PING":
            self._record.append(payload)

    def __aiter__(self):
        async def gen():
            for frame in self._frames:
                yield frame
            # Then hold the connection open, like the venue does.
            await asyncio.sleep(3600)

        return gen()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        self.closed = True
        return False


class TestTheFanOutActuallyFans:
    @pytest.mark.asyncio
    async def test_each_shard_sends_its_own_subscribe_and_none_is_oversized(
        self, monkeypatch
    ):
        sent: list[str] = []
        sockets: list[_FakeSocket] = []

        def connect(*args, **kwargs):
            sock = _FakeSocket([], sent)
            sockets.append(sock)
            return sock

        monkeypatch.setattr(
            "websockets.connect", connect, raising=False
        )

        assets = _ids(3274)
        ws = PolymarketWebSocket()
        task = asyncio.create_task(ws.run(asset_ids=assets))
        await asyncio.sleep(0.2)
        task.cancel()
        with pytest.raises((asyncio.CancelledError, Exception)):
            await task

        expected_shards = len(_shard_asset_ids(assets))
        assert len(sent) == expected_shards, (
            f"{expected_shards} shards should have produced {expected_shards} "
            f"subscribe frames, got {len(sent)}"
        )

        subscribed = []
        for frame in sent:
            payload = json.loads(frame)
            assert payload["type"] == "market"
            assert payload["custom_feature_enabled"] is True
            assert len(frame.encode("utf-8")) <= MAX_SUBSCRIBE_BYTES
            subscribed.extend(payload["assets_ids"])

        assert sorted(subscribed) == sorted(assets), (
            "every asset must be subscribed by exactly one shard"
        )

    @pytest.mark.asyncio
    async def test_cancellation_closes_every_connection(self, monkeypatch):
        # The caller recycles on SUBSCRIPTION_REFRESH_SECONDS, so a connection
        # that outlives the cancel leaks one socket per shard every 10 minutes.
        sent: list[str] = []
        sockets: list[_FakeSocket] = []

        def connect(*args, **kwargs):
            sock = _FakeSocket([], sent)
            sockets.append(sock)
            return sock

        monkeypatch.setattr("websockets.connect", connect, raising=False)

        ws = PolymarketWebSocket()
        task = asyncio.create_task(ws.run(asset_ids=_ids(1500)))
        await asyncio.sleep(0.2)
        assert len(sockets) > 1, "the population should have fanned"

        task.cancel()
        with pytest.raises((asyncio.CancelledError, Exception)):
            await task
        await asyncio.sleep(0.05)

        assert all(s.closed for s in sockets), "a connection outlived the cancel"
        assert ws.is_connected is False

    @pytest.mark.asyncio
    async def test_one_shard_failing_hard_does_not_strand_its_siblings(
        self, monkeypatch
    ):
        # THE ARM THAT ACTUALLY GRADES THE TEARDOWN. `asyncio.gather` already
        # cancels its children when the awaiting task is cancelled, so the
        # cancel case above passes with or without the explicit teardown — it
        # pins behaviour but convicts nothing. The hole is the OTHER exit: when
        # one child leaves by an exception `_run_one` does not catch, gather
        # re-raises immediately and the siblings keep running with live sockets,
        # once per recycle, forever. Verified by mutation: deleting the
        # teardown leaves every other arm in this file green.
        class Boom(BaseException):
            """Not an Exception, so `_run_one`'s reconnect loop cannot swallow it."""

        sent: list[str] = []
        sockets: list[_FakeSocket] = []
        calls = {"n": 0}

        def connect(*args, **kwargs):
            calls["n"] += 1
            if calls["n"] == 2:
                raise Boom()
            sock = _FakeSocket([], sent)
            sockets.append(sock)
            return sock

        monkeypatch.setattr("websockets.connect", connect, raising=False)

        before = asyncio.all_tasks()
        ws = PolymarketWebSocket()
        with pytest.raises(BaseException):
            # Bounded, because a regression that stops fanning never reaches the
            # second connect and so never raises: this line would then hang to
            # the CI job timeout instead of failing. Only exit 1 is a result
            # (gotcha #124), and a gate that can only time out reports nothing.
            await asyncio.wait_for(ws.run(asset_ids=_ids(1500)), timeout=5)
        await asyncio.sleep(0.05)

        try:
            assert sockets, "sanity: at least one sibling connected before the failure"
            assert all(s.closed for s in sockets), (
                "a sibling connection was stranded when another shard died"
            )
            assert ws.is_connected is False
        finally:
            # Sweep whatever the assertion just caught, IN A FINALLY so it also
            # runs when the assertion fails. A stranded shard reconnects forever
            # and keeps the loop alive, which turns this arm's red into a CI
            # job timeout — a failure nobody can read as a failure (gotcha #124:
            # only exit 1 is a result).
            stranded = asyncio.all_tasks() - before - {asyncio.current_task()}
            for task in stranded:
                task.cancel()
            if stranded:
                await asyncio.gather(*stranded, return_exceptions=True)

    @pytest.mark.asyncio
    async def test_a_single_small_population_is_not_fanned(self, monkeypatch):
        sent: list[str] = []

        def connect(*args, **kwargs):
            return _FakeSocket([], sent)

        monkeypatch.setattr("websockets.connect", connect, raising=False)

        ws = PolymarketWebSocket()
        task = asyncio.create_task(ws.run(asset_ids=_ids(10)))
        await asyncio.sleep(0.1)
        task.cancel()
        with pytest.raises((asyncio.CancelledError, Exception)):
            await task

        assert len(sent) == 1

    @pytest.mark.asyncio
    async def test_no_asset_ids_still_subscribes_to_everything(self, monkeypatch):
        # The shadow resolution-only consumer subscribes with no ids at all.
        # There is nothing to fan, and the frame must not grow an empty list.
        sent: list[str] = []

        def connect(*args, **kwargs):
            return _FakeSocket([], sent)

        monkeypatch.setattr("websockets.connect", connect, raising=False)

        ws = PolymarketWebSocket()
        task = asyncio.create_task(ws.run())
        await asyncio.sleep(0.1)
        task.cancel()
        with pytest.raises((asyncio.CancelledError, Exception)):
            await task

        assert len(sent) == 1
        assert "assets_ids" not in json.loads(sent[0])


class TestCoverageIsCountedOnTheWire:
    @pytest.mark.asyncio
    async def test_a_frame_we_do_not_handle_still_counts_as_served(
        self, monkeypatch
    ):
        # Counting after handler filtering reads zero while the venue IS
        # sending us frames, which makes a silent shard indistinguishable from
        # an unhandled event type. The coverage number has to answer "did the
        # venue send us this asset", not "did we act on it".
        sent: list[str] = []
        frames = [
            json.dumps({"event_type": "something_we_ignore", "asset_id": "abc"}),
            json.dumps({"event_type": "tick_size_change", "asset_id": "def"}),
        ]

        def connect(*args, **kwargs):
            return _FakeSocket(frames, sent)

        monkeypatch.setattr("websockets.connect", connect, raising=False)

        ws = PolymarketWebSocket()
        task = asyncio.create_task(ws.run(asset_ids=["abc", "def", "ghi"]))
        await asyncio.sleep(0.2)
        task.cancel()
        with pytest.raises((asyncio.CancelledError, Exception)):
            await task

        stats = ws.stats
        assert stats["assets_subscribed"] == 3
        assert stats["assets_served"] == 2, (
            "both frames carried an asset_id, so both count, handled or not"
        )

    @pytest.mark.asyncio
    async def test_a_book_snapshot_list_counts_as_served(self, monkeypatch):
        # THE INSTRUMENT'S OWN BLIND SPOT. The consumer skips list frames
        # ("book snapshot — skip for now"), and the first draft of the coverage
        # counter sat BELOW that skip reading a top-level `asset_id`. A shard
        # whose markets send nothing but book snapshots then read as serving
        # zero assets — healthy, and reported as exactly the starvation this
        # change exists to detect. live/512's probe, which measured the cliff,
        # harvests these shapes; a counter that reads fewer grades the fix
        # against its own blind spots.
        sent: list[str] = []
        frames = [json.dumps([{"asset_id": "abc"}, {"asset_id": "def"}])]

        def connect(*args, **kwargs):
            return _FakeSocket(frames, sent)

        monkeypatch.setattr("websockets.connect", connect, raising=False)

        ws = PolymarketWebSocket()
        task = asyncio.create_task(ws.run(asset_ids=["abc", "def", "ghi"]))
        await asyncio.sleep(0.2)
        task.cancel()
        with pytest.raises((asyncio.CancelledError, Exception)):
            await task

        assert ws.stats["assets_served"] == 2, (
            "a book snapshot is the venue serving us those assets, skipped or not"
        )

    @pytest.mark.asyncio
    async def test_price_change_ids_nested_under_changes_count_as_served(
        self, monkeypatch
    ):
        # The other shape the probe harvests: `price_change` carries its ids in
        # a nested array, not at the top level.
        sent: list[str] = []
        frames = [
            json.dumps(
                {
                    "event_type": "price_change",
                    "market": "0xwhatever",
                    "changes": [{"asset_id": "abc"}, {"asset_id": "def"}],
                }
            )
        ]

        def connect(*args, **kwargs):
            return _FakeSocket(frames, sent)

        monkeypatch.setattr("websockets.connect", connect, raising=False)

        ws = PolymarketWebSocket()
        task = asyncio.create_task(ws.run(asset_ids=["abc", "def", "ghi"]))
        await asyncio.sleep(0.2)
        task.cancel()
        with pytest.raises((asyncio.CancelledError, Exception)):
            await task

        assert ws.stats["assets_served"] == 2, (
            "price_change ids live under `changes`; a top-level-only read sees none"
        )

    @pytest.mark.asyncio
    async def test_the_same_asset_twice_counts_once(self, monkeypatch):
        sent: list[str] = []
        frames = [
            json.dumps({"event_type": "best_bid_ask", "asset_id": "abc"}),
            json.dumps({"event_type": "last_trade_price", "asset_id": "abc"}),
        ]

        def connect(*args, **kwargs):
            return _FakeSocket(frames, sent)

        monkeypatch.setattr("websockets.connect", connect, raising=False)

        ws = PolymarketWebSocket()
        task = asyncio.create_task(ws.run(asset_ids=["abc", "def"]))
        await asyncio.sleep(0.2)
        task.cancel()
        with pytest.raises((asyncio.CancelledError, Exception)):
            await task

        assert ws.stats["assets_served"] == 1, "coverage is DISTINCT assets"

    @pytest.mark.asyncio
    async def test_one_shard_down_does_not_report_the_whole_consumer_dead(
        self, monkeypatch
    ):
        # `is_connected` feeds the liveness line that prints
        # "streaming"/"disconnected". With one connection it was a boolean the
        # single socket owned; with seven, every shard writing that one boolean
        # means the first to drop calls a working fan-out dead — and a
        # disconnected reading is exactly what somebody chasing #837 would act
        # on. Derived from the per-shard set instead, so it means what it says.
        sent: list[str] = []
        calls = {"n": 0}

        def connect(*args, **kwargs):
            calls["n"] += 1
            if calls["n"] == 2:
                raise ConnectionError("shard 1 is having a bad time")
            return _FakeSocket([], sent)

        monkeypatch.setattr("websockets.connect", connect, raising=False)

        assets = _ids(1500)
        ws = PolymarketWebSocket()
        task = asyncio.create_task(ws.run(asset_ids=assets))
        await asyncio.sleep(0.2)
        stats = ws.stats
        connected = ws.is_connected
        task.cancel()
        with pytest.raises((asyncio.CancelledError, Exception)):
            await task

        total = len(_shard_asset_ids(assets))
        assert total > 2, "sanity: this arm needs siblings to survive"
        assert stats["shards_connected"] == total - 1, (
            "exactly one shard should be down"
        )
        assert connected is True, (
            "siblings are streaming; the consumer is not disconnected"
        )

    def test_a_shard_that_just_reconnected_is_not_yet_a_coverage_subject(self):
        # Graded on seeded state rather than by sleeping, because the grace is
        # precisely the rule a timing-raced test pins without ever convicting.
        # A shard reconnects after a blip, the coverage tick lands one second
        # later, and it has had no chance to be served — reporting it starved
        # would be the instrument accusing the shard of the instrument's own
        # impatience.
        ws = PolymarketWebSocket()
        ws._shard_subscribed = {0: 500, 1: 500}
        ws._shard_served = {0: {"served"}, 1: set()}
        ws._shards_connected = {0, 1}
        ws._shard_connected_at = {0: 0.0, 1: 1_000.0}

        just_reconnected = 1_001.0
        assert ws._silent_shards(just_reconnected) == []

        settled = 1_000.0 + COVERAGE_GRACE_SECONDS
        assert ws._silent_shards(settled) == [1]

    def test_a_disconnected_shard_is_not_reported_as_starved(self):
        # A shard with no socket is a disconnect, already logged loudly. Calling
        # it a starved subscription would send the next reader hunting #837 in a
        # shard that simply is not connected.
        ws = PolymarketWebSocket()
        ws._shard_subscribed = {0: 500, 1: 500}
        ws._shard_served = {0: {"served"}, 1: set()}
        ws._shards_connected = {0}
        ws._shard_connected_at = {0: 0.0}

        assert ws._silent_shards(10_000.0) == []

    @pytest.mark.asyncio
    async def test_a_silent_shard_is_reported_when_its_siblings_stream(
        self, monkeypatch, caplog
    ):
        monkeypatch.setattr(
            "app.services.polymarket_ws.COVERAGE_GRACE_SECONDS", 0.05
        )
        sent: list[str] = []
        calls = {"n": 0}

        def connect(*args, **kwargs):
            calls["n"] += 1
            # Only the first shard is served anything. That is the signature of
            # the defect: same-sized subscribes, one connection streaming and
            # another getting nothing at all.
            frames = (
                [json.dumps({"event_type": "best_bid_ask", "asset_id": "served"})]
                if calls["n"] == 1
                else []
            )
            return _FakeSocket(frames, sent)

        monkeypatch.setattr("websockets.connect", connect, raising=False)

        ws = PolymarketWebSocket()
        with caplog.at_level(logging.WARNING, logger="app.services.polymarket_ws"):
            task = asyncio.create_task(ws.run(asset_ids=_ids(1500)))
            await asyncio.sleep(0.3)
            task.cancel()
            with pytest.raises((asyncio.CancelledError, Exception)):
                await task

        assert "served 0 distinct" in caplog.text, (
            "a starved shard beside streaming siblings must be said out loud — "
            "the only other symptom is a chart that does not move"
        )

    @pytest.mark.asyncio
    async def test_a_wholly_quiet_venue_is_not_reported_as_a_coverage_failure(
        self, monkeypatch, caplog
    ):
        # THE DISCRIMINATOR. Without this arm the warning could be "every
        # subscribed leg must emit", which fires all night on a quiet book and
        # teaches everyone to ignore it. Absence on its own proves nothing; the
        # signal is COMPARATIVE, so with no sibling streaming there is nothing
        # to report.
        monkeypatch.setattr(
            "app.services.polymarket_ws.COVERAGE_GRACE_SECONDS", 0.05
        )
        sent: list[str] = []

        def connect(*args, **kwargs):
            return _FakeSocket([], sent)

        monkeypatch.setattr("websockets.connect", connect, raising=False)

        ws = PolymarketWebSocket()
        with caplog.at_level(logging.WARNING, logger="app.services.polymarket_ws"):
            task = asyncio.create_task(ws.run(asset_ids=_ids(1500)))
            await asyncio.sleep(0.3)
            task.cancel()
            with pytest.raises((asyncio.CancelledError, Exception)):
                await task

        assert "served 0 distinct" not in caplog.text, (
            "a quiet venue is quiet for honest reasons and is not a finding"
        )

    @pytest.mark.asyncio
    async def test_stats_report_the_fan_out_shape(self, monkeypatch):
        sent: list[str] = []

        def connect(*args, **kwargs):
            return _FakeSocket([], sent)

        monkeypatch.setattr("websockets.connect", connect, raising=False)

        assets = _ids(1500)
        ws = PolymarketWebSocket()
        task = asyncio.create_task(ws.run(asset_ids=assets))
        await asyncio.sleep(0.2)
        stats = ws.stats
        task.cancel()
        with pytest.raises((asyncio.CancelledError, Exception)):
            await task

        assert stats["shards"] == len(_shard_asset_ids(assets))
        assert stats["assets_subscribed"] == len(assets)
        assert stats["shards_connected"] == stats["shards"]
