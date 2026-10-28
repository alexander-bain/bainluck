"""#10090 M3: a left observation read whose statement had started is served next.

Before: a read past its 0.25 s budget was abandoned once its statement returned,
so while reads kept missing, the page's "observed" clock froze until a changed
price committed (hill-climb lab M3: 8.3 s worst against a 0.63 s control). Now
the read finishes its graph without writing and keeps it, with its caller's
frozen inputs and validate, for that consumer's next call. That call serves it
first, inside its own scope, counting no input newer than the read's start.
"""

import asyncio
import time
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.tasks import live_blend_refresh as module
from app.tasks.live_blend_refresh import HeldRowQuotes
from tests.test_blend_preview_display_before_persist_195 import _blends
from tests.test_fresh_observation_preview_10090 import (
    preview_enabled as preview_enabled,
)
from tests.test_observation_read_deadline_10090 import join_detached, slow_rig


async def refuse_all(event_ids):
    return set()


def observed_at(frame):
    return datetime.fromisoformat(frame["display_observed_at"]).timestamp()


async def test_a_left_read_is_served_first_by_the_next_call(monkeypatch):
    r, session, frames, obs, validate, state, _entered, release = slow_rig(monkeypatch, ticket=7)
    assert await r.preview_accepted_observations(obs, validate) is False
    release.set()
    await join_detached(r)
    assert not frames and r._late_observation is not None and r._late_observation.finished
    # Nothing new to observe, and a validate that refuses everything: only the
    # left call's own frozen inputs and its own validate can publish.
    await r.preview_accepted_observations({}, refuse_all)
    [frame] = _blends(frames)
    [(_value, bound, _mark)] = [obs[1][101]]
    assert abs(observed_at(frame) - bound) < 1e-3
    assert state["executed"] == 1 and state["retired"] == 0 and not session.updates
    assert r._late_observation is None and r.observation_read_stats["served_late"] == 1
    # Served once.
    await r.preview_accepted_observations({}, refuse_all)
    assert len(_blends(frames)) == 1 and r.observation_read_stats["served_late"] == 1


async def test_the_serve_rechecks_with_the_left_calls_validate(monkeypatch):
    r, _, frames, obs, _validate, state, _entered, release = slow_rig(monkeypatch)
    allowed = [True]

    async def validate(event_ids):
        return set(event_ids) if allowed[0] else set()

    assert await r.preview_accepted_observations(obs, validate) is False
    release.set()
    await join_detached(r)
    allowed[0] = False  # e.g. a changed price now owns the event
    await r.preview_accepted_observations({}, refuse_all)
    assert not _blends(frames) and r._late_observation is None


async def test_an_input_newer_than_the_read_start_is_not_observed(monkeypatch):
    for newer, served in ((False, 1), (True, 0)):
        r, _, frames, obs, validate, _state, _entered, release = slow_rig(monkeypatch)
        # Received after the read started but before the serve: a waited read
        # validated at serve time would accept it; this graph cannot have seen it.
        bound = time.time() + (.1 if newer else -.1)
        obs = {1: {oid: (value, bound, mark) for oid, (value, _b, mark) in obs[1].items()}}
        assert await r.preview_accepted_observations(obs, validate) is False
        release.set()
        await join_detached(r)
        assert time.time() > bound
        await r.preview_accepted_observations({}, refuse_all)
        assert len(_blends(frames)) == served, newer


async def test_a_left_read_older_than_its_ceiling_is_not_served(monkeypatch):
    monkeypatch.setattr(module, "OBSERVATION_READ_DETACHED_S", .3)
    r, _, frames, obs, validate, _state, _entered, release = slow_rig(monkeypatch)
    assert await r.preview_accepted_observations(obs, validate) is False
    release.set()
    await join_detached(r)
    await asyncio.sleep(.1)
    await r.preview_accepted_observations({}, refuse_all)
    assert not _blends(frames) and r.observation_read_stats["served_late"] == 0
    assert r._late_observation is None


async def test_a_left_read_needing_a_retirement_writes_nothing_and_is_dropped(monkeypatch):
    r, session, frames, obs, validate, state, _entered, release = slow_rig(monkeypatch, ticket=7)
    event = session._market_rows[0][1]
    event.completed_at = datetime.now(timezone.utc)
    assert await r.preview_accepted_observations(obs, validate) is False
    release.set()
    await join_detached(r)
    assert state["exits"] == ["_ObservationReadAbandoned"] and state["retired"] == 0
    assert r._late_observation is None
    await r.preview_accepted_observations({}, refuse_all)
    assert not frames and r.observation_read_stats["served_late"] == 0


async def test_a_read_left_before_its_statement_keeps_nothing(monkeypatch):
    r, _, frames, obs, validate, state, _entered, release = slow_rig(monkeypatch, block="admission")
    assert await r.preview_accepted_observations(obs, validate) is False
    release.set()
    await join_detached(r)
    assert state["executed"] == 0 and r._late_observation is None
    await r.preview_accepted_observations({}, refuse_all)
    assert not frames


async def test_a_kept_read_bounds_only_inputs_after_it_ends(monkeypatch):
    r, session, frames, obs, validate, state, entered, release = slow_rig(monkeypatch)
    now = datetime.now(timezone.utc)
    held = HeldRowQuotes()
    r.held_quotes = held
    held.preview_events = lambda: ()
    held._database_bound = before = (now - timedelta(seconds=1)).timestamp()
    held._sample_started = held._sample_published = 1
    frozen = SimpleNamespace(event_id=1, outcome_id=101, seq=1, probability=0.9)
    held.note_input(frozen)
    execute = session.execute

    async def clocked(statement):
        columns = list(statement.selected_columns)
        has_clock = columns[-1].key == "observation_clock"
        graph = statement.with_only_columns(*columns[:-1]) if has_clock else statement
        result = await execute(graph)
        if has_clock:
            result._rows = [tuple(row) + (now,) for row in result._rows]
        return result

    monkeypatch.setattr(session, "execute", clocked)
    assert await r.preview_accepted_observations(obs, validate) is False
    assert held._database_bound == before
    release.set()
    await join_detached(r)
    # Nothing else samples while prices stay unchanged: the kept read's DB time
    # bounds inputs from now on, never the frozen one it read for.
    assert held._database_bound == now.timestamp()
    assert held.bound_for(frozen) == before and held._sampling == 0
    later = SimpleNamespace(event_id=1, outcome_id=102, seq=2, probability=0.1)
    held.note_input(later)
    assert held.bound_for(later) == now.timestamp()
