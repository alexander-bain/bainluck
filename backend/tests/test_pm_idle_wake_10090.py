"""Virtual clocks/actual PM callbacks prove idle progress and ownership, not speed."""

import ast
import asyncio
import inspect
import os
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Optional

import pytest

from app.tasks import live_blend_refresh as blend
from app.tasks import polymarket_ws as pm
from tests.test_polymarket_withdrawal_speed_10651 import ROOT, compile_functions, rig

pytestmark = pytest.mark.asyncio


class Clock:
    def __init__(self, monkeypatch, actions):
        self.t = 0.0
        self.actions = list(actions)
        self.wake, self.stop = asyncio.Event(), asyncio.Event()
        self.prices, self.calls = {}, []
        self.work = 0
        self.sleep = asyncio.sleep
        monkeypatch.setattr(blend, "_mono", lambda: self.t)
        monkeypatch.setattr(asyncio, "sleep", self.advance_sleep)
        monkeypatch.setattr(asyncio, "timeout", self.timeout)

    def advance(self, deadline):
        while self.actions and self.actions[0][0] <= deadline:
            self.t, action = self.actions.pop(0)
            if action == "stop":
                self.stop.set()
            else:
                self.prices[1] = action
                self.wake.set()
        self.t = deadline

    async def advance_sleep(self, seconds):
        self.advance(self.t + seconds)
        await self.sleep(0)

    @asynccontextmanager
    async def timeout(self, seconds):
        deadline = self.t + seconds
        if not self.wake.is_set():
            self.advance(
                self.actions[0][0]
                if self.actions and self.actions[0][0] < deadline
                else deadline
            )
        if not self.wake.is_set():
            raise TimeoutError
        yield

    async def run(self, *, count=1, fail=False, debt=False, work_seconds=0):
        actual, pending = 0, debt

        async def flush(started):
            nonlocal actual, pending
            assert started == self.t
            if self.prices or pending:
                self.work += 1
                actual += 1
                self.calls.append((started, dict(self.prices), pending))
                if actual == 1 and fail:
                    self.advance(self.t + 0.07)
                    return False
                self.prices.clear()
                self.advance(self.t + work_seconds)
                pending = False
                if actual == count:
                    self.stop.set()
            await self.sleep(0)
            return True

        cadence = blend.run_flush_cadence
        if os.environ.get("PM_IDLE_PARENT"):
            source = Path(os.environ["PM_IDLE_PARENT"]).read_text()
            nodes = [
                n
                for n in ast.parse(source).body
                if isinstance(n, ast.AsyncFunctionDef) and n.name == "run_flush_cadence"
            ]
            namespace = {"Optional": Optional, "_mono": lambda: self.t}
            exec(
                compile(ast.Module(body=nodes, type_ignores=[]), "parent", "exec"),
                namespace,
            )
            cadence = namespace["run_flush_cadence"]
        kwargs = dict(stop=self.stop, failed_retry_interval_s=2.0)
        if "wake" in inspect.signature(cadence).parameters:
            kwargs.update(wake=self.wake, work_count=lambda: self.work)
        await cadence(flush, 0.25, **kwargs)


async def test_post_idle_quote_flushes_at_receipt_not_next_empty_timer_phase(
    monkeypatch,
):
    c = Clock(monkeypatch, [(0.751, 0.61)])
    await c.run()
    # Empty probes at .25/.5/.75 cannot spend actual write budget. Parent waits1.0.
    assert c.calls == [(0.751, {1: 0.61}, False)]


async def test_burst_coalesces_and_actual_starts_remain_one_period_apart(monkeypatch):
    c = Clock(
        monkeypatch,
        [(0.751, 0.61), (0.752, 0.62), (0.753, 0.63), (0.754, 0.64), (1.002, 0.65)],
    )
    await c.run(count=3)
    assert [call[0] for call in c.calls] == pytest.approx([0.751, 1.001, 1.251])
    assert [call[1][1] for call in c.calls] == [0.61, 0.64, 0.65]
    assert all(b[0] - a[0] >= 0.25 - 1e-12 for a, b in zip(c.calls, c.calls[1:]))


async def test_failed_attempt_retains_full_retry_despite_fresh_wakes(monkeypatch):
    c = Clock(monkeypatch, [(0.751, 0.61), (0.752, 0.62), (1.0, 0.63)])
    await c.run(count=2, fail=True)
    assert [call[0] for call in c.calls] == pytest.approx([0.751, 2.821])
    assert c.calls[-1][1] == {1: 0.63}


async def test_pending_only_timer_progress_spends_actual_budget(monkeypatch):
    c = Clock(monkeypatch, [(0.251, 0.61)])
    await c.run(count=2, debt=True)
    assert c.calls == [(0.25, {}, True), (0.5, {1: 0.61}, False)]


async def test_stop_in_budget_wait_prevents_flush_and_retains_final_drain_buffer(
    monkeypatch,
):
    c = Clock(monkeypatch, [(0.751, 0.61), (0.752, 0.62), (0.8, "stop")])
    await c.run(count=2)
    assert c.calls == [(0.751, {1: 0.61}, False)] and c.prices == {1: 0.62}


def callbacks():
    p = rig(batch={}, books={}, mapping={1: 10, 2: 10})
    p.release.set()
    marks = []
    p.ns.update(
        asset_to_market={"yes": 10, "open": 90},
        asset_to_outcome={"yes": 1},
        open_asset_to_market={"open": 90},
        open_asset_to_outcome={"open": 900},
        open_asset_mirrors={},
        books_by_asset={},
        routing_generation=0,
        with_complements=pm.with_complements,
        books_with_complements=pm.books_with_complements,
        trade_sets_a_price=pm.trade_sets_a_price,
        trade_prints_outside_wide_book=pm.trade_prints_outside_wide_book,
        _poly_book_is_untradeable=pm._poly_book_is_untradeable,
        tail_receipts=SimpleNamespace(
            note_raw=lambda _: None,
            note_input=lambda *args: marks.append(args) or SimpleNamespace(args=args),
            stage=lambda _: None,
        ),
    )
    p.ns["open_complement_of"].update({900: 901, 901: 900})
    compile_functions(
        ROOT / "app/tasks/polymarket_ws.py",
        ["handle_price", "handle_trade", "_tick_targets", "_note_raw", "_mark_input"],
        p.ns,
    )
    return p, marks


@pytest.mark.parametrize("kind", ["price", "trade", "withdrawal"])
async def test_actual_callback_wakes_complete_game_cohort_retaining_venue_time(kind):
    p, marks = callbacks()
    msg = {"asset_id": "yes", "timestamp": "1720000123456"}
    if kind == "trade":
        msg.update(price="0.61", size="10")
        await p.ns["handle_trade"](msg)
    else:
        msg.update(
            best_bid="0.1" if kind == "withdrawal" else "0.60",
            best_ask="0.9" if kind == "withdrawal" else "0.62",
        )
        await p.ns["handle_price"](msg)
    assert p.ns["catalog_boundary"].flush_wake.is_set()
    if kind == "withdrawal":
        assert set(p.ns["withdraw_buffer"]) == {1, 2} and not marks
    else:
        assert p.ns["price_buffer"] == {1: 0.61, 2: 0.39}
        assert {m[1] for m in marks} == {1, 2}
        assert {m[-1] for m in marks} == {msg["timestamp"]}


@pytest.mark.parametrize(
    "kind", ["bad_price", "small_trade", "standalone", "old_generation"]
)
async def test_refused_or_standalone_input_does_not_wake_game_cadence(kind):
    p, marks = callbacks()
    msg = {"asset_id": "yes", "timestamp": "1720000123456"}
    if kind == "small_trade":
        msg.update(price="0.61", size="0.1")
        await p.ns["handle_trade"](msg)
    else:
        msg.update(best_bid="bad" if kind == "bad_price" else "0.60", best_ask="0.62")
        if kind == "standalone":
            msg["asset_id"] = "open"
        if kind == "old_generation":
            await p.ns["buffer_lock"].acquire()
            task = asyncio.create_task(p.ns["handle_price"](msg))
            await asyncio.sleep(0)
            p.ns["routing_generation"] = 1
            p.ns["buffer_lock"].release()
            await task
        else:
            await p.ns["handle_price"](msg)
    assert not p.ns["catalog_boundary"].flush_wake.is_set()
    if kind != "standalone":
        assert not p.ns["price_buffer"] and not marks


@pytest.mark.parametrize(
    "work", ["empty", "price", "withdrawal", "pending", "standalone"]
)
async def test_actual_pm_flush_spends_budget_only_on_game_or_owed_work(work):
    p, _ = callbacks()
    if work == "price":
        p.ns["price_buffer"].update({1: 0.61, 2: 0.39})
    elif work == "withdrawal":
        p.ns["withdraw_buffer"].update({1: (0.1, 0.9), 2: (0.1, 0.9)})
    elif work == "pending":
        p.ns["blend_refresher"].pending_event_ids = lambda: frozenset({10})
    elif work == "standalone":
        p.ns["price_buffer"].update({900: 0.61, 901: 0.39})
        p.ns["withdraw_buffer"].update({900: (0.1, 0.9), 901: (0.1, 0.9)})
    await p.ns["flush_prices"](flush_started=1000)
    await p.ns["catalog_boundary"].join_stamps()
    assert p.ns["catalog_boundary"].flush_work == (
        0 if work in {"empty", "standalone"} else 1
    )


async def test_slow_opted_flush_never_overlaps_and_retains_ticks_during_work(
    monkeypatch,
):
    c = Clock(monkeypatch, [(0.751, 0.61), (0.8, 0.62)])
    await c.run(count=2, work_seconds=0.4)
    assert [call[0] for call in c.calls] == pytest.approx([0.751, 1.151])
    assert [call[1][1] for call in c.calls] == [0.61, 0.62]


async def test_cancelled_idle_wait_does_not_leave_a_flush_owner_or_late_call():
    wake, stop = asyncio.Event(), asyncio.Event()
    calls = []

    async def flush(started):
        calls.append(started)

    owner = asyncio.create_task(
        blend.run_flush_cadence(
            flush,
            120,
            stop=stop,
            wake=wake,
            work_count=lambda: 0,
        )
    )
    await asyncio.sleep(0)
    assert not calls
    owner.cancel()
    with pytest.raises(asyncio.CancelledError):
        await owner
    wake.set()
    await asyncio.sleep(0)
    assert not calls and owner.done()
