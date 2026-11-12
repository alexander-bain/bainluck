"""#12042: ``update_max_movement`` names the statement it was in when it times out.

It raised ``SoftTimeLimitExceeded`` on every run Fable read on Nov 12 (7:23, 8:52,
9:06 AM PT) and has no phase timings, so its one session is wrapped in a
``StatementClock`` and the summary is logged from the outer ``finally``.
"""

import logging
from contextlib import asynccontextmanager

import pytest
from celery.exceptions import SoftTimeLimitExceeded

import app.tasks as tasks_mod
from app.utils.statement_clock import StatementClock, statement_label


def test_a_label_is_the_statements_first_words():
    assert statement_label("  UPDATE   futures_markets\n SET x = 1 ") == "UPDATE futures_markets SET x = 1"
    assert len(statement_label("SELECT " + "a, " * 100)) == 72


class _Session:
    def __init__(self, fail_on=None):
        self.calls, self.fail_on = [], fail_on
        self.commits = self.rollbacks = 0

    async def execute(self, statement, *a, **k):
        self.calls.append(str(statement))
        if self.fail_on and self.fail_on in str(statement):
            raise SoftTimeLimitExceeded()
        return "result"

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1


class _Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        self.t += 1.0
        return self.t


@pytest.mark.asyncio
async def test_the_clock_times_statements_and_forwards_everything_else():
    inner = _Session()
    clock = StatementClock(inner, clock=_Clock())
    assert await clock.execute("SELECT 1") == "result"
    await clock.execute("SELECT 1")
    await clock.execute("UPDATE futures_outcomes SET a = 1")
    await clock.commit()
    await clock.rollback()
    assert inner.calls == ["SELECT 1", "SELECT 1", "UPDATE futures_outcomes SET a = 1"]
    assert inner.commits == 1 and inner.rollbacks == 1
    assert clock.totals["SELECT 1"][1] == 2
    line = clock.summary()
    assert "x2 [SELECT 1]" in line and "in_flight=none" in line and "interrupted=none" in line


@pytest.mark.asyncio
async def test_the_statement_a_timeout_interrupts_is_named():
    clock = StatementClock(_Session(fail_on="LATERAL"), clock=_Clock())
    await clock.execute("SELECT 1")
    with pytest.raises(SoftTimeLimitExceeded):
        await clock.execute("SELECT * FROM snapshots s, LATERAL (SELECT 1) x")
    line = clock.summary()
    assert "interrupted=" in line and "LATERAL" in line.split("interrupted=")[1].split(" slowest")[0]


def test_update_max_movement_logs_the_interrupted_statement(monkeypatch, caplog):
    """Drive the real task: its first statement raises the soft limit, and the
    outer finally still logs which statement it was in."""
    session = _Session(fail_on="UPDATE")

    @asynccontextmanager
    async def _fake_session(*a, **k):
        yield session

    monkeypatch.setattr("app.tasks.base.get_task_session", _fake_session)
    caplog.set_level(logging.INFO, logger=tasks_mod.logger.name)
    task = tasks_mod.celery_app.tasks["app.tasks.update_max_movement"]
    with pytest.raises(SoftTimeLimitExceeded):
        task.run(heavy=False)
    lines = [r.getMessage() for r in caplog.records if "update_max_movement statements" in r.getMessage()]
    assert lines, "no statement summary was logged"
    assert "heavy=False" in lines[0]
    assert "interrupted=" in lines[0] and "[UPDATE" in lines[0]
