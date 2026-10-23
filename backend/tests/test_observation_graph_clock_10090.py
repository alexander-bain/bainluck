"""A completed graph SELECT may sample DB time for future inputs, never its own."""

import asyncio
from contextlib import asynccontextmanager
from datetime import timedelta
from types import SimpleNamespace

import pytest

from app.tasks.live_blend_refresh import HeldRowQuotes
from tests.test_fresh_observation_preview_10090 import acknowledged_rig
from tests.test_fresh_observation_preview_10090 import (
    preview_enabled as preview_enabled,
)
from tests.test_blend_preview_display_before_persist_195 import _blends


def clock_rig(monkeypatch, *, failure=None):
    r, session, frames, committed, _, _, observations, validate, now = acknowledged_rig(
        monkeypatch
    )
    held = HeldRowQuotes()
    r.held_quotes = held
    held.preview_events = lambda: ()
    held._database_bound = (now - timedelta(seconds=1)).timestamp()
    held._sample_started = held._sample_published = 1
    frozen = SimpleNamespace(event_id=1, outcome_id=101, seq=1, probability=0.9)
    held.note_input(frozen)
    entered, release = asyncio.Event(), asyncio.Event()
    calls = []
    original = session.execute

    async def execute(statement):
        calls.append(statement)
        if failure == "query":
            raise TimeoutError("query unavailable")
        result = await original(statement)
        if "observation_clock" in [column.key for column in statement.selected_columns]:
            result._rows = [tuple(row) + (now,) for row in result._rows]
        return result

    monkeypatch.setattr(session, "execute", execute)

    @asynccontextmanager
    async def scope():
        yield session
        entered.set()
        if failure in ("cleanup", "cancel"):
            await release.wait()
        if failure == "close-error":
            raise TimeoutError("close unavailable")

    r._observation_read_factory = scope
    return (
        r,
        held,
        frames,
        committed,
        observations,
        validate,
        now,
        frozen,
        entered,
        release,
        calls,
    )


async def test_completed_graph_advances_only_future_inputs_without_second_read(
    monkeypatch,
):
    r, held, frames, committed, obs, validate, now, frozen, *_rest, calls = clock_rig(
        monkeypatch
    )
    before = held.bound_for(frozen)
    await r.preview_accepted_observations(obs, validate)
    assert held._database_bound == now.timestamp()
    assert held.bound_for(frozen) == before
    future = SimpleNamespace(event_id=1, outcome_id=102, seq=2, probability=0.1)
    held.note_input(future)
    assert held.bound_for(future) == now.timestamp()
    assert len(calls) == 1 and not committed
    [frame] = _blends(frames)
    assert frame["display_observed_at"] == (now - timedelta(seconds=1)).isoformat()


@pytest.mark.parametrize("failure", ["query", "cleanup", "close-error", "cancel"])
async def test_incomplete_read_never_advances_clock(monkeypatch, failure):
    r, held, _, _, obs, validate, _, frozen, entered, release, _ = clock_rig(
        monkeypatch, failure=failure
    )
    before = held._database_bound
    task = asyncio.create_task(r.preview_accepted_observations(obs, validate))
    if failure in ("cleanup", "cancel"):
        await asyncio.wait_for(entered.wait(), 1)
        assert held._database_bound == before
        if failure == "cancel":
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        else:
            await task
    else:
        await task
    assert held._database_bound == before == held.bound_for(frozen)
    assert held._sampling == 0


async def test_newer_clock_survives_late_graph_completion(monkeypatch):
    r, held, _, _, obs, validate, now, _, entered, release, _ = clock_rig(
        monkeypatch, failure="cleanup"
    )
    task = asyncio.create_task(r.preview_accepted_observations(obs, validate))
    await asyncio.wait_for(entered.wait(), 1)
    held._sample_started += 1
    held._sample_published = held._sample_started
    held._database_bound = (now + timedelta(seconds=1)).timestamp()
    release.set()
    await task
    assert held._database_bound == (now + timedelta(seconds=1)).timestamp()
    assert held._sampling == 0


async def test_completed_graph_recovers_failed_clock_without_retrying_pool(monkeypatch):
    r, held, _, _, obs, validate, now, *_rest, calls = clock_rig(monkeypatch)
    held._sample_failure_episode = True
    held._sample_failure_ordinal = held._sample_started
    held._sample_backoff_until = held._now() + 5
    until = held._sample_backoff_until
    await r.preview_accepted_observations(obs, validate)
    assert held._database_bound == now.timestamp()
    # The graph's longer read budget does not prove the standalone sampler's
    # shorter budget is healthy. It supplies future bounds without rearming it.
    assert held._sample_failure_episode and held._sample_backoff_until == until
    assert len(calls) == 1


async def test_replaced_owner_is_not_resurrected_by_completed_read(monkeypatch):
    r, held, _, _, obs, validate, _, _, entered, release, _ = clock_rig(
        monkeypatch, failure="cleanup"
    )
    before = held._database_bound
    task = asyncio.create_task(r.preview_accepted_observations(obs, validate))
    await asyncio.wait_for(entered.wait(), 1)
    replacement = HeldRowQuotes()
    r.held_quotes = replacement
    release.set()
    await task
    assert held._closed and held._database_bound == before
    assert replacement._database_bound is None
    assert held._sampling == 0


async def test_older_graph_cannot_clear_a_newer_failed_sample(monkeypatch):
    r, held, _, _, obs, validate, now, _, entered, release, _ = clock_rig(
        monkeypatch, failure="cleanup"
    )
    task = asyncio.create_task(r.preview_accepted_observations(obs, validate))
    await asyncio.wait_for(entered.wait(), 1)
    held._sample_started += 1
    held._sample_failure_ordinal = held._sample_started
    held._sample_failure_episode = True
    held._sample_backoff_until = held._now() + 5
    until = held._sample_backoff_until
    release.set()
    await task
    assert held._database_bound == now.timestamp()
    assert held._sample_failure_episode and held._sample_backoff_until == until


async def test_empty_graph_cannot_supply_a_clock(monkeypatch):
    r, held, _, _, obs, validate, _, _, *_ = clock_rig(monkeypatch)
    before = held._database_bound

    async def empty(*args, **kwargs):
        return {}

    monkeypatch.setattr(r, "_read_groups", empty)
    await r.preview_accepted_observations(obs, validate)
    assert held._database_bound == before and held._sampling == 0


async def test_ordinary_writer_scope_never_supplies_graph_clock(monkeypatch):
    r, held, _, _, obs, validate, _, _, *_rest, calls = clock_rig(monkeypatch)
    before = held._database_bound
    scope, r._observation_read_factory = r._observation_read_factory, None
    r._session_factory = scope
    await r.preview_accepted_observations(obs, validate)
    assert held._database_bound == before and held._sampling == 0
    assert "observation_clock" not in [
        column.key for column in calls[0].selected_columns
    ]
