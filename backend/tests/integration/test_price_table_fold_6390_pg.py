"""#6390 — the price-table fold, against a real server.

WHY THIS NEEDS A DATABASE
=========================

The unit suite (`tests/test_price_table_fold_6390.py`) drives the real route
through a rig that HONOURS the id filter, so it is not the usual
"every arm satisfied by construction" mock. But one fact it cannot establish is
the one the whole ship turns on: that
`latest_odds_per_bookmaker_query([canonical, ghost])` really does return a
bookmaker present on BOTH rows **twice**. The rig emulates that grouping —
which means the rig is only as good as the belief it encodes. If the recursive
CTE happened to collapse across events by itself, the picker would be dead code
and the emulation would be inventing the problem it solves.

So this gate asserts the server's behaviour first and the repair second. Same
reasoning, same shape, as the sibling #6221 gate in this directory.

WHAT IT PINS
============

1. `test_the_server_really_does_return_the_book_twice` — the premise. Without
   it the picker is unjustified, and a reader would see Pinnacle printed twice
   and counted twice in `bookmaker_count`.
2. `test_the_production_read_path_serves_one_row_per_book` — the repair, run
   through the real functions the route composes rather than a copy of them.
3. `test_CONTROL_the_unfolded_read_is_the_defect` — the parent behaviour over
   the identical rows: the canonical alone, which is the empty Brest page.
4. `test_a_crossed_ghost_is_refused_by_the_real_fold` — the orientation gate on
   a real server. A crossed pair's prices are inverted, not merely extra.
"""

from __future__ import annotations

import datetime as dt
import os

import pytest
from sqlalchemy import text

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

needs_postgres = pytest.mark.skipif(
    not DB_URL,
    reason=(
        "set SEARCH_TEST_DATABASE_URL to run the real-Postgres #6390 price-table "
        "fold gate (CI's search-recall job provides it)"
    ),
)

#: Production ids, kept so a failure names the rows a reader would have seen.
#: Brest v Paris Saint-Germain, the page that rendered a score and nothing else.
PROD_CANONICAL = 15311919
PROD_GHOST = 15297786

#: Reserved ids. Explicit so this gate never draws from the shared database's
#: sequences — see the #6221 sibling's `_sport_id` for the CI failure that costs.
S_SOCCER = 90_006_391
CANONICAL_ID = 90_006_395
GHOST_ID = 90_006_396
CROSSED_GHOST_ID = 90_006_397

SNAP_CANON_PINNACLE = 90_006_381
SNAP_GHOST_PINNACLE = 90_006_382
SNAP_GHOST_FANDUEL = 90_006_383
SNAP_CROSSED_FANDUEL = 90_006_384

KICKOFF = dt.datetime(2026, 9, 13, 19, 0, tzinfo=dt.timezone.utc)


@pytest.fixture
async def pg_engine():
    """Function-scoped: `pytest.ini` leaves the fixture loop scope unset."""
    from sqlalchemy.ext.asyncio import create_async_engine

    from app.models.models import Event, OddsSnapshot, Sport
    from app.services.database import Base

    # Only the tables these rows need. `create_all()` over the whole metadata
    # emits DDL for a table carrying `NULLS NOT DISTINCT` (PG 15+), so building
    # everything would make this gate's ability to RUN depend on a clause it does
    # not use. Same as the #6221/#5918/#5621 siblings.
    seen: dict = {}
    pending = [Event.__table__, OddsSnapshot.__table__, Sport.__table__]
    while pending:
        table = pending.pop()
        if table.key in seen:
            continue
        seen[table.key] = table
        pending.extend(fk.column.table for fk in table.foreign_keys)

    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(
            lambda sync: Base.metadata.create_all(
                sync, tables=list(seen.values()), checkfirst=True
            )
        )
    yield engine
    await engine.dispose()


async def _sport_id(conn):
    """Get or create the one sport, WITHOUT drawing from the `sports` sequence.

    `search-recall` shares ONE database across all its gates, and the ones that
    ran first seeded `sports` with EXPLICIT ids — which does not advance the
    sequence, so `nextval` still returns a taken id and an untargeted
    `ON CONFLICT DO NOTHING` is the only form that survives both an id and a key
    collision. The SELECT below is the real check.
    """
    await conn.execute(
        text(
            "INSERT INTO sports (id, key, name, active) "
            "VALUES (:i, 'soccer_france_ligue_one', 'Ligue 1', true) "
            "ON CONFLICT DO NOTHING"
        ),
        {"i": S_SOCCER},
    )
    sport_id = (
        await conn.execute(
            text("SELECT id FROM sports WHERE key = 'soccer_france_ligue_one'")
        )
    ).scalar()
    assert sport_id is not None, (
        f"reserved sport id {S_SOCCER} is likely taken by a different key — pick "
        f"another"
    )
    return sport_id


async def _seed(conn):
    """Brest-PSG as production holds it: the prices on the row nobody prints.

    `pinnacle` sits on BOTH rows (the ghost's reading fresher, which is the
    realistic case — the ghost is the row the poller kept writing to), `fanduel`
    only on the ghost. That is the smallest population that exercises both
    halves: the union AND the de-duplication.
    """
    from app.services.anchor_channel import duplicate_tag

    await conn.execute(
        text("DELETE FROM odds_snapshots WHERE id = ANY(:ids)"),
        {
            "ids": [
                SNAP_CANON_PINNACLE,
                SNAP_GHOST_PINNACLE,
                SNAP_GHOST_FANDUEL,
                SNAP_CROSSED_FANDUEL,
            ]
        },
    )
    await conn.execute(
        text("DELETE FROM events WHERE id = ANY(:ids)"),
        {"ids": [CANONICAL_ID, GHOST_ID, CROSSED_GHOST_ID]},
    )

    sport_id = await _sport_id(conn)

    await conn.execute(
        text(
            "INSERT INTO events (id, sport_id, home_team_name, away_team_name, "
            "commence_time, status) VALUES "
            "(:i, :s, 'Brest', 'Paris Saint-Germain', :c, 'completed')"
        ),
        {"i": CANONICAL_ID, "s": sport_id, "c": KICKOFF},
    )
    # The ghost, oriented in AGREEMENT — the hyphen-less spelling is what
    # production actually holds on 15297786, and punctuation is dropped before
    # the subset test.
    await conn.execute(
        text(
            "INSERT INTO events (id, sport_id, home_team_name, away_team_name, "
            "commence_time, status, event_tags) VALUES "
            "(:i, :s, 'Brest', 'Paris Saint Germain', :c, 'completed', "
            "CAST(:t AS jsonb))"
        ),
        {
            "i": GHOST_ID,
            "s": sport_id,
            "c": KICKOFF,
            "t": f'["{duplicate_tag(CANONICAL_ID)}"]',
        },
    )

    for snap_id, event_id, bookmaker, minutes in (
        (SNAP_CANON_PINNACLE, CANONICAL_ID, "pinnacle", 0),
        (SNAP_GHOST_PINNACLE, GHOST_ID, "pinnacle", 30),
        (SNAP_GHOST_FANDUEL, GHOST_ID, "fanduel", 10),
    ):
        await conn.execute(
            text(
                "INSERT INTO odds_snapshots (id, event_id, bookmaker, captured_at, "
                "home_win_probability, away_win_probability, reading_count) "
                "VALUES (:i, :e, :b, :c, 0.6, 0.4, 1)"
            ),
            {
                "i": snap_id,
                "e": event_id,
                "b": bookmaker,
                "c": KICKOFF - dt.timedelta(hours=2) + dt.timedelta(minutes=minutes),
            },
        )
    return sport_id


async def _seed_crossed_ghost(conn, sport_id):
    """A second ghost whose home/away slots are SWAPPED, carrying a price."""
    from app.services.anchor_channel import duplicate_tag

    await conn.execute(
        text(
            "INSERT INTO events (id, sport_id, home_team_name, away_team_name, "
            "commence_time, status, event_tags) VALUES "
            "(:i, :s, 'Paris Saint Germain', 'Brest', :c, 'completed', "
            "CAST(:t AS jsonb))"
        ),
        {
            "i": CROSSED_GHOST_ID,
            "s": sport_id,
            "c": KICKOFF,
            "t": f'["{duplicate_tag(CANONICAL_ID)}"]',
        },
    )
    await conn.execute(
        text(
            "INSERT INTO odds_snapshots (id, event_id, bookmaker, captured_at, "
            "home_win_probability, away_win_probability, reading_count) "
            "VALUES (:i, :e, 'betmgm', :c, 0.9, 0.1, 1)"
        ),
        {
            "i": SNAP_CROSSED_FANDUEL,
            "e": CROSSED_GHOST_ID,
            "c": KICKOFF - dt.timedelta(hours=1),
        },
    )


async def _server_rows(conn, event_ids):
    """The production statement, not a copy of it."""
    from app.routes.events import latest_odds_per_bookmaker_query

    return list(
        (await conn.execute(latest_odds_per_bookmaker_query(event_ids))).all()
    )


@needs_postgres
class TestThePriceTableFold:
    async def test_the_server_really_does_return_the_book_twice(self, pg_engine):
        """The premise the picker exists for. If this ever goes green the other
        way, the picker is dead code and the unit rig is inventing a problem."""
        async with pg_engine.begin() as conn:
            await _seed(conn)
            rows = await _server_rows(conn, [CANONICAL_ID, GHOST_ID])
            books = [r.bookmaker for r in rows]
            assert books.count("pinnacle") == 2, (
                f"the CTE groups per (event, bookmaker), so a folded pair must "
                f"return the shared book twice — got {books}"
            )

    async def test_the_production_read_path_serves_one_row_per_book(self, pg_engine):
        """The repair, composed exactly as `get_event` composes it."""
        from sqlalchemy.ext.asyncio import AsyncSession

        from app.routes.events import latest_odds_per_bookmaker_query
        from app.utils.proven_duplicates import (
            folded_series_event_ids,
            latest_snapshot_for_each_bookmaker,
        )

        async with pg_engine.begin() as conn:
            await _seed(conn)

        # A SESSION, not the raw connection the other tests use: `.scalars()`
        # over `select(entity)` only yields ORM objects under a session, and the
        # route hands the picker ORM objects. On a connection it returns the
        # first COLUMN — ints — and the picker would be exercised against the
        # wrong type rather than against production's.
        async with AsyncSession(pg_engine) as session:
            ids = await folded_series_event_ids(session, CANONICAL_ID)
            assert set(ids) == {CANONICAL_ID, GHOST_ID}

            rows = list(
                (
                    await session.execute(latest_odds_per_bookmaker_query(ids))
                ).scalars().all()
            )
            picked = latest_snapshot_for_each_bookmaker(rows, CANONICAL_ID)

            assert [s.bookmaker for s in picked] == ["fanduel", "pinnacle"]
            # The ghost's reading is the fresher one, so it is the one kept.
            assert [s.id for s in picked if s.bookmaker == "pinnacle"] == [
                SNAP_GHOST_PINNACLE
            ]

    async def test_CONTROL_the_unfolded_read_is_the_defect(self, pg_engine):
        """Byte-for-byte what the parent computed, over the identical rows.

        This is the empty Brest page: the canonical's own snapshots and nothing
        else. It is what makes the test above a ship rather than a restatement.
        """
        async with pg_engine.begin() as conn:
            await _seed(conn)
            rows = await _server_rows(conn, [CANONICAL_ID])
            assert [r.bookmaker for r in rows] == ["pinnacle"]
            assert "fanduel" not in [r.bookmaker for r in rows]

    async def test_a_crossed_ghost_is_refused_by_the_real_fold(self, pg_engine):
        """Orientation, on a real server rather than against the pure predicate.

        A crossed ghost's `home_win_probability` describes the OTHER side, so
        admitting it would print an exactly inverted price — worse than the
        omission this ship repairs.
        """
        from app.utils.proven_duplicates import folded_series_event_ids

        async with pg_engine.begin() as conn:
            sport_id = await _seed(conn)
            await _seed_crossed_ghost(conn, sport_id)

            ids = await folded_series_event_ids(conn, CANONICAL_ID)
            assert CROSSED_GHOST_ID not in ids, (
                "the swapped ghost reached the price read — its prices are "
                "inverted relative to the canonical"
            )
            # And the aligned one is still folded, so the refusal is selective
            # rather than the fold having collapsed to the canonical.
            assert set(ids) == {CANONICAL_ID, GHOST_ID}
