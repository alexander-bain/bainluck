"""#10090 — the two remaining score writers read nothing over the network while
they hold a row.

## the ship

Live prices stop waiting behind score writes: every score writer releases a
live game's row before its next network read.

## the defect

PR #11714 gave the 30-second StatPal livescore writer a commit per sport, after
production 10/28 showed its confirm-only score stamp idle in transaction
14-18 s while the next sport's board was read, with venue price stamps refused
behind it. A read of every writer of that statement shape
(`write_live_state_if_unmoved` with scores) found two more that commit only at
the very end:

- `_sync_statpal_schedules` — one transaction over every sport. The hourly
  beats and the ESPN failover pass one sport, so there the hold covers only the
  0.5 s pause; the all-sports form (admin trigger, no `sport_key`) held each
  sport's rows through the next sport's two StatPal reads.
- `POST /api/admin/espn/sync-live-events` — one commit after the loop, so a
  game's score write stayed locked through every later game's LLM match.

The ESPN live pass (#9049), the odds poller (#837 / #10090) and the livescore
writer (#11714) already release first; the ESPN tennis pass reads its boards
before it opens a session.

## the arm

Statement order on the real writer: every network read (and the schedule
pass's pause) happens with no `events` UPDATE outstanding since the last
COMMIT. RED on master 8925b985 for both writers.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, event as sa_event, select
from sqlalchemy.orm import Session

from tests.test_live_state_does_not_run_backwards_6056 import (
    _AdminEspnEvent,
    _FixtureFetch,
    _LiveFixture,
    _ScheduleFixture,
)

NFL, NBA = "americanfootball_nfl", "basketball_nba"


def _rail():
    from app.models.models import Base, Event, ScoreSnapshot, Sport

    engine = create_engine("sqlite://")
    Base.metadata.create_all(
        engine, tables=[Event.__table__, Sport.__table__, ScoreSnapshot.__table__]
    )
    session = Session(engine, expire_on_commit=False)

    # sqlite reloads datetimes naive; the guards compare against an aware `now`.
    # Rail fidelity gap, not a production shape.
    @sa_event.listens_for(session, "loaded_as_persistent")
    def _reattach_utc(_sess, instance):  # pragma: no cover - test rail
        for attr, value in list(instance.__dict__.items()):
            if isinstance(value, datetime) and value.tzinfo is None:
                instance.__dict__[attr] = value.replace(tzinfo=timezone.utc)

    log: list[str] = []

    @sa_event.listens_for(engine, "before_cursor_execute")
    def _record(conn, cursor, statement, params, context, executemany):
        if statement.lstrip().upper().startswith("UPDATE EVENTS"):
            log.append("UPDATE")

    class _AsyncShim:
        def __init__(self, inner):
            self._s = inner

        async def execute(self, statement):
            return self._s.execute(statement)

        def add(self, obj):
            self._s.add(obj)

        async def flush(self):
            self._s.flush()

        async def commit(self):
            self._s.commit()
            log.append("COMMIT")

    return engine, session, log, _AsyncShim


def _assert_nothing_held_across(log: list[str], waits: tuple[str, ...]) -> None:
    at = [i for i, entry in enumerate(log) if entry.startswith(waits)]
    # The arm reached its question: a row was written before a later wait.
    assert at and "UPDATE" in log[: at[-1]], log
    for i in at:
        since_commit = log[:i][::-1]
        held = since_commit.index("COMMIT") if "COMMIT" in since_commit else len(since_commit)
        assert "UPDATE" not in since_commit[:held], (
            f"{log[i]} happened with an uncommitted events UPDATE outstanding: {log}"
        )


@pytest.mark.asyncio
async def test_the_schedule_pass_holds_no_row_across_the_next_sports_reads(monkeypatch):
    import app.services.statpal_api as statpal_api
    import app.tasks.statpal_sync as statpal_sync
    from app.models.models import Event, Sport
    from app.services import team_identity

    engine, session, log, _AsyncShim = _rail()
    now = datetime.now(timezone.utc)
    for key in (NFL, NBA):
        session.add(Sport(key=key, name=key))
    session.flush()
    nfl_id = session.execute(select(Sport.id).where(Sport.key == NFL)).scalar_one()
    # The row is at 5:21 Q4 28-20; the board says 3:04 Q4 28-14, a later
    # moment — so the NFL pass writes this live row, then NBA's reads follow.
    row = Event(
        sport_id=nfl_id, home_team_name="New York Giants",
        away_team_name="Dallas Cowboys", commence_time=now - timedelta(hours=3),
        status="live", period="5:21 - 4th Quarter", game_clock="5:21",
        home_score=28, away_score=20, statpal_fixture_id="280459",
        home_team_id=1, away_team_id=2,
    )
    session.add(row)
    session.commit()
    log.clear()

    boards = {
        "nfl": (
            [_ScheduleFixture(now - timedelta(hours=3), "New York Giants",
                              "Dallas Cowboys", fixture_id="280459")],
            [_LiveFixture(now - timedelta(hours=3), "New York Giants",
                          "Dallas Cowboys", raw_status="4th Quarter",
                          game_clock="3:04", scores=(28, 14))],
        ),
    }

    class _Ctx:
        async def __aenter__(self_inner):
            return _AsyncShim(session)

        async def __aexit__(self_inner, *exc):
            session.commit()
            log.append("COMMIT")
            return False

    class _Service:
        async def get_fixtures_result(self, sport):
            log.append(f"READ fixtures {sport}")
            return _FixtureFetch(list(boards.get(sport, ([], []))[0]))

        async def get_live_scores(self, sport):
            log.append(f"READ live {sport}")
            return list(boards.get(sport, ([], []))[1])

        async def close(self):
            pass

    async def _sleep(_seconds):
        log.append("PAUSE")

    class _Team:
        id = 1

    async def _resolve_team(session, source, sport_key, source_name=None):
        return _Team()

    monkeypatch.setattr(statpal_sync, "get_task_session", lambda: _Ctx())
    monkeypatch.setattr(statpal_api, "is_available", lambda: True)
    monkeypatch.setattr(statpal_api, "StatPalAPIService", _Service)
    monkeypatch.setattr(statpal_sync, "asyncio", SimpleNamespace(sleep=_sleep))
    monkeypatch.setattr(
        team_identity.team_identity_service, "resolve_team", _resolve_team
    )
    monkeypatch.setattr(
        statpal_sync, "accept_team_binding", lambda **kw: False, raising=False
    )

    # The all-sports form: every mapped key without a `sports` row is dropped
    # before its fetch, so NFL then NBA are the two sports asked.
    result = await statpal_sync._sync_statpal_schedules()

    assert [e for e in log if e.startswith("READ")] == [
        "READ fixtures nfl", "READ live nfl", "READ fixtures nba", "READ live nba",
    ], log
    _assert_nothing_held_across(log, ("READ", "PAUSE"))

    # WRITE CONTROL: the later score landed (this pass writes no position).
    assert result["schedule_live_write_lost_race"] == 0, result
    session.expire_all()
    landed = session.execute(
        select(Event.home_score, Event.away_score).where(Event.id == row.id)
    ).one()
    assert tuple(landed) == (28, 14), landed


@pytest.mark.asyncio
async def test_the_admin_espn_sync_holds_no_row_across_the_next_games_llm_match(
    monkeypatch,
):
    import app.services as services
    from app.models.models import Event, Sport
    from app.routes import admin_providers

    engine, session, log, _AsyncShim = _rail()
    sport = Sport(key=NFL, name=NFL)
    session.add(sport)
    session.flush()
    commence_time = datetime.now(timezone.utc) - timedelta(hours=2)
    # Game one is anchored by its ESPN id and ESPN is later in the game, so the
    # route writes it. Game two has no ESPN row, so the route asks the model.
    first = Event(
        sport_id=sport.id, home_team_name="New York Giants",
        away_team_name="Dallas Cowboys", commence_time=commence_time,
        status="live", period="5:26 - 4th Quarter", game_clock="5:26",
        espn_id="401872930", win_probability_sources={},
    )
    session.add(first)
    session.flush()
    second = Event(
        sport_id=sport.id, home_team_name="Green Bay Packers",
        away_team_name="Chicago Bears", commence_time=commence_time,
        status="live", win_probability_sources={},
    )
    session.add(second)
    session.commit()
    first_id = first.id
    log.clear()

    ee = _AdminEspnEvent(
        clock="5:21", status_detail="5:21 - 4th Quarter",
        home="New York Giants", away="Dallas Cowboys",
        espn_id="401872930", date=commence_time,
    )

    class _Espn:
        async def get_scoreboard(self, sport_key):
            log.append("READ espn board")
            return [ee]

    async def _llm(fn, *args, **kwargs):
        log.append("READ llm")
        return None, "no-name-match"

    monkeypatch.setattr(admin_providers, "_check_admin_secret", lambda *a, **k: True)
    monkeypatch.setattr(services, "get_espn_service", lambda: _Espn())
    monkeypatch.setattr(services.llm, "is_available", lambda: True)
    monkeypatch.setattr(admin_providers, "run_llm_off_loop", _llm)

    result = await admin_providers.sync_espn_live_events(
        request=None, secret="unused", sport_key=NFL,
        dry_run=False, skip_llm=False, db=_AsyncShim(session),
    )

    assert log.count("READ llm") == 1, log
    _assert_nothing_held_across(log, ("READ",))

    # WRITE CONTROL: game one's later position landed.
    assert result["updated"] == 1, result
    session.expire_all()
    landed = session.execute(
        select(Event.period, Event.game_clock).where(Event.id == first_id)
    ).one()
    assert tuple(landed) == ("5:21 - 4th Quarter", "5:21"), landed
