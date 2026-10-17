"""lane1 countercase for PR11181 fe19d1624c (root 154425Z): the quiet final
observation must stay recoverable when BOTH the ordinary backlog and the spill
are occupied. Small fixture bounds (limit 1, spill 1) on the existing
_ready_rig. Unit policy proof only; no production-clock claim."""
import asyncio
import pytest
from tests.test_next_quote_owns_no_chart_wait_10090 import _ready_rig

WANT = [(.40, "2026-10-11T00:52:30+00:00"),
        (.50, "2026-10-11T00:52:55+00:00"),
        (.60, "2026-10-11T00:53:20+00:00")]


def _quote(session, price, value, stamp):
    price[0] = value
    session._returned = {"polymarket": {"value": value, "updated_at": stamp}}


async def _fill_both_then_final(monkeypatch):
    r, session, frames, price = _ready_rig(monkeypatch)
    r._history_limit, r._history_spill_limit = 1, 2
    entered, release, calls = asyncio.Event(), asyncio.Event(), []

    async def chart(session_, **kw):
        calls.append(kw)
        entered.set()
        await release.wait()
        return object(), True

    monkeypatch.setattr("app.tasks.snapshots._create_or_update_win_prob_snapshot", chart)
    await r.refresh([1], flush_started=1000)            # .40 writing: backlog full
    await asyncio.wait_for(entered.wait(), 1)
    _quote(session, price, .50, WANT[1][1])
    await asyncio.wait_for(r.refresh([1], flush_started=1025), .25)  # spill full
    _quote(session, price, .60, WANT[2][1])
    await asyncio.wait_for(r.refresh([1], flush_started=1050), .25)  # due final
    return r, frames, calls, release


@pytest.mark.asyncio
async def test_quiet_final_past_backlog_and_spill_is_recovered(monkeypatch):
    r, frames, calls, release = await _fill_both_then_final(monkeypatch)
    release.set()
    await r.drain_history()
    await r.refresh_pending(flush_started=1075)          # venue quiet: no new quote
    await r.drain_history()
    paid = [(c["home_win_probability"], c["observed_at"]) for c in calls]
    assert [f["source_value"] for f in frames] == [.40, .50, .60]
    assert paid == WANT, {"history": paid, "pending": list(r.pending_event_ids()),
                          "deferred": r.stats.get("history_deferred"),
                          "unretained": r.stats.get("history_unretained")}


@pytest.mark.asyncio
async def test_quiet_final_past_backlog_and_spill_survives_handoff(monkeypatch):
    """Same occupancy via the PR's own failed-writer hand-off shape."""
    from app.tasks import live_blend_refresh as blend
    r, session, frames, price = _ready_rig(monkeypatch)
    r._history_limit, r._history_spill_limit = 1, 2
    clock, failing, calls = [1000.0], [True], []
    monkeypatch.setattr(blend, "_mono", lambda: clock[0])

    async def chart(session_, **kw):
        calls.append(kw)
        if failing[0]:
            raise RuntimeError("retry on next run")
        return object(), True

    monkeypatch.setattr("app.tasks.snapshots._create_or_update_win_prob_snapshot", chart)
    await r.refresh([1], flush_started=1000)
    await r._history_task
    for at, (value, stamp) in ((1025, WANT[1]), (1050, WANT[2])):
        _quote(session, price, value, stamp)
        clock[0] += 2
        await asyncio.wait_for(r.refresh([1], flush_started=at), .25)
        if r._history_task is not None:
            await r._history_task
    blend.hand_off_pending(r)
    replacement, _, _, _ = _ready_rig(monkeypatch)
    monkeypatch.setattr("app.tasks.snapshots._create_or_update_win_prob_snapshot", chart)
    failing[0] = False
    clock[0] = 1080
    blend.adopt_handed_off(replacement)
    await replacement.refresh_pending(flush_started=1080)  # venue quiet
    await replacement.drain_history()
    paid = [(c["home_win_probability"], c["observed_at"]) for c in calls]
    tail = paid[-3:]
    assert tail == WANT, {"paid_after_handoff": tail,
                          "unretained": r.stats.get("history_unretained"),
                          "deferred": r.stats.get("history_deferred")}
