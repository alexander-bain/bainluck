"""#10090 — the StatPal livescore writer reads no board while it holds a row.

## the ship

Live games' prices stop freezing every minute behind the score updater.

## the defect

Production 10/28 00:00-00:02Z: three holders from the realtime dyno sat idle in
transaction 14.0-18.5 s, each one's last statement the confirm-only score stamp
(`UPDATE events SET score_source=…, score_observed_at=… WHERE id AND period AND
game_clock AND home_score AND away_score`), with 5-9 venue price stamps refused
behind each under their 500 ms lock budget. `_sync_statpal_livescores` held one
transaction over every sport, so the rows one sport wrote stayed locked while
the next sport's StatPal board was fetched — the ESPN live pass's #9049 defect,
on the 30-second writer.

## the arm

Statement order on the real task: every StatPal read happens with no `events`
UPDATE outstanding since the last COMMIT. RED at 76013097 (the second sport's
read followed the first sport's confirm stamp with no commit between). The lock
itself, on real Postgres, is
`tests/integration/test_espn_pass_releases_rows_pg_9049.py::TestStatPalLivescoresHoldNoRowAcrossTheNextBoard`.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, event as sa_event, select
from sqlalchemy.orm import Session

from tests.test_live_state_does_not_run_backwards_6056 import _Fixture

NHL, MLB = "icehockey_nhl", "baseball_mlb"


@pytest.mark.asyncio
async def test_no_statpal_board_is_read_while_a_written_row_is_uncommitted(monkeypatch):
    import app.services.statpal_api as statpal_api
    import app.tasks.statpal_sync as statpal_sync
    from app.models.models import Base, Event, ScoreSnapshot, Sport
    from app.utils.score_observation import SCORE_SOURCE_STATPAL

    engine = create_engine("sqlite://")
    Base.metadata.create_all(
        engine, tables=[Event.__table__, Sport.__table__, ScoreSnapshot.__table__]
    )
    sync_session = Session(engine, expire_on_commit=False)

    # sqlite reloads datetimes naive; the premature-live guard (#1945) compares
    # against an aware `now`. Rail fidelity gap, not a production shape.
    @sa_event.listens_for(sync_session, "loaded_as_persistent")
    def _reattach_utc(_sess, instance):  # pragma: no cover - test rail
        for attr, value in list(instance.__dict__.items()):
            if isinstance(value, datetime) and value.tzinfo is None:
                instance.__dict__[attr] = value.replace(tzinfo=timezone.utc)

    now = datetime.now(timezone.utc)
    boards = {
        "nhl": _Fixture(
            now - timedelta(minutes=40), "San Jose Sharks", "Anaheim Ducks",
            raw_status="2nd Period", game_clock="10:00", scores=(1, 0),
        ),
        "mlb": _Fixture(
            now - timedelta(minutes=40), "Seattle Mariners", "Los Angeles Angels",
            raw_status="Top 5th", game_clock=None, scores=(2, 1),
            clock_field_served=False,
        ),
    }
    # Each row already holds what its board says (NHL its anchor too), so the
    # pass's only write per row is the confirm-only stamp — the holder's
    # statement on production.
    rows = {}
    for key, home, away, period, clock, scores, anchor in (
        (NHL, "San Jose Sharks", "Anaheim Ducks", "10:00 - 2nd Period", "10:00",
         (1, 0), boards["nhl"].fixture_id),
        (MLB, "Seattle Mariners", "Los Angeles Angels", "Top 5th", None,
         (2, 1), None),
    ):
        sport = Sport(key=key, name=key)
        sync_session.add(sport)
        sync_session.flush()
        row = Event(
            sport_id=sport.id, home_team_name=home, away_team_name=away,
            commence_time=now - timedelta(minutes=40), status="live",
            period=period, game_clock=clock,
            home_score=scores[0], away_score=scores[1],
            statpal_fixture_id=anchor,
        )
        sync_session.add(row)
        sync_session.flush()
        rows[key] = row.id
    sync_session.commit()

    log: list[str] = []

    @sa_event.listens_for(engine, "before_cursor_execute")
    def _record(conn, cursor, statement, params, context, executemany):
        if statement.lstrip().upper().startswith("UPDATE EVENTS"):
            log.append("UPDATE")

    class _AsyncShim:
        def __init__(self, session):
            self._s = session

        async def execute(self, statement):
            return self._s.execute(statement)

        def add(self, obj):
            self._s.add(obj)

        async def commit(self):
            self._s.commit()
            log.append("COMMIT")

        async def flush(self):
            self._s.flush()

    class _Ctx:
        async def __aenter__(self_inner):
            return _AsyncShim(sync_session)

        async def __aexit__(self_inner, *exc):
            sync_session.commit()
            log.append("COMMIT")
            return False

    class _Service:
        async def get_live_scores(self, sport):
            log.append(f"READ {sport}")
            board = boards.get(sport)
            return [board] if board else []

        async def close(self):
            pass

    monkeypatch.setattr(statpal_sync, "get_task_session", lambda: _Ctx())
    monkeypatch.setattr(statpal_api, "is_available", lambda: True)
    monkeypatch.setattr(statpal_api, "StatPalAPIService", _Service)

    result = await statpal_sync._sync_statpal_livescores()

    reads = [i for i, entry in enumerate(log) if entry.startswith("READ")]
    assert len(reads) == 2, log
    # The arm reached its question: a row was written before the second read.
    assert "UPDATE" in log[: reads[1]], log
    for i in reads:
        since_commit = log[:i][::-1]
        held = since_commit.index("COMMIT") if "COMMIT" in since_commit else len(since_commit)
        assert "UPDATE" not in since_commit[:held], (
            f"{log[i]} was read with an uncommitted events UPDATE outstanding: {log}"
        )

    # WRITE CONTROL: confirmation only, and both stamps landed.
    assert result["events_updated"] == 0, result
    assert result["livescore_confirmation_lost_race"] == 0, result
    sync_session.expire_all()
    stamps = dict(
        sync_session.execute(
            select(Event.id, Event.score_source).where(Event.id.in_(rows.values()))
        ).all()
    )
    assert stamps == {rows[NHL]: SCORE_SOURCE_STATPAL, rows[MLB]: SCORE_SOURCE_STATPAL}, stamps
