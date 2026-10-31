"""#10090: a repeated Polymarket top of book costs almost nothing on receipt.

Production 2026-10-31 01:05Z/01:23Z (v5990): receive was 40 % of the PM
loop, `_price_quotes` 23-26 % cumulative and `handle_price` 18-21 %, while
71-75 % of messages were repeats that `_skip_repeat` dropped only at the end.
"""

import pytest

from app.services import polymarket_ws as svc
from tests.test_pm_nested_bbo_10090 import FRAMES, drive


@pytest.mark.asyncio
async def test_a_price_change_frame_is_normalized_once_not_again_per_quote(monkeypatch):
    calls = []
    real = svc._price_change_entries

    def counted(message):
        calls.append(message)
        return real(message)

    monkeypatch.setattr(svc, "_price_change_entries", counted)
    observed, _ = await drive(monkeypatch, FRAMES[:1])
    assert len(observed) == len(FRAMES[0]["price_changes"]) == 2
    # The frame once, and the raw `best_bid_ask` sentinel once (it arrives
    # unvalidated) — never each quote the frame already produced.
    assert len(calls) == 2
    assert calls[0] is not None and calls[0].get("event_type") == "price_change"


# --- cut 2: a repeat is recognised before its quote is built -----------------

import asyncio  # noqa: E402
import logging  # noqa: E402

from tests.test_pm_repeat_skip_10090 import callbacks  # noqa: E402
from tests.test_pm_repeat_skip_parity_probe import _shape  # noqa: E402


def frame(ts, *legs):
    return {
        "event_type": "price_change",
        "market": "0xm",
        "timestamp": str(ts),
        "price_changes": [
            {"asset_id": a, "price": "0.5", "best_bid": b, "best_ask": k}
            for a, b, k in legs
        ],
    }


YES = ("yes", "0.60", "0.62")
NO = ("no", "0.38", "0.40")
MOVED = ("yes", "0.61", "0.63")


def consumer(monkeypatch, case, hook):
    r = callbacks(monkeypatch)
    r.confirmed = _shape(r, case)
    r.ns["asset_to_market"]["no"] = 10
    r.ns["asset_to_outcome"]["no"] = 2
    client = svc.PolymarketWebSocket()
    r.calls = []

    async def on_price(quote):
        r.calls.append(dict(quote))
        await r.ns["handle_price"](quote)

    client.on_price = on_price
    client.on_price_repeat = r.ns["handle_price_repeat"] if hook else None
    r.client = client
    r.versions = dict.fromkeys(["yes", "no"])
    return r


def state(r):
    ns = r.ns
    return (
        list(r.confirmed.notes), list(r.raws), ns["stats"]["repeats_skipped"],
        dict(ns["price_buffer"]), dict(ns["withdraw_buffer"]), dict(ns["books_by_asset"]),
        dict(ns["leg_writes"]),
        {k: (v[0], v[1], v[2], v[3], v[4], v[5]) for k, v in ns["repeat_memo"].items()},
        ns["catalog_boundary"].flush_wake.is_set(), dict(r.versions),
    )


def flush(r):
    r.ns["price_buffer"].clear()
    r.ns["withdraw_buffer"].clear()
    r.ns["catalog_boundary"].flush_wake.clear()


def tick(seconds):
    def step(r):
        r.clock.t += seconds
    return step


async def trade(r):
    await r.ns["handle_trade"](
        {"asset_id": "no", "timestamp": "1", "price": "0.41", "size": "10"}
    )


def reroute(r):
    r.ns["routing_generation"] += 1


def unmap(r):
    r.saved = r.ns["asset_to_market"].pop("yes")


def remap(r):
    r.ns["asset_to_market"]["yes"] = r.saved


SCRIPT = [
    frame(1, YES), flush, tick(0.05),
    frame(2, YES),               # a repeat
    frame(3, YES, NO),           # yes repeats; no is new and writes yes's legs
    tick(0.05),
    frame(4, YES, NO),           # each leg's write reopens the other: both handled
    flush,
    frame(5, NO), frame(6, NO),  # handled, then a repeat
    frame(7, YES),               # handled: no's write reopened it
    frame(8, ("yes", "0", "0")),  # moves the trade-side book, leaves the memo
    frame(9, YES),               # a repeat that puts the book back
    trade, frame(10, NO),        # a trade reopens the token
    frame(11, MOVED), tick(0.3), frame(12, MOVED),  # changed; then past W
    frame(13, MOVED),            # a repeat
    reroute, frame(14, MOVED),   # a routing generation reopens it
    unmap, frame(15, MOVED), remap,  # an unmapped token is never handled
    frame(16, ("yes", "0.1", "0.9")), flush,  # a wide book reopens it
    frame(17, MOVED), frame(18, MOVED),
    frame(18, MOVED), frame(17, MOVED),  # duplicate and older: dropped first
    tick(0.01), frame(19, MOVED, ("no", "0.37", "0.39")),
]


async def run(r):
    trail = []
    for step in SCRIPT:
        if isinstance(step, dict):
            await r.client._price_changes(step, None, r.versions, subscribed_only=True)
        else:
            result = step(r)
            if asyncio.iscoroutine(result):
                await result
        trail.append(state(r))
    return trail


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["slate", "non_blend", "bridged"])
async def test_the_receipt_skip_leaves_exactly_the_state_handle_prices_skip_leaves(
    monkeypatch, case
):
    # Built and run one after the other: each rig patches the clock to its own.
    on = consumer(monkeypatch, case, hook=True)
    trail_on = await run(on)
    off = consumer(monkeypatch, case, hook=False)
    trail_off = await run(off)
    for i, (a, b) in enumerate(zip(trail_on, trail_off)):
        assert a == b, (i, SCRIPT[i])
    skipped = on.ns["stats"]["repeats_skipped"]
    assert skipped == off.ns["stats"]["repeats_skipped"] >= 5
    # The step after the terminal book was one of them, and it moved the
    # trade-side book back (`handle_trade` reads it).
    at = SCRIPT.index(frame(9, YES))
    assert trail_on[at][2] == trail_on[at - 1][2] + 1
    assert trail_on[at][5]["yes"] == ((0.60, 0.62), (0.0, 0.0))
    # Every skip happened at receipt: no quote, no coroutine, no handle_price.
    assert len(off.calls) - len(on.calls) == skipped
    # Whatever did reach `on_price` is today's quote, byte for byte.
    assert all(q in off.calls for q in on.calls)


@pytest.mark.asyncio
async def test_a_binary_pairs_second_leg_is_judged_after_the_first_is_handled(monkeypatch):
    r = consumer(monkeypatch, "slate", hook=True)
    await r.client._price_changes(frame(1, NO), None, r.versions, subscribed_only=True)
    flush(r)
    r.clock.t += 0.05
    # yes is new and writes the complement leg 2, so the remembered `no`
    # book no longer stands: a pre-pass over the frame would skip it.
    await r.client._price_changes(frame(2, YES, NO), None, r.versions, subscribed_only=True)
    assert [q["asset_id"] for q in r.calls] == ["no", "yes", "no"]
    assert r.ns["stats"]["repeats_skipped"] == 0


def client_with(hook, on_price):
    client = svc.PolymarketWebSocket()
    client.on_price = on_price
    client.on_price_repeat = hook
    return client


@pytest.mark.asyncio
async def test_a_settled_repeat_stores_its_identity_and_never_reaches_on_price():
    seen, asked = [], []

    def hook(asset, bid, ask):
        asked.append((asset, bid, ask))
        return True

    client = client_with(hook, seen.append)
    versions = dict.fromkeys(["yes"])
    await client._price_changes(frame(5, YES), None, versions, subscribed_only=True)
    assert seen == [] and asked == [("yes", 0.60, 0.62)]
    assert versions["yes"] == (5, 0.60, 0.62)
    # Its duplicate and anything older are refused before the hook, as before.
    await client._price_changes(frame(5, YES), None, versions, subscribed_only=True)
    await client._price_changes(frame(4, YES), None, versions, subscribed_only=True)
    assert len(asked) == 1


@pytest.mark.asyncio
async def test_a_leg_the_hook_declines_reaches_on_price_as_todays_quote():
    seen = []
    client = client_with(lambda *_: False, seen.append)
    message = frame(5, YES, NO)
    await client._price_changes(
        message, None, dict.fromkeys(["yes", "no"]), subscribed_only=True
    )
    assert seen == svc._price_change_quotes(message)


@pytest.mark.asyncio
async def test_an_unrouted_or_unsubscribed_leg_never_reaches_the_hook():
    asked = []
    client = client_with(lambda a, *_: asked.append(a) or True, lambda q: None)
    client._shard_routed[0] = frozenset({"no"})
    await client._price_changes(
        frame(5, YES, NO, ("other", "0.1", "0.2")), 0,
        dict.fromkeys(["yes", "no"]), subscribed_only=True,
    )
    assert asked == ["no"]


@pytest.mark.asyncio
async def test_a_failing_hook_hides_no_sibling_and_leaves_the_leg_retryable(caplog):
    seen = []

    def hook(asset, *_):
        if asset == "yes":
            raise RuntimeError("boom")
        return False

    client = client_with(hook, seen.append)
    versions = dict.fromkeys(["yes", "no"])
    with caplog.at_level(logging.ERROR):
        await client._price_changes(frame(5, YES, NO), None, versions, subscribed_only=True)
    assert [q["asset_id"] for q in seen] == ["no"]
    assert versions["yes"] is None
    assert "Polymarket price handler error" in caplog.text


@pytest.mark.asyncio
async def test_a_raw_best_bid_ask_frame_never_consults_the_hook(monkeypatch):
    asked = []
    observed, client = await drive(monkeypatch, [])
    client.on_price_repeat = lambda *a: asked.append(a) or True
    await client._price_quotes(
        [{"event_type": "best_bid_ask", "asset_id": "yes", "timestamp": "5",
          "best_bid": "0.6", "best_ask": "0.62"}],
        None, book_snapshot=False, quote_versions=dict.fromkeys(["yes"]),
    )
    assert asked == []


@pytest.mark.asyncio
async def test_the_skip_switch_off_installs_no_hook():
    import re
    from pathlib import Path

    source = (Path(svc.__file__).parents[1] / "tasks/polymarket_ws.py").read_text()
    lines = re.findall(r"(\w+)\.on_price_repeat = \(?\s*handle_price_repeat if repeat_skip_s > 0 else None", source)
    assert sorted(lines) == ["open_ws", "ws"]
