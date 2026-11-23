"""Exercise onboarding team selection and save against isolated Postgres and Redis."""

import asyncio
import logging
import os
import socket
import uuid
from datetime import datetime, timezone
from threading import Event as ThreadEvent
from time import perf_counter
from unittest.mock import AsyncMock, patch

import pytest
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
from app.routes import user as user_route
from app.routes.user import OnboardingRequest, TeamRef, search_teams, submit_onboarding
from app.services import onboarding_team_aliases as venue_aliases
from app.services import onboarding_team_membership as membership
from app.services.database import Base, get_db
from app.tasks.task_checkpoint import advisory_lock_key
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from redis import Redis as SyncRedis
from redis.asyncio import Redis
from redis.exceptions import ConnectionError
from sqlalchemy import delete, event, func, select, text, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")
REDIS_URL = os.environ.get("ONBOARDING_TEST_REDIS_URL")
pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not (DB_URL and REDIS_URL),
        reason="set SEARCH_TEST_DATABASE_URL and ONBOARDING_TEST_REDIS_URL",
    ),
]

LA_LIGA = "soccer_spain_la_liga"
EPL = "soccer_epl"
UCL = "soccer_uefa_champs_league"
UCL_WOMEN = "soccer_uefa_champs_league_women"
CLUB_FRIENDLIES = "soccer_club_friendlies"
MLS = "soccer_usa_mls"
NBA = "basketball_nba"
MLB = "baseball_mlb"
NFL = "americanfootball_nfl"
NCAAB = "basketball_ncaab"
NCAAF = "americanfootball_ncaaf"
OTHER = "soccer_other"
SERIE_A = "soccer_italy_serie_a"

ISSUE_SEARCHES = {
    "Real Madrid": ("Real Madrid", LA_LIGA),
    "Manchester": ("Manchester City", EPL),
    "New York": ("New York Yankees", MLB),
    "Los Angeles": ("Los Angeles Lakers", NBA),
    "Tottenham": ("Tottenham Hotspur", EPL),
    "Arsenal": ("Arsenal", EPL),
}
FULL_NAME_SEARCHES = {
    "Real Madrid": ("Real Madrid", LA_LIGA),
    "Manchester City": ("Manchester City", EPL),
    "New York Knicks": ("New York Knicks", NBA),
    "Los Angeles Lakers": ("Los Angeles Lakers", NBA),
    "Tottenham Hotspur": ("Tottenham Hotspur", EPL),
    "Harvard Crimson": ("Harvard Crimson", NCAAB),
}
ADDITIONAL_SEARCHES = {
    "Real Madr": ("Real Madrid", LA_LIGA),
    "Canadiens": ("Montreal Canadiens", "icehockey_nhl"),
    "LAFC": ("Los Angeles FC", MLS),
    "Spurs": ("Tottenham Hotspur", EPL),
    "Harv": ("Harvard Crimson", NCAAB),
    "Magpies": ("Newcastle United", EPL),
}
FABLE_SEARCHES = {
    "Real Madrid": ("Real Madrid", LA_LIGA),
    "Lakers": ("Los Angeles Lakers", NBA),
    "Arsenal": ("Arsenal", EPL),
    "Manchester United": ("Manchester United", EPL),
    "Boston Celtics": ("Boston Celtics", NBA),
    "New York Yankees": ("New York Yankees", MLB),
    "Los Angeles Dodgers": ("Los Angeles Dodgers", MLB),
    "Kansas City Chiefs": ("Kansas City Chiefs", NFL),
    "Tottenham": ("Tottenham Hotspur", EPL),
    "Barcelona": ("Barcelona", LA_LIGA),
}


async def seed_clubs(session):
    clubs = [
        (1001, "Real Madrid", LA_LIGA, "86", ["Madrid"]),
        (1002, "Real Sociedad", LA_LIGA, None, []),
        (1003, "Real Salt Lake", MLS, None, []),
        (1004, "Montreal Canadiens", "icehockey_nhl", None, []),
        (1005, "Oviedo", LA_LIGA, None, []),
        (1006, "Real Betis", LA_LIGA, "244", []),
        (1007, "Barcelona", LA_LIGA, "83", []),
        (1008, "Real Madrid", UCL, "86", []),
        (1009, "Real Madrid", UCL_WOMEN, "22758", []),
        (1010, "Manchester City", EPL, "382", []),
        (1011, "Manchester United", EPL, "360", []),
        (1012, "Manchester 62", OTHER, None, []),
        (1020, "New York Knicks", NBA, None, []),
        (1021, "New York Yankees", MLB, "10", []),
        (1022, "New York Mets", MLB, None, []),
        (1023, "New York City FC", MLS, None, []),
        (1024, "Newcastle United", EPL, None, []),
        (1030, "Los Angeles Lakers", NBA, "13", ["Lakers"]),
        (1031, "Los Angeles Clippers", NBA, None, []),
        (1032, "Los Angeles Dodgers", MLB, None, []),
        (1033, "Los Angeles FC", MLS, None, ["LAFC"]),
        (1034, "Carlos Rivera", "boxing", None, []),
        (1040, "Tottenham Hotspur", EPL, "367", []),
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
        (1053, "Boston Celtics", NBA, "2", []),
        (1054, "Kansas City Chiefs", NFL, "12", []),
        (1055, "Benjamin Torrealba", "tennis_itf", None, []),
        (1060, "Internazionale", SERIE_A, "110", []),
        (1061, "Inter Milan", SERIE_A, "110", []),
        (1062, "Real Madrid", CLUB_FRIENDLIES, "86", []),
    ]
    wrong_leagues = [
        (1090, "Montreal Canadiens", MLS),
        (1091, "Manchester 62", "soccer_france_ligue_one"),
        (1092, "New York Yankees", MLS),
        (1093, "Tottenham Hotspur", "soccer_germany_bundesliga"),
        (1094, "Arsenal Tula", SERIE_A),
        (1095, "Tottenham Hotspur", MLS),
    ]
    sports = sorted({club[2] for club in clubs + wrong_leagues})
    sport_ids = {sport: index for index, sport in enumerate(sports, 1)}
    session.add_all(
        Sport(id=identifier, key=key, name=key) for key, identifier in sport_ids.items()
    )
    await session.flush()
    session.add_all(
        Team(
            id=identity,
            name=name,
            sport_id=sport_ids[league],
            espn_id=espn,
            alternate_names=aliases,
        )
        for identity, name, league, espn, aliases in clubs
    )
    session.add_all(
        Team(id=identity, name=name, sport_id=sport_ids[league])
        for identity, name, league in wrong_leagues
    )
    await session.flush()

    played_at = datetime(2024, 1, 1, 12, tzinfo=timezone.utc)
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
    session.add(
        Event(
            sport_id=sport_ids[SERIE_A],
            away_team_id=1061,
            home_team_name="Other side",
            away_team_name="Inter Milan",
            commence_time=datetime(2024, 1, 2, 12, tzinfo=timezone.utc),
        )
    )
    # A venue label alone cannot establish a club or its league.
    session.add_all(
        Event(
            sport_id=sport_ids[league],
            home_team_name=name,
            away_team_name="Another venue label",
            commence_time=played_at,
        )
        for _, name, league in wrong_leagues
        + [
            (0, "Harvard Crimson - Player Props", EPL),
            (0, "Tottenham", MLS),
        ]
    )
    session.add(User(id=1, firebase_uid="onboarding-search-test"))
    session.add(
        RetiredTeamRedirect(
            retired_team_id=14545,
            canonical_team_id=1040,
            retired_name="Spurs",
            sport_id=sport_ids[EPL],
        )
    )
    session.add(
        TeamIdentityMapping(
            team_id=1024,
            source="odds_api",
            source_name="Magpies",
            sport_key=EPL,
        )
    )
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
                tables=[
                    model.__table__
                    for model in (
                        Sport,
                        Team,
                        Event,
                        Venue,
                        TeamIdentityMapping,
                        RetiredTeamRedirect,
                        User,
                        UserFavorite,
                        UserPreference,
                    )
                ],
            )
        async with maker() as session:
            await seed_clubs(session)
        yield maker
    finally:
        async with engine.begin() as conn:
            await conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        await engine.dispose()


@pytest.fixture
async def cache(monkeypatch):
    key = f"test:onboarding:{uuid.uuid4().hex}"
    monkeypatch.setattr(membership, "_KEY", key)
    async with Redis.from_url(REDIS_URL) as client:
        monkeypatch.setattr(
            membership, "get_shared_async_redis", AsyncMock(return_value=client)
        )
        try:
            yield client
        finally:
            await client.delete(key)


@pytest.fixture
def writer():
    with SyncRedis.from_url(REDIS_URL) as client:
        yield client


async def rebuild(sessions, writer):
    async with sessions.begin() as db:
        return await membership.rebuild_onboarding_team_membership(db, writer)


@pytest.fixture
async def alias_source(sessions):
    source = venue_aliases._alias_refresh_engine(sessions.kw["bind"])
    try:
        yield source
    finally:
        await source.dispose()


@pytest.fixture
async def warmed_sessions(sessions, cache, writer, alias_source):
    await rebuild(sessions, writer)
    await venue_aliases._refresh_aliases(alias_source, sessions.kw["bind"].sync_engine)
    return sessions


@pytest.fixture
async def client(sessions):
    application = FastAPI()
    application.include_router(user_route.router, prefix="/api/me")

    async def override_db():
        async with sessions() as db:
            await db.execute(text("SET TRANSACTION READ ONLY"))
            yield db

    async def override_write_db():
        async with sessions.begin() as db:
            yield db

    async def signed_in_user():
        async with sessions() as db:
            return await db.get(User, 1)

    application.dependency_overrides[get_db] = override_db
    application.dependency_overrides[user_route.get_db_rw] = override_write_db
    application.dependency_overrides[user_route.get_current_user] = signed_in_user
    application.dependency_overrides[user_route.get_optional_user] = signed_in_user
    async with AsyncClient(
        transport=ASGITransport(app=application), base_url="http://test"
    ) as client:
        yield client


async def test_issue_and_additional_onboarding_queries_return_real_clubs(
    warmed_sessions,
):
    sessions = warmed_sessions
    async with sessions() as db:
        await db.execute(text("SET TRANSACTION READ ONLY"))
        team_ids = set((await db.scalars(select(Team.id))).all())
        searches = (
            ISSUE_SEARCHES | FULL_NAME_SEARCHES | ADDITIONAL_SEARCHES | FABLE_SEARCHES
        )
        for query, first in searches.items():
            results = await search_teams(query, db)
            assert (results[0].name, results[0].sport_key) == first, query
            assert all(result.id in team_ids for result in results), query
            assert all(
                variant.id in team_ids
                for result in results
                for variant in result.sports
            ), query
            assert all(result.id < 1090 for result in results), query
            assert all(" - " not in result.name for result in results), query
        real = await search_teams("real", db)
        assert {"Real Madrid", "Real Sociedad", "Real Betis", "Real Salt Lake"} <= {
            row.name for row in real
        }
        assert await search_teams("Benjamin Torrealba", db) == []


async def test_prefixes_keep_other_clubs_separate_and_group_confirmed_spurs_variants(
    warmed_sessions,
):
    async with warmed_sessions() as db:
        city_results = await search_teams("Manchester", db)
        assert {r.name for r in city_results} == {
            "Manchester City",
            "Manchester United",
            "Manchester 62",
        }
        new_york = await search_teams("New York", db)
        assert {r.name for r in new_york} == {
            "New York Knicks",
            "New York Yankees",
            "New York Mets",
            "New York City FC",
        }
        los_angeles = await search_teams("Los Angeles", db)
        assert {r.id for r in los_angeles} == {1030, 1031, 1032, 1033}
        assert {r.id for r in await search_teams("Los", db)} == {1030, 1031, 1032, 1033}
        spurs = await search_teams("Tottenham", db)
        assert [club.id for club in spurs] == [1040]
        assert [(variant.id, variant.sport_key) for variant in spurs[0].sports] == [
            (1040, EPL),
            (1041, UCL),
        ]
        assert {r.id for r in await search_teams("Spurs", db)} == {1040, 1052}
        assert [r.id for r in await search_teams("Magpies", db)] == [1024]


async def test_only_the_top_sixty_name_matches_can_be_verified(sessions, cache, writer):
    async with sessions() as db:
        league_ids = dict(
            (
                await db.execute(
                    select(Sport.key, Sport.id).where(Sport.key.in_((NBA, MLB)))
                )
            ).all()
        )
        candidates = [
            Team(id=3000 + i, name=f"Bounded Club {i:02d}", sport_id=league_ids[NBA])
            for i in range(61)
        ]
        db.add_all(candidates)
        await db.flush()
        played_at = datetime(2024, 1, 1, tzinfo=timezone.utc)
        db.add_all(
            [
                Event(
                    sport_id=league_ids[MLB],
                    home_team_id=candidates[0].id,
                    home_team_name=candidates[0].name,
                    away_team_name="Other side",
                    commence_time=played_at,
                ),
                Event(
                    sport_id=league_ids[NBA],
                    away_team_id=candidates[59].id,
                    home_team_name="Other side",
                    away_team_name=candidates[59].name,
                    commence_time=played_at,
                ),
                Event(
                    sport_id=league_ids[NBA],
                    home_team_id=candidates[60].id,
                    home_team_name=candidates[60].name,
                    away_team_name="Other side",
                    commence_time=played_at,
                ),
            ]
        )
        await db.commit()
        await rebuild(sessions, writer)

        # A fixture lookup would time out behind this lock.
        schema = db.get_bind().get_execution_options()["schema_translate_map"][None]
        await db.execute(text("SET LOCAL statement_timeout = '1s'"))
        async with sessions() as lock:
            await lock.execute(
                text(f'LOCK TABLE "{schema}".events IN ACCESS EXCLUSIVE MODE')
            )
            results = await search_teams("Bounded", db)
        assert [(row.id, row.name) for row in results] == [(3059, "Bounded Club 59")]
        # An exact alias changes the rank of the previously excluded 61st club.
        candidates[60].alternate_names = ["Bounded"]
        await db.commit()
        ranked = await search_teams("Bounded", db)
        assert [(row.id, row.name) for row in ranked] == [(3060, "Bounded Club 60")]


async def test_two_eligible_teams_with_the_same_exact_name_and_league_show_one_row(
    sessions, cache, writer
):
    async with sessions() as db:
        nba_id = await db.scalar(select(Sport.id).where(Sport.key == NBA))
        duplicate = Team(id=2060, name="New York Knicks", sport_id=nba_id)
        db.add(duplicate)
        await db.flush()
        db.add(
            Event(
                sport_id=nba_id,
                away_team_id=duplicate.id,
                home_team_name="Other side",
                away_team_name=duplicate.name,
                commence_time=datetime(2024, 1, 1, tzinfo=timezone.utc),
            )
        )
        await db.commit()
        await rebuild(sessions, writer)

        results = await search_teams("New York Knicks", db)
        assert [(row.id, row.name, row.sport_key) for row in results] == [
            (1020, "New York Knicks", NBA),
        ]


async def test_same_league_espn_duplicate_resolves_to_the_club_with_more_games(
    warmed_sessions,
):
    async with warmed_sessions() as db:
        inter = await search_teams("Inter", db)
        alias_only = await search_teams("Internazionale", db)
        assert [(row.id, row.name) for row in inter] == [(1061, "Inter Milan")]
        assert [(row.id, row.name) for row in alias_only] == [(1061, "Inter Milan")]


async def test_empty_redis_returns_ranked_clubs_then_rebuild_filters(
    sessions, cache, writer, client, caplog
):
    caplog.set_level(logging.INFO, logger=membership.__name__)
    assert not await cache.exists(membership._KEY)
    started = perf_counter()
    params = {"q": "Tottenham"}
    cold = await client.get("/api/me/teams/search", params=params)
    assert perf_counter() - started < 3
    assert cold.status_code == 200
    assert cold.json()[0]["name"] == "Tottenham Hotspur"
    assert cold.json()[0]["sport_key"] == EPL
    assert {row["id"] for row in cold.json()} == {1040, 1093, 1095}
    assert not await cache.exists(membership._KEY)

    receipt = await rebuild(sessions, writer)
    assert receipt["terminal"] == "complete"
    assert await cache.strlen(membership._KEY) == receipt["bytes"]
    warm = await client.get("/api/me/teams/search", params=params)
    assert warm.status_code == 200
    assert [row["id"] for row in warm.json()] == [1040]
    assert [row["id"] for row in warm.json()[0]["sports"]] == [1040, 1041]
    snapshot_lines = [
        record.getMessage()
        for record in caplog.records
        if record.name == membership.__name__
        and "snapshot present=" in record.getMessage()
    ]
    assert len(snapshot_lines) == 2
    assert "present=False age_s=None members=0 bytes=0" in snapshot_lines[0]
    assert f"members={receipt['members']} bytes={receipt['bytes']}" in snapshot_lines[1]
    assert "present=True age_s=" in snapshot_lines[1]
    assert all("Tottenham" not in line for line in snapshot_lines)

    madrid = await client.get("/api/me/teams/search", params={"q": "Real Madrid"})
    assert madrid.status_code == 200
    clubs = madrid.json()
    assert {
        (variant["id"], variant["sport_key"], variant["sport_display"])
        for variant in clubs[0]["sports"]
    } == {
        (1001, LA_LIGA, "La Liga"),
        (1008, UCL, "UEFA Champions League"),
        (1062, CLUB_FRIENDLIES, "Club Friendlies"),
    }
    assert [(club["id"], club["name"], club["sport_key"]) for club in clubs] == [
        (1001, "Real Madrid", LA_LIGA),
        (1009, "Real Madrid (Women)", UCL_WOMEN),
    ]
    assert clubs[1]["sports"] == []


async def test_unreachable_redis_returns_ranked_clubs(client, monkeypatch):
    # Reserve a port without listening, so Redis gets a real connection refusal.
    with socket.socket() as closed:
        closed.bind(("127.0.0.1", 0))
        async with Redis(host="127.0.0.1", port=closed.getsockname()[1]) as offline:
            monkeypatch.setattr(
                membership, "get_shared_async_redis", AsyncMock(return_value=offline)
            )
            started = perf_counter()
            response = await client.get(
                "/api/me/teams/search", params={"q": "Real Madrid"}
            )
    assert perf_counter() - started < 3
    assert response.status_code == 200
    assert response.json()[0]["name"] == "Real Madrid"
    assert response.json()[0]["sport_key"] == LA_LIGA


async def test_snapshot_evicted_during_request_returns_ranked_clubs(
    warmed_sessions, cache, client
):
    assert await cache.exists(membership._KEY)
    execute = cache.execute_command

    async def evict_then_read(*args, **kwargs):
        assert args[0] == "BITFIELD_RO"
        assert await execute("DEL", membership._KEY) == 1
        return await execute(*args, **kwargs)

    with patch.object(cache, "execute_command", wraps=evict_then_read) as lookup:
        response = await client.get("/api/me/teams/search", params={"q": "Tottenham"})
    lookup.assert_awaited_once()
    assert response.status_code == 200
    assert response.json()[0]["id"] == 1040
    assert {row["id"] for row in response.json()} == {1040, 1093, 1095}


async def test_primary_league_clubs_win_nickname_search_with_an_empty_snapshot(
    sessions,
    cache,
    client,
):
    async with sessions.begin() as db:
        other = await db.scalar(select(Sport.id).where(Sport.key == OTHER))
        ncaa = Sport(id=501, key="baseball_ncaa", name="NCAA Baseball")
        db.add(ncaa)
        await db.flush()
        db.add_all(
            [
                Team(
                    id=6081,
                    sport_id=ncaa.id,
                    name="ROOSEVELT Lakers",
                    espn_id="ncaa-lakers",
                    alternate_names=["Lakers"],
                ),
                Team(id=6082, sport_id=other, name="Tottenham"),
            ]
        )

    assert not await cache.exists(membership._KEY)
    for term, first in (
        ("Lakers", "Los Angeles Lakers"),
        ("Tottenham", "Tottenham Hotspur"),
    ):
        response = await client.get("/api/me/teams/search", params={"q": term})
        assert response.status_code == 200
        assert response.json()[0]["name"] == first


async def test_preseason_and_summer_aliases_return_the_saved_parent_club(
    sessions,
    cache,
    client,
    writer,
):
    async with sessions.begin() as db:
        db.add_all(
            [
                Sport(id=501, key="basketball_nba_summer_league", name="Summer League"),
                Sport(id=502, key="baseball_mlb_preseason", name="Spring Training"),
                Sport(
                    id=503, key="americanfootball_nfl_preseason", name="NFL Preseason"
                ),
            ]
        )
        await db.flush()
        db.add_all(
            [
                Team(
                    id=6091,
                    sport_id=501,
                    name="LA Lakers Summer",
                    espn_id="13",
                    alternate_names=["South Bay Summer"],
                ),
                Team(
                    id=6092,
                    sport_id=502,
                    name="NEW YORK YANKEES",
                    alternate_names=["Yankees Spring"],
                ),
                Team(id=6093, sport_id=503, name="Kansas City Chiefs", espn_id="12"),
            ]
        )

    for state in ("missing", "present"):
        if state == "present":
            await rebuild(sessions, writer)
        for query, team_id, sport_key in (
            ("Lakers", 1030, NBA),
            ("South Bay Summer", 1030, NBA),
            ("Yankees Spring", 1021, MLB),
            ("Kansas City Chiefs", 1054, NFL),
        ):
            response = await client.get("/api/me/teams/search", params={"q": query})
            assert response.status_code == 200
            rows = response.json()
            assert [(row["id"], row["sport_key"]) for row in rows] == [
                (team_id, sport_key)
            ]
            assert rows[0]["sports"] == []


async def test_authenticated_onboarding_search_and_save_during_alias_refresh(
    sessions, cache, client, writer, alias_source, monkeypatch
):
    engine = sessions.kw["bind"].sync_engine
    alias_reads = []

    def collect_alias_reads(_conn, _cursor, sql, _params, _context, _many):
        if "team_identity_mapping" in sql:
            alias_reads.append(sql)

    event.listen(engine, "before_cursor_execute", collect_alias_reads)
    try:
        await rebuild(sessions, writer)
        cold = await client.get("/api/me/teams/search", params={"q": "Lakers"})
        assert cold.status_code == 200
        assert cold.json()[0]["id"] == 1030
        cold_alias = await client.get("/api/me/teams/search", params={"q": "Magp"})
        assert cold_alias.status_code == 200
        assert cold_alias.json() == []
        assert alias_reads == []

        await venue_aliases._refresh_aliases(alias_source, engine)
        async with sessions.begin() as db:
            await db.execute(
                update(TeamIdentityMapping)
                .where(TeamIdentityMapping.source_name == "Magpies")
                .values(source_name="Toon Army")
            )
        alias_reads.clear()

        # Hold the real refresh after its read. Request progress and the save
        # must complete while the new copy is still being built.
        started = asyncio.Event()
        release = ThreadEvent()
        loop = asyncio.get_running_loop()
        build = venue_aliases._build_aliases

        def held_build(rows):
            loop.call_soon_threadsafe(started.set)
            if not release.wait(timeout=10):
                raise TimeoutError("test did not release alias projection")
            return build(rows)

        monkeypatch.setattr(venue_aliases, "_build_aliases", held_build)
        monkeypatch.setattr(venue_aliases, "_REFRESH_BUDGET_SECONDS", 10)
        refresh = asyncio.create_task(
            venue_aliases._refresh_aliases(alias_source, engine)
        )
        try:
            async with asyncio.timeout(5):
                await started.wait()
                search = await client.get("/api/me/teams/search", params={"q": "Magp"})
                assert search.status_code == 200
                picked = search.json()[0]
                assert (picked["id"], picked["name"]) == (1024, "Newcastle United")

                saved = await client.post(
                    "/api/me/onboarding",
                    json={"follow_teams": [{"team_id": picked["id"]}]},
                )
                assert saved.status_code == 200
                assert saved.json()["onboarding_completed"] is True
                preferences = await client.get("/api/me/preferences")
                assert preferences.status_code == 200
                assert [
                    (row["team_id"], row["sport_key"], row["relation_type"])
                    for row in preferences.json()["favorites"]
                ] == [(1024, EPL, "follow")]
                assert not refresh.done()
        finally:
            release.set()
            await refresh

        current = await client.get("/api/me/teams/search", params={"q": "Toon"})
        assert current.status_code == 200
        assert current.json()[0]["id"] == 1024
        old = await client.get("/api/me/teams/search", params={"q": "Magp"})
        assert old.status_code == 200
        assert old.json() == []
        assert alias_reads == []
    finally:
        event.remove(engine, "before_cursor_execute", collect_alias_reads)


async def test_timed_out_and_empty_alias_refresh_keep_the_last_copy(
    sessions, alias_source, monkeypatch, caplog
):
    engine = sessions.kw["bind"].sync_engine
    assert isinstance(alias_source.pool, NullPool)
    assert alias_source.pool is not engine.pool
    async with alias_source.connect() as reader:
        assert await reader.scalar(text("SHOW transaction_read_only")) == "on"
        assert await reader.scalar(text("SHOW statement_timeout")) == "2s"
        assert await reader.scalar(text("SHOW lock_timeout")) == "250ms"

    await venue_aliases._refresh_aliases(alias_source, engine)
    async with sessions() as db:
        before = venue_aliases.onboarding_venue_aliases(db)
        assert before.prefix("Magp")

    started = asyncio.Event()

    def observe_slow_query(_conn, _cursor, sql, _params, _context, _many):
        if "pg_sleep" in sql:
            started.set()

    event.listen(alias_source.sync_engine, "before_cursor_execute", observe_slow_query)
    try:
        with monkeypatch.context() as pause:
            pause.setattr(venue_aliases, "_ALIAS_QUERY", select(func.pg_sleep(30)))
            refresh = asyncio.create_task(
                venue_aliases._refresh_aliases(alias_source, engine)
            )
            try:
                async with asyncio.timeout(4):
                    await started.wait()
                    assert engine.pool.checkedout() == 0
                    await refresh
            finally:
                if not refresh.done():
                    refresh.cancel()
                    await asyncio.gather(refresh, return_exceptions=True)
        assert "Onboarding venue alias refresh skipped reason=" in caplog.text
    finally:
        event.remove(
            alias_source.sync_engine, "before_cursor_execute", observe_slow_query
        )

    async with sessions.begin() as db:
        assert venue_aliases.onboarding_venue_aliases(db) is before
        await db.execute(delete(TeamIdentityMapping))
    await venue_aliases._refresh_aliases(alias_source, engine)
    async with sessions() as db:
        assert venue_aliases.onboarding_venue_aliases(db) is before
    assert "Onboarding venue alias refresh skipped reason=empty" in caplog.text


async def test_first_alias_failure_retries_and_then_serves_the_copy(
    sessions, cache, client, monkeypatch
):
    engine = sessions.kw["bind"]
    alias_query = venue_aliases._ALIAS_QUERY
    waits = []
    monkeypatch.setattr(venue_aliases, "_ALIAS_QUERY", text("SELECT 1 / 0"))

    async def record_delay(seconds):
        waits.append(seconds)
        if len(waits) == 1:
            assert engine.sync_engine not in venue_aliases._by_bind
            monkeypatch.setattr(venue_aliases, "_ALIAS_QUERY", alias_query)
            return
        raise asyncio.CancelledError

    monkeypatch.setattr(venue_aliases, "sleep", record_delay)
    with pytest.raises(asyncio.CancelledError):
        await venue_aliases.refresh_onboarding_venue_aliases(engine)

    assert waits == [30, 15 * 60]
    match = await client.get("/api/me/teams/search", params={"q": "Magp"})
    assert match.status_code == 200
    assert (match.json()[0]["id"], match.json()[0]["name"]) == (
        1024,
        "Newcastle United",
    )


async def test_rebuild_has_one_owner_and_failed_publish_keeps_previous_snapshot(
    sessions, cache, writer
):
    async with sessions() as db:
        first = await membership.rebuild_onboarding_team_membership(db, writer)
        assert await db.scalar(text("SHOW statement_timeout")) == "2min"
    assert first["terminal"] == "complete"
    assert first["members"] > 0
    original_members = await cache.get(membership._KEY)
    assert original_members
    assert (7 * 24 - 1) * 60 * 60 < await cache.ttl(membership._KEY) <= 7 * 24 * 60 * 60

    async with sessions() as lock:
        await lock.execute(
            text("SELECT pg_advisory_xact_lock(:key)"),
            {"key": advisory_lock_key(membership._REBUILD_TASK)},
        )
        assert (await rebuild(sessions, writer))["reason"] == "rebuild_already_running"

    with patch.object(writer, "set", side_effect=ConnectionError):
        with pytest.raises(ConnectionError):
            await rebuild(sessions, writer)
    assert await cache.get(membership._KEY) == original_members
    assert (await rebuild(sessions, writer))["terminal"] == "complete"


async def test_empty_rebuild_keeps_last_snapshot_or_ranked_search(
    sessions,
    cache,
    writer,
    client,
    caplog,
):
    assert (await rebuild(sessions, writer))["terminal"] == "complete"
    original = await cache.get(membership._KEY)
    assert original
    async with sessions.begin() as db:
        await db.execute(delete(Event))

    skipped = {"terminal": "skipped", "reason": "no_eligible_teams"}
    assert await rebuild(sessions, writer) == skipped
    assert await cache.get(membership._KEY) == original

    await cache.delete(membership._KEY)
    assert await rebuild(sessions, writer) == skipped
    assert not await cache.exists(membership._KEY)
    searched = await client.get("/api/me/teams/search", params={"q": "Real Madrid"})
    assert searched.status_code == 200
    assert searched.json()[0]["name"] == "Real Madrid"
    assert "Onboarding team membership rebuild found no eligible teams" in caplog.text


async def test_oversized_rebuild_leaves_last_snapshot_in_place(
    sessions, cache, writer, monkeypatch
):
    first = await rebuild(sessions, writer)
    original = await cache.get(membership._KEY)
    monkeypatch.setattr(membership, "_MAX_SNAPSHOT_BYTES", first["bytes"] - 1)
    skipped = await rebuild(sessions, writer)
    assert skipped == {
        "terminal": "skipped",
        "reason": "snapshot_too_large",
        "bytes": first["bytes"],
    }
    assert await cache.get(membership._KEY) == original


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
        saved = (
            await db.execute(select(UserFavorite.team_id, UserFavorite.relation_type))
        ).all()
        assert set(saved) == {(1040, "follow"), (1050, "alma_mater")}
        assert ret["onboarding_completed"] is True
        assert ret["skipped_team_ids"] == [20922, 20927, 20930, 20958, 2**40]
        assert (
            ret["message"]
            == "Saved your preferences. Some selected teams no longer exist."
        )
