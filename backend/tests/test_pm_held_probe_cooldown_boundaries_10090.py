"""Follow-on cooldown must not gate withdrawal or final persistence."""
import pytest
from app.tasks.live_blend_refresh import HeldRowQuotes
from tests.test_pm_quote_lock_bound_10090 import writer_rig
from tests.test_ws_flush_cadence_10090 import _FakeTime

async def cooling_pair(monkeypatch):
    clock = _FakeTime(monkeypatch, t=1000)
    database = {1: .6, 2: .4}
    r, state = writer_rig(clock, database=database, batch={1: .7, 2: .3})
    held = HeldRowQuotes()
    held.hold({1: (.7, 900), 2: (.3, 900)})
    r.ns["blend_refresher"].held_quotes = held
    assert await r.ns["write_chunk"]({1: .7, 2: .3}) is None
    assert await r.ns["write_chunk"]({1: .7, 2: .3}) is None
    deadline = max(r.ns["lock_retry_until"].values())
    assert clock.t < deadline <= clock.t + .25
    return clock, r, state, database, held, deadline

@pytest.mark.asyncio
async def test_final_drain_writes_newest_pair_before_probe_deadline(monkeypatch):
    clock, r, state, database, held, deadline = await cooling_pair(monkeypatch)
    state.held = False
    r.ns["price_buffer"].update({1: .81, 2: .19})
    attempts, settings = len(state.attempts), len(state.settings)
    result = await r.ns["write_chunk"]({1: .81, 2: .19}, final=True)
    assert result.written_ids == (1, 2)
    assert clock.t < deadline
    assert len(state.attempts) == attempts + 1
    assert len(state.settings) == settings
    assert state.nowait[-1] is False
    assert database == {1: .81, 2: .19}
    assert not r.ns["price_buffer"] and not r.ns["lock_retry_until"]
    assert 1 not in held and 2 not in held

@pytest.mark.asyncio
async def test_price_probe_cooldown_does_not_suppress_withdrawal(monkeypatch):
    clock, r, state, database, held, deadline = await cooling_pair(monkeypatch)
    before = len(state.attempts)
    assert r.ns["withdraw_buffer"]
    assert await r.ns["flush_withdrawals"]() == [1]
    assert clock.t < deadline
    assert ("withdraw", [1]) in r.trace
    assert not r.ns["withdraw_buffer"]
    assert not r.ns["withdrawal_retry_until"]
    assert len(state.attempts) == before
    assert r.ns["lock_retry_until"]


@pytest.mark.asyncio
async def test_a_probe_timeout_on_a_wholly_held_chunk_still_arms_no_cooldown(monkeypatch):
    # Only a confirmed NOWAIT row refusal earns the 250 ms re-probe budget. A
    # probe that timed out (a table lock it queued on, or an unrecognised
    # 55P03) keeps the every-flush probe even when the overlay holds the
    # whole chunk: nothing proved the row-lock holder is the one known.
    from tests.test_pm_quote_lock_bound_10090 import LOCK_TIMEOUT_MESSAGE
    clock = _FakeTime(monkeypatch, t=1000)
    r, state = writer_rig(clock)
    held = HeldRowQuotes()
    held.hold({1: (.6, 900), 2: (.4, 900)})
    r.ns["blend_refresher"].held_quotes = held
    r.ns["lock_retry_until"].update({1: 0, 2: 0})
    state.refusal_message = LOCK_TIMEOUT_MESSAGE
    assert await r.ns["write_chunk"]({1: .6, 2: .4}) is None
    assert state.nowait == [True]
    assert r.ns["stats"]["price_lock_timeouts"] == 1
    assert r.ns["lock_retry_until"] == {1: 0, 2: 0}
