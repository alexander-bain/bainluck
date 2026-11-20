"""Real PostgreSQL: refused venue identities never persist or escape resolution.

Synthetic rows in an isolated schema; no production connection or data repair.
"""

import os
import uuid

import pytest
from sqlalchemy import event, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.models import Sport, Team, TeamIdentityMapping
from app.services.database import Base
from app.services.team_identity import TeamIdentityService, _NAME_WITNESS_LIMIT

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")
pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not DB_URL, reason="set SEARCH_TEST_DATABASE_URL for real PostgreSQL"
    ),
]


@pytest.fixture
async def rig():
    schema = "test_identity_12534_" + uuid.uuid4().hex
    engine = create_async_engine(
        DB_URL,
        execution_options={"schema_translate_map": {None: schema}},
    )
    statements = []
    try:
        async with engine.begin() as conn:
            await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
            await conn.run_sync(
                Base.metadata.create_all,
                tables=[Sport.__table__, Team.__table__, TeamIdentityMapping.__table__],
            )
            for column in ("source_id", "source_name"):
                await conn.execute(
                    text(
                        f'CREATE UNIQUE INDEX unique_{column} ON "{schema}".team_identity_mapping '
                        f"(source, {column}, sport_key) WHERE {column} IS NOT NULL"
                    )
                )
        event.listen(
            engine.sync_engine,
            "before_cursor_execute",
            lambda _c, _u, sql, *_: statements.append(sql),
        )
        yield async_sessionmaker(engine, expire_on_commit=False), statements
    finally:
        async with engine.begin() as conn:
            await conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        await engine.dispose()


async def seed(maker, sport="soccer_france_ligue_one"):
    async with maker() as session:
        session.add(Sport(id=1, key=sport, name="Test league"))
        await session.flush()
        session.add_all(
            [
                Team(
                    id=1,
                    sport_id=1,
                    name="Stade Brest",
                    alternate_names=["Brest"],
                    espn_id="6997",
                ),
                Team(
                    id=2,
                    sport_id=1,
                    name="Paris Saint-Germain",
                    alternate_names=["PSG"],
                    espn_id="160",
                ),
            ]
        )
        await session.commit()


async def mappings(maker):
    async with maker() as session:
        rows = (await session.execute(select(TeamIdentityMapping))).scalars().all()
        return [(r.source, r.source_name, r.team_id) for r in rows]


async def test_foreign_cached_fuzzy_hit_cannot_create_a_new_exact_hit(rig):
    maker, _ = rig
    await seed(maker)
    async with maker() as session:
        session.add(
            TeamIdentityMapping(
                team_id=1,
                source="polymarket",
                source_name="PSG",
                sport_key="soccer_france_ligue_one",
            )
        )
        await session.commit()
    async with maker() as session:
        result = await TeamIdentityService().resolve_team(
            session,
            "kalshi",
            "soccer_france_ligue_one",
            source_name="PSG",
        )
        assert result is None
        await session.commit()
    # The old row is the separate attended repair, not automatically deleted.
    assert await mappings(maker) == [("polymarket", "PSG", 1)]


async def test_refused_upsert_cannot_overwrite_an_existing_correct_identity(rig):
    maker, _ = rig
    await seed(maker)
    service = TeamIdentityService()
    async with maker() as session:
        assert (
            await service.register_team_identity(
                session,
                2,
                "kalshi",
                "soccer_france_ligue_one",
                source_name="PSG",
            )
            is True
        )
        await session.commit()
    async with maker() as session:
        assert (
            await service.register_team_identity(
                session,
                1,
                "kalshi",
                "soccer_france_ligue_one",
                source_name="PSG",
            )
            is False
        )
        await session.commit()
    assert await mappings(maker) == [("kalshi", "PSG", 2)]


async def test_witness_read_uses_the_requested_league_not_the_sport_family(rig):
    maker, statements = rig
    await seed(maker, sport="soccer_other_league")
    async with maker() as session:
        session.add(Sport(id=2, key="soccer_france_ligue_one", name="Requested league"))
        await session.flush()
        target = await session.get(Team, 1)
        target.sport_id = 2
        await session.commit()
    async with maker() as session:
        assert (
            await TeamIdentityService().register_team_identity(
                session,
                1,
                "kalshi",
                "soccer_france_ligue_one",
                source_name="PSG",
            )
            is True
        )  # The other league is not enough evidence to refuse an alias.
        await session.commit()
    assert await mappings(maker) == [("kalshi", "PSG", 1)]
    witness_reads = [s for s in statements if "JOIN" in s and ".sports" in s]
    assert len(witness_reads) == 1
    assert " LIKE " not in witness_reads[0]
    assert " LIMIT " in witness_reads[0]


async def test_known_alias_registration_has_no_added_pool_read(rig):
    maker, statements = rig
    await seed(maker)
    async with maker() as session:
        target = await session.get(Team, 2)
        statements.clear()
        for _ in range(3):
            assert (
                await TeamIdentityService().register_team_identity(
                    session,
                    target.id,
                    "kalshi",
                    "soccer_france_ligue_one",
                    source_name="PSG",
                )
                is True
            )
        await session.commit()
    assert len(statements) == 3
    assert all(s.startswith("INSERT INTO") for s in statements)
    assert await mappings(maker) == [("kalshi", "PSG", 2)]


async def test_witness_pool_cap_cannot_turn_a_truncated_read_into_admission(rig):
    maker, statements = rig
    await seed(maker)
    async with maker() as session:
        session.add_all(
            [
                Team(id=i + 3, sport_id=1, name=f"Synthetic club {i}")
                for i in range(_NAME_WITNESS_LIMIT)
            ]
        )
        await session.commit()
    async with maker() as session:
        statements.clear()
        assert (
            await TeamIdentityService().register_team_identity(
                session,
                1,
                "kalshi",
                "soccer_france_ligue_one",
                source_name="Unrecognized alias",
            )
            is False
        )
        await session.commit()
    assert not any(s.startswith("INSERT") for s in statements)
    assert await mappings(maker) == []
