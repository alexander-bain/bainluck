"""Fresh selected-market observations in captured price_change packets reach DNPL."""

import asyncio
import copy
import json
from pathlib import Path

import pytest
import websockets

from app.services import polymarket_ws as svc

FRAMES = json.loads(
    (Path(__file__).parent / "fixtures/pm_nested_bbo_10090.json").read_text()
)
TOKENS = [q["asset_id"] for q in FRAMES[0]["price_changes"]]


async def drive(monkeypatch, frames, tokens=TOKENS):
    observed = []
    done = asyncio.Event()
    sentinel = {
        "event_type": "best_bid_ask",
        "asset_id": tokens[0],
        "best_bid": ".2",
        "best_ask": ".3",
        "sentinel": True,
    }

    async def peer(sock):
        await sock.recv()
        for frame in [*frames, sentinel]:
            await sock.send(json.dumps(frame))
        await sock.wait_closed()

    async with websockets.serve(peer, "127.0.0.1", 0) as server:
        monkeypatch.setattr(
            svc, "WS_URL", f"ws://127.0.0.1:{server.sockets[0].getsockname()[1]}"
        )
        client = svc.PolymarketWebSocket()

        def price(quote):
            if quote.get("sentinel"):
                done.set()
            else:
                observed.append(quote)

        client.on_price = price
        task = asyncio.create_task(client.run(asset_ids=tokens))
        try:
            await asyncio.wait_for(done.wait(), 5)
            return observed, client
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_retained_73_packets_deliver_140_distinct_observations(monkeypatch):
    observed, client = await drive(monkeypatch, FRAMES)
    expected = [
        (q["asset_id"], q["best_bid"], q["best_ask"], f["timestamp"])
        for f in FRAMES
        for q in f["price_changes"]
    ]
    # Three exact repeated envelopes contribute six duplicate token identities.
    expected = list(dict.fromkeys(expected))
    assert len(observed) == 140
    assert [
        (q["asset_id"], q["best_bid"], q["best_ask"], q["timestamp"]) for q in observed
    ] == expected
    assert all(q["market"] == FRAMES[0]["market"] for q in observed)
    assert all(q["event_type"] == "best_bid_ask" for q in observed)
    assert client._book_snapshot_quotes == 0


@pytest.mark.asyncio
async def test_unsubscribed_nested_token_never_reaches_handler(monkeypatch):
    observed, _ = await drive(monkeypatch, FRAMES[:1], TOKENS[:1])
    assert [q["asset_id"] for q in observed] == TOKENS[:1]


@pytest.mark.parametrize(
    "field,value",
    [
        ("best_bid", None),
        ("best_ask", ""),
        ("best_bid", "nan"),
        ("best_ask", "inf"),
        ("best_bid", True),
        ("best_bid", "0.9"),
        ("best_bid", "-0.1"),
        ("best_ask", "1.1"),
        ("asset_id", ""),
    ],
)
def test_malformed_leg_does_not_hide_healthy_sibling(field, value):
    frame = copy.deepcopy(FRAMES[0])
    frame["price_changes"][0][field] = value
    quotes = svc._price_change_quotes(frame)
    assert [q["asset_id"] for q in quotes] == TOKENS[1:]


@pytest.mark.parametrize("timestamp", [None, "", "nan", "inf", True, "-1", "0", "1.5"])
def test_no_timestamp_means_no_manufactured_observation(timestamp):
    frame = copy.deepcopy(FRAMES[0])
    frame["timestamp"] = timestamp
    assert svc._price_change_quotes(frame) == []


def test_depth_price_is_not_used_and_wide_quote_reaches_existing_refusal():
    frame = copy.deepcopy(FRAMES[0])
    frame["price_changes"][0].update(price="0.8", best_bid="0.01", best_ask="0.99")
    q = svc._price_change_quotes(frame)[0]
    assert (q["best_bid"], q["best_ask"]) == ("0.01", "0.99")
    assert "price" not in q


@pytest.mark.asyncio
async def test_route_fence_rechecked_after_first_callback():
    client = svc.PolymarketWebSocket()
    client._shard_routed[0] = frozenset(TOKENS)
    observed = []

    async def price(q):
        observed.append(q)
        client._shard_routed[0] = frozenset()
        await asyncio.sleep(0)

    client.on_price = price
    await client._price_quotes(
        svc._price_change_quotes(FRAMES[0]), 0, book_snapshot=False
    )
    assert len(observed) == 1


@pytest.mark.asyncio
async def test_cross_shape_duplicate_new_time_reversal_and_old_order(monkeypatch):
    frame = copy.deepcopy(FRAMES[0])
    q = frame["price_changes"][0]
    top = {
        "event_type": "best_bid_ask",
        "market": frame["market"],
        "timestamp": frame["timestamp"],
        **q,
    }
    newer = copy.deepcopy(frame)
    newer["timestamp"] = str(int(frame["timestamp"]) + 1)
    changed = copy.deepcopy(newer)
    changed["price_changes"][0]["best_bid"] = "0.51"
    # Duplicate top/nested is one observation; a fresh equal BBO passes.
    # Equal-time A→B→A passes; the older packet cannot roll the bound back.
    observed, _ = await drive(
        monkeypatch, [top, frame, newer, changed, newer, frame], TOKENS[:1]
    )
    assert [(x["timestamp"], x["best_bid"]) for x in observed] == [
        (frame["timestamp"], q["best_bid"]),
        (newer["timestamp"], q["best_bid"]),
        (newer["timestamp"], "0.51"),
        (newer["timestamp"], q["best_bid"]),
    ]


@pytest.mark.asyncio
async def test_callback_failure_leaves_duplicate_retryable_and_sibling_delivered():
    client = svc.PolymarketWebSocket()
    observed = []
    calls = 0
    versions = dict.fromkeys(TOKENS)

    async def price(q):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("failed before accepting")
        observed.append(q["asset_id"])

    client.on_price = price
    quotes = svc._price_change_quotes(FRAMES[0])
    await client._price_quotes(
        quotes, None, book_snapshot=False, quote_versions=versions
    )
    await client._price_quotes(
        quotes, None, book_snapshot=False, quote_versions=versions
    )
    assert observed == [TOKENS[1], TOKENS[0]]


@pytest.mark.asyncio
async def test_new_connection_quote_state_accepts_same_source_observation():
    client = svc.PolymarketWebSocket()
    observed = []
    client.on_price = observed.append
    quotes = svc._price_change_quotes(FRAMES[0])
    for _ in range(2):
        await client._price_quotes(
            quotes, None, book_snapshot=False, quote_versions=dict.fromkeys(TOKENS)
        )
    assert len(observed) == 4
