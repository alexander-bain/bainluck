"""#10663 — what the open-contract receiver child keeps resident, per socket.

The child holds ~136 sockets for a ~68k-token catalog. A rig at that size
(fake TLS venue, the production child and proxy, 10/22) traced ~101 MB of live
Python memory at steady state, and about half of it was waste:

* asyncio's TLS read buffer, 256 KiB per socket for the socket's life: 34 MiB;
* a second copy of every subscribed id in the raw wire sets, decoded inside the
  book dumps and so also keeping the dumps' freed memory in place: 7.9 MB;
* each socket's sent subscribe frame (~40 KB), held for the socket's life;
* per-shard fences built from generators (doubled tables), and rebuilt on
  every refresh even when unchanged.

(The refresh pass's catalog-sized sets, ~8 MB held through its wait, are NOT
released early: freed after the venue process's per-refresh trim, they read as
unreturned heap in #11218's handover control — CI lab, 10/22: end reclaimable
4.0 MB with them held, 8.3 MB released.)

Each test pins one of those, and the decode's keys-only string cache, by
behaviour. None of them changes what a socket subscribes to, receives,
forwards or counts.
"""

import asyncio
import json
import os
import subprocess
import sys
import textwrap
from collections import deque

import pytest
import websockets

from app.services import polymarket_ws as svc
from app.services import polymarket_ws_process as pwp

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROCESS_FILE = os.path.join(BACKEND, "app", "services", "polymarket_ws_process.py")


def _ids(n, seed=0):
    # Production-shaped ids: 77-digit strings, built at runtime so each is its
    # own object (never a compiler-shared constant).
    return [str(10**76 + seed * 100_000 + i) for i in range(n)]


class Socket:
    def __init__(self, frames):
        self.frames = deque(frames)
        self.sent = []
        self.quiet = asyncio.Event()
        self.task = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        pass

    async def send(self, value):
        self.sent.append(value)

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self.frames:
            return self.frames.popleft()
        self.quiet.set()
        await asyncio.Event().wait()

    def local(self, name):
        return self.task.get_coro().cr_frame.f_locals.get(name, "absent")

    async def stop(self):
        self.task.cancel()
        await asyncio.gather(self.task, return_exceptions=True)


def _book(asset_id):
    return {
        "event_type": "book", "asset_id": asset_id, "market": "0x" + "ab" * 32,
        "bids": [{"price": "0.40", "size": "20"}],
        "asks": [{"price": "0.60", "size": "30"}],
    }


def _change(asset_id):
    return {
        "event_type": "price_change", "market": "0x" + "cd" * 32, "timestamp": "1",
        "price_changes": [{"asset_id": asset_id, "price": "0.5", "size": "1",
                           "side": "BUY", "best_bid": "0.49", "best_ask": "0.51"}],
    }


async def _run(monkeypatch, subscribed, frames, **client):
    socket = Socket([json.dumps(f) for f in frames])
    monkeypatch.setattr(websockets, "connect", lambda *_a, **_kw: socket)
    consumer = svc.PolymarketWebSocket(**client)
    consumer.on_price = lambda _quote: None
    consumer._shard_ids[0] = list(subscribed)
    socket.task = asyncio.create_task(consumer._run_one(subscribed, 0))
    await asyncio.wait_for(socket.quiet.wait(), 5)
    return socket, consumer


def _member(collection, value):
    return next(item for item in collection if item == value)


@pytest.mark.asyncio
async def test_wire_set_keeps_the_subscriptions_own_id_strings(monkeypatch):
    subscribed = _ids(40)
    late, foreign = subscribed[-1], str(10**76 + 999_999)
    frames = [[_book(a) for a in subscribed[:-1]], _change(late), _change(foreign),
              _change(foreign), _change(subscribed[0])]
    socket, consumer = await _run(monkeypatch, subscribed, frames,
                                  price_book_snapshots=True)
    try:
        wire = consumer._shard_wire[0]
        # The same ids as before: every subscribed id seen, and the foreign one.
        assert wire == set(subscribed) | {foreign}
        # A dump's ids are held as the subscription's string objects, never
        # the decoded copies. A few new ids in a later frame cost no scan of
        # the subscription and are kept as decoded: equal strings either way.
        assert all(_member(wire, a) is a for a in subscribed[:-1])
        assert _member(wire, late) == late
        assert consumer.stats["assets_served"] == len(subscribed)
    finally:
        await socket.stop()


@pytest.mark.asyncio
async def test_wire_set_from_a_dump_is_sized_once(monkeypatch):
    subscribed = _ids(500)
    socket, consumer = await _run(monkeypatch, subscribed,
                                  [[_book(a) for a in subscribed]])
    try:
        reference = set()
        reference.update(set(subscribed))
        assert sys.getsizeof(consumer._shard_wire[0]) == sys.getsizeof(reference)
    finally:
        await socket.stop()


@pytest.mark.asyncio
async def test_the_socket_does_not_keep_its_sent_subscribe_frame(monkeypatch):
    subscribed = _ids(5)
    socket, _ = await _run(monkeypatch, subscribed, [[_book(a) for a in subscribed]])
    try:
        assert len(socket.sent) == 1
        assert json.loads(socket.sent[0])["assets_ids"] == subscribed
        # Streaming now: the frame went to the venue and is no longer bound.
        assert socket.local("frame") is None
    finally:
        await socket.stop()


class _Sockets:
    def __init__(self):
        self.subscribed: dict[int, tuple] = {}

    async def run_one(self, ids, index):
        self.subscribed[index] = tuple(ids)
        try:
            await asyncio.Event().wait()
        finally:
            self.subscribed.pop(index, None)


@pytest.mark.asyncio
async def test_shard_fences_are_sized_once(monkeypatch):
    ws, sockets = svc.PolymarketWebSocket(), _Sockets()
    ws._run_one = sockets.run_one
    catalog = _ids(500)
    task = asyncio.create_task(ws.run_refreshable(catalog))
    try:
        await asyncio.wait_for(_until(lambda: 0 in ws._shard_routed), 5)
        assert ws._shard_routed[0] == frozenset(catalog)
        assert sys.getsizeof(ws._shard_routed[0]) == sys.getsizeof(frozenset(set(catalog)))
        assert sys.getsizeof(ws._shard_routed[0]) < sys.getsizeof(frozenset(iter(catalog)))
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_an_unchanged_fence_is_kept_and_a_changed_one_rebuilt(monkeypatch):
    monkeypatch.setattr(svc, "MAX_ASSETS_PER_CONNECTION", 4)
    split = svc._shard_asset_ids
    monkeypatch.setattr(svc, "_shard_asset_ids", lambda ids: split(ids, max_assets=4))
    ws, sockets = svc.PolymarketWebSocket(), _Sockets()
    ws._run_one = sockets.run_one
    catalog = _ids(8)
    task = asyncio.create_task(ws.run_refreshable(catalog))
    try:
        await asyncio.wait_for(_until(lambda: len(ws._shard_routed) == 2), 5)
        before = dict(ws._shard_routed)
        # Shard 1 loses one token (stays >= half full, so it is kept, fenced);
        # shard 0 is untouched.
        ws.update_asset_ids(catalog[:7])
        await asyncio.wait_for(_until(lambda: not ws._asset_refresh.is_set()), 5)
        for _ in range(5):
            await asyncio.sleep(0)
        assert ws._shard_routed[0] is before[0]
        assert ws._shard_routed[1] == frozenset(catalog[4:7]) != before[1]
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


def test_fence_equality_matches_the_built_set():
    ids, latest = _ids(6), set(_ids(6)[1:5])
    built = frozenset(a for a in ids if a in latest)
    assert svc._fence_is(built, ids, latest)
    assert not svc._fence_is(built | {"x"}, ids, latest)
    assert not svc._fence_is(frozenset(list(built)[1:]), ids, latest)
    assert svc._fence_is(frozenset(), ids, set())


async def _until(predicate):
    while not predicate():
        await asyncio.sleep(0)


def test_decode_shares_key_strings_and_never_caches_values():
    raw = json.dumps([_book(a) for a in _ids(3)] + [{"bids": [
        {"price": "0.45", "size": "10"}, {"price": "0.45", "size": "10"}]}])
    for decode in (svc._decode_message, svc._decode_text_frame_bytes):
        data = decode(raw.encode() if decode is svc._decode_text_frame_bytes else raw)
        assert data == json.loads(raw)
        one, two = data[-1]["bids"]
        assert [k1 is k2 for k1, k2 in zip(one, two)] == [True, True]
        assert one["price"] is not two["price"]
        assert data[0]["asset_id"] is not data[1]["asset_id"]


def test_tls_read_buffer_bound_sizes_each_new_connection(monkeypatch):
    from asyncio import sslproto

    monkeypatch.setattr(sslproto.SSLProtocol, "max_size", sslproto.SSLProtocol.max_size)
    assert sslproto.SSLProtocol.max_size == 256 * 1024
    assert pwp.bound_tls_read_buffers() is True
    loop = asyncio.new_event_loop()
    try:
        import ssl

        proto = sslproto.SSLProtocol(
            loop, asyncio.Protocol(), ssl.create_default_context(), None,
            server_hostname="example.com",
        )
        assert len(proto._ssl_buffer) == pwp.TLS_READ_BUFFER_BYTES == 32 * 1024
        # A larger read request is clipped to the bound, never grown past it.
        assert len(proto.get_buffer(1 << 20)) == 32 * 1024
    finally:
        loop.close()


def test_a_missing_buffer_attribute_is_logged_and_never_stops_the_child(
    monkeypatch, caplog,
):
    from asyncio import sslproto

    monkeypatch.delattr(sslproto.SSLProtocol, "max_size")
    with caplog.at_level("ERROR"):
        assert pwp.bound_tls_read_buffers() is False
    assert not hasattr(sslproto.SSLProtocol, "max_size")
    assert "no max_size" in caplog.text


CHILD = textwrap.dedent(
    """
    import asyncio, importlib.util, sys
    from asyncio import sslproto
    spec = importlib.util.spec_from_file_location("pwp_child", sys.argv[1])
    pwp = importlib.util.module_from_spec(spec); spec.loader.exec_module(pwp)
    pwp.STATS_SECONDS = 0.02

    class FakeClient:
        def __init__(self, **config):
            self.on_price = self.on_trade = None
        @property
        def stats(self):
            return {"connected": True, "tls_max": sslproto.SSLProtocol.max_size}
        def update_asset_ids(self, ids, *, price_book_snapshots=None):
            pass
        async def run_refreshable(self, ids, *, price_book_snapshots=None):
            await asyncio.Event().wait()

    sys.exit(asyncio.run(pwp.serve_receiver(FakeClient)))
    """
)


@pytest.mark.asyncio
async def test_the_receiver_child_runs_with_the_bounded_tls_buffer():
    proxy = pwp.PolymarketOpenReceiverProcess(
        command=[sys.executable, "-c", CHILD, PROCESS_FILE],
    )
    proxy.on_price, proxy.on_trade = (lambda m: None), (lambda m: None)
    run = asyncio.create_task(proxy.run_refreshable(["a"]))
    try:
        await asyncio.wait_for(_until(lambda: "tls_max" in proxy.stats), 20)
        assert proxy.stats["tls_max"] == 32 * 1024
    finally:
        run.cancel()
        await asyncio.gather(run, return_exceptions=True)
    # This (parent) process is untouched: only the child's sockets are bound.
    from asyncio import sslproto
    assert sslproto.SSLProtocol.max_size == 256 * 1024


def test_the_child_entry_point_still_imports_nothing_from_the_app_packages():
    out = subprocess.run(
        [sys.executable, "-c",
         "import sys, importlib.util;"
         f"s=importlib.util.spec_from_file_location('p', {PROCESS_FILE!r});"
         "m=importlib.util.module_from_spec(s); s.loader.exec_module(m);"
         "m.bound_tls_read_buffers();"
         "print(sorted(n for n in sys.modules if n.startswith('app')))"],
        capture_output=True, text=True, check=True,
    )
    assert out.stdout.strip() == "[]"
