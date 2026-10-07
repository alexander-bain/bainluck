"""Bounded exact evidence on the existing socket, with no quote-policy change.

Service/control tests reuse the existing #10667 socket harness; writer tests
reuse the #8753 real consumer/SQL replay and #10640 transaction-boundary rig.
ACK fixtures describe a correlated channel response, never accepted membership.
"""

import ast
import asyncio
import contextlib
from datetime import datetime, timezone
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import app.tasks.kalshi_ws as task
from app.tasks.kalshi import _kalshi_yes_probability
from app.tasks.live_blend_refresh import InputMark, LiveBlendRefresher, TailReceipts
from app.utils.kalshi_exact_trace import ExactKalshiTrace, MAX_PENDING
from app.utils.live_push import build_frame
from tests.test_event_frame_batching_10659 import ProtocolRedis
from tests.test_kalshi_ws_lifecycle_dispatch_10667 import (
    Feed,
    connect as socket_connect,
    stop,
)

connect = socket_connect

TICKER = "KXATPCHALLENGERDOUBLES-26OCT07BARVOCMARWAL-BARVOC"


def trace_for(target=TICKER, limit=128):
    clock = [1000.0, 10.0]
    records = []
    trace = ExactKalshiTrace.from_env(
        {
            "WS_KALSHI_TRACE_TICKERS": target,
            "WS_KALSHI_TRACE_EXPIRES_AT": "1100",
            "WS_KALSHI_TRACE_MAX_LINES": str(limit),
        },
        run="test-run",
        wall=lambda: clock[0],
        mono=lambda: clock[1],
        emit=records.append,
    )
    return trace, records, clock


@pytest.mark.parametrize(
    "env",
    [
        {},
        {"WS_KALSHI_TRACE_TICKERS": TICKER},
        {"WS_KALSHI_TRACE_TICKERS": "A,B,C,D,E", "WS_KALSHI_TRACE_EXPIRES_AT": "1100"},
        {"WS_KALSHI_TRACE_TICKERS": "A secret", "WS_KALSHI_TRACE_EXPIRES_AT": "1100"},
        {"WS_KALSHI_TRACE_TICKERS": "A", "WS_KALSHI_TRACE_EXPIRES_AT": "1601"},
        {"WS_KALSHI_TRACE_TICKERS": "A", "WS_KALSHI_TRACE_EXPIRES_AT": "nan"},
        {"WS_KALSHI_TRACE_TICKERS": "A", "WS_KALSHI_TRACE_EXPIRES_AT": "999"},
        {
            "WS_KALSHI_TRACE_TICKERS": "A",
            "WS_KALSHI_TRACE_EXPIRES_AT": "1100",
            "WS_KALSHI_TRACE_MAX_LINES": "257",
        },
    ],
)
def test_off_or_invalid_configuration_is_disabled(env):
    assert ExactKalshiTrace.from_env(env, run="test", wall=lambda: 1000) is None


@pytest.mark.parametrize("expiry_clock", [(1100, 10), (999, 110)])
def test_expiry_uses_both_clocks_and_erases_retained_state(expiry_clock):
    trace, records, clock = trace_for()
    trace.sent("socket", 1, "ticker", [TICKER])
    msg = {"market_ticker": TICKER}
    trace.received("socket", msg)
    clock[:] = expiry_clock
    trace.received("socket", msg)
    trace.sent("socket", 2, "ticker", [TICKER])
    assert records[-1]["stage"] == "STOP" and records[-1]["reason"] == "EXPIRED"
    assert len(records) == 4
    assert all(
        not s
        for s in (
            trace.commands,
            trace.receives,
            trace.accepted,
            trace.commits,
            trace.stamps,
        )
    )


def test_budget_includes_stop_and_retained_maps_are_bounded():
    trace, records, _ = trace_for(limit=256)
    for i in range(80):
        trace.sent("socket", i, "ticker", [TICKER])
    assert len(trace.commands) == MAX_PENDING
    for i in range(1000):
        trace.response(
            "socket",
            {"id": 79, "type": "subscribed", "msg": {"channel": "ticker", "sid": i}},
        )
    assert len(records) == 256 and records[-1]["reason"] == "BUDGET_STOP"
    assert not trace.commands


def test_whitelist_never_retains_error_text_credentials_headers_or_arbitrary_values():
    trace, records, _ = trace_for()
    trace.sent("socket", 1, "ticker", [TICKER, "OTHER"])
    msg = {
        "market_ticker": TICKER,
        "yes_bid_dollars": "secret-token",
        "price_dollars": "0.8",
        "headers": {"Authorization": "secret-token"},
        "ts": 123,
        "secret": "secret-token",
    }
    trace.received("socket", msg)
    trace.response(
        "socket", {"id": 1, "type": "error", "msg": {"code": 12, "msg": "secret-token"}}
    )
    rendered = json.dumps(records)
    assert (
        "secret-token" not in rendered
        and "Authorization" not in rendered
        and "OTHER" not in rendered
    )
    assert records[2]["prices"]["yes_bid_dollars"] == "INVALID"
    assert records[2]["vendor_clock"] == {"ts": 123}
    assert records[-1]["code"] == 12


async def test_actual_socket_correlates_control_frames_without_changing_callbacks(
    connect,
):
    import app.services.kalshi_ws as service

    feed = Feed(
        [
            json.dumps(
                {"id": 1, "type": "subscribed", "msg": {"channel": "ticker", "sid": 7}}
            ),
            json.dumps(
                {"id": 2, "type": "error", "msg": {"code": 8, "msg": "do not log me"}}
            ),
            json.dumps(
                {
                    "id": 999,
                    "type": "subscribed",
                    "msg": {"channel": "ticker", "sid": 9},
                }
            ),
            json.dumps(
                {
                    "type": "ticker",
                    "msg": {"market_ticker": TICKER, "price_dollars": "0.8"},
                }
            ),
        ]
    )
    connect(feed)
    ws = service.KalshiWebSocket()
    trace, records, _ = trace_for()
    ws.exact_trace = trace
    seen = []
    ws.on_ticker = seen.append
    running = asyncio.create_task(ws.run([TICKER]))
    try:
        await asyncio.wait_for(feed.exhausted.wait(), 1)
    finally:
        await stop(running)
    assert len(seen) == 1 and seen[0]["price_dollars"] == "0.8"
    assert [r["stage"] for r in records] == [
        "START",
        "SENT",
        "SENT",
        "ACK",
        "ERROR",
        "RECEIVED",
    ]
    assert records[3]["membership"] == "UNPROVEN_CHANNEL_ACK_ONLY"
    assert records[3]["channel_matches"]
    assert records[3]["connection"] == records[1]["connection"]
    assert "do not log me" not in json.dumps(records)


async def test_trace_connection_identity_failure_preserves_subscription_and_callbacks(
    connect, monkeypatch
):
    import uuid
    import app.services.kalshi_ws as service

    class RecordingFeed(Feed):
        def __init__(self):
            super().__init__(
                [
                    json.dumps({"type": kind, "msg": {"market_ticker": TICKER}})
                    for kind in ("ticker", "market_lifecycle_v2", "trade")
                ]
            )
            self.sent = []

        async def send(self, value):
            self.sent.append(json.loads(value))

    async def run(trace):
        feed = RecordingFeed()
        connections = connect(feed)
        prior_connections = len(connections)
        ws = service.KalshiWebSocket()
        ws.exact_trace = trace
        seen = []
        ws.on_ticker = lambda msg: seen.append(("ticker", msg))
        ws.on_lifecycle = lambda msg: seen.append(("lifecycle", msg))
        ws.on_trade = lambda msg: seen.append(("trade", msg))
        running = asyncio.create_task(ws.run([TICKER]))
        try:
            await asyncio.wait_for(feed.exhausted.wait(), 1)
            assert ws.is_connected and len(connections) == prior_connections + 1
        finally:
            await stop(running)
        return feed.sent, seen

    baseline = await run(None)
    trace, records, _ = trace_for()
    attempts = []

    def failed():
        attempts.append(True)
        raise RuntimeError("diagnostic connection identity failed")

    monkeypatch.setattr(uuid, "uuid4", failed)
    assert await run(trace) == baseline
    assert len(attempts) == 1 and len(baseline[0]) == 2
    assert [kind for kind, _ in baseline[1]] == ["ticker", "lifecycle", "trade"]
    assert [r["stage"] for r in records] == ["START"]


def handler(trace, mapped=True):
    tree = ast.parse(Path(task.__file__).read_text())
    nodes = [
        n
        for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        and n.name in ("_parse_dollar", "handle_ticker")
    ]
    receipts = TailReceipts("kalshi")
    receipts.exact_trace = trace
    ns = dict(
        contextlib=contextlib,
        asyncio=asyncio,
        tail_receipts=receipts,
        ticker_to_ids={TICKER: (7, 81)} if mapped else {},
        open_contract_ids={},
        event_id_by_outcome={81: 900},
        _kalshi_yes_probability=_kalshi_yes_probability,
        buffer_lock=asyncio.Lock(),
        price_buffer={},
        input_marks={},
    )
    exec(compile(ast.Module(body=nodes, type_ignores=[]), task.__file__, "exec"), ns)
    return ns


@pytest.mark.parametrize(
    "fields,reason",
    [
        ({}, "MISSING_OR_INVALID_DOLLAR_FIELDS"),
        (
            {"price": 80, "yes_bid": 66, "yes_ask": 70},
            "MISSING_OR_INVALID_DOLLAR_FIELDS",
        ),
        (
            {"yes_bid_dollars": "secret", "yes_ask_dollars": None},
            "MISSING_OR_INVALID_DOLLAR_FIELDS",
        ),
        ({"yes_bid_dollars": ".1", "yes_ask_dollars": ".9"}, "PRICE_POLICY_REFUSED"),
        ({"price_dollars": "1"}, "TERMINAL_OR_INVALID"),
        (
            {
                "price_dollars": ".80",
                "yes_bid_dollars": ".66",
                "yes_ask_dollars": ".70",
            },
            "ACCEPTED",
        ),
    ],
)
async def test_actual_handler_retains_price_policy_and_records_why(fields, reason):
    trace, records, _ = trace_for()
    on, off = handler(trace), handler(None)
    msg = dict(market_ticker=TICKER, **fields)
    trace.received("socket", msg)
    await on["handle_ticker"](msg)
    await off["handle_ticker"](dict(msg))
    assert on["price_buffer"] == off["price_buffer"]
    assert records[-1]["reason"] == reason
    if reason == "ACCEPTED":
        mark = on["input_marks"][81]
        assert records[-1]["input_seq"] == mark.seq and records[-1]["receive_id"] == 1
        assert mark.probability == pytest.approx(0.68)
        assert records[-1]["input_recv_wall"] == mark.recv_wall
    else:
        assert not on["input_marks"]


async def test_unmapped_target_is_recorded_before_it_disappears():
    trace, records, _ = trace_for()
    ns = handler(trace, mapped=False)
    msg = dict(market_ticker=TICKER, price_dollars=".5")
    trace.received("socket", msg)
    await ns["handle_ticker"](msg)
    assert records[-1]["reason"] == "UNMAPPED" and not ns["price_buffer"]


def mark(seq=1):
    return InputMark(seq, 900, 81, 0.68, "ticker", 1000, 10, None, seq)


def accepted(trace, value=None):
    value = value or mark()
    msg = dict(market_ticker=TICKER, price_dollars=".68")
    trace.received("socket", msg)
    trace.decided(
        msg,
        reason="ACCEPTED",
        market=7,
        outcome=81,
        event=900,
        probability=0.68,
        mark=value,
    )
    return value


async def test_exact_observation_basis_and_revision_link_to_real_publisher_ack():
    trace, records, _ = trace_for()
    value = accepted(trace)
    observed = datetime.fromtimestamp(1001, timezone.utc)
    trace.committed(value, observed)
    trace.stamp(900, {"81": 1000.999999}, 251, "wrong")
    trace.publication(900, 251, "REDIS_ACK")
    assert not any(r["stage"] == "EVENT_COMMITTED" for r in records)
    trace.stamp(900, {"81": observed.timestamp()}, 252, observed.isoformat())
    client = ProtocolRedis([0])
    r = LiveBlendRefresher("kalshi")
    r.receipts = SimpleNamespace(exact_trace=trace)
    r._redis = client
    frame = build_frame(
        event_id=900,
        probability=0.68,
        source="kalshi",
        source_value=0.68,
        updated_at=observed.isoformat(),
        status="live",
        rev=252,
    )
    await r._publish([frame])
    assert client.commands == [("PUBLISH", "live:event:900", json.dumps(frame))]
    assert records[-1]["stage"] == "EVENT_PUBLICATION"
    assert records[-1]["publication"] == "REDIS_ACK" and records[-1]["revision"] == 252
    assert (
        records[-1]["input_seq"] == value.seq
        and records[-1]["browser_delivery"] == "UNAVAILABLE"
    )


async def test_actual_consumer_price_write_is_identical_with_trace_enabled(
    monkeypatch, caplog
):
    import time
    from tests.test_kalshi_socket_prices_by_the_rest_rule_8753 import (
        TICKER as existing_ticker,
        _price_updates,
        _stored_after,
        _tick,
    )

    caplog.set_level("INFO")
    frame = _tick(price_dollars=".96", yes_bid_dollars=".59", yes_ask_dollars=".95")
    off = await _price_updates(monkeypatch, frame)
    monkeypatch.setenv("WS_KALSHI_TRACE_TICKERS", existing_ticker)
    monkeypatch.setenv("WS_KALSHI_TRACE_EXPIRES_AT", str(time.time() + 60))
    on = await _price_updates(monkeypatch, frame)
    assert len(on) == len(off) == 1 and _stored_after(on[0]) == _stored_after(off[0])
    lines = [
        json.loads(r.message.split("kalshi-exact-trace ", 1)[1])
        for r in caplog.records
        if r.message.startswith("kalshi-exact-trace ")
    ]
    decision = next(r for r in lines if r["stage"] == "DECISION")
    committed = next(r for r in lines if r["stage"] == "PRICE_COMMITTED")
    assert committed["input_seq"] == decision["input_seq"]
    assert committed["receive_id"] == decision["receive_id"]


async def test_configured_target_absent_from_both_maps_has_explicit_admission(
    monkeypatch, caplog
):
    import time
    from tests.test_kalshi_socket_prices_by_the_rest_rule_8753 import (
        _price_updates,
        _tick,
    )

    caplog.set_level("INFO")
    monkeypatch.setenv("WS_KALSHI_TRACE_TICKERS", "ABSENT-TARGET")
    monkeypatch.setenv("WS_KALSHI_TRACE_EXPIRES_AT", str(time.time() + 60))
    writes = await _price_updates(
        monkeypatch, _tick(yes_bid_dollars=".66", yes_ask_dollars=".70")
    )
    records = [
        json.loads(r.message.split("kalshi-exact-trace ", 1)[1])
        for r in caplog.records
        if r.message.startswith("kalshi-exact-trace ")
    ]
    assert len(writes) == 1  # the existing selected ticker still moves
    assert records[0]["stage"] == "START"
    assert records[0]["mapping"] == "UNAVAILABLE_BEFORE_SLATE"
    admitted = [r for r in records if r["stage"] == "ADMISSION"]
    assert admitted and all(
        not r["selected_in_linked"] and not r["selected_in_open"] for r in admitted
    )
    assert (
        admitted[-1]["phase"] == "OPEN_ADMISSION"
        and admitted[-1]["open_status"] == "SELECTED"
    )
    assert not any(r["stage"] == "SENT" for r in records)


async def test_failed_actual_writer_never_reports_commit_or_stamp(monkeypatch, caplog):
    import time
    from tests.test_ws_kalshi_linked_first_10640 import (
        _Rig,
        _start,
        GAME_TICKER,
        GAME_OUTCOME,
    )

    caplog.set_level("INFO")
    monkeypatch.setenv("WS_KALSHI_TRACE_TICKERS", GAME_TICKER)
    monkeypatch.setenv("WS_KALSHI_TRACE_EXPIRES_AT", str(time.time() + 60))
    rig = _Rig()

    async def fail(_prob, _attempt):
        raise RuntimeError("price transaction failed")

    rig.hooks[GAME_OUTCOME] = fail
    running = await _start(monkeypatch, rig, recycle=0.15)
    await asyncio.wait_for(running, 2)
    lines = [
        json.loads(r.message.split("kalshi-exact-trace ", 1)[1])
        for r in caplog.records
        if r.message.startswith("kalshi-exact-trace ")
    ]
    assert any(r["stage"] == "PRICE_NOT_COMMITTED" for r in lines)
    assert not any(
        r["stage"] in ("PRICE_COMMITTED", "EVENT_COMMITTED", "EVENT_PUBLICATION")
        for r in lines
    )


async def test_trace_factory_failure_never_costs_actual_consumer_price_write(
    monkeypatch,
):
    from tests.test_kalshi_socket_prices_by_the_rest_rule_8753 import (
        _price_updates,
        _stored_after,
        _tick,
    )

    frame = _tick(price_dollars=".96", yes_bid_dollars=".59", yes_ask_dollars=".95")
    baseline = await _price_updates(monkeypatch, frame)
    calls = []

    def failed(*_a, **_kw):
        calls.append(True)
        raise RuntimeError("diagnostic initialization failed")

    monkeypatch.setattr(ExactKalshiTrace, "from_env", failed)
    writes = await _price_updates(monkeypatch, frame)
    assert len(calls) == len(writes) == len(baseline) == 1
    assert _stored_after(writes[0]) == _stored_after(baseline[0])
    assert _stored_after(writes[0]) == pytest.approx((0.77, 0.59, 0.95))


async def test_trace_predicate_failure_never_costs_actual_price_write(monkeypatch):
    from tests.test_kalshi_socket_prices_by_the_rest_rule_8753 import (
        TICKER as existing_ticker,
        _price_updates,
        _stored_after,
        _tick,
    )

    trace, _records, _clock = trace_for(existing_ticker)
    calls = []

    def failed(mark):
        calls.append(mark)
        raise RuntimeError("diagnostic retention failed")

    trace.tracks = failed
    monkeypatch.setattr(ExactKalshiTrace, "from_env", lambda *_a, **_kw: trace)
    writes = await _price_updates(
        monkeypatch,
        _tick(price_dollars=".96", yes_bid_dollars=".59", yes_ask_dollars=".95"),
    )
    assert len(calls) == len(writes) == 1
    assert _stored_after(writes[0]) == pytest.approx((0.77, 0.59, 0.95))


async def test_trace_predicate_failure_never_costs_actual_event_stamp(monkeypatch):
    from tests.test_live_blend_refresh import (
        _event_and_market,
        _LockedRowSession,
        _one_event_refresher,
    )

    event, market = _event_and_market()
    session = _LockedRowSession(
        [(market, event)],
        [],
        {"polymarket": {"updated_at": "2026-09-25T18:00:00+00:00"}},
        locked=False,
    )
    r, published = _one_event_refresher(monkeypatch, session)
    # Supply the snapshot metadata omitted by the older stamp-only fixture.
    monkeypatch.setattr(
        "app.utils.live_blend.compute_source_home_probability",
        lambda group, home, away: SimpleNamespace(
            home_probability=0.9,
            away_probability=None,
            draw_probability=None,
            eligibility=None,
            market=market,
            outcome=SimpleNamespace(name="Phillies"),
            yes_probability=0.9,
        ),
    )
    r.receipts = TailReceipts("polymarket")
    trace, _records, _clock = trace_for()
    r.receipts.exact_trace = trace
    calls = []

    def failed(event_id):
        calls.append(event_id)
        raise RuntimeError("diagnostic retention failed")

    trace.tracks_event = failed
    await r.refresh([1])
    assert calls == [1] and r.stats["stamped"] == 1 and r.stats["errors"] == 0
    assert len(session.updates) == 1 and [f["event_id"] for f in published] == [1]


async def test_production_repeat_pattern_keeps_budget_for_late_exact_changed_chain():
    # Raw run10a12bf6: 52 receives, ATL23/LAD29, each with identical full book.
    # This repeats the actual accepted numeric books through the real handler.
    atl = "KXMLBGAME-26OCT071800LADATL-ATL"
    lad = "KXMLBGAME-26OCT071800LADATL-LAD"
    trace, records, clock = trace_for(atl + "," + lad)
    on, off = handler(trace), handler(None)
    for ns in (on, off):
        ns["ticker_to_ids"] = {atl: (7, 81), lad: (7, 82)}
        ns["event_id_by_outcome"] = {81: 900, 82: 900}
    pattern = LIVE_REPEAT_PATTERN
    for index, ticker in enumerate(pattern):
        bid, ask, last = (0.54, 0.55, 0.55) if ticker == "ATL" else (0.45, 0.46, 0.46)
        msg = dict(
            market_ticker=atl if ticker == "ATL" else lad,
            price_dollars=last,
            yes_bid_dollars=bid,
            yes_ask_dollars=ask,
        )
        trace.received("socket", msg)
        await on["handle_ticker"](msg)
        await off["handle_ticker"](dict(msg))
        # Twelve successful unchanged price commits were present in the receipt.
        if index in (1, 5, 9, 13, 17, 31):
            trace.snapshot(on["input_marks"].values())
            for mark_value in on["input_marks"].values():
                trace.committed(
                    mark_value, datetime.fromtimestamp(1001 + index, timezone.utc)
                )
        clock[0] += 0.6
        clock[1] += 0.6
    assert len(pattern) == 52 and pattern.count("ATL") == 23
    assert (
        on["tail_receipts"].stats["inputs"]
        == off["tail_receipts"].stats["inputs"]
        == 52
    )
    assert on["price_buffer"] == off["price_buffer"]
    assert len(records) < 20 and not trace.stopped
    # >64 same-price accepts after a writer snapshot must preserve that old mark.
    snapshot_mark = on["input_marks"][81]
    trace.snapshot([snapshot_mark])
    for _ in range(100):
        msg = dict(
            market_ticker=atl,
            price_dollars=0.55,
            yes_bid_dollars=0.54,
            yes_ask_dollars=0.55,
        )
        trace.received("socket", msg)
        await on["handle_ticker"](msg)
        await off["handle_ticker"](dict(msg))
        clock[0] += 0.3
        clock[1] += 0.3
    assert clock[0] > 1060 and trace.tracks(snapshot_mark)
    stored = datetime.fromtimestamp(1062, timezone.utc)
    trace.committed(snapshot_mark, stored)
    trace.stamp(900, {"81": stored.timestamp()}, 252, stored.isoformat())
    trace.publication(900, 252, "REDIS_ACK")
    old_chain = [r for r in records if r.get("input_seq") == snapshot_mark.seq]
    assert {r["stage"] for r in old_chain} >= {
        "DECISION",
        "PRICE_COMMITTED",
        "EVENT_COMMITTED",
        "EVENT_PUBLICATION",
    }
    assert (
        old_chain[-1]["receive_id"] == 52
    )  # exact earlier snapshot, never newest repeat
    # A changed quote followed by an identical superseding repeat: chain must
    # belong to the newest InputMark, not the first changed input.
    for _ in range(2):
        msg = dict(
            market_ticker=atl,
            price_dollars=0.47,
            yes_bid_dollars=0.46,
            yes_ask_dollars=0.47,
        )
        trace.received("socket", msg)
        await on["handle_ticker"](msg)
        await off["handle_ticker"](dict(msg))
        clock[0] += 0.1
        clock[1] += 0.1
    latest = on["input_marks"][81]
    trace.snapshot([latest])
    observed = datetime.fromtimestamp(1063, timezone.utc)
    trace.committed(latest, observed)
    trace.stamp(900, {"81": observed.timestamp()}, 253, observed.isoformat())
    trace.publication(900, 253, "REDIS_ACK")
    chain = [r for r in records if r.get("input_seq") == latest.seq]
    assert [r["stage"] for r in chain] == [
        "DECISION",
        "PRICE_COMMITTED",
        "EVENT_COMMITTED",
        "EVENT_PUBLICATION",
    ]
    receive = next(
        r
        for r in records
        if r["stage"] == "RECEIVED" and r["receive_id"] == chain[0]["receive_id"]
    )
    assert latest.seq == 154 and receive["receive_id"] == 154
    assert receive["emitted_mono"] > receive["receive_mono"]
    assert all(
        r["input_recv_wall"] == latest.recv_wall
        and r["input_recv_mono"] == latest.recv_mono
        for r in chain
    )
    assert len(records) < 40 and not trace.stopped
    assert on["price_buffer"] == off["price_buffer"]
    assert on["tail_receipts"].stats == off["tail_receipts"].stats


@pytest.mark.parametrize(
    "change", ["connection", "mapping", "reason", "fields", "book"]
)
def test_repeat_compression_keeps_every_semantic_transition(change):
    trace, records, _ = trace_for()
    accepted(trace)
    msg = dict(market_ticker=TICKER, price_dollars=".68")
    if change == "fields":
        msg["price"] = 68
    if change == "book":
        msg.update(yes_bid_dollars=".67", yes_ask_dollars=".69")
    trace.received("reconnected" if change == "connection" else "socket", msg)
    trace.decided(
        msg,
        reason="PRICE_POLICY_REFUSED" if change == "reason" else "ACCEPTED",
        market=8 if change == "mapping" else 7,
        outcome=81,
        event=900,
        probability=0.68,
        mark=None if change == "reason" else mark(2),
    )
    assert [r["stage"] for r in records][-2:] == ["RECEIVED", "DECISION"]
    assert records[-1]["receive_id"] == 2


@pytest.mark.parametrize(
    "failure", ["LOCK_TIMEOUT", "ROLLED_BACK", "DECLINED_SETTLED_OR_MISSING"]
)
def test_suppressed_repeat_failure_and_retry_keep_exact_chain(failure):
    trace, records, _ = trace_for()
    first = accepted(trace)
    trace.committed(first, datetime.fromtimestamp(1001, timezone.utc))
    repeat = accepted(trace, mark(2))
    trace.snapshot([repeat])
    trace.write_failed([repeat], failure)
    assert records[-1]["stage"] == "PRICE_NOT_COMMITTED"
    assert (
        records[-1]["input_seq"] == repeat.seq
        and records[-1]["write_reason"] == failure
    )
    observed = datetime.fromtimestamp(1002, timezone.utc)
    trace.committed(repeat, observed)
    assert (
        records[-1]["stage"] == "PRICE_COMMITTED"
        and records[-1]["input_seq"] == repeat.seq
    )
    trace.stamp(900, {"81": observed.timestamp()}, 253, observed.isoformat())
    trace.publication(900, 253, "REDIS_ERROR")
    assert records[-1]["publication"] == "REDIS_ERROR"


def test_new_repeat_state_stays_bounded_and_is_cleared_on_expiry():
    trace, records, clock = trace_for()
    for seq in range(1, 200):
        accepted(trace, mark(seq))
    trace.snapshot([mark(199)])
    assert len(trace.accepted) == MAX_PENDING and len(trace.pinned) == 1
    assert len(trace.last_quotes) == len(trace.last_decisions) == 1
    assert len(records) == 3
    clock[0] = 1100
    assert not trace.active()
    assert all(
        not state
        for state in (
            trace.accepted,
            trace.pinned,
            trace.last_quotes,
            trace.last_decisions,
            trace.last_writes,
        )
    )


async def test_snapshot_failure_is_fail_open_for_actual_consumer(monkeypatch):
    from tests.test_kalshi_socket_prices_by_the_rest_rule_8753 import (
        TICKER as ticker,
        _price_updates,
        _stored_after,
        _tick,
    )

    trace, records, _ = trace_for(ticker)

    def failed(*_args):
        raise RuntimeError("diagnostic snapshot failed")

    trace.snapshot = failed
    monkeypatch.setattr(ExactKalshiTrace, "from_env", lambda *_a, **_kw: trace)
    writes = await _price_updates(
        monkeypatch,
        _tick(price_dollars=".96", yes_bid_dollars=".59", yes_ask_dollars=".95"),
    )
    assert len(writes) == 1 and _stored_after(writes[0]) == pytest.approx(
        (0.77, 0.59, 0.95)
    )


LIVE_REPEAT_PATTERN = [
    "ATL",
    "LAD",
    "ATL",
    "LAD",
    "LAD",
    "LAD",
    "ATL",
    "ATL",
    "LAD",
    "LAD",
    "ATL",
    "ATL",
    "LAD",
    "ATL",
    "LAD",
    "LAD",
    "ATL",
    "ATL",
    "LAD",
    "ATL",
    "LAD",
    "LAD",
    "LAD",
    "ATL",
    "LAD",
    "ATL",
    "LAD",
    "ATL",
    "LAD",
    "ATL",
    "LAD",
    "ATL",
    "LAD",
    "ATL",
    "LAD",
    "LAD",
    "ATL",
    "LAD",
    "LAD",
    "ATL",
    "ATL",
    "LAD",
    "ATL",
    "LAD",
    "ATL",
    "LAD",
    "LAD",
    "LAD",
    "LAD",
    "LAD",
    "ATL",
    "ATL",
]


@pytest.mark.parametrize("limit", [5, 6, 7])
def test_stop_during_deferred_failure_erases_state_without_repopulation(limit):
    trace, records, _ = trace_for(limit=limit)
    accepted(trace)
    repeat = accepted(trace, mark(2))
    trace.snapshot([repeat])
    trace.write_failed([repeat], "ROLLED_BACK")
    trace.active()
    assert records[-1]["stage"] == "STOP"
    assert sum(r["stage"] == "STOP" for r in records) == 1
    assert len(records) <= limit
    assert all(
        not state
        for state in (
            trace.commands,
            trace.receives,
            trace.accepted,
            trace.commits,
            trace.stamps,
            trace.pinned,
            trace.last_quotes,
            trace.last_decisions,
            trace.last_writes,
        )
    )


def test_emitter_failure_on_deferred_materialization_never_raises_or_changes_mark():
    trace, _records, _ = trace_for()
    first = accepted(trace)
    trace.committed(first, datetime.fromtimestamp(1001, timezone.utc))
    repeat = accepted(trace, mark(2))

    def failed(_record):
        raise RuntimeError("logger unavailable")

    trace.emit = failed
    trace.write_failed([repeat], "ROLLED_BACK")
    trace.committed(repeat, datetime.fromtimestamp(1002, timezone.utc))
    assert trace.tracks(repeat) and trace.commits[81]["input_seq"] == repeat.seq


def test_two_target_tickers_for_same_outcome_do_not_collapse_write_identity():
    trace, records, _ = trace_for(TICKER + ",ALIAS")
    first = accepted(trace)
    trace.committed(first, datetime.fromtimestamp(1001, timezone.utc))
    msg = dict(market_ticker="ALIAS", price_dollars=".68")
    trace.received("socket", msg)
    trace.decided(
        msg,
        reason="ACCEPTED",
        market=7,
        outcome=81,
        event=900,
        probability=0.68,
        mark=mark(2),
    )
    trace.committed(mark(2), datetime.fromtimestamp(1002, timezone.utc))
    assert records[-1]["stage"] == "PRICE_COMMITTED"
    assert records[-1]["ticker"] == "ALIAS" and records[-1]["input_seq"] == 2


def test_materialized_decision_and_commit_keep_occurrence_separate_from_emission():
    trace, records, clock = trace_for()
    first = accepted(trace)
    trace.committed(first, datetime.fromtimestamp(1001, timezone.utc))
    clock[:] = [1001.5, 11.5]
    msg = dict(market_ticker=TICKER, price_dollars=".68")
    trace.received("socket", msg)
    clock[:] = [1002, 12]
    repeat = mark(2)
    trace.decided(
        msg,
        reason="ACCEPTED",
        market=7,
        outcome=81,
        event=900,
        probability=0.68,
        mark=repeat,
    )
    clock[:] = [1003, 13]
    observed = datetime.fromtimestamp(1003, timezone.utc)
    trace.committed(repeat, observed)  # unchanged commit is retained silently
    clock[:] = [1004, 14]
    trace.stamp(900, {"81": observed.timestamp()}, 253, observed.isoformat())
    chain = [r for r in records if r.get("input_seq") == 2]
    decision, commit = [
        r for r in chain if r["stage"] in ("DECISION", "PRICE_COMMITTED")
    ]
    assert (decision["receive_wall"], decision["receive_mono"]) == (1002, 12)
    assert (commit["receive_wall"], commit["receive_mono"]) == (1003, 13)
    assert decision["emitted_wall"] == commit["emitted_wall"] == 1004
    assert decision["emitted_mono"] == commit["emitted_mono"] == 14

    clock[:] = [1005, 15]
    trace.publication(900, 253, "REDIS_ACK")
    receive = next(
        r for r in records if r["stage"] == "RECEIVED" and r["receive_id"] == 2
    )
    event = next(
        r for r in records if r["stage"] == "EVENT_COMMITTED" and r["input_seq"] == 2
    )
    publication = records[-1]
    assert [
        receive["receive_wall"],
        decision["receive_wall"],
        commit["receive_wall"],
        event["receive_wall"],
        publication["receive_wall"],
    ] == [1001.5, 1002, 1003, 1004, 1005]
