"""#10090 — the ESPN tennis pass holds no row while it works on the next match.

## the ship

Live tennis prices stop freezing for up to 29 s every five minutes behind the
tennis score sync.

## the defect

Production 10/29 04:10Z (R8, master 980edb3b): a backend from the background
dyno sat idle in transaction 29.18 s, its last statement this pass's score stamp
(`UPDATE events SET score_source=CASE WHEN … WHERE events.id AND home_score IS
NOT DISTINCT FROM …`, `write_row_if_unmoved(what="tennis score")`). It blocked
the live EI writer, which in turn held two `win_probability_sources` stamps.
`_sync_tennis_from_espn` committed once, after its loop over up to ~1000 rows,
so every row it wrote stayed locked until the last one was done.

## the arm

Statement order on the real task: every match's work begins with no `events`
UPDATE outstanding since the last COMMIT. RED at 980edb3b (the second match's
work followed the first match's score stamp with no commit between). The write
control: both stamps still land.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, event as sa_event, select
from sqlalchemy.orm import Session

from tests.test_live_state_does_not_run_backwards_6056 import _tennis_competition

MATCHES = (
    ("182705", "Carlos Alcaraz", "Roman Safiullin"),
    ("182706", "Jannik Sinner", "Daniil Medvedev"),
)


@pytest.mark.asyncio
async def test_no_tennis_match_is_worked_while_a_written_row_is_uncommitted(monkeypatch):
    import app.services.espn_tennis as espn_tennis
    import app.tasks.espn_sync as espn_sync
    import app.utils.espn_tennis_anchor as anchor
    from app.models.models import Base, Event, Sport
    from app.utils.score_observation import SCORE_SOURCE_ESPN

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine, tables=[Event.__table__, Sport.__table__])
    sync_session = Session(engine, expire_on_commit=False)

    # sqlite reloads datetimes naive; the anchor window compares against an
    # aware `now`. Rail fidelity gap, not a production shape.
    @sa_event.listens_for(sync_session, "loaded_as_persistent")
    def _reattach_utc(_sess, instance):  # pragma: no cover - test rail
        for attr, value in list(instance.__dict__.items()):
            if isinstance(value, datetime) and value.tzinfo is None:
                instance.__dict__[attr] = value.replace(tzinfo=timezone.utc)

    sport = Sport(key="tennis_atp_us_open", name="tennis_atp_us_open")
    sync_session.add(sport)
    sync_session.flush()

    # Offset FIRST, then truncate to the minute the board carries (gotcha #44).
    started = (datetime.now(timezone.utc) - timedelta(hours=2)).replace(
        second=0, microsecond=0
    )
    # Each row is anchored and already holds the 1-0 its board says, so the
    # pass's only write per row is the confirm-only score stamp — the holder's
    # statement on production.
    ids = {}
    for offset, (comp_id, home, away) in enumerate(MATCHES):
        row = Event(
            sport_id=sport.id,
            home_team_name=home,
            away_team_name=away,
            commence_time=started - timedelta(minutes=offset),
            status="live",
            espn_id=comp_id,
            home_score=1,
            away_score=0,
        )
        sync_session.add(row)
        sync_session.flush()
        ids[comp_id] = row.id
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

        async def flush(self):
            self._s.flush()

        async def commit(self):
            self._s.commit()
            log.append("COMMIT")

    class _Ctx:
        async def __aenter__(self_inner):
            return _AsyncShim(sync_session)

        async def __aexit__(self_inner, *exc):
            return False

    board = [{
        "events": [{
            "name": "US Open",
            "groupings": [{
                "grouping": {"slug": "mens-singles"},
                "competitions": [
                    _tennis_competition(
                        comp_id, [home, away], home_sets=1, away_sets=0,
                        date=(started - timedelta(minutes=offset)).strftime(
                            "%Y-%m-%dT%H:%MZ"
                        ),
                    )
                    for offset, (comp_id, home, away) in enumerate(MATCHES)
                ],
            }],
        }]
    }]
    monkeypatch.setattr(espn_tennis, "fetch_scoreboards", lambda dates=None: (board, []))
    monkeypatch.setattr(espn_sync, "get_task_session", lambda: _Ctx())

    # A match's work starts at its state decision — the first thing the pass
    # does with an anchored row, before any of that row's writes.
    real_authority_write = anchor.authority_write

    def _mark_match(**kwargs):
        log.append("MATCH")
        return real_authority_write(**kwargs)

    monkeypatch.setattr(anchor, "authority_write", _mark_match)

    stats = await espn_sync._sync_tennis_from_espn()

    matches = [i for i, entry in enumerate(log) if entry == "MATCH"]
    assert len(matches) == 2, (stats, log)
    # The arm reached its question: a row was written before the second match.
    assert "UPDATE" in log[: matches[1]], log
    for i in matches:
        since_commit = log[:i][::-1]
        held = since_commit.index("COMMIT") if "COMMIT" in since_commit else len(since_commit)
        assert "UPDATE" not in since_commit[:held], (
            f"match {matches.index(i) + 1} was worked with an uncommitted events "
            f"UPDATE outstanding: {log}"
        )

    # WRITE CONTROL: confirmation only, nothing lost to a race, both stamps landed.
    assert stats["row_errors"] == 0, stats
    assert stats["score_writes"] == 0, stats
    assert stats["score_write_lost_race"] == 0, stats
    assert stats.get("score_confirmation_lost_race", 0) == 0, stats
    sync_session.expire_all()
    landed = dict(
        sync_session.execute(
            select(Event.id, Event.score_source).where(Event.id.in_(ids.values()))
        ).all()
    )
    assert landed == {i: SCORE_SOURCE_ESPN for i in ids.values()}, landed
    assert log[-1] == "COMMIT", log
