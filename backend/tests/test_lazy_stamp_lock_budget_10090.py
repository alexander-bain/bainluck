"""Skipped known readings need no GUC; cold reads and writes stay bounded."""

from copy import copy
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy.sql.dml import Update

from app.tasks.live_blend_refresh import FRESH_STAMP_WORKERS
from app.utils.repair_lock_budget import (
    SET_LOCK_AND_STATEMENT_TIMEOUT_SQL, SET_LOCK_TIMEOUT_SQL, SET_STATEMENT_TIMEOUT_SQL,
)

#: #11138: the stamp bounds its UPDATE as a whole statement, the cold read only
#: its lock waits.
BUDGETS = {
    id(SET_LOCK_TIMEOUT_SQL): "budget",
    id(SET_LOCK_AND_STATEMENT_TIMEOUT_SQL): "stamp_budget",
    id(SET_STATEMENT_TIMEOUT_SQL): "statement_bound",
}
from tests.test_live_blend_refresh import (
    _RecordingSession, _event_and_market, _one_event_refresher,
    is_normal_publication_intent,
)


class _Canceled(Exception):
    sqlstate = "57014"  # query_canceled: what statement_timeout raises


def rig(
    monkeypatch, *, count=1, skipped="unobserved", named=False, cold=False, fail=False,
    cancel=None,
):
    observed = datetime(2026, 10, 8, 18, tzinfo=timezone.utc)
    returned = {"polymarket": {"value": 0.9, "updated_at": observed.isoformat()}}
    event, market = _event_and_market()
    rows = []
    for eid in range(1, count + 1):
        e, m = copy(event), copy(market)
        e.id = m.event_id = eid
        m.id = eid * 10
        e.home_team_name = str(eid)
        e.win_probability_sources = returned if skipped == "unobserved" else None
        rows.append((m, e))

    class Session(_RecordingSession):
        def __init__(self):
            super().__init__(rows, [], returned)
            self.returned_rev = 42
            self.calls = []

        async def execute(self, statement, *args, **kwargs):
            if id(statement) in BUDGETS:
                self.calls.append(BUDGETS[id(statement)])
                if fail:
                    raise RuntimeError("budget setup failed")
            elif isinstance(statement, Update):
                self.calls.append("update")
                if cancel == "update":
                    raise _Canceled("canceling statement due to statement timeout")
            elif is_normal_publication_intent(statement):
                self.calls.append("intent")
            else:
                self.calls.append("read")
            return await super().execute(statement, *args, **kwargs)

        def begin_nested(self):
            self.calls.append("savepoint")
            return super().begin_nested()

    session = Session()
    r, frames = _one_event_refresher(monkeypatch, session, min_refresh_interval_s=0)
    r._last_snapshot_at = dict.fromkeys(range(1, count + 1), 1000)
    if not cold:
        r._inversion = dict.fromkeys(range(1, count + 1), (float("inf"), False))
    if skipped == "unchanged":
        r._last_written_value = dict.fromkeys(range(1, count + 1), 0.9)
        r._last_write_at = dict.fromkeys(range(1, count + 1), 1000)

    def reading(group, home, away):
        if skipped == "no_reading":
            return None
        return SimpleNamespace(
            home_probability=0.9, eligibility=None, named_home_quote=named,
            outcome=SimpleNamespace(id=int(home), last_updated=observed),
        )

    async def orientation_read(session, eid, home_prob, source):
        assert session.calls[-1] == "budget", "cold orientation lost its lock bound"
        session.calls.append("orientation_read")
        if cancel == "orientation":
            raise _Canceled("canceling statement due to user request")
        return home_prob

    monkeypatch.setattr("app.utils.live_blend.compute_source_home_probability", reading)
    monkeypatch.setattr(
        "app.tasks.prediction_market_matching._check_and_fix_inversion", orientation_read,
    )
    return SimpleNamespace(**locals())


@pytest.mark.parametrize("skipped", ["unobserved", "unchanged", "no_reading"])
@pytest.mark.parametrize("named", [False, True])
async def test_known_skipped_readings_do_not_issue_lock_budget_sql(monkeypatch, skipped, named):
    x = rig(monkeypatch, skipped=skipped, named=named)
    await x.r.refresh([1], flush_started=1000)
    assert x.session.calls == ["read"]
    assert x.frames == [] and x.r.stats["stamped"] == 0


async def test_prepared_skipped_group_has_no_write_session_statement(monkeypatch):
    x = rig(monkeypatch, count=5)
    await x.r.refresh(range(1, 6), flush_started=1000)
    # The shared preparation read, plus one reread per queued fresh event
    # behind the worker slots (6d8b493900) — reads only, no budget or write.
    assert x.session.calls == ["read"] * (1 + 5 - FRESH_STAMP_WORKERS), (
        "only the preparation read and the queued rereads remain"
    )
    assert x.frames == [] and x.r.stats["unobserved_skipped"] == 5


async def test_mixed_group_installs_one_budget_before_savepoint_and_actual_update(monkeypatch):
    x = rig(monkeypatch, count=2)
    x.rows[1][1].win_probability_sources = None
    await x.r.refresh([1, 2], flush_started=1000)
    # fe0aa54fbf: each fresh stamp reads its own event in its own session;
    # e0b52e11ed: each owns its transaction, so no sibling savepoint. The
    # skipped event still issues nothing past its read.
    assert x.session.calls.count("read") == 2
    # attempt151: the stamp's publication intent follows its UPDATE.
    assert [c for c in x.session.calls if c != "read"] == ["stamp_budget", "update", "intent"]
    assert [f["event_id"] for f in x.frames] == [2]


async def test_cold_orientation_read_retains_its_existing_lock_budget(monkeypatch):
    x = rig(monkeypatch, cold=True)
    await x.r.refresh([1], flush_started=1000)
    assert x.session.calls == ["read", "budget", "orientation_read"]
    assert x.frames == [] and x.r.stats["unobserved_skipped"] == 1


async def test_a_cold_stamp_adds_only_the_statement_bound_before_its_update(monkeypatch):
    """#11138: the cold read keeps the lock budget alone; the stamp's UPDATE
    then gains the whole-statement bound without re-sending the lock budget."""
    x = rig(monkeypatch, cold=True, skipped=None)
    await x.r.refresh([1], flush_started=1000)
    assert x.session.calls == [
        "read", "budget", "orientation_read", "statement_bound", "update", "intent",
    ]
    assert [f["event_id"] for f in x.frames] == [1]


@pytest.mark.parametrize("count", [2, 5])
async def test_budget_failure_requeues_entire_batch_or_groups(monkeypatch, count):
    x = rig(monkeypatch, count=count, skipped=None, fail=True)
    await x.r.refresh(range(1, count + 1), flush_started=1000)
    assert x.r.pending_event_ids() == frozenset(range(1, count + 1))
    assert set(x.r._failed_hold_until) == set(range(1, count + 1))
    assert x.frames == [] and x.session.updates == []
    # e0b52e11ed: one write transaction, and so one contained error, per event.
    assert x.r.stats["errors"] == count


async def test_a_statement_bound_cancel_requeues_like_a_lock_timeout(monkeypatch):
    """#11138: the stamp's whole-statement bound firing is a row wait past its
    budget — the price is stored, so the event is owed at once, not failed."""
    x = rig(monkeypatch, skipped=None, cancel="update")
    await x.r.refresh([1], flush_started=1000)
    assert x.session.calls[-2:] == ["stamp_budget", "update"]
    assert x.r.stats["lock_skipped"] == 1 and x.r.stats["errors"] == 0, x.r.stats
    assert x.r._lock_retry == {1} and 1 not in x.r._failed_hold_until
    assert x.frames == [] and x.r.stats["stamped"] == 0


async def test_a_cancel_before_the_stamp_armed_its_bound_stays_an_error(monkeypatch):
    """A 57014 the stamp did not arm (an operator's cancel during the cold
    orientation read) is not the bound firing: it keeps the failure path."""
    x = rig(monkeypatch, cold=True, skipped=None, cancel="orientation")
    await x.r.refresh([1], flush_started=1000)
    assert "statement_bound" not in x.session.calls and "update" not in x.session.calls
    assert x.r.stats["lock_skipped"] == 0 and x.r.stats["errors"] == 1, x.r.stats
    assert x.r._lock_retry == set()
