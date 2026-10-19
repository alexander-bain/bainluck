"""#11296 — the pregame projection read returns each book's last row BEFORE the start, on real Postgres.

The unit sibling (``tests/test_pregame_projection_11296.py``) pins selection on
hand-built rows. It cannot see what the server returns for
``PREGAME_PROJECTION_SQL``: ``unnest`` of two positional arrays, a recursive
loose index scan over each event's books and a strict-bound ``LATERAL`` top-1.
Those are Postgres constructs, and the defect this ship exists to prevent, an
IN-PLAY pair served as the pregame forecast, is a wrong row coming back from
that statement.

So this file seeds real ``odds_snapshots`` on both sides of each start and
checks four things:

* the statement returns exactly what a plain ``DISTINCT ON`` oracle returns;
* the seed can tell a dropped bound apart (control);
* the read, end to end through ``read_pregame_projections`` on real ORM rows,
  serves the pregame pair and refuses the in-play-only final;
* with the production index present the statement is served by it, with no
  sequential scan of ``odds_snapshots`` (a shape check, not a timing).

Opt-in on ``SEARCH_TEST_DATABASE_URL`` like its neighbours. The schema is
created if absent and only this file's own fixed ids are seeded and removed,
so it shares the database with the other gates in its CI step.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import select, text

from app.utils.odds_math import project_scores
from app.utils.pregame_projection import (
    PREGAME_PROJECTION_SQL,
    PROJECTION_KEY,
    REASON_NO_PREGAME_READING,
    UNAVAILABLE_KEY,
    plan_pregame_projections,
    read_pregame_projections,
)

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not DB_URL,
        reason=(
            "set SEARCH_TEST_DATABASE_URL to run the real-Postgres #11296 "
            "pregame projection read (the database-integration CI job provides one)"
        ),
    ),
]

# gotcha #44: a fixed anchor, offsets only.
_T0 = datetime(2026, 10, 18, 17, 0, tzinfo=timezone.utc)
#: This file's own event ids, so it can share a database and clean up after itself.
_IDS = {"A": 911_296_11, "B": 911_296_12, "C": 911_296_13, "D": 911_296_14}

#: The oracle: every row, one per (event, book), newest strictly before the
#: event's cutoff. Lives in the test so nothing in production can drift onto it.
_ORACLE_SQL = """
    SELECT DISTINCT ON (s.event_id, s.bookmaker)
           s.id, s.event_id, s.bookmaker
    FROM odds_snapshots s
    JOIN unnest(cast(:ids as integer[]), cast(:cutoffs as timestamptz[]))
         AS u(event_id, cutoff) ON u.event_id = s.event_id
    WHERE s.captured_at < u.cutoff
    ORDER BY s.event_id, s.bookmaker, s.captured_at DESC, s.id DESC
"""

#: The live statement with its bound deleted — only to show the seed notices.
_UNBOUNDED_SQL = PREGAME_PROJECTION_SQL.replace("AND s.captured_at < k.cutoff", "")


@pytest.fixture
async def maker():
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    import app.models.models  # noqa: F401 — registers every table on Base
    from app.services.database import Base

    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(lambda sync: Base.metadata.create_all(sync, checkfirst=True))
        # The production index the statement is written for
        # (`4623658a2704`, created out of band — gotcha #31).
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_odds_snapshots_bookmaker_closing "
            "ON odds_snapshots (event_id, bookmaker, captured_at DESC)"
        ))
    await _clear(engine)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await _clear(engine)
    await engine.dispose()


async def _clear(engine):
    ids = list(_IDS.values())
    async with engine.begin() as conn:
        await conn.execute(
            text("DELETE FROM odds_snapshots WHERE event_id = ANY(:ids)"), {"ids": ids}
        )
        await conn.execute(text("DELETE FROM events WHERE id = ANY(:ids)"), {"ids": ids})


async def _seed(maker):
    """Three settled NFL games and one scheduled, rows on both sides of each start.

    Returns ``{name: event_id}`` and ``{label: snapshot_id}`` for the rows the
    answers must be.
    """
    from app.models.models import Event, OddsSnapshot, Sport

    ids: dict[str, int] = {}
    want: dict[str, int] = {}
    async with maker() as session:
        sport = (
            await session.execute(select(Sport).where(Sport.key == "americanfootball_nfl"))
        ).scalar_one_or_none()
        if sport is None:
            sport = Sport(key="americanfootball_nfl", name="NFL", active=True)
            session.add(sport)
            await session.flush()

        def game(name, start, status="completed"):
            ev = Event(
                id=_IDS[name],
                sport_id=sport.id,
                home_team_name=f"Home {name}",
                away_team_name=f"Away {name}",
                commence_time=start,
                commence_time_source="odds_api",
                status=status,
            )
            session.add(ev)
            return ev

        a = game("A", _T0)
        b = game("B", _T0 + timedelta(hours=3))   # starts AFTER A's in-play rows
        c = game("C", _T0)                        # only in-play rows (15328569)
        d = game("D", _T0, status="scheduled")
        await session.flush()
        ids.update(A=a.id, B=b.id, C=c.id, D=d.id)

        def snap(ev, book, minutes, spread, total, home_p=0.6):
            h, w = project_scores(spread, total)
            s = OddsSnapshot(
                event_id=ev.id, bookmaker=book,
                captured_at=ev.commence_time + timedelta(minutes=minutes),
                home_win_probability=home_p, away_win_probability=round(1 - home_p, 4),
                home_spread=spread, over_under=total,
                projected_home_score=h, projected_away_score=w, reading_count=1,
            )
            session.add(s)
            return s

        # A: two books; each has rows before AND after the start; one row AT it.
        snap(a, "draftkings", -900, -2.5, 46.5)
        want["A_dk"] = snap(a, "draftkings", -10, -3.5, 48.0)       # 25.8 / 22.2
        snap(a, "draftkings", 0, -4.5, 48.0)                         # AT start: excluded
        snap(a, "draftkings", 205, -7.4, 55.0, home_p=0.9)           # in-play
        want["A_fd"] = snap(a, "fanduel", -30, -2.5, 47.5)          # 25.0 / 22.5
        snap(a, "fanduel", 95, -10.5, 52.0, home_p=0.95)             # in-play
        snap(a, "inplayonly", 15, -1.0, 40.0)                        # no pregame row
        # B: its "in-play-looking" +60 row is before B's later start.
        want["B_dk"] = snap(b, "draftkings", 60 - 180, -6.0, 50.0)
        snap(b, "draftkings", 30, -14.0, 50.0, home_p=0.97)
        # C: every row after its start.
        snap(c, "draftkings", 205, -7.4, 55.0, home_p=0.9)
        # D: scheduled; must never be asked.
        snap(d, "draftkings", -5, -3.0, 47.0)
        await session.flush()
        want = {k: v.id for k, v in want.items()}
        await session.commit()
    return ids, want


def _binds(ids, names, starts):
    return {"ids": [ids[n] for n in names], "cutoffs": starts}


async def test_the_statement_returns_exactly_what_the_oracle_returns(maker):
    ids, want = await _seed(maker)
    binds = _binds(ids, ["A", "B", "C"], [_T0, _T0 + timedelta(hours=3), _T0])
    async with maker() as session:
        live = (await session.execute(text(PREGAME_PROJECTION_SQL), binds)).all()
        oracle = (await session.execute(text(_ORACLE_SQL), binds)).all()
    assert sorted(r.id for r in live) == sorted(r.id for r in oracle)
    assert sorted(r.id for r in live) == sorted(want.values())
    # C has no pregame row and `inplayonly` none either: absent, not NULL rows.
    assert {r.event_id for r in live} == {ids["A"], ids["B"]}


async def test_the_seed_can_tell_a_dropped_bound_apart(maker):
    ids, want = await _seed(maker)
    binds = _binds(ids, ["A", "C"], [_T0, _T0])
    async with maker() as session:
        unbounded = (await session.execute(text(_UNBOUNDED_SQL), binds)).all()
    assert sorted(r.id for r in unbounded) != sorted([want["A_dk"], want["A_fd"]])
    assert any(r.event_id == ids["C"] for r in unbounded)


async def test_swapped_cutoffs_change_the_answer(maker):
    # The arrays are positional: give A the later start and its +205 in-play row
    # is still excluded but the 0-minute row is admitted — a different answer.
    ids, want = await _seed(maker)
    right = _binds(ids, ["A", "B"], [_T0, _T0 + timedelta(hours=3)])
    swapped = _binds(ids, ["A", "B"], [_T0 + timedelta(hours=3), _T0])
    async with maker() as session:
        a = (await session.execute(text(PREGAME_PROJECTION_SQL), right)).all()
        b = (await session.execute(text(PREGAME_PROJECTION_SQL), swapped)).all()
    assert sorted(r.id for r in a) != sorted(r.id for r in b)


async def test_the_read_serves_the_pregame_pair_end_to_end(maker):
    from sqlalchemy.orm import selectinload

    from app.models.models import Event

    ids, _ = await _seed(maker)
    async with maker() as session:
        events = (
            await session.execute(
                select(Event)
                .options(selectinload(Event.sport))
                .where(Event.id.in_(list(_IDS.values())))
                .order_by(Event.id)
            )
        ).scalars().all()
        answers = await read_pregame_projections(
            session, events, lambda e: e.sport.key
        )
    a = answers[ids["A"]][PROJECTION_KEY]
    assert (a["projected_home_score"], a["projected_away_score"]) == (25.4, 22.4)
    assert a["bookmaker_count"] == 2
    assert a["latest_captured_at"] == (_T0 - timedelta(minutes=10)).isoformat()
    assert a["earliest_captured_at"] == (_T0 - timedelta(minutes=30)).isoformat()
    assert a["kind"] == "last_before_scheduled_start" and a["boundary"] == "scheduled_start"
    b = answers[ids["B"]][PROJECTION_KEY]
    assert (b["projected_home_score"], b["projected_away_score"]) == (28.0, 22.0)
    assert answers[ids["C"]] == {UNAVAILABLE_KEY: REASON_NO_PREGAME_READING}
    assert ids["D"] not in answers


async def test_the_production_index_serves_the_statement_without_a_seq_scan(maker):
    ids, _ = await _seed(maker)
    plan, _ = plan_pregame_projections(
        [SimpleNamespace(id=ids["A"], status="completed", commence_time=_T0,
                         commence_time_source="odds_api", event_tags=[])],
        lambda e: "americanfootball_nfl",
    )
    async with maker() as session:
        await session.execute(text("SET LOCAL enable_seqscan = off"))
        rows = (
            await session.execute(
                text("EXPLAIN " + PREGAME_PROJECTION_SQL),
                {"ids": plan["ids"], "cutoffs": plan["cutoffs"]},
            )
        ).all()
    shown = "\n".join(r[0] for r in rows)
    assert "ix_odds_snapshots_bookmaker_closing" in shown, shown
    assert "Seq Scan on odds_snapshots" not in shown, shown


async def test_a_bounded_read_leaves_the_sessions_timeout_as_it_found_it(maker):
    """#11295's C1 on the feed's read: the SET LOCAL dies with the savepoint."""
    from sqlalchemy import select as _select
    from sqlalchemy.orm import selectinload

    from app.models.models import Event

    ids, _ = await _seed(maker)
    async with maker() as session:
        await session.execute(text("SET LOCAL statement_timeout = '7s'"))
        events = (
            await session.execute(
                _select(Event).options(selectinload(Event.sport))
                .where(Event.id == ids["A"])
            )
        ).scalars().all()
        answers = await read_pregame_projections(
            session, events, lambda e: e.sport.key, timeout_ms=1500
        )
        after = (await session.execute(text("SHOW statement_timeout"))).scalar()
    assert PROJECTION_KEY in answers[ids["A"]]
    assert after == "7s"
