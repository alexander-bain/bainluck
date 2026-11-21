"""Exercise onboarding team selection and save against isolated PostgreSQL."""

import os
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.models import (
    Event,
    RetiredTeamRedirect,
    Sport,
    Team,
    TeamIdentityMapping,
    User,
    UserFavorite,
    UserPreference,
    Venue,
)
from app.routes.user import OnboardingRequest, TeamRef, search_teams, submit_onboarding
from app.services.database import Base

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")
pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(not DB_URL, reason="set SEARCH_TEST_DATABASE_URL for PostgreSQL"),
]

LA_LIGA = "soccer_spain_la_liga"
EPL = "soccer_epl"
UCL = "soccer_uefa_champs_league"
MLS = "soccer_usa_mls"
NBA = "basketball_nba"
MLB = "baseball_mlb"
NCAAB = "basketball_ncaab"
NCAAF = "americanfootball_ncaaf"
OTHER = "soccer_other"

ISSUE_SEARCHES = {
    "Real Madrid": ("Real Madrid", LA_LIGA),
    "Manchester": ("Manchester City", EPL),
    "New York": ("New York City FC", MLS),
    "Los Angeles": ("Los Angeles Clippers", NBA),
    "Tottenham": ("Tottenham Hotspur", EPL),
    "Arsenal": ("Arsenal", EPL),
}
ADDITIONAL_SEARCHES = {
    "Manchester City": ("Manchester City", EPL),
    "New York Knicks": ("New York Knicks", NBA),
    "Los Angeles Lakers": ("Los Angeles Lakers", NBA),
    "Tottenham Hotspur": ("Tottenham Hotspur", EPL),
    "Harvard Crimson": ("Harvard Crimson", NCAAB),
    "Spurs": ("San Antonio Spurs", NBA),
}


async def seed_clubs(session):
    clubs = [
        (1001, "Real Madrid", LA_LIGA, "86", ["Madrid"]),
        (1002, "Real Sociedad", LA_LIGA, None, []),
        (1003, "Real Salt Lake", MLS, None, []),
        (1004, "Montreal Canadiens", "icehockey_nhl", None, []),
        (1005, "Oviedo", LA_LIGA, None, []),
        (1010, "Manchester City", EPL, None, []),
        (1011, "Manchester United", EPL, None, []),
        (1012, "Manchester 62", OTHER, None, []),
        (1020, "New York Knicks", NBA, None, []),
        (1021, "New York Yankees", MLB, None, []),
        (1022, "New York Mets", MLB, None, []),
        (1023, "New York City FC", MLS, None, []),
        (1024, "Newcastle United", EPL, None, []),
        (1030, "Los Angeles Lakers", NBA, None, []),
        (1031, "Los Angeles Clippers", NBA, None, []),
        (1032, "Los Angeles Dodgers", MLB, None, []),
        (1033, "Los Angeles FC", MLS, None, ["LAFC"]),
        (1034, "Carlos Rivera", "boxing", None, []),
        (1040, "Tottenham Hotspur", EPL, "367", ["Spurs"]),
        (1041, "Tottenham Hotspur", UCL, "367", ["Spurs"]),
        (1042, "Tottenham Hotspur FC - Exact Score", EPL, None, []),
        (1043, "Arsenal", EPL, "359", ["Arsenal FC"]),
        (1044, "Arsenal FC - More Markets", EPL, None, []),
        (1045, "Arsenal FC - Player Props", EPL, None, []),
        (1046, "Arsenal FC - Total Corners", EPL, None, []),
        (1047, "Arsenal Tula", OTHER, None, []),
        (1050, "Harvard Crimson", NCAAB, "108", []),
        (1051, "Harvard Crimson", NCAAF, "108", []),
        (1052, "San Antonio Spurs", NBA, None, []),
    ]
    wrong_leagues = [
        (1090, "Montreal Canadiens", MLS),
        (1091, "Manchester 62", "soccer_france_ligue_one"),
        (1092, "New York Yankees", MLS),
        (1093, "Tottenham Hotspur", "soccer_germany_bundesliga"),
        (1094, "Arsenal Tula", "soccer_italy_serie_a"),
    ]
    sports = sorted({club[2] for club in clubs + wrong_leagues})
    sport_ids = {sport: index for index, sport in enumerate(sports, 1)}
    session.add_all(Sport(id=identifier, key=key, name=key)
                    for key, identifier in sport_ids.items())
    await session.flush()
    session.add_all(
        Team(id=identity, name=name, sport_id=sport_ids[league], espn_id=espn,
             alternate_names=aliases)
        for identity, name, league, espn, aliases in clubs
    )
    session.add_all(Team(id=identity, name=name, sport_id=sport_ids[league])
                    for identity, name, league in wrong_leagues)
    await session.flush()

    played_at = datetime(2026, 11, 1, 12, tzinfo=timezone.utc)
    session.add_all(
        Event(
            sport_id=sport_ids[league],
            home_team_id=identity,
            home_team_name=name,
            away_team_name="Other side",
            commence_time=played_at,
        )
        for identity, name, league, *_ in clubs
    )
    # A venue label alone cannot establish a club or its league.
    session.add_all(
        Event(
            sport_id=sport_ids[league],
            home_team_name=name,
            away_team_name="Another venue label",
            commence_time=played_at,
        )
        for _, name, league in wrong_leagues + [
            (0, "Harvard Crimson - Player Props", EPL),
            (0, "Tottenham", MLS),
        ]
    )
    session.add(User(id=1, firebase_uid="onboarding-search-test"))
    session.add(RetiredTeamRedirect(retired_team_id=14545, canonical_team_id=1040))
    await session.commit()


@pytest.fixture
async def sessions():
    schema = "test_onboarding_13338_" + uuid.uuid4().hex
    engine = create_async_engine(
        DB_URL, execution_options={"schema_translate_map": {None: schema}}
    )
    maker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with engine.begin() as conn:
            await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
            await conn.execute(text(f'SET LOCAL search_path TO "{schema}", public'))
            await conn.run_sync(
                Base.metadata.create_all,
                tables=[model.__table__ for model in (
                    Sport, Team, Event, Venue, TeamIdentityMapping, RetiredTeamRedirect,
                    User, UserFavorite, UserPreference,
                )],
            )
        async with maker() as session:
            await seed_clubs(session)
        yield maker
    finally:
        async with engine.begin() as conn:
            await conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        await engine.dispose()


async def test_twelve_onboarding_queries_return_real_clubs(sessions):
    async with sessions() as db:
        await db.execute(text("SET TRANSACTION READ ONLY"))
        team_ids = set((await db.scalars(select(Team.id))).all())
        for query, first in (ISSUE_SEARCHES | ADDITIONAL_SEARCHES).items():
            results = await search_teams(query, db)
            assert (results[0].name, results[0].sport_key) == first, query
            assert all(result.id in team_ids for result in results), query
            assert all(result.id < 1090 for result in results), query
            assert all(" - " not in result.name for result in results), query


async def test_prefixes_keep_other_clubs_separate_and_group_confirmed_spurs_variants(sessions):
    async with sessions() as db:
        city_results = await search_teams("Manchester", db)
        assert {r.name for r in city_results} == {
            "Manchester City", "Manchester United", "Manchester 62",
        }
        new_york = await search_teams("New York", db)
        assert {r.name for r in new_york} == {
            "New York Knicks", "New York Yankees", "New York Mets", "New York City FC",
        }
        los_angeles = await search_teams("Los Angeles", db)
        assert {r.id for r in los_angeles} == {1030, 1031, 1032, 1033}
        assert {r.id for r in await search_teams("Los", db)} == {1030, 1031, 1032, 1033}
        spurs = await search_teams("Tottenham", db)
        assert [club.id for club in spurs] == [1040]
        assert [(variant.id, variant.sport_key) for variant in spurs[0].sports] == [
            (1040, EPL), (1041, UCL),
        ]
        assert {r.id for r in await search_teams("Spurs", db)} == {1040, 1052}


async def test_save_resolves_old_id_skips_missing_ids_and_saves_the_rest(sessions):
    async with sessions() as db:
        user = await db.get(User, 1)
        ret = await submit_onboarding(
            OnboardingRequest(
                home_location="London",
                follow_teams=[
                    TeamRef(team_id=i)
                    for i in (14545, 1040, 20922, 20927, 20930, 20958, 2**40)
                ],
                alma_mater_teams=[TeamRef(team_id=1050)],
            ),
            user,
            db,
        )
        await db.commit()
        saved = (await db.execute(select(UserFavorite.team_id, UserFavorite.relation_type))).all()
        assert set(saved) == {(1040, "follow"), (1050, "alma_mater")}
        assert ret["onboarding_completed"] is True
        assert ret["skipped_team_ids"] == [20922, 20927, 20930, 20958, 2**40]
        assert ret["message"] == "Saved your preferences. Some selected teams no longer exist."
