"""#10090: a preview read past its 0.25 s deadline is left to end, not cancelled.

Cancelling the in-flight SELECT made SQLAlchemy invalidate its pooled
connection, then held the run's shared slot through the graceful close. The
caller still skips the preview at the deadline exactly as before; the read
returns its connection normally, bounded by a per-refresher cap, a ceiling and
the final drain, and publishes nothing once its caller has stopped waiting.
"""

import asyncio
from contextlib import asynccontextmanager

import pytest

from app.tasks import live_blend_refresh as module
from tests.test_fresh_observation_preview_10090 import acknowledged_rig
from tests.test_fresh_observation_preview_10090 import (
    preview_enabled as preview_enabled,
)


def slow_rig(monkeypatch, *, block="query", ticket=None):
    """A dedicated read scope whose `block` stage waits for `release`."""
    r, session, frames, committed, rows, _, observations, validate, now = acknowledged_rig(monkeypatch)
    state = {"executed": 0, "exits": [], "retired": 0}
    entered, release = asyncio.Event(), asyncio.Event()

    @asynccontextmanager
    async def scope():
        try:
            yield session
        except BaseException as exc:
            state["exits"].append(type(exc).__name__)
            raise
        state["exits"].append(None)

    async def admission():
        if block == "admission":
            entered.set()
            await release.wait()
        return ticket

    execute = session.execute

    async def query(statement):
        state["executed"] += 1
        if block == "query":
            entered.set()
            await release.wait()
        return await execute(statement)

    async def retire(grouped, read_ticket):
        state["retired"] += 1
        if block == "retire":
            entered.set()
            await release.wait()

    r._observation_read_factory = scope
    monkeypatch.setattr(r, "_preview_admission_read", admission)
    monkeypatch.setattr(r, "_retire_terminal_preview_read", retire)
    monkeypatch.setattr(session, "execute", query)
    return r, session, frames, observations, validate, state, entered, release


async def join_detached(r):
    if r._detached_reads:
        await asyncio.wait_for(asyncio.wait(set(r._detached_reads)), 1)
    await asyncio.sleep(0)


async def test_deadline_skips_as_before_and_the_statement_ends_by_itself(monkeypatch, caplog):
    r, session, frames, obs, validate, state, entered, release = slow_rig(monkeypatch, ticket=7)
    assert await r.preview_accepted_observations(obs, validate) is False
    # Same disposition and receipt line as before; the slot stays counted.
    records = [record for record in caplog.records
               if "optional observation preview unavailable" in record.msg]
    assert len(records) == 1 and isinstance(records[0].exc_info[1], TimeoutError)
    assert records[0].args[1]["query_completed"] is False
    assert records[0].args[2] == {"detached": 1, "finished": 0, "capped": 0,
                                  "ceiling_cancelled": 0, "served_late": 0,
                                  "running": 1}
    assert r.preview_stats["publish_errors"] == 1
    assert len(r._detached_reads) == 1 and r._session_slots._value == 2
    release.set()
    await join_detached(r)
    # The statement finished and the scope exited normally: no cancellation
    # reached the connection. Its graph is kept for the next call, which
    # serves it (test_observation_late_serve_10090.py); a live event needs no
    # retirement, and none runs after its caller left.
    assert state["exits"] == [None]
    assert state["executed"] == 1 and state["retired"] == 0
    assert not frames and not session.updates
    assert r._session_slots._value == 3 and not r._detached_reads
    assert r.observation_read_stats == {
        "detached": 1, "finished": 1, "capped": 0, "ceiling_cancelled": 0, "served_late": 0,
    }


async def test_a_read_left_before_its_statement_issues_none(monkeypatch):
    r, _, frames, obs, validate, state, entered, release = slow_rig(monkeypatch, block="admission")
    assert await r.preview_accepted_observations(obs, validate) is False
    release.set()
    await join_detached(r)
    assert state["executed"] == 0 and state["exits"] == ["_ObservationReadAbandoned"]
    assert not frames and r.observation_read_stats["finished"] == 1


async def test_past_the_cap_no_second_read_starts(monkeypatch):
    r, _, frames, obs, validate, state, entered, release = slow_rig(monkeypatch)
    assert await r.preview_accepted_observations(obs, validate) is False
    assert await r.preview_accepted_observations(obs, validate) is False
    # The retry starts no read beside the detached one: one preview slot.
    assert len(r._detached_reads) == module.OBSERVATION_READ_DETACHED_MAX == 1
    assert state["executed"] == 1 and state["exits"] == []
    assert r._session_slots._value == 2
    assert r.observation_read_stats == {
        "detached": 1, "finished": 0, "capped": 1, "ceiling_cancelled": 0, "served_late": 0,
    }
    release.set()
    await join_detached(r)
    assert r._session_slots._value == 3 and not frames


async def test_retries_never_hold_a_second_slot(monkeypatch):
    r, _, _, obs, validate, state, entered, release = slow_rig(monkeypatch)
    fewest, stop = [3], asyncio.Event()

    async def sample():
        while not stop.is_set():
            fewest[0] = min(fewest[0], r._session_slots._value)
            await asyncio.sleep(.005)

    sampler = asyncio.create_task(sample())
    for _ in range(3):
        assert await r.preview_accepted_observations(obs, validate) is False
    stop.set()
    await sampler
    assert fewest[0] == 2
    release.set()
    await join_detached(r)


async def test_a_read_left_while_opening_does_no_admission(monkeypatch):
    r, session, frames, obs, validate, state, entered, release = slow_rig(monkeypatch, ticket=7)
    admissions = []
    opened = asyncio.Event()

    @asynccontextmanager
    async def slow_scope():
        await opened.wait()
        yield session

    async def admission():
        admissions.append(1)
        return 7

    r._observation_read_factory = slow_scope
    monkeypatch.setattr(r, "_preview_admission_read", admission)
    assert await r.preview_accepted_observations(obs, validate) is False
    opened.set()
    release.set()
    await join_detached(r)
    assert admissions == [] and state["executed"] == 0 and not frames
    assert r.observation_read_stats["finished"] == 1


async def test_a_read_still_running_at_the_ceiling_is_cancelled(monkeypatch):
    monkeypatch.setattr(module, "OBSERVATION_READ_DETACHED_S", .05)
    r, _, frames, obs, validate, state, entered, release = slow_rig(monkeypatch)
    assert await r.preview_accepted_observations(obs, validate) is False
    await join_detached(r)
    assert state["exits"] == ["CancelledError"]
    assert r._session_slots._value == 3 and not r._detached_reads and not frames
    assert r.observation_read_stats == {
        "detached": 1, "finished": 0, "capped": 0, "ceiling_cancelled": 1, "served_late": 0,
    }


async def test_final_drain_cancels_and_the_reap_joins_a_detached_read(monkeypatch):
    r, _, _, obs, validate, state, entered, release = slow_rig(monkeypatch)
    assert await r.preview_accepted_observations(obs, validate) is False
    [task] = r._detached_reads
    await asyncio.wait_for(r.drain_history(), 1)
    assert await asyncio.wait_for(module.reap_stopped_loops("polymarket", ()), 2) == 0
    assert task.cancelled() and state["exits"] == ["CancelledError"]
    assert r._session_slots._value == 3 and not r._detached_reads


async def test_a_retirement_in_flight_at_the_deadline_is_cancelled(monkeypatch):
    r, _, frames, obs, validate, state, entered, release = slow_rig(
        monkeypatch, block="retire", ticket=7,
    )
    assert await r.preview_accepted_observations(obs, validate) is False
    # A Redis/row write never outlives its caller: cancelled and joined.
    assert state["retired"] == 1 and state["exits"] == ["CancelledError"]
    assert not r._detached_reads and r._session_slots._value == 3 and not frames
    assert r.observation_read_stats == {
        "detached": 0, "finished": 0, "capped": 0, "ceiling_cancelled": 0, "served_late": 0,
    }


async def test_external_cancellation_still_cancels_and_joins_the_read(monkeypatch):
    r, _, _, obs, validate, state, entered, release = slow_rig(monkeypatch)
    task = asyncio.create_task(r.preview_accepted_observations(obs, validate))
    await asyncio.wait_for(entered.wait(), 1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, 1)
    assert state["exits"] == ["CancelledError"]
    assert not r._detached_reads and r._session_slots._value == 3


async def test_stamps_keep_their_slots_beside_a_slow_detached_read(monkeypatch):
    r, session, _, obs, validate, state, entered, release = slow_rig(monkeypatch)
    assert await r.preview_accepted_observations(obs, validate) is False
    assert await r.preview_accepted_observations(obs, validate) is False  # capped
    # One slot is the detached read's; both remaining slots serve stamps now,
    # concurrently, while the read is still blocked.
    holding = asyncio.Event()
    inside = 0

    @asynccontextmanager
    async def stamp_session():
        nonlocal inside
        inside += 1
        if inside == 2:
            holding.set()
        await holding.wait()
        yield session

    r._session_factory = stamp_session

    async def stamp_read(session, event_ids, **kwargs):
        return {}

    monkeypatch.setattr(r, "_read_groups", stamp_read)
    await asyncio.wait_for(asyncio.gather(r._prepare_groups([1]), r._prepare_groups([1])), .5)
    assert not release.is_set() and len(r._detached_reads) == 1
    release.set()
    await join_detached(r)
    assert r._session_slots._value == 3


async def test_owner_replaced_while_detached_gets_no_clock(monkeypatch):
    from datetime import timedelta
    from types import SimpleNamespace
    from app.tasks.live_blend_refresh import HeldRowQuotes

    r, session, frames, obs, validate, state, entered, release = slow_rig(monkeypatch)
    held = HeldRowQuotes()
    r.held_quotes = held
    held.preview_events = lambda: ()
    original = session.execute

    async def clocked(statement):
        columns = list(statement.selected_columns)
        assert columns[-1].key == "observation_clock"
        result = await original(statement.with_only_columns(*columns[:-1]))
        result._rows = [tuple(row) + (module.datetime.now(module.timezone.utc),)
                        for row in result._rows]
        return result

    monkeypatch.setattr(session, "execute", clocked)
    assert await r.preview_accepted_observations(obs, validate) is False
    assert held._sampling == 1
    replacement = HeldRowQuotes()
    r.held_quotes = replacement
    release.set()
    await join_detached(r)
    assert held._database_bound is None and replacement._database_bound is None
    assert held._sampling == 0 and not frames
