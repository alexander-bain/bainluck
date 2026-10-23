"""lane1 acceptance case for PR11181's next head (root 155537Z): past the
backlog AND the spill, two due observations for ONE event must both be paid,
each at its own observation time. A latest-only slot (thinning) fails here;
root did not authorize dropping owed intermediate points. Small fixture bounds
(limit 1, spill 1) on the existing _ready_rig. Unit policy proof only."""
import asyncio
import pytest
from tests.test_next_quote_owns_no_chart_wait_10090 import _ready_rig

SPILL = 3
WANT = [(.40, "2026-10-11T00:52:30+00:00"),
        (.50, "2026-10-11T00:52:55+00:00"),
        (.60, "2026-10-11T00:53:20+00:00"),
        (.70, "2026-10-11T00:53:45+00:00")]


def _quote(session, price, value, stamp):
    price[0] = value
    session._returned = {"polymarket": {"value": value, "updated_at": stamp}}


@pytest.mark.asyncio
async def test_two_over_bound_observations_for_one_event_are_both_paid(monkeypatch):
    r, session, frames, price = _ready_rig(monkeypatch)
    r._history_limit, r._history_spill_limit = 1, SPILL
    entered, release, calls = asyncio.Event(), asyncio.Event(), []

    async def chart(session_, **kw):
        calls.append(kw)
        entered.set()
        await release.wait()
        return object(), True

    monkeypatch.setattr("app.tasks.snapshots._create_or_update_win_prob_snapshot", chart)
    await r.refresh([1], flush_started=1000)            # .40 writing: backlog full
    await asyncio.wait_for(entered.wait(), 1)
    for at, (value, stamp) in zip((1025, 1050, 1075), WANT[1:]):
        _quote(session, price, value, stamp)
        await asyncio.wait_for(r.refresh([1], flush_started=at), .25)  # never waits
    release.set()
    await r.drain_history()
    await r.refresh_pending(flush_started=1100)          # venue quiet: no new quote
    await r.drain_history()
    paid = [(c["home_win_probability"], c["observed_at"]) for c in calls]
    assert [f["source_value"] for f in frames] == [.40, .50, .60, .70]
    assert paid == WANT, {"history": paid, "pending": list(r.pending_event_ids()),
                          "deferred": r.stats.get("history_deferred"),
                          "unretained": r.stats.get("history_unretained")}
