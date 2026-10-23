"""Only a whole held game may decouple persistence retries from delivery."""
import pytest
from app.tasks.live_blend_refresh import HeldRowQuotes
from tests.test_pm_quote_lock_bound_10090 import writer_rig
from tests.test_ws_flush_cadence_10090 import _FakeTime

@pytest.mark.parametrize("held_ids,open_catalog,throttled", [
    ((),False,False), ((1,),False,False), ((1,2),True,False), ((1,2),False,True),
])
async def test_only_whole_held_game_bounds_failed_probe_work_and_recovers_newest(
    monkeypatch,held_ids,open_catalog,throttled,
):
    clock=_FakeTime(monkeypatch,t=1000)
    database={1:.6,2:.4}
    r,state=writer_rig(clock,database=database)
    assert await r.ns["write_chunk"]({1:.7,2:.3}) is None
    held=HeldRowQuotes();held.hold({oid:(.7 if oid==1 else .3,900) for oid in held_ids})
    r.ns["blend_refresher"].held_quotes=held
    if open_catalog:r.ns["open_outcome_ids"].add(1)
    clock.t+=.01
    assert await r.ns["write_chunk"]({1:.7,2:.3}) is None
    deadline=max(r.ns["lock_retry_until"].values())
    assert (deadline>clock.t)==throttled
    before=len(state.attempts)
    clock.t+=.10
    r.ns["price_buffer"].update({1:.8,2:.2})
    assert await r.ns["write_chunk"]({1:.8,2:.2}) is None
    assert (len(state.attempts)==before)==throttled
    if throttled:assert r.ns["price_buffer"][1]==.8
    state.held=False
    clock.t=max(clock.t,deadline)+.001
    r.ns["price_buffer"].update({1:.8,2:.2})
    assert (await r.ns["write_chunk"]({1:.8,2:.2})).written_ids==(1,2)
    assert database=={1:.8,2:.2}
    assert not r.ns["lock_retry_until"]
    assert 1 not in held and 2 not in held
