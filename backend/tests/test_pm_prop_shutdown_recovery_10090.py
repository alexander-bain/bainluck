"""#10090 — cancelling the props' loop mid-write keeps the newest prop state.

Root's independent control on 90ec48ab6e (stage-trace/review/prop-loop-recovery/),
adopted with its assertions unchanged; only its artifact JSON output is dropped.
Cancellation during a prop write or its post-commit publication, then a
twice-cancelled shutdown join: the newer pair and withdrawals survive, the prop
task is joined before the final drain writes, no two writers overlap, and the
drain writes the latest pair and withdraws the cohort once. Existing extracted
writer/shutdown fixtures; fake database and publication boundary.
"""
import asyncio
from contextlib import asynccontextmanager

import pytest

from tests.test_pm_event_before_notification_10090 import committed_rig
from tests.test_polymarket_withdrawal_speed_10651 import ROOT, compile_functions


@pytest.mark.asyncio
@pytest.mark.parametrize("phase", ["write", "post_commit_publication"])
async def test_prop_cancel_repeat_shutdown_cancel_then_latest_final_drain(phase):
    (p, publishing, publish_release, _, publishing_cleanup,
     publishing_cleanup_release) = committed_rig(hold_cleanup=True)
    p.ns["non_blend_outcome_ids"].update({1, 2})
    write_entered, write_cleanup, write_cleanup_release = (
        asyncio.Event(), asyncio.Event(), asyncio.Event(),
    )
    initial_session = p.ns["get_task_session"]
    write_hold_used = False

    @asynccontextmanager
    async def held_session():
        nonlocal write_hold_used
        async with initial_session() as session:
            execute = session.execute

            async def held_execute(stmt, params=None):
                nonlocal write_hold_used
                result = await execute(stmt, params)
                if (phase == "write" and not write_hold_used
                        and isinstance(stmt, tuple) and stmt[0] == "prices"):
                    write_hold_used = True
                    write_entered.set()
                    try:
                        await asyncio.Event().wait()
                    finally:
                        write_cleanup.set()
                        await write_cleanup_release.wait()
                return result

            session.execute = held_execute
            yield session

    p.ns["get_task_session"] = held_session
    inner_write = p.ns["write_chunk"]
    active = maximum = 0
    writes = []
    prop = None

    async def track_write(chunk, **kwargs):
        nonlocal active, maximum
        if kwargs.get("final"):
            assert prop.done(), "final write overlapped unfinished prop task"
            assert active == 0, "final write overlapped old writer cleanup"
        active += 1
        maximum = max(maximum, active)
        row = {"values": dict(chunk), "final": kwargs.get("final", False),
               "outcome": "running"}
        writes.append(row)
        try:
            value = await inner_write(chunk, **kwargs)
            row["outcome"] = "returned"
            return value
        except asyncio.CancelledError:
            row["outcome"] = "cancelled"
            raise
        finally:
            active -= 1

    p.ns["write_chunk"] = track_write
    compile_functions(
        ROOT / "app/tasks/polymarket_ws.py", ["drain_prices", "join_flushes_then_drain"], p.ns,
    )
    done = asyncio.create_task(asyncio.sleep(0))
    await done
    p.ns.update({name: done for name in
                 ["flush_task", "standalone_task", "admission_task", "game_run_task"]})
    p.ns.update(resolution_tasks=set(), open_run_task=None, FINAL_FLUSH_ATTEMPTS=3,
                LOOP_REAP_TIMEOUT_S=1, asyncio=asyncio)
    prop = asyncio.create_task(p.ns["flush_props"](1000), name="review-prop-owner")
    p.ns["prop_task"] = prop
    join = None
    try:
        await asyncio.wait_for((write_entered if phase == "write" else publishing).wait(), 1)
        # Newer accepted pair and withdrawal remain pending while old work unwinds.
        p.ns["price_buffer"].update({1: .7, 2: .3})
        p.ns["withdraw_buffer"].update({1: (.1, .9), 2: (.2, .8)})
        prop.cancel()
        await asyncio.wait_for(
            (write_cleanup if phase == "write" else publishing_cleanup).wait(), 1,
        )
        assert not prop.done() and active == 1
        assert p.ns["catalog_boundary"].side_writer.locked()
        join = asyncio.create_task(p.ns["join_flushes_then_drain"](),
                                   name="review-shutdown-join")
        for _ in range(3):
            await asyncio.sleep(0)
        join.cancel()
        for _ in range(3):
            await asyncio.sleep(0)
        join.cancel()
        for _ in range(3):
            await asyncio.sleep(0)
        assert not join.done() and not prop.done()
        assert len(writes) == 1 and p.ns["price_buffer"] == {1: .7, 2: .3}
        assert p.ns["withdraw_buffer"] == {1: (.1, .9), 2: (.2, .8)}
        before = list(p.trace)
        assert sum(kind == "commit" for kind, _ in before) == (0 if phase == "write" else 1)
        publish_release.set()
        publishing_cleanup_release.set()
        write_cleanup_release.set()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(join, 2)
        assert prop.cancelled()
        final = [row for row in writes if row["final"]]
        assert final == [{"values": {1: .7, 2: .3}, "final": True, "outcome": "returned"}]
        assert maximum == 1 and active == 0
        withdrawals = [value for kind, value in p.trace if kind == "withdraw"]
        assert withdrawals == [[1, 2]], withdrawals
        assert not p.ns["price_buffer"] and not p.ns["withdraw_buffer"]
        assert not p.ns["catalog_boundary"].side_writer.locked()
        assert p.ns["catalog_boundary"].active == p.ns["catalog_boundary"].standalone_active == 0
        assert p.ns["stats"]["errors"] == p.ns["stats"]["final_flush_dropped"] == 0
    finally:
        publish_release.set()
        publishing_cleanup_release.set()
        write_cleanup_release.set()
        for task in (prop, join):
            if task is not None and not task.done():
                task.cancel()
        await asyncio.gather(*(task for task in (prop, join) if task is not None),
                             return_exceptions=True)
        await p.ns["catalog_boundary"].join_stamps(cancel=True)
