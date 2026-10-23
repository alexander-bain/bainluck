"""lane1 independent cases for PR11181 (CERT-4192): due observations at
capacity must be retained at their original time and recovered without a
future quote. Unit policy cases on the existing _ready_rig only."""
import asyncio
import pytest
from tests.test_next_quote_owns_no_chart_wait_10090 import _ready_rig

TIMEBOX = {"on": True}


def _chart(calls, entered, release):
    async def chart(session, **kw):
        calls.append(kw)
        entered.set()
        await release.wait()
        return object(), True
    return chart


async def _stamp(r, at, timebox):
    call = r.refresh([1], flush_started=at)
    if timebox:
        await asyncio.wait_for(call, .25)
    else:
        await call


def _quote(session, price, value, stamp):
    price[0] = value
    session._returned = {"polymarket": {"value": value, "updated_at": stamp}}


async def _multi(monkeypatch, timebox):
    r, session, frames, price = _ready_rig(monkeypatch)
    r._history_limit = 1
    entered, release, calls = asyncio.Event(), asyncio.Event(), []
    monkeypatch.setattr("app.tasks.snapshots._create_or_update_win_prob_snapshot",
                        _chart(calls, entered, release))
    await r.refresh([1], flush_started=1000)
    await asyncio.wait_for(entered.wait(), 1)
    tasks = []
    try:
        _quote(session, price, .60, "2026-10-11T00:52:55+00:00")
        if timebox:
            await _stamp(r, 1025, True)
        else:
            tasks.append(asyncio.create_task(_stamp(r, 1025, False)))
            await asyncio.sleep(.05)
        if timebox:
            _quote(session, price, .70, "2026-10-11T00:53:20+00:00")
            await _stamp(r, 1050, True)
    finally:
        release.set()
        await asyncio.gather(*tasks)
        await r.drain_history()
    await r.refresh_pending(flush_started=1075)
    await r.drain_history()
    return r, frames, calls


@pytest.mark.asyncio
async def test_two_due_observations_through_one_hold_are_both_recovered_quietly(monkeypatch):
    r, frames, calls = await _multi(monkeypatch, True)
    actual = [(c["home_win_probability"], c["observed_at"]) for c in calls]
    assert [f["source_value"] for f in frames] == [.40, .60, .70]
    assert actual == [(.40, "2026-10-11T00:52:30+00:00"),
                      (.60, "2026-10-11T00:52:55+00:00"),
                      (.70, "2026-10-11T00:53:20+00:00")], {
        "history": actual, "pending": list(r.pending_event_ids()),
        "deferred": r.stats.get("history_deferred")}


@pytest.mark.asyncio
async def test_control_quiet_final_without_timebox_shows_what_base_retained(monkeypatch):
    r, frames, calls = await _multi(monkeypatch, False)
    actual = [(c["home_win_probability"], c["observed_at"]) for c in calls]
    assert actual == [(.40, "2026-10-11T00:52:30+00:00"),
                      (.60, "2026-10-11T00:52:55+00:00")], actual
