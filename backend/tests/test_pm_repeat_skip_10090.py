"""#10090: a repeated top of book changes nothing a reader sees, so it is skipped.

Production 2026-10-30 23:23Z: both venue loops were CPU-saturated (PM 0.96-0.97)
and on an in-play capture 98.8 % of the quotes reaching `handle_price` repeated
the last book handled for their token. Below the raw count, a repeat inside
`PM_WS_REPEAT_SKIP_MS` of the last handled book skips the mark, receipts,
observation token, price re-buffer and flush wake — and still feeds
"confirmed at" exactly as `_mark_input` would. These drive the REAL
`handle_price` / `handle_trade` / `_mark_input` source in the consumer's rig.
"""

import contextlib
import itertools
import logging
from types import SimpleNamespace


from app.tasks import live_blend_refresh as blend
from app.tasks import polymarket_ws as pm
from tests.test_polymarket_withdrawal_speed_10651 import ROOT, compile_functions, rig

TS = "1720000123456"


class Confirmed:
    def __init__(self):
        self.notes = []

    def note_input(self, event_id, outcome_id, probability, recv_wall):
        self.notes.append((event_id, outcome_id, probability, recv_wall))

    def note_mark(self, mark):
        self.notes.append((mark.args[0], mark.args[1], mark.args[2], "mark"))

    def note_withdrawal(self, *_args):
        pass


def callbacks(monkeypatch, window_s=0.25):
    clock = SimpleNamespace(t=1000.0)
    monkeypatch.setattr(blend, "_mono", lambda: clock.t)
    monkeypatch.setattr(blend, "_wall", lambda: 5000.0 + clock.t)
    p = rig(batch={}, books={}, mapping={1: 10, 2: 10})
    p.release.set()
    marks, raws = [], []
    confirmed = Confirmed()
    p.ns.update(
        asset_to_market={"yes": 10},
        asset_to_outcome={"yes": 1},
        open_asset_to_market={},
        open_asset_to_outcome={},
        open_asset_mirrors={},
        books_by_asset={},
        routing_generation=0,
        contextlib=contextlib,
        with_complements=pm.with_complements,
        books_with_complements=pm.books_with_complements,
        trade_sets_a_price=pm.trade_sets_a_price,
        trade_prints_outside_wide_book=pm.trade_prints_outside_wide_book,
        _poly_book_is_untradeable=pm._poly_book_is_untradeable,
        REPEAT_SKIP_PRUNE_S=pm.REPEAT_SKIP_PRUNE_S,
        repeat_skip_s=window_s,
        repeat_memo={},
        leg_writes={},
        leg_write_counter=itertools.count(1),
        repeat_memo_pruned=[0.0],
        tail_receipts=SimpleNamespace(
            note_raw=raws.append,
            note_input=lambda *args: marks.append(args) or SimpleNamespace(args=args),
            stage=lambda _: None,
            confirmed=confirmed,
        ),
    )
    p.ns["input_marks"].clear()
    compile_functions(
        ROOT / "app/tasks/polymarket_ws.py",
        ["handle_price", "handle_trade", "_tick_targets", "_note_raw", "_mark_input",
         "_skip_repeat", "_repeat_holds", "_note_repeat_skipped", "handle_price_repeat",
         "_remember_handled"],
        p.ns,
    )
    return SimpleNamespace(p=p, ns=p.ns, clock=clock, marks=marks, raws=raws,
                           confirmed=confirmed)


def quote(bid="0.60", ask="0.62", **extra):
    return {"asset_id": "yes", "timestamp": TS, "best_bid": bid, "best_ask": ask, **extra}


async def handled_once(r):
    await r.ns["handle_price"](quote())
    assert r.ns["price_buffer"] == {1: 0.61, 2: 0.39}
    assert len(r.marks) == 2
    # A flush wrote the pair (buffer emptied) and the wake was consumed.
    r.ns["price_buffer"].clear()
    r.ns["catalog_boundary"].flush_wake.clear()
    r.marks.clear()
    r.confirmed.notes.clear()
    r.clock.t += 0.1


def assert_handled(r):
    assert len(r.marks) == 2
    assert r.ns["price_buffer"] == {1: 0.61, 2: 0.39}
    assert r.ns["catalog_boundary"].flush_wake.is_set()


async def test_a_repeat_inside_the_window_skips_everything_but_confirmed_at(monkeypatch):
    r = callbacks(monkeypatch)
    await handled_once(r)
    await r.ns["handle_price"](quote())
    assert r.marks == []
    assert r.ns["price_buffer"] == {}
    assert not r.ns["catalog_boundary"].flush_wake.is_set()
    assert r.ns["stats"]["repeats_skipped"] == 1
    # "confirmed at" is fed exactly as `_mark_input` feeds it: both blend legs,
    # their event, their prices, at this receipt.
    assert r.confirmed.notes == [(10, 1, 0.61, 5000.0 + r.clock.t), (10, 2, 0.39, 5000.0 + r.clock.t)]
    # The raw message is counted on both, against the same game.
    assert r.raws == [10, 10]


async def test_a_repeat_with_the_leg_still_buffered_at_its_price_is_skipped(monkeypatch):
    r = callbacks(monkeypatch)
    await r.ns["handle_price"](quote())
    r.marks.clear()
    r.clock.t += 0.1
    await r.ns["handle_price"](quote())
    assert r.marks == [] and r.ns["stats"]["repeats_skipped"] == 1


async def test_switch_zero_is_todays_path(monkeypatch):
    r = callbacks(monkeypatch, window_s=0.0)
    await handled_once(r)
    await r.ns["handle_price"](quote())
    assert_handled(r)
    assert r.ns["stats"]["repeats_skipped"] == 0
    assert r.ns["repeat_memo"] == {} and r.ns["leg_writes"] == {}


async def test_a_repeat_after_the_window_is_handled(monkeypatch):
    r = callbacks(monkeypatch)
    await handled_once(r)
    r.clock.t += 0.25
    await r.ns["handle_price"](quote())
    assert_handled(r)


async def test_a_changed_book_is_handled(monkeypatch):
    r = callbacks(monkeypatch)
    await handled_once(r)
    await r.ns["handle_price"](quote(bid="0.61", ask="0.63"))
    assert len(r.marks) == 2 and r.ns["price_buffer"] == {1: 0.62, 2: 0.38}


async def test_a_book_snapshot_and_the_first_quote_after_it_are_always_handled(monkeypatch):
    r = callbacks(monkeypatch)
    await handled_once(r)
    await r.ns["handle_price"](quote(book_snapshot=True))
    assert_handled(r)
    r.ns["price_buffer"].clear()
    r.marks.clear()
    await r.ns["handle_price"](quote())
    assert_handled(r)
    assert r.ns["stats"]["repeats_skipped"] == 0


async def test_a_routing_change_reopens_the_token(monkeypatch):
    r = callbacks(monkeypatch)
    await handled_once(r)
    r.ns["routing_generation"] += 1
    await r.ns["handle_price"](quote())
    assert_handled(r)


async def test_a_trade_on_the_leg_reopens_the_token_even_after_its_write(monkeypatch):
    r = callbacks(monkeypatch)
    await handled_once(r)
    await r.ns["handle_trade"]({"asset_id": "yes", "timestamp": TS, "price": "0.65", "size": "10"})
    # Its flush wrote it and left the buffer: only the write stamp remembers.
    r.ns["price_buffer"].clear()
    r.marks.clear()
    await r.ns["handle_price"](quote())
    assert_handled(r)


async def test_another_buffered_price_on_the_leg_is_never_skipped_over(monkeypatch):
    r = callbacks(monkeypatch)
    await handled_once(r)
    r.ns["price_buffer"][2] = 0.5
    await r.ns["handle_price"](quote())
    assert len(r.marks) == 2 and r.ns["price_buffer"] == {1: 0.61, 2: 0.39}


async def test_a_buffered_withdrawal_on_the_leg_is_never_skipped_over(monkeypatch):
    r = callbacks(monkeypatch)
    await handled_once(r)
    r.ns["withdraw_buffer"][1] = (0.1, 0.9)
    await r.ns["handle_price"](quote())
    assert_handled(r)
    assert 1 not in r.ns["withdraw_buffer"]


async def test_a_write_from_another_path_reopens_the_token(monkeypatch):
    # A mirror or complement token buffering the same leg stamps it.
    r = callbacks(monkeypatch)
    await handled_once(r)
    r.ns["leg_writes"][2] = next(r.ns["leg_write_counter"])
    await r.ns["handle_price"](quote())
    assert_handled(r)


async def test_a_wide_book_is_never_remembered_or_skipped(monkeypatch):
    r = callbacks(monkeypatch)
    for _ in range(2):
        await r.ns["handle_price"](quote(bid="0.1", ask="0.9"))
        assert set(r.ns["withdraw_buffer"]) == {1, 2}
        r.ns["withdraw_buffer"].clear()
        r.clock.t += 0.01
    assert r.ns["repeat_memo"] == {} and r.ns["stats"]["repeats_skipped"] == 0


async def test_a_wide_book_between_repeats_reopens_the_token(monkeypatch):
    r = callbacks(monkeypatch)
    await handled_once(r)
    await r.ns["handle_price"](quote(bid="0.1", ask="0.9"))
    r.ns["withdraw_buffer"].clear()  # the withdrawal flushed
    await r.ns["handle_price"](quote())
    assert_handled(r)


async def test_the_memo_and_stamps_are_pruned_to_live_entries(monkeypatch):
    r = callbacks(monkeypatch)
    await r.ns["handle_price"](quote())
    assert set(r.ns["repeat_memo"]) == {"yes"} and set(r.ns["leg_writes"]) == {1, 2}
    r.ns["asset_to_market"]["no"] = 10
    r.ns["asset_to_outcome"]["no"] = 7
    r.clock.t += 5.0
    await r.ns["handle_price"]({**quote(), "asset_id": "no"})
    assert set(r.ns["repeat_memo"]) == {"no"}
    assert set(r.ns["leg_writes"]) == {7}


def test_switch_reads_milliseconds_default_250_and_zero_or_junk_is_off(monkeypatch, caplog):
    monkeypatch.delenv("PM_WS_REPEAT_SKIP_MS", raising=False)
    assert pm._repeat_skip_window_s() == 0.25
    for raw, expected in (("", 0.25), ("0", 0.0), ("-5", 0.0), ("500", 0.5), ("nan", 0.0)):
        monkeypatch.setenv("PM_WS_REPEAT_SKIP_MS", raw)
        assert pm._repeat_skip_window_s() == expected, raw
    monkeypatch.setenv("PM_WS_REPEAT_SKIP_MS", "fast")
    with caplog.at_level(logging.WARNING):
        assert pm._repeat_skip_window_s() == 0.0
    assert "PM_WS_REPEAT_SKIP_MS" in caplog.text


def test_the_minute_line_prints_the_skipped_count(caplog):
    stats = {"price_updates": 0, "trade_updates": 0, "resolutions": 0, "errors": 0,
             "repeats_skipped": 4321}
    blend_stats = {"stamped": 0, "no_reading": 0, "throttled": 0, "errors": 0}
    with caplog.at_level(logging.INFO):
        pm._log_stats_line(stats, {}, blend_stats)
    assert "repeats_skipped=4321" in caplog.text


async def test_a_snapshot_that_prices_nothing_still_reopens_the_token(monkeypatch):
    # A snapshot at a terminal book writes no leg, so no write stamp can say
    # it happened; the quote after it is still handled.
    r = callbacks(monkeypatch)
    await handled_once(r)
    await r.ns["handle_price"](quote(bid="1", ask="1", book_snapshot=True))
    assert r.marks == []
    await r.ns["handle_price"](quote())
    assert_handled(r)


async def test_a_wide_book_on_the_complement_token_reopens_the_token(monkeypatch):
    # Another token's wide book withdraws this token's legs; once that
    # withdrawal has flushed, only the write stamp remembers it.
    r = callbacks(monkeypatch)
    r.ns["asset_to_market"]["no"] = 10
    r.ns["asset_to_outcome"]["no"] = 2
    await handled_once(r)
    await r.ns["handle_price"]({**quote(bid="0.1", ask="0.9"), "asset_id": "no"})
    assert set(r.ns["withdraw_buffer"]) == {1, 2}
    r.ns["withdraw_buffer"].clear()
    r.ns["catalog_boundary"].flush_wake.clear()
    await r.ns["handle_price"](quote())
    assert_handled(r)
