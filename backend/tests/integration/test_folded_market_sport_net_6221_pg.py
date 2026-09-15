"""#6221 follow-up — a CROSS-KEY folded row's markets reach the canonical's page.

WHY THIS NEEDS A DATABASE
=========================

The thing under test is a SQL ``OR`` with three arms. A mocked session hands the
route back whatever list the test built, so every arm is satisfied by
construction and the filter is never evaluated at all — the mock-backed
``test_game_markets.py`` suite can seed a market with any sport it likes and
still see it "survive". Only a server can answer "would this row come back".

Same reasoning, same shape, as the sibling #5918 gate in this directory.

WHAT #6221 CHANGED, AND WHAT IT LEFT CARRYING THE LOAD
======================================================

``_build_game_markets`` has always ANDed a cross-sport safety net onto its
linked-market read. Its first arm is ``market.sport_id == event.sport_id``, and
that was a complete question for exactly as long as a fold could not cross a
sport key.

#6221 ended that. ``soccer_ghost_twins`` now pairs a ``soccer_other`` ghost with
a ``soccer_korea_kleague1`` canonical — Daejeon Citizen v Pohang Steelers, where
the ghost held all 13 markets and the canonical held none — and
``folded_event_ids`` hands the ghost's id to this query. So on every cross-key
fold the first arm is false BY CONSTRUCTION: the ghost's markets carry the
ghost's ``sport_id``, which is precisely the id the net was comparing against
and rejecting.

That left the second arm, ``llm_sport_category == expected_category``, carrying
the fold alone for the first time. It holds on today's population — 2,865 folded
soccer markets, 2,865 ``soccer``, 0 null, 0 other, measured on #6221. **That is a
census, and a census is not a contract.** This file is the contract, so that the
guard does not depend on the census staying true — which is the whole reason the
follow-up was owed.

THE ROW THE CENSUS DOES NOT COVER
=================================

Nothing exotic: ``llm_sport_category IS NULL`` with the ghost's ``sport_id``
set. First arm false (wrong sport id), second false (NULL is not ``soccer``),
third false (the id is not null). The market is dropped, and the reader gets the
fixture page #6221 exists to repair with nothing on it. Nothing warns. The fold
still reports that it worked.

THE CONTROL IS THE SAME QUERY WITH THE WIDENING STRIPPED
========================================================

``test_CONTROL_parent_behaviour_drops_it`` runs the identical production
construct with the fold hidden from the net — which is byte-for-byte what the
parent computed — over the identical rows. So this suite cannot go green for a
reason other than the one it names, and it goes red the day somebody stops
passing the folded ids, which is the defect restored.

``test_CONTROL_a_foreign_sport_is_still_refused`` is the other direction, and it
is why this is a widening and not a removal: the net still refuses a baseball
market sitting on the ghost. Both controls pass on the parent AND on the ship;
only the first test changes colour.
"""

from __future__ import annotations

import datetime as dt
import os

import pytest
from sqlalchemy import select, text

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

needs_postgres = pytest.mark.skipif(
    not DB_URL,
    reason=(
        "set SEARCH_TEST_DATABASE_URL to run the real-Postgres #6221 folded "
        "market sport-net gate (CI's search-recall job provides it)"
    ),
)

#: Production ids, kept so a failure names the rows a reader would have seen.
CANONICAL_ID = 15305024          # Daejeon Citizen v Pohang Steelers, the real row
GHOST_ID = 15307887              # the soccer_other twin that held all 13 markets

KLEAGUE = "soccer_korea_kleague1"
OTHER = "soccer_other"           # the ingest catch-all the ghost lands in
BASEBALL = "baseball_mlb"        # the foreign sport the net must keep refusing

#: Reserved `sports.id`s. Explicit so this gate never draws from the shared
#: database's id sequence — see `_sport_id` for the CI failure that costs.
S_KLEAGUE = 90_006_231
S_OTHER = 90_006_232
S_BASEBALL = 90_006_233

#: The market ids under test, one per arm of the net.
M_CATEGORY = 90_006_221          # llm_sport_category='soccer'  — today's population
M_NULL_CATEGORY = 90_006_222     # llm_sport_category IS NULL   — the row it drops
M_FOREIGN = 90_006_223           # a baseball market on the ghost — must stay out


@pytest.fixture
async def pg_engine():
    """Function-scoped: `pytest.ini` leaves the fixture loop scope unset."""
    from sqlalchemy.ext.asyncio import create_async_engine

    from app.models.models import Event, FuturesMarket, Sport
    from app.services.database import Base

    # Only the tables these rows actually need. `create_all()` over the whole
    # metadata emits DDL for a table carrying `NULLS NOT DISTINCT` (PG 15+), so
    # building everything would make this gate's ability to RUN depend on a
    # clause it does not use — and the failure would read as "the #6221 gate is
    # broken" rather than "the server is old". Same as the #5918/#5621 siblings.
    seen: dict = {}
    pending = [Event.__table__, FuturesMarket.__table__, Sport.__table__]
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


async def _sport_id(conn, key, name, reserved_id):
    """Get or create one sport, WITHOUT drawing from the `sports` id sequence.

    🔴 The explicit id is not tidiness, it is the difference between this gate
    running and not. `search-recall` shares ONE database (`bl_searchtest`)
    across all ~55 of its gates, and the ones that ran first seeded `sports`
    with EXPLICIT ids — which does not advance the sequence. So `nextval`
    still returns 1, and `INSERT ... ON CONFLICT (key) DO NOTHING` draws it
    before it evaluates the conflict: a key that is genuinely new dies on
    `UniqueViolationError: Key (id)=(1) already exists` against `sports_pkey`,
    never against the key this statement guards.

    The sibling gates get away with the sequence form because each inserts a
    single sport the shared database already holds, so `DO NOTHING` fires and
    nothing is drawn. This gate needs THREE — including `soccer_other` and a
    foreign `baseball_mlb` — so a genuinely new key is the normal case here,
    not the edge. Measured both ways: green against a fresh local database,
    red in CI on exactly this, and the CI failure reproduced locally by
    seeding an explicit-id row and rewinding the sequence.

    `ON CONFLICT DO NOTHING` is deliberately untargeted so it absorbs an id
    collision as well as a key one; the SELECT below is then the real check,
    and it asserts rather than returning None into arithmetic.
    """
    await conn.execute(
        text(
            "INSERT INTO sports (id, key, name, active) "
            "VALUES (:i, :k, :n, true) ON CONFLICT DO NOTHING"
        ),
        {"i": reserved_id, "k": key, "n": name},
    )
    sport_id = (
        await conn.execute(text("SELECT id FROM sports WHERE key = :k"), {"k": key})
    ).scalar()
    assert sport_id is not None, (
        f"sport {key!r} is neither present nor insertable — reserved id "
        f"{reserved_id} is likely taken by a different key, so pick another"
    )
    return sport_id


async def _seed(conn):
    """The Daejeon/Pohang pair as #6221 folded it, plus the three markets."""
    from app.services.anchor_channel import duplicate_tag

    await conn.execute(
        text("DELETE FROM futures_markets WHERE id = ANY(:ids)"),
        {"ids": [M_CATEGORY, M_NULL_CATEGORY, M_FOREIGN]},
    )
    await conn.execute(
        text("DELETE FROM events WHERE id = ANY(:ids)"),
        {"ids": [CANONICAL_ID, GHOST_ID]},
    )

    kleague = await _sport_id(conn, KLEAGUE, "K League 1", S_KLEAGUE)
    other = await _sport_id(conn, OTHER, "Other", S_OTHER)
    baseball = await _sport_id(conn, BASEBALL, "MLB", S_BASEBALL)
    assert kleague != other, "the two sport ids must differ or the gate is vacuous"

    kickoff = dt.datetime(2026, 9, 12, 10, 30, tzinfo=dt.timezone.utc)
    await conn.execute(
        text(
            "INSERT INTO events (id, sport_id, home_team_name, away_team_name, "
            "commence_time, status) VALUES "
            "(:i, :s, 'Daejeon Citizen', 'Pohang Steelers', :c, 'completed')"
        ),
        {"i": CANONICAL_ID, "s": kleague, "c": kickoff},
    )
    # The ghost: a DIFFERENT sport key, tagged as a proven duplicate of the
    # canonical. This is the row `folded_event_ids` will hand the query.
    await conn.execute(
        text(
            "INSERT INTO events (id, sport_id, home_team_name, away_team_name, "
            "commence_time, status, event_tags) VALUES "
            "(:i, :s, 'Daejeon', 'Pohang', :c, 'suspended', CAST(:t AS jsonb))"
        ),
        {
            "i": GHOST_ID,
            "s": other,
            "c": kickoff,
            "t": f'["{duplicate_tag(CANONICAL_ID)}"]',
        },
    )

    for mid, category, sport_id, name, ticker in (
        (M_CATEGORY, "soccer", other, "Daejeon v Pohang: Total Goals",
         "KXKLEAGUETOTAL-26SEP12DJNPOH"),
        (M_NULL_CATEGORY, None, other, "Daejeon v Pohang: Both Teams To Score",
         "KXKLEAGUEBTTS-26SEP12DJNPOH"),
        (M_FOREIGN, "baseball", baseball, "Yankees v Red Sox: Total Runs",
         "KXMLBTOTAL-26SEP12NYYBOS"),
    ):
        await conn.execute(
            text(
                "INSERT INTO futures_markets (id, event_id, sport_id, "
                "llm_sport_category, name, external_id, category, source, "
                "status, mutually_exclusive) "
                "VALUES (:i, :e, :s, :c, :n, :x, 'game_prop', 'kalshi', "
                "'resolved', false)"
            ),
            {
                "i": mid, "e": GHOST_ID, "s": sport_id, "c": category,
                "n": name, "x": ticker,
            },
        )
    return kleague


async def _surviving_market_ids(conn, event_sport_id):
    """Run the PRODUCTION decision — not a copy of it — and report what returns.

    `folded_market_read_filters` is the whole of what `_build_game_markets`
    computes: which rows to read from AND which of their markets the sport net
    admits. Calling it rather than reassembling its parts is what makes "somebody
    stops looking up the folded rows' sports" a killable mutant — a gate that
    only exercised the pure net would stay green through exactly that edit.
    """
    from app.models.models import FuturesMarket
    from app.routes.events import folded_market_read_filters

    market_event_ids, filters = await folded_market_read_filters(
        conn, CANONICAL_ID, event_sport_id, "soccer",
    )
    assert GHOST_ID in market_event_ids, (
        "the fold itself is not firing — this gate would be vacuous"
    )
    assert len(filters) == 2, "the sport net was not built; the gate tests nothing"

    rows = await conn.execute(select(FuturesMarket.id).where(*filters))
    return set(rows.scalars().all())


async def _surviving_market_ids_parent(conn, event_sport_id):
    """The same query with the widening stripped — byte-for-byte the parent.

    The net is handed only the canonical's own sport id, which is what
    `_build_game_markets` compared against before #6221.
    """
    from app.models.models import FuturesMarket
    from app.routes.events import linked_market_sport_filter
    from app.utils.proven_duplicates import folded_event_ids

    market_event_ids = await folded_event_ids(conn, CANONICAL_ID)
    net = linked_market_sport_filter(event_sport_id, "soccer", [CANONICAL_ID])
    rows = await conn.execute(
        select(FuturesMarket.id).where(
            FuturesMarket.event_id.in_(market_event_ids), net,
        )
    )
    return set(rows.scalars().all())


@needs_postgres
@pytest.mark.asyncio
async def test_a_null_category_market_on_a_cross_key_ghost_reaches_the_page(pg_engine):
    """The row the #6221 census does not cover still reaches the reader.

    RED ON THE PARENT: with only the canonical's sport id to compare against,
    all three arms of the net are false for this market and the page loses it.
    """
    async with pg_engine.begin() as conn:
        kleague = await _seed(conn)
        survivors = await _surviving_market_ids(conn, kleague)

        assert M_NULL_CATEGORY in survivors, (
            "a market on a PROVEN duplicate was dropped for carrying the ghost's "
            "sport_id and no llm_sport_category — the fold reports success and "
            "the fixture page renders empty"
        )


@needs_postgres
@pytest.mark.asyncio
async def test_the_category_bearing_market_survives_both_ways(pg_engine):
    """CONTROL — today's whole population. Green on the parent AND on the ship."""
    async with pg_engine.begin() as conn:
        kleague = await _seed(conn)

        assert M_CATEGORY in await _surviving_market_ids(conn, kleague)
        assert M_CATEGORY in await _surviving_market_ids_parent(conn, kleague)


@needs_postgres
@pytest.mark.asyncio
async def test_CONTROL_a_foreign_sport_is_still_refused(pg_engine):
    """CONTROL — this is a widening, not a removal.

    A baseball market sitting on the ghost is in neither the canonical's sport
    nor any folded row's, so it stays out. Green on the parent AND on the ship;
    it is what separates this from "drop the sport key entirely", the broad
    relaxation #6221 already rejected once.
    """
    async with pg_engine.begin() as conn:
        kleague = await _seed(conn)

        assert M_FOREIGN not in await _surviving_market_ids(conn, kleague)
        assert M_FOREIGN not in await _surviving_market_ids_parent(conn, kleague)


@needs_postgres
@pytest.mark.asyncio
async def test_CONTROL_parent_behaviour_drops_it(pg_engine):
    """CONTROL — the same query with the widening stripped, over the same rows.

    `folded_sport_ids=[]` is byte-for-byte what the parent computed. Pinning the
    parent's behaviour here is what proves the test above changes colour for the
    named reason and not for an unrelated one, and it goes red the day somebody
    stops passing the folded ids.
    """
    async with pg_engine.begin() as conn:
        kleague = await _seed(conn)

        assert M_NULL_CATEGORY not in await _surviving_market_ids_parent(
            conn, kleague,
        )

