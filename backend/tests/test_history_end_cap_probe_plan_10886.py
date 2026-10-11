"""#10886: history's end-cap probe must never aggregate the bare ``captured_at``.

`_end_cap_hides_every_point` asks ``min(captured_at)`` for one event. Postgres
may answer a bare ``min(col)`` by walking an index on ``col`` from the low end
and stopping at the first row that passes the ``WHERE`` — and both snapshot
tables carry an all-events ``captured_at`` index. Production planned exactly
that for win-prob (plan-only EXPLAIN, 2026-10-11):

    Limit -> Index Scan using ix_winprob_captured  Filter: (event_id = X)

against 9.5M rows. pg_stat_statements: 119 calls, mean 54.4 s, max 177.4 s;
~120 chart requests ran past the 30 s router deadline in one 17-minute window.
The expression form plans ``Aggregate -> Index Scan using
ix_winprob_event_source (event_id = X)``.

The guard reads the SQL the helper actually sends, compiled for the production
dialect, so a later edit that drops the expression goes red here rather than
on the next storm.
"""

import asyncio
import re
from datetime import datetime, timedelta, timezone

from sqlalchemy.dialects import postgresql

from app.routes.events import _end_cap_hides_every_point

UTC = timezone.utc
CAP = datetime(2026, 9, 1, 6, 30, tzinfo=UTC)


class _Result:
    def __init__(self, value):
        self._value = value

    def scalar(self):
        return self._value


class _RecordingSession:
    """Answers each probe by table and keeps the SQL it was sent."""

    def __init__(self, win_prob_min=None, odds_min=None):
        self._answers = {"win_prob_snapshots": win_prob_min, "odds_snapshots": odds_min}
        self.sql = []

    async def execute(self, statement, *_a, **_kw):
        sql = str(statement.compile(dialect=postgresql.asyncpg.dialect()))
        self.sql.append(sql)
        for table, value in self._answers.items():
            if f"FROM {table}" in sql:
                return _Result(value)
        raise AssertionError(f"unexpected statement: {sql}")


def _run(session):
    return asyncio.run(_end_cap_hides_every_point(session, 15327378, CAP))


def _bare_min(sql):
    return re.search(r"min\(\s*\w+\.captured_at\s*\)", sql)


def test_both_probes_aggregate_an_expression_not_the_bare_column():
    # win-prob empty, so the helper reaches the odds fallback too.
    session = _RecordingSession(win_prob_min=None, odds_min=None)
    assert _run(session) is False
    assert len(session.sql) == 2, session.sql
    for table, sql in zip(("win_prob_snapshots", "odds_snapshots"), session.sql):
        assert f"FROM {table}" in sql
        assert not _bare_min(sql), sql
        assert f"min({table}.captured_at + interval '0 seconds')" in sql, sql


def test_answers_are_unchanged_by_the_rewrite():
    after = CAP + timedelta(hours=9, minutes=26)
    before = CAP - timedelta(minutes=1)
    # Win-prob decides when it has a row; odds is never asked.
    s = _RecordingSession(win_prob_min=after, odds_min=before)
    assert _run(s) is True and len(s.sql) == 1
    s = _RecordingSession(win_prob_min=before, odds_min=after)
    assert _run(s) is False and len(s.sql) == 1
    # No win-prob rows: odds decides.
    assert _run(_RecordingSession(odds_min=after)) is True
    assert _run(_RecordingSession(odds_min=before)) is False
