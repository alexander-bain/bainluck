"""An unchanged price acknowledgement can feed optional DNPL, never a stamp."""

from types import SimpleNamespace
import pytest

from tests.test_pm_quote_lock_bound_10090 import writer_rig
from tests.test_ws_flush_cadence_10090 import _FakeTime
from tests.test_polymarket_withdrawal_speed_10651 import ROOT, compile_functions


@pytest.mark.parametrize("successor", [None, "same-price", "a-b-a", "withdraw-restore", "routing"])
async def test_successful_unchanged_ack_hands_frozen_observation_to_preview_only(monkeypatch, successor):
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

        def note_input(self, mark):
            pass

    async def preview(observations, validate):
        if successor == "same-price":
            r.ns["_mark_input"](1, .6, "price_change", {})
        elif successor == "a-b-a":
            r.ns["_mark_input"](1, .7, "price_change", {})
            r.ns["_mark_input"](1, .6, "price_change", {})
        elif successor == "withdraw-restore":
            r.ns["observation_continuity"].pop(1)
            r.ns["_mark_input"](1, .6, "price_change", {})
        elif successor == "routing":
            r.ns["routing_generation"] += 1
        allowed = await validate(set(observations))
        observed.append((observations, allowed))

    refresher.held_quotes = Bounds()
    refresher.preview_accepted_observations = preview
    r.ns["routing_generation"] = 0
    r.ns["observation_continuity"] = {oid: (object(), value) for oid, value in database.items()}
    marks = {oid: SimpleNamespace(seq=oid + 10, outcome_id=oid, probability=value)
             for oid, value in database.items()}
    r.ns["input_marks"].update(marks)
    seq = [100]

    def note_input(eid, oid, value, kind, timestamp):
        seq[0] += 1
        return SimpleNamespace(seq=seq[0], outcome_id=oid, probability=value)

    r.ns["tail_receipts"].note_input = note_input
    compile_functions(ROOT / "app/tasks/polymarket_ws.py", ["_mark_input"], r.ns)
    r.ns["price_buffer"].update(database)
    r.trace.clear()
    r.marks.clear()
    clock.t = 1001
    assert await r.ns["flush_prices"](flush_started=1001)
    assert len(observed) == 1
    observations, allowed = observed[0]
    assert allowed == ({10} if successor in (None, "same-price") else set())
    assert observations == {10: {oid: (value, 1000.5, marks[oid]) for oid, value in database.items()}}
    assert state.commits == original_writes
    assert r.ns["successful_price_write_at"] == {1: 1000, 2: 1000}
    assert not r.marks and not any(kind == "refresh" for kind, _ in r.trace)
