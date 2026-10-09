"""#10090: PM CPU cannot hold K's loop; one copy and final drains survive split.

No venue/API/DB/Redis work. The runner is exercised with held arm coroutines
and process-control doubles; a fresh local Python child also receives real
TERM twice while its final drain is held.
"""

import asyncio
import os
from pathlib import Path
import signal
import sys

import pytest

import run_kalshi_ws as runner


def _signals(monkeypatch):
    callbacks = {}
    loop = asyncio.get_running_loop()
    monkeypatch.setattr(loop, "add_signal_handler", lambda sig, cb: callbacks.update({sig: cb}))
    monkeypatch.setattr(loop, "remove_signal_handler", lambda sig: callbacks.pop(sig))
    return callbacks


@pytest.mark.asyncio
@pytest.mark.parametrize("value", [None, "0", "false", "1"])
async def test_switch_keeps_legacy_rollback_and_child_cannot_spawn_parent(monkeypatch, value):
    if value is None:
        monkeypatch.delenv("WS_VENUE_PROCESSES", raising=False)
    else:
        monkeypatch.setenv("WS_VENUE_PROCESSES", value)
    called = []

    async def legacy():
        called.append("legacy")

    async def parent():
        called.append("parent")
        return 7

    async def venue(name):
        called.append(name)

    monkeypatch.setattr(runner, "main", legacy)
    monkeypatch.setattr(runner, "supervise_venues", parent)
    monkeypatch.setattr(runner, "run_venue", venue)
    assert await runner.entrypoint() == (7 if value == "1" else 0)
    assert called == ["parent" if value == "1" else "legacy"]
    called.clear()
    assert await runner.entrypoint("kalshi") == 0
    assert called == ["kalshi"]


@pytest.mark.asyncio
@pytest.mark.parametrize("venue", ["kalshi", "polymarket"])
async def test_venue_owns_only_its_arm_shadow_heartbeat_and_joins_drain(monkeypatch, venue):
    callbacks = _signals(monkeypatch)
    started, cancelled = [], []
    ready, draining, release = asyncio.Event(), asyncio.Event(), asyncio.Event()

    def arm(name):
        async def held():
            started.append(name)
            if len(started) == 3:
                ready.set()
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.append(name)
                if name == venue:
                    draining.set()
                    await release.wait()  # stand in for the existing final drain
        return held

    for name in ("kalshi", "polymarket"):
        monkeypatch.setattr(runner, f"run_{name}", arm(name))
        monkeypatch.setattr(runner, f"run_{name}_shadow", arm(f"{name}_shadow"))

    async def beat(arms):
        assert arms == (venue,)
        await arm("heartbeat")()

    monkeypatch.setattr(runner, "heartbeat", beat)
    task = asyncio.create_task(runner.run_venue(venue))
    try:
        await asyncio.wait_for(ready.wait(), 1)
        callbacks[signal.SIGTERM]()
        await asyncio.wait_for(draining.wait(), 1)
        callbacks[signal.SIGTERM]()
        callbacks[signal.SIGINT]()
        await asyncio.sleep(0)
        assert not task.done()
        assert sorted(started) == sorted([venue, f"{venue}_shadow", "heartbeat"])
        assert sorted(cancelled) == sorted(started)
        release.set()
        await asyncio.wait_for(task, 1)
        assert callbacks == {}
    finally:
        release.set()
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)


class Child:
    def __init__(self, pid, *, holds_drain=False):
        self.pid = pid
        self.returncode = None
        self.terms = self.kills = 0
        self.holds_drain = holds_drain
        self.exited = asyncio.Event()

    def exit(self, code):
        self.returncode = code
        self.exited.set()

    def terminate(self):
        self.terms += 1
        if not self.holds_drain:
            self.exit(0)

    def kill(self):
        self.kills += 1
        self.exit(-signal.SIGKILL)

    async def wait(self):
        await self.exited.wait()
        return self.returncode


@pytest.mark.asyncio
@pytest.mark.parametrize("unexpected", [False, True])
async def test_parent_execs_once_per_venue_then_joins_without_respawn(monkeypatch, unexpected):
    callbacks = _signals(monkeypatch)
    children, commands = [], []
    ready = asyncio.Event()

    async def spawn(*command):
        commands.append(command)
        child = Child(100 + len(children), holds_drain=True)
        children.append(child)
        if len(children) == 2:
            ready.set()
        return child

    monkeypatch.setattr(runner.asyncio, "create_subprocess_exec", spawn)
    task = asyncio.create_task(runner.supervise_venues())
    try:
        await asyncio.wait_for(ready.wait(), 1)
        if unexpected:
            children[0].exit(9)
        else:
            callbacks[signal.SIGTERM]()
        for _ in range(20):
            if children[1].terms:
                break
            await asyncio.sleep(0)
        assert not task.done(), "parent must await its still-draining child"
        callbacks[signal.SIGTERM]()  # does not resend or restart during the join
        await asyncio.sleep(0)
        assert len(children) == 2
        assert [child.terms for child in children] == ([0, 1] if unexpected else [1, 1])
        assert [child.kills for child in children] == [0, 0]
        assert commands == [
            (sys.executable, os.path.abspath(runner.__file__), "--venue", venue)
            for venue in ("kalshi", "polymarket")
        ]
        for child in children:
            if child.returncode is None:
                child.exit(0)
        assert await asyncio.wait_for(task, 1) == (1 if unexpected else 0)
        assert len(commands) == 2
    finally:
        for child in children:
            child.exit(0)
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_shutdown_deadline_kills_only_child_that_did_not_finish(monkeypatch):
    monkeypatch.setattr(runner, "SHUTDOWN_SECONDS", 0.01)
    drained, stuck = Child(1), Child(2, holds_drain=True)
    waiters = [asyncio.create_task(child.wait()) for child in (drained, stuck)]
    await asyncio.wait_for(runner._join_children([drained, stuck], waiters), 1)
    assert (drained.terms, drained.kills, drained.returncode) == (1, 0, 0)
    assert (stuck.terms, stuck.kills, stuck.returncode) == (1, 1, -signal.SIGKILL)
    assert all(task.done() for task in waiters)


@pytest.mark.asyncio
async def test_second_child_spawn_failure_still_stops_and_joins_first(monkeypatch):
    _signals(monkeypatch)
    children = []

    async def spawn(*command):
        if children:
            raise OSError("cannot start PM")
        child = Child(1)
        children.append(child)
        return child

    monkeypatch.setattr(runner.asyncio, "create_subprocess_exec", spawn)
    with pytest.raises(OSError, match="cannot start PM"):
        await runner.supervise_venues()
    assert len(children) == 1
    assert (children[0].terms, children[0].returncode) == (1, 0)


@pytest.mark.asyncio
async def test_fresh_child_real_term_twice_preserves_awaited_drain():
    # Importing the parent module cannot preload app clients. Replace the
    # venue coroutines in this *fresh local process* before running its mode.
    code = """
import asyncio, sys
import run_kalshi_ws as r
assert not any(n == 'app' or n.startswith('app.') for n in sys.modules)
async def production():
    print('ready', flush=True)
    try:
        await asyncio.Event().wait()
    finally:
        print('draining', flush=True)
        await asyncio.sleep(0.05)
        print('drained', flush=True)
async def held(*args):
    await asyncio.Event().wait()
r.run_kalshi = production
r.run_kalshi_shadow = held
r.heartbeat = held
asyncio.run(r.run_venue('kalshi'))
"""
    child = await asyncio.create_subprocess_exec(
        sys.executable, "-u", "-c", code,
        cwd=Path(runner.__file__).resolve().parent,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    try:
        assert await asyncio.wait_for(child.stdout.readline(), 2) == b"ready\n"
        child.send_signal(signal.SIGTERM)
        assert await asyncio.wait_for(child.stdout.readline(), 2) == b"draining\n"
        child.send_signal(signal.SIGTERM)
        assert await asyncio.wait_for(child.stdout.readline(), 2) == b"drained\n"
        assert await asyncio.wait_for(child.wait(), 2) == 0
    finally:
        if child.returncode is None:
            child.kill()
        await child.wait()
