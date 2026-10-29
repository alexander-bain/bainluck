"""#10090 — the live excitement-index write neither waits on a held live row nor holds one.

WHAT PRODUCTION RECORDED. Speed's read-only lock watch, 00:45:41Z 10/29: the
scores pass's ``UPDATE events SET raw_ei=..., ei_metadata=..., ei_computed_at=...``
(transaction 5.3 s old) and the score writer's ``UPDATE events SET
score_source=...`` (2.8 s) each waited on the other — a lock-order deadlock.

WHY. ``update_live_ei`` set ``raw_ei`` on every live ``Event`` and left the write
to the pass's one commit. The flush issued one UPDATE per live game in id order
and kept each row locked until COMMIT, so a row held by another writer stalled
the flush while it still held every game it had already reached.

THE RIG. Real Postgres, two live games with enough snapshots to score. Another
transaction holds the HIGHER-id game (the flush reaches the lower one first).
The pass's own step runs — ``update_live_ei`` then the caller's commit — while
it is held, and:

1. it must finish while the row is still held (no wait), and
2. a second connection must take the LOWER-id game's row within 500 ms, the
   live price stamp's ``lock_timeout`` (no hold), and must already read its EI.

On unfixed ``origin/master`` dca1ff3baf both read the other way: the step is
still parked on the held row, and the lower game's row is locked (55P03).

Controls: ``test_the_probe_can_see_a_held_row`` (the probe is not blind), and
``test_the_ei_values_are_the_formulas`` (same values as calling the formula, so
the rewrite moved only when and how the write lands).
"""

import asyncio
import os
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.skipif(
        not DB_URL,
        reason=(
            "set SEARCH_TEST_DATABASE_URL to run the real-Postgres #10090 live EI "
            "lock gate (CI job `search-recall` provides one)"
        ),
    ),
    pytest.mark.asyncio,
]

#: The live price stamp's own bound (PR #8490).
STAMP_LOCK_TIMEOUT = "500ms"

SPORT_KEY = "basketball_nba"
SPORT_ID = 993801
FREE_GAME = 993811  # lower id: the old flush reaches and locks it first
HELD_GAME = 993812  # held by another writer for the whole step
EVENT_IDS = [FREE_GAME, HELD_GAME]
TEAM_IDS = [993821, 993822, 993823, 993824]
#: Home win probability per minute after tip: real travel, so EI scores.
PATH = (0.55, 0.62, 0.48, 0.70, 0.41)


@pytest.fixture
async def pg_engine():
    """Real schema with ``checkfirst``; drop nothing, remove only our own ids."""
    from sqlalchemy.ext.asyncio import create_async_engine

    import app.models.models  # noqa: F401 — registers every table on Base
    from app.services.database import Base

    tables = [
        Base.metadata.tables[name]
        for name in ("sports", "teams", "venues", "events", "odds_snapshots")
    ]
    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=tables, checkfirst=True)
        await _clear(conn)
        await _seed(conn)
    yield engine
    async with engine.begin() as conn:
        await _clear(conn)
    await engine.dispose()


async def _clear(conn):
    await conn.execute(
        text("DELETE FROM odds_snapshots WHERE event_id = ANY(:ids)"), {"ids": EVENT_IDS}
    )
    await conn.execute(text("DELETE FROM events WHERE id = ANY(:ids)"), {"ids": EVENT_IDS})
    await conn.execute(text("DELETE FROM teams WHERE id = ANY(:ids)"), {"ids": TEAM_IDS})
    await conn.execute(text("DELETE FROM sports WHERE id = :i"), {"i": SPORT_ID})


async def _seed(conn):
    sport_id = (
        await conn.execute(text("SELECT id FROM sports WHERE key = :k"), {"k": SPORT_KEY})
    ).scalar_one_or_none()
    if sport_id is None:
        await conn.execute(
            text("INSERT INTO sports (id, key, name, active) VALUES (:i, :k, :k, true)"),
            {"i": SPORT_ID, "k": SPORT_KEY},
        )
        sport_id = SPORT_ID
    tip = datetime.now(timezone.utc) - timedelta(minutes=30)
    for n, event_id in enumerate(EVENT_IDS):
        home, away = TEAM_IDS[2 * n], TEAM_IDS[2 * n + 1]
        for team_id in (home, away):
            await conn.execute(
                text("INSERT INTO teams (id, sport_id, name) VALUES (:i, :s, :n)"),
                {"i": team_id, "s": sport_id, "n": f"Team {team_id}"},
            )
        await conn.execute(
            text(
                "INSERT INTO events (id, sport_id, external_id, home_team_id, "
                "away_team_id, home_team_name, away_team_name, commence_time, "
                "status) VALUES (:i, :s, :x, :ht, :at, :h, :a, :c, 'live')"
            ),
            {
                "i": event_id, "s": sport_id, "x": f"ei-10090-pg-{event_id}",
                "ht": home, "at": away, "h": f"Team {home}", "a": f"Team {away}",
                "c": tip,
            },
        )
        for minute, p in enumerate(PATH, start=1):
            await conn.execute(
                text(
                    "INSERT INTO odds_snapshots (event_id, captured_at, bookmaker, "
                    "home_win_probability, away_win_probability, reading_count) "
                    "VALUES (:e, :t, 'draftkings', :p, :q, 1)"
                ),
                {"e": event_id, "t": tip + timedelta(minutes=minute), "p": p, "q": 1 - p},
            )


async def _hold(engine, event_id):
    """Another writer's open transaction holding one events row."""
    conn = await engine.connect()
    await conn.begin()
    await conn.execute(text("SELECT id FROM events WHERE id = :i FOR UPDATE"), {"i": event_id})
    return conn


async def _probe(engine, event_id) -> str:
    """The live price stamp's move: lock the row, give up after 500 ms."""
    async with engine.connect() as conn:
        await conn.begin()
        await conn.execute(text(f"SET LOCAL lock_timeout = '{STAMP_LOCK_TIMEOUT}'"))
        try:
            await conn.execute(
                text("UPDATE events SET status = status WHERE id = :i"), {"i": event_id}
            )
        except DBAPIError as e:
            await conn.rollback()
            return f"locked: {getattr(e.orig, 'sqlstate', None) or e}"
        await conn.rollback()
        return "free"


async def _committed_ei(engine) -> dict:
    async with engine.connect() as conn:
        rows = await conn.execute(
            text("SELECT id, raw_ei, ei_metadata, ei_computed_at FROM events WHERE id = ANY(:ids)"),
            {"ids": EVENT_IDS},
        )
        return {r.id: r for r in rows}


async def _the_pass_step(engine):
    """What ``_poll_all_odds`` runs: ``update_live_gei(session)``, then its commit."""
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.tasks.excitement_index import update_live_ei

    async with AsyncSession(engine, expire_on_commit=False) as session:
        updated = await update_live_ei(session)
        await session.commit()
        return updated


async def test_the_probe_can_see_a_held_row(pg_engine):
    holder = await _hold(pg_engine, HELD_GAME)
    try:
        assert (await _probe(pg_engine, HELD_GAME)).startswith("locked: 55P03")
        assert await _probe(pg_engine, FREE_GAME) == "free"
    finally:
        await holder.rollback()
        await holder.close()


async def test_a_held_live_row_neither_blocks_the_ei_write_nor_has_its_neighbour_held(pg_engine):
    holder = await _hold(pg_engine, HELD_GAME)
    step = asyncio.create_task(_the_pass_step(pg_engine))
    try:
        done, _ = await asyncio.wait({step}, timeout=3)
        probe = await _probe(pg_engine, FREE_GAME)
        ei = await _committed_ei(pg_engine)

        # Both halves in one comparison, so a red run shows each of them.
        assert {
            "finished_while_held": step in done,
            "other_game_row": probe,
            "other_game_ei_committed": ei[FREE_GAME].raw_ei is not None,
        } == {
            "finished_while_held": True,
            "other_game_row": "free",
            "other_game_ei_committed": True,
        }
        assert ei[HELD_GAME].raw_ei is None  # skipped, recomputed next pass
        assert step.result() == 1
    finally:
        await holder.rollback()
        await holder.close()
        await asyncio.wait_for(step, timeout=10)


async def test_the_ei_values_are_the_formulas(pg_engine):
    """Nothing held: both games get exactly what ``calculate_ei`` says, as before."""
    from app.utils.excitement_index import EIDataPoint, calculate_ei

    assert await _the_pass_step(pg_engine) == 2
    ei = await _committed_ei(pg_engine)

    for event_id in EVENT_IDS:
        row = ei[event_id]
        async with pg_engine.connect() as conn:
            tip, snaps = (
                await conn.execute(
                    text("SELECT commence_time FROM events WHERE id = :i"), {"i": event_id}
                )
            ).scalar_one(), (
                await conn.execute(
                    text(
                        "SELECT captured_at, home_win_probability, bookmaker, valid_until "
                        "FROM odds_snapshots WHERE event_id = :i ORDER BY captured_at"
                    ),
                    {"i": event_id},
                )
            ).all()
        expected = calculate_ei(
            snapshots=[
                EIDataPoint(
                    captured_at=s.captured_at,
                    home_win_probability=float(s.home_win_probability),
                    source=s.bookmaker,
                    valid_until=s.valid_until,
                )
                for s in snaps
            ],
            game_start=tip,
            current_time=row.ei_computed_at,
            sport_key=SPORT_KEY,
        )
        assert expected is not None
        assert float(row.raw_ei) == pytest.approx(expected.score / 100.0)
        assert row.ei_metadata == expected.metadata.to_json()
