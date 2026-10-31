"""#10090 — CPU cuts for the saturated venue processes, each with its undo.

Production 2026-10-30 23:23-23:33Z: Polymarket's venue loop ran at cpu
0.96-0.97 and Kalshi's at 0.94, and the worst user-visible delay rose with that
load. Three cuts, each undone by one setting that restores today's path:

* Kalshi socket frames decode with the parser Polymarket's frames already use,
  ``app.utils.ws_json.loads`` (``WS_FAST_JSON=0``).
* Socket-consumer engines decode JSONB with the same parser. Every other
  engine is asked exactly what it was asked before (``WS_FAST_JSON=0``).
* Each venue child raises generation 0's GC threshold (``WS_GC_GEN0``; ``0``
  keeps the interpreter's).
"""

import asyncio
import gc
import importlib
import inspect
import json
import logging
import math

import pytest

import app.tasks.base as task_base
import run_kalshi_ws
from app.services import kalshi_ws as kalshi_service
from app.utils import ws_json

CORPUS = [
    '{"type":"ticker","sid":1,"seq":7,"msg":{"market_ticker":"KXNBAGAME-26OCT30LALBOS-LAL",'
    '"yes_bid":55,"yes_ask":57,"price":56,"yes_bid_dollars":"0.5500","ts":1793392118}}',
    '{"type":"orderbook_delta","sid":2,"seq":9,"msg":{"market_ticker":"X","price":44,'
    '"delta":-120,"side":"yes"}}',
    '{"big":123456789012345678901234567890,"negbig":-98765432109876543210987654321,'
    '"zero":-0,"f":0.1,"e":1e-7,"max":1.7976931348623157e308,"tiny":5e-324,'
    '"neg":-0.0,"t":true,"fa":false,"n":null}',
    '{"s":"caf\\u00e9 \\ud83d\\ude00 \\"q\\" \\\\ \\/ \\b\\f\\n\\r\\t","raw":"café 😀",'
    '"nested":[[],[{}],{"a":[1,2,{"b":"c"}]}]}',
    '[{"asset_id":"71321045679252212594626385532706912750332728571942532289631379312455583992563",'
    '"bids":[{"price":"0.55","size":"100"}],"asks":[],"timestamp":"1793392118376"}]',
    '{"dup":1,"dup":2}',
    '  {"padded": [1, 2.50, 3e2]}  \n',
    '"just a string"',
    "12",
    "[]",
]


def _shape(value):
    """The value with every leaf's exact type, so 1 == 1.0 == True can't pass."""
    if isinstance(value, dict):
        return {k: _shape(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_shape(v) for v in value]
    return (type(value).__name__, repr(value))


@pytest.fixture
def reload_ws_json(monkeypatch):
    """Rebind ``ws_json.loads`` under a test's setting; restore the default after."""
    yield lambda: importlib.reload(ws_json)
    monkeypatch.delenv(ws_json.FAST_JSON_ENV, raising=False)
    importlib.reload(ws_json)


# ------------------------------------------------------------ the parser ----


@pytest.mark.parametrize("raw", CORPUS)
def test_the_fast_parser_returns_exactly_what_json_loads_returns(raw):
    for form in (raw, raw.encode("utf-8")):
        assert _shape(ws_json._fast_loads(form)) == _shape(json.loads(form))


def test_inputs_the_fast_parser_refuses_take_json_loads():
    lone = '{"s":"\\ud800"}'  # a lone surrogate escape: stdlib accepts it
    assert _shape(ws_json._fast_loads(lone)) == _shape(json.loads(lone))
    special = '{"a":NaN,"b":Infinity,"c":-Infinity}'
    fast, slow = ws_json._fast_loads(special), json.loads(special)
    assert math.isnan(fast["a"]) and math.isnan(slow["a"])
    assert fast["b"] == slow["b"] == math.inf and fast["c"] == slow["c"] == -math.inf


@pytest.mark.parametrize("raw", ['{"a":', "", '{"a":1} x', "{'a': 1}", "[1,]", "PONG"])
def test_malformed_frames_raise_what_json_loads_raises(raw):
    with pytest.raises(json.JSONDecodeError):
        json.loads(raw)
    with pytest.raises(json.JSONDecodeError):
        ws_json._fast_loads(raw)


def test_a_non_text_frame_raises_type_error_as_before():
    with pytest.raises(TypeError):
        ws_json._fast_loads(None)


def test_the_default_binds_the_fast_parser(monkeypatch, reload_ws_json):
    monkeypatch.delenv(ws_json.FAST_JSON_ENV, raising=False)
    reload_ws_json()
    assert ws_json.fast_json_enabled() is True
    assert ws_json.loads is ws_json._fast_loads


@pytest.mark.parametrize("raw", ["0", " 0 "])
def test_ws_fast_json_0_is_exactly_json_loads(monkeypatch, reload_ws_json, raw):
    monkeypatch.setenv(ws_json.FAST_JSON_ENV, raw)
    reload_ws_json()
    assert ws_json.fast_json_enabled() is False
    assert ws_json.loads is json.loads


# ----------------------------------------------------- Kalshi socket frames ----


def test_kalshi_frames_decode_through_ws_json_with_the_old_skip_clause():
    source = inspect.getsource(kalshi_service)
    assert "data = ws_json.loads(raw)" in source
    assert "json.loads(raw)" not in source.replace("ws_json.loads(raw)", "")
    # The skip clause is unchanged: a malformed frame is still skipped.
    assert "except (json.JSONDecodeError, TypeError):" in source


# ------------------------------------------------ socket-consumer engines ----


def _engine_kwargs(monkeypatch, **factory_kwargs):
    seen = {}

    def fake_create_async_engine(url, **kwargs):
        seen.update(kwargs)
        return object()

    monkeypatch.setattr(task_base, "create_async_engine", fake_create_async_engine)
    task_base._get_task_engine(**factory_kwargs)
    return seen


def test_a_socket_consumer_engine_decodes_jsonb_with_the_fast_parser(monkeypatch):
    monkeypatch.delenv(ws_json.FAST_JSON_ENV, raising=False)
    kwargs = _engine_kwargs(monkeypatch, retain_full_pool=True)
    assert kwargs["json_deserializer"] is ws_json.loads
    kwargs = _engine_kwargs(monkeypatch, retain_full_pool=True, pool_pre_ping=False)
    assert kwargs["json_deserializer"] is ws_json.loads


def test_every_other_engine_is_asked_what_it_was_asked_before(monkeypatch):
    monkeypatch.delenv(ws_json.FAST_JSON_ENV, raising=False)
    kwargs = _engine_kwargs(monkeypatch)
    assert "json_deserializer" not in kwargs
    assert set(kwargs) == {
        "pool_pre_ping",
        "pool_size",
        "max_overflow",
        "pool_recycle",
        "connect_args",
    }


def test_ws_fast_json_0_gives_socket_consumers_the_stdlib_decoder(monkeypatch):
    monkeypatch.setenv(ws_json.FAST_JSON_ENV, "0")
    kwargs = _engine_kwargs(monkeypatch, retain_full_pool=True)
    assert "json_deserializer" not in kwargs


# ------------------------------------------------------ venue child GC ----


@pytest.fixture
def thresholds(monkeypatch):
    """Record set_threshold calls instead of changing this test process's GC."""
    calls = []
    monkeypatch.setattr(gc, "set_threshold", lambda *args: calls.append(args))
    monkeypatch.setattr(gc, "get_threshold", lambda: (700, 10, 10))
    return calls


def test_by_default_a_venue_child_raises_only_generation_0(monkeypatch, thresholds):
    monkeypatch.delenv(run_kalshi_ws.WS_GC_GEN0_ENV, raising=False)
    assert run_kalshi_ws._tune_gc_young_generation("kalshi") == 5_000
    assert thresholds == [(5_000, 10, 10)]


def test_ws_gc_gen0_0_keeps_the_interpreter_thresholds(monkeypatch, thresholds):
    monkeypatch.setenv(run_kalshi_ws.WS_GC_GEN0_ENV, "0")
    assert run_kalshi_ws._tune_gc_young_generation("polymarket") is None
    assert thresholds == []


def test_ws_gc_gen0_takes_another_value(monkeypatch, thresholds):
    monkeypatch.setenv(run_kalshi_ws.WS_GC_GEN0_ENV, " 20000 ")
    assert run_kalshi_ws._tune_gc_young_generation("polymarket") == 20_000
    assert thresholds == [(20_000, 10, 10)]


def test_a_non_integer_uses_the_default_with_one_warning(
    monkeypatch, thresholds, caplog
):
    monkeypatch.setenv(run_kalshi_ws.WS_GC_GEN0_ENV, "lots")
    with caplog.at_level(logging.WARNING, logger=run_kalshi_ws.logger.name):
        assert run_kalshi_ws._tune_gc_young_generation("kalshi") == 5_000
    assert thresholds == [(5_000, 10, 10)]
    assert [r.levelno for r in caplog.records] == [logging.WARNING]


def test_a_collector_failure_never_stops_the_venue(monkeypatch):
    monkeypatch.delenv(run_kalshi_ws.WS_GC_GEN0_ENV, raising=False)

    def broken(*_args):
        raise RuntimeError("collector says no")

    monkeypatch.setattr(gc, "set_threshold", broken)
    assert run_kalshi_ws._tune_gc_young_generation("kalshi") is None


@pytest.mark.parametrize("venue", run_kalshi_ws.HEARTBEAT_ARMS)
def test_run_venue_tunes_gc_before_any_arm_starts(monkeypatch, venue):
    seen, started = [], []

    class Tuned(Exception):
        pass

    def tune(name):
        seen.append(name)
        raise Tuned

    def arm():
        # Recorded when the arm is CALLED (task creation), not when it runs.
        started.append(True)
        return asyncio.sleep(0)

    monkeypatch.setattr(run_kalshi_ws, "_tune_gc_young_generation", tune)
    for name in (
        "run_kalshi",
        "run_kalshi_shadow",
        "run_polymarket",
        "run_polymarket_shadow",
    ):
        monkeypatch.setattr(run_kalshi_ws, name, arm)
    with pytest.raises(Tuned):
        asyncio.run(run_kalshi_ws.run_venue(venue))
    assert seen == [venue] and started == []
