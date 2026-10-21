"""An unchanged price acknowledgement can feed optional DNPL, never a stamp."""

from types import SimpleNamespace

from tests.test_pm_quote_lock_bound_10090 import writer_rig
from tests.test_ws_flush_cadence_10090 import _FakeTime


async def test_successful_unchanged_ack_hands_frozen_observation_to_preview_only(monkeypatch):
    clock = _FakeTime(monkeypatch, t=1000)
    database = {1: .6, 2: .4}
    r, state = writer_rig(clock, database=database, batch=dict(database), mapping={1: 10, 2: 10}, books={})
    state.held = False
    assert await r.ns["flush_prices"](flush_started=1000)
    original_writes = list(state.commits)
    refresher = r.ns["blend_refresher"]
    refresher.preview_events = {10}
    observed = []

    class Bounds:
        def bound_for(self, mark):
            return None if mark is None else 1000.5

        async def sample_database_clock(self, *args):
            pass

        def release(self, *args):
            pass

        def __contains__(self, oid):
            return False

    async def preview(observations, validate):
        allowed = await validate(set(observations))
        observed.append((observations, allowed))

    refresher.held_quotes = Bounds()
    refresher.preview_accepted_observations = preview
    r.ns["routing_generation"] = 0
    marks = {oid: SimpleNamespace(seq=oid + 10, outcome_id=oid, probability=value)
             for oid, value in database.items()}
    r.ns["input_marks"].update(marks)
    r.ns["price_buffer"].update(database)
    r.trace.clear()
    r.marks.clear()
    clock.t = 1001
    assert await r.ns["flush_prices"](flush_started=1001)
    assert len(observed) == 1
    observations, allowed = observed[0]
    assert allowed == {10}
    assert observations == {10: {oid: (value, 1000.5, marks[oid]) for oid, value in database.items()}}
    assert state.commits == original_writes
    assert r.ns["successful_price_write_at"] == {1: 1000, 2: 1000}
    assert not r.marks and not any(kind == "refresh" for kind, _ in r.trace)
