"""#7867 on REAL Postgres — the widened roster read and the served payload.

The mocked-session suite beside this (`…_team_paths_7867.py`) answers the
route's queries by statement text, so it cannot see the ONE thing the SQL
change is for: that `_load_team_roster` now returns the sport FAMILY's
`teams` rows (Yomiuri Giants is `baseball_npb`; the MLB event is
`baseball_mlb`) while every pre-existing consumer still receives only the
event's league. A mutant that narrows the query back to the league passes
every mocked test by construction. This file is what convicts it.

It runs the real handler over the real schema (`Base.metadata.create_all` on
the database named by `SEARCH_TEST_DATABASE_URL`, the repo's convention for
`_pg` suites), through the HTTP app with the session dependency pointed at
the disposable database. Redis is NOT required: every cache in the path
fails open, and `debug=1` bypasses them anyway; the arm that measures query
count uses the normal (cached) path so the count is the request's own.

Skips itself, loudly, when no database is named — an unavailable check is
NOT RUN, not passed.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import event as sa_event
from sqlalchemy import text

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

needs_postgres = pytest.mark.skipif(
    not DB_URL,
    reason="set SEARCH_TEST_DATABASE_URL to run the real-Postgres #7867 roster-width test",
)

pytestmark = needs_postgres

NOW = datetime(2026, 9, 23, 20, 0, tzinfo=timezone.utc)

# ── production ids where the public API gave them (2026-09-23) ──────────────
GIANTS, TWINS, TIGERS = 6609, 10739, 10747
YOMIURI, HANSHIN, LOTTE, LG = 12494, 12483, 12796, 12794
ISLANDERS, ISL_TWIN, RANGERS, RANGERS_TWIN, BRIDGEPORT = 54, 6181, 57, 8293, 1347
LYNX, LIBERTY, WOLVES, KNICKS = 13923, 13414, 106, 108
HURRICANES, REDHAWKS, WAKE, BALLST = 900002, 15332, 900020, 15299

MLB_EVENT, NHL_EVENT, WNBA_EVENT, NCAAF_EVENT = 78670001, 78670002, 78670003, 78670004


@pytest.fixture
async def pg_engine():
    from sqlalchemy.ext.asyncio import create_async_engine

    import app.models.models  # noqa: F401
    from app.services.database import Base

    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


async def _seed(conn) -> dict:
    sports = {}
    for key, name in [
        ("baseball_mlb", "MLB"), ("baseball_npb", "NPB"), ("baseball_kbo", "KBO"),
        ("icehockey_nhl", "NHL"), ("icehockey_ahl", "AHL"),
        ("basketball_wnba", "WNBA"), ("basketball_nba", "NBA"),
        ("americanfootball_ncaaf", "NCAAF"), ("americanfootball_nfl", "NFL"),
    ]:
        sports[key] = (await conn.execute(text(
            "INSERT INTO sports (key, name, active) VALUES (:k, :n, true) RETURNING id"
        ), {"k": key, "n": name})).scalar_one()

    teams = [
        # id, sport, name, abbreviation, location, alternate_names
        (GIANTS, "baseball_mlb", "San Francisco Giants", "SF", "San Francisco", ["Giants", "San Francisco"]),
        (TWINS, "baseball_mlb", "Minnesota Twins", "MIN", "Minnesota", ["Twins", "Minnesota"]),
        (TIGERS, "baseball_mlb", "Detroit Tigers", "DET", "Detroit", ["Tigers", "Detroit"]),
        (YOMIURI, "baseball_npb", "Yomiuri Giants", None, None, None),
        (HANSHIN, "baseball_npb", "Hanshin Tigers", None, None, None),
        (LOTTE, "baseball_kbo", "Lotte Giants", None, None, None),
        (LG, "baseball_kbo", "LG Twins", None, None, None),
        (ISLANDERS, "icehockey_nhl", "New York Islanders", "NYI", "New York", ["Islanders", "New York"]),
        (ISL_TWIN, "icehockey_nhl", "New York I", "NYI", None, None),
        (RANGERS, "icehockey_nhl", "New York Rangers", "NYR", "New York", ["Rangers", "New York"]),
        (RANGERS_TWIN, "icehockey_nhl", "New York R", "NYR", None, None),
        (900040, "icehockey_nhl", "New Jersey Devils", "NJ", "New Jersey", ["Devils"]),
        (BRIDGEPORT, "icehockey_ahl", "Bridgeport Islanders", None, None, None),
        (LYNX, "basketball_wnba", "Minnesota Lynx", "MIN", "Minnesota", ["Lynx", "Minnesota"]),
        (LIBERTY, "basketball_wnba", "New York Liberty", "NY", "New York", ["Liberty", "New York"]),
        (WOLVES, "basketball_nba", "Minnesota Timberwolves", "MIN", "Minnesota", ["Timberwolves", "Minnesota"]),
        (KNICKS, "basketball_nba", "New York Knicks", "NY", "New York", ["Knicks", "New York"]),
        (HURRICANES, "americanfootball_ncaaf", "Miami Hurricanes", "MIA", "Miami (FL)", ["Miami (FL)", "Hurricanes"]),
        (REDHAWKS, "americanfootball_ncaaf", "Miami (OH) RedHawks", "M-OH", "Miami (OH)", ["Miami (OH)"]),
        (WAKE, "americanfootball_ncaaf", "Wake Forest Demon Deacons", "WAKE", "Wake Forest", ["Wake Forest"]),
        (BALLST, "americanfootball_ncaaf", "Ball State Cardinals", "BALL", "Ball St.", ["Ball St."]),
        (565, "americanfootball_nfl", "Miami Dolphins", "MIA", "Miami", ["Miami", "Dolphins"]),
    ]
    import json
    for tid, sk, name, abbr, loc, alts in teams:
        await conn.execute(text(
            "INSERT INTO teams (id, sport_id, name, abbreviation, location, alternate_names) "
            "VALUES (:id, :sid, :n, :a, :l, CAST(:alts AS jsonb))"
        ), {"id": tid, "sid": sports[sk], "n": name, "a": abbr, "l": loc,
            "alts": json.dumps(alts) if alts is not None else None})

    events = [
        (MLB_EVENT, "baseball_mlb", "San Francisco Giants", "Minnesota Twins"),
        (NHL_EVENT, "icehockey_nhl", "New Jersey Devils", "New York Islanders"),
        (WNBA_EVENT, "basketball_wnba", "Minnesota Lynx", "New York Liberty"),
        (NCAAF_EVENT, "americanfootball_ncaaf", "Wake Forest Demon Deacons", "Miami Hurricanes"),
    ]
    for eid, sk, home, away in events:
        await conn.execute(text(
            "INSERT INTO events (id, sport_id, home_team_name, away_team_name, commence_time, status) "
            "VALUES (:id, :sid, :h, :a, :ct, 'scheduled')"
        ), {"id": eid, "sid": sports[sk], "h": home, "a": away, "ct": NOW + timedelta(days=2)})

    # market: id, source, external_id, name, llm_sport_category, sport (or None), tier
    markets = [
        (11371619, "kalshi", "KXNPB-26", "Japan NPB Champion", "baseball", None, 1),
        (11371643, "kalshi", "KXKBO-26", "Korea KBO Champion", "baseball", None, 1),
        (114584, "polymarket", "0xws2026", "MLB World Series Champion 2026", "baseball", "baseball_mlb", 1),
        (900300, "polymarket", "0xnhl2027", "NHL: 2027 Champion", "hockey", "icehockey_nhl", 1),
        (900301, "polymarket", "0xahl", "American Hockey League: Winner", "hockey", None, 1),
        (900400, "odds_api", "basketball_wnba_championship_winner", "WNBA Championship Winner", "women's basketball", "basketball_wnba", 1),
        (900401, "odds_api", "basketball_nba_championship_winner", "NBA Championship Winner", "basketball", "basketball_nba", 1),
        (59172719, "kalshi", "KXNCAAFCONFMATCHUP-26MAC", "MAC Conference Championship Matchup", "football", None, 2),
        (52756023, "kalshi", "KXNCAAFACCQUAL-26", "College Football ACC Championship Game Qualifiers", "football", None, 2),
    ]
    for mid, src, ext, name, cat, sk, tier in markets:
        await conn.execute(text(
            "INSERT INTO futures_markets (id, source, external_id, name, category, mutually_exclusive, "
            "status, llm_sport_category, sport_id, market_tier, updated_at) "
            "VALUES (:id, :src, :ext, :n, 'championship', true, 'open', :cat, :sid, :tier, :now)"
        ), {"id": mid, "src": src, "ext": ext, "n": name, "cat": cat,
            "sid": sports[sk] if sk else None, "tier": tier, "now": NOW})

    outcomes = [
        # id, market, name, probability, external_id
        (64406477, 11371619, "Yomiuri Giants", 0.08, "KXNPB-26-YOM"),
        (64406819, 11371643, "LG Twins", 0.155, "KXKBO-26-LG"),
        (78670030, 11371643, "Lotte Giants", 0.01, "KXKBO-26-LOT"),
        (1634483, 114584, "San Francisco Giants", 0.0, "0xws-sf"),
        (78670031, 114584, "Minnesota Twins", None, "0xws-min"),          # unpriced leg
        (78670050, 900301, "Bridgeport Islanders", 0.06, "0xahl-bri"),
        (78670051, 900300, "New York Rangers", 0.03, "0xnhl-nyr"),
        (78670053, 900300, "New York Islanders", 0.02, "0xnhl-nyi"),
        (78670070, 900401, "Minnesota Timberwolves", 0.04, "nba-min"),
        (78670071, 900401, "New York Knicks", 0.09, "nba-ny"),
        (78670072, 900400, "Minnesota Lynx", 0.3, "wnba-min"),
        (78670073, 900400, "New York Liberty", 0.25, "wnba-ny"),
        (225996032, 59172719, "Ball St. vs Miami (OH)", 0.1, "KXNCAAFCONFMATCHUP-26MAC-BALLMOH"),
        (198635142, 52756023, "Miami (FL)", 0.9, "KXNCAAFACCQUAL-26-MIAFL"),
        (206775933, 52756023, "Wake Forest", 0.06, "KXNCAAFACCQUAL-26-WAKE"),
    ]
    for oid, mid, name, prob, ext in outcomes:
        await conn.execute(text(
            "INSERT INTO futures_outcomes (id, market_id, external_id, name, current_probability, last_updated) "
            "VALUES (:id, :mid, :ext, :n, :p, :now)"
        ), {"id": oid, "mid": mid, "ext": ext, "n": name, "p": prob, "now": NOW})
    return sports


class _Counter:
    def __init__(self):
        self.statements: list[str] = []

    def __call__(self, conn, cursor, statement, parameters, context, executemany):
        self.statements.append(statement)


async def _get(monkeypatch, engine, event_id, *, debug=False):
    from unittest.mock import AsyncMock, patch

    from httpx import ASGITransport, AsyncClient
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from app.dependencies.auth import get_optional_user
    from app.main import app
    from app.services.database import get_db, get_db_rw

    monkeypatch.setenv("BYPASS_RATE_LIMITS", "1")
    counter = _Counter()
    sa_event.listen(engine.sync_engine, "before_cursor_execute", counter)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def _db():
        async with maker() as session:
            yield session

    async def _user():
        return None

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_db_rw] = _db
    app.dependency_overrides[get_optional_user] = _user
    try:
        with (
            patch("app.main.init_db", new_callable=AsyncMock),
            patch("app.services.league_context.enrich_event_with_context",
                  new_callable=AsyncMock, return_value=None),
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                url = f"/api/events/{event_id}/related-futures"
                if debug:
                    url += "?debug=1"
                resp = await ac.get(url)
    finally:
        app.dependency_overrides.clear()
        sa_event.remove(engine.sync_engine, "before_cursor_execute", counter)
    assert resp.status_code == 200, resp.text
    return resp.json(), counter.statements


def _ids(body):
    return {r["outcome_id"] for s in ("home_team_futures", "away_team_futures") for r in body[s]}


def _row(body, oid):
    for s in ("home_team_futures", "away_team_futures"):
        for r in body[s]:
            if r["outcome_id"] == oid:
                return r
    return None


async def test_the_family_roster_reaches_the_route_on_real_sql(pg_engine, monkeypatch):
    """The MLB page: NPB/KBO clubs are refused only because the roster read
    really returns them. Narrow the query to the event's league and this
    arm goes red — which no mocked session can show."""
    async with pg_engine.begin() as conn:
        await _seed(conn)
    body, stmts = await _get(monkeypatch, pg_engine, MLB_EVENT, debug=True)
    ids = _ids(body)
    assert not {64406477, 64406819, 78670030} & ids, body
    assert {1634483, 78670031} <= ids
    assert _row(body, 1634483)["probability"] in (0.0, None)
    assert _row(body, 78670031)["probability"] is None
    roster_reads = [s for s in stmts if "FROM teams" in s and "logo_url" in s]
    assert len(roster_reads) == 1, roster_reads
    assert "JOIN sports" in roster_reads[0]


async def test_nhl_wnba_and_ncaaf_pages_on_real_sql(pg_engine, monkeypatch):
    async with pg_engine.begin() as conn:
        await _seed(conn)

    body, _ = await _get(monkeypatch, pg_engine, NHL_EVENT, debug=True)
    ids = _ids(body)
    assert not {78670050, 78670051} & ids, body
    assert 78670053 in ids

    body, _ = await _get(monkeypatch, pg_engine, WNBA_EVENT, debug=True)
    ids = _ids(body)
    # The women's branch narrows the candidate pool to `basketball_wnba` rows,
    # so the NBA market never enters it at all here (the gender filter is a
    # second, independent refusal); asserted so a reader knows this arm does
    # not prove the family read on its own — the MLB arm above does.
    assert not {78670070, 78670071} & ids
    assert {78670072, 78670073} <= ids

    body, _ = await _get(monkeypatch, pg_engine, NCAAF_EVENT, debug=True)
    ids = _ids(body)
    assert 225996032 not in ids, body
    assert {198635142, 206775933} <= ids


async def test_query_count_on_the_normal_request_path(pg_engine, monkeypatch):
    """The request path's own statement count, recorded for the report.

    The candidate adds NO statement: the roster read is the same single
    statement, widened by a JOIN. Asserted as 'exactly one roster read' and the
    total is printed so the base-vs-candidate comparison in REPORT.md is a
    measurement, not an argument."""
    async with pg_engine.begin() as conn:
        await _seed(conn)
    body, stmts = await _get(monkeypatch, pg_engine, MLB_EVENT, debug=False)
    roster_reads = [s for s in stmts if "FROM teams" in s and "logo_url" in s]
    assert len(roster_reads) == 1
    print(f"\nQUERY_COUNT related-futures MLB_EVENT total={len(stmts)} roster_reads={len(roster_reads)}")
    for s in stmts:
        print("  STMT:", " ".join(s.split())[:110])
