"""#5918 — the league rail's own query, run by a real server, folds the twin.

WHY THIS NEEDS A DATABASE
=========================

CERT-2805 blocked the #5918 soccer name-pair fold for a reason no in-memory
test could have caught: the fold works, and it never fired on the page.

`upcoming_games_query` has joined `sports` since it was written, so every
earlier reading of this rail looked correct. But a join in the FROM clause
makes the table available to the WHERE — it does not populate `Event.sport` on
the hydrated row. `loaded_sport_key` answers ``None`` for an unloaded
relationship (deliberately: a lazy load here would emit IO inside a stage
wrapped in a bare ``except``, gotcha #42, and silently disable the whole fold),
so the soccer pass skipped every row the league page served.

Only a server can tell those two states apart. A mock session hands back
whatever object the test built, and an object built by a test has its sport in
memory — which is the passing case, every time. That is exactly how a fold
measured at nine folds over 765 production rows reached no reader at all.

THE SPECIMEN
============

Celta–Málaga as production held it at 2026-09-13 15:39Z: two rows for one
fixture, named by two provider vocabularies (`RC Celta de Vigo` / `Celta Vigo`),
same sport, same minute. The strict `twin_fold_key` cannot see them as one
fixture because it squashes names; the soccer pass can, and must.

`15310518` — the row that gets absorbed — is the one carrying the price.
Electing the other row and discarding its sources would serve a card with no
number, which is why the fold unions rather than filters, and why this test
asserts the PRICE survives and not merely that one card does.

THE CONTROL IS THE SAME QUERY WITH THE OPTION STRIPPED
======================================================

Both arms execute the real `upcoming_games_query` against the real server over
the same two rows. The only difference is the loader option, so the test cannot
pass for a reason other than the one it names, and it goes red the day somebody
deletes the option — which is the whole defect, restored.
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
        "set SEARCH_TEST_DATABASE_URL to run the real-Postgres #5918 league "
        "rail reach gate (CI's search-recall job provides it)"
    ),
)

SOCCER = "soccer_spain_la_liga"

#: Production ids, kept so a failure names the rows a reader would have seen.
SURVIVOR_ID = 15310519
ABSORBED_ID = 15310518

#: The absorbed row's only price. The whole point of unioning rather than
#: filtering is that this reaches the served card.
ABSORBED_SOURCES = {
    "betting": {"home": 0.62, "away": 0.38},
    "betting_book_count": 7,
}


@pytest.fixture
async def pg_engine():
    """Function-scoped: `pytest.ini` leaves the fixture loop scope unset."""
    from sqlalchemy.ext.asyncio import create_async_engine

    # Importing these two names executes `app.models.models`, which is what
    # registers every table on `Base` — the sibling gate's extra bare
    # `import app.models.models` alongside this is redundant, and CodeQL files
    # it as a note (`Module is imported with 'import' and 'import from'`).
    from app.models.models import Event, Sport
    from app.services.database import Base

    # Only the tables `events` actually needs. `create_all()` over the whole
    # metadata emits DDL for a table carrying `NULLS NOT DISTINCT` (PG 15+), so
    # building everything would make this gate's ability to RUN depend on a
    # clause it does not use — and the failure would read as "the #5918 gate is
    # broken" rather than "the server is old". Same reasoning, same shape, as
    # the sibling #5621 gate in this directory.
    seen: dict = {}
    pending = [Event.__table__, Sport.__table__]
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


async def _seed(conn, kickoff):
    """The two Celta rows, one fixture, two vocabularies, same minute."""
    await conn.execute(
        text("DELETE FROM events WHERE id = ANY(:ids)"),
        {"ids": [SURVIVOR_ID, ABSORBED_ID]},
    )
    await conn.execute(
        text(
            "INSERT INTO sports (key, name, active) VALUES (:k, :n, true) "
            "ON CONFLICT (key) DO NOTHING"
        ),
        {"k": SOCCER, "n": "La Liga"},
    )
    sport_id = (
        await conn.execute(text("SELECT id FROM sports WHERE key = :k"), {"k": SOCCER})
    ).scalar()

    # The survivor carries an espn_id, so `twin_identity_rank` elects it — and
    # it carries NO sources, which is why the union is the half that matters.
    await conn.execute(
        text(
            "INSERT INTO events (id, sport_id, home_team_name, away_team_name, "
            "commence_time, status, espn_id) VALUES "
            "(:i, :s, 'RC Celta de Vigo', 'Malaga CF', :c, 'scheduled', '999001')"
        ),
        {"i": SURVIVOR_ID, "s": sport_id, "c": kickoff},
    )
    await conn.execute(
        text(
            "INSERT INTO events (id, sport_id, home_team_name, away_team_name, "
            "commence_time, status, win_probability_sources) VALUES "
            "(:i, :s, 'Celta Vigo', 'Malaga', :c, 'scheduled', "
            "CAST(:w AS jsonb))"
        ),
        {
            "i": ABSORBED_ID,
            "s": sport_id,
            "c": kickoff,
            "w": __import__("json").dumps(ABSORBED_SOURCES),
        },
    )
    return sport_id


async def _rail(engine, kickoff, *, strip_options: bool):
    """Run the REAL rail query and the REAL fold over what it returns."""
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from app.routes.league_futures import _folded_upcoming, upcoming_games_query

    statement = upcoming_games_query(SOCCER, kickoff - dt.timedelta(hours=1))
    if strip_options:
        # The control: the same statement as it was before the repair — the
        # join still there, the loader gone.
        statement = statement.options()
        statement._with_options = ()

    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        rows = list((await session.execute(statement)).scalars().all())
        return rows, _folded_upcoming(rows)


@needs_postgres
async def test_league_route_name_pair_fold_has_loaded_sport_5918(pg_engine):
    """THE SHIP, on the page. One card, and it keeps the absorbed row's price.

    The required repair's test (CERT-2805): the real league query/build path,
    one card, and the absorbed row's only price preserved on the survivor.
    """
    kickoff = dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=6)
    async with pg_engine.begin() as conn:
        await _seed(conn, kickoff)

    rows, folded = await _rail(pg_engine, kickoff, strip_options=False)

    # Non-vacuity: the rail really did serve both rows before the fold ran.
    assert {r.id for r in rows} == {SURVIVOR_ID, ABSORBED_ID}
    assert len(folded) == 1, "two rows for one fixture must serve ONE card"
    card = folded[0]
    assert card.id == SURVIVOR_ID
    assert (card.win_probability_sources or {}).get("betting") == ABSORBED_SOURCES[
        "betting"
    ], "the surviving card must keep the absorbed row's only price"


@needs_postgres
async def test_without_the_loader_the_same_query_serves_the_duplicate(pg_engine):
    """THE CONTROL — this is what a reader saw, and what CERT-2805 reproduced.

    Same server, same rows, same fold, same query. Only the loader option is
    gone, and the page is two cards again. Without this arm the test above
    could pass for any reason at all.
    """
    kickoff = dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=6)
    async with pg_engine.begin() as conn:
        await _seed(conn, kickoff)

    rows, folded = await _rail(pg_engine, kickoff, strip_options=True)

    assert {r.id for r in rows} == {SURVIVOR_ID, ABSORBED_ID}
    assert len(folded) == 2, (
        "with Event.sport unloaded the soccer pass must be inert — if this "
        "folds, the fold is reading the sport some other way and the repair "
        "above is not what makes the page correct"
    )


@needs_postgres
async def test_the_loaded_relationship_is_what_the_fold_reads(pg_engine):
    """Names the mechanism, so a failure above is diagnosable in one read.

    `loaded_sport_key` is the function the fold consults; it must answer the
    league's key for a row this query returned, and None for the same row read
    without the option.
    """
    from app.utils.kalshi_occurrence_start import loaded_sport_key

    kickoff = dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=6)
    async with pg_engine.begin() as conn:
        await _seed(conn, kickoff)

    loaded, _ = await _rail(pg_engine, kickoff, strip_options=False)
    bare, _ = await _rail(pg_engine, kickoff, strip_options=True)

    assert {loaded_sport_key(r) for r in loaded} == {SOCCER}
    assert {loaded_sport_key(r) for r in bare} == {None}
