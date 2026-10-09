"""PM receive decoding keeps stdlib values, errors and callback delivery."""

import asyncio
import json

import pytest

from app.services import polymarket_ws as service
from tests.test_pm_socket_fairness_10090 import BufferedSocket


def value_signature(value):
    # Equality alone hides int-to-float changes, signed zero, and float ULPs.
    if isinstance(value, float):
        return (float, value.hex())
    if isinstance(value, dict):
        return (dict, tuple((k, value_signature(v)) for k, v in value.items()))
    if isinstance(value, list):
        return (list, tuple(value_signature(v) for v in value))
    return (type(value), value)


@pytest.mark.parametrize("raw", [
    '{"n":18446744073709551616,"negative":-18446744073709551617}',
    '{"n":' + str(10**200 + 17) + '}',
    str(10**4000),
    '[0.0,-0.0,0.1,1.2345678901234567,1e999,-1e999,5e-324,1.7976931348623157e308]',
    '[null,true,false,"é 🎾","\\ud83c\\udfbe"]',
    '{"a":1,"b":null,"a":2}',
    '[NaN,Infinity,-Infinity]',
    '["\\ud800","\\udfff"]',
    '"' + chr(0xd800) + '"',
    '{"a":1}'.encode("utf-16"),
    bytearray(b'{"a":1}'),
    '"bare\\ntext"',
])
def test_values_types_order_and_float_bits_match_stdlib(raw):
    assert value_signature(service._decode_message(raw)) == value_signature(json.loads(raw))


@pytest.mark.parametrize("raw", [
    '{bad', '[1]junk', '-NaN', '+Infinity', '[01]', '{"a":1,}',
    '1' * 5000, None, [], b'"\xff"',
])
def test_rejections_keep_stdlib_error_type_message_and_position(raw):
    with pytest.raises(Exception) as expected:
        json.loads(raw)
    with pytest.raises(type(expected.value)) as actual:
        service._decode_message(raw)
    assert str(actual.value) == str(expected.value)
    if isinstance(expected.value, json.JSONDecodeError):
        assert actual.value.pos == expected.value.pos
        assert actual.value.doc == expected.value.doc


@pytest.mark.parametrize("error", [ValueError, TypeError])
def test_fast_parser_refusal_falls_back_without_string_cache(monkeypatch, error):
    calls = []

    def refuse(raw, **kwargs):
        calls.append(kwargs)
        raise error("parser refused")

    monkeypatch.setattr(service, "from_json", refuse)
    assert service._decode_message('{"n":18446744073709551616}') == {"n": 18446744073709551616}
    assert calls == [{"cache_strings": False}]


@pytest.mark.asyncio
@pytest.mark.parametrize("async_handler", [False, True])
async def test_actual_receive_loop_keeps_callback_payloads_order_and_invalid_skips(
    monkeypatch, async_handler,
):
    payload = {
        "big": 10**200 + 17, "values": [None, -0.0, 0.1, float("nan"), float("inf")],
        "label": "é 🎾", "duplicates": {"n": 2},
    }
    messages = [dict(payload, event_type=kind, asset_id="a", sequence=i)
                for i, kind in enumerate(("best_bid_ask", "last_trade_price",
                                          "market_resolved", "new_market"))]
    frames = ["PONG", "{bad", *[json.dumps(message) for message in messages]]
    socket = BufferedSocket(frames)
    monkeypatch.setattr("websockets.connect", lambda *args, **kwargs: socket)
    client = service.PolymarketWebSocket()
    delivered = []

    def receive(message):
        delivered.append(message)

    async def receive_async(message):
        receive(message)

    for callback in ("on_price", "on_trade", "on_resolved", "on_new_market"):
        setattr(client, callback, receive_async if async_handler else receive)
    task = asyncio.create_task(client._run_one(["a"], 0))
    try:
        await asyncio.wait_for(socket.drained.wait(), 1)
        assert value_signature(delivered) == value_signature(messages)
        assert client.stats["messages"] == 5  # PONG excluded, invalid counted
        assert client._shard_wire == {0: {"a"}}
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert socket.closed
