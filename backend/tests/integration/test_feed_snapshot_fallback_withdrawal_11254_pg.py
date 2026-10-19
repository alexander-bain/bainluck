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

``test_the_statement_reads_the_snapshots_table_once`` holds the follow-through:
the first fix read the same rows twice (a joined, grouped pass to find the
withdrawals), which doubled the buffers the fallback touches on production.
Its control is that first statement, kept below, which plans two scans.

Opt-in on ``SEARCH_TEST_DATABASE_URL`` like its neighbours, and named by a step
in the ``database-integration`` CI job (a ``*_pg.py`` nobody names runs nowhere).
"""

import json
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

#: The first #11254 statement: right answers, two reads of the same rows. Kept
#: only as the control for the one-scan test.
_TWO_PASS_SQL = """
    WITH retired AS (
        SELECT event_id, source, max(captured_at) AS withdrawn_at
        FROM win_prob_snapshots
        WHERE event_id = ANY(:ids)
          AND home_win_probability IS NULL
          AND game_state -> 'live_source_withdrawal' = CAST('true' AS jsonb)
        GROUP BY event_id, source
    )
    SELECT DISTINCT ON (s.event_id) s.event_id, s.home_win_probability
    FROM win_prob_snapshots s
    LEFT JOIN retired r
      ON r.event_id = s.event_id AND r.source = s.source
    WHERE s.event_id = ANY(:ids)
      AND s.home_win_probability IS NOT NULL
      AND (r.withdrawn_at IS NULL OR s.captured_at > r.withdrawn_at)
    ORDER BY s.event_id, s.captured_at DESC
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
    # A reading stamped at the withdrawal's own instant is retired with it
    # ("after", not "at or after", brings a venue back); another venue's older
    # reading still stands.
    "reading_at_the_withdrawal_instant": (
        [
            ("kalshi", -30, 0.40, None),
            ("polymarket", 0, 0.55, None),
            ("polymarket", 0, None, _WITHDRAWN),
        ],
        Decimal("0.4000"),
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
    assert old["reading_at_the_withdrawal_instant"] == Decimal("0.5500")
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


def _scans_of(plan_node, relation="win_prob_snapshots"):
    own = 1 if plan_node.get("Relation Name") == relation else 0
    return own + sum(_scans_of(child, relation) for child in plan_node.get("Plans", []))


async def _plan(session, sql, ids):
    rows = (
        await session.execute(text("EXPLAIN (FORMAT JSON) " + sql), {"ids": list(ids.values())})
    ).all()
    raw = rows[0][0]
    return (json.loads(raw) if isinstance(raw, str) else raw)[0]["Plan"]


async def test_the_statement_reads_the_snapshots_table_once(seeded_db):
    """The withdrawal check rides the same read as the fallback itself. Counted
    on the plan, so it holds whichever scan type the planner picks."""
    session, ids = seeded_db
    assert _scans_of(await _plan(session, SNAPSHOT_FALLBACK_SQL, ids)) == 1


async def test_the_two_pass_control_plans_two_scans_and_answers_the_same(seeded_db):
    """The control. The first #11254 statement must count as two scans here, or
    the test above could not tell them apart; and the rewrite must return what
    it returned on every case."""
    session, ids = seeded_db
    assert _scans_of(await _plan(session, _TWO_PASS_SQL, ids)) == 2
    assert await _fallbacks(session, _TWO_PASS_SQL, ids) == await _fallbacks(
        session, SNAPSHOT_FALLBACK_SQL, ids
    )
