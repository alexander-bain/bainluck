"""Validated same-BBO input can advance observation without price-write debt."""
import json
import asyncio
import ast
from copy import deepcopy
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock

import pytest

from app.services.kalshi_ws import KalshiWebSocket, _KalshiCallbackDispatch
from app.utils.kalshi_orderbook import KalshiOrderBook
from tests.test_fresh_observation_preview_10090 import preview_enabled


def retained():
    return json.loads((Path(__file__).parent / "fixtures/kalshi_unchanged_book_tail_10090.json").read_text())


async def test_retained_tail_reaches_observation_callback_without_price_callback():
    fixture = retained()
    sock = KalshiWebSocket()
    sock._book = KalshiOrderBook()
    sock.book_tickers = frozenset(f["msg"]["market_ticker"] for f in fixture["seed"])
    for frame in fixture["seed"]:
        sock._book.apply(frame)
    sock._request_resnapshots = AsyncMock()
    prices, observed = [], []
    sock.on_ticker = prices.append
    sock.on_book_observation = observed.append
    async with _KalshiCallbackDispatch() as dispatch:
        for frame in fixture["tail"]:
            await sock._handle_book_frame(None, frame, dispatch)
    assert not prices
    assert len(observed) == len(fixture["tail"]) == 20
    assert {row["yes_bid_dollars"] for row in observed} == {"0.4700", "0.5300"}
    assert all("price_dollars" not in row for row in observed)


@pytest.mark.parametrize("case", ["disabled", "duplicate", "late", "gap", "missing", "negative", "crossed", "malformed"])
def test_invalid_or_unopted_book_does_not_mint_an_observation(case):
    fixture = retained()
    book = KalshiOrderBook()
    if case != "missing":
        for frame in fixture["seed"]:
            book.apply(frame)
    frame = deepcopy(fixture["tail"][0])
    if case == "duplicate":
        frame["seq"] -= 1
    elif case == "late":
        frame["seq"] -= 2
    elif case == "gap":
        frame["seq"] += 1
    elif case == "negative":
        frame["msg"]["delta_fp"] = "-100000000"
    elif case == "crossed":
        frame["msg"].update(price_dollars=".99", delta_fp="1", side="yes")
    elif case == "malformed":
        frame["msg"]["delta_fp"] = "NaN"
    assert book.apply(frame, observe_unchanged=case != "disabled") is None


def test_new_subscription_needs_its_own_snapshot_before_observing():
    fixture = retained()
    book = KalshiOrderBook()
    for frame in fixture["seed"]:
        book.apply(frame)
    delta = deepcopy(fixture["tail"][0])
    delta.update(sid=99, seq=1)
    delta["msg"]["delta_fp"] = "1"
    assert book.apply(delta, observe_unchanged=True) is None
    delta["seq"] = 2
    assert book.apply(delta, observe_unchanged=True) is None
    ticker = delta["msg"]["market_ticker"]
    seed = deepcopy(next(f for f in fixture["seed"] if f["msg"]["market_ticker"] == ticker))
    seed.update(sid=99, seq=3)
    book.apply(seed, observe_unchanged=True)
    delta["seq"] = 4
    assert book.apply(delta, observe_unchanged=True)["_observation_only"] is True


def test_shared_subscription_gap_revokes_both_books_observation_proof():
    fixture = retained()
    book = KalshiOrderBook()
    for frame in fixture["seed"]:
        book.apply(frame)
    delta = deepcopy(fixture["tail"][0])
    delta["seq"] += 1
    assert book.apply(delta, observe_unchanged=True) is None
    delta["seq"] += 1
    delta["msg"]["market_ticker"] = fixture["tail"][1]["msg"]["market_ticker"]
    assert book.apply(delta, observe_unchanged=True) is None


async def test_observation_is_dropped_behind_same_event_lifecycle():
    gate = asyncio.Event()
    entered = asyncio.Event()
    seen = []

    async def prepare(payload):
        async def settle(_):
            entered.set()
            await gate.wait()
        return settle

    async with _KalshiCallbackDispatch() as dispatch:
        payload = {"market_ticker": retained()["seed"][0]["msg"]["market_ticker"]}
        await dispatch.submit(None, payload, "lifecycle", lifecycle=True, prepare=prepare)
        await entered.wait()
        await dispatch.submit(seen.append, payload, "observation", discard_if_delayed=True)
        gate.set()
    assert not seen


def consumer_rig(monkeypatch):
    import app.tasks.kalshi_ws as consumer
    from tests.test_kalshi_unchanged_observation_preview_10090 import kalshi_rig
    from app.tasks.live_blend_refresh import TailReceipts
    from app.tasks.kalshi import _kalshi_yes_probability
    r, session, frames, committed, rows, reading, _, _, now = kalshi_rig(monkeypatch)
    r.preview_events = {1}
    bound = (now - timedelta(seconds=1)).timestamp()
    held = NS(_database_bound=bound, sample_database_clock=AsyncMock())
    r.held_quotes = held
    r._admission = NS(released={})
    tickers = {row.id: f"KXATPMATCH-26OCT21PAIR-{row.id}" for row in rows}
    midpoint = {tickers[row.id]: Decimal(str(row.current_probability)) for row in rows}
    client = NS(sock=NS(current_book_midpoint=midpoint.get))
    signatures = {t: object() for t in tickers.values()}
    prices = NS(settled_market_ids=set(), stamping=None, flush_work=0,
                held_events=lambda _: set())
    ns = dict(asyncio=asyncio, ticker_to_ids={t: (10, oid) for oid, t in tickers.items()},
              ticker_owner={t: client for t in tickers.values()},
              event_id_by_outcome={row.id: 1 for row in rows},
              market_id_by_outcome={row.id: 10 for row in rows},
              blend_refresher=r, live_event_ids={1}, non_blend_outcome_ids=set(),
              prices=prices, _kalshi_yes_probability=_kalshi_yes_probability,
              buffer_lock=asyncio.Lock(), observation_signature=signatures.get,
              book_observation_pending={}, book_observation_wake=asyncio.Event(),
              tail_receipts=TailReceipts("kalshi"),
              flush_wake=asyncio.Event(), price_buffer={}, get_task_session=object())
    tree = ast.parse(Path(consumer.__file__).read_text())
    nodes = [n for n in ast.walk(tree) if isinstance(n, (ast.AsyncFunctionDef, ast.FunctionDef))
             and n.name in {"handle_book_observation", "flush_book_observations", "_parse_dollar"}]
    exec(compile(ast.Module(body=nodes, type_ignores=[]), consumer.__file__, "exec"), ns)
    payloads = [{"market_ticker": tickers[row.id],
                 "yes_bid_dollars": str(row.current_probability - .01),
                 "yes_ask_dollars": str(row.current_probability + .01), "ts_ms": 123}
                for row in rows]
    return NS(ns=ns, r=r, session=session, frames=frames, committed=committed,
              rows=rows, held=held, client=client, payloads=payloads,
              signatures=signatures, bound=bound)


async def test_consumer_coalesces_without_price_or_custody_writes(monkeypatch):
    from tests.test_blend_preview_display_before_persist_195 import _blends
    rig = consumer_rig(monkeypatch)
    for _ in range(10):
        for payload in rig.payloads:
            await rig.ns["handle_book_observation"](payload, rig.client)
    assert len(rig.ns["book_observation_pending"]) == len(rig.rows)
    assert not rig.ns["price_buffer"]
    await rig.ns["flush_book_observations"]()
    assert len(_blends(rig.frames)) == 1
    assert not rig.session.updates and not rig.committed
    assert not rig.r._history and not rig.r._lock_retry
    assert not rig.ns["book_observation_pending"]
    rig.held.sample_database_clock.assert_awaited_once()
    assert rig.ns["prices"].flush_work == 1


@pytest.mark.parametrize("transition", ["new-clock", "new-connection", "new-owner"])
async def test_receive_freezes_clock_and_connection_before_waiting_for_buffer(monkeypatch, transition):
    rig = consumer_rig(monkeypatch)
    lock = rig.ns["buffer_lock"]
    await lock.acquire()
    pending = asyncio.create_task(rig.ns["handle_book_observation"](rig.payloads[0], rig.client))
    await asyncio.sleep(0)
    ticker = rig.payloads[0]["market_ticker"]
    if transition == "new-clock":
        rig.held._database_bound += 1
    elif transition == "new-connection":
        rig.signatures[ticker] = object()
    else:
        rig.ns["ticker_owner"][ticker] = object()
    lock.release()
    await pending
    if transition == "new-clock":
        [entry] = rig.ns["book_observation_pending"].values()
        assert entry[2] == rig.bound
    else:
        assert not rig.ns["book_observation_pending"]


@pytest.mark.parametrize("case", ["settled", "left-live", "source-disabled", "signature", "busy-price", "busy-stamp", "released", "changed-row", "old-bound", "null-bound", "half-snapshot", "post-read-connection"])
async def test_consumer_revalidates_before_observation_publication(monkeypatch, case):
    from tests.test_blend_preview_display_before_persist_195 import _blends
    rig = consumer_rig(monkeypatch)
    if case == "null-bound":
        rig.held._database_bound = None
    if case == "old-bound":
        rig.held._database_bound = rig.rows[0].last_updated.timestamp()
    for payload in rig.payloads[:1] if case == "half-snapshot" else rig.payloads:
        await rig.ns["handle_book_observation"](payload, rig.client)
    if case == "settled":
        rig.ns["prices"].settled_market_ids.add(10)
    elif case == "left-live":
        rig.ns["live_event_ids"].clear()
    elif case == "source-disabled":
        rig.r.preview_events = set()
    elif case == "signature":
        rig.signatures[rig.payloads[0]["market_ticker"]] = object()
    elif case == "busy-price":
        rig.ns["price_buffer"][rig.rows[0].id] = (.8, .79, .81)
    elif case == "busy-stamp":
        rig.ns["prices"].stamping = NS(done=lambda: False)
        rig.ns["prices"].held_events = lambda _: {1}
    elif case == "changed-row":
        rig.rows[0].current_probability = .8
    elif case == "released":
        original = rig.r.preview_accepted_observations
        async def released(groups, validate):
            rig.r._admission.released[1] = 1
            return await original(groups, validate)
        rig.r.preview_accepted_observations = released
    elif case == "post-read-connection":
        original_publish = rig.r._publish_previews
        async def replaced(initial, *, prepare_frames=None):
            rig.signatures[rig.payloads[0]["market_ticker"]] = object()
            return await original_publish(initial, prepare_frames=prepare_frames)
        rig.r._publish_previews = replaced
    await rig.ns["flush_book_observations"]()
    assert not _blends(rig.frames) and not rig.session.updates and not rig.committed


@pytest.mark.parametrize("during_publish", [None, False, True])
async def test_queued_observation_refuses_sid_excursion_without_new_snapshot(monkeypatch, during_publish):
    """Legacy BBO can return to the original SID; observation proof cannot."""
    import app.tasks.kalshi_ws as consumer
    from tests.test_blend_preview_display_before_persist_195 import _blends
    rig = consumer_rig(monkeypatch)
    fixture = retained()
    book = KalshiOrderBook()
    ticker = rig.payloads[0]["market_ticker"]
    original_ticker = fixture["tail"][0]["msg"]["market_ticker"]
    for frame in fixture["seed"]:
        frame = deepcopy(frame)
        if frame["msg"]["market_ticker"] == original_ticker:
            frame["msg"]["market_ticker"] = ticker
        book.apply(frame)
    delta = deepcopy(fixture["tail"][0])
    delta["msg"]["market_ticker"] = ticker
    assert book.apply(delta, observe_unchanged=True)["_observation_only"]
    rig.client.sock._book = book
    rig.client.sock._primary_generation = object()
    rig.client.tickers = {p["market_ticker"] for p in rig.payloads}
    rig.client.task = NS(done=lambda: False)
    rig.ns.update(game_clients=[rig.client], steady_book_signature=lambda _: "unchanged-legacy-bbo")
    tree = ast.parse(Path(consumer.__file__).read_text())
    node = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)
                and n.name == "observation_signature")
    exec(compile(ast.Module(body=[node], type_ignores=[]), consumer.__file__, "exec"), rig.ns)
    for payload in rig.payloads:
        await rig.ns["handle_book_observation"](payload, rig.client)
    assert len(rig.ns["book_observation_pending"]) == 2

    def excursion():
        other = deepcopy(delta)
        other.update(sid=99, seq=1)
        other["msg"]["delta_fp"] = "1"
        assert book.apply(other, observe_unchanged=True) is None
        delta["seq"] += 1
        assert book.apply(delta, observe_unchanged=True) is None
        assert book._owners[ticker] == delta["sid"]
        assert ticker not in book._observation_snapshot_sids

    if during_publish:
        original_publish = rig.r._publish_previews
        async def after_read(initial, *, prepare_frames=None):
            excursion()
            return await original_publish(initial, prepare_frames=prepare_frames)
        rig.r._publish_previews = after_read
    elif during_publish is False:
        excursion()
    await rig.ns["flush_book_observations"]()
    assert bool(_blends(rig.frames)) is (during_publish is None)
    assert not rig.session.updates and not rig.committed
