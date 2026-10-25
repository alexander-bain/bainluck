"""#10090 — a deleted event does not owe a chart write forever.

Production 2026-10-22: event 15331401's row was deleted after a stamp had
committed its owed chart point. `win_prob_snapshots` has an FK to `events`,
so every drain raised ForeignKeyViolation, the savepoint restored the custody
row, and the point was retried every 5 s for ever (restarts reload it).

The fix retires a point only on positive evidence: it already failed once AND
its events row is absent now (ids are never reused). Unit policy cases on the
#11181 rig, with the existence lookup answered by the test and the FK raised by
the chart write. The real FK, table and restart are proven on Postgres in
`tests/integration/test_owed_chart_custody_11181_pg.py`.
"""

import asyncio
from contextlib import asynccontextmanager

import pytest

from tests import test_next_quote_owns_no_chart_wait_10090 as base
from tests.test_owed_chart_custody_11181 import _quote

A = "2026-10-11T00:52:30+00:00"
B = "2026-10-11T00:52:55+00:00"


class _Rows:
    def __init__(self, rows):
        self._rows = rows

    def first(self):
        return self._rows[0] if self._rows else None


def _rig(monkeypatch, *, gone=(), chart_fails=()):
    """Two live events on the #11181 rig. `gone`: event ids whose events row is
    absent (the chart write raises the FK, the lookup finds nothing).
    `chart_fails`: event ids whose NEXT chart write fails for another reason
    (a lock timeout on a present row), once each."""
    from app.tasks import live_blend_refresh as blend

    real_rig = base._HeadlineRig._rig
    monkeypatch.setattr(
        base._HeadlineRig, "_rig",
        lambda self, mp, count, **kw: real_rig(self, mp, 2, **kw),
    )
    r, session, frames, price = base._ready_rig(monkeypatch)
    gone, fails = set(gone), set(chart_fails)
    calls, lookups, lookup_error = [], [], []

    async def chart(session_, **kw):
        eid = kw["event_id"]
        if eid in gone:
            raise RuntimeError(
                'insert or update on table "win_prob_snapshots" violates foreign '
                'key constraint "win_prob_snapshots_event_id_fkey"'
            )
        if eid in fails:
            fails.discard(eid)
            raise RuntimeError("canceling statement due to lock timeout")
        calls.append((eid, kw["home_win_probability"], kw["observed_at"]))
        return object(), True

    monkeypatch.setattr("app.tasks.snapshots._create_or_update_win_prob_snapshot", chart)
    real_execute = session.execute

    async def execute(statement, *args, **kwargs):
        cols = list(getattr(statement, "selected_columns", ()))
        if (
            len(cols) == 1 and getattr(cols[0], "name", None) == "id"
            and getattr(getattr(cols[0], "table", None), "name", None) == "events"
        ):
            eid = next(iter(statement.compile().params.values()))
            lookups.append(eid)
            if lookup_error:
                raise lookup_error.pop(0)
            return _Rows([] if eid in gone else [(eid,)])
        return await real_execute(statement, *args, **kwargs)

    session.execute = execute
    clock = [1000.0]
    monkeypatch.setattr(blend, "_mono", lambda: clock[0])
    return r, session, price, clock, calls, lookups, lookup_error


async def _first_attempt(r):
    await base._custody_read(r)
    await r.refresh([1, 2], flush_started=1000)
    await r._history_task


async def _retry(r, clock, at=None):
    clock[0] = at if at is not None else clock[0] + r.failed_retry_interval_s
    await r.refresh_pending(flush_started=clock[0])
    await r._history_task


def _owed_events(r):
    return sorted(row[1] for row in r._chart_custody.rows.values())


@pytest.mark.asyncio
async def test_a_gone_event_is_retired_on_its_retry_while_its_sibling_drains(monkeypatch):
    r, session, price, clock, calls, lookups, _ = _rig(monkeypatch, gone={1})
    await _first_attempt(r)
    # The first attempt is unchanged: no lookup, the FK fails it, debt kept.
    assert lookups == []
    assert calls == [(2, 0.40, A)], "the healthy sibling is paid in the same drain"
    assert _owed_events(r) == [1] and [p[0] for p in r._history] == [1]
    assert r.stats.get("history_event_gone", 0) == 0 and r.stats["errors"] == 1
    assert 1 in r._history_retry_at

    # The sibling owes a new point (one reservation spacing later) in the
    # drain that retries the gone event.
    _quote(session, price, 0.60, B)
    clock[0] = 1025.0
    await r.refresh([2], flush_started=clock[0])
    await r._history_task
    assert lookups == [1]
    assert calls == [(2, 0.40, A), (2, 0.60, B)], "no chart write for the gone event"
    assert r.stats.get("history_event_gone", 0) == 1 and r.stats["errors"] == 1
    assert not r._chart_custody.rows, "its custody row is settled with the retirement"
    assert not r._history and not r._history_count
    assert not r._history_retry_at and not r._history_reserved
    assert 1 not in r._last_snapshot_at, "a retirement takes no chart slot"


@pytest.mark.asyncio
async def test_a_present_event_that_failed_once_is_written_on_its_retry(monkeypatch):
    """Legitimate debt: a lock timeout on a present row is retried and paid."""
    r, session, price, clock, calls, lookups, _ = _rig(monkeypatch, chart_fails={1})
    await _first_attempt(r)
    assert lookups == [] and calls == [(2, 0.40, A)] and _owed_events(r) == [1]
    await _retry(r, clock)
    assert lookups == [1]
    assert calls == [(2, 0.40, A), (1, 0.40, A)]
    assert r.stats.get("history_event_gone", 0) == 0
    assert not r._chart_custody.rows and not r._history


@pytest.mark.asyncio
async def test_a_failed_commit_of_the_retirement_keeps_the_debt_and_counts_nothing(
    monkeypatch,
):
    r, session, price, clock, calls, lookups, _ = _rig(monkeypatch, gone={1})
    inner = r._session_factory.__wrapped__
    failing = [False]

    @asynccontextmanager
    async def factory():
        seen = len(lookups)
        async with inner() as s:
            yield s
        if failing[0] and len(lookups) > seen:
            failing[0] = False
            raise RuntimeError("history outer COMMIT failed")

    r._session_factory = r._chart_custody._transactional(factory)
    await _first_attempt(r)
    failing[0] = True
    await _retry(r, clock)
    assert lookups == [1] and not failing[0], "the retirement ran and its COMMIT failed"
    assert r.stats.get("history_event_gone", 0) == 0, "a failed COMMIT never reports retirement"
    assert _owed_events(r) == [1] and [p[0] for p in r._history] == [1]
    assert r.stats["errors"] == 2
    await _retry(r, clock)
    assert lookups == [1, 1] and r.stats.get("history_event_gone", 0) == 1
    assert not r._chart_custody.rows and not r._history
    assert calls == [(2, 0.40, A)]


@pytest.mark.asyncio
async def test_a_lookup_error_keeps_the_debt(monkeypatch):
    r, session, price, clock, calls, lookups, lookup_error = _rig(monkeypatch, gone={1})
    await _first_attempt(r)
    lookup_error.append(RuntimeError("connection reset during the lookup"))
    await _retry(r, clock)
    assert lookups == [1] and r.stats.get("history_event_gone", 0) == 0
    assert _owed_events(r) == [1] and [p[0] for p in r._history] == [1]
    await _retry(r, clock)
    assert r.stats.get("history_event_gone", 0) == 1 and not r._chart_custody.rows


@pytest.mark.asyncio
async def test_a_cancelled_lookup_keeps_the_debt_and_propagates(monkeypatch):
    r, session, price, clock, calls, lookups, lookup_error = _rig(monkeypatch, gone={1})
    await _first_attempt(r)
    eid, value, reading, observed_clock, _ready = r._history[0]
    lookup_error.append(asyncio.CancelledError())
    with pytest.raises(asyncio.CancelledError):
        await r._write_owed_snapshots(
            [(eid, value, reading)], observed_clock, r._session_factory,
            verify_event=True,
        )
    assert lookups == [1] and r.stats.get("history_event_gone", 0) == 0
    assert _owed_events(r) == [1]
