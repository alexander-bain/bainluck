"""#10090 — the open fleet's subscribe-snapshot quotes are paced in the child.

## the ship

A live game's probability keeps reaching readers within a second while the
worker restores its open catalog: the ~66k open snapshot quotes no longer land
on the consumer's loop (and in its price buffer) faster than the open rows can
be written.

## what is held fixed

Live prices and trades are forwarded at once. Per token, and across one venue
market's legs, the consumer sees the exact order the client produced: a live
frame first releases that market's pending snapshot quotes, in arrival order.
A newer snapshot replaces a pending one. ``0`` restores the unpaced path.
"""

import asyncio
import os
import sys

import pytest

from app.services import polymarket_ws_process as pwp


def _snap(token, market, bid, ask="0.6"):
    return {"event_type": "best_bid_ask", "asset_id": token, "market": market,
            "best_bid": bid, "best_ask": ask, "book_snapshot": True}


def _live(token, market, bid, ask="0.6"):
    return {"event_type": "best_bid_ask", "asset_id": token, "market": market,
            "best_bid": bid, "best_ask": ask}


def _trade(token, market, price):
    return {"event_type": "last_trade_price", "asset_id": token, "market": market,
            "price": price}


class _Rig:
    def __init__(self, rate=10.0):
        self.out, self.sleeps, self.drains = [], [], 0
        self.gate = asyncio.Event()

        async def drain():
            self.drains += 1

        async def sleep(seconds):
            self.sleeps.append(seconds)
            await self.gate.wait()
            self.gate.clear()

        self.pacer = pwp.SnapshotPacer(
            lambda kind, message: self.out.append((kind, message.get("asset_id"),
                                                   message.get("best_bid") or message.get("price"))),
            drain, rate, sleep=sleep,
        )


async def _turns(n=5):
    for _ in range(n):
        await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_live_frames_pass_at_once_and_snapshots_wait_for_the_pacer():
    rig = _Rig()
    await rig.pacer.price(_snap("a", "m1", "0.40"))
    await rig.pacer.price(_live("x", "m9", "0.10"))
    await rig.pacer.trade(_trade("y", "m8", "0.20"))
    assert rig.out == [("p", "x", "0.10"), ("t", "y", "0.20")]
    assert rig.pacer.pending == 1


@pytest.mark.asyncio
async def test_the_pacer_releases_a_whole_market_then_sleeps_its_share_of_the_rate():
    rig = _Rig(rate=4.0)
    for token, market, bid in (("a", "m1", "0.40"), ("b", "m1", "0.41"),
                               ("c", "m2", "0.50"), ("d", "m3", "0.60")):
        await rig.pacer.price(_snap(token, market, bid))
    runner = asyncio.create_task(rig.pacer.run())
    try:
        await _turns()
        assert rig.out == [("p", "a", "0.40"), ("p", "b", "0.41")]
        assert rig.sleeps == [0.5]  # 2 quotes at 4/s
        rig.gate.set()
        await _turns()
        assert rig.out[2:] == [("p", "c", "0.50")]
        assert rig.sleeps == [0.5, 0.25]
        rig.gate.set()
        await _turns()
        assert rig.out[3:] == [("p", "d", "0.60")]
        assert rig.pacer.pending == 0 and rig.pacer.released == 4
    finally:
        runner.cancel()
        await asyncio.gather(runner, return_exceptions=True)


@pytest.mark.asyncio
async def test_a_live_frame_first_releases_its_markets_pending_snapshots_in_arrival_order():
    """The No token's snapshot came first; a live Yes tick must not overtake it,
    or the No snapshot would re-price the Yes leg's complement with an older book."""
    rig = _Rig()
    await rig.pacer.price(_snap("no", "m1", "0.55"))
    await rig.pacer.price(_snap("other", "m2", "0.30"))
    await rig.pacer.price(_snap("yes", "m1", "0.44"))
    await rig.pacer.price(_live("yes", "m1", "0.47"))
    assert rig.out == [("p", "no", "0.55"), ("p", "yes", "0.44"), ("p", "yes", "0.47")]
    assert rig.pacer.pending == 1  # m2 still paced


@pytest.mark.asyncio
async def test_a_trade_releases_the_book_it_is_read_against_first():
    rig = _Rig()
    await rig.pacer.price(_snap("a", "m1", "0.40"))
    await rig.pacer.trade(_trade("a", "m1", "0.41"))
    assert rig.out == [("p", "a", "0.40"), ("t", "a", "0.41")]


@pytest.mark.asyncio
async def test_a_newer_snapshot_replaces_the_pending_one_and_keeps_its_place():
    rig = _Rig()
    await rig.pacer.price(_snap("a", "m1", "0.40"))
    await rig.pacer.price(_snap("b", "m2", "0.50"))
    await rig.pacer.price(_snap("a", "m1", "0.42"))
    runner = asyncio.create_task(rig.pacer.run())
    try:
        await _turns()
        assert rig.out == [("p", "a", "0.42")]
        rig.gate.set()
        await _turns()
        assert rig.out == [("p", "a", "0.42"), ("p", "b", "0.50")]
        assert rig.pacer.released == 2
    finally:
        runner.cancel()
        await asyncio.gather(runner, return_exceptions=True)


@pytest.mark.asyncio
async def test_a_quote_with_no_market_is_its_own_group():
    rig = _Rig()
    await rig.pacer.price({**_snap("a", None, "0.40")})
    await rig.pacer.price({**_snap("b", None, "0.50")})
    await rig.pacer.price(_live("a", None, "0.41"))
    assert rig.out == [("p", "a", "0.40"), ("p", "a", "0.41")]
    assert rig.pacer.pending == 1


def test_the_rate_reads_its_undo_flag(monkeypatch):
    monkeypatch.delenv("POLYMARKET_WS_OPEN_SNAPSHOT_QUOTES_PER_SECOND", raising=False)
    assert pwp.open_snapshot_quotes_per_second() == pwp.OPEN_SNAPSHOT_QUOTES_PER_SECOND == 250.0
    for raw, want in (("0", 0.0), ("-3", 0.0), ("inf", 0.0), ("80", 80.0), ("junk", 250.0)):
        monkeypatch.setenv("POLYMARKET_WS_OPEN_SNAPSHOT_QUOTES_PER_SECOND", raw)
        assert pwp.open_snapshot_quotes_per_second() == want, raw


BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROCESS_FILE = os.path.join(BACKEND, "app", "services", "polymarket_ws_process.py")
DRIVER = """
import asyncio, importlib.util, sys
spec = importlib.util.spec_from_file_location("pwp_child", sys.argv[1])
pwp = importlib.util.module_from_spec(spec); spec.loader.exec_module(pwp)
N = int(sys.argv[2])

class FakeClient:
    def __init__(self, **config):
        self.on_price = self.on_trade = None
    @property
    def stats(self):
        return {"connected": True}
    def update_asset_ids(self, ids, *, price_book_snapshots=None):
        pass
    async def run_refreshable(self, ids, *, price_book_snapshots=None):
        # one subscribe dump: N snapshot quotes, two tokens per market ...
        for i in range(N):
            await self.on_price({"asset_id": f"t{i}", "market": f"m{i // 2}",
                                 "best_bid": "0.4", "best_ask": "0.5", "book_snapshot": True})
        # ... then a live tick on the LAST market's first token
        await self.on_price({"asset_id": f"t{N - 2}", "market": f"m{(N - 2) // 2}",
                             "best_bid": "0.45", "best_ask": "0.5"})
        await asyncio.Event().wait()

sys.exit(asyncio.run(pwp.serve_receiver(FakeClient)))
"""


@pytest.mark.asyncio
@pytest.mark.parametrize("rate", ["0", "200"])
async def test_through_a_real_child_every_snapshot_arrives_once_and_the_live_tick_never_waits(
    rate, monkeypatch,
):
    """Rate 0 is today's path: the dump, in order, then the tick. Paced, the
    tick's own market is released with it and every other snapshot follows at
    <= the rate; nothing is dropped or duplicated."""
    monkeypatch.setenv("POLYMARKET_WS_OPEN_SNAPSHOT_QUOTES_PER_SECOND", rate)
    n = 200
    proxy = pwp.PolymarketOpenReceiverProcess(
        max_concurrent_handshakes=1, max_queue=4, price_book_snapshots=True,
        command=[sys.executable, "-c", DRIVER, PROCESS_FILE, str(n)],
    )
    seen = []
    loop = asyncio.get_running_loop()
    proxy.on_price = lambda msg: seen.append((loop.time(), msg["asset_id"], msg.get("book_snapshot", False)))
    proxy.on_trade = lambda msg: None
    run = asyncio.create_task(proxy.run_refreshable([f"t{i}" for i in range(n)]))
    try:
        for _ in range(600):
            if len(seen) == n + 1:
                break
            await asyncio.sleep(0.01)
        snaps = [token for _, token, snap in seen if snap]
        lives = [(i, token) for i, (_, token, snap) in enumerate(seen) if not snap]
        assert sorted(snaps) == sorted(f"t{i}" for i in range(n)) and len(snaps) == n
        assert len(lives) == 1 and lives[0][1] == f"t{n - 2}"
        live_at = lives[0][0]
        # its market's two snapshots arrive before it, in arrival order
        before = [token for _, token, snap in seen[:live_at] if snap]
        assert before[-2:] == [f"t{n - 2}", f"t{n - 1}"]
        if rate == "0":
            assert [token for _, token, _ in seen] == [f"t{i}" for i in range(n)] + [f"t{n - 2}"]
        else:
            # the live tick is not held behind the paced dump ...
            assert live_at < n // 2, live_at
            # ... and the dump is spread at no more than the rate (+ one burst)
            span = seen[-1][0] - seen[0][0]
            assert span >= (n - 4) / float(rate) * 0.8, span
    finally:
        run.cancel()
        await asyncio.gather(run, return_exceptions=True)
