import asyncio
import pytest
from tests.test_next_quote_owns_no_chart_wait_10090 import _ready_rig

@pytest.mark.asyncio
async def test_full_history_retains_final_changed_quote_without_a_future_tick(monkeypatch):
    r, session, frames, price = _ready_rig(monkeypatch)
    r._history_limit = 1
    entered, release, calls = asyncio.Event(), asyncio.Event(), []
    async def chart(session, **kw):
        calls.append(kw)
        entered.set()
        await release.wait()
        return object(), True
    monkeypatch.setattr("app.tasks.snapshots._create_or_update_win_prob_snapshot", chart)
    await r.refresh([1], flush_started=1000)
    await asyncio.wait_for(entered.wait(), 1)
    price[0] = .60
    session._returned = {"polymarket": {"value": .60, "updated_at": "2026-10-11T00:52:55+00:00"}}
    try:
        await asyncio.wait_for(r.refresh([1], flush_started=1025), .25)
        assert [f["source_value"] for f in frames] == [.40,.60]
    finally:
        release.set()
        await r.drain_history()
    # No further venue input. Exercise ordinary empty/debt refresh and drain,
    # not a fabricated new quote or a weakening of the 25s eligibility floor.
    await r.refresh_pending(flush_started=1050)
    await r.drain_history()
    actual = [(c["home_win_probability"], c["observed_at"]) for c in calls]
    assert actual == [(.40,"2026-10-11T00:52:30+00:00"),(.60,"2026-10-11T00:52:55+00:00")], {
        "history": actual, "published": [f["source_value"] for f in frames],
        "pending": list(r.pending_event_ids()), "deferred": r.stats["history_deferred"],
    }
