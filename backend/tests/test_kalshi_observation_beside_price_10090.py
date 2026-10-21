"""Fresh book observations must not wait behind an unrelated price write."""

import ast
import asyncio
import time
from pathlib import Path
from types import SimpleNamespace as NS
import pytest
from app.tasks.ws_observation_drain import ObservationDrain
from tests.test_kalshi_book_observation_10090 import consumer_rig
from tests.test_fresh_observation_preview_10090 import (
    preview_enabled,
)  # noqa: F401; autouse fixture
from tests.test_blend_preview_display_before_persist_195 import _blends


def timed_rig(monkeypatch, *, serial=False, period=0.01):
    import app.tasks.kalshi_ws as consumer

    rig = consumer_rig(monkeypatch)
    entered, release = asyncio.Event(), asyncio.Event()

    async def price_work(_):
        entered.set()
        await release.wait()
        return "persisted"

    drain = ObservationDrain(
        rig.ns["flush_book_observations"],
        lambda: bool(rig.ns["book_observation_pending"]),
        rig.ns["book_observation_wake"],
        period,
    )
    gate = asyncio.Lock()
    rig.ns.update(
        flush_gate=gate,
        time=time,
        flush_prices=price_work,
        observation_drain=drain,
        flush_timings=NS(flushed=lambda _: None),
    )
    tree = ast.parse(Path(consumer.__file__).read_text())
    node = next(
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.AsyncFunctionDef) and n.name == "timed_flush"
    )
    exec(
        compile(ast.Module(body=[node], type_ignores=[]), consumer.__file__, "exec"),
        rig.ns,
    )
    if serial:
        # Exact prior ordering, retained as a causal parent control.
        async def old_timed(started):
            async with gate:
                result = await price_work(started)
                await rig.ns["flush_book_observations"]()
                return result

        rig.ns["timed_flush"] = old_timed
    rig.ns["event_id_by_outcome"][999] = 2
    rig.ns["price_buffer"][999] = (0.8, 0.79, 0.81)
    rig.entered, rig.release, rig.gate, rig.drain = entered, release, gate, drain
    return rig


async def feed(rig):
    for payload in rig.payloads:
        await rig.ns["handle_book_observation"](payload, rig.client)


async def until(predicate):
    async with asyncio.timeout(1):
        while not predicate():
            await asyncio.sleep(0.001)


@pytest.mark.parametrize("serial", [True, False])
async def test_serial_waits_but_candidate_publishes_during_unrelated_write(
    monkeypatch, serial
):
    rig = timed_rig(monkeypatch, serial=serial)
    task = asyncio.create_task(rig.ns["timed_flush"](time.monotonic()))
    await rig.entered.wait()
    await feed(rig)
    if serial:
        await asyncio.sleep(0.02)
        assert not _blends(rig.frames)
        assert len(rig.ns["book_observation_pending"]) == 2
    else:
        await until(lambda: len(_blends(rig.frames)) == 1)
        assert not task.done() and rig.gate.locked()
    rig.release.set()
    assert await task == "persisted"
    assert len(_blends(rig.frames)) == 1
    assert not rig.session.updates and not rig.committed and not rig.r._history


async def test_capacity_restoration_delivers_frozen_input_without_new_tick(monkeypatch):
    rig = timed_rig(monkeypatch)
    slots = 0
    while not rig.r._session_slots.locked():
        await rig.r._session_slots.acquire()
        slots += 1
    task = asyncio.create_task(rig.ns["timed_flush"](time.monotonic()))
    await rig.entered.wait()
    await feed(rig)
    frozen = dict(rig.ns["book_observation_pending"])
    await until(lambda: rig.ns["prices"].flush_work > 0)
    assert not _blends(rig.frames)
    assert rig.ns["book_observation_pending"] == frozen
    rig.held._database_bound += 10
    for _ in range(slots):
        rig.r._session_slots.release()
    await until(lambda: len(_blends(rig.frames)) == 1)
    from datetime import datetime

    assert (
        datetime.fromisoformat(
            _blends(rig.frames)[0]["display_observed_at"]
        ).timestamp()
        == rig.bound
    )
    assert not task.done()
    rig.release.set()
    await task


async def test_read_failure_retains_frozen_observation_for_retry(monkeypatch):
    rig = timed_rig(monkeypatch)
    original = rig.r._read_groups
    attempts = 0

    async def unavailable_once(*args, **kwargs):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise TimeoutError("bounded observation read")
        return await original(*args, **kwargs)

    rig.r._read_groups = unavailable_once
    task = asyncio.create_task(rig.ns["timed_flush"](time.monotonic()))
    await rig.entered.wait()
    await feed(rig)
    frozen = dict(rig.ns["book_observation_pending"])
    await until(lambda: attempts == 1)
    assert rig.ns["book_observation_pending"] == frozen
    rig.held._database_bound += 10
    await until(lambda: len(_blends(rig.frames)) == 1)
    from datetime import datetime

    assert (
        datetime.fromisoformat(
            _blends(rig.frames)[0]["display_observed_at"]
        ).timestamp()
        == rig.bound
    )
    assert attempts == 2 and rig.r.preview_stats["publish_errors"] == 1
    rig.release.set()
    await task


async def test_retry_restore_never_overwrites_newer_arrival(monkeypatch):
    rig = timed_rig(monkeypatch)
    entered, release = asyncio.Event(), asyncio.Event()

    async def refused(*_):
        entered.set()
        await release.wait()
        return False

    rig.r.preview_accepted_observations = refused
    await feed(rig)
    task = asyncio.create_task(rig.ns["flush_book_observations"]())
    await entered.wait()
    rig.held._database_bound += 0.25
    await feed(rig)
    newer = dict(rig.ns["book_observation_pending"])
    release.set()
    await task
    assert rig.ns["book_observation_pending"] == newer
    assert all(entry[2] == rig.bound + 0.25 for entry in newer.values())


@pytest.mark.parametrize("busy", ["price", "stamp", "unknown-stamp"])
async def test_same_event_precedence_retains_until_owner_releases(monkeypatch, busy):
    rig = timed_rig(monkeypatch)
    if busy == "price":
        rig.ns["price_buffer"][rig.rows[0].id] = (0.8, 0.79, 0.81)
    else:
        rig.ns["prices"].stamping = NS(done=lambda: False)
        rig.ns["prices"].held_events = lambda _: (
            None if busy == "unknown-stamp" else {1}
        )
    task = asyncio.create_task(rig.ns["timed_flush"](time.monotonic()))
    await rig.entered.wait()
    await feed(rig)
    frozen = dict(rig.ns["book_observation_pending"])
    await asyncio.sleep(0.02)
    assert not _blends(rig.frames) and rig.ns["book_observation_pending"] == frozen
    rig.ns["price_buffer"].pop(rig.rows[0].id, None)
    rig.ns["prices"].stamping = None
    await until(lambda: len(_blends(rig.frames)) == 1)
    rig.release.set()
    await task


@pytest.mark.parametrize("change", ["settled", "signature", "admission"])
async def test_final_send_refuses_authority_change_during_read(monkeypatch, change):
    rig = timed_rig(monkeypatch)
    entered, release = asyncio.Event(), asyncio.Event()
    original = rig.r._publish_previews

    async def delayed(*args, **kwargs):
        entered.set()
        await release.wait()
        await original(*args, **kwargs)

    rig.r._publish_previews = delayed
    task = asyncio.create_task(rig.ns["timed_flush"](time.monotonic()))
    await rig.entered.wait()
    await feed(rig)
    await entered.wait()
    if change == "settled":
        rig.ns["prices"].settled_market_ids.add(10)
    elif change == "signature":
        rig.signatures[rig.payloads[0]["market_ticker"]] = object()
    else:
        rig.r._admission = NS(released={})
    release.set()
    rig.release.set()
    await task
    assert not _blends(rig.frames)


async def test_scope_swap_waits_for_read_and_pump_join(monkeypatch):
    rig = timed_rig(monkeypatch)
    entered, release, swapped = asyncio.Event(), asyncio.Event(), asyncio.Event()
    original = rig.r._publish_previews

    async def delayed(*args, **kwargs):
        entered.set()
        await release.wait()
        await original(*args, **kwargs)

    rig.r._publish_previews = delayed
    task = asyncio.create_task(rig.ns["timed_flush"](time.monotonic()))
    await rig.entered.wait()
    await feed(rig)
    await entered.wait()
    rig.release.set()

    async def swap():
        async with rig.gate:
            rig.ns["event_id_by_outcome"].clear()
            swapped.set()

    swapping = asyncio.create_task(swap())
    await asyncio.sleep(0.01)
    assert not swapped.is_set()
    release.set()
    await task
    await swapping
    assert len(_blends(rig.frames)) == 1 and swapped.is_set()
    assert not any(
        t.get_name() == "kalshi-book-observations" for t in asyncio.all_tasks()
    )


async def test_repeated_cancel_joins_pump_and_restores_pending(monkeypatch):
    rig = timed_rig(monkeypatch)
    entered = asyncio.Event()

    async def delayed(*_, **__):
        entered.set()
        await asyncio.Event().wait()

    rig.r._publish_previews = delayed
    task = asyncio.create_task(rig.ns["timed_flush"](time.monotonic()))
    await rig.entered.wait()
    await feed(rig)
    frozen = dict(rig.ns["book_observation_pending"])
    await entered.wait()
    await rig.ns["buffer_lock"].acquire()
    task.cancel()
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    task.cancel()
    rig.ns["buffer_lock"].release()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert rig.ns["book_observation_pending"] == frozen
    assert not rig.gate.locked() and not _blends(rig.frames)
    assert not any(
        t.get_name() == "kalshi-book-observations" for t in asyncio.all_tasks()
    )


async def test_cadence_survives_flush_boundaries_without_overlap():
    now, starts, active = [10.0], [], [0]

    async def drain():
        active[0] += 1
        assert active[0] == 1
        starts.append(now[0])
        await asyncio.sleep(0)
        active[0] -= 1

    async def work():
        await asyncio.sleep(0)

    owner = ObservationDrain(
        drain, lambda: True, asyncio.Event(), 0.25, clock=lambda: now[0]
    )
    for at in [10.0, 10.1, 10.24, 10.25, 10.4, 10.5]:
        now[0] = at
        await owner.run_with(work)
    assert starts == [10.0, 10.25, 10.5]
    assert not any(
        t.get_name() == "kalshi-book-observations" for t in asyncio.all_tasks()
    )
