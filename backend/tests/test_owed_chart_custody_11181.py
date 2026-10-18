"""#11181 — every chart point a committed live stamp owes has durable custody.

Unit policy cases on the existing `_ready_rig`, with the transactional custody
double (`_MemoryCustody`). The real table's atomic boundary, replay and
restart are proven on Postgres in
`tests/integration/test_owed_chart_custody_11181_pg.py`.
"""

import ast
import asyncio
import inspect

import pytest

from tests.test_next_quote_owns_no_chart_wait_10090 import (
    _custody,
    _custody_read,
    _ready_rig,
)

A = "2026-10-11T00:52:30+00:00"
B = "2026-10-11T00:52:55+00:00"


def _quote(session, price, value, stamp):
    price[0] = value
    session._returned = {"polymarket": {"value": value, "updated_at": stamp}}


def _recording_chart(monkeypatch, calls):
    async def chart(session, **kw):
        calls.append(kw)
        return object(), True

    monkeypatch.setattr(
        "app.tasks.snapshots._create_or_update_win_prob_snapshot", chart
    )


def _earlier_row(store, source, event_id, value, observed_at):
    """A row a previous run or process committed and never paid."""
    custody_id, store._next = store._next, store._next + 1
    store.rows[custody_id] = (source, event_id, value, {
        "home_probability": value, "away_probability": None,
        "draw_probability": None, "yes_probability": value,
        "market_name": "game", "market_id": 10, "outcome_name": "home",
        "observed_at": observed_at,
    })
    return custody_id


def test_both_production_consumers_give_their_refresher_custody():
    """Without custody a refresher keeps owed points in memory alone, which a
    restart empties: production must always pass one."""
    from app.tasks import kalshi_ws, polymarket_ws

    for module, consumer in (
        (kalshi_ws, "_run_kalshi_ws_consumer"),
        (polymarket_ws, "_run_polymarket_ws_consumer"),
    ):
        tree = ast.parse(inspect.getsource(module))
        node = next(
            n for n in ast.walk(tree)
            if isinstance(n, ast.AsyncFunctionDef) and n.name == consumer
        )
        calls = [
            c for c in ast.walk(node)
            if isinstance(c, ast.Call) and getattr(c.func, "id", None) == "LiveBlendRefresher"
        ]
        assert calls, consumer
        for call in calls:
            custody = [k.value for k in call.keywords if k.arg == "chart_custody"]
            assert custody and isinstance(custody[0], ast.Call), consumer
            assert custody[0].func.id == "OwedChartCustody", consumer


def test_a_reading_round_trips_through_custody_with_its_time_verbatim():
    from app.tasks.live_blend_refresh import (
        _chart_reading, _chart_reading_from_payload, _chart_reading_payload,
    )
    from types import SimpleNamespace

    live = _chart_reading(
        SimpleNamespace(
            home_probability=0.4, away_probability=0.6, draw_probability=None,
            yes_probability=0.41, market=SimpleNamespace(id=10, name="game"),
            outcome=SimpleNamespace(name="home"),
        ),
        A,
    )
    loaded = _chart_reading_from_payload(7, _chart_reading_payload(live))
    assert loaded.snapshot_observed_at == A
    assert loaded.custody_id == 7 and loaded.owned_history
    for field in ("home_probability", "away_probability", "draw_probability",
                  "yes_probability", "market", "outcome"):
        assert getattr(loaded, field) == getattr(live, field), field


@pytest.mark.asyncio
async def test_a_new_run_pays_earlier_rows_first_then_its_own_point(monkeypatch):
    """Restart order: rows an earlier process left are paid at their own times
    before the new run's first point for the same event, which stays in
    custody until the run's first read has moved them into memory."""
    store = _custody(monkeypatch)
    _earlier_row(store, "polymarket", 1, 0.30, "2026-10-11T00:51:40+00:00")
    _earlier_row(store, "polymarket", 1, 0.35, "2026-10-11T00:52:05+00:00")
    _earlier_row(store, "kalshi", 1, 0.99, "2026-10-11T00:52:06+00:00")
    r, session, frames, price = _ready_rig(monkeypatch)
    calls = []
    _recording_chart(monkeypatch, calls)
    await r.refresh([1], flush_started=1000)
    await r.drain_history()
    await r.refresh_pending(flush_started=1002)
    await r.drain_history()
    assert [(c["home_win_probability"], c["observed_at"]) for c in calls] == [
        (0.30, "2026-10-11T00:51:40+00:00"),
        (0.35, "2026-10-11T00:52:05+00:00"),
        (0.40, A),
    ]
    assert [f["source_value"] for f in frames] == [0.40]
    assert [row[0] for row in store.rows.values()] == ["kalshi"], "per source"
    assert not r._history and not r._history_count and not r._custody_backlog


@pytest.mark.asyncio
async def test_a_row_already_settled_elsewhere_is_never_written_again(monkeypatch):
    """A commit whose acknowledgement was lost, or another drain, settled the
    row first: the point it carried is paid, so this drain writes nothing."""
    r, session, frames, price = _ready_rig(monkeypatch)
    calls, entered, release = [], asyncio.Event(), asyncio.Event()

    async def chart(session_, **kw):
        calls.append(kw)
        entered.set()
        await release.wait()
        return object(), True

    monkeypatch.setattr(
        "app.tasks.snapshots._create_or_update_win_prob_snapshot", chart
    )
    await _custody_read(r)
    await r.refresh([1], flush_started=1000)
    await asyncio.wait_for(entered.wait(), 1)
    _quote(session, price, 0.60, B)
    await asyncio.wait_for(r.refresh([1], flush_started=1025), 0.25)
    second = r._history[1][2].custody_id
    del r._chart_custody.rows[second]  # paid by another drain
    release.set()
    await r.drain_history()
    assert [c["home_win_probability"] for c in calls] == [0.40]
    assert r.stats["history_already_paid"] == 1
    assert not r._history and not r._history_count and not r._chart_custody.rows


@pytest.mark.asyncio
async def test_a_stamp_whose_custody_row_fails_does_not_commit(monkeypatch):
    """The atomic boundary at the unit level: no committed stamp without its
    owed point's row. The failed stamp is not recorded as written, so the
    next quote is stamped and owes its point as usual."""
    r, session, frames, price = _ready_rig(monkeypatch)
    calls = []
    _recording_chart(monkeypatch, calls)
    await _custody_read(r)
    real = r._chart_custody.record

    async def failing(*args, **kwargs):
        raise RuntimeError("custody insert refused")

    r._chart_custody.record = failing
    await r.refresh([1], flush_started=1000)
    assert not frames and not r._last_written_value
    assert not r._history and not r._history_count and not r._chart_custody.rows
    r._chart_custody.record = real
    await r.refresh([1], flush_started=1030)
    await r.drain_history()
    assert [f["source_value"] for f in frames] == [0.40]
    assert [(c["home_win_probability"], c["observed_at"]) for c in calls] == [(0.40, A)]
    assert not r._chart_custody.rows


@pytest.mark.asyncio
async def test_a_custody_read_overlapping_a_custody_only_commit_keeps_reading(
    monkeypatch,
):
    """A point committed to custody alone while a read is in flight may be
    invisible to it; the read cannot conclude the table is drained."""
    r, session, frames, price = _ready_rig(monkeypatch)
    store = r._chart_custody
    real_load = store.load

    async def overlapping(session_, source, held, limit):
        rows = await real_load(session_, source, held, limit)
        r._custody_only_committed += 1  # committed after this read's snapshot
        return rows

    store.load = overlapping
    await r.refresh_pending(flush_started=999)
    await r._history_task
    assert r._custody_backlog, "an overlapped read must not clear the backlog"
    store.load = real_load
    await r.refresh_pending(flush_started=1000)
    await r._history_task
    assert not r._custody_backlog


@pytest.mark.asyncio
async def test_an_owned_point_is_never_skipped_by_the_snapshot_throttle(monkeypatch):
    """Its custody row is settled in the same savepoint, so a throttle skip
    there would delete the row and write nothing. The reservation already
    spaced it; a sibling written moments before must not stop it (lane1 M6)."""
    from app.tasks.live_blend_refresh import _chart_reading
    from types import SimpleNamespace

    r, session, frames, price = _ready_rig(monkeypatch)
    calls = []
    _recording_chart(monkeypatch, calls)
    r._last_snapshot_at[1] = 1000.0
    owned = _chart_reading(
        SimpleNamespace(
            home_probability=0.4, away_probability=None, draw_probability=None,
            yes_probability=0.4, market=SimpleNamespace(id=10, name="game"),
            outcome=SimpleNamespace(name="home"),
        ),
        A,
    )
    await r._maybe_snapshot(session, 1, 0.4, owned, 1001.0)
    assert [(c["home_win_probability"], c["observed_at"]) for c in calls] == [(0.4, A)]
    assert r._last_snapshot_at == {1: 1001.0}
    # Unchanged for a reading that is not owned: the cadence still applies.
    unowned = SimpleNamespace(**{**owned.__dict__, "owned_history": False})
    await r._maybe_snapshot(session, 1, 0.5, unowned, 1002.0)
    assert len(calls) == 1
