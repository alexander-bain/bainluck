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
ids in one ~255 KiB frame and re-dealing it six times an hour, well inside the
degraded band. A 176-minute MNF game produced a single 15.5-minute band of
prices; the measurement proves this transport was defective during that game,
not that it was the sole cause of that particular hole.

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
    UNSERVED_SAMPLE_PER_SHARD,
    PolymarketWebSocket,
    _evenly_spaced,
    _frame_overheads,
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


class TestTheSizingArithmeticIsExactAtEveryIdLength:
    """The ceiling is breached only in a WINDOW of id lengths, and the rest of
    this class sat inside that window's blind spot.

    The first version of `_shard_asset_ids` charged one byte per separator;
    `json.dumps` writes `", "`, two bytes. Codex caught it on the frozen sha by
    executing the committed functions: 1,100 ids of 78 characters planned frames
    of 41066 / 41066 / 8266 bytes against a 40960 ceiling, and at 90 characters
    41332 / 41332 / 20934.

    Why the sizing tests above missed a one-byte-per-id error for a whole
    session — the part worth keeping:

      * at their fixture length of 76, the ASSET cap binds first (500 ids is
        ~40066 bytes), so the byte arithmetic never decides anything;
      * at length 400 the byte cap binds, but only ~101 ids fit a shard, so the
        undercount totals ~100 bytes and disappears into the rounding slack.

    The error is proportional to ids-per-shard, so it only surfaces where the
    BYTE cap binds AND shards stay large — roughly 78-90 characters. Real ids
    are 74-78 today (live/512). The defect was one character of id drift away
    from production, and a fixture at a single length cannot see it. So this
    sweeps the length axis instead of sampling it.
    """

    #: Spans both regimes: count-bound (small), the window the defect lived in
    #: (77-92), and byte-bound with few ids per shard (large).
    LENGTHS = [1, 8, 20, 40, 60, 74, 76, 77, 78, 80, 84, 88, 90, 92, 120, 200, 400, 900]

    def test_the_real_frame_fits_the_ceiling_at_every_id_length(self):
        for length in self.LENGTHS:
            for shard in _shard_asset_ids(_ids(1100, length=length)):
                frame = len(_subscribe_frame(shard).encode("utf-8"))
                assert frame <= MAX_SUBSCRIBE_BYTES, (
                    f"ids of {length} chars plan a {frame}-byte frame, over the "
                    f"{MAX_SUBSCRIBE_BYTES} ceiling — the venue accepts this and "
                    "serves only part of it, which is #837 all over again"
                )

    def test_no_id_is_lost_at_any_id_length(self):
        # The ceiling can always be met by dropping ids. Pin the two properties
        # together or the arm above is satisfiable the wrong way.
        for length in self.LENGTHS:
            assets = _ids(1100, length=length)
            flattened = [a for shard in _shard_asset_ids(assets) for a in shard]
            assert flattened == assets, f"ids of {length} chars lost or reordered"

    def test_codex_exact_populations_now_fit(self):
        """The two populations from the finding, by the numbers it reported."""
        for length, was in ((78, 41066), (90, 41332)):
            frames = [
                len(_subscribe_frame(s).encode("utf-8"))
                for s in _shard_asset_ids(_ids(1100, length=length))
            ]
            assert max(frames) <= MAX_SUBSCRIBE_BYTES, (length, frames)
            assert was > MAX_SUBSCRIBE_BYTES, "the reported breach must be a breach"

    def test_the_one_byte_separator_this_replaced_really_did_breach(self):
        """STRAWMAN — without it every arm above passes on arithmetic that was
        never wrong, and a `+1` could be reintroduced tomorrow unnoticed.

        Reproduces the old planner exactly and asserts it breaks the ceiling in
        the window, so the sweep is proven to be looking where the defect lives.
        """
        envelope, _ = _frame_overheads()

        def old_planner(assets):
            shards, current, current_bytes = [], [], 0
            for asset_id in assets:
                cost = len(json.dumps(asset_id).encode("utf-8")) + 1  # the bug
                if current and (
                    len(current) + 1 > MAX_ASSETS_PER_CONNECTION
                    or envelope + current_bytes + cost > MAX_SUBSCRIBE_BYTES
                ):
                    shards.append(current)
                    current, current_bytes = [], 0
                current.append(asset_id)
                current_bytes += cost
            if current:
                shards.append(current)
            return shards

        breached = {
            length: max(
                len(_subscribe_frame(s).encode("utf-8"))
                for s in old_planner(_ids(1100, length=length))
            )
            for length in self.LENGTHS
        }
        over = {k: v for k, v in breached.items() if v > MAX_SUBSCRIBE_BYTES}
        assert over, (
            "the strawman did not reproduce the breach at any length — this "
            "guard is vacuous and would not notice the bug coming back"
        )
        assert 78 in over and 90 in over, (
            f"the finding's own two lengths must breach under the old "
            f"arithmetic; breached: {over}"
        )

    def test_the_separator_width_is_derived_from_json_not_assumed(self):
        """The repair's actual mechanism. If someone hardcodes the separator
        again, this is the arm that says so."""
        _, separator = _frame_overheads()
        measured = (
            len(json.dumps(["x", "x"]).encode("utf-8"))
            - len(json.dumps(["x"]).encode("utf-8"))
            - len(json.dumps("x").encode("utf-8"))
        )
        assert separator == measured
        assert separator == 2, (
            "json.dumps defaults to ', ' — if this is 1, the serializer changed "
            "and the sizing above needs re-measuring, not re-assuming"
        )

    def test_the_boundary_guard_fires_when_the_arithmetic_drifts(self, monkeypatch):
        """The boundary guard, driven by the exact drift it exists to catch.

        With correct arithmetic a multi-id shard can never exceed the ceiling —
        the planner only adds a second id after the byte check passes — so the
        guard is unreachable through the public path by construction. That is
        the point of a boundary guard, and it also means the only honest way to
        test it is to reintroduce the fault.

        So: put the one-byte separator back and confirm the planner now REFUSES
        rather than handing the venue a frame it would silently half-serve. A
        venue-side sizing bug produces missing prices, never an error, so the
        loud failure is the whole value.
        """
        envelope, _ = _frame_overheads()
        monkeypatch.setattr(
            "app.services.polymarket_ws._frame_overheads", lambda: (envelope, 1)
        )
        with pytest.raises(RuntimeError, match="over the 40960-byte ceiling"):
            _shard_asset_ids(_ids(1100, length=78))

    def test_the_boundary_guard_exempts_a_lone_id_that_cannot_fit(self):
        """...but never at the cost of dropping one: a single id too large for
        the bound still rides alone rather than raising or vanishing."""
        huge = "x" * (MAX_SUBSCRIBE_BYTES * 2)
        assert _shard_asset_ids([huge]) == [[huge]]


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
        ws._shard_ids = {0: _ids(500), 1: _ids(500)}
        ws._shard_wire = {0: {"served"}, 1: set()}
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
        ws._shard_ids = {0: _ids(500), 1: _ids(500)}
        ws._shard_wire = {0: {"served"}, 1: set()}
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


class TestTheCoverageNumberReachesAReader:
    """#837 — the served count is EMITTED, not merely computed.

    The fan-out counts, on the wire, how many distinct assets each shard was
    actually served. Nothing read it: `assets_served` and `served_by_shard`
    appeared in `PolymarketWebSocket.stats` and in no log line, no liveness
    field and no endpoint, so across 236 KB of captured production logs the
    number occurred zero times. A silently-served fraction was therefore still
    unmeasurable from production — the exact condition #837 exists to end.

    The sibling coverage WARNING does not close this: it fires only when a
    shard serves LITERALLY ZERO while another streams. A shard served 3 assets
    of 500 is the same defect, and is silent under that rule. Only the ratio
    shows it, so the ratio is stated unconditionally.
    """

    def _blend(self):
        return {"stamped": 1, "no_reading": 2, "throttled": 3, "errors": 0}

    def _task_stats(self):
        return {
            "price_updates": 10,
            "trade_updates": 4,
            "resolutions": 0,
            "errors": 0,
        }

    def test_the_served_ratio_is_in_the_line(self, caplog):
        from app.tasks.polymarket_ws import _log_stats_line

        ws_stats = {
            "messages": 99,
            "shards": 8,
            "shards_connected": 8,
            "assets_subscribed": 3961,
            "assets_served": 1204,
        }
        with caplog.at_level(logging.INFO):
            _log_stats_line(self._task_stats(), ws_stats, self._blend())

        assert "served=1204/3961" in caplog.text
        assert "shards=8/8" in caplog.text

    def test_the_fraction_the_warning_cannot_see_is_visible_here(self, caplog):
        """3 of 500 on a live shard: silent to `_coverage_loop`, loud here."""
        from app.tasks.polymarket_ws import _log_stats_line

        ws_stats = {
            "messages": 5,
            "shards": 8,
            "shards_connected": 8,
            "assets_subscribed": 4000,
            "assets_served": 3,
        }
        with caplog.at_level(logging.INFO):
            _log_stats_line(self._task_stats(), ws_stats, self._blend())

        assert "served=3/4000" in caplog.text

    def test_a_client_with_no_shards_prints_zero_rather_than_raising(self, caplog):
        """The shadow consumer subscribes without shards and shares this line.

        An exception in the stats loop kills the socket's only heartbeat, so
        absent keys must degrade to 0.
        """
        from app.tasks.polymarket_ws import _log_stats_line

        with caplog.at_level(logging.INFO):
            _log_stats_line(self._task_stats(), {}, self._blend())

        assert "served=0/0" in caplog.text

    @pytest.mark.asyncio
    async def test_the_real_clients_numbers_are_what_gets_logged(
        self, monkeypatch, caplog
    ):
        """Ties the two halves: the client's OWN stats, not a hand-built dict.

        A test that only feeds a literal dict to the formatter would pass even
        if the client stopped exposing the keys, which is half the defect.
        """
        from app.tasks.polymarket_ws import _log_stats_line

        served_frames = [
            json.dumps({"event_type": "best_bid_ask", "asset_id": a})
            for a in _ids(1500)[:7]
        ]

        def connect(*args, **kwargs):
            return _FakeSocket(served_frames, [])

        monkeypatch.setattr("websockets.connect", connect, raising=False)

        assets = _ids(1500)
        ws = PolymarketWebSocket()
        task = asyncio.create_task(ws.run(asset_ids=assets))
        await asyncio.sleep(0.3)
        stats = ws.stats
        task.cancel()
        with pytest.raises((asyncio.CancelledError, Exception)):
            await task

        with caplog.at_level(logging.INFO):
            _log_stats_line(self._task_stats(), stats, self._blend())

        assert f"served={stats['assets_served']}/{len(assets)}" in caplog.text
        assert stats["assets_served"] > 0, (
            "the fake socket served assets, so the client must have counted them"
        )


class TestThePerShardShapeReachesTheMinuteLine:
    """#837 follow-up — the SHAPE at reader cadence, not only at the recycle.

    `served_by_shard` and `subscribed_by_shard` have been in
    `PolymarketWebSocket.stats` since the coverage emit, and reached a reader
    only in the ten-minute recycle line. The once-a-minute line carried the
    aggregate alone, which is the number this program has twice recorded as
    "measured breadth, not a finding": 49% served reads identically whether the
    venue is quiet everywhere or is truncating half the subscription.

    live/521 measured the consequence on 2026-09-23 at 01:1xZ — eight live MLB
    games written at 1 of ~79 outcomes in 150s while Phillies/Brewers sat at 50
    of 79 in the same instant — and had to reconstruct the per-shard
    denominators from a separate capture to see it. The pairs cost one field.
    """

    def _blend(self):
        return {"stamped": 1, "no_reading": 2, "throttled": 3, "errors": 0}

    def _task_stats(self):
        return {
            "price_updates": 10,
            "trade_updates": 4,
            "resolutions": 0,
            "errors": 0,
        }

    #: The production read, verbatim: four shards starved, four streaming.
    STARVED = {0: 14, 1: 26, 2: 36, 3: 39, 4: 492, 5: 500, 6: 500, 7: 230}
    #: Same 1837 assets served, spread evenly — a quiet venue, nothing wrong.
    UNIFORM = {0: 230, 1: 230, 2: 230, 3: 230, 4: 230, 5: 229, 6: 229, 7: 229}
    SUBSCRIBED = {0: 500, 1: 500, 2: 500, 3: 500, 4: 500, 5: 500, 6: 500, 7: 293}

    def _ws_stats(self, served):
        return {
            "messages": 99,
            "shards": 8,
            "shards_connected": 8,
            "assets_subscribed": sum(self.SUBSCRIBED.values()),
            "assets_served": sum(served.values()),
            "served_by_shard": dict(served),
            "subscribed_by_shard": dict(self.SUBSCRIBED),
        }

    def test_the_production_shape_reaches_the_minute_line(self, caplog):
        from app.tasks.polymarket_ws import _log_stats_line

        with caplog.at_level(logging.INFO):
            _log_stats_line(
                self._task_stats(), self._ws_stats(self.STARVED), self._blend()
            )

        assert "by_shard=0:14/500 1:26/500 2:36/500 3:39/500 " \
               "4:492/500 5:500/500 6:500/500 7:230/293" in caplog.text

    def test_one_aggregate_two_shapes_produce_two_different_lines(self, caplog):
        """The whole reason the field exists, stated as a discriminator.

        Both populations serve 1837 of 3793. If the emitted line cannot tell
        them apart then the field is decoration: a reader seeing 49% still
        cannot say whether to call the venue. Asserting only that some
        `by_shard=` text appears would pass on a constant.
        """
        from app.tasks.polymarket_ws import _log_stats_line

        with caplog.at_level(logging.INFO):
            _log_stats_line(
                self._task_stats(), self._ws_stats(self.STARVED), self._blend()
            )
        starved_line = caplog.text
        caplog.clear()

        with caplog.at_level(logging.INFO):
            _log_stats_line(
                self._task_stats(), self._ws_stats(self.UNIFORM), self._blend()
            )
        uniform_line = caplog.text

        aggregate = "served=1837/3793"
        assert aggregate in starved_line and aggregate in uniform_line, (
            "the two populations must be indistinguishable in the aggregate, "
            "or this test is not testing what it claims"
        )
        assert starved_line != uniform_line
        assert "0:14/500" in starved_line and "0:14/500" not in uniform_line
        assert "0:230/500" in uniform_line and "0:230/500" not in starved_line

    def test_the_denominator_is_each_shards_own_subscription(self, caplog):
        """Shard 7 is the remainder, 293 not 500.

        A formatter that printed `MAX_ASSETS_PER_CONNECTION`, or the aggregate
        divided by the shard count, would read 230/500 here and understate the
        one shard whose share is hardest to judge.
        """
        from app.tasks.polymarket_ws import _log_stats_line

        with caplog.at_level(logging.INFO):
            _log_stats_line(
                self._task_stats(), self._ws_stats(self.STARVED), self._blend()
            )

        assert "7:230/293" in caplog.text
        assert "7:230/500" not in caplog.text

    def test_a_client_with_no_shards_prints_a_dash_rather_than_raising(
        self, caplog
    ):
        """The shadow consumer subscribes without shards and shares this line.

        An exception in the stats loop kills the socket's only heartbeat, and a
        field that vanishes when empty is a field no grep can rely on.
        """
        from app.tasks.polymarket_ws import _log_stats_line

        with caplog.at_level(logging.INFO):
            _log_stats_line(self._task_stats(), {}, self._blend())

        assert "by_shard=-" in caplog.text
        assert "served=0/0" in caplog.text

    def test_shard_keys_are_ordered_numerically_not_as_text(self):
        """Ten shards sort 2 before 10, including after a JSON round trip."""
        from app.tasks.polymarket_ws import _format_by_shard

        served = {i: i for i in range(11)}
        subscribed = {i: 500 for i in range(11)}
        as_ints = _format_by_shard(
            {"served_by_shard": served, "subscribed_by_shard": subscribed}
        )
        as_text = _format_by_shard(
            {
                "served_by_shard": {str(k): v for k, v in served.items()},
                "subscribed_by_shard": {str(k): v for k, v in subscribed.items()},
            }
        )

        assert as_ints == as_text
        assert as_ints.split()[2].startswith("2:")
        assert as_ints.split()[-1].startswith("10:")

    def test_a_shard_missing_from_one_half_still_prints_both(self):
        """Never a KeyError, and never a pair that silently drops a shard."""
        from app.tasks.polymarket_ws import _format_by_shard

        line = _format_by_shard(
            {"served_by_shard": {0: 5}, "subscribed_by_shard": {1: 500}}
        )

        assert line == "0:5/0 1:0/500"

    @pytest.mark.asyncio
    async def test_the_real_clients_per_shard_numbers_are_what_gets_logged(
        self, monkeypatch, caplog
    ):
        """Ties the two halves: the client's OWN stats, not a hand-built dict.

        A test that only feeds literal dicts to the formatter would pass even if
        the client stopped exposing `subscribed_by_shard`, which is the half
        that makes a served count readable as a share.
        """
        from app.tasks.polymarket_ws import _log_stats_line

        assets = _ids(1500)
        served_frames = [
            json.dumps({"event_type": "best_bid_ask", "asset_id": a})
            for a in assets[:7]
        ]

        def connect(*args, **kwargs):
            return _FakeSocket(served_frames, [])

        monkeypatch.setattr("websockets.connect", connect, raising=False)

        ws = PolymarketWebSocket()
        task = asyncio.create_task(ws.run(asset_ids=assets))
        await asyncio.sleep(0.3)
        stats = ws.stats
        task.cancel()
        with pytest.raises((asyncio.CancelledError, Exception)):
            await task

        with caplog.at_level(logging.INFO):
            _log_stats_line(self._task_stats(), stats, self._blend())

        assert stats["subscribed_by_shard"], (
            "the client must expose per-shard denominators for the line to "
            "have anything to print"
        )
        for shard, subscribed in stats["subscribed_by_shard"].items():
            served = stats["served_by_shard"].get(shard, 0)
            assert f"{shard}:{served}/{subscribed}" in caplog.text


class TestTheUnservedIdsAreNamed:
    """#837 follow-up — WHICH ids the venue never sent, not just how many.

    The first production read of the coverage ratio came back `served=1832/3738`
    (49%), broken down per shard as {0:14, 1:26, 2:36, 3:39, 4:492, 5:500,
    6:500, 7:230}. That is measured BREADTH and it is not a finding, because
    `assets_served` counts assets that sent at least one message: a book nobody
    traded and a subscription the venue truncated produce the identical number.

    Worse, the bimodality has an innocent explanation that must be ruled out
    before it is reported as a venue defect. `_shard_asset_ids` slices the
    caller's list CONTIGUOUSLY, and that list is built by a query with no
    `ORDER BY` — heap order, which tracks insertion order, which tracks market
    age. "Shards 0-3 are old long-tail futures and 4-7 are today's slate" fits
    the numbers with nothing wrong at the venue at all.

    The database cannot settle it: `handle_price` skips untradeable books
    through early returns that increment no counter, so quiet and starved are
    indistinguishable there too. Only the wire separates them, and only if the
    ids are named — they exist in memory at the recycle and were discarded.

    So what is pinned here is that the ids come out, that they are the right
    ones, and that they are sampled in a way that does not select on the very
    variable under test.
    """

    def _client(self, shard_ids, served):
        ws = PolymarketWebSocket()
        ws._shard_ids = dict(shard_ids)
        ws._shard_wire = {i: set(s) for i, s in served.items()}
        return ws

    def test_the_sample_names_ids_that_were_subscribed_and_never_served(self):
        ids = _ids(10)
        ws = self._client({0: ids}, {0: {ids[0], ids[1]}})

        sample = ws.unserved_sample(limit=4)

        assert set(sample[0]).isdisjoint({ids[0], ids[1]}), (
            "a served id in the unserved sample sends the next reader to ask "
            "the venue about a book it demonstrably did serve"
        )
        assert set(sample[0]) <= set(ids[2:])

    def test_a_fully_served_shard_is_omitted_rather_than_reported_empty(self):
        ids = _ids(4)
        ws = self._client({0: ids, 1: ids}, {0: set(ids), 1: set()})

        sample = ws.unserved_sample()

        assert 0 not in sample, "a healthy shard does not need a line"
        assert sample[1] == ids, "the starved shard is still named in full"

    def test_the_sample_is_spread_across_the_shard_not_taken_off_its_head(self):
        """The mutation this exists to kill is `unserved[:limit]`.

        Caller order tracks market age, so the first few ids of a shard are its
        oldest corner. A sample drawn from there and found uniformly quiet
        would be reported as "this shard is starved" when all it showed was
        that old long-tail futures do not trade — the exact confound that stops
        49% from being a finding.
        """
        ids = _ids(100)
        ws = self._client({0: ids}, {0: set()})

        sample = ws.unserved_sample(limit=5)[0]

        assert len(sample) == 5
        assert sample[0] == ids[0] and sample[-1] == ids[-1], (
            "a spread sample reaches both ends of the shard"
        )
        assert len(set(sample)) == 5, "spacing must not pick the same id twice"
        positions = [ids.index(a) for a in sample]
        assert positions == sorted(positions)
        assert max(positions) > len(ids) // 2, (
            "a head-only slice ([:limit]) never reaches past the midpoint — "
            "that is the selection bias this assertion convicts"
        )

    def test_a_short_unserved_list_is_reported_whole(self):
        ids = _ids(3)
        ws = self._client({0: ids}, {0: set()})

        assert ws.unserved_sample(limit=UNSERVED_SAMPLE_PER_SHARD)[0] == ids

    def test_evenly_spaced_handles_the_degenerate_limits(self):
        assert _evenly_spaced([], 5) == []
        assert _evenly_spaced(_ids(5), 0) == []
        assert _evenly_spaced(_ids(5), -1) == []
        assert _evenly_spaced(_ids(9), 1) == [_ids(9)[4]]

    def test_the_counts_are_exact_on_both_halves(self):
        ws = self._client(
            {0: _ids(10), 1: _ids(4)},
            {0: set(_ids(10)[:3]), 1: set()},
        )

        stats = ws.stats

        assert stats["subscribed_by_shard"] == {0: 10, 1: 4}
        assert stats["unserved_by_shard"] == {0: 7, 1: 4}
        assert stats["assets_subscribed"] == 14

    def test_a_frame_for_an_id_we_never_asked_for_does_not_credit_the_shard(self):
        """Coverage is measured against the SUBSCRIPTION, not against traffic.

        The venue may send an id that is not in this shard's subscribe. Counted
        as coverage, it would shrink the unserved set without a single
        subscribed book having been served — the instrument reporting progress
        made by somebody else's traffic.
        """
        ids = _ids(5)
        ws = self._client({0: ids}, {0: {"an-id-we-never-subscribed"}})

        assert ws.stats["unserved_by_shard"] == {0: 5}
        assert ws.unserved_sample()[0] == ids

    def test_the_sample_reaches_a_reader(self, caplog):
        """#837's own lesson: a number that is computed and never emitted is
        not measurable from production. `assets_served` sat in `stats` and in
        no log line for the whole of that ship."""
        from app.tasks.polymarket_ws import _log_unserved_sample

        ids = _ids(6)
        ws = self._client({0: ids}, {0: {ids[0]}})

        with caplog.at_level(logging.INFO):
            _log_unserved_sample(ws)

        assert "unserved sample (#837)" in caplog.text
        assert ids[-1] in caplog.text, "the ids themselves must be in the line"

    def test_nothing_is_logged_when_every_subscribed_id_was_served(self, caplog):
        from app.tasks.polymarket_ws import _log_unserved_sample

        ids = _ids(6)
        ws = self._client({0: ids}, {0: set(ids)})

        with caplog.at_level(logging.INFO):
            _log_unserved_sample(ws)

        assert "unserved sample" not in caplog.text

    def test_a_raising_client_does_not_take_the_recycle_down(self, caplog):
        """This runs in the resubscribe path. A diagnostic that can crash the
        consumer costs the socket to save a log line."""
        from app.tasks.polymarket_ws import _log_unserved_sample

        class _Broken:
            def unserved_sample(self, *a, **k):
                raise RuntimeError("boom")

        with caplog.at_level(logging.ERROR):
            _log_unserved_sample(_Broken())

        assert "unserved sample failed" in caplog.text

    @pytest.mark.asyncio
    async def test_the_real_client_excludes_what_the_socket_actually_served(
        self, monkeypatch
    ):
        """Ties it to the wire rather than to seeded state: a hand-set
        `_shard_wire` would pass even if `run` stopped recording ids."""
        assets = _ids(1500)
        served_ids = assets[:7]
        frames = [
            json.dumps({"event_type": "best_bid_ask", "asset_id": a})
            for a in served_ids
        ]

        def connect(*args, **kwargs):
            return _FakeSocket(frames, [])

        monkeypatch.setattr("websockets.connect", connect, raising=False)

        ws = PolymarketWebSocket()
        task = asyncio.create_task(ws.run(asset_ids=assets))
        await asyncio.sleep(0.3)
        stats = ws.stats
        sample = ws.unserved_sample()
        task.cancel()
        with pytest.raises((asyncio.CancelledError, Exception)):
            await task

        assert stats["assets_served"] > 0, "sanity: the fake socket served ids"
        # THE OVER-COUNT, END TO END, through `run` rather than seeded state.
        # Every shard here shares one fake socket, so all three connections
        # receive frames for shard 0's seven ids: 21 id-arrivals on the wire for
        # 7 subscribed ids actually served. `assets_served` summed those 21 —
        # two shards credited with a sibling's traffic — while the denominator
        # beside it counted only what each shard asked for. The wire total is
        # still reported, under a name that says it is the wire.
        assert stats["assets_served"] == len(served_ids), (
            "a shard is credited only for ids IT subscribed to; 21 was the bug"
        )
        assert stats["assets_on_wire"] == len(served_ids) * stats["shards"], (
            "the sibling arrivals are not lost, they are named as wire traffic"
        )
        assert sum(stats["unserved_by_shard"].values()) == len(assets) - len(
            served_ids
        ), "subscribed minus served must account for every id, losing none"
        flat = [a for picks in sample.values() for a in picks]
        assert flat, "1500 ids and 7 served: there is plenty unserved to name"
        assert set(flat).isdisjoint(set(served_ids))


class TestCoverageCountsOnePopulation:
    """#837 — `served/subscribed` must not put the wire over the subscription.

    THE DEFECT. `_shard_wire` is filled from the wire, above every filter, and
    that is correct: it is receipt. But the coverage ratio read it as the
    numerator against the SUBSCRIPTION as the denominator, and those are two
    different populations — the venue sends ids nobody asked for. Measured on
    production either side of the v4953 release, shard 2 served MORE than it
    subscribed to, `2:394/375` and then `2:498/479`, an excess of exactly 19
    both times.

    WHY THAT MATTERS MORE THAN THE 105%. A ratio over 100% is absurd on its
    face and gets noticed. The damage is the readings that stayed plausible:
    98.3% and 97.8% coverage were reported as measurements when they were upper
    bounds, because shards 0 and 1 may carry foreign ids too and theirs read as
    coverage rather than as excess, having never crossed their own denominator.
    An instrument built to answer "is the venue serving the whole subscription"
    was answering it too generously, in the one direction that hides the defect
    it exists to find.

    So the property pinned here is that the numerator is drawn from the
    denominator's own population, and its companion: nothing is thrown away to
    achieve that. `_silent_shards` still asks the raw wire whether a socket
    received anything at all, which is a question about the connection and not
    about coverage, and the excess itself is reported rather than discarded.
    """

    #: The production read this class exists because of.
    SUBSCRIBED = 375
    FOREIGN = 19

    def _client(self, subscribed, wire):
        ws = PolymarketWebSocket()
        ws._shard_ids = {i: list(ids) for i, ids in subscribed.items()}
        ws._shard_wire = {i: set(s) for i, s in wire.items()}
        return ws

    def test_an_id_the_shard_never_subscribed_to_does_not_raise_its_served_count(
        self,
    ):
        ids = _ids(10)
        foreign = ["not-ours-1", "not-ours-2"]
        ws = self._client({0: ids}, {0: set(ids[:3]) | set(foreign)})

        assert ws.stats["served_by_shard"][0] == 3, (
            "five ids arrived, three of them were ours; coverage counts ours"
        )

    def test_the_production_specimen_stops_reading_over_its_own_denominator(self):
        # `2:394/375`, reproduced. The venue served the whole subscription AND
        # 19 ids outside it, so the honest reading is 375/375 and not 394/375.
        ids = _ids(self.SUBSCRIBED)
        foreign = [f"foreign-{i}" for i in range(self.FOREIGN)]
        ws = self._client({2: ids}, {2: set(ids) | set(foreign)})

        stats = ws.stats
        assert stats["served_by_shard"][2] == self.SUBSCRIBED
        assert stats["served_by_shard"][2] <= stats["subscribed_by_shard"][2], (
            "a shard cannot be served more of its subscription than it has"
        )
        assert stats["served_by_shard"][2] != self.SUBSCRIBED + self.FOREIGN, (
            "394 was the number the old counter printed against a 375 denominator"
        )

    def test_served_and_unserved_partition_the_subscription(self):
        # The invariant the old counter could not satisfy, and the reason this
        # is a partition rather than two independent counts: with a foreign id
        # in the wire set the two halves summed to MORE than the denominator
        # they were both reported beside, so a reader subtracting one from the
        # other got a different answer than a reader adding them.
        ids = _ids(40)
        foreign = [f"foreign-{i}" for i in range(7)]
        ws = self._client(
            {0: ids[:25], 1: ids[25:]},
            {0: set(ids[:10]) | set(foreign), 1: set(ids[25:30]) | set(foreign)},
        )

        stats = ws.stats
        for shard in (0, 1):
            assert (
                stats["served_by_shard"][shard]
                + stats["unserved_by_shard"][shard]
                == stats["subscribed_by_shard"][shard]
            ), f"shard {shard}: served + unserved must be the subscription"

    def test_the_ids_the_venue_sent_unasked_are_reported_not_discarded(self):
        # Narrowing the numerator at the READ and not at the write is what
        # keeps this readable: with served capped at subscribed, `375/375` looks
        # identical whether the wire carried 375 ids or 394, so the excess would
        # become invisible at the exact moment it stopped being counted as
        # coverage. That would trade one silent number for another.
        ids = _ids(self.SUBSCRIBED)
        foreign = [f"foreign-{i}" for i in range(self.FOREIGN)]
        ws = self._client({2: ids}, {2: set(ids) | set(foreign)})

        stats = ws.stats
        assert stats["on_wire_by_shard"][2] == self.SUBSCRIBED + self.FOREIGN
        assert (
            stats["on_wire_by_shard"][2] - stats["served_by_shard"][2]
            == self.FOREIGN
        ), "the excess is still a number a reader can get to"

    def test_a_shard_sent_only_ids_it_never_asked_for_is_not_called_silent(self):
        # THE DISCRIMINATOR for the half that did NOT move. `_silent_shards`
        # asks whether a connection received anything at all — a socket being
        # answered, even with ids outside its subscription, has plainly not gone
        # quiet, and reporting it as a starved subscription would be a false
        # positive in the instrument this whole change is graded on. Scoring
        # silence on the intersection would have introduced exactly that.
        ws = self._client({0: _ids(500), 1: _ids(500)}, {0: {"not-ours"}, 1: set()})
        ws._shards_connected = {0, 1}
        ws._shard_connected_at = {0: 0.0, 1: 0.0}

        settled = COVERAGE_GRACE_SECONDS + 1.0
        assert ws._silent_shards(settled) == [1], (
            "shard 0 received a frame; only shard 1 was told nothing at all"
        )
        assert ws.stats["served_by_shard"][0] == 0, (
            "and it is still zero COVERAGE — the two questions differ, which is "
            "the whole reason both sets are kept"
        )

    @pytest.mark.asyncio
    async def test_the_excess_reaches_the_minute_line_and_not_only_the_stats_dict(
        self, monkeypatch, caplog
    ):
        # THE OTHER HALF, and the one this file has already been burned by:
        # `served_by_shard` sat in `stats` and in no log line for long enough
        # that a silently-served fraction was unmeasurable from production. The
        # same trap is open here. Narrowing `served` to the subscription means
        # the ratio can no longer print 105%, so if the wire total were computed
        # and never emitted, the excess would simply stop existing for every
        # reader — a number fixed into invisibility is not a number fixed.
        #
        # Real client, not a hand-built dict, so this also fails if the client
        # stops exposing the key. All three shards share one fake socket and are
        # sent shard 0's seven ids, so the wire carries 21 arrivals for 7 served.
        from app.tasks.polymarket_ws import _log_stats_line

        assets = _ids(1500)
        served_ids = assets[:7]
        frames = [
            json.dumps({"event_type": "best_bid_ask", "asset_id": a})
            for a in served_ids
        ]

        def connect(*args, **kwargs):
            return _FakeSocket(frames, [])

        monkeypatch.setattr("websockets.connect", connect, raising=False)

        ws = PolymarketWebSocket()
        task = asyncio.create_task(ws.run(asset_ids=assets))
        await asyncio.sleep(0.3)
        stats = ws.stats
        task.cancel()
        with pytest.raises((asyncio.CancelledError, Exception)):
            await task

        blend = {"stamped": 1, "no_reading": 2, "throttled": 3, "errors": 0}
        task_stats = {
            "price_updates": 0, "trade_updates": 0, "resolutions": 0, "errors": 0,
        }
        with caplog.at_level(logging.INFO):
            _log_stats_line(task_stats, stats, blend)

        assert f"served={len(served_ids)}/{len(assets)}" in caplog.text
        assert f"wire={len(served_ids) * stats['shards']}" in caplog.text, (
            "the ids the venue sent unasked must still be readable from a log"
        )

    def test_an_absent_wire_key_prints_a_zero_rather_than_killing_the_heartbeat(
        self, caplog
    ):
        # The shadow consumer shares this line and subscribes without shards, so
        # every coverage key can be missing. An exception in the stats loop takes
        # the socket's only heartbeat with it.
        from app.tasks.polymarket_ws import _log_stats_line

        blend = {"stamped": 0, "no_reading": 0, "throttled": 0, "errors": 0}
        task_stats = {
            "price_updates": 0, "trade_updates": 0, "resolutions": 0, "errors": 0,
        }
        with caplog.at_level(logging.INFO):
            _log_stats_line(task_stats, {}, blend)

        assert "wire=0" in caplog.text
