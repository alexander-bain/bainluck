"""#11254 — a withdrawn venue's last price is not a feed card's fallback, on real Postgres.

When the blend has no answer, ``routes/feed.py`` serves the newest non-NULL
``win_prob_snapshots`` row as the card's current probability. Live's withdrawal
path (#10090) marks a removed venue with one NULL history row whose
``game_state`` is ``{"live_source_withdrawal": true}``. The old statement
skipped that row and served the venue's previous price. On a single-source live
game that put the retired number back on the Discover card.

This file EXECUTES ``SNAPSHOT_FALLBACK_SQL`` over rows built for each case.
``test_the_seed_reproduces_the_defect_under_the_old_statement`` runs the old
statement on the same rows and shows the seed can tell them apart, so a green
run here is not vacuous.

Opt-in on ``SEARCH_TEST_DATABASE_URL`` like its neighbours, and named by a step
in the ``database-integration`` CI job (a ``*_pg.py`` nobody names runs nowhere).
"""

import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.models.models import Event, Sport, WinProbSnapshot
from app.utils.feed_snapshot_fallback import SNAPSHOT_FALLBACK_SQL

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not DB_URL,
        reason=(
            "set SEARCH_TEST_DATABASE_URL to run the real-Postgres feed snapshot "
            "fallback gate (the database-integration CI job provides one)"
        ),
    ),
]

# gotcha #44 — a fixed anchor, offsets only.
_T0 = datetime(2026, 10, 18, 0, 0, tzinfo=timezone.utc)

#: The statement #11254 replaced, kept only as the control.
_OLD_SQL = """
    SELECT DISTINCT ON (event_id) event_id, home_win_probability
    FROM win_prob_snapshots
    WHERE event_id = ANY(:ids)
      AND home_win_probability IS NOT NULL
    ORDER BY event_id, captured_at DESC
"""

_WITHDRAWN = {"live_source_withdrawal": True}

#: case name -> (rows as (source, minutes, home, game_state), expected fallback)
_CASES = {
    # The defect: Polymarket was the only contributor and was withdrawn.
    "single_source_withdrawn": (
        [("polymarket", -10, 0.82, None), ("polymarket", 0, None, _WITHDRAWN)],
        None,
    ),
    # Another venue's last reading still stands, even though it is older.
    "other_source_survives": (
        [
            ("kalshi", -30, 0.40, None),
            ("polymarket", -10, 0.82, None),
            ("polymarket", 0, None, _WITHDRAWN),
        ],
        Decimal("0.4000"),
    ),
    # The venue quoted again after the withdrawal, so it is back.
    "requote_after_withdrawal": (
        [
            ("polymarket", -10, 0.82, None),
            ("polymarket", 0, None, _WITHDRAWN),
            ("polymarket", 5, 0.61, None),
        ],
        Decimal("0.6100"),
    ),
    # Withdrawn, back, withdrawn again: the latest withdrawal wins.
    "withdrawn_twice": (
        [
            ("polymarket", -10, 0.82, None),
            ("polymarket", 0, None, _WITHDRAWN),
            ("polymarket", 5, 0.61, None),
            ("polymarket", 9, None, _WITHDRAWN),
        ],
        None,
    ),
    # A NULL row without the marker has never meant "withdrawn".
    "ordinary_null": (
        [("polymarket", -10, 0.82, None), ("polymarket", 0, None, {"period": 2})],
        Decimal("0.8200"),
    ),
    # Only JSON true counts, the same as Live's history reader.
    "string_true_is_not_a_withdrawal": (
        [
            ("polymarket", -10, 0.82, None),
            ("polymarket", 0, None, {"live_source_withdrawal": "true"}),
        ],
        Decimal("0.8200"),
    ),
    "false_is_not_a_withdrawal": (
        [
            ("polymarket", -10, 0.82, None),
            ("polymarket", 0, None, {"live_source_withdrawal": False}),
        ],
        Decimal("0.8200"),
    ),
    # A marker on a row that still carries a price is not Live's vertex.
    "marker_with_a_price_is_not_a_withdrawal": (
        [("polymarket", -10, 0.82, None), ("polymarket", 0, 0.55, _WITHDRAWN)],
        Decimal("0.5500"),
    ),
    # One venue's withdrawal never retires another venue's newer reading.
    "withdrawal_is_per_source": (
        [
            ("kalshi", -60, 0.30, None),
            ("kalshi", -40, None, _WITHDRAWN),
            ("polymarket", -20, 0.70, None),
        ],
        Decimal("0.7000"),
    ),
}


async def _seed(session):
    sport = Sport(key="basketball_nba_11254", name="#11254 NBA", active=True)
    session.add(sport)
    await session.flush()

    ids: dict[str, int] = {}
    for i, (name, (rows, _expected)) in enumerate(_CASES.items()):
        ev = Event(
            sport_id=sport.id,
            home_team_name=f"11254 Home {i}",
            away_team_name=f"11254 Away {i}",
            commence_time=_T0 - timedelta(hours=1),
            status="live",
        )
        session.add(ev)
        await session.flush()
        ids[name] = ev.id
        for source, minutes, home, game_state in rows:
            session.add(
                WinProbSnapshot(
                    event_id=ev.id,
                    source=source,
                    captured_at=_T0 + timedelta(minutes=minutes),
                    home_win_probability=home,
                    away_win_probability=None if home is None else round(1 - home, 4),
                    game_state=game_state,
                    reading_count=1,
                )
            )
    await session.commit()
    return ids


@pytest.fixture
async def seeded_db():
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    import app.models.models  # noqa: F401 — registers every table on Base
    from app.services.database import Base

    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        ids = await _seed(session)

    async with maker() as session:
        yield session, ids

    await engine.dispose()


async def _fallbacks(session, sql, ids):
    rows = (await session.execute(text(sql), {"ids": list(ids.values())})).all()
    by_id = {int(r.event_id): Decimal(r.home_win_probability).quantize(Decimal("0.0001")) for r in rows}
    return {name: by_id.get(event_id) for name, event_id in ids.items()}


async def test_each_case_gets_the_expected_fallback(seeded_db):
    session, ids = seeded_db
    got = await _fallbacks(session, SNAPSHOT_FALLBACK_SQL, ids)
    expected = {name: case[1] for name, case in _CASES.items()}
    assert got == expected


async def test_the_seed_reproduces_the_defect_under_the_old_statement(seeded_db):
    """The control. Without it, a fixture that never served the retired price
    would pass the test above for the wrong reason."""
    session, ids = seeded_db
    old = await _fallbacks(session, _OLD_SQL, ids)
    assert old["single_source_withdrawn"] == Decimal("0.8200")
    assert old["withdrawn_twice"] == Decimal("0.6100")
    assert old["other_source_survives"] == Decimal("0.8200")
    # Everything the fix must leave alone reads the same under both statements.
    new = await _fallbacks(session, SNAPSHOT_FALLBACK_SQL, ids)
    unchanged = {
        "requote_after_withdrawal",
        "ordinary_null",
        "string_true_is_not_a_withdrawal",
        "false_is_not_a_withdrawal",
        "marker_with_a_price_is_not_a_withdrawal",
    }
    assert {n: old[n] for n in unchanged} == {n: new[n] for n in unchanged}


# --- #1459: the two-pass reader returns the single statement's answer ---------
#
# `read_snapshot_fallbacks` runs the statement over the last
# SNAPSHOT_FALLBACK_RECENT_WINDOW first, then the unchanged statement for the
# ids that pass left unanswered. Each case below is placed against the window
# edge `_SINCE`; the answer must equal one execution of SNAPSHOT_FALLBACK_SQL,
# and the expected value is written out so equality cannot be two wrongs.

from app.utils.feed_snapshot_fallback import (  # noqa: E402
    SNAPSHOT_FALLBACK_RECENT_SQL,
    SNAPSHOT_FALLBACK_RECENT_WINDOW,
    read_snapshot_fallbacks,
)

_NOW = _T0 + timedelta(days=1)
_SINCE = _NOW - SNAPSHOT_FALLBACK_RECENT_WINDOW
_US = timedelta(microseconds=1)

#: case -> (rows as (source, captured_at, home, game_state), expected, pass 1 answers?)
_WINDOW_CASES = {
    # A valid row exactly on the edge is inside it.
    "valid_on_the_edge": (
        [("kalshi", _SINCE - timedelta(hours=2), 0.30, None), ("kalshi", _SINCE, 0.35, None)],
        Decimal("0.3500"),
        True,
    ),
    # One microsecond before the edge is history: pass 2 answers.
    "valid_just_before_the_edge": (
        [("kalshi", _SINCE - timedelta(hours=2), 0.30, None), ("kalshi", _SINCE - _US, 0.36, None)],
        Decimal("0.3600"),
        False,
    ),
    # The only in-window reading is withdrawn in the window; the other venue's
    # older reading, before the window, is the answer.
    "in_window_withdrawal_falls_back_to_history": (
        [
            ("kalshi", _SINCE - timedelta(hours=4), 0.40, None),
            ("polymarket", _NOW - timedelta(hours=1), 0.82, None),
            ("polymarket", _NOW - timedelta(minutes=30), None, _WITHDRAWN),
        ],
        Decimal("0.4000"),
        False,
    ),
    # A withdrawal before the window, then a re-quote inside it.
    "earlier_withdrawal_then_in_window_requote": (
        [
            ("polymarket", _SINCE - timedelta(hours=3), 0.82, None),
            ("polymarket", _SINCE - timedelta(hours=2), None, _WITHDRAWN),
            ("polymarket", _NOW - timedelta(hours=1), 0.61, None),
        ],
        Decimal("0.6100"),
        True,
    ),
    # A withdrawal before the window retires the venue's earlier price, and
    # nothing is in the window: still nothing.
    "earlier_withdrawal_with_nothing_in_window": (
        [
            ("polymarket", _SINCE - timedelta(hours=3), 0.82, None),
            ("polymarket", _SINCE - timedelta(hours=2), None, _WITHDRAWN),
        ],
        None,
        False,
    ),
    # Withdrawn, re-quoted and withdrawn again, all inside the window.
    "in_window_requote_then_withdrawal": (
        [
            ("polymarket", _NOW - timedelta(hours=2), 0.82, None),
            ("polymarket", _NOW - timedelta(hours=1), None, _WITHDRAWN),
            ("polymarket", _NOW - timedelta(minutes=30), 0.61, None),
            ("polymarket", _NOW - timedelta(minutes=10), None, _WITHDRAWN),
        ],
        None,
        False,
    ),
    # A withdrawal on the edge retires a reading at the same instant.
    "withdrawal_on_the_edge_retires_its_instant": (
        [
            ("kalshi", _SINCE - timedelta(hours=1), 0.45, None),
            ("polymarket", _SINCE, 0.82, None),
            ("polymarket", _SINCE, None, _WITHDRAWN),
        ],
        Decimal("0.4500"),
        False,
    ),
    # Another venue's withdrawal before the window never touches this one.
    "other_venue_withdrawn_earlier": (
        [
            ("polymarket", _SINCE - timedelta(hours=6), 0.70, None),
            ("polymarket", _SINCE - timedelta(hours=5), None, _WITHDRAWN),
            ("kalshi", _NOW - timedelta(hours=1), 0.55, None),
        ],
        Decimal("0.5500"),
        True,
    ),
    # All history is old.
    "all_old_history": (
        [("kalshi", _SINCE - timedelta(hours=20), 0.20, None), ("kalshi", _SINCE - timedelta(hours=10), 0.25, None)],
        Decimal("0.2500"),
        False,
    ),
    # Only ordinary NULL rows in the window; the valid reading is older.
    "only_nulls_in_window": (
        [
            ("kalshi", _SINCE - timedelta(hours=1), 0.65, None),
            ("kalshi", _NOW - timedelta(minutes=5), None, {"period": 2}),
        ],
        Decimal("0.6500"),
        False,
    ),
    # No history at all.
    "no_rows": ([], None, False),
}


@pytest.fixture
async def windowed_db():
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    import app.models.models  # noqa: F401 — registers every table on Base
    from app.services.database import Base

    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        sport = Sport(key="basketball_nba_1459", name="#1459 NBA", active=True)
        session.add(sport)
        await session.flush()
        ids: dict[str, int] = {}
        for i, (name, (rows, _expected, _p1)) in enumerate(_WINDOW_CASES.items()):
            ev = Event(
                sport_id=sport.id,
                home_team_name=f"1459 Home {i}",
                away_team_name=f"1459 Away {i}",
                commence_time=_NOW + timedelta(hours=2),
                status="scheduled",
            )
            session.add(ev)
            await session.flush()
            ids[name] = ev.id
            for source, captured_at, home, game_state in rows:
                session.add(
                    WinProbSnapshot(
                        event_id=ev.id,
                        source=source,
                        captured_at=captured_at,
                        home_win_probability=home,
                        away_win_probability=None if home is None else round(1 - home, 4),
                        game_state=game_state,
                        reading_count=1,
                    )
                )
        await session.commit()

    yield maker, engine, ids
    await engine.dispose()


def _q(value):
    return None if value is None else Decimal(value).quantize(Decimal("0.0001"))


class _Recording:
    """The session, with every statement's parameters kept in order."""

    def __init__(self, session):
        self._session = session
        self.calls: list[dict] = []

    async def execute(self, statement, params=None):
        self.calls.append(dict(params or {}))
        return await self._session.execute(statement, params)


async def test_the_two_pass_reader_returns_the_single_statements_answer(windowed_db):
    maker, _engine, ids = windowed_db
    async with maker() as session:
        single = await _fallbacks(session, SNAPSHOT_FALLBACK_SQL, ids)
        rec = _Recording(session)
        got = await read_snapshot_fallbacks(rec, list(ids.values()), now=_NOW)

    two_pass = {name: _q(got.get(event_id)) for name, event_id in ids.items()}
    expected = {name: case[1] for name, case in _WINDOW_CASES.items()}
    assert two_pass == single == expected


async def test_pass_one_answers_the_recent_ids_and_pass_two_only_the_rest(windowed_db):
    """Not an equivalence claim — the cost claim. A reader that ran the full
    statement for every id would return the same answer and save nothing."""
    maker, _engine, ids = windowed_db
    async with maker() as session:
        rec = _Recording(session)
        await read_snapshot_fallbacks(rec, list(ids.values()), now=_NOW)

    by_id = {event_id: name for name, event_id in ids.items()}
    assert len(rec.calls) == 2
    assert rec.calls[0]["since"] == _SINCE
    assert sorted(rec.calls[0]["ids"]) == sorted(ids.values())
    assert "since" not in rec.calls[1]
    pass_two = {by_id[i] for i in rec.calls[1]["ids"]}
    assert pass_two == {n for n, case in _WINDOW_CASES.items() if not case[2]}


async def test_pass_one_alone_cannot_answer_old_history(windowed_db):
    """The control: the windowed statement by itself misses every pass-2 case
    with a value, so the equivalence above depends on pass 2 running."""
    maker, _engine, ids = windowed_db
    async with maker() as session:
        rows = (
            await session.execute(
                text(SNAPSHOT_FALLBACK_RECENT_SQL),
                {"ids": list(ids.values()), "since": _SINCE},
            )
        ).all()
    answered = {int(r.event_id) for r in rows}
    by_id = {event_id: name for name, event_id in ids.items()}
    assert {by_id[i] for i in answered} == {
        n for n, case in _WINDOW_CASES.items() if case[2]
    }
    assert any(case[1] is not None and not case[2] for case in _WINDOW_CASES.values())


async def test_a_cancelled_first_pass_returns_nothing_and_runs_no_second(windowed_db):
    """A deadline that fires while pass 1 waits on the server raises to the
    caller, as the single statement did: no partial answer, no pass 2."""
    import asyncio

    maker, engine, ids = windowed_db
    async with engine.connect() as holder:
        await holder.execute(text("BEGIN"))
        await holder.execute(text("LOCK TABLE win_prob_snapshots IN ACCESS EXCLUSIVE MODE"))
        async with maker() as session:
            rec = _Recording(session)
            with pytest.raises((asyncio.TimeoutError, TimeoutError)):
                await asyncio.wait_for(
                    read_snapshot_fallbacks(rec, list(ids.values()), now=_NOW),
                    timeout=0.5,
                )
            assert len(rec.calls) == 1, "pass 2 never started"
            await session.rollback()
        await holder.execute(text("ROLLBACK"))

    # The table and a fresh session are unharmed: same answer as before.
    async with maker() as session:
        got = await read_snapshot_fallbacks(session, list(ids.values()), now=_NOW)
    assert {n: _q(got.get(i)) for n, i in ids.items()} == {
        n: case[1] for n, case in _WINDOW_CASES.items()
    }
