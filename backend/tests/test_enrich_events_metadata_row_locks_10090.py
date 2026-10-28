"""#10090: the hourly event-metadata enrichment commits BEFORE it counts.

`_enrich_events_metadata` classifies the 50 newest unenriched events — today's
live and upcoming games — by plain ORM attribute assignment. Nothing is written
until the next query autoflushes. On master that next query was the "count
remaining" fetch-all of every unenriched id, so autoflush took the 50 row locks
and the full-table scan then held them until the session exited: a 45 s holder
measured on production 10/28 23:25Z, with live `opening_home_probability`
stamps (500 ms lock budget) queued behind it.

The guard reads the order of statements the task sends: an explicit commit
lands after the classification and before the count, and the count is a
server-side ``count(*)`` rather than a fetch of every id. The real-Postgres
control (another session UPDATEs an enriched row while the count runs) lives in
``tests/integration/test_enrich_events_metadata_row_locks_10090_pg.py``.
"""

from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest
from sqlalchemy.dialects import postgresql

from app.tasks import espn_sync


def _sql(stmt) -> str:
    return str(stmt.compile(dialect=postgresql.dialect())).lower()


class _Result:
    def __init__(self, rows=None, scalar=None):
        self._rows = rows or []
        self._scalar = scalar

    def scalars(self):
        return self

    def all(self):
        return list(self._rows)

    def scalar(self):
        return self._scalar


class _RecordingSession:
    """Logs what the task sends, and which events were assigned at each step."""

    def __init__(self, events, remaining):
        self.events = events
        self.remaining = remaining
        self.log = []
        self._selected = False

    def _assigned(self):
        return sum(1 for e in self.events if e.llm_gender is not None)

    async def execute(self, stmt):
        sql = _sql(stmt)
        self.log.append(("execute", sql, self._assigned()))
        if not self._selected:
            self._selected = True
            return _Result(rows=self.events)
        if "count(" in sql:
            return _Result(scalar=self.remaining)
        # The old fetch-all shape: one row per unenriched id.
        return _Result(rows=[(i,) for i in range(self.remaining)])

    async def commit(self):
        self.log.append(("commit", None, self._assigned()))


def _event(i):
    return SimpleNamespace(
        id=i,
        sport=SimpleNamespace(key="americanfootball_nfl"),
        away_team_name=f"Away {i}",
        home_team_name=f"Home {i}",
        llm_gender=None,
        llm_level=None,
        llm_league=None,
        llm_importance=None,
    )


def _install(monkeypatch, session):
    @asynccontextmanager
    async def _fake_task_session(*args, **kwargs):
        yield session
        # The real helper commits here; recorded separately so an exit commit
        # can never be mistaken for the in-body commit the fix adds.
        session.log.append(("session-exit", None, session._assigned()))

    monkeypatch.setattr(espn_sync, "get_task_session", _fake_task_session)

    from app.services import llm

    monkeypatch.setattr(llm, "is_available", lambda: False)
    monkeypatch.setattr(llm, "classify_gender_cached", lambda t, s: "men")
    monkeypatch.setattr(llm, "classify_level_cached", lambda t, s: "professional")
    monkeypatch.setattr(llm, "classify_league_cached", lambda t, s: "NFL")
    monkeypatch.setattr(llm, "classify_importance_cached", lambda t, s: "regular_season")


@pytest.mark.asyncio
async def test_enrichment_commits_before_the_remaining_count(monkeypatch):
    events = [_event(i) for i in range(3)]
    session = _RecordingSession(events, remaining=7)
    _install(monkeypatch, session)

    stats = await espn_sync._enrich_events_metadata(limit=3)

    kinds = [k for k, _, _ in session.log]
    assert kinds == ["execute", "commit", "execute", "session-exit"], session.log

    # The commit carries every assignment: nothing is left for the count's
    # autoflush to write (and so lock) inside the counting transaction.
    _, _, assigned_at_commit = session.log[1]
    assert assigned_at_commit == len(events)

    _, count_sql, _ = session.log[2]
    assert "count(" in count_sql, count_sql
    assert "llm_gender is null" in count_sql and "llm_level is null" in count_sql
    assert "limit" not in count_sql

    assert stats == {
        "processed": 3,
        "enriched": 3,
        "errors": 0,
        "remaining": 7,
        "llm_available": False,
    }


@pytest.mark.asyncio
async def test_nothing_to_enrich_counts_server_side(monkeypatch):
    session = _RecordingSession([], remaining=0)
    _install(monkeypatch, session)

    stats = await espn_sync._enrich_events_metadata(limit=50)

    assert [k for k, _, _ in session.log] == ["execute", "execute", "session-exit"]
    assert "count(" in session.log[1][1]
    assert stats["remaining"] == 0 and stats["processed"] == 0
