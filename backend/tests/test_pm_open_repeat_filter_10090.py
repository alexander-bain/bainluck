"""#10090 CPU: the open-contract child drops the quotes the consumer would skip.

A quote that repeats the last top of book the child forwarded for its token,
inside the consumer's repeat window, changes nothing a reader sees (the
consumer's `_skip_repeat` feeds only "confirmed at" for it). It cost the
consumer a pickle, a pipe read, a dispatch, a loop turn and its handler: on
production 11/01 ~07:00Z the open path was 24% of the Polymarket consumer's
CPU at 0.93 of a core. The child now drops it before the pipe.
"""

import asyncio
import sys
import textwrap

import pytest

from app.services import polymarket_ws_process as pwp
from tests.test_pm_open_receiver_process_10090 import PROCESS_FILE


class Clock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


def quote(asset="a", bid="0.40", ask="0.42", **extra):
    return {"event_type": "best_bid_ask", "asset_id": asset, "best_bid": bid,
            "best_ask": ask, **extra}


def test_a_repeat_inside_the_window_is_dropped_and_one_after_it_goes():
    clock = Clock()
    f = pwp.RepeatFilter(0.25, clock)
    assert f.forward(quote())
    clock.now += 0.1
    assert not f.forward(quote(timestamp="2"))
    clock.now += 0.1
    assert not f.forward(quote(timestamp="3"))
    # The window runs from the last FORWARDED quote, as the consumer's runs
    # from the last book it handled.
    clock.now += 0.06
    assert f.forward(quote(timestamp="4"))
    assert f.filtered == 2


def test_a_changed_book_goes_and_becomes_the_reference():
    clock = Clock()
    f = pwp.RepeatFilter(0.25, clock)
    assert f.forward(quote())
    assert f.forward(quote(ask="0.43"))
    assert not f.forward(quote(ask="0.43"))
    assert f.forward(quote())  # back to the first book: a change again
    assert f.forward(quote(asset="b"))  # tokens are independent


def test_a_snapshot_always_goes_and_starts_its_token_over():
    clock = Clock()
    f = pwp.RepeatFilter(0.25, clock)
    assert f.forward(quote())
    assert f.forward(quote(book_snapshot=True))
    assert f.forward(quote())  # the snapshot forgot the reference


@pytest.mark.parametrize("message", [
    quote(bid=None), quote(ask=None), {"asset_id": "a"}, ["a"], None,
    {"event_type": "best_bid_ask", "best_bid": "0.4", "best_ask": "0.42"},
])
def test_anything_but_a_two_sided_quote_goes_untouched(message):
    f = pwp.RepeatFilter(0.25, Clock())
    assert f.forward(message) and f.forward(message)
    assert f.filtered == 0


def test_a_zero_window_forwards_everything():
    f = pwp.RepeatFilter(0.0, Clock())
    assert all(f.forward(quote()) for _ in range(3))


def test_stale_books_are_forgotten_so_memory_follows_the_active_tokens():
    clock = Clock()
    f = pwp.RepeatFilter(0.25, clock)
    for i in range(100):
        f.forward(quote(asset=str(i)))
    clock.now += pwp.REPEAT_FILTER_PRUNE_S
    f.forward(quote(asset="fresh"))
    assert set(f._sent) == {"fresh"}


@pytest.mark.parametrize("environ, window", [
    ({}, 0.25),
    ({"PM_WS_REPEAT_SKIP_MS": "500"}, 0.5),
    ({"PM_WS_REPEAT_SKIP_MS": "500", "PM_OPEN_REPEAT_FILTER_MS": "100"}, 0.1),
    ({"PM_OPEN_REPEAT_FILTER_MS": "0"}, 0.0),
    ({"PM_WS_REPEAT_SKIP_MS": "0"}, 0.0),
    ({"PM_WS_REPEAT_SKIP_MS": "-5"}, 0.0),
    ({"PM_WS_REPEAT_SKIP_MS": "soon"}, 0.0),
    ({"PM_WS_REPEAT_SKIP_MS": "  "}, 0.25),
])
def test_the_window_follows_the_consumers_repeat_setting(environ, window):
    assert pwp.repeat_filter_window_s(environ) == pytest.approx(window)


DRIVER = textwrap.dedent(
    """
    import asyncio, importlib.util, sys
    spec = importlib.util.spec_from_file_location("pwp_child", sys.argv[1])
    pwp = importlib.util.module_from_spec(spec); spec.loader.exec_module(pwp)
    pwp.STATS_SECONDS = 0.05

    def q(seq, ask="0.42", **extra):
        return {"asset_id": "a", "best_bid": "0.40", "best_ask": ask, "seq": seq, **extra}

    class FakeClient:
        def __init__(self, **config):
            self.on_price = self.on_trade = None
        @property
        def stats(self):
            return {"connected": True}
        def update_asset_ids(self, ids, *, price_book_snapshots=None):
            pass
        async def run_refreshable(self, ids, *, price_book_snapshots=None):
            await self.on_price(q(0))
            for seq in (1, 2, 3):           # repeats inside the window
                await self.on_price(q(seq))
            await self.on_trade({"asset_id": "a", "seq": 4})
            await self.on_price(q(5, ask="0.43"))           # a change
            await self.on_price(q(6, ask="0.43", book_snapshot=True))
            await self.on_price({"asset_id": "a", "seq": 7})  # one-sided
            await self.on_price({"asset_id": "a", "seq": 8})
            await asyncio.Event().wait()

    sys.exit(asyncio.run(pwp.serve_receiver(FakeClient)))
    """
)


@pytest.mark.asyncio
async def test_a_real_child_forwards_only_what_the_consumer_would_handle(monkeypatch):
    monkeypatch.delenv("PM_OPEN_REPEAT_FILTER_MS", raising=False)
    monkeypatch.setenv("PM_WS_REPEAT_SKIP_MS", "60000")  # a slow machine stays inside it
    proxy = pwp.PolymarketOpenReceiverProcess(
        max_concurrent_handshakes=1, max_queue=1, price_book_snapshots=True,
        command=[sys.executable, "-c", DRIVER, PROCESS_FILE],
    )
    seen = []

    async def on_price(msg):
        seen.append(("p", msg["seq"]))

    async def on_trade(msg):
        seen.append(("t", msg["seq"]))

    proxy.on_price, proxy.on_trade = on_price, on_trade
    run = asyncio.create_task(proxy.run_refreshable(["a"]))
    try:
        for _ in range(500):
            if len(seen) >= 6 and proxy.stats.get("repeats_filtered") == 3:
                break
            await asyncio.sleep(0.01)
        assert seen == [("p", 0), ("t", 4), ("p", 5), ("p", 6), ("p", 7), ("p", 8)]
        assert proxy.stats["repeats_filtered"] == 3
    finally:
        run.cancel()
        await asyncio.gather(run, return_exceptions=True)
