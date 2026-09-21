"""A game in a weather delay stays on the live rail. #7617, real Postgres.

lane1/537 photographed the defect on production, 2026-09-20 ~22:10Z: the NFL
league page carried a section headed **"NO RESULT REPORTED"** and the only card
under it was CLE @ TB — a marquee game paused in the FOURTH QUARTER with 2:00 on
the clock and Cleveland leading by four. ESPN the same minute said
``state=in, desc=Delayed``. We were telling the reader we had nothing about the
most interesting screen on the site.

## the cause, and why it cannot be photographed twice

Nothing maps ``Delayed`` to ``suspended`` (live/470 falsified that). The
wall-clock staleness net fired, on a reading that was wrong:

    event 14782150, its ESPN win_prob_snapshots row
    captured_at 20:02:39Z · valid_until 22:00:49Z · reading_count 109

``tasks/snapshots.py`` writes a new row only when the value MOVES and otherwise
bumps ``reading_count``/``valid_until`` on the row it already has. A delay is
precisely the state in which a win probability cannot move, so ESPN reported on
that game 109 times across the pause and ``MAX(captured_at)`` — the whole of
``LAST_POST_COMMENCE_SNAPSHOT_SQL`` before this fix — read it as one observation
118 minutes stale.

## why this is a Postgres test and not a unit test

The defect is a column that a SQL expression did not select. Every existing
guard in ``test_staleness_does_not_end_a_match.py`` is either a source assertion
on the query string or a fake session that HANDS the net a ``last_snap`` — and
every one of them was green while the marquee game sat on the unreported rail,
because none of them let Postgres answer the question. So each case here seeds
real ``win_prob_snapshots`` rows, runs the real
``_transition_event_statuses_impl``, and reads the row's status back.

## the cases, and which direction each one fails in

``the_delayed_game`` is the ship. ``the_game_nobody_is_reporting_on`` is its kill
control: if the fix had disabled the net rather than corrected its reading, that
row would stay live and this file would say so. ``the_venue_tick`` is live/042 —
a Kalshi market stays open for hours after the whistle (the specimen's own row
was still being bumped at 01:00Z, two and a half hours past the final), so
reading ``valid_until`` makes the venue exclusion strictly more load-bearing than
it was. ``the_pregame_line`` holds the post-commence gate, ``the_row_with_no_
valid_until`` holds the COALESCE fallback for rows written before this column was
maintained, and ``the_suspended_row`` proves the door back: a row an earlier pass
suspended on the old reading is resumed by the next pass, so the fix heals the
rows the defect already made rather than only preventing new ones.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pytest

#: A DATABASE OF ITS OWN, never `bl_searchtest`. This file creates the handful of
#: tables the net touches and drops them again, and the shared recall database is
#: populated by eighty steps before this one — `futures_markets` there carries
#: nine inbound foreign keys, so the drop fails with `DependentObjectsStillExist`
#: before a single case runs. The disposable database is provisioned by the step
#: above this one in `search-recall` and thrown away with the runner; it holds
#: nothing but these tables, which is what makes the drop safe by construction.
#: It deliberately does NOT fall back to `$DATABASE_URL` or to the recall URL.
DB_URL = os.environ.get("DELAY_CONTRACT_DATABASE_URL")

pytestmark = [pytest.mark.asyncio]

needs_postgres = pytest.mark.skipif(
    not DB_URL,
    reason=(
        "set DELAY_CONTRACT_DATABASE_URL to run the real-Postgres delay contract "
        "(CI job `search-recall` provisions a disposable one)"
    ),
)

#: ``americanfootball`` is 4.5h in ``SPORT_MAX_DURATIONS`` and the net adds its
#: own 0.5h margin, so every seeded game starts 5.2h ago: past the bound on the
#: first pass, the way the specimen was at 22:00Z off a 17:00Z kickoff. Read from
#: the real table rather than written down, so a retune of the sport maximum
#: moves this file instead of silently making every case unreachable.
SPORT_KEY = "americanfootball_nfl"


def _hours_since_start() -> float:
    from app.tasks.config import SPORT_MAX_DURATIONS

    return SPORT_MAX_DURATIONS["americanfootball"] + 0.7


async def _seed(session):
    """Six live/suspended NFL rows, each with the snapshot history its case needs."""
    from app.models.models import Event, Sport, WinProbSnapshot

    now = datetime.now(timezone.utc)
    start = now - timedelta(hours=_hours_since_start())

    nfl = Sport(key=SPORT_KEY, name="NFL")
    session.add(nfl)
    await session.flush()

    def _game(name, status="live"):
        # Scores, a period and an espn_id: this row has been observed, so it
        # keeps the full sport maximum rather than the narrower unobserved bound
        # (#3946). The specimen carried all three.
        return Event(
            sport_id=nfl.id,
            home_team_name=f"Tampa Bay {name}",
            away_team_name=f"Cleveland {name}",
            commence_time=start,
            status=status,
            home_score=19,
            away_score=23,
            period="Delayed",
            game_clock="2:00",
            espn_id=f"7617-{name}",
        )

    rows = {
        "the_delayed_game": _game("Delayed"),
        "the_game_nobody_is_reporting_on": _game("Quiet"),
        "the_venue_tick": _game("Venue"),
        "the_pregame_line": _game("Pregame"),
        "the_row_with_no_valid_until": _game("NullVU"),
        "the_suspended_row": _game("Resumed", status="suspended"),
    }
    session.add_all(list(rows.values()))
    await session.flush()

    def _snap(event, source, captured_at, valid_until, reading_count=1):
        session.add(
            WinProbSnapshot(
                event_id=event.id,
                source=source,
                captured_at=captured_at,
                valid_until=valid_until,
                home_win_probability=0.5001,
                away_win_probability=0.4999,
                reading_count=reading_count,
            )
        )

    # The specimen's own shape: one reading that began two hours ago and has been
    # re-observed ever since. 109 is the production count.
    _snap(
        rows["the_delayed_game"],
        "espn",
        start + timedelta(minutes=2),
        now - timedelta(seconds=90),
        reading_count=109,
    )
    # Genuinely gone quiet: the reading began AND ended long ago.
    _snap(
        rows["the_game_nobody_is_reporting_on"],
        "espn",
        start + timedelta(minutes=2),
        now - timedelta(hours=2),
        reading_count=40,
    )
    # A market that is still quoting. It is the freshest row in the table and it
    # must not count: a price says nothing about play (live/042).
    _snap(
        rows["the_venue_tick"],
        "kalshi",
        start + timedelta(minutes=2),
        now - timedelta(seconds=10),
        reading_count=200,
    )
    # A pregame line, re-read all afternoon. Excluded on where the reading
    # BEGAN, however long it has been renewed.
    _snap(
        rows["the_pregame_line"],
        "espn",
        start - timedelta(minutes=10),
        now - timedelta(seconds=30),
        reading_count=300,
    )
    # Written before anything maintained `valid_until`; the fallback has to read
    # it exactly as the old query did.
    _snap(
        rows["the_row_with_no_valid_until"],
        "espn",
        now - timedelta(minutes=2),
        None,
    )
    # Already suspended by an earlier pass on the old reading, and the authority
    # has been reporting on it throughout.
    _snap(
        rows["the_suspended_row"],
        "espn",
        start + timedelta(minutes=2),
        now - timedelta(seconds=60),
        reading_count=109,
    )

    await session.commit()
    return {name: row.id for name, row in rows.items()}


@pytest.fixture
async def seeded():
    """Real Postgres, real schema.

    Function-scoped for the reason `test_search_recall_contract.py` gives:
    `pytest.ini` leaves `asyncio_default_fixture_loop_scope` unset, so a
    module-scoped async fixture outlives the loop that created its engine.
    """
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    import app.models.models  # noqa: F401 — registers every table on Base
    from app.services.database import Base

    # ONLY THE TABLES THE NET TOUCHES, and that is a portability fact rather
    # than a performance one: `uq_container_anchor` is declared
    # `NULLS NOT DISTINCT`, which is Postgres 15 syntax, so a whole-schema
    # `create_all` dies on the 14 a developer is likely to have locally. The
    # closure below is transitive (`events` carries FKs to sports, teams and
    # venues), and a table this net reads that is missing from it raises rather
    # than passing quietly — the net would not be able to run at all.
    wanted = [
        Base.metadata.tables[name]
        for name in (
            "sports",
            "teams",
            "venues",
            "events",
            "win_prob_snapshots",
            "futures_markets",
        )
    ]

    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all, tables=wanted, checkfirst=True)
        await conn.run_sync(Base.metadata.create_all, tables=wanted)

    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        ids = await _seed(session)

    yield maker, ids

    await engine.dispose()


@pytest.fixture
async def statuses(seeded):
    """Run the real net once, return ``{case: status}`` read back from the row.

    ``get_task_session`` is replaced rather than pointed at the test database,
    so the pass runs on this fixture's engine and nothing depends on the
    process-wide ``DATABASE_URL`` the app imported at startup. It commits on a
    clean exit, exactly as the real one does.
    """
    import contextlib
    from unittest.mock import patch

    from sqlalchemy import select

    from app.models.models import Event

    maker, ids = seeded

    @contextlib.asynccontextmanager
    async def _session(**_kwargs):
        async with maker() as session:
            yield session
            await session.commit()

    from app.tasks.espn_sync import _transition_event_statuses_impl

    with patch("app.tasks.base.get_task_session", _session):
        stats = await _transition_event_statuses_impl()

    async with maker() as session:
        rows = (
            await session.execute(
                select(Event.id, Event.status).where(Event.id.in_(list(ids.values())))
            )
        ).all()

    by_id = {row.id: row.status for row in rows}
    return {name: by_id[event_id] for name, event_id in ids.items()}, stats


@needs_postgres
class TestADelayIsNotSilence:
    """#7617 — the ship, and the controls that keep it from being a no-op."""

    async def test_the_delayed_game_stays_live(self, statuses):
        """THE SHIP. RED before #7617: `MAX(captured_at)` read this row's single
        109-reading observation as two hours old and the net suspended it, which
        is what put a marquee NFL game under "NO RESULT REPORTED" while it was
        being played."""
        by_case, _ = statuses

        assert by_case["the_delayed_game"] == "live"

    async def test_the_game_nobody_is_reporting_on_is_still_suspended(self, statuses):
        """THE KILL CONTROL. A fix that widened the reading far enough to
        disable the net would pass the test above and fail this one. The net's
        real job — stop a row claiming to be live when nothing is reporting on
        it — is unchanged."""
        by_case, stats = statuses

        assert by_case["the_game_nobody_is_reporting_on"] == "suspended"
        assert stats["live_to_suspended"] >= 1

    async def test_a_venue_tick_does_not_hold_a_game_live(self, statuses):
        """live/042. The Kalshi row is the freshest in the table by two minutes;
        a market stays open long after the whistle, so a price may never be the
        evidence that play continues. Reading `valid_until` makes this exclusion
        MORE load-bearing than it was, which is why it is asserted here rather
        than left to the filter's own unit test."""
        by_case, _ = statuses

        assert by_case["the_venue_tick"] == "suspended"

    async def test_a_pregame_line_does_not_hold_a_game_live(self, statuses):
        """The post-commence gate still keys on where the reading BEGAN. A line
        first published before kickoff says nothing about play, however many
        times it is re-read afterwards."""
        by_case, _ = statuses

        assert by_case["the_pregame_line"] == "suspended"

    async def test_a_row_with_no_valid_until_reads_exactly_as_before(self, statuses):
        """The COALESCE fallback. Rows predating the column's maintenance carry
        NULL, and for them the answer must be the old one — `captured_at` two
        minutes ago holds this game live."""
        by_case, _ = statuses

        assert by_case["the_row_with_no_valid_until"] == "live"

    async def test_a_row_the_old_reading_suspended_comes_back(self, statuses):
        """The door back. The resume arm consults the same query, so the fix
        heals the rows the defect has already made instead of only preventing
        the next one — the difference between a reader waiting one minute and a
        reader waiting for the final whistle."""
        by_case, stats = statuses

        assert by_case["the_suspended_row"] == "live"
        assert stats["suspended_to_live"] >= 1
