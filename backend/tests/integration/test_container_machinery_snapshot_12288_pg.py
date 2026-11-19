"""#12288 — Real PostgreSQL integration contract for `_load_snapshot_from_db` and preview error logging.

PILLAR: DISCOVER · FORMATTING · MATCHING · TRUTH
SHIP: Alex's grouping preview loads every candidate definition in
`backend/data/groupings/candidates/` against real PostgreSQL without failing on
relationship joins (`Sport.key`, `Team` eager loads), executes every SQL statement
in `_load_snapshot_from_db` (events, paired-stage markets, open markets,
verified-title member markets, and history window snapshots), and logs one
warning line naming the `slug` and `exception_class` whenever a grouping becomes
an error item.

Run locally with:
    SEARCH_TEST_DATABASE_URL=postgresql+asyncpg://localhost/bl_searchtest \\
        python3 -m pytest tests/integration/test_container_machinery_snapshot_12288_pg.py -v
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import event as sa_event, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.models import (
    Event,
    FuturesMarket,
    FuturesOddsSnapshot,
    FuturesOutcome,
    Sport,
    Team,
    Venue,
)
from app.utils import container_machinery as cm
from app.utils.container_machinery import (
    _load_snapshot_from_db,
    discover_machinery_candidate_paths,
    evaluate_machinery_candidates_preview,
    load_machinery_definition,
)

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.skipif(
        not DB_URL,
        reason="SEARCH_TEST_DATABASE_URL required for the #12288 container machinery PostgreSQL gate",
    ),
    pytest.mark.asyncio,
]

_TABLES = [
    Sport.__table__,
    Team.__table__,
    Venue.__table__,
    Event.__table__,
    FuturesMarket.__table__,
    FuturesOutcome.__table__,
    FuturesOddsSnapshot.__table__,
]


def _validated_url():
    url = make_url(DB_URL)
    assert url.get_backend_name() == "postgresql", "PostgreSQL gate requires PostgreSQL"
    assert url.database == "bl_searchtest", "Only the disposable bl_searchtest database is permitted"
    return url


async def _seed_all_candidates(session, now_dt: datetime) -> None:
    """Seed real PostgreSQL rows covering every candidate definition in
    `backend/data/groupings/candidates/` (NFL, Oscars, 2028 Presidential, Fed/Macro,
    and NBA) so every SQL statement in `_load_snapshot_from_db` executes and returns
    real rows.
    """
    fresh_iso = (now_dt - timedelta(minutes=5)).isoformat()
    recent_obs = now_dt - timedelta(minutes=5)
    res_future = now_dt + timedelta(days=120)

    nfl = Sport(key="americanfootball_nfl", name="NFL", group="American Football", active=True)
    nba = Sport(key="basketball_nba", name="NBA", group="Basketball", active=True)
    session.add_all([nfl, nba])
    await session.flush()

    bills = Team(
        sport_id=nfl.id,
        name="Buffalo Bills",
        abbreviation="BUF",
        primary_color="#00338D",
        secondary_color="#C60C30",
        logo_url_small="https://a.espncdn.com/i/teamlogos/nfl/500/buf.png",
    )
    chiefs = Team(
        sport_id=nfl.id,
        name="Kansas City Chiefs",
        abbreviation="KC",
        primary_color="#E31837",
        secondary_color="#FFB81C",
        logo_url_small="https://a.espncdn.com/i/teamlogos/nfl/500/kc.png",
    )
    lions = Team(
        sport_id=nfl.id,
        name="Detroit Lions",
        abbreviation="DET",
        primary_color="#0076B6",
        secondary_color="#B0B7BC",
        logo_url_small="https://a.espncdn.com/i/teamlogos/nfl/500/det.png",
    )
    packers = Team(
        sport_id=nfl.id,
        name="Green Bay Packers",
        abbreviation="GB",
        primary_color="#203731",
        secondary_color="#FFB612",
        logo_url_small="https://a.espncdn.com/i/teamlogos/nfl/500/gb.png",
    )
    celtics = Team(
        sport_id=nba.id,
        name="Boston Celtics",
        abbreviation="BOS",
        primary_color="#007A33",
        secondary_color="#BA9653",
        logo_url_small="https://a.espncdn.com/i/teamlogos/nba/500/bos.png",
    )
    cavs = Team(
        sport_id=nba.id,
        name="Cleveland Cavaliers",
        abbreviation="CLE",
        primary_color="#860038",
        secondary_color="#FDBB30",
        logo_url_small="https://a.espncdn.com/i/teamlogos/nba/500/cle.png",
    )
    thunder = Team(
        sport_id=nba.id,
        name="Oklahoma City Thunder",
        abbreviation="OKC",
        primary_color="#007AC1",
        secondary_color="#EF3B24",
        logo_url_small="https://a.espncdn.com/i/teamlogos/nba/500/okc.png",
    )
    nuggets = Team(
        sport_id=nba.id,
        name="Denver Nuggets",
        abbreviation="DEN",
        primary_color="#0E2240",
        secondary_color="#FEC524",
        logo_url_small="https://a.espncdn.com/i/teamlogos/nba/500/den.png",
    )
    session.add_all([bills, chiefs, lions, packers, celtics, cavs, thunder, nuggets])
    await session.flush()

    def _wps(home_prob: float) -> dict:
        return {
            "betting": {
                "value": home_prob,
                "bookmaker_count": 5,
                "updated_at": fresh_iso,
            },
            "kalshi": {
                "value": home_prob,
                "updated_at": fresh_iso,
            },
        }

    session.add_all(
        [
            Event(
                sport_id=nfl.id,
                external_id="pg-nfl-1",
                home_team_id=chiefs.id,
                away_team_id=bills.id,
                home_team_name="Kansas City Chiefs",
                away_team_name="Buffalo Bills",
                commence_time=now_dt + timedelta(hours=18),
                status="scheduled",
                win_probability_sources=_wps(0.52),
            ),
            Event(
                sport_id=nfl.id,
                external_id="pg-nfl-2",
                home_team_id=packers.id,
                away_team_id=lions.id,
                home_team_name="Green Bay Packers",
                away_team_name="Detroit Lions",
                commence_time=now_dt + timedelta(hours=24),
                status="scheduled",
                win_probability_sources=_wps(0.47),
            ),
            Event(
                sport_id=nfl.id,
                external_id="pg-nfl-3",
                home_team_id=bills.id,
                away_team_id=lions.id,
                home_team_name="Buffalo Bills",
                away_team_name="Detroit Lions",
                commence_time=now_dt + timedelta(hours=36),
                status="scheduled",
                win_probability_sources=_wps(0.71),
            ),
            Event(
                sport_id=nfl.id,
                external_id="pg-nfl-4",
                home_team_id=chiefs.id,
                away_team_id=packers.id,
                home_team_name="Kansas City Chiefs",
                away_team_name="Green Bay Packers",
                commence_time=now_dt + timedelta(hours=42),
                status="scheduled",
                win_probability_sources=_wps(0.74),
            ),
            Event(
                sport_id=nba.id,
                external_id="pg-nba-1",
                home_team_id=celtics.id,
                away_team_id=cavs.id,
                home_team_name="Boston Celtics",
                away_team_name="Cleveland Cavaliers",
                commence_time=now_dt + timedelta(hours=12),
                status="scheduled",
                win_probability_sources=_wps(0.54),
            ),
            Event(
                sport_id=nba.id,
                external_id="pg-nba-2",
                home_team_id=thunder.id,
                away_team_id=nuggets.id,
                home_team_name="Oklahoma City Thunder",
                away_team_name="Denver Nuggets",
                commence_time=now_dt + timedelta(hours=15),
                status="scheduled",
                win_probability_sources=_wps(0.51),
            ),
            Event(
                sport_id=nba.id,
                external_id="pg-nba-3",
                home_team_id=cavs.id,
                away_team_id=nuggets.id,
                home_team_name="Cleveland Cavaliers",
                away_team_name="Denver Nuggets",
                commence_time=now_dt + timedelta(hours=30),
                status="scheduled",
                win_probability_sources=_wps(0.72),
            ),
            Event(
                sport_id=nba.id,
                external_id="pg-nba-4",
                home_team_id=celtics.id,
                away_team_id=thunder.id,
                home_team_name="Boston Celtics",
                away_team_name="Oklahoma City Thunder",
                commence_time=now_dt + timedelta(hours=34),
                status="scheduled",
                win_probability_sources=_wps(0.69),
            ),
        ]
    )
    await session.flush()

    async def _add_market(
        *,
        external_id: str,
        name: str,
        category: str,
        outcomes: list[tuple[str, float, float | None]],
        market_id: int | None = None,
        source: str = "kalshi",
        sport_id: int | None = None,
        with_history: bool = False,
    ) -> FuturesMarket:
        kw = {"id": market_id} if market_id is not None else {}
        fm = FuturesMarket(
            **kw,
            source=source,
            external_id=external_id,
            sport_id=sport_id,
            name=name,
            category=category,
            llm_sport_category=category,
            market_tier=1,
            mutually_exclusive=True,
            status="open",
            volume=250_000,
            resolution_date=res_future,
        )
        session.add(fm)
        await session.flush()
        for idx, (o_name, prob, hist_start) in enumerate(outcomes):
            fo = FuturesOutcome(
                market_id=fm.id,
                external_id=f"{external_id}-O{idx}",
                name=o_name,
                current_probability=prob,
                opening_probability=hist_start if hist_start is not None else prob,
                current_yes_bid=max(0.01, round(prob - 0.01, 4)),
                current_yes_ask=min(0.99, round(prob + 0.01, 4)),
                volume=5_000,
                volume_24h=500.0,
                volume_24h_at=recent_obs,
                last_updated=recent_obs,
                price_changed_at=recent_obs,
            )
            session.add(fo)
            await session.flush()
            if with_history:
                start_p = hist_start if hist_start is not None else max(0.05, prob - 0.06)
                mid_p = round((start_p + prob) / 2.0, 4)
                for hours_ago, snap_p in ((120, start_p), (48, mid_p), (2, prob)):
                    session.add(
                        FuturesOddsSnapshot(
                            outcome_id=fo.id,
                            bookmaker=source,
                            probability=snap_p,
                            yes_bid=max(0.01, round(snap_p - 0.01, 4)),
                            yes_ask=min(0.99, round(snap_p + 0.01, 4)),
                            captured_at=now_dt - timedelta(hours=hours_ago),
                            reading_count=1,
                        )
                    )
        return fm

    # 1. Oscars paired-stage register markets (5165726, 27988771, 6173044) + companion markets
    films_s1 = [
        ("The Odyssey", 0.96, 0.92),
        ("You Can See Everything", 0.84, 0.80),
        ("The Black Ball", 0.78, 0.74),
        ("Dune: Part Three", 0.72, 0.70),
    ]
    await _add_market(
        market_id=5165726,
        external_id="KXOSCARNOM-BP-27",
        name="Oscar Nominees: Best Picture",
        category="entertainment",
        outcomes=films_s1,
    )
    await _add_market(
        market_id=27988771,
        source="polymarket",
        external_id="PM-OSCARNOM-BP-27",
        name="Oscars Best Picture Nominees",
        category="entertainment",
        outcomes=films_s1,
    )
    await _add_market(
        market_id=6173044,
        external_id="KXOSCARWIN-BP-27",
        name="Oscar Winner: Best Picture",
        category="entertainment",
        outcomes=[
            ("The Odyssey", 0.42, 0.36),
            ("You Can See Everything", 0.24, 0.26),
            ("The Black Ball", 0.19, 0.21),
            ("Dune: Part Three", 0.15, 0.17),
        ],
        with_history=True,
    )
    await _add_market(
        external_id="KXOSCAR-SUPPACT-27",
        name="Oscar Winner: Best Supporting Actress",
        category="entertainment",
        outcomes=[("Zendaya", 0.38, 0.29), ("Saoirse Ronan", 0.33, 0.37), ("Emily Blunt", 0.29, 0.34)],
        with_history=True,
    )
    await _add_market(
        external_id="KXOSCAR-DIR-27",
        name="Oscar Winner: Best Director",
        category="entertainment",
        outcomes=[
            ("Christopher Nolan", 0.44, 0.40),
            ("Paul Thomas Anderson", 0.31, 0.34),
            ("Denis Villeneuve", 0.25, 0.26),
        ],
    )
    await _add_market(
        external_id="KXOSCAR-ACTOR-27",
        name="Oscar Winner: Best Actor",
        category="entertainment",
        outcomes=[("Matt Damon", 0.41, 0.39), ("Leonardo DiCaprio", 0.34, 0.35), ("Cillian Murphy", 0.25, 0.26)],
    )
    await _add_market(
        external_id="KXOSCAR-ACTRESS-27",
        name="Oscar Winner: Best Actress",
        category="entertainment",
        outcomes=[("Jessie Buckley", 0.43, 0.41), ("Anne Hathaway", 0.32, 0.33), (" Emma Stone", 0.25, 0.26)],
    )

    # 2. NFL markets
    await _add_market(
        external_id="KXNFL-PASSTD-26",
        name="NFL Passing Touchdowns Leader",
        category="football",
        sport_id=nfl.id,
        outcomes=[("Joe Burrow", 0.36, 0.31), ("Josh Allen", 0.34, 0.36), ("Lamar Jackson", 0.30, 0.33)],
    )
    await _add_market(
        external_id="KXNFL-RUSHTD-26",
        name="NFL Rushing Touchdowns Leader",
        category="football",
        sport_id=nfl.id,
        outcomes=[("Derrick Henry", 0.39, 0.35), ("Saquon Barkley", 0.33, 0.35), ("Jahmyr Gibbs", 0.28, 0.30)],
    )
    await _add_market(
        external_id="KXNFL-MVP-26",
        name="NFL MVP Winner",
        category="football",
        sport_id=nfl.id,
        outcomes=[
            ("Josh Allen", 0.38, 0.32),
            ("Lamar Jackson", 0.29, 0.33),
            ("Patrick Mahomes", 0.19, 0.21),
            ("Jared Goff", 0.14, 0.14),
        ],
        with_history=True,
    )
    await _add_market(
        external_id="KXNFL-NFCN-26",
        name="NFC North Champion",
        category="football",
        sport_id=nfl.id,
        outcomes=[("Detroit Lions", 0.51, 0.48), ("Green Bay Packers", 0.33, 0.35), ("Minnesota Vikings", 0.16, 0.17)],
    )
    await _add_market(
        external_id="KXNFL-AFCW-26",
        name="AFC West Champion",
        category="football",
        sport_id=nfl.id,
        outcomes=[("Kansas City Chiefs", 0.53, 0.55), ("Los Angeles Chargers", 0.31, 0.29), ("Denver Broncos", 0.16, 0.16)],
    )

    # 3. NBA markets (supports `machinery-nba-night` as well)
    await _add_market(
        external_id="KXNBA-PPG-26",
        name="NBA Points Per Game Leader",
        category="basketball",
        sport_id=nba.id,
        outcomes=[
            ("Shai Gilgeous-Alexander", 0.41, 0.37),
            ("Luka Doncic", 0.33, 0.35),
            ("Giannis Antetokounmpo", 0.26, 0.28),
        ],
    )
    await _add_market(
        external_id="KXNBA-APG-26",
        name="NBA Assists Per Game Leader",
        category="basketball",
        sport_id=nba.id,
        outcomes=[("Trae Young", 0.42, 0.39), ("Nikola Jokic", 0.33, 0.35), ("Tyrese Haliburton", 0.25, 0.26)],
    )
    await _add_market(
        external_id="KXNBA-MVP-26",
        name="NBA MVP Winner",
        category="basketball",
        sport_id=nba.id,
        outcomes=[
            ("Shai Gilgeous-Alexander", 0.39, 0.34),
            ("Nikola Jokic", 0.32, 0.35),
            ("Victor Wembanyama", 0.17, 0.19),
            ("Jayson Tatum", 0.12, 0.12),
        ],
        with_history=True,
    )
    await _add_market(
        external_id="KXNBA-6MOY-26",
        name="NBA Sixth Man of the Year Winner",
        category="basketball",
        sport_id=nba.id,
        outcomes=[("Payton Pritchard", 0.44, 0.40), ("Malik Monk", 0.31, 0.33), ("Naz Reid", 0.25, 0.27)],
    )
    await _add_market(
        external_id="KXNBA-DPOY-26",
        name="NBA Defensive Player of the Year Winner",
        category="basketball",
        sport_id=nba.id,
        outcomes=[("Victor Wembanyama", 0.48, 0.45), ("Chet Holmgren", 0.29, 0.31), ("Evan Mobley", 0.23, 0.24)],
    )

    # 4. 2028 Presidential markets + history
    await _add_market(
        external_id="KXPRES-PARTY-28",
        name="2028 Presidential Election Winning Party",
        category="politics",
        outcomes=[("Democratic Party", 0.51, 0.48), ("Republican Party", 0.49, 0.52)],
    )
    await _add_market(
        external_id="KXPRES-WIN-28",
        name="2028 Presidential Election Winner",
        category="politics",
        outcomes=[
            ("JD Vance", 0.31, 0.27),
            ("Gavin Newsom", 0.24, 0.26),
            ("Josh Shapiro", 0.23, 0.24),
            ("Marco Rubio", 0.22, 0.23),
        ],
        with_history=True,
    )
    await _add_market(
        external_id="KXPRES-DEMPRIM-28",
        name="2028 Democratic Presidential Primary Winner",
        category="politics",
        outcomes=[("Gavin Newsom", 0.36, 0.29), ("Josh Shapiro", 0.34, 0.39), ("Pete Buttigieg", 0.30, 0.32)],
        with_history=True,
    )
    await _add_market(
        external_id="KXPRES-DEMNOM-28",
        name="2028 Democratic Presidential Nominee",
        category="politics",
        outcomes=[("Gavin Newsom", 0.37, 0.35), ("Josh Shapiro", 0.35, 0.36), ("Gretchen Whitmer", 0.28, 0.29)],
    )
    await _add_market(
        external_id="KXPRES-REPNOM-28",
        name="2028 Republican Presidential Nominee",
        category="politics",
        outcomes=[("JD Vance", 0.49, 0.46), ("Marco Rubio", 0.28, 0.30), ("Ron DeSantis", 0.23, 0.24)],
    )

    # 5. Fed & U.S. Macro markets + history
    await _add_market(
        external_id="KXFED-JAN27",
        name="Fed Decision in Jan 2027",
        category="economics",
        outcomes=[
            ("Cut 50 bps", 0.12, 0.10),
            ("Cut 25 bps", 0.46, 0.39),
            ("No change", 0.34, 0.42),
            ("Hike 25 bps", 0.08, 0.09),
        ],
        with_history=True,
    )
    await _add_market(
        external_id="KXFED-MAR27",
        name="Fed Decision in Mar 2027",
        category="economics",
        outcomes=[("Cut 25 bps", 0.48, 0.39), ("No change", 0.39, 0.47), ("Hike 25 bps", 0.13, 0.14)],
        with_history=True,
    )
    await _add_market(
        external_id="KXFED-END26",
        name="What will the Fed rate be at the end of 2026?",
        category="economics",
        outcomes=[("3.50% - 3.75%", 0.38, 0.36), ("3.75% - 4.00%", 0.37, 0.39), ("4.00% - 4.25%", 0.25, 0.25)],
    )
    await _add_market(
        external_id="KXFED-HIKES26",
        name="How many Fed rate hikes in 2026?",
        category="economics",
        outcomes=[("0 hikes", 0.52, 0.50), ("1 hike", 0.33, 0.35), ("2 hikes", 0.15, 0.15)],
    )
    await _add_market(
        external_id="KXRECESSION-27",
        name="US Recession in 2027?",
        category="economics",
        outcomes=[("Yes", 0.29, 0.26), ("No", 0.71, 0.74)],
    )
    await _add_market(
        external_id="KXGDP-26",
        name="US GDP growth in 2026",
        category="economics",
        outcomes=[("1.0% to 1.5%", 0.24, 0.31), ("1.5% to 2.5%", 0.47, 0.41), ("2.5% to 3.5%", 0.29, 0.28)],
        with_history=True,
    )
    await session.commit()


@pytest.fixture
async def pg_machinery(monkeypatch):
    monkeypatch.setenv("CONTAINERS_READ_CACHE_ENABLED", "false")
    monkeypatch.setenv("VERIFIED_TITLE_CACHE_SECONDS", "0")
    url = _validated_url()
    schema = "machinery_12288_" + uuid4().hex
    admin = create_async_engine(url)
    async with admin.begin() as conn:
        await conn.execute(text(f'CREATE SCHEMA "{schema}"'))

    engine = create_async_engine(
        url,
        connect_args={"server_settings": {"search_path": f'"{schema}", public'}},
    )
    async with engine.begin() as conn:
        for tbl in _TABLES:
            await conn.run_sync(tbl.create)

    maker = async_sessionmaker(engine, expire_on_commit=False)
    now_dt = datetime.now(timezone.utc)
    async with maker() as seed_session:
        await _seed_all_candidates(seed_session, now_dt)

    yield {"maker": maker, "engine": engine, "now_dt": now_dt}

    await engine.dispose()
    async with admin.begin() as conn:
        await conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
    await admin.dispose()


async def test_load_snapshot_from_db_executes_every_query_for_every_candidate_definition(
    pg_machinery,
):
    """Ask 1 + Ask 2: run `_load_snapshot_from_db` against real PostgreSQL for every
    definition in `backend/data/groupings/candidates/` and verify that every SQL
    statement family (events via `Sport.key`, paired-stage register markets, open
    markets, verified-title member markets, and `futures_odds_snapshots` window
    history) executes and returns properly serialized primitives.
    """
    maker = pg_machinery["maker"]
    engine = pg_machinery["engine"]
    now_dt = pg_machinery["now_dt"]

    paths = discover_machinery_candidate_paths()
    assert len(paths) >= 4

    executed_sql: list[str] = []

    def _record_sql(_conn, _cursor, statement, _parameters, _context, _executemany):
        executed_sql.append(statement)

    sa_event.listen(engine.sync_engine, "before_cursor_execute", _record_sql)
    try:
        snapshots_by_slug: dict[str, dict] = {}
        async with maker() as session:
            for path in paths:
                defn = load_machinery_definition(path)
                snap = await _load_snapshot_from_db(session, defn, now_dt=now_dt)
                snapshots_by_slug[defn["slug"]] = snap
    finally:
        sa_event.remove(engine.sync_engine, "before_cursor_execute", _record_sql)

    # Verify events query filtered through Sport.key and serialized plain strings + team data
    nfl_snap = snapshots_by_slug["machinery-nfl-week"]
    assert len(nfl_snap["events"]) >= 2
    ev0 = nfl_snap["events"][0]
    assert ev0["sport"] == "americanfootball_nfl"
    assert ev0["sport_name"] == "NFL"
    assert isinstance(ev0["home_team"], str) and ev0["home_team"]
    assert isinstance(ev0["away_team"], str) and ev0["away_team"]
    assert isinstance(ev0.get("home_team_data"), dict)
    assert ev0["home_team_data"]["logo_small"].startswith("https://")

    # Verify paired_stage, markets, and market_histories queries returned real rows
    oscars_snap = snapshots_by_slug["machinery-oscars-best-picture"]
    assert "oscars-2027-best-picture" in oscars_snap["paired_sets"]
    assert len(oscars_snap["markets"]) >= 4
    assert len(oscars_snap["market_histories"]) >= 1

    pres_snap = snapshots_by_slug["machinery-2028-presidential"]
    assert len(pres_snap["markets"]) >= 4
    assert len(pres_snap["market_histories"]) >= 1

    fed_snap = snapshots_by_slug["machinery-fed-and-macro"]
    assert len(fed_snap["markets"]) >= 5
    assert len(fed_snap["market_histories"]) >= 1

    # Verify every SQL statement family actually ran on PostgreSQL
    joined_sql = "\n".join(executed_sql).lower()
    assert "join sports on events.sport_id = sports.id" in joined_sql
    assert "sports.key in" in joined_sql
    assert "from futures_markets" in joined_sql
    assert "from futures_odds_snapshots" in joined_sql
    assert "row_number() over (partition by futures_odds_snapshots.outcome_id" in joined_sql


async def test_evaluate_machinery_candidates_preview_returns_all_ok_with_zero_error_logs(
    pg_machinery, caplog
):
    """Ask 4 local proof on real PostgreSQL: every candidate definition in
    `backend/data/groupings/candidates/` evaluates to `status: 'ok'` with published
    container sections, passing member-number parity, and zero `machinery_preview_error`
    log lines.
    """
    maker = pg_machinery["maker"]
    now_dt = pg_machinery["now_dt"]
    expected_count = len(discover_machinery_candidate_paths())

    caplog.set_level(logging.WARNING, logger=cm.__name__)
    async with maker() as session:
        items = await evaluate_machinery_candidates_preview(session, now=now_dt)

    assert len(items) == expected_count
    for item in items:
        assert item["status"] == "ok", f"{item['slug']} failed with {item}"
        assert item["container"]["state"] == "published"
        assert item["diversity_report"]["member_number_parity"]["passes"] is True

    error_logs = [r.getMessage() for r in caplog.records if "machinery_preview_error" in r.getMessage()]
    assert error_logs == []


async def test_error_item_logs_slug_and_exception_class_and_keeps_session_usable(
    pg_machinery, monkeypatch, caplog
):
    """Ask 3: when a grouping becomes an error item on a real PostgreSQL session
    (including after an aborted SQL statement), `serve_machinery_candidate_preview`
    logs one line with its `slug` and exception class, rolls back the aborted
    transaction, and still serves the remaining candidate groupings with `status: 'ok'`.
    """
    maker = pg_machinery["maker"]
    now_dt = pg_machinery["now_dt"]
    real_load = cm._load_snapshot_from_db

    async def _explode_on_nfl(db, defn, *args, **kwargs):
        if defn.get("slug") == "machinery-nfl-week":
            # Force a real PostgreSQL statement error so the transaction enters aborted state
            await db.execute(text("SELECT * FROM nonexistent_machinery_table_12288"))
        return await real_load(db, defn, *args, **kwargs)

    monkeypatch.setattr(cm, "_load_snapshot_from_db", _explode_on_nfl)
    caplog.set_level(logging.WARNING, logger=cm.__name__)

    async with maker() as session:
        items = await evaluate_machinery_candidates_preview(session, now=now_dt)

    by_slug = {it["slug"]: it for it in items}
    assert by_slug["machinery-nfl-week"]["status"] == "error"
    for slug, item in by_slug.items():
        if slug != "machinery-nfl-week":
            assert item["status"] == "ok", f"sibling {slug} poisoned by aborted tx: {item}"

    error_logs = [r.getMessage() for r in caplog.records if "machinery_preview_error" in r.getMessage()]
    assert len(error_logs) == 1
    assert "slug=machinery-nfl-week" in error_logs[0]
    assert "ProgrammingError" in error_logs[0]
